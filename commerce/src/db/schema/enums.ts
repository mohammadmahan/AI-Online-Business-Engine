import { commerce } from './schema';

/** D-172 §1.2 — product lifecycle: DRAFT → PUBLISHED → ARCHIVED. */
export const productStatus = commerce.enum('product_status', [
  'DRAFT',
  'PUBLISHED',
  'ARCHIVED',
]);

/** D-172 §1.5 — order lifecycle as specified for the fashion track. */
export const orderStatus = commerce.enum('order_status', [
  'PENDING',
  'PAID',
  'PROCESSING',
  'SHIPPED',
  'CANCELLED',
]);

/** D-172 §2.4 — coupon kind: percentage or fixed amount. */
export const discountType = commerce.enum('discount_type', ['PERCENT', 'FIXED']);

/**
 * D-172 Phase 3.5 / §6 — WHO moved an order's status.
 *
 * The audit trail records a transition's actor as a CLOSED set rather than a
 * free-text note, because the value is read by humans investigating a parcel
 * and by tests asserting that a slot was served by the path it claims:
 *
 *   - `STOREFRONT`        — the customer's own checkout wrote the opening row;
 *   - `MERCHANT_PANEL`    — the owner moved the order from `/admin/orders`;
 *   - `PAYMENT_CALLBACK`  — an async gateway/notification callback (the seam
 *                           scaffolded under `/api/webhooks/payment`);
 *   - `SYSTEM`            — a future automated rule (timeout, reconciliation).
 *
 * A provider-specific `actor` is deliberately NOT modelled here: the payment
 * and SMS providers are still open owner decisions (G-4 / decisions 10 and 11),
 * so a provider identity would be invented today and changed tomorrow. It
 * belongs in `metadata` until its provider exists.
 */
export const orderStatusSource = commerce.enum('order_status_source', [
  'STOREFRONT',
  'MERCHANT_PANEL',
  'PAYMENT_CALLBACK',
  'SYSTEM',
]);

/**
 * D-172 §6.2 — the delivery channel of a queued notification.
 *
 * A closed set of ONE today, on purpose: the owner selected Kavenegar as the
 * SMS provider (decision-register row 74), and no other channel has a provider.
 * Adding `EMAIL` later is a migration, not a free-text column that quietly
 * accumulates values nothing can deliver.
 */
export const notificationChannel = commerce.enum('notification_channel', ['SMS']);

/**
 * D-172 §6.2 — a queued notification's delivery state.
 *
 *   - `PENDING`  — enqueued, due at `next_attempt_at` (the initial state);
 *   - `SENDING`  — CLAIMED by a dispatcher, whose lease expires so a crashed
 *                  claimant cannot strand the row forever;
 *   - `SENT`     — the provider accepted it (`sent_at` is set);
 *   - `FAILED`   — terminal: a permanent refusal, or the attempt budget spent.
 *
 * `SENT` and `ready_to_send` are deliberately different facts: a queue entry is
 * not a delivery, and only the provider's own acceptance moves this row on.
 */
export const notificationStatus = commerce.enum('notification_status', [
  'PENDING',
  'SENDING',
  'SENT',
  'FAILED',
]);

export type ProductStatus = (typeof productStatus.enumValues)[number];
export type OrderStatus = (typeof orderStatus.enumValues)[number];
export type DiscountType = (typeof discountType.enumValues)[number];
export type OrderStatusSource = (typeof orderStatusSource.enumValues)[number];
export type NotificationChannel = (typeof notificationChannel.enumValues)[number];
export type NotificationStatus = (typeof notificationStatus.enumValues)[number];
