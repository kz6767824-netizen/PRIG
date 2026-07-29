from datahub.sdk.main_client import DataHubClient
from datahub_agent_context.context import DataHubContext
from datahub_agent_context.mcp_tools import add_tags

client = DataHubClient(server="http://localhost:8081", token="")

with DataHubContext(client):
    result = add_tags(
        tag_urns=["urn:li:tag:pending-review"],
        entity_urns=["urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)"]
    )
    print(result)	