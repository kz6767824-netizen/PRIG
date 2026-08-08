ALTER TABLE support_tickets
  DROP COLUMN priority,
  ADD COLUMN sla_breached BOOLEAN,
  RENAME COLUMN subject TO ticket_subject;

ALTER TABLE marketing_campaigns
  DROP COLUMN budget,
  ADD COLUMN target_audience VARCHAR(50);

ALTER TABLE sessions
  ALTER COLUMN duration_seconds TYPE BIGINT,
  ADD COLUMN device_type VARCHAR(20);
