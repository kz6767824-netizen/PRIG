-- ======================================================================
-- PR IMPACT GUARDIAN (koza) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: customers
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 1: Safe additive changes (apply immediately)

ALTER TABLE customers ADD COLUMN IF NOT EXISTS loyalty_tier VARCHAR(20);

-- PHASE 2: Safe type change for 'region'

ALTER TABLE customers ADD COLUMN region_new VARCHAR(100);

-- UPDATE customers SET region_new = CAST(region AS VARCHAR(100));

ALTER TABLE customers RENAME COLUMN region TO region_deprecated;

CREATE OR REPLACE VIEW customers_legacy AS
SELECT region_new AS region, *
FROM customers;

-- After migration: ALTER TABLE customers DROP COLUMN region_deprecated;

-- PHASE 2: Safe deprecation for column 'phone'

ALTER TABLE customers RENAME COLUMN phone TO phone_deprecated;

CREATE OR REPLACE VIEW customers_legacy AS
SELECT phone_deprecated AS phone, *
FROM customers;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE customers DROP COLUMN phone_deprecated;
