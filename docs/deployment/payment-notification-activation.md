# Payment and notification activation checklist

**Current state: NOT ACTIVATED.** The payment webhook and notification dispatch
endpoints are fail-closed. With no secret they answer `503` and process nothing.
That is intentional, not a defect. This checklist is an authorization record, not
permission to enable a provider.

## Preconditions (owner decisions)

- [ ] Payment provider selected and approved for the target environment.
- [ ] SMS provider, sender line, template registration and delivery-report
      contract approved.
- [ ] Explicit authorization to use real payment/SMS credentials in the named
      environment (D-045 / D-139).
- [ ] A sandbox or provider test mode is available; no real customer data or
      charge is used for the first round-trip.

## Required environment names

Commerce runtime:

- `COMMERCE_PAYMENT_WEBHOOK_SECRET` — HMAC secret for the signed payment webhook.
- Payment provider credentials named by the selected adapter; never commit them.
- `DATABASE_URL` / `COMMERCE_DATABASE_URL` — the authorized canonical target.

Notification dispatch:

- `NOTIFICATIONS_DISPATCH_TOKEN` — bearer secret for the operator trigger.
- `SMS_LIVE_ENABLED` — remains unset/false until the owner activates live SMS.
- Provider credentials named by the selected SMS adapter.

Set values only in the environment's secret store or an untracked `.env`. Never
paste them into chat, source, logs, screenshots or documentation.

## Verification sequence (sandbox only)

1. Send an unsigned webhook: expect **503** when no secret is configured, or
   **401** when a secret exists but the signature is absent/invalid.
2. Send a correctly signed sandbox event for a disposable order: expect the
   intended `PENDING → PAID` transition or a documented duplicate response.
3. Replay the identical event: expect a duplicate response and **no** second
   order/history/outbox row.
4. Send the same event with a different reference or illegal transition: expect a
   refusal and no state change.
5. Dispatch notifications with the bearer token against a disposable outbox:
   expect exactly one claim/send, then zero claims on a second pass.
6. Verify the outbox row, order history, payment reference and provider response
   in the disposable database.
7. Remove the sandbox credentials and confirm both endpoints return to their
   fail-closed state.

## Stop conditions

- Any real charge, live SMS, customer data, or external post.
- Any request accepted without the configured signature/token.
- Any duplicate order, stock decrement, coupon use, or outbox delivery.
- Any secret value appearing in output, browser storage, logs or Git.

Until every precondition is signed off, production activation remains **NO-GO**;
G0 remains unverified/owner-gated.
