"""
create_large_sample_data.py

Builds a bigger, more realistic-looking lineage graph on top of what
create_extended_sample_data.py already created. Adds 14 new source tables
and 8 new downstream dashboards/reports with varied upstream counts, so
different tables show different downstream counts (not every column
showing "3" like before).

Also boosts 'orders', 'customers', and 'products' with one extra
downstream dependent each, since those already existed.

Run create_extended_sample_data.py FIRST if you haven't already -- this
script references its output (orders, customers, products, order_items)
by URN without re-declaring their schemas.

Safe to re-run: no randomness, all tables/edges are explicit, so repeated
runs just re-emit the same state.

Requires DATAHUB_TOKEN env var to be set if your DataHub instance has auth
enabled (same token your Slack bot uses).

After running, total tables in DataHub:
  9  (from create_extended_sample_data.py + the original orders/daily_revenue_dashboard)
  + 14 new source tables
  + 8  new downstream dashboards
  = ~31 tables total
"""

import os

from datahub.emitter.mce_builder import make_dataset_urn
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    SchemaMetadataClass, SchemaFieldClass, SchemaFieldDataTypeClass,
    StringTypeClass, NumberTypeClass, BooleanTypeClass, OtherSchemaClass,
    UpstreamLineageClass, UpstreamClass, DatasetLineageTypeClass,
)
from datahub.emitter.mcp import MetadataChangeProposalWrapper

DATAHUB_GMS_URL = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8081")
DATAHUB_TOKEN = os.environ.get("DATAHUB_TOKEN", "")

emitter = DatahubRestEmitter(gms_server=DATAHUB_GMS_URL, token=DATAHUB_TOKEN or None)


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


def ref(name: str):
    """Reference an existing table's URN without re-declaring its schema."""
    return make_dataset_urn(platform="postgres", name=name, env="PROD")


# --- Existing tables from create_extended_sample_data.py (referenced only) ---
orders_urn = ref("orders")
customers_urn = ref("customers")
products_urn = ref("products")
order_items_urn = ref("order_items")

# --- 14 new source tables -------------------------------------------------

suppliers_urn = emit_dataset("suppliers", [
    ("supplier_id", NumberTypeClass, "INT"),
    ("name", StringTypeClass, "VARCHAR"),
    ("country", StringTypeClass, "VARCHAR"),
    ("rating", NumberTypeClass, "DECIMAL"),
])

warehouses_urn = emit_dataset("warehouses", [
    ("warehouse_id", NumberTypeClass, "INT"),
    ("location", StringTypeClass, "VARCHAR"),
    ("capacity", NumberTypeClass, "INT"),
])

shipments_urn = emit_dataset("shipments", [
    ("shipment_id", NumberTypeClass, "INT"),
    ("order_id", NumberTypeClass, "INT"),
    ("warehouse_id", NumberTypeClass, "INT"),
    ("status", StringTypeClass, "VARCHAR"),
    ("shipped_at", StringTypeClass, "TIMESTAMP"),
])

returns_urn = emit_dataset("returns", [
    ("return_id", NumberTypeClass, "INT"),
    ("order_id", NumberTypeClass, "INT"),
    ("product_id", NumberTypeClass, "INT"),
    ("reason", StringTypeClass, "VARCHAR"),
    ("refund_amount", NumberTypeClass, "DECIMAL"),
])

payments_urn = emit_dataset("payments", [
    ("payment_id", NumberTypeClass, "INT"),
    ("order_id", NumberTypeClass, "INT"),
    ("amount", NumberTypeClass, "DECIMAL"),
    ("method", StringTypeClass, "VARCHAR"),
    ("status", StringTypeClass, "VARCHAR"),
])

invoices_urn = emit_dataset("invoices", [
    ("invoice_id", NumberTypeClass, "INT"),
    ("customer_id", NumberTypeClass, "INT"),
    ("amount_due", NumberTypeClass, "DECIMAL"),
    ("due_date", StringTypeClass, "DATE"),
    ("paid", BooleanTypeClass, "BOOLEAN"),
])

subscriptions_urn = emit_dataset("subscriptions", [
    ("subscription_id", NumberTypeClass, "INT"),
    ("customer_id", NumberTypeClass, "INT"),
    ("plan", StringTypeClass, "VARCHAR"),
    ("status", StringTypeClass, "VARCHAR"),
    ("renewed_at", StringTypeClass, "TIMESTAMP"),
])

support_tickets_urn = emit_dataset("support_tickets", [
    ("ticket_id", NumberTypeClass, "INT"),
    ("customer_id", NumberTypeClass, "INT"),
    ("subject", StringTypeClass, "VARCHAR"),
    ("status", StringTypeClass, "VARCHAR"),
    ("priority", StringTypeClass, "VARCHAR"),
])

reviews_urn = emit_dataset("reviews", [
    ("review_id", NumberTypeClass, "INT"),
    ("product_id", NumberTypeClass, "INT"),
    ("customer_id", NumberTypeClass, "INT"),
    ("rating", NumberTypeClass, "INT"),
    ("comment", StringTypeClass, "TEXT"),
])

carts_urn = emit_dataset("carts", [
    ("cart_id", NumberTypeClass, "INT"),
    ("customer_id", NumberTypeClass, "INT"),
    ("status", StringTypeClass, "VARCHAR"),
    ("updated_at", StringTypeClass, "TIMESTAMP"),
])

sessions_urn = emit_dataset("sessions", [
    ("session_id", NumberTypeClass, "INT"),
    ("customer_id", NumberTypeClass, "INT"),
    ("started_at", StringTypeClass, "TIMESTAMP"),
    ("duration_seconds", NumberTypeClass, "INT"),
])

page_views_urn = emit_dataset("page_views", [
    ("view_id", NumberTypeClass, "INT"),
    ("session_id", NumberTypeClass, "INT"),
    ("url", StringTypeClass, "VARCHAR"),
    ("viewed_at", StringTypeClass, "TIMESTAMP"),
])

marketing_campaigns_urn = emit_dataset("marketing_campaigns", [
    ("campaign_id", NumberTypeClass, "INT"),
    ("name", StringTypeClass, "VARCHAR"),
    ("channel", StringTypeClass, "VARCHAR"),
    ("budget", NumberTypeClass, "DECIMAL"),
])

employees_urn = emit_dataset("employees", [
    ("employee_id", NumberTypeClass, "INT"),
    ("name", StringTypeClass, "VARCHAR"),
    ("department", StringTypeClass, "VARCHAR"),
    ("hired_at", StringTypeClass, "DATE"),
])

# --- 8 new downstream dashboards/reports, with varied upstream counts ----

shipping_ops_dashboard_urn = emit_dataset("shipping_ops_dashboard", [
    ("warehouse_id", NumberTypeClass, "INT"),
    ("on_time_rate", NumberTypeClass, "DECIMAL"),
    ("shipment_count", NumberTypeClass, "INT"),
])

finance_summary_dashboard_urn = emit_dataset("finance_summary_dashboard", [
    ("period", StringTypeClass, "VARCHAR"),
    ("revenue", NumberTypeClass, "DECIMAL"),
    ("outstanding_balance", NumberTypeClass, "DECIMAL"),
])

support_analytics_dashboard_urn = emit_dataset("support_analytics_dashboard", [
    ("customer_id", NumberTypeClass, "INT"),
    ("open_tickets", NumberTypeClass, "INT"),
    ("avg_resolution_hours", NumberTypeClass, "DECIMAL"),
])

marketing_performance_dashboard_urn = emit_dataset("marketing_performance_dashboard", [
    ("campaign_id", NumberTypeClass, "INT"),
    ("sessions", NumberTypeClass, "INT"),
    ("conversion_rate", NumberTypeClass, "DECIMAL"),
])

supplier_scorecard_dashboard_urn = emit_dataset("supplier_scorecard_dashboard", [
    ("supplier_id", NumberTypeClass, "INT"),
    ("avg_product_rating", NumberTypeClass, "DECIMAL"),
    ("on_time_delivery_rate", NumberTypeClass, "DECIMAL"),
])

customer_retention_dashboard_urn = emit_dataset("customer_retention_dashboard", [
    ("customer_id", NumberTypeClass, "INT"),
    ("subscription_status", StringTypeClass, "VARCHAR"),
    ("churn_risk_score", NumberTypeClass, "DECIMAL"),
])

returns_analysis_dashboard_urn = emit_dataset("returns_analysis_dashboard", [
    ("product_id", NumberTypeClass, "INT"),
    ("return_rate", NumberTypeClass, "DECIMAL"),
    ("top_reason", StringTypeClass, "VARCHAR"),
])

employee_productivity_dashboard_urn = emit_dataset("employee_productivity_dashboard", [
    ("employee_id", NumberTypeClass, "INT"),
    ("tickets_resolved", NumberTypeClass, "INT"),
    ("avg_response_time_minutes", NumberTypeClass, "DECIMAL"),
])

# --- Lineage edges ---------------------------------------------------------

emit_lineage(shipping_ops_dashboard_urn, [shipments_urn, warehouses_urn])
emit_lineage(finance_summary_dashboard_urn, [payments_urn, invoices_urn, subscriptions_urn])
emit_lineage(support_analytics_dashboard_urn, [support_tickets_urn, customers_urn])
emit_lineage(marketing_performance_dashboard_urn, [marketing_campaigns_urn, sessions_urn, page_views_urn])
emit_lineage(supplier_scorecard_dashboard_urn, [suppliers_urn, products_urn])
emit_lineage(customer_retention_dashboard_urn, [subscriptions_urn, customers_urn, orders_urn])
emit_lineage(returns_analysis_dashboard_urn, [returns_urn, order_items_urn, products_urn])
emit_lineage(employee_productivity_dashboard_urn, [employees_urn, support_tickets_urn])

print()
print("Done. New/updated downstream counts of interest:")
print("  orders     -> 4 (daily_revenue_dashboard, customer_summary_dashboard, regional_sales_dashboard, customer_retention_dashboard)")
print("  customers  -> 4 (customer_summary_dashboard, regional_sales_dashboard, support_analytics_dashboard, customer_retention_dashboard)")
print("  products   -> 3 (inventory_report, supplier_scorecard_dashboard, returns_analysis_dashboard)")
print("  suppliers, warehouses, invoices, etc. -> 1-2 each (new, previously 0)")
print()
print("Verify in the UI: localhost:9002 -> search a table name -> Lineage tab.")
