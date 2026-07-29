"""
test_pii_lookup_v2.py

Now that we know the correct way to write a field-level tag (confirmed from
add_tags()'s real docstring — NOT the schemaField-URN guess from before):

    add_tags(
        tag_urns=["urn:li:tag:PII"],
        entity_urns=["urn:li:dataset:(...)"],
        column_paths=["shipping_address"],
    )

This script:
  1. Writes the PII tag to the 'shipping_address' COLUMN using column_paths
     (not a schemaField URN).
  2. Re-checks list_schema_fields() — expected, per prior verified output,
     to still have no 'tags' key. We check again anyway rather than assume
     the earlier result still holds after a real field-level write.
  3. Re-checks get_entities() on the dataset URN — we already confirmed this
     DOES return a 'tags' key at the dataset level; the open question is
     whether it now also surfaces something at the column/schemaMetadata
     level once a real field tag exists.
  4. Tries get_entity (singular) if it exists, since the add_tags docstring
     referenced it by that name specifically ("Use get_entity tool to
     verify") — we haven't confirmed whether this is a distinct function
     from get_entities or a naming slip in the docstring.
"""

from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from datahub_agent_context.mcp_tools import list_schema_fields, add_tags

try:
    from datahub_agent_context.mcp_tools import get_entities
    HAVE_GET_ENTITIES = True
except ImportError as e:
    HAVE_GET_ENTITIES = False
    print(f"[info] could not import get_entities: {e}")

try:
    from datahub_agent_context.mcp_tools import get_entity
    HAVE_GET_ENTITY = True
except ImportError as e:
    HAVE_GET_ENTITY = False
    print(f"[info] could not import get_entity (singular): {e}")


client = DataHubClient(server="http://localhost:8081", token="")

DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"

with DataHubContext(client):
    print("=" * 70)
    print("STEP 1: add_tags with column_paths=['shipping_address']")
    print("=" * 70)
    try:
        result = add_tags(
            tag_urns=["urn:li:tag:PII"],
            entity_urns=[DATASET_URN],
            column_paths=["shipping_address"],
        )
        print("add_tags() result:", result)
    except Exception as e:
        print(f"add_tags() FAILED: {type(e).__name__}: {e}")

    print()
    print("=" * 70)
    print("STEP 2: list_schema_fields() again — checking for a 'tags' key now")
    print("=" * 70)
    fields = list_schema_fields(urn=DATASET_URN)
    print(fields)

    print()
    print("=" * 70)
    print("STEP 3: get_entities() on the dataset URN — full raw output")
    print("=" * 70)
    if HAVE_GET_ENTITIES:
        try:
            entities = get_entities(urns=[DATASET_URN])
            print(entities)
        except Exception as e:
            print(f"get_entities() FAILED: {type(e).__name__}: {e}")
    else:
        print("get_entities not available — skipped.")

    print()
    print("=" * 70)
    print("STEP 4: get_entity (singular), if it exists")
    print("=" * 70)
    if HAVE_GET_ENTITY:
        try:
            print(get_entity(urn=DATASET_URN))
        except Exception as e:
            print(f"get_entity() FAILED: {type(e).__name__}: {e}")
    else:
        print("get_entity (singular) not available in this package version.")

print()
print("Done. Paste the FULL output back — especially step 2 and step 3,")
print("so we can see exactly where (if anywhere) the field-level PII tag")
print("shows up.")