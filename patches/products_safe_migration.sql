-- ======================================================================
-- PR IMPACT GUARDIAN (koza) - AUTOMATED SAFE REMEDIATION PATCH
-- Target Table: products
-- Pattern: Rename-Then-View (preserves data, keeps old names working)
-- NOTE: Review and adapt column lists before running in production.
-- ======================================================================

-- PHASE 1: Safe additive changes (apply immediately)

ALTER TABLE products ADD COLUMN IF NOT EXISTS discontinued BOOLEAN;

-- PHASE 2: Safe type change for 'price'

ALTER TABLE products ADD COLUMN price_new DECIMAL(12,2);

-- UPDATE products SET price_new = CAST(price AS DECIMAL(12,2));

ALTER TABLE products RENAME COLUMN price TO price_deprecated;

CREATE OR REPLACE VIEW products_legacy AS
SELECT price_new AS price, *
FROM products;

-- After migration: ALTER TABLE products DROP COLUMN price_deprecated;

-- PHASE 2: Safe deprecation for column 'category'

ALTER TABLE products RENAME COLUMN category TO category_deprecated;

CREATE OR REPLACE VIEW products_legacy AS
SELECT category_deprecated AS category, *
FROM products;

-- PHASE 3: After all consumers migrate, drop deprecated column:
-- ALTER TABLE products DROP COLUMN category_deprecated;
