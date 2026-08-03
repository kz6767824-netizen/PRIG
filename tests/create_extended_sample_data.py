"""
create_extended_sample_data.py

Extends your existing lineage graph (orders -> daily_revenue_dashboard)
into a richer, more realistic one:

    orders          --> daily_revenue_dashboard      (existing)
    orders          --> customer_summary_dashboard   (new)
    orders          --> regional_sales_dashboard      (new)
    customers       --> customer_summary_dashboard   (new)
    customers       --> regional_sales_dashboard      (new)
    order_items     --> inventory_report              (new)
    products        --> inventory_report              (new)

Result: orders ends up with 3 real downstream dependents (previously 1),
customers has 2, order_items and products each have 1. This is the first
time your pipeline will see a real (not mocked) downstream_count > 2,
exercising the "phased deprecation" suggestion branch in explainer.py
against live data for the first time.

Safe to re-run -- this only ADDS new tables/lineage, it does not remove
or modify the existing orders / daily_revenue_dashboard setup.
"""

from datahub.emitter.mce_builder import make_dataset_urn
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    SchemaMetadataClass, SchemaFieldClass, SchemaFieldDataTypeClass,
    StringTypeClass, NumberTypeClass, OtherSchemaClass,
    UpstreamLineageClass, UpstreamClass, DatasetLineageTypeClass,
)
from datahub.emitter.mcp import MetadataChangeProposalWrapper

emitter = DatahubRestEmitter(gms_server="http://localhost:8081")


def emit_dataset(name: str, fields: list):
    """fields: list of (fieldPath, type_class, nativeDataType) tuples."""
    urn = make_dataset_urn(platform="postgres", name=name, env="PROD")
    schema = SchemaMetadataClass(
        schemaName=name,
        platform="urn:li:dataPlatform:postgres",
        version=0,
        hash="",
        platformSchema=OtherSchemaClass(rawSchema=""),
        fields=[
            SchemaFieldClass(fieldPath=fp, type=SchemaFieldDataTypeClass(tc()), nativeDataType=ndt)
            for fp, tc, ndt in fields
        ],
    )
    emitter.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=schema))
    print(f"Created/updated: {name}")
    return urn


def emit_lineage(downstream_urn: str, upstream_urns: list):
    lineage = UpstreamLineageClass(
        upstreams=[
            UpstreamClass(dataset=u, type=DatasetLineageTypeClass.TRANSFORMED)
            for u in upstream_urns
        ]
    )
    emitter.emit(MetadataChangeProposalWrapper(entityUrn=downstream_urn, aspect=lineage))
    print(f"Linked lineage: {upstream_urns} -> {downstream_urn}")


# --- New source tables ---
customers_urn = emit_dataset("customers", [
    ("customer_id", NumberTypeClass, "INT"),
    ("name", StringTypeClass, "VARCHAR"),
    ("email", StringTypeClass, "VARCHAR"),
    ("phone", StringTypeClass, "VARCHAR"),
    ("region", StringTypeClass, "VARCHAR"),
])

products_urn = emit_dataset("products", [
    ("product_id", NumberTypeClass, "INT"),
    ("name", StringTypeClass, "VARCHAR"),
    ("category", StringTypeClass, "VARCHAR"),
    ("price", NumberTypeClass, "DECIMAL"),
])

order_items_urn = emit_dataset("order_items", [
    ("item_id", NumberTypeClass, "INT"),
    ("order_id", NumberTypeClass, "INT"),
    ("product_id", NumberTypeClass, "INT"),
    ("quantity", NumberTypeClass, "INT"),
    ("unit_price", NumberTypeClass, "DECIMAL"),
])

# --- Existing orders table URN (not re-defining its schema, just referencing it) ---
orders_urn = make_dataset_urn(platform="postgres", name="orders", env="PROD")

# --- New downstream dashboards ---
customer_summary_urn = emit_dataset("customer_summary_dashboard", [
    ("customer_id", NumberTypeClass, "INT"),
    ("lifetime_value", NumberTypeClass, "DECIMAL"),
    ("order_count", NumberTypeClass, "INT"),
])

inventory_report_urn = emit_dataset("inventory_report", [
    ("product_id", NumberTypeClass, "INT"),
    ("units_sold", NumberTypeClass, "INT"),
    ("revenue", NumberTypeClass, "DECIMAL"),
])

regional_sales_urn = emit_dataset("regional_sales_dashboard", [
    ("region", StringTypeClass, "VARCHAR"),
    ("total_sales", NumberTypeClass, "DECIMAL"),
])

# --- Lineage: this is what makes orders have 3 downstream, customers have 2 ---
emit_lineage(customer_summary_urn, [orders_urn, customers_urn])
emit_lineage(regional_sales_urn, [orders_urn, customers_urn])
emit_lineage(inventory_report_urn, [order_items_urn, products_urn])

print()
print("Done. Expected downstream counts after this run:")
print("  orders       -> 3 (daily_revenue_dashboard, customer_summary_dashboard, regional_sales_dashboard)")
print("  customers    -> 2 (customer_summary_dashboard, regional_sales_dashboard)")
print("  order_items  -> 1 (inventory_report)")
print("  products     -> 1 (inventory_report)")
print()
print("Verify in the UI: localhost:9002 -> search 'orders' -> Lineage tab -> should now show 3 downstream nodes.")
