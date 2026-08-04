-- ======================================================================
-- PR IMPACT GUARDIAN (PRIG) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: orders
-- Pattern: Expand-Contract (Parallel Run)
-- ======================================================================

-- PHASE 1: Additive & Non-Breaking Changes (SAFE TO APPLY IMMEDIATELY)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS loyalty_points INT;

-- PHASE 2: Create Backward-Compatible View for Downstream Consumers
CREATE OR REPLACE VIEW orders_v1 AS
SELECT
    *,
    NULL AS shipping_address -- Fallback for deprecated column
FROM orders;

-- PHASE 3: Future Cleanup (Execute ONLY after all downstream dashboards are updated)
-- ALTER TABLE orders DROP COLUMN IF EXISTS shipping_address;