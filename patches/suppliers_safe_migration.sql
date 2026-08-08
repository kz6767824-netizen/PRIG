-- ======================================================================
-- PR IMPACT GUARDIAN (koza) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: suppliers
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 1: Safe additive changes (apply immediately)

ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS contract_expiry DATE;

-- PHASE 2: Safe rename for 'country' -> 'origin_country'

ALTER TABLE suppliers ADD COLUMN origin_country <TYPE>;

-- UPDATE suppliers SET origin_country = country;

ALTER TABLE suppliers RENAME COLUMN country TO country_deprecated;

CREATE OR REPLACE VIEW suppliers_legacy AS
SELECT country_deprecated AS country, *
FROM suppliers;

-- After migration: ALTER TABLE suppliers DROP COLUMN country_deprecated;

-- PHASE 2: Safe deprecation for column 'rating'

ALTER TABLE suppliers RENAME COLUMN rating TO rating_deprecated;

CREATE OR REPLACE VIEW suppliers_legacy AS
SELECT rating_deprecated AS rating, *
FROM suppliers;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE suppliers DROP COLUMN rating_deprecated;
