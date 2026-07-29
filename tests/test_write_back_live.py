"""
test_write_back_live.py

Deliberately SEPARATE from test_live_pipeline.py. This is the one script
in the project whose entire purpose is to perform a REAL write to your
live DataHub instance. Keeping it isolated means:
  - it's easy to review exactly what it does before running it
  - re-running the full pipeline test (test_live_pipeline.py) never
    accidentally re-triggers a live write, since that file stays
    dry_run=True permanently

This applies the 'pending-review-breaking' tag to the 'orders' dataset,
matching the exact scenario just confirmed in dry-run mode:
  - shipping_address DROP -> Breaking
  - loyalty_points ADD -> Safe
  - Overall: Breaking -> tag: pending-review-breaking

After running this, check localhost:9002 -> Manage Tags -> confirm
'pending-review-breaking' now shows '1 entity / 1 Datasets' applied,
the same way you visually confirmed 'pending-review' and 'PII' earlier.
"""

import sys
import os

AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent")
sys.path.insert(0, AGENT_DIR)

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from write_back_tag import write_back_tag

client = DataHubClient(server="http://localhost:8081", token="")

TABLE_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"
OVERALL_SEVERITY = "Breaking"  # matches the confirmed dry-run scenario

with DataHubContext(client):
    print("Performing REAL write-back (dry_run=False) -- confirmed scenario:")
    print(f"  entity: {TABLE_URN}")
    print(f"  overall severity: {OVERALL_SEVERITY}")
    print()
    result = write_back_tag(TABLE_URN, OVERALL_SEVERITY, dry_run=False)
    print()
    print(f"Result: {result}")