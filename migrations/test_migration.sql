ALTER TABLE orders
  DROP COLUMN shipping_address,
  ADD COLUMN referral_code VARCHAR(20),
  RENAME COLUMN customer_notes TO internal_notes;

ALTER TABLE customers
  DROP COLUMN phone,
  ALTER COLUMN region TYPE VARCHAR(100),
  ADD COLUMN loyalty_tier VARCHAR(20) NOT NULL DEFAULT 'bronze';
