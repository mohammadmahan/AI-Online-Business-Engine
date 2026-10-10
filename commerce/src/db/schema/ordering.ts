import { sql } from 'drizzle-orm';
import {
  bigint,
  check,
  index,
  integer,
  text,
  timestamp,
  uuid,
  varchar,
} from 'drizzle-orm/pg-core';

import { orderStatus } from './enums';
import { commerce } from './schema';
import { productVariants } from './catalog';

/**
 * D-172 Phase 1 — customers, orders and order_items (roadmap §1.5).
 *
 * Lifecycle reading of §1.5 (the section does not annotate nullability, so it
 * is inferred where the lifecycle REQUIRES absence — nothing else is optional):
 * - `payment_ref_id` is null until the gateway callback lands (Phase 6.1);
 * - `tracking_code` is null until the parcel is handed to the carrier (P2.3).
 *
 * Deletion policy: order history is never cascaded away — a customer or a
 * variant referenced by an order is `restrict`ed, while deleting an order takes
 * its own line items with it. Money is integer Toman (D-010) and never negative.
 */

/** §1.5 — customers. Phone number is the login identity (Phase 3.4 OTP). */
export const customers = commerce.table(
  'customers',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    phoneNumber: varchar('phone_number', { length: 32 }).notNull().unique(),
    fullName: varchar('full_name', { length: 255 }).notNull(),
    address: text('address').notNull(),
    postalCode: varchar('postal_code', { length: 16 }).notNull(),
    createdAt: timestamp('created_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [index('customers_phone_number_idx').on(table.phoneNumber)],
);

/** §1.5 — orders. */
export const orders = commerce.table(
  'orders',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    customerId: uuid('customer_id')
      .notNull()
      .references(() => customers.id, { onDelete: 'restrict' }),
    totalAmount: bigint('total_amount', { mode: 'number' }).notNull(),
    discountAmount: bigint('discount_amount', { mode: 'number' })
      .notNull()
      .default(0),
    shippingAmount: bigint('shipping_amount', { mode: 'number' })
      .notNull()
      .default(0),
    status: orderStatus('status').notNull().default('PENDING'),
    paymentRefId: varchar('payment_ref_id', { length: 255 }),
    shippingAddress: text('shipping_address').notNull(),
    trackingCode: varchar('tracking_code', { length: 120 }),
    createdAt: timestamp('created_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index('orders_customer_id_idx').on(table.customerId),
    index('orders_status_idx').on(table.status),
    check('orders_total_amount_non_negative', sql`${table.totalAmount} >= 0`),
    check('orders_discount_amount_non_negative', sql`${table.discountAmount} >= 0`),
    check('orders_shipping_amount_non_negative', sql`${table.shippingAmount} >= 0`),
  ],
);

/** §1.5 — order_items (one line per purchased variant). */
export const orderItems = commerce.table(
  'order_items',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    orderId: uuid('order_id')
      .notNull()
      .references(() => orders.id, { onDelete: 'cascade' }),
    variantId: uuid('variant_id')
      .notNull()
      .references(() => productVariants.id, { onDelete: 'restrict' }),
    quantity: integer('quantity').notNull(),
    unitPrice: bigint('unit_price', { mode: 'number' }).notNull(),
  },
  (table) => [
    index('order_items_order_id_idx').on(table.orderId),
    index('order_items_variant_id_idx').on(table.variantId),
    check('order_items_quantity_positive', sql`${table.quantity} > 0`),
    check('order_items_unit_price_non_negative', sql`${table.unitPrice} >= 0`),
  ],
);
