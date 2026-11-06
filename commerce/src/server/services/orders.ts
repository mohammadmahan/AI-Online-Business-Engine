import type { OrderStatus } from '@/db/schema';
import { ORDER_SHIPPED_KIND, SMS_CHANNEL } from '@/lib/notification-rules';
import {
  TRACKING_ALLOWED_STATUSES,
  canTransition,
} from '@/lib/order-rules';
import { issuesToMessage, validateTrackingCode } from '@/lib/validation';

import type {
  CommerceRepository,
  OrderDetail,
  OrderNotificationIntent,
  OrderStatusHistoryEntry,
  OrderTransitionTrigger,
} from '../repository';

/**
 * D-172 §2.3 — fulfillment service (server half).
 *
 * The lifecycle map and the slip arithmetic live in `@/lib/order-rules` because
 * the browser reads the same map to build the status dropdown; this module owns
 * the WRITES and re-checks every rule before touching the database.
 */

/**
 * The trigger a MERCHANT-PANEL transition uses.
 *
 * Exported so the panel action and the tests that simulate an owner's click name
 * the same actor instead of each spelling the literal, and so the async callback
 * path cannot borrow the panel's identity by accident: a transition always has to
 * say who asked, and this constant only ever means "the owner did this".
 */
export const MERCHANT_TRANSITION: OrderTransitionTrigger = { source: 'MERCHANT_PANEL' };

export type OrderMutationResult =
  | { ok: true }
  | {
      ok: false;
      code: 'VALIDATION_ERROR' | 'NOT_FOUND' | 'ILLEGAL_TRANSITION' | 'ILLEGAL_STATE';
      message: string;
      issues?: Array<{ field: string; message: string }>;
    };

export async function listOrders(repo: CommerceRepository) {
  return repo.listOrders();
}

export async function getOrder(
  repo: CommerceRepository,
  orderId: string,
): Promise<OrderDetail | null> {
  return repo.getOrderDetail(orderId);
}

/**
 * Moves an order's status. `trigger` is REQUIRED (D-172 Phase 4 transition):
 * every transition states who asked for it, because the audit row this writes is
 * read by a human investigating a parcel, and defaulting the actor would make
 * the trail quietly wrong exactly when it matters. The trigger is not validated
 * beyond its type — it is attribution, not authority.
 *
 * The refusal of a status the order is already in happens HERE (a clear Persian
 * message for the panel), while the repository's no-op branch covers a direct
 * caller and a retried callback.
 *
 * `notifications` (§6.2) are queued by the SAME write that moves the status, so
 * a crash between "status changed" and "buyer told" is not a state this can
 * reach. Passing an explicit list overrides the default; otherwise a move to
 * `SHIPPED` announces the shipment to the buyer and every other move announces
 * nothing (a cancellation is not a message the roadmap asks for).
 */
export async function transitionOrder(
  repo: CommerceRepository,
  orderId: string,
  next: OrderStatus,
  trigger: OrderTransitionTrigger,
  notifications: OrderNotificationIntent[] = [],
): Promise<OrderMutationResult> {
  const order = await repo.getOrderDetail(orderId);
  if (!order) {
    return { ok: false, code: 'NOT_FOUND', message: 'سفارش پیدا نشد.' };
  }
  if (order.status === next) {
    return { ok: false, code: 'ILLEGAL_TRANSITION', message: 'سفارش در همین وضعیت است.' };
  }
  if (!canTransition(order.status, next)) {
    return {
      ok: false,
      code: 'ILLEGAL_TRANSITION',
      message: `تغییر وضعیت از «${order.status}» به «${next}» مجاز نیست.`,
    };
  }
  const intents =
    notifications.length > 0
      ? notifications
      : next === 'SHIPPED'
        ? [{ kind: ORDER_SHIPPED_KIND, channel: SMS_CHANNEL }]
        : [];
  const updated = await repo.updateOrderStatus(orderId, next, trigger, intents);
  return updated
    ? { ok: true }
    : { ok: false, code: 'NOT_FOUND', message: 'سفارش پیدا نشد.' };
}

/** Phase 4 transition — the order's audit trail, oldest first. */
export async function listOrderStatusHistory(
  repo: CommerceRepository,
  orderId: string,
): Promise<OrderStatusHistoryEntry[]> {
  return repo.listOrderStatusHistory(orderId);
}

export async function setTrackingCode(
  repo: CommerceRepository,
  orderId: string,
  trackingCode: string,
): Promise<OrderMutationResult> {
  const order = await repo.getOrderDetail(orderId);
  if (!order) {
    return { ok: false, code: 'NOT_FOUND', message: 'سفارش پیدا نشد.' };
  }
  if (!TRACKING_ALLOWED_STATUSES.includes(order.status)) {
    return {
      ok: false,
      code: 'ILLEGAL_STATE',
      message: 'کد رهگیری فقط برای سفارش‌های در حال پردازش یا ارسال‌شده ثبت می‌شود.',
    };
  }
  const validation = validateTrackingCode(trackingCode);
  if (!validation.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(validation.issues),
      issues: validation.issues,
    };
  }
  const updated = await repo.updateOrderTracking(orderId, trackingCode.trim());
  return updated
    ? { ok: true }
    : { ok: false, code: 'NOT_FOUND', message: 'سفارش پیدا نشد.' };
}
