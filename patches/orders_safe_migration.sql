-- ======================================================================
-- PR IMPACT GUARDIAN (koza) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: orders
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 1: Safe additive changes (apply immediately)

ALTER TABLE orders ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20);

-- PHASE 2: Safe rename for 'customer_notes' -> 'internal_notes'

ALTER TABLE orders ADD COLUMN internal_notes <TYPE>;

-- UPDATE orders SET internal_notes = customer_notes;

ALTER TABLE orders RENAME COLUMN customer_notes TO customer_notes_deprecated;

CREATE OR REPLACE VIEW orders_legacy AS
SELECT customer_notes_deprecated AS customer_notes, *
FROM orders;

-- After migration: ALTER TABLE orders DROP COLUMN customer_notes_deprecated;

-- PHASE 2: Safe deprecation for column 'shipping_address'

ALTER TABLE orders RENAME COLUMN shipping_address TO shipping_address_deprecated;

CREATE OR REPLACE VIEW orders_legacy AS
SELECT shipping_address_deprecated AS shipping_address, *
FROM orders;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE orders DROP COLUMN shipping_address_deprecated;
