-- ======================================================================
-- PR IMPACT GUARDIAN (koza) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: orders
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 2: Safe deprecation for column 'loyalty_points'

ALTER TABLE orders RENAME COLUMN loyalty_points TO loyalty_points_deprecated;

CREATE OR REPLACE VIEW orders_legacy AS
SELECT loyalty_points_deprecated AS loyalty_points, *
FROM orders;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE orders DROP COLUMN loyalty_points_deprecated;
