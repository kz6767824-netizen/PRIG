# PRIG Impact Report

> **Mode:** `live`. Includes live downstream lineage counts from your DataHub instance. Breaking/Critical changes are tagged and logged as Context Documents in DataHub automatically.

## File: `.\migrations\test_migration.sql`

**Table:** `orders`

**Mode:** `live` (downstream assets: 3)

**Overall Severity:** `Breaking`



| Operation | Column | Severity |

|---|---|---|

| DROP | `shipping_address` | **Breaking** |

| ADD | `loyalty_points` | **Safe** |



### Downstream Lineage

```mermaid

graph LR
  orders["orders"]
  orders --> orders_d0["customer_summary_dashboard<br/><i>DATASET</i>"]
  orders --> orders_d1["daily_revenue_dashboard<br/><i>DATASET</i>"]
  orders --> orders_d2["regional_sales_dashboard<br/><i>DATASET</i>"]

```



> 🏷️ Tag written to DataHub for `orders` (severity: Breaking).

> 📄 Context Document saved to DataHub for `orders`.

