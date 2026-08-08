-- ======================================================================
-- PR IMPACT GUARDIAN (PRIG) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: customers
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 2: Safe deprecation for column 'phone'

ALTER TABLE customers RENAME COLUMN phone TO phone_deprecated;

CREATE OR REPLACE VIEW customers_legacy AS
SELECT phone_deprecated AS phone, *
FROM customers;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE customers DROP COLUMN phone_deprecated;
