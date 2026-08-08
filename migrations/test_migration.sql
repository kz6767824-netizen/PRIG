ALTER TABLE customers
  DROP COLUMN phone,
  DROP COLUMN email,
  ADD COLUMN loyalty_tier VARCHAR(20),
  ADD COLUMN marketing_opt_in BOOLEAN,
  ADD COLUMN last_login_at TIMESTAMP,
  DROP COLUMN region,
  ADD COLUMN preferred_language VARCHAR(10),
  DROP COLUMN name;
