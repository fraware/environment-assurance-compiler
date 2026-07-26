CREATE VIEW refund_summary AS
  SELECT 1 AS total;

CREATE INDEX idx_refunds_status ON refunds(status);
