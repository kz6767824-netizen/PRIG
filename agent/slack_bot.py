"""
agent/slack_bot.py

Slack bot for PR Impact Guardian (PRIG). Listens for @mentions over Socket
Mode. Two analysis modes:

  SINGLE-TABLE (unchanged from before):
    @PRIG analyze ALTER TABLE orders DROP COLUMN shipping_address;
    @PRIG check ALTER TABLE orders DROP COLUMN shipping_address;
  Follow-ups: report | downstream | fix | patch | severity

  MULTI-TABLE + MULTI-HOP (new):
    @PRIG multi ALTER TABLE orders DROP COLUMN x; ALTER TABLE customers DROP COLUMN y;
  Analyzes every table in the pasted SQL independently, traverses lineage
  2 hops deep (not just direct dependents), and flags when two tables in
  the SAME migration both feed the same downstream dashboard.
  Follow-ups: report | downstream | fix | patch | severity  (same words,
  routed to the multi-table formatter based on which kind of session is
  active in this channel)

  Also: @PRIG notify <team> that <message>

Requires SLACK_BOT_TOKEN (xoxb-...) and SLACK_APP_TOKEN (xapp-...) to be set
as environment variables before running. DATAHUB_GMS_URL and DATAHUB_TOKEN
are optional (default to http://localhost:8081 and no token).
"""

import os
import sys
import re

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext

from parse_migration import parse_migration, parse_multi_table_migration
from report_builder import (
    build_full_report,
    get_downstream_assets,
    get_multi_hop_downstream,
    format_lineage_chains,
)
from severity import classify_migration
from severity_rollup import compute_overall_severity, SEVERITY_RANK, RANK_TO_SEVERITY
from patch_generator import save_patch_file

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
DATAHUB_GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8081")
DATAHUB_TOKEN = os.environ.get("DATAHUB_TOKEN", "")
MULTI_HOP_DEPTH = int(os.environ.get("PRIG_MULTI_HOP_DEPTH", "2"))

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    raise SystemExit("Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN before running this script.")

app = App(token=SLACK_BOT_TOKEN)

# One active analysis per channel. In-memory only -- resets if the bot
# restarts, which is fine for a hackathon demo. Each session dict has a
# "_type" key of "single" or "multi" so answer routing knows which
# formatter to use.
sessions = {}


# ---------------------------------------------------------------------------
# Markdown -> Slack mrkdwn conversion
# ---------------------------------------------------------------------------
# build_full_report() returns standard Markdown (### headers, **bold**,
# pipe tables). Slack's mrkdwn supports none of that natively -- no headers,
# no tables, single-asterisk bold -- so anything coming out of that function
# needs converting before it's posted.

TABLE_ROW_PATTERN = re.compile(r"^\|.*\|$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\|[\s\-:|]+\|$")
HEADER_PATTERN = re.compile(r"^#{1,6}\s*(.+)$")
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _render_table(rows):
    data_rows = [r for r in rows if not TABLE_SEPARATOR_PATTERN.match(r)]
    # Strip ** bold markers here -- code blocks render everything as plain
    # monospace text, so leaving them in just shows literal asterisks.
    parsed = [[c.strip().replace("**", "") for c in r.strip("|").split("|")] for r in data_rows]
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


def markdown_to_slack(text):
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


# ---------------------------------------------------------------------------
# Single-table analysis (unchanged behavior from before)
# ---------------------------------------------------------------------------

def analyze_sql(sql_text, env="PROD"):
    parsed = parse_migration(sql_text)
    table = parsed.get("table")
    operations = parsed.get("operations", [])

    if not table or not operations:
        return None, "Could not parse valid ALTER/DROP operations from that SQL."

    table_urn = f"urn:li:dataset:(urn:li:dataPlatform:postgres,{table},{env})"
    downstream_assets = []
    try:
        client = DataHubClient(server=DATAHUB_GMS_URL, token=DATAHUB_TOKEN)
        with DataHubContext(client):
            downstream_assets = get_downstream_assets(table_urn)
    except Exception as e:
        return None, f"Could not reach DataHub: {e}"

    downstream_count = len(downstream_assets)
    downstream_lookup = {op["column"]: downstream_count for op in operations if op.get("column")}
    pii_lookup = {op["column"]: False for op in operations if op.get("column")}
    classified = classify_migration(operations, downstream_lookup, pii_lookup)
    overall_severity = compute_overall_severity(classified)

    session = {
        "_type": "single",
        "table": table,
        "table_urn": table_urn,
        "operations": operations,
        "downstream_assets": downstream_assets,
        "classified": classified,
        "overall_severity": overall_severity,
    }

    warning = ""
    if parsed.get("ignored_statement_count", 0) > 0:
        warning = (
            f"⚠️ *This migration contains multiple statements — only `{table}` was analyzed. "
            f"Use `multi <SQL>` to analyze every table at once.*\n\n"
        )

    summary = (
        f"{warning}"
        f"*Table:* `{table}`\n"
        f"*Overall Severity:* `{overall_severity}`\n"
        f"*Downstream assets:* {downstream_count}\n\n"
        f"Ask me: `report`, `downstream`, `fix`, `severity`, or `patch`."
    )
    return session, summary


def answer_query_single(query, session):
    q = query.lower()
    table = session["table"]
    operations = session["operations"]
    downstream_assets = session["downstream_assets"]
    classified = session["classified"]
    overall_severity = session["overall_severity"]

    if "report" in q:
        report = build_full_report(
            table=table,
            table_urn=session["table_urn"],
            operations=operations,
            use_llm=False,
            downstream_assets=downstream_assets,
        )
        return markdown_to_slack(report)

    if "downstream" in q or "who" in q or "own" in q:
        if not downstream_assets:
            return f"No active downstream consumers found in DataHub for `{table}`."
        lines = [f"Modifying `{table}` will impact {len(downstream_assets)} downstream asset(s):"]
        for asset in downstream_assets:
            name = asset.get("name") if isinstance(asset, dict) else str(asset)
            asset_type = asset.get("type", "dataset") if isinstance(asset, dict) else ""
            lines.append(f"  - {name} ({asset_type})")
        return "\n".join(lines)

    if "fix" in q or "remediation" in q or "safe" in q:
        return (
            "Safe migration strategy:\n"
            "1. Keep the current column live in production.\n"
            "2. Rename it to `*_deprecated` and create a backward-compatible view.\n"
            "3. Deprecate the column in DataHub and notify asset owners before final removal."
        )

    if "severity" in q or "risk" in q:
        lines = [f"Current migration severity: *{overall_severity}*."]
        for c in classified:
            lines.append(f"  - `{c.get('column')}`: {c.get('severity')} ({c.get('action')})")
        return "\n".join(lines)

    if "patch" in q or "generate" in q:
        try:
            patch_path = save_patch_file(table, operations)
            with open(patch_path, "r") as f:
                patch_sql = f.read()
            return f"Generated safe remediation SQL patch, saved to `{patch_path}`:\n```sql\n{patch_sql}\n```"
        except Exception as e:
            return f"Could not generate patch: {e}"

    return (
        f"Migration on `{table}`: {len(operations)} operations, overall *{overall_severity}*.\n"
        "Ask `report`, `downstream`, `fix`, `severity`, or `patch`."
    )


# ---------------------------------------------------------------------------
# Multi-table + multi-hop analysis (new)
# ---------------------------------------------------------------------------

def analyze_multi_table(sql_text, env="PROD"):
    table_parses = parse_multi_table_migration(sql_text)
    if not table_parses:
        return None, "Could not parse any ALTER/DROP TABLE statements from that SQL."

    try:
        client = DataHubClient(server=DATAHUB_GMS_URL, token=DATAHUB_TOKEN)
    except Exception as e:
        return None, f"Could not create DataHub client: {e}"

    tables = {}
    try:
        with DataHubContext(client):
            for tp in table_parses:
                table = tp["table"]
                operations = tp["operations"]
                table_urn = f"urn:li:dataset:(urn:li:dataPlatform:postgres,{table},{env})"

                downstream_assets, edges = get_multi_hop_downstream(table_urn, max_hops=MULTI_HOP_DEPTH)
                downstream_count = len(downstream_assets)
                downstream_lookup = {op["column"]: downstream_count for op in operations if op.get("column")}
                pii_lookup = {op["column"]: False for op in operations if op.get("column")}
                classified = classify_migration(operations, downstream_lookup, pii_lookup)
                overall_severity = compute_overall_severity(classified)

                tables[table] = {
                    "table_urn": table_urn,
                    "operations": operations,
                    "downstream_assets": downstream_assets,
                    "edges": edges,
                    "classified": classified,
                    "overall_severity": overall_severity,
                }
    except Exception as e:
        return None, f"Could not reach DataHub: {e}"

    # Cross-table effects: does table X's downstream lineage include
    # another table THAT'S ALSO being changed in this same migration?
    # That means changing both together compounds risk on whatever they
    # both feed, and ordering of the changes may matter.
    migration_table_names = set(tables.keys())
    cross_effects = []
    for table, data in tables.items():
        for asset in data["downstream_assets"]:
            name = asset.get("name") if isinstance(asset, dict) else str(asset)
            if name in migration_table_names and name != table:
                cross_effects.append((table, name))

    # Overall severity across the whole migration = worst of any table.
    worst_rank = max(
        (SEVERITY_RANK.get(data["overall_severity"], 0) for data in tables.values()),
        default=0,
    )
    combined_severity = RANK_TO_SEVERITY[worst_rank]

    session = {
        "_type": "multi",
        "tables": tables,
        "table_order": [tp["table"] for tp in table_parses],
        "cross_effects": cross_effects,
        "combined_severity": combined_severity,
    }

    lines = [
        f"*Combined Overall Severity:* `{combined_severity}`",
        f"*Tables analyzed:* {', '.join(f'`{t}`' for t in session['table_order'])}",
        "",
    ]
    for table in session["table_order"]:
        data = tables[table]
        lines.append(f"  • `{table}` — *{data['overall_severity']}*, {len(data['downstream_assets'])} downstream asset(s) within {MULTI_HOP_DEPTH} hop(s)")

    if cross_effects:
        lines.append("")
        lines.append("⚠️ *Cross-table effects detected in this migration:*")
        for src, dst in cross_effects:
            lines.append(f"  - `{src}` feeds `{dst}`, which is *also* being modified in this same migration.")

    lines.append("")
    lines.append("Ask me: `report`, `downstream`, `fix`, `severity`, or `patch`.")

    return session, "\n".join(lines)


def answer_query_multi(query, session):
    q = query.lower()
    tables = session["tables"]
    table_order = session["table_order"]

    if "report" in q:
        parts = []
        for table in table_order:
            data = tables[table]
            report = build_full_report(
                table=table,
                table_urn=data["table_urn"],
                operations=data["operations"],
                use_llm=False,
                downstream_assets=data["downstream_assets"],
            )
            parts.append(markdown_to_slack(report))
        return "\n\n---\n\n".join(parts)

    if "downstream" in q or "who" in q or "own" in q:
        lines = []
        for table in table_order:
            data = tables[table]
            lines.append(f"*`{table}`* ({len(data['downstream_assets'])} downstream within {MULTI_HOP_DEPTH} hop(s)):")
            chain_text = format_lineage_chains(table, data["table_urn"], data["edges"])
            lines.append(f"```{chain_text}```")
        if session["cross_effects"]:
            lines.append("⚠️ *Cross-table effects:*")
            for src, dst in session["cross_effects"]:
                lines.append(f"  - `{src}` -> `{dst}` (also being changed in this migration)")
        return "\n".join(lines)

    if "fix" in q or "remediation" in q or "safe" in q:
        return (
            "Safe migration strategy (applies per table):\n"
            "1. Keep the current column live in production.\n"
            "2. Rename it to `*_deprecated` and create a backward-compatible view.\n"
            "3. Deprecate the column in DataHub and notify asset owners before final removal.\n"
            "4. If cross-table effects were flagged, coordinate the order of changes so a "
            "shared downstream dashboard doesn't see both source tables change at once."
        )

    if "severity" in q or "risk" in q:
        lines = [f"*Combined severity:* `{session['combined_severity']}`"]
        for table in table_order:
            data = tables[table]
            lines.append(f"\n`{table}` — *{data['overall_severity']}*:")
            for c in data["classified"]:
                lines.append(f"  - `{c.get('column')}`: {c.get('severity')} ({c.get('action')})")
        return "\n".join(lines)

    if "patch" in q or "generate" in q:
        parts = []
        for table in table_order:
            data = tables[table]
            try:
                patch_path = save_patch_file(table, data["operations"])
                with open(patch_path, "r") as f:
                    patch_sql = f.read()
                parts.append(f"*`{table}`* — saved to `{patch_path}`:\n```sql\n{patch_sql}\n```")
            except Exception as e:
                parts.append(f"*`{table}`* — could not generate patch: {e}")
        return "\n\n".join(parts)

    lines = [f"Combined severity: *{session['combined_severity']}* across {len(table_order)} table(s)."]
    lines.append("Ask `report`, `downstream`, `fix`, `severity`, or `patch`.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Slack event handling
# ---------------------------------------------------------------------------

NOTIFY_PATTERN = re.compile(r"notify\s+(?:the\s+)?(\S+)\s+(?:team\s+)?that\s+(.+)", re.IGNORECASE)


@app.event("app_mention")
def handle_mention(event, say):
    text = event.get("text", "")
    text = re.sub(r"<@[^>]+>", "", text).strip()
    channel = event.get("channel")

    notify_match = NOTIFY_PATTERN.match(text)
    if notify_match:
        team, message = notify_match.groups()
        say(f":mega: *Notice for {team}:* {message}")
        return

    lower = text.lower()

    if lower.startswith("multi"):
        parts = text.split(None, 1)
        sql_text = parts[1] if len(parts) > 1 else ""
        if not sql_text.strip():
            say("Send SQL after `multi`, e.g. `@PRIG multi ALTER TABLE orders DROP COLUMN x; ALTER TABLE customers DROP COLUMN y;`")
            return
        say("🔍 Analyzing all tables (this can take a bit longer -- multi-hop lineage means several DataHub queries)...")
        session, summary = analyze_multi_table(sql_text)
        if session is None:
            say(f"❌ {summary}")
            return
        sessions[channel] = session
        say(summary)
        return

    if lower.startswith("analyze") or lower.startswith("check"):
        parts = text.split(None, 1)
        sql_text = parts[1] if len(parts) > 1 else ""
        if not sql_text.strip():
            say("Send SQL after `analyze`, e.g. `@PRIG analyze ALTER TABLE orders DROP COLUMN shipping_address;`")
            return
        session, summary = analyze_sql(sql_text)
        if session is None:
            say(f"❌ {summary}")
            return
        sessions[channel] = session
        say(summary)
        return

    session = sessions.get(channel)
    if not session:
        say(
            "No active migration in this channel yet. Start with `@PRIG analyze <SQL>` "
            "(one table) or `@PRIG multi <SQL>` (multiple tables)."
        )
        return

    try:
        if session.get("_type") == "multi":
            say(answer_query_multi(text, session))
        else:
            say(answer_query_single(text, session))
    except Exception as e:
        say(f"❌ Something went wrong answering that: {e}")


if __name__ == "__main__":
    print("⚡️ PRIG Slack bot starting (Socket Mode)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
