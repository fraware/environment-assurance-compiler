-- Refund reference schema (optional Postgres path; in-memory server is default).
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  balance INTEGER NOT NULL,
  currency TEXT NOT NULL,
  role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id),
  amount INTEGER NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS approvals (
  refund_id TEXT NOT NULL REFERENCES refunds(id),
  approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
