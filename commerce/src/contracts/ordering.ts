import type { InferInsertModel, InferSelectModel } from 'drizzle-orm';

import type { OrderStatus, customers, orderItems, orders } from '../db/schema';

/**
 * D-172 Phase 1 — typed contracts for customers and orders (§1.5).
 *
 * `order_status` follows the roadmap's specified lifecycle
 * (PENDING → PAID → PROCESSING → SHIPPED, plus CANCELLED). The transition
 * edges, reservation semantics and idempotency are NOT re-implemented here:
 * they belong to the canonical order layer (D-081–D-084), which the storefront
 * calls through its own write path. These types describe shape only.
 */

/* ------------------------------------------------------------------ read */

export type Customer = InferSelectModel<typeof customers>;
export type Order = InferSelectModel<typeof orders>;
export type OrderItem = InferSelectModel<typeof orderItems>;

export interface OrderWithItems extends Order {
  items: OrderItem[];
}

/* ------------------------------------------------------------ raw inserts */

export type NewCustomer = InferInsertModel<typeof customers>;
export type NewOrder = InferInsertModel<typeof orders>;
export type NewOrderItem = InferInsertModel<typeof orderItems>;

/* ------------------------------------------------------------ §1.5 writes */

export interface CustomerCreatePayload {
  /** Login identity for phone-OTP checkout (Phase 3.4). */
  phoneNumber: string;
  fullName: string;
  address: string;
  postalCode: string;
}

export type CustomerUpdatePayload = Partial<CustomerCreatePayload>;

/** One purchased line: a variant, a quantity and the price it was sold at. */
export interface OrderItemPayload {
  variantId: string;
  quantity: number;
  unitPrice: number;
}

/**
 * Checkout submission (Phase 3.4): the customer, the lines, the shipping
 * address and any discount/shipping amounts. `totalAmount` is computed by the
 * write path, never trusted from the client.
 */
export interface OrderCreatePayload {
  customerId: string;
  items: OrderItemPayload[];
  shippingAddress: string;
  discountAmount?: number;
  shippingAmount?: number;
}

/** Status transition request (Phase 2.3 dropdown). */
export interface OrderStatusUpdatePayload {
  status: OrderStatus;
}

/** Postal tracking code entry (Phase 2.3), which triggers the buyer SMS. */
export interface OrderTrackingPayload {
  trackingCode: string;
}

/** Gateway callback reference (Phase 6.1); idempotent on the write path. */
export interface OrderPaymentReferencePayload {
  paymentRefId: string;
}
