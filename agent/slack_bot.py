"""
agent/slack_bot.py

Slack bot for PR Impact Guardian (PRIG). Listens for @mentions over Socket
Mode, reuses the parsing/lineage/severity/report logic from
interactive_agent.py, and posts answers back into the channel.

Flow:
  1. First message in a channel must include a migration statement:
       @PRIG Asstistance ALTER TABLE orders DROP COLUMN shipping_address;
  2. Follow-up messages in that same channel are treated as questions
     against that loaded migration:
       @PRIG Asstistance downstream
       @PRIG Asstistance report
       @PRIG Asstistance fix
       @PRIG Asstistance patch
       @PRIG Asstistance severity

Requires SLACK_BOT_TOKEN (xoxb-...) and SLACK_APP_TOKEN (xapp-...) to be set
as environment variables before running.
"""

import os
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from interactive_agent import build_session_context, answer_query

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    raise RuntimeError(
        "SLACK_BOT_TOKEN and SLACK_APP_TOKEN must both be set as environment "
        "variables before starting the bot. Run:\n"
        "  set SLACK_BOT_TOKEN=xoxb-...\n"
        "  set SLACK_APP_TOKEN=xapp-...\n"
        "in this same terminal window before running slack_bot.py."
    )

app = App(token=SLACK_BOT_TOKEN)

# One active migration context per channel, kept in memory only.
# Restarting the bot clears all sessions -- fine for a demo.
channel_sessions = {}

MENTION_PATTERN = re.compile(r"<@[^>]+>\s*")
TABLE_ROW_PATTERN = re.compile(r"^\|.*\|$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\|[\s\-:|]+\|$")
HEADER_PATTERN = re.compile(r"^#{1,6}\s*(.+)$")
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def strip_mention(text: str) -> str:
    return MENTION_PATTERN.sub("", text).strip()


def looks_like_sql(text: str) -> bool:
    upper = text.upper()
    return "ALTER TABLE" in upper or "DROP COLUMN" in upper


def _render_table(rows: list) -> list:
    """Turn buffered markdown '| a | b |' rows into an aligned monospace
    table wrapped in a code block, since Slack has no native table support."""
    data_rows = [r for r in rows if not TABLE_SEPARATOR_PATTERN.match(r)]
    parsed = [[c.strip() for c in r.strip("|").split("|")] for r in data_rows]
    if not parsed:
        return []

    col_count = max(len(r) for r in parsed)
    widths = [0] * col_count
    for row in parsed:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    rendered = ["```"]
    for row in parsed:
        padded = [(row[i] if i < len(row) else "").ljust(widths[i]) for i in range(col_count)]
        rendered.append("  ".join(padded).rstrip())
    rendered.append("```")
    return rendered


def markdown_to_slack(text: str) -> str:
    """
    Convert the Markdown produced by report_builder.build_full_report() (and
    similar) into Slack's mrkdwn dialect: no headers, no tables, single-
    asterisk bold instead of double. Backtick code spans already work as-is
    in Slack, so those are left untouched.
    """
    out = []
    table_buffer = []

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        if TABLE_ROW_PATTERN.match(stripped):
            table_buffer.append(stripped)
            continue
        elif table_buffer:
            out.extend(_render_table(table_buffer))
            table_buffer = []

        header_match = HEADER_PATTERN.match(stripped)
        if header_match:
            out.append(f"*{header_match.group(1)}*")
            continue

        out.append(BOLD_PATTERN.sub(r"*\1*", line))

    if table_buffer:
        out.extend(_render_table(table_buffer))

    return "\n".join(out)


@app.event("app_mention")
def handle_mention(event, say):
    raw_text = event.get("text", "")
    channel = event.get("channel")
    text = strip_mention(raw_text)

    if not text:
        say(
            "Give me a migration to analyze, e.g. "
            "`ALTER TABLE orders DROP COLUMN shipping_address;` "
            "or ask `report | downstream | fix | patch | severity` once one is loaded."
        )
        return

    if looks_like_sql(text):
        say("🔍 Analyzing migration...")
        context, error = build_session_context(text)
        if error:
            say(f"❌ {error}")
            return
        channel_sessions[channel] = context
        say(
            f"🚨 *Overall Migration Severity:* `{context['overall_severity'].upper()}`\n"
            f"*Target table:* `{context['table']}`\n"
            f"*Downstream assets found:* {len(context['downstream_assets'])}\n"
            "Ask me: `report` | `downstream` | `fix` | `patch` | `severity`"
        )
        return

    context = channel_sessions.get(channel)
    if not context:
        say(
            "I don't have a migration loaded for this channel yet. Send me "
            "an ALTER/DROP statement first, e.g. "
            "`ALTER TABLE orders DROP COLUMN shipping_address;`"
        )
        return

    try:
        answer = answer_query(
            query=text,
            table=context["table"],
            table_urn=context["table_urn"],
            operations=context["operations"],
            downstream_assets=context["downstream_assets"],
            classified=context["classified"],
            overall_severity=context["overall_severity"],
        )
        answer = markdown_to_slack(answer)
    except Exception as err:
        answer = f"❌ Something went wrong answering that: {err}"

    say(answer)


if __name__ == "__main__":
    print("⚡️ PRIG Slack bot starting (Socket Mode)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
