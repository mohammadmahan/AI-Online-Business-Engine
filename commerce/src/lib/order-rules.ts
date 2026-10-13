import type { OrderStatus } from '@/db/schema';
import type { OrderDetail } from '@/server/repository';

/**
 * D-172 §2.3 — order lifecycle rules, as a PURE module.
 *
 * The roadmap fixes the STATUS SET (`PENDING · PAID · PROCESSING · SHIPPED ·
 * CANCELLED`) but not the edges, so the forward chain is an explicit,
 * reviewable inference: money arrives before processing, a parcel leaves before
 * it can be tracked, and a shipped order is terminal. Cancellation is allowed
 * only while the parcel is still in the merchant's hands.
 *
 * The dropdown in the browser and the refusal on the server both read THIS map,
 * so the UI can never offer a transition the server would reject.
 */

export const ORDER_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  PENDING: ['PAID', 'CANCELLED'],
  PAID: ['PROCESSING', 'CANCELLED'],
  PROCESSING: ['SHIPPED', 'CANCELLED'],
  SHIPPED: [],
  CANCELLED: [],
};

/** Statuses in which a postal tracking code may be recorded (§2.3). */
export const TRACKING_ALLOWED_STATUSES: OrderStatus[] = ['PROCESSING', 'SHIPPED'];

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  PENDING: 'در انتظار پرداخت',
  PAID: 'پرداخت‌شده',
  PROCESSING: 'در حال پردازش',
  SHIPPED: 'ارسال‌شده',
  CANCELLED: 'لغوشده',
};

export function nextStatuses(current: OrderStatus): OrderStatus[] {
  return ORDER_TRANSITIONS[current] ?? [];
}

export function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  return nextStatuses(from).includes(to);
}

export function isTerminal(status: OrderStatus): boolean {
  return nextStatuses(status).length === 0;
}

export function canSetTracking(status: OrderStatus): boolean {
  return TRACKING_ALLOWED_STATUSES.includes(status);
}

export interface TransitionConfirmation {
  title: string;
  body: string;
  /** The destructive confirmation is styled as danger, not as a plain move. */
  danger: boolean;
}

/**
 * Confirmation copy for a status change.
 *
 * The roadmap's merchant-panel requirement is that every irreversible action
 * carries a confirmation (roadmap §UI/UX → merchant-panel-specific). In THIS
 * lifecycle every transition is one-way — the map above has no back-edges and
 * refuses self-transitions — so every status change is confirmed, and
 * cancellation is additionally styled as destructive.
 *
 * The copy states only what the panel actually does. As of the Phase 4
 * transition work, a status change DOES leave a record — the previous status, the
 * new status, the actor and the time are appended to `order_status_history` in
 * the same transaction as the move — so the copy says exactly that and nothing
 * stronger. It must not promise machinery the track does not write (canonical
 * provenance, notifications) nor repeat the older claim that only the row's
 * update timestamp moves, which this change made false (`PROJECT_RULES.md` §37).
 * The order remains unrecoverable to its previous status.
 */
export function transitionConfirmation(to: OrderStatus): TransitionConfirmation {
  if (to === 'CANCELLED') {
    return {
      title: 'لغو سفارش — این کار بازگشت‌پذیر نیست',
      body: 'لغو، وضعیت پایانی سفارش است و بازگرداندن آن به وضعیت پیشین از این پنل ممکن نیست. پس از ثبت، این تغییر در تاریخچه سفارش ثبت می‌شود.',
      danger: true,
    };
  }
  return {
    title: `تغییر وضعیت به «${ORDER_STATUS_LABELS[to]}»`,
    body: 'مسیر وضعیت سفارش یک‌طرفه است؛ پس از ثبت، بازگشت به وضعیت پیشین ممکن نیست. پس از ثبت، این تغییر در تاریخچه سفارش ثبت می‌شود.',
    danger: false,
  };
}

export interface OrderTotals {
  itemsTotal: number;
  discountAmount: number;
  shippingAmount: number;
  payable: number;
  storedTotal: number;
  consistent: boolean;
}

/**
 * Packing-slip arithmetic. `storedTotal` is what the SSOT holds; `payable` is
 * recomputed from the lines. They must agree — when they do not, the slip says
 * so instead of printing a number nobody can reconcile.
 */
export function computeTotals(order: OrderDetail): OrderTotals {
  const itemsTotal = order.items.reduce(
    (total, item) => total + item.quantity * item.unitPrice,
    0,
  );
  const payable = itemsTotal - order.discountAmount + order.shippingAmount;
  return {
    itemsTotal,
    discountAmount: order.discountAmount,
    shippingAmount: order.shippingAmount,
    payable,
    storedTotal: order.totalAmount,
    consistent: payable === order.totalAmount,
  };
}
