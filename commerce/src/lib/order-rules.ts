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
