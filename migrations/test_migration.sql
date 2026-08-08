#now after it restart     rd retest
ALTER TABLE orders
  DROP COLUMN shipping_address,
  DROP COLUMN customer_notes,
  ADD COLUMN loyalty_points INT,
  ADD COLUMN discount_code VARCHAR(20),
  DROP COLUMN legacy_tracking_id;
