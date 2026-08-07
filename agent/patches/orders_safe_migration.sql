-- ======================================================================
-- PR IMPACT GUARDIAN (PRIG) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: orders
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 1: Safe additive changes (apply immediately)

ALTER TABLE orders ADD COLUMN IF NOT EXISTS loyalty_points INT;

-- PHASE 2: Safe deprecation for column 'shipping_address'

ALTER TABLE orders RENAME COLUMN shipping_address TO shipping_address_deprecated;

CREATE OR REPLACE VIEW orders_legacy AS
SELECT shipping_address_deprecated AS shipping_address, *
FROM orders;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE orders DROP COLUMN shipping_address_deprecated;
