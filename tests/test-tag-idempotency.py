"""
test_tag_idempotency.py

Deliberate, isolated live test -- checks whether applying the SAME tag to
the SAME dataset twice increases some kind of count, or is a true no-op
the second time (idempotent), as DataHub's tag model is documented to
behave but which we have NOT yet verified against this live instance.

Run this, then manually check the DataHub UI (Manage Tags page) BEFORE
and AFTER the second call, and compare the "Applied to" count for
pending-review-breaking on the orders dataset.
"""

import sys
import os


AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent")
sys.path.insert(0, AGENT_DIR)
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AGENT_DIR)

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from write_back_tag import write_back_tag

client = DataHubClient(server="http://localhost:8081", token="")

TABLE_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"
OVERALL_SEVERITY = "Breaking"

with DataHubContext(client):
    print("=" * 70)
    print("CALL 1: applying pending-review-breaking to orders")
    print("=" * 70)
    result1 = write_back_tag(TABLE_URN, OVERALL_SEVERITY, dry_run=False)
    print(f"Result 1: {result1}")

    print()
    print(">>> Go check localhost:9002 -> Manage Tags -> pending-review-breaking")
    print(">>> Note the 'Applied to' count right now, THEN press Enter to continue.")
    input(">>> Press Enter once you've checked the count...")

    print()
    print("=" * 70)
    print("CALL 2: applying the SAME tag to the SAME dataset again")
    print("=" * 70)
    result2 = write_back_tag(TABLE_URN, OVERALL_SEVERITY, dry_run=False)
    print(f"Result 2: {result2}")

print()
print("Now go check the 'Applied to' count again.")
print("If it's still the SAME number as before -> confirmed idempotent (no-op).")
print("If it INCREASED -> DataHub is tracking multiple applications, which")
print("would be a real, previously-unverified behavior worth documenting.")