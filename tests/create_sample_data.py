from datahub.emitter.mce_builder import make_dataset_urn
from datahub.emitter.mcp_builder import DatahubKey
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    SchemaMetadataClass, SchemaFieldClass, SchemaFieldDataTypeClass,
    StringTypeClass, NumberTypeClass, OtherSchemaClass,
    UpstreamLineageClass, UpstreamClass, DatasetLineageTypeClass,
)
from datahub.emitter.mcp import MetadataChangeProposalWrapper

emitter = DatahubRestEmitter(gms_server="http://localhost:8081")

# --- Define the 'orders' table ---
orders_urn = make_dataset_urn(platform="postgres", name="orders", env="PROD")

orders_schema = SchemaMetadataClass(
    schemaName="orders",
    platform="urn:li:dataPlatform:postgres",
    version=0,
    hash="",
    platformSchema=OtherSchemaClass(rawSchema=""),
    fields=[
        SchemaFieldClass(fieldPath="order_id", type=SchemaFieldDataTypeClass(NumberTypeClass()), nativeDataType="INT"),
        SchemaFieldClass(fieldPath="customer_id", type=SchemaFieldDataTypeClass(NumberTypeClass()), nativeDataType="INT"),
        SchemaFieldClass(fieldPath="total_amount", type=SchemaFieldDataTypeClass(NumberTypeClass()), nativeDataType="DECIMAL"),
        SchemaFieldClass(fieldPath="shipping_address", type=SchemaFieldDataTypeClass(StringTypeClass()), nativeDataType="VARCHAR"),
    ],
)

emitter.emit(MetadataChangeProposalWrapper(entityUrn=orders_urn, aspect=orders_schema))

# --- Define the downstream 'daily_revenue_dashboard' table ---
dashboard_urn = make_dataset_urn(platform="postgres", name="daily_revenue_dashboard", env="PROD")

dashboard_schema = SchemaMetadataClass(
    schemaName="daily_revenue_dashboard",
    platform="urn:li:dataPlatform:postgres",
    version=0,
    hash="",
    platformSchema=OtherSchemaClass(rawSchema=""),
    fields=[
        SchemaFieldClass(fieldPath="report_date", type=SchemaFieldDataTypeClass(StringTypeClass()), nativeDataType="DATE"),
        SchemaFieldClass(fieldPath="revenue_total", type=SchemaFieldDataTypeClass(NumberTypeClass()), nativeDataType="DECIMAL"),
    ],
)

emitter.emit(MetadataChangeProposalWrapper(entityUrn=dashboard_urn, aspect=dashboard_schema))

# --- Connect them: dashboard depends on orders ---
lineage = UpstreamLineageClass(
    upstreams=[
        UpstreamClass(dataset=orders_urn, type=DatasetLineageTypeClass.TRANSFORMED)
    ]
)

emitter.emit(MetadataChangeProposalWrapper(entityUrn=dashboard_urn, aspect=lineage))

print("Sample data created successfully!")
print(f"Orders table: {orders_urn}")
print(f"Dashboard table: {dashboard_urn}")