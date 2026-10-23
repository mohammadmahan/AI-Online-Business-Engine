import { sql } from 'drizzle-orm';
import {
  bigint,
  check,
  index,
  integer,
  jsonb,
  text,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
} from 'drizzle-orm/pg-core';

import { orderStatus, orderStatusSource } from './enums';
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
    /**
     * §6.1 — the redirect-based provider's AUTHORISATION, persisted at the moment
     * the payment is requested.
     *
     * A ZarinPal payment request answers an `authority` and a redirect URL, and
     * its VERIFY call requires the amount that was requested — but the callback
     * carries only the authority. Holding that pair in process memory would make
     * every callback fail after a restart and refuse every callback that lands on
     * another instance, so the mapping lives HERE, on the order it belongs to,
     * where the verify path can read it from the SSOT (G-1).
     *
     * All three are NULL until a provider has actually issued an authority, and
     * the pair-wise check below keeps them that way: a half-written authorisation
     * is not a fact this table may hold. `payment_amount` is integer Toman
     * (D-010) — the amount the provider was ASKED for, recorded next to (not
     * instead of) `total_amount` so a later order edit cannot change what a
     * pending authorisation must be verified for. No secret is stored: an
     * authority is a provider-issued payment token, never a credential.
     */
    paymentProvider: varchar('payment_provider', { length: 32 }),
    paymentAuthority: varchar('payment_authority', { length: 255 }),
    paymentAmount: bigint('payment_amount', { mode: 'number' }),
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
    // The callback's ONLY lookup key: an authority identifies exactly one order,
    // so a callback can never resolve to two of them. PostgreSQL allows many
    // NULLs here, which is what keeps every order without an authorisation valid.
    uniqueIndex('orders_payment_authority_unique').on(table.paymentAuthority),
    check('orders_total_amount_non_negative', sql`${table.totalAmount} >= 0`),
    check('orders_discount_amount_non_negative', sql`${table.discountAmount} >= 0`),
    check('orders_shipping_amount_non_negative', sql`${table.shippingAmount} >= 0`),
    check(
      'orders_payment_amount_positive',
      sql`${table.paymentAmount} is null or ${table.paymentAmount} > 0`,
    ),
    check(
      'orders_payment_authorization_complete',
      // Either no provider has issued anything, or all three fields are present.
      sql`(${table.paymentProvider} is null and ${table.paymentAuthority} is null and ${table.paymentAmount} is null) or (${table.paymentProvider} is not null and ${table.paymentAuthority} is not null and ${table.paymentAmount} is not null)`,
    ),
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

/**
 * D-172 Phase 4 transition — the order state machine's AUDIT TRAIL, appended to
 * by the same transaction that moves the order.
 *
 * Every status an order reaches leaves exactly one row here, written from
 * inside the write that reached it: order creation (`PENDING`, with a NULL
 * `from_status` because nothing preceded it), a merchant transition, and a
 * future payment callback. A transition that is refused leaves NOTHING behind,
 * and a status change can never commit without its row — the two writes share
 * one transaction, so the trail cannot silently disagree with the order row.
 *
 * What this table is: an append-only record of WHAT the lifecycle did, WHO did
 * it (`source`, a closed set from `order_status_source`) and WHEN, with an
 * optional `metadata` object for the facts that belong to the transition but
 * have nowhere else to live (a gateway reference, a provider event id). It is
 * NOT a general activity log: the order's own `updated_at`, its line items and
 * the coupon counter are not duplicated here, and recording a postal tracking
 * code is NOT a status transition, so it writes no row.
 *
 * `unique (order_id, to_status)` is deliberate and is the storage-level
 * idempotency boundary the async callback path leans on: in this one-way
 * lifecycle (D-172 §2.3 — no back-edges, and a transition to the CURRENT status
 * is refused before any write) an order reaches a given status at most once, so
 * a retried provider callback cannot append a second row claiming it, even if
 * the code above it were wrong. A FUTURE phase that legitimately adds a
 * back-edge (a refund returning `PAID` to `PENDING`, say) must drop this index
 * in its own reviewed migration — it is an assumption about the lifecycle, and
 * the lifecycle map is the thing it mirrors.
 *
 * Deletion: `on delete cascade`, matching `order_items` — an order's history is
 * part of the order, and `order_items.variant_id` / `orders.customer_id` still
 * RESTRICT deletion of anything an order refers to, so this cascade cannot be
 * reached by deleting a customer or a variant.
 */
export const orderStatusHistory = commerce.table(
  'order_status_history',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    orderId: uuid('order_id')
      .notNull()
      .references(() => orders.id, { onDelete: 'cascade' }),
    /** The status the order was in; NULL only for the creation row. */
    fromStatus: orderStatus('from_status'),
    toStatus: orderStatus('to_status').notNull(),
    source: orderStatusSource('source').notNull(),
    /** Transition facts with no column of their own; never customer PII. */
    metadata: jsonb('metadata').$type<Record<string, unknown>>(),
    createdAt: timestamp('created_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    index('order_status_history_order_id_idx').on(table.orderId, table.createdAt),
    uniqueIndex('order_status_history_order_to_status_unique').on(
      table.orderId,
      table.toStatus,
    ),
    check(
      'order_status_history_status_changes',
      sql`${table.fromStatus} is null or ${table.fromStatus} <> ${table.toStatus}`,
    ),
    check(
      'order_status_history_creation_has_no_origin',
      // A NULL origin means "this is where the order began", which is only true
      // of the opening PENDING row — the audit trail's own guard against a later
      // transition being written as if it had created the order.
      sql`${table.fromStatus} is not null or ${table.toStatus} = 'PENDING'`,
    ),
  ],
);
