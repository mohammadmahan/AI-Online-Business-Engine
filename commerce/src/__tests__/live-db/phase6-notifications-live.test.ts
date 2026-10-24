import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import { Pool } from 'pg';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { createCommerceDb, type CommerceDb } from '@/db';
import { categories } from '@/db/schema';
import { ORDER_CONFIRMED_KIND, SMS_CHANNEL, orderReference } from '@/lib/notification-rules';
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import { dispatchNotifications } from '@/server/notifications/dispatcher';
import { handleNotificationDispatchRequest } from '@/server/notifications/dispatch-endpoint';
import { MockSmsChannel, type SmsChannel } from '@/server/notifications/sms';
import { mockPaymentGateway } from '@/server/payments/gateway';
import { createPostgresRepository, type CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §6.2 — the LIVE notification-outbox suite (disposable harness).
 *
 * The unit tests run against the in-memory double, which models BEHAVIOUR. Two
 * claims of the outbox are not behavioural, they are properties of the storage,
 * and only a real server can settle them:
 *
 *   1. EXACTLY ONCE PER ORDER. The enqueue is an `ON CONFLICT DO NOTHING` inside
 *      the payment transaction, and the idempotency boundary is the unique index
 *      on `(order_id, kind, channel)`. Two genuinely concurrent `PAID` writes
 *      must leave ONE row and ONE `PAID` trail entry — a memory map cannot
 *      demonstrate that, because it has no index to violate.
 *   2. EXACTLY ONE CLAIMANT. `claimNotificationBatch` selects with
 *      `FOR UPDATE SKIP LOCKED` and moves the rows to `SENDING` in the same
 *      transaction. Two dispatchers racing over the same due rows must claim
 *      disjoint batches; if the lock were decorative, both would send.
 *
 * The suite also proves the enqueue is TRANSACTIONAL with the status move, that
 * the queue row carries no PII, that the storage CHECKs refuse a malformed row,
 * that a stale `SENDING` lease is reclaimed while a fresh one is not, that the
 * attempt budget stops a bad message for good, and that the operator endpoint
 * drains this same queue when called with the right bearer token.
 *
 * Target and gates are identical to `phase2`/`phase3`/`phase4`: the disposable
 * loopback harness only, SKIP with a named reason when `COMMERCE_DATABASE_URL`
 * is absent or not loopback (an absent configuration is a refusal, never a pass
 * — D-171 §2.2), and a full schema reset plus the COMMITTED migrations on every
 * run, so the migration evidence is produced rather than assumed.
 */

const HARNESS_URL = process.env.COMMERCE_DATABASE_URL?.trim();
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function skipReason(): string | undefined {
  if (!HARNESS_URL) {
    return 'COMMERCE_DATABASE_URL not set — live notification-outbox suite skipped (no target is guessed; fail-closed)';
  }
  try {
    const target = new URL(HARNESS_URL);
    if (!LOOPBACK_HOSTS.has(target.hostname)) {
      return `COMMERCE_DATABASE_URL host "${target.hostname}" is not loopback — refusing to write to a non-local instance (D-172 G-2: staging and production are out of scope)`;
    }
  } catch {
    return 'COMMERCE_DATABASE_URL is not a parseable URL — skipped';
  }
  return undefined;
}

/** The COMMITTED migration folder, three levels up from the compiled output. */
const MIGRATIONS_FOLDER = fileURLToPath(new URL('../../../drizzle', import.meta.url));

const SLUG = 'manto-notify-p6';
const TOKEN = 'live-dispatch-token-0123456789';
const PHONE = '09123456789';

describe(
  'D-172 §6.2 — live notification outbox and SMS dispatch (disposable harness)',
  { skip: skipReason() },
  () => {
    let pool!: Pool;
    let db!: CommerceDb;
    let repo!: CommerceRepository;

    let categoryId = '';
    const variantIds: Record<string, string> = {};

    interface OutboxRow {
      id: string;
      order_id: string;
      kind: string;
      channel: string;
      status: string;
      payload: Record<string, unknown>;
      attempts: number;
      last_error: string | null;
      provider_message_id: string | null;
      next_attempt_at: Date;
      sent_at: Date | null;
    }

    /**
     * The SQLSTATE of a statement that must be refused, unwrapping the cause
     * chain (Drizzle wraps driver errors; the PostgreSQL code sits on `cause`).
     * Raw `pool.query` calls need no unwrapping, but this helper is also used
     * for repository calls, so it walks both shapes.
     */
    async function refusalCode(run: () => Promise<unknown>): Promise<string> {
      try {
        await run();
      } catch (error) {
        let current: unknown = error;
        for (let depth = 0; depth < 6 && current !== null && typeof current === 'object'; depth += 1) {
          const candidate = current as { code?: unknown; cause?: unknown };
          if (typeof candidate.code === 'string' && /^[0-9A-Z]{5}$/.test(candidate.code)) {
            return candidate.code;
          }
          current = candidate.cause;
        }
        return 'unknown';
      }
      assert.fail('the database ACCEPTED a write the outbox must refuse');
    }

    async function outboxOf(orderId: string): Promise<OutboxRow[]> {
      const { rows } = await pool.query<OutboxRow>(
        `select id, order_id, kind, channel, status, payload, attempts, last_error,
                provider_message_id, next_attempt_at, sent_at
           from commerce.notification_outbox
          where order_id = $1
          order by created_at, kind`,
        [orderId],
      );
      return rows;
    }

    /** Every row in the queue, newest last — used for global counts. */
    async function outboxCount(): Promise<number> {
      const { rows } = await pool.query<{ n: number }>(
        'select count(*)::int as n from commerce.notification_outbox',
      );
      return rows[0]?.n as number;
    }

    /** A real storefront order, through the real write path. */
    async function placeOrder(sku: string, quantity = 1): Promise<string> {
      const draft: CheckoutDraft = {
        customer: {
          fullName: 'زهرا محمدی',
          phoneNumber: PHONE,
          address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
          postalCode: '1999999999',
        },
        couponCode: null,
        shippingMethodId: DEFAULT_SHIPPING_METHOD_ID,
        lines: [{ variantId: variantIds[sku] as string, quantity }],
      };
      const placed = await placeCheckoutOrder(repo, mockPaymentGateway, draft);
      assert.ok(placed.ok, `the live order must be written: ${JSON.stringify(placed)}`);
      return placed.orderId;
    }

    /** An order moved to PAID through the real service, queueing one SMS. */
    async function paidOrderWithQueue(sku = 'P6-BLK-S'): Promise<string> {
      const orderId = await placeOrder(sku);
      const moved = await transitionOrder(repo, orderId, 'PAID', MERCHANT_TRANSITION, [
        { kind: ORDER_CONFIRMED_KIND, channel: SMS_CHANNEL },
      ]);
      assert.deepEqual(moved, { ok: true }, 'the fixture order must reach PAID');
      const rows = await outboxOf(orderId);
      assert.equal(rows.length, 1, 'the PAID fixture must have queued exactly one message');
      return orderId;
    }

    before(async () => {
      const handle = createCommerceDb(HARNESS_URL as string);
      pool = handle.pool;
      db = handle.db;
      repo = createPostgresRepository(db);

      await pool.query('drop schema if exists "commerce" cascade');
      const journal = await pool.query<{ schema: string; table: string }>(
        `select schemaname as schema, tablename as table from pg_tables
          where tablename = '__drizzle_migrations' order by schemaname limit 1`,
      );
      const found = journal.rows[0];
      if (found) {
        await pool.query(`delete from "${found.schema}"."${found.table}"`);
      }
      assert.ok(
        existsSync(`${MIGRATIONS_FOLDER}/meta/_journal.json`),
        `the committed migrations must be readable at ${MIGRATIONS_FOLDER}`,
      );
      await migrate(db, { migrationsFolder: MIGRATIONS_FOLDER });

      const [category] = await db
        .insert(categories)
        .values({ name: 'مانتو', slug: 'manto-notify' })
        .returning({ id: categories.id });
      categoryId = category?.id as string;

      const payload: ProductCreatePayload = {
        categoryId,
        title: 'مانتو کتان صف اطلاع‌رسانی',
        slug: SLUG,
        basePrice: 1_850_000,
        discountPrice: null,
        descriptionRaw: 'مانتو کتان برای آزمون صف اطلاع‌رسانی.',
        descriptionHtml: '<p>مانتو کتان</p>',
        fabricType: 'کتان',
        season: 'تابستان',
        status: 'PUBLISHED',
        // One variant, generous stock: every test places its own order against it.
        variants: [
          { sku: 'P6-BLK-S', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 40 },
        ],
        images: [],
      };
      const created = await createProduct(repo, payload);
      assert.ok(created.ok, `the live fixture must be written: ${JSON.stringify(created)}`);
      variantIds['P6-BLK-S'] = created.variantIds[0] as string;
    });

    after(async () => {
      await pool.end();
    });

    describe('migration 0004 — the outbox table and the guards it carries', () => {
      it('materialises the table, both enums, the unique index and the due-scan index', async () => {
        const columns = await pool.query<{ column_name: string }>(
          `select column_name from information_schema.columns
            where table_schema = 'commerce' and table_name = 'notification_outbox'
            order by column_name`,
        );
        assert.deepEqual(
          columns.rows.map((row) => row.column_name),
          [
            'attempts',
            'channel',
            'created_at',
            'id',
            'kind',
            'last_error',
            'next_attempt_at',
            'order_id',
            'payload',
            'provider_message_id',
            'sent_at',
            'status',
            'updated_at',
          ],
        );

        const enums = await pool.query<{ type: string; value: string }>(
          `select t.typname as type, e.enumlabel as value
             from pg_enum e
             join pg_type t on t.oid = e.enumtypid
             join pg_namespace ns on ns.oid = t.typnamespace
            where ns.nspname = 'commerce'
              and t.typname in ('notification_channel', 'notification_status')
            order by t.typname, e.enumsortorder`,
        );
        assert.deepEqual(
          enums.rows.map((row) => `${row.type}:${row.value}`),
          [
            'notification_channel:SMS',
            'notification_status:PENDING',
            'notification_status:SENDING',
            'notification_status:SENT',
            'notification_status:FAILED',
          ],
        );

        const unique = await pool.query<{ indexdef: string }>(
          `select indexdef from pg_indexes where indexname = 'notification_outbox_unique'`,
        );
        assert.match(
          unique.rows[0]?.indexdef as string,
          /CREATE UNIQUE INDEX .*\(order_id, kind, channel\)/,
          'one notification of a kind, on a channel, per order — the idempotency boundary',
        );

        const due = await pool.query<{ indexdef: string }>(
          `select indexdef from pg_indexes where indexname = 'notification_outbox_due_idx'`,
        );
        assert.match(due.rows[0]?.indexdef as string, /\(status, next_attempt_at\)/);

        const fk = await pool.query<{ confdeltype: string }>(
          `select confdeltype from pg_constraint
            where conname = 'notification_outbox_order_id_orders_id_fk'`,
        );
        assert.equal(fk.rows[0]?.confdeltype, 'c', 'deleting an order takes its queue with it');
      });

      it('refuses an unknown kind, a negative attempt count and a PENDING row that claims SENT', async () => {
        const orderId = await placeOrder('P6-BLK-S');

        // A kind is admitted by a migration, not by a caller that guessed.
        assert.equal(
          await refusalCode(() =>
            pool.query(
              `insert into commerce.notification_outbox (order_id, kind, channel)
               values ($1, 'order.shipped', 'SMS')`,
              [orderId],
            ),
          ),
          '23514',
          'notification_outbox_kind_known',
        );

        assert.equal(
          await refusalCode(() =>
            pool.query(
              `insert into commerce.notification_outbox (order_id, kind, channel, attempts)
               values ($1, 'order.confirmed', 'SMS', -1)`,
              [orderId],
            ),
          ),
          '23514',
          'notification_outbox_attempts_non_negative',
        );

        // SENT and sent_at are two spellings of one fact, in BOTH directions.
        assert.equal(
          await refusalCode(() =>
            pool.query(
              `insert into commerce.notification_outbox (order_id, kind, channel, status)
               values ($1, 'order.confirmed', 'SMS', 'SENT')`,
              [orderId],
            ),
          ),
          '23514',
          'notification_outbox_delivery_consistent',
        );

        assert.equal(
          await refusalCode(() =>
            pool.query(
              `insert into commerce.notification_outbox (order_id, kind, channel, sent_at)
               values ($1, 'order.confirmed', 'SMS', now())`,
              [orderId],
            ),
          ),
          '23514',
          'notification_outbox_delivery_consistent',
        );

        // The payload is an OBJECT of template variables, never an array or a body.
        assert.equal(
          await refusalCode(() =>
            pool.query(
              `insert into commerce.notification_outbox (order_id, kind, channel, payload)
               values ($1, 'order.confirmed', 'SMS', '[]'::jsonb)`,
              [orderId],
            ),
          ),
          '23514',
          'notification_outbox_payload_is_object',
        );

        assert.equal(await outboxCount(), 0, 'every refused insert left the queue empty');
      });

      it('refuses a second row for the same order, kind and channel', async () => {
        const orderId = await paidOrderWithQueue();

        assert.equal(
          await refusalCode(() =>
            pool.query(
              `insert into commerce.notification_outbox (order_id, kind, channel)
               values ($1, 'order.confirmed', 'SMS')`,
              [orderId],
            ),
          ),
          '23505',
          'notification_outbox_unique',
        );

        assert.equal((await outboxOf(orderId)).length, 1);
      });
    });


    describe('the transaction that marks an order paid also queues the announcement', () => {
      it('writes the row with the status move, holding no PII and no body', async () => {
        const orderId = await paidOrderWithQueue();

        const [row] = await outboxOf(orderId);
        assert.ok(row);
        assert.equal(row.kind, 'order.confirmed');
        assert.equal(row.channel, 'SMS');
        assert.equal(row.status, 'PENDING');
        assert.equal(row.attempts, 0);
        assert.equal(row.last_error, null);
        assert.equal(row.sent_at, null);
        assert.deepEqual(Object.keys(row.payload), ['orderRef'], 'only the order reference is snapshotted');

        // The whole row, rendered, must not contain the customer's number or a
        // message body: the recipient is read from `customers` at DISPATCH time.
        const serialised = JSON.stringify(row);
        assert.ok(!serialised.includes(PHONE), 'the queue must not hold a phone number');
        assert.ok(!serialised.includes('ثبت شد'), 'the queue must not hold a rendered body');
      });

      it('queues ONE row when two PAID writes race for the same order', async () => {
        const orderId = await placeOrder('P6-BLK-S');
        const intent = { kind: ORDER_CONFIRMED_KIND, channel: SMS_CHANNEL } as const;

        const results = await Promise.all([
          transitionOrder(repo, orderId, 'PAID', MERCHANT_TRANSITION, [intent]),
          transitionOrder(repo, orderId, 'PAID', MERCHANT_TRANSITION, [intent]),
        ]);
        assert.equal(
          results.filter((result) => result.ok).length,
          1,
          'exactly one concurrent writer may move the order',
        );

        const rows = await outboxOf(orderId);
        assert.equal(rows.length, 1, 'the unique index is the idempotency boundary, not the caller');

        const trail = await pool.query<{ n: number }>(
          `select count(*)::int as n from commerce.order_status_history
            where order_id = $1 and to_status = 'PAID'`,
          [orderId],
        );
        assert.equal(trail.rows[0]?.n, 1);
      });

      it('queues nothing for a transition that is not a payment', async () => {
        const orderId = await placeOrder('P6-BLK-S');
        const moved = await transitionOrder(repo, orderId, 'CANCELLED', MERCHANT_TRANSITION);
        assert.deepEqual(moved, { ok: true });
        assert.deepEqual(await outboxOf(orderId), []);
      });
    });


    describe('the claim is atomic: one row belongs to exactly one dispatcher', () => {
      /** Puts a fixture row back on the queue, as if it had never been claimed. */
      async function requeue(orderId: string): Promise<void> {
        await pool.query(
          `update commerce.notification_outbox
              set status = 'PENDING', attempts = 0, last_error = null,
                  next_attempt_at = now(), sent_at = null, updated_at = now()
            where order_id = $1`,
          [orderId],
        );
      }

      it('hands each due row to ONE of two racing claimants', async () => {
        const orderId = await paidOrderWithQueue();

        const [left, right] = await Promise.all([
          repo.claimNotificationBatch(1_000),
          repo.claimNotificationBatch(1_000),
        ]);
        const ids = [...left, ...right].map((item) => item.id);
        assert.equal(new Set(ids).size, ids.length, 'the two batches must be disjoint');

        const mine = left.filter((item) => item.orderId === orderId);
        const theirs = right.filter((item) => item.orderId === orderId);
        assert.equal(mine.length + theirs.length, 1, 'exactly one claimant owns the row');

        const [row] = await outboxOf(orderId);
        assert.equal(row?.status, 'SENDING', 'the claim IS the status change');
        assert.equal(row?.attempts, 1);

        assert.deepEqual(await repo.claimNotificationBatch(1_000), [], 'freshly claimed rows are not due');

        await requeue(orderId);
      });

      it('reclaims a STALE lease and leaves a fresh one alone', async () => {
        const orderId = await paidOrderWithQueue();

        const first = await repo.claimNotificationBatch(1_000);
        assert.ok(first.some((item) => item.orderId === orderId), 'the fresh row is claimable');

        const again = await repo.claimNotificationBatch(1_000);
        assert.ok(
          !again.some((item) => item.orderId === orderId),
          'a claimant inside its lease keeps the row',
        );

        // A dispatcher that died mid-send leaves `SENDING` behind. The lease is
        // what stops that from stranding the message forever.
        await pool.query(
          `update commerce.notification_outbox
              set updated_at = now() - interval '6 minutes'
            where order_id = $1`,
          [orderId],
        );

        const reclaimed = await repo.claimNotificationBatch(1_000);
        const mine = reclaimed.filter((item) => item.orderId === orderId);
        assert.equal(mine.length, 1, 'the expired lease is reclaimed');
        assert.equal(mine[0]?.attempts, 2, 'the reclaim counts as an attempt');

        await requeue(orderId);
      });

      it('keeps a spent row out of every future batch', async () => {
        const orderId = await paidOrderWithQueue();
        await pool.query(
          `update commerce.notification_outbox
              set attempts = 3, status = 'PENDING'
            where order_id = $1`,
          [orderId],
        );

        const batch = await repo.claimNotificationBatch(1_000);
        assert.ok(!batch.some((item) => item.orderId === orderId), 'the budget is what stops a bad row');

        await requeue(orderId);
      });
    });


    describe('the dispatcher delivers against the real queue', () => {
      /** A channel whose every answer is a transient refusal. */
      function retryableChannel(): {
        channel: SmsChannel;
        sends: Array<{ to: string; body: string }>;
      } {
        const sends: Array<{ to: string; body: string }> = [];
        const channel: SmsChannel = {
          id: 'mock',
          mode: 'MOCK',
          async send(message) {
            sends.push({ to: message.to, body: message.body });
            return { ok: false, code: 'provider_unavailable', retryable: true };
          },
        };
        return { channel, sends };
      }

      it('sends one message per order and never sends it twice', async () => {
        const first = await paidOrderWithQueue();
        const second = await paidOrderWithQueue();
        const channel = new MockSmsChannel();

        const initial = await dispatchNotifications(repo, channel, { limit: 1_000 });
        assert.ok(initial.sent >= 2, 'both queued orders must be delivered');

        const refs = [orderReference(first), orderReference(second)];
        const delivered = channel.calls.filter((call) => refs.some((ref) => call.body.includes(ref)));
        assert.equal(delivered.length, 2, 'each order produced exactly one message');
        assert.deepEqual(
          delivered.map((call) => call.to),
          [PHONE, PHONE],
          'the recipient is resolved from the customer record at dispatch time',
        );

        for (const orderId of [first, second]) {
          const [row] = await outboxOf(orderId);
          assert.equal(row?.status, 'SENT');
          assert.equal(row?.provider_message_id?.startsWith('MOCK-SMS-'), true);
          assert.ok(row?.sent_at instanceof Date, 'SENT and sent_at travel together');
          assert.equal(row?.last_error, null);
        }

        const before = channel.calls.length;
        await dispatchNotifications(repo, channel, { limit: 1_000 });
        const resent = channel.calls
          .slice(before)
          .filter((call) => refs.some((ref) => call.body.includes(ref)));
        assert.deepEqual(resent, [], 'a SENT row is never claimable again');
      });

      it('reschedules a transient refusal, then gives up when the budget is spent', async () => {
        const orderId = await paidOrderWithQueue();
        const { channel, sends } = retryableChannel();

        const now = Date.now();
        for (let attempt = 0; attempt < 3; attempt += 1) {
          await dispatchNotifications(repo, channel, {
            // Well past every backoff in the table, so each run is due.
            now: () => new Date(now + attempt * 3_600_000),
          });
        }

        const [row] = await outboxOf(orderId);
        assert.equal(row?.status, 'FAILED');
        assert.equal(row?.attempts, 3);
        assert.equal(row?.last_error, 'provider_unavailable');
        assert.equal(row?.sent_at, null);

        const attemptsSoFar = sends.length;
        await dispatchNotifications(repo, channel, { now: () => new Date(now + 86_400_000) });
        assert.equal(sends.length, attemptsSoFar, 'a spent row is never retried');
        assert.equal((await outboxOf(orderId))[0]?.attempts, 3);
      });

      it('drains the queue through the operator endpoint, and refuses a caller without the token', async () => {
        const orderId = await paidOrderWithQueue();
        const channel = new MockSmsChannel();
        const resolution = { ok: true, channel, mode: 'MOCK' } as const;

        const request = (authorization?: string) =>
          new Request('http://localhost/api/internal/notifications/dispatch', {
            method: 'POST',
            headers: authorization === undefined ? {} : { authorization },
          });

        const refused = await handleNotificationDispatchRequest(request(), {
          token: TOKEN,
          getRepository: () => repo,
          channel: resolution,
        });
        assert.equal(refused.status, 401);
        assert.equal((await outboxOf(orderId))[0]?.status, 'PENDING', '401 claims nothing');

        const accepted = await handleNotificationDispatchRequest(request(`Bearer ${TOKEN}`), {
          token: TOKEN,
          getRepository: () => repo,
          channel: resolution,
          limit: 1_000,
        });
        assert.equal(accepted.status, 200);
        assert.equal(accepted.headers.get('cache-control'), 'no-store');

        const body = (await accepted.json()) as {
          ok: boolean;
          mode: string;
          report: { claimed: number; sent: number };
        };
        assert.equal(body.ok, true);
        assert.equal(body.mode, 'MOCK');
        assert.ok(body.report.sent >= 1);
        assert.equal((await outboxOf(orderId))[0]?.status, 'SENT');
      });
    });
  },
);

