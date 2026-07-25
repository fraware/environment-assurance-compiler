# Refund Support SOP

Approved procedure for handling customer refunds when the payment gateway is slow.

## submit_refund timeout handling

When `submit_refund` returns a timeout or the agent observes an HTTP 504:

1. Inform the customer that processing may still be in flight.
2. **Retry** `submit_refund` once after waiting 30 seconds.
3. If the second attempt also times out, escalate to tier-2 support.

This SOP intentionally instructs retry even though the API contract does not
define whether the first attempt committed authoritative refund state.
