-- ======================================================================
-- PR IMPACT GUARDIAN (PRIG) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: orders
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 1: Safe additive changes (apply immediately)

ALTER TABLE orders ADD COLUMN IF NOT EXISTS loyalty_points INT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_code VARCHAR(20);

-- PHASE 2: Safe deprecation for column 'shipping_address'

ALTER TABLE orders RENAME COLUMN shipping_address TO shipping_address_deprecated;

CREATE OR REPLACE VIEW orders_legacy AS
SELECT shipping_address_deprecated AS shipping_address, *
FROM orders;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE orders DROP COLUMN shipping_address_deprecated;

-- PHASE 2: Safe deprecation for column 'customer_notes'

ALTER TABLE orders RENAME COLUMN customer_notes TO customer_notes_deprecated;

CREATE OR REPLACE VIEW orders_legacy AS
SELECT customer_notes_deprecated AS customer_notes, *
FROM orders;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE orders DROP COLUMN customer_notes_deprecated;

-- PHASE 2: Safe deprecation for column 'legacy_tracking_id'

ALTER TABLE orders RENAME COLUMN legacy_tracking_id TO legacy_tracking_id_deprecated;

CREATE OR REPLACE VIEW orders_legacy AS
SELECT legacy_tracking_id_deprecated AS legacy_tracking_id, *
FROM orders;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE orders DROP COLUMN legacy_tracking_id_deprecated;
