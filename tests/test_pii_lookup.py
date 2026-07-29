"""
test_pii_lookup.py

Investigates two unknowns, in order:
  1. Can we actually apply a tag to a specific COLUMN (not the whole
     dataset) using the Agent Context Kit's add_tags()? This requires a
     schemaField-level URN, which has NOT been verified against your
     installed package yet.
  2. Once a field-level PII tag exists for real, which retrieval method
     actually surfaces it: list_schema_fields() (already confirmed to NOT
     have a 'tags' key), get_entities(), or search()?

Run this from the same venv/terminal setup you've used for the other
test scripts (remember: `set DATAHUB_MAPPED_GMS_PORT=8081` first if it's
a new terminal window). Paste the FULL raw output back — every print()
here is there so we can see exactly what came back, not just whether it
"worked".
"""

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from datahub_agent_context.mcp_tools import list_schema_fields, add_tags

# Import extras defensively — we don't yet know which of these exist
# in your installed version of the package, so failing to import one
# is itself useful information, not a script bug.
try:
    from datahub_agent_context.mcp_tools import get_entities
    HAVE_GET_ENTITIES = True
except ImportError as e:
    HAVE_GET_ENTITIES = False
    print(f"[info] could not import get_entities: {e}")

try:
    from datahub_agent_context.mcp_tools import search
    HAVE_SEARCH = True
except ImportError as e:
    HAVE_SEARCH = False
    print(f"[info] could not import search: {e}")


client = DataHubClient(server="http://localhost:8081", token="")

DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"
# Guessed schemaField URN format — this is the actual thing being tested,
# not assumed to be correct.
FIELD_URN = f"urn:li:schemaField:({DATASET_URN},shipping_address)"

with DataHubContext(client):
    print("=" * 70)
    print("STEP 1: attempt to tag the 'shipping_address' FIELD as PII")
    print("=" * 70)
    print(f"Using field URN guess: {FIELD_URN}")

    try:
        result = add_tags(
            tag_urns=["urn:li:tag:PII"],
            entity_urns=[FIELD_URN],
        )
        print("add_tags() result:", result)
    except Exception as e:
        print(f"add_tags() FAILED with exception: {type(e).__name__}: {e}")
        print("(This itself is useful — it may mean this URN format is wrong,")
        print(" or that the 'PII' tag entity doesn't exist yet and needs to")
        print(" be created first via the DataHub UI, same as 'pending-review' was.)")

    print()
    print("=" * 70)
    print("STEP 2a: re-check list_schema_fields() (expected: still no 'tags' key)")
    print("=" * 70)
    fields = list_schema_fields(urn=DATASET_URN)
    print(fields)

    print()
    print("=" * 70)
    print("STEP 2b: try get_entities() on the dataset and on the field URN")
    print("=" * 70)
    if HAVE_GET_ENTITIES:
        try:
            print("-- get_entities on dataset URN --")
            print(get_entities(urns=[DATASET_URN]))
        except Exception as e:
            print(f"get_entities(dataset) FAILED: {type(e).__name__}: {e}")
        try:
            print("-- get_entities on field URN --")
            print(get_entities(urns=[FIELD_URN]))
        except Exception as e:
            print(f"get_entities(field) FAILED: {type(e).__name__}: {e}")
    else:
        print("get_entities not available in this package version — skipped.")

    print()
    print("=" * 70)
    print("STEP 2c: try search() for the PII tag")
    print("=" * 70)
    if HAVE_SEARCH:
        try:
            print(search(query="tags:PII"))
        except Exception as e:
            print(f"search(query='tags:PII') FAILED: {type(e).__name__}: {e}")
        try:
            print(search(query="tag:PII"))
        except Exception as e:
            print(f"search(query='tag:PII') FAILED: {type(e).__name__}: {e}")
    else:
        print("search not available in this package version — skipped.")

print()
print("Done. Paste the full output back so we can see which method, if any,")
print("actually surfaced the field-level PII tag.")