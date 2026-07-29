"""
test_live_pipeline.py (v2)

Adds to the previous end-to-end test:
    parse -> build_full_report -> [NEW] compute overall severity ->
    [NEW] write_back_tag(dry_run=True)

dry_run=True is hardcoded in this version on purpose -- this run should
NEVER write anything real to your live DataHub instance. Only after you
review this dry-run output and are ready to confirm, we'll flip it in a
SEPARATE deliberate step (not by editing this file casually).
"""

import sys
import os

AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent")
sys.path.insert(0, AGENT_DIR)

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext

from parse_migration import parse_migration
from report_builder import build_full_report
from severity import classify_migration
from severity_rollup import compute_overall_severity
from write_back_tag import write_back_tag

client = DataHubClient(server="http://localhost:8081", token="")

TABLE_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"

TEST_SQL = """
ALTER TABLE orders
  DROP COLUMN shipping_address,
  ADD COLUMN loyalty_points INT;
"""

print("=" * 70)
print("STEP 1: parse the migration")
print("=" * 70)
parsed = parse_migration(TEST_SQL)
print(parsed)

with DataHubContext(client):
    print()
    print("=" * 70)
    print("STEP 2: build the report (real lineage, real severity)")
    print("=" * 70)
    report = build_full_report(
        table=parsed["table"],
        table_urn=TABLE_URN,
        operations=parsed["operations"],
    )
    print(report)

    print()
    print("=" * 70)
    print("STEP 3: compute overall severity across all operations")
    print("=" * 70)
    # We need the classified operations again here since build_full_report
    # doesn't return them directly -- for this test we recompute using the
    # same live downstream count as a simple stand-in (both operations
    # share the same table-level downstream count, per the documented
    # approximation already in report_builder.py).
    from report_builder import get_downstream_assets

    downstream_assets = get_downstream_assets(TABLE_URN)
    downstream_count = len(downstream_assets)
    downstream_lookup = {
        op.get("column"): downstream_count for op in parsed["operations"] if op.get("column")
    }
    pii_lookup = {op.get("column"): False for op in parsed["operations"] if op.get("column")}

    classified = classify_migration(parsed["operations"], downstream_lookup, pii_lookup)
    for c in classified:
        print(f"  {c['column']}: {c['severity']}")

    overall = compute_overall_severity(classified)
    print(f"\nOverall migration severity: {overall}")

    print()
    print("=" * 70)
    print("STEP 4: write_back_tag -- DRY RUN (no live write will happen)")
    print("=" * 70)
    result = write_back_tag(TABLE_URN, overall, dry_run=True)
    print(f"\nwrite_back_tag returned: {result}")

print()
print("Nothing was written to DataHub in this run (dry_run=True throughout).")
print("Review the output above -- if the tag choice and severity look right,")
print("we'll flip dry_run=False in a separate deliberate step next.")