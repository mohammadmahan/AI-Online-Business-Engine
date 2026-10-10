import type { OrderStatus } from '@/db/schema';
import {
  TRACKING_ALLOWED_STATUSES,
  canTransition,
} from '@/lib/order-rules';
import { issuesToMessage, validateTrackingCode } from '@/lib/validation';

import type { CommerceRepository, OrderDetail } from '../repository';

/**
 * D-172 §2.3 — fulfillment service (server half).
 *
 * The lifecycle map and the slip arithmetic live in `@/lib/order-rules` because
 * the browser reads the same map to build the status dropdown; this module owns
 * the WRITES and re-checks every rule before touching the database.
 */

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

export async function transitionOrder(
  repo: CommerceRepository,
  orderId: string,
  next: OrderStatus,
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
  const updated = await repo.updateOrderStatus(orderId, next);
  return updated
    ? { ok: true }
    : { ok: false, code: 'NOT_FOUND', message: 'سفارش پیدا نشد.' };
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
