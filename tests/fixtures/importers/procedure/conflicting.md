# Conflicting SOP

## submit_refund timeout handling

When `submit_refund` times out:

1. **Retry** `submit_refund` immediately.
2. Do not check authoritative state before retrying.
