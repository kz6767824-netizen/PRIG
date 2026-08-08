"""
agent/ci_impact_check.py

Headless CI version of the PR Impact Guardian check, run inside GitHub
Actions. Kept as a real file (not inline in the workflow YAML) so
indentation can't get mangled, and so it's runnable/testable locally
the same way it runs in CI.

Falls back to offline mode (severity via structural risk only, no
lineage, no write-back) if DATAHUB_GMS_URL / DATAHUB_GMS_TOKEN aren't
set or the connection fails -- never raises, so forks without a
DataHub tunnel configured still get a useful check.

MULTI-TABLE ADDITION: previously used parse_migration(), which only ever
returns the FIRST table in a .sql file -- a file with two semicolon-
separated ALTER TABLE statements would silently only get the first one
checked. Now uses parse_multi_table_migration() and loops every table
found in each file, so nothing in a koza's .sql files goes unchecked.

SOURCE TAGGING ADDITION: the combined Context Document write-back now
passes source="github-actions" so the saved document records that it
came from an automated CI run, not a manual Streamlit/Slack check.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parse_migration import parse_multi_table_migration
from severity import classify_migration
from severity_rollup import compute_overall_severity
from lineage_graph import build_mermaid_graph

GMS_URL = os.environ.get("DATAHUB_GMS_URL", "").rstrip("/")
GMS_TOKEN = os.environ.get("DATAHUB_GMS_TOKEN", "")

live_client = None
mode = "offline"

if GMS_URL and GMS_TOKEN:
    try:
        from datahub.sdk.main_client import DataHubClient
        live_client = DataHubClient(server=GMS_URL, token=GMS_TOKEN)
        mode = "live"
    except Exception as e:
        print(f"[ci_impact_check] Live client init failed, falling back to offline: {e}")
        mode = "offline"

reports = []
any_critical = False
context_doc_entries = []  # collected across ALL files/tables, written as ONE combined document at the end

for root, dirs, files in os.walk('.'):
    if 'patches' in root.split(os.sep):
        continue
    for f in files:
        if not f.endswith('.sql'):
            continue
        path = os.path.join(root, f)
        with open(path, 'r') as file:
            sql = file.read()

        table_parses = parse_multi_table_migration(sql)
        if not table_parses:
            continue

        if len(table_parses) > 1:
            table_names = ", ".join(f"`{tp['table']}`" for tp in table_parses)
            reports.append(f"## File: `{path}` — {len(table_parses)} tables detected: {table_names}\n")
        else:
            reports.append(f"## File: `{path}`")

        for tp in table_parses:
            table = tp['table']
            ops = tp['operations']
            table_urn = f"urn:li:dataset:(urn:li:dataPlatform:postgres,{table},PROD)"
            downstream_assets = []

            if mode == "live":
                try:
                    from datahub_agent_context.context import DataHubContext
                    from report_builder import get_downstream_assets
                    with DataHubContext(live_client):
                        downstream_assets = get_downstream_assets(table_urn)
                except Exception as e:
                    print(f"[ci_impact_check] Lineage lookup failed for {table}: {e}")
                    downstream_assets = []

            downstream_count = len(downstream_assets)
            downstream_lookup = {op.get('column'): downstream_count for op in ops if op.get('column')}
            pii_lookup = {op.get('column'): False for op in ops if op.get('column')}

            classified = classify_migration(ops, downstream_lookup, pii_lookup)
            overall = compute_overall_severity(classified)

            if any(c['severity'] == 'Critical' for c in classified):
                any_critical = True

            reports.append(f"### Table: `{table}`")
            reports.append(f"**Mode:** `{mode}`" + (f" (downstream assets: {downstream_count})" if mode == "live" else ""))
            reports.append(f"**Overall Severity:** `{overall}`")
            reports.append("")
            reports.append("| Operation | Column | Severity |")
            reports.append("|---|---|---|")
            for c in classified:
                col = c.get('column', 'N/A')
                reports.append(f"| {c['action']} | `{col}` | **{c['severity']}** |")
            reports.append("")

            reports.append("#### Downstream Lineage")
            reports.append("```mermaid")
            reports.append(build_mermaid_graph(table, downstream_assets))
            reports.append("```")
            reports.append("")

            if mode == "live" and overall in ("Breaking", "Critical"):
                try:
                    from datahub_agent_context.context import DataHubContext
                    from write_back_tag import write_back_tag
                    from report_builder import build_full_report

                    with DataHubContext(live_client):
                        tag_result = write_back_tag(table_urn, overall, dry_run=False, server=GMS_URL, token=GMS_TOKEN)
                        if tag_result:
                            reports.append(f"> \U0001F3F7\uFE0F Tag written to DataHub for `{table}` (severity: {overall}).")

                        full_report = build_full_report(
                            table=table, table_urn=table_urn, operations=ops,
                            use_llm=False, downstream_assets=downstream_assets,
                        )
                        # NOT written individually anymore -- collected here and
                        # written as ONE combined Context Document covering every
                        # Breaking/Critical table across the whole PR, after the
                        # full scan below finishes.
                        context_doc_entries.append({
                            "table": table,
                            "table_urn": table_urn,
                            "report_content": full_report,
                            "overall_severity": overall,
                        })
                    reports.append("")
                except Exception as e:
                    print(f"[ci_impact_check] Tag write-back failed for {table}: {e}")
                    reports.append(f"> \u26A0\uFE0F Tag write-back to DataHub failed: {e}")
                    reports.append("")

if mode == "live" and context_doc_entries:
    try:
        from datahub_agent_context.context import DataHubContext
        from write_back_context_document import write_back_combined_context_document

        with DataHubContext(live_client):
            doc_result = write_back_combined_context_document(
                tables=context_doc_entries, dry_run=False, source="github-actions"
            )
        if doc_result:
            table_list = ", ".join(f"`{t['table']}`" for t in context_doc_entries)
            reports.append(
                f"> \U0001F4C4 One combined Context Document saved to DataHub, "
                f"covering {len(context_doc_entries)} table(s): {table_list}"
            )
    except Exception as e:
        print(f"[ci_impact_check] Combined context document write-back failed: {e}")
        reports.append(f"> \u26A0\uFE0F Combined Context Document write-back failed: {e}")

if mode == "live":
    note = (
        "> **Mode:** `live`. Includes live downstream lineage counts from "
        "your DataHub instance. Breaking/Critical changes are tagged "
        "individually per table; a single combined Context Document covering "
        "every Breaking/Critical table in this PR is saved to DataHub. Files "
        "with multiple `ALTER TABLE` statements are fully analyzed, one "
        "section per table.\n"
    )
else:
    note = (
        "> **Mode:** `offline`. No DataHub connection configured or reachable "
        "-- severity reflects structural risk only. No write-back performed. "
        "Files with multiple `ALTER TABLE` statements are fully analyzed, one "
        "section per table.\n"
    )

header = "# koza Impact Report\n\n" + note + "\n"
body = "\n\n".join(reports) if reports else "_No recognizable SQL operations found._"

os.makedirs('koza-reports', exist_ok=True)
with open('koza-reports/offline-impact-report.md', 'w', encoding='utf-8') as out:
    out.write(header + body)

github_output = os.environ.get('GITHUB_OUTPUT')
if github_output:
    with open(github_output, 'a') as gh_out:
        gh_out.write(f"any_critical={'true' if any_critical else 'false'}\n")

print(f"[ci_impact_check] Report generated. mode={mode} any_critical={any_critical}")
