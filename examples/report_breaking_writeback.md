# Example: Breaking — With Live Write-Back to DataHub

This example shows the full pipeline with **dry run OFF**: a migration with
two operations (a Breaking drop and a Safe add) on the same table,
including the actual write-back step and DataHub's real API responses.

**Input SQL:**
```sql
ALTER TABLE orders
  DROP COLUMN shipping_address,
  ADD COLUMN loyalty_points INT;
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

### Column: `loyalty_points`
![Safe](https://img.shields.io/badge/loyalty__points-Safe-brightgreen)

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

## Write-back to DataHub (live, dry_run=False)

**Overall severity: Breaking** (highest of the two per-column verdicts above) →
the agent auto-creates the `pending-review-breaking` tag if it doesn't
already exist, then applies it to the `orders` dataset via the Agent
Context Kit's `add_tags()`:

```
[ensure_tags_exist] Ensured tag exists: pending-review-breaking
[write_back_tag] LIVE WRITE -- applied 'urn:li:tag:pending-review-breaking' to
'urn:li:dataset:(urn:li:dataPlatform:postgres,orders,PROD)'.
```

**Real DataHub API response:**
```json
{
  "success": true,
  "message": "Successfully added 1 tag(s) to 1 entit(ies)"
}
```

**Also saved as a Context Document** (permanent audit trail, separate from
the ephemeral tag), via `save_document()` — content is the exact two-column
report shown above:

**Real DataHub API response:**
```json
{
  "success": true,
  "urn": "urn:li:document:shared-759de5fb-af10-4200-a9cb-25873bbf6fa3",
  "message": "Successfully created document: PR Impact Report: orders (Breaking)",
  "author": "__datahub_system"
}
```

**Verified in the DataHub UI:**
- `localhost:9002` → Manage Tags → `pending-review-breaking` → shows the
  tag applied to the `orders` dataset, confirming the write actually
  landed (not just an API success message).
- Re-applying the same tag to the same dataset a second time was tested
  and confirmed **idempotent** — the "Applied to" count does not increase
  on repeat writes.
- The saved Context Document is visible and searchable at
  `localhost:9002/document/urn:li:document:shared-759de5fb-af10-4200-a9cb-25873bbf6fa3`,
  linked to the `orders` dataset.
