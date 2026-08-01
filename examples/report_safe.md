# Example: Safe — Additive Column

**Input SQL:**
```sql
ALTER TABLE orders ADD COLUMN status VARCHAR;
```

**Overall Severity: ✅ Safe**

---

## PR Impact Report: `orders`

### Column: `status`

- **Table:** `orders`
- **Severity:** `Safe`

**Downstream impact:** 1 asset(s) found in DataHub:
- `daily_revenue_dashboard` (dataset)

**Suggestion:** Additive changes are generally safe. No action needed beyond normal review.

---

**Note:** These suggestions reflect general best-practice patterns and do not account for your team's specific constraints, release cycle, compliance deadlines, or urgency. A human reviewer should confirm this approach fits the actual situation before merging.

Severity classification is fully deterministic and reproducible. If an LLM-generated explanation is used instead of the template, its exact wording may vary slightly between runs on the same input — the severity label itself will not.

**PII detection:** this version does not attempt automatic column-level PII detection. Live testing confirmed the tag WRITE path works (`add_tags` with `column_paths`), but no read path currently available through the Agent Context Kit tools surfaces column-level tags back. See README for detail.

---

*Write-back: Dry run mode was ON for this example — nothing was written to DataHub.*
