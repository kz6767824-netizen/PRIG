# Example: Breaking — Dropping a Column with a Downstream Dependent

**Input SQL:**
```sql
ALTER TABLE orders DROP COLUMN shipping_address;
```

![Overall Severity: Breaking](https://img.shields.io/badge/Overall%20Severity-Breaking-red?style=for-the-badge)

---

## PR Impact Report: `orders`

### Column: `shipping_address`
![Breaking](https://img.shields.io/badge/shipping__address-Breaking-red)

- **Table:** `orders`
- **Severity:** `Breaking`

**Downstream impact:** 1 asset(s) found in DataHub:
- `daily_revenue_dashboard` (dataset)

**Suggestion:** Dependencies checked against DataHub's lineage graph — affected downstream asset(s): `daily_revenue_dashboard`; please review before merging. Coordinate with the owner(s) of these asset(s) before merging. A short deprecation window reduces risk compared to an immediate drop.

---

**Note:** These suggestions reflect general best-practice patterns and do not account for your team's specific constraints, release cycle, compliance deadlines, or urgency. A human reviewer should confirm this approach fits the actual situation before merging.

Severity classification is fully deterministic and reproducible. If an LLM-generated explanation is used instead of the template, its exact wording may vary slightly between runs on the same input — the severity label itself will not.

**PII detection:** this version does not attempt automatic column-level PII detection. Live testing confirmed the tag WRITE path works (`add_tags` with `column_paths`), but no read path currently available through the Agent Context Kit tools surfaces column-level tags back. See README for detail.

---

*Write-back: Dry run mode was ON for this example — nothing was written to DataHub.*
