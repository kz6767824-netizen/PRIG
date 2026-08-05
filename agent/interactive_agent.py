"""
agent/interactive_agent.py

Interactive multi-turn agent for PR Impact Guardian (PRIG).

FIX: the 'report' command now passes the already-fetched downstream_assets
into build_full_report(), matching report_builder.py's restored optional
parameter. This avoids a second, out-of-context DataHub call that would
otherwise crash with "No DataHubClient in context".
"""

import sys
import os

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext

from parse_migration import parse_migration
from report_builder import build_full_report, get_downstream_assets
from severity import classify_migration
from severity_rollup import compute_overall_severity


def run_interactive_loop(table: str, table_urn: str, operations: list, downstream_assets: list):
    downstream_count = len(downstream_assets)
    downstream_lookup = {op["column"]: downstream_count for op in operations if op.get("column")}
    pii_lookup = {op["column"]: False for op in operations if op.get("column")}
    classified = classify_migration(operations, downstream_lookup, pii_lookup)
    overall_severity = compute_overall_severity(classified)

    print(f"\n🚨 Overall Migration Severity: [{overall_severity.upper()}]")
    print("-" * 70)
    print("💡 Commands: report | downstream | fix | patch | severity | exit")
    print("-" * 70)

    while True:
        try:
            query = input("\n👤 Developer > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting session. Goodbye!")
            break

        if not query:
            continue

        q_lower = query.lower()

        if q_lower in ["exit", "quit", "q"]:
            print("👋 Ending PRIG Interactive Session.")
            break

        elif "report" in q_lower:
            print("\n--- Generating Full PRIG Report ---")
            try:
                # FIX: pass the already-fetched downstream_assets so this
                # does NOT try to query DataHub again outside any active
                # DataHubContext.
                report = build_full_report(
                    table=table,
                    table_urn=table_urn,
                    operations=operations,
                    use_llm=False,
                    downstream_assets=downstream_assets,
                )
                print(report)
            except Exception as err:
                print(f"❌ Error generating report: {err}")

        elif "downstream" in q_lower or "break" in q_lower or "who" in q_lower:
            print(f"\n🤖 PRIG Answer:")
            if not downstream_assets:
                print(f"No active downstream consumers found in DataHub for table '{table}'.")
            else:
                print(f"Modifying '{table}' will impact {len(downstream_assets)} downstream asset(s):")
                for asset in downstream_assets:
                    name = asset.get('name') if isinstance(asset, dict) else str(asset)
                    asset_type = asset.get('type', 'dataset') if isinstance(asset, dict) else ''
                    print(f"  - {name} ({asset_type})")

        elif "fix" in q_lower or "remediation" in q_lower or "safe" in q_lower:
            print(f"\n🤖 PRIG Answer:")
            print("Safe migration strategies:")
            print("1. Keep the current column live in production.")
            print("2. Rename it to *_deprecated and create a backward-compatible view.")
            print("3. Deprecate the column in DataHub and notify asset owners before final removal.")

        elif "severity" in q_lower or "risk" in q_lower:
            print(f"\n🤖 PRIG Answer:")
            print(f"Current migration severity: **{overall_severity}**.")
            for c in classified:
                print(f"  - Column '{c.get('column')}': {c.get('severity')} ({c.get('action')})")

        elif "patch" in q_lower or "generate" in q_lower:
            print(f"\n🤖 PRIG Answer:")
            from patch_generator import save_patch_file
            try:
                patch_path = save_patch_file(table, operations)
                print(f"✅ Generated safe remediation SQL patch!")
                print(f"📁 Saved to: `{patch_path}`\n")
                with open(patch_path, "r") as f:
                    print(f.read())
            except Exception as e:
                print(f"❌ Could not generate patch: {e}")
        else:
            print(f"\n🤖 PRIG Answer:")
            print(f"Migration on '{table}': {len(operations)} operations, overall [{overall_severity}].")
            print("Type 'report' for full details, 'fix' for mitigation strategies, or 'patch' to generate SQL.")


def interactive_session(sql_text: str, env: str = "PROD"):
    print("=" * 70)
    print("🤖 PR Impact Guardian (PRIG) — Interactive Session")
    print("=" * 70)

    parsed = parse_migration(sql_text)
    table = parsed.get("table")
    operations = parsed.get("operations", [])

    if not table or not operations:
        print("❌ Could not parse valid ALTER/DROP operations from the SQL provided.")
        return

    table_urn = f"urn:li:dataset:(urn:li:dataPlatform:postgres,{table},{env})"
    print(f"📊 Target Table: '{table}'")
    print(f"🔗 Entity URN: {table_urn}")
    print(f"⚡ Operations Detected: {len(operations)}")
    for op in operations:
        print(f"   - {op.get('action')}: column='{op.get('column')}'")

    print("\n🔍 Querying DataHub Graph Lineage...")
    downstream_assets = []
    try:
        client = DataHubClient(server="http://localhost:8081", token="")
        with DataHubContext(client):
            downstream_assets = get_downstream_assets(table_urn)
    except Exception as e:
        print(f"⚠️ Lineage query notice: {e}")

    print(f"🎯 Downstream Dependents Found: {len(downstream_assets)}")
    for asset in downstream_assets:
        name = asset.get('name') if isinstance(asset, dict) else str(asset)
        print(f"   • {name}")

    run_interactive_loop(table, table_urn, operations, downstream_assets)


if __name__ == "__main__":
    sample_sql = """
    ALTER TABLE orders
      DROP COLUMN shipping_address,
      ADD COLUMN loyalty_points INT;
    """
    interactive_session(sample_sql)