-- Offline Postgres DDL fixture (no live server required).
CREATE TABLE IF NOT EXISTS app.accounts (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    balance NUMERIC(12, 2) DEFAULT 0,
    meta JSONB,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE "orders" (
    order_id BIGSERIAL PRIMARY KEY,
    account_id UUID NOT NULL,
    status TEXT NOT NULL,
    CONSTRAINT orders_status_check CHECK (status IN ('open', 'closed'))
);
