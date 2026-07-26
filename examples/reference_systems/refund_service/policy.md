# Refund SOP (reference)

1. Customer submits refund with idempotency key.
2. Approver approves; balance decreases atomically.
3. Timeouts leave status unknown until reconcile.
4. Retry-safe: keyed submit. Retry-unsafe: approve without receipt check.
