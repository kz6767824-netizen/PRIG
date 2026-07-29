from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from datahub_agent_context.mcp_tools import list_schema_fields, get_lineage

client = DataHubClient(server="http://localhost:8081", token="")

with DataHubContext(client):
    print("=== Schema fields for 'orders' ===")
    fields = list_schema_fields(urn="urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)")
    print(fields)

    print("\n=== Downstream lineage for 'orders' ===")
    lineage = get_lineage(
    urn="urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)",
    upstream=False
)
    print(lineage)