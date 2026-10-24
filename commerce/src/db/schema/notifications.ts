import { sql } from 'drizzle-orm';
import {
  check,
  index,
  integer,
  jsonb,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
} from 'drizzle-orm/pg-core';

import { notificationChannel, notificationStatus } from './enums';
import { orders } from './ordering';
import { commerce } from './schema';

/**
 * D-172 §6.2 — the notification OUTBOX: the queue a paid order is announced
 * through.
 *
 * Why a table and not a call inside the payment path: the provider call is a
 * network round-trip that can take seconds and can fail, while the payment
 * transition has already committed. Sending inside that path would either make a
 * payment depend on Kavenegar being reachable, or lose the announcement when it
 * is not. The outbox is the standard answer — the row is written in the SAME
 * transaction as the status move, and a separate dispatcher delivers it later,
 * with retries, at its own pace. The two halves share nothing but this table.
 *
 * Why exactly-once is structural, not a flag: `notification_outbox_unique` on
 * `(order_id, kind, channel)` means a second, concurrent payment callback cannot
 * enqueue a second SMS for the same order and the same message kind. The enqueue
 * is an `ON CONFLICT DO NOTHING`, so the loser is a no-op rather than an error —
 * the same shape the audit trail uses for `(order_id, to_status)`.
 *
 * What is deliberately NOT here:
 *  - NO phone number. The recipient is read from `commerce.customers` at
 *    DISPATCH time, so this table holds no second copy of customer PII and a
 *    corrected number is not shadowed by a stale queue entry;
 *  - NO credentials. The provider key is read from the environment at send time
 *    and never stored (D-045/D-124);
 *  - NO message body. The Persian body is rendered at dispatch from the kind and
 *    the order reference, so a body edit is a code change and not a data
 *    migration.
 */
export const notificationOutbox = commerce.table(
  'notification_outbox',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    orderId: uuid('order_id')
      .notNull()
      .references(() => orders.id, { onDelete: 'cascade' }),
    /**
     * The notification KIND — the canonical template id
     * (`order.confirmed`), never a rendered title. One kind per migration: the
     * check constraint below is the reason an unknown kind cannot be enqueued by
     * a caller that guessed.
     */
    kind: varchar('kind', { length: 64 }).notNull(),
    channel: notificationChannel('channel').notNull(),
    status: notificationStatus('status').notNull().default('PENDING'),
    /**
     * Non-PII template variables snapshotted at enqueue time (today: the order
     * reference). The recipient and the body are resolved from the order at
     * dispatch, so nothing here is customer data.
     */
    payload: jsonb('payload').$type<Record<string, unknown>>().notNull().default({}),
    /** How many times a dispatcher has CLAIMED this row. Bounded by policy. */
    attempts: integer('attempts').notNull().default(0),
    /** A stable failure CODE (never a provider message, never a credential). */
    lastError: varchar('last_error', { length: 64 }),
    /** The provider's own message id — the only correlator worth recording. */
    providerMessageId: varchar('provider_message_id', { length: 128 }),
    /** When the row becomes claimable again; `now()` for a fresh entry. */
    nextAttemptAt: timestamp('next_attempt_at', { withTimezone: true })
      .notNull()
      .defaultNow(),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
    sentAt: timestamp('sent_at', { withTimezone: true }),
  },
  (table) => [
    // THE idempotency boundary: one notification of a kind, on a channel, per
    // order — no matter how many concurrent callbacks report the same payment.
    uniqueIndex('notification_outbox_unique').on(table.orderId, table.kind, table.channel),
    // The dispatcher's only scan: due rows, oldest first.
    index('notification_outbox_due_idx').on(table.status, table.nextAttemptAt),
    check('notification_outbox_attempts_non_negative', sql`${table.attempts} >= 0`),
    // A kind is admitted by a migration, not by a caller's imagination.
    check('notification_outbox_kind_known', sql`${table.kind} = 'order.confirmed'`),
    // `sent_at` and `SENT` are two spellings of one fact; a row may not hold one
    // without the other.
    check(
      'notification_outbox_delivery_consistent',
      sql`(${table.status} = 'SENT') = (${table.sentAt} is not null)`,
    ),
    check(
      'notification_outbox_payload_is_object',
      sql`jsonb_typeof(${table.payload}) = 'object'`,
    ),
  ],
);
