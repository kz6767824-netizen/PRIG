ALTER TABLE orders
  DROP COLUMN loyalty_points,
  ADD COLUMN referral_code VARCHAR(20);
#test number 2
ALTER TABLE customers
  DROP COLUMN phone;
  
