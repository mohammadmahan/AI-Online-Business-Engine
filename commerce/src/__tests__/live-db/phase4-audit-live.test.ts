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
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import { mockPaymentGateway } from '@/server/payments/gateway';
import { createRepositoryPaymentAuthorizationStore } from '@/server/payments/authority-store';
import {
  ZARINPAL_PROVIDER,
  createZarinPalGateway,
} from '@/server/payments/zarinpal';
import {
  WEBHOOK_SECRET_ENV,
  WEBHOOK_SIGNATURE_HEADER,
  signWebhookBody,
} from '@/server/payments/webhook-signature';
import { createPostgresRepository, type CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import { updateStock } from '@/server/services/inventory';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';
import { handleZarinPalCallback } from '@/server/services/payment-callback';
import { handlePaymentWebhook } from '@/server/services/payment-webhook';
import { createProduct } from '@/server/services/products';

/**
 * D-172 Phase 4 transition — the LIVE audit-trail and callback suite (disposable
 * harness).
 *
 * Two Phase 4-transition claims are only worth anything against a real server,
 * because both are TRANSACTIONAL claims:
 *
 *   1. an order's status move and its audit row commit TOGETHER — an order
 *      cannot move without a trail, and a refused move leaves neither;
 *   2. the trail's own storage guards (one row per reached status, no
 *      self-transition, no origin-less row that is not the creation) hold under
 *      a genuine constraint violation, which is what makes a retried provider
 *      callback harmless.
 *
 * The in-memory double cannot demonstrate either: it models behaviour, not
 * atomicity, and it has no constraints. So the suite below drives the REAL
 * Postgres repository, provokes a REAL 23505 by hand to force a rollback, and
 * reads every assertion back out of `commerce.order_status_history` with SQL
 * rather than trusting a service's return value. It also drives the webhook
 * pipeline itself (a `Request` in, a `Response` out) against that database, so
 * the callback path persisting its row is proven end to end rather than unit
 * tested only.
 *
 * Target and gates are identical to `phase2-live.test.ts` / `phase3`: the
 * disposable loopback harness only, SKIP with a named reason when
 * `COMMERCE_DATABASE_URL` is absent or not loopback (an absent configuration is
 * a refusal, never a pass — D-171 §2.2), and a full schema reset plus the
 * COMMITTED migrations on every run so the migration evidence is produced rather
 * than assumed.
 *
 * `npm run smoke:db` runs the live directory with `--test-concurrency=1`: all
 * three files share one database and each drops the schema, so in parallel
 * processes one file would truncate another's fixtures mid-run.
 */

const HARNESS_URL = process.env.COMMERCE_DATABASE_URL?.trim();
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function skipReason(): string | undefined {
  if (!HARNESS_URL) {
    return 'COMMERCE_DATABASE_URL not set — live audit-trail suite skipped (no target is guessed; fail-closed)';
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

const SLUG = 'manto-audit-p4';
const COUPON_FREE_DRAFT = DEFAULT_SHIPPING_METHOD_ID;
const SECRET = 'live-harness-webhook-secret';

describe(
  'D-172 Phase 4 transition — live audit trail and payment callback (disposable harness)',
  { skip: skipReason() },
  () => {
    let pool!: Pool;
    let db!: CommerceDb;
    let repo!: CommerceRepository;

    let categoryId = '';
    const variantIds: Record<string, string> = {};

    interface HistoryRow {
      from_status: string | null;
      to_status: string;
      source: string;
      metadata: Record<string, unknown> | null;
    }

    /**
     * The SQLSTATE of a refused call, unwrapping the cause chain.
     *
     * Drizzle wraps what the driver throws — the outer error is a `Failed query`
     * Error with no code, and the PostgreSQL error sits on its `cause` — so an
     * assertion that reads only the top level would see `undefined` and quietly
     * mean nothing. (The raw `pool.query` calls above need no unwrapping: nothing
     * wraps those.)
     */
    async function refusalState(run: () => Promise<unknown>): Promise<string> {
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
      assert.fail('the repository ACCEPTED a write that must be refused');
    }

    async function historyOf(orderId: string): Promise<HistoryRow[]> {
      const { rows } = await pool.query<HistoryRow>(
        `select from_status, to_status, source, metadata
           from commerce.order_status_history
          where order_id = $1
          order by created_at, to_status`,
        [orderId],
      );
      return rows;
    }

    async function statusOf(orderId: string): Promise<string> {
      const { rows } = await pool.query<{ status: string }>(
        'select status from commerce.orders where id = $1',
        [orderId],
      );
      assert.equal(rows.length, 1, 'the order row must exist');
      return rows[0]?.status as string;
    }

    async function stockOfSku(sku: string): Promise<number> {
      const { rows } = await pool.query<{ stock_quantity: number }>(
        'select stock_quantity from commerce.product_variants where id = $1',
        [variantIds[sku] as string],
      );
      return rows[0]?.stock_quantity as number;
    }

    async function historyCount(): Promise<number> {
      const { rows } = await pool.query<{ n: number }>(
        'select count(*)::int as n from commerce.order_status_history',
      );
      return rows[0]?.n as number;
    }

    /**
     * Tops a variant up through the REAL §2.2 service. The orders below share one
     * fixture, so an exact starting quantity has to be stated rather than
     * inherited from whatever the previous test consumed.
     */
    async function setStock(sku: string, quantity: number): Promise<void> {
      const result = await updateStock(repo, variantIds[sku] as string, quantity);
      assert.ok(result.ok, `the fixture stock must be settable: ${JSON.stringify(result)}`);
      assert.equal(await stockOfSku(sku), quantity);
    }

    /** A real storefront order, through the real write path. */
    async function placeOrder(sku: string, quantity: number): Promise<string> {
      const draft: CheckoutDraft = {
        customer: {
          fullName: 'زهرا محمدی',
          phoneNumber: '۰۹۱۲۳۴۵۶۷۸۹',
          address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
          postalCode: '۱۹۹۹۹۹۹۹۹۹',
        },
        couponCode: null,
        shippingMethodId: COUPON_FREE_DRAFT,
        lines: [{ variantId: variantIds[sku] as string, quantity }],
      };
      const placed = await placeCheckoutOrder(repo, mockPaymentGateway, draft);
      assert.ok(placed.ok, `the live order must be written: ${JSON.stringify(placed)}`);
      return placed.orderId;
    }

    /** A signed callback request, exactly as the endpoint receives one. */
    function callbackRequest(payload: Record<string, unknown>): Request {
      const rawBody = JSON.stringify(payload);
      return new Request('http://localhost/api/webhooks/payment', {
        method: 'POST',
        body: rawBody,
        headers: { [WEBHOOK_SIGNATURE_HEADER]: signWebhookBody(rawBody, SECRET) },
      });
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
        .values({ name: 'مانتو', slug: 'manto-audit' })
        .returning({ id: categories.id });
      categoryId = category?.id as string;

      const payload: ProductCreatePayload = {
        categoryId,
        title: 'مانتو کتان دفتر رخداد',
        slug: SLUG,
        basePrice: 2_450_000,
        discountPrice: null,
        descriptionRaw: 'مانتو کتان برای آزمون دفتر رخداد وضعیت.',
        descriptionHtml: '<p>مانتو کتان</p>',
        fabricType: 'کتان',
        season: 'تابستان',
        status: 'PUBLISHED',
        // Generous on purpose: several tests below place their own order against
        // this one fixture, and each states the stock it needs explicitly.
        variants: [
          { sku: 'P4-BLK-S', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 20 },
          { sku: 'P4-WHT-M', colorName: 'سفید', colorHex: '#FFFFFF', size: 'M', stockQuantity: 2 },
        ],
        images: [],
      };
      const created = await createProduct(repo, payload);
      assert.ok(created.ok, `the live fixture must be written: ${JSON.stringify(created)}`);
      variantIds['P4-BLK-S'] = created.variantIds[0] as string;
      variantIds['P4-WHT-M'] = created.variantIds[1] as string;
    });

    after(async () => {
      await pool.end();
    });

    describe('migration 0002 — the audit table and the guards it carries', () => {
      it('materialises the table, the enum, the cascade, the unique index and both CHECKs', async () => {
        const columns = await pool.query<{ column_name: string; is_nullable: string }>(
          `select column_name, is_nullable from information_schema.columns
            where table_schema = 'commerce' and table_name = 'order_status_history'
            order by column_name`,
        );
        assert.deepEqual(
          columns.rows.map((row) => row.column_name),
          ['created_at', 'from_status', 'id', 'metadata', 'order_id', 'source', 'to_status'],
        );
        assert.equal(
          columns.rows.find((row) => row.column_name === 'from_status')?.is_nullable,
          'YES',
          'the creation row has no origin, which is why the column is nullable',
        );

        const values = await pool.query<{ v: string }>(
          `select e.enumlabel as v from pg_enum e
             join pg_type t on t.oid = e.enumtypid
             join pg_namespace ns on ns.oid = t.typnamespace
            where ns.nspname = 'commerce' and t.typname = 'order_status_source'
            order by e.enumsortorder`,
        );
        assert.deepEqual(
          values.rows.map((row) => row.v),
          ['STOREFRONT', 'MERCHANT_PANEL', 'PAYMENT_CALLBACK', 'SYSTEM'],
        );

        const fk = await pool.query<{ confdeltype: string }>(
          `select confdeltype from pg_constraint
             where conname = 'order_status_history_order_id_orders_id_fk'`,
        );
        assert.equal(fk.rows[0]?.confdeltype, 'c', 'deleting an order takes its history with it');
      });

      it('refuses a self-transition, an origin-less non-creation row and a repeated status', async () => {
        const orderId = await placeOrder('P4-BLK-S', 1);

        /** The SQLSTATE of a statement that must be refused. */
        async function refusal(run: () => Promise<unknown>): Promise<string> {
          try {
            await run();
          } catch (error) {
            const code = (error as { code?: unknown }).code;
            return typeof code === 'string' ? code : 'unknown';
          }
          assert.fail('the database ACCEPTED a row the audit trail must refuse');
        }

        // from = to: nothing changed, so nothing may be recorded.
        assert.equal(
          await refusal(() =>
            pool.query(
              `insert into commerce.order_status_history (order_id, from_status, to_status, source)
               values ($1, 'PENDING', 'PENDING', 'SYSTEM')`,
              [orderId],
            ),
          ),
          '23514',
          'order_status_history_status_changes',
        );

        // An origin-less row that is not the creation of the order.
        assert.equal(
          await refusal(() =>
            pool.query(
              `insert into commerce.order_status_history (order_id, from_status, to_status, source)
               values ($1, null, 'PAID', 'SYSTEM')`,
              [orderId],
            ),
          ),
          '23514',
          'order_status_history_creation_has_no_origin',
        );

        // The status this order already reached, a second time: the storage-level
        // idempotency boundary a replayed callback relies on.
        assert.equal(
          await refusal(() =>
            pool.query(
              `insert into commerce.order_status_history (order_id, from_status, to_status, source)
               values ($1, 'PAID', 'PENDING', 'SYSTEM')`,
              [orderId],
            ),
          ),
          '23505',
          'order_status_history_order_to_status_unique',
        );

        assert.deepEqual(
          (await historyOf(orderId)).map((row) => [row.from_status, row.to_status, row.source]),
          [[null, 'PENDING', 'STOREFRONT']],
          'every refused insert left the trail exactly as it was',
        );
      });
    });

    describe('the write path appends the trail in its own transaction', () => {
      it('records the storefront’s opening row with the order it created', async () => {
        const orderId = await placeOrder('P4-WHT-M', 1);

        assert.deepEqual(await historyOf(orderId), [
          {
            from_status: null,
            to_status: 'PENDING',
            source: 'STOREFRONT',
            metadata: null,
          },
        ]);
      });

      it('writes NOTHING when the checkout is refused', async () => {
        const before = await historyCount();
        await setStock('P4-WHT-M', 2);

        const refused = await placeCheckoutOrder(repo, mockPaymentGateway, {
          customer: {
            fullName: 'زهرا محمدی',
            phoneNumber: '09123456789',
            address: 'تهران',
            postalCode: '1999999999',
          },
          couponCode: null,
          shippingMethodId: COUPON_FREE_DRAFT,
          lines: [{ variantId: variantIds['P4-WHT-M'] as string, quantity: 5 }],
        });
        assert.ok(!refused.ok, 'the oversell must be refused');

        assert.equal(await historyCount(), before, 'a refused order leaves no audit row');
      });

      it('appends the merchant’s row for a transition, with the previous status read under the lock', async () => {
        const orderId = await placeOrder('P4-BLK-S', 1);

        const moved = await transitionOrder(repo, orderId, 'PAID', {
          source: 'MERCHANT_PANEL',
          metadata: { note: 'kart-be-kart' },
        });
        assert.deepEqual(moved, { ok: true });

        assert.deepEqual(await historyOf(orderId), [
          { from_status: null, to_status: 'PENDING', source: 'STOREFRONT', metadata: null },
          {
            from_status: 'PENDING',
            to_status: 'PAID',
            source: 'MERCHANT_PANEL',
            metadata: { note: 'kart-be-kart' },
          },
        ]);
        assert.equal(await statusOf(orderId), 'PAID');
      });

      it('records the cancellation AND returns the stock, once', async () => {
        await setStock('P4-WHT-M', 2);
        const orderId = await placeOrder('P4-WHT-M', 2);
        assert.equal(await stockOfSku('P4-WHT-M'), 0, 'the order took the last pieces');

        assert.deepEqual(await transitionOrder(repo, orderId, 'CANCELLED', MERCHANT_TRANSITION), {
          ok: true,
        });
        assert.equal(await stockOfSku('P4-WHT-M'), 2, 'and the shelf is whole again');

        const afterCancel = await historyOf(orderId);
        // The white variant was ordered twice above, so its stock moves between
        // tests; the assertion that matters is the ORDER's own trail.
        assert.deepEqual(
          afterCancel.map((row) => [row.from_status, row.to_status, row.source]),
          [
            [null, 'PENDING', 'STOREFRONT'],
            ['PENDING', 'CANCELLED', 'MERCHANT_PANEL'],
          ],
        );

        // The service refuses a repeat before any write...
        const again = await transitionOrder(repo, orderId, 'CANCELLED', MERCHANT_TRANSITION);
        assert.equal(again.ok, false);
        // ...and the repository's own no-op branch covers a direct caller.
        assert.equal(
          await repo.updateOrderStatus(orderId, 'CANCELLED', MERCHANT_TRANSITION),
          true,
          'a repeat reports success without writing anything',
        );
        assert.deepEqual(await historyOf(orderId), afterCancel, 'no second row, no second restock');
        assert.equal(await stockOfSku('P4-WHT-M'), 2);
      });

      it('ROLLS BACK the status move when the trail cannot be written — the two are one transaction', async () => {
        const orderId = await placeOrder('P4-BLK-S', 1);

        // Occupy the status the transition will try to record, using the table's
        // own unique index as the lever: the history INSERT must fail, and with
        // it the order update it shares a transaction with.
        await pool.query(
          `insert into commerce.order_status_history (order_id, from_status, to_status, source)
           values ($1, 'PENDING', 'PAID', 'SYSTEM')`,
          [orderId],
        );

        assert.equal(
          await refusalState(() => repo.updateOrderStatus(orderId, 'PAID', MERCHANT_TRANSITION)),
          '23505',
        );

        assert.equal(
          await statusOf(orderId),
          'PENDING',
          'the order must NOT have moved: its audit row could not be written',
        );
        assert.deepEqual(
          (await historyOf(orderId)).map((row) => [row.from_status, row.to_status, row.source]),
          [
            [null, 'PENDING', 'STOREFRONT'],
            ['PENDING', 'PAID', 'SYSTEM'],
          ],
          'the trail holds the opening row and the manual one — nothing the failed transition attempted',
        );
      });

      it('cascades the trail away with its order', async () => {
        const orderId = await placeOrder('P4-BLK-S', 1);
        assert.equal((await historyOf(orderId)).length, 1);

        await pool.query('delete from commerce.orders where id = $1', [orderId]);

        assert.deepEqual(await historyOf(orderId), []);
      });
    });

    describe('the payment callback seam, against real PostgreSQL', () => {
      it('answers 503 and writes nothing while no secret is configured', async () => {
        await setStock('P4-BLK-S', 20);
        const orderId = await placeOrder('P4-BLK-S', 1);
        const before = await historyCount();
        assert.equal(process.env[WEBHOOK_SECRET_ENV], undefined, 'the harness must not set a secret');

        // No dependencies: the production wiring, where the secret and the
        // connection both come from the environment.
        const response = await handlePaymentWebhook(
          callbackRequest({ orderId, status: 'PAID', reference: 'GW-LIVE-1' }),
        );
        assert.equal(response.status, 503);
        assert.equal(((await response.json()) as { code: string }).code, 'WEBHOOK_NOT_CONFIGURED');

        assert.equal(await statusOf(orderId), 'PENDING');
        assert.equal(await historyCount(), before);
      });

      it('moves the order to PAID, stores the reference and appends the callback’s row', async () => {
        const orderId = await placeOrder('P4-BLK-S', 1);
        const deps = { secret: SECRET, getRepository: () => repo };

        const response = await handlePaymentWebhook(
          callbackRequest({ eventId: 'evt-live-1', orderId, status: 'PAID', reference: 'GW-LIVE-2' }),
          deps,
        );
        assert.equal(response.status, 200, await response.clone().text());
        assert.deepEqual(await response.json(), {
          ok: true,
          orderId,
          status: 'PAID',
          duplicate: false,
        });

        const order = await repo.getOrderDetail(orderId);
        assert.equal(order?.status, 'PAID');
        assert.equal(order?.paymentRefId, 'GW-LIVE-2');

        assert.deepEqual(await historyOf(orderId), [
          { from_status: null, to_status: 'PENDING', source: 'STOREFRONT', metadata: null },
          {
            from_status: 'PENDING',
            to_status: 'PAID',
            source: 'PAYMENT_CALLBACK',
            metadata: { eventId: 'evt-live-1', reference: 'GW-LIVE-2' },
          },
        ]);
      });

      it('answers a REPLAY as a duplicate success, and the storage guard backs the no-op up', async () => {
        const orderId = await placeOrder('P4-BLK-S', 1);
        const deps = { secret: SECRET, getRepository: () => repo };

        assert.equal(
          (
            await handlePaymentWebhook(
              callbackRequest({ orderId, status: 'PAID', reference: 'GW-LIVE-3' }),
              deps,
            )
          ).status,
          200,
        );
        const afterFirst = await historyOf(orderId);

        const replay = await handlePaymentWebhook(
          callbackRequest({ orderId, status: 'PAID', reference: 'GW-LIVE-3' }),
          deps,
        );
        assert.equal(replay.status, 200, 'a provider that sees an error would retry forever');
        assert.equal(((await replay.json()) as { duplicate: boolean }).duplicate, true);

        assert.deepEqual(await historyOf(orderId), afterFirst, 'a replay appends nothing');
        assert.equal((await repo.getOrderDetail(orderId))?.paymentRefId, 'GW-LIVE-3');

        // Even a DIRECT second attempt at the same status is a no-op, and the
        // unique index would refuse the row if it ever were not.
        assert.equal(await repo.updateOrderStatus(orderId, 'PAID', MERCHANT_TRANSITION), true);
        assert.deepEqual(await historyOf(orderId), afterFirst);
      });

      it('returns the reserved stock for a callback that cancels, exactly once', async () => {
        await setStock('P4-WHT-M', 2);
        const orderId = await placeOrder('P4-WHT-M', 2);
        assert.equal(await stockOfSku('P4-WHT-M'), 0);
        const deps = { secret: SECRET, getRepository: () => repo };

        const cancelled = await handlePaymentWebhook(
          callbackRequest({ orderId, status: 'CANCELLED' }),
          deps,
        );
        assert.equal(cancelled.status, 200);
        assert.equal(await stockOfSku('P4-WHT-M'), 2);

        const replay = await handlePaymentWebhook(
          callbackRequest({ orderId, status: 'CANCELLED' }),
          deps,
        );
        assert.equal(((await replay.json()) as { duplicate: boolean }).duplicate, true);
        assert.equal(await stockOfSku('P4-WHT-M'), 2, 'the second delivery returns nothing');

        assert.deepEqual(
          (await historyOf(orderId)).map((row) => [row.from_status, row.to_status, row.source]),
          [
            [null, 'PENDING', 'STOREFRONT'],
            ['PENDING', 'CANCELLED', 'PAYMENT_CALLBACK'],
          ],
        );
      });

      it('rejects a forged signature and refuses a callback the lifecycle forbids', async () => {
        const orderId = await placeOrder('P4-BLK-S', 1);
        const before = await historyOf(orderId);

        const forged = new Request('http://localhost/api/webhooks/payment', {
          method: 'POST',
          body: JSON.stringify({ orderId, status: 'PAID', reference: 'GW-FORGED' }),
          headers: { [WEBHOOK_SIGNATURE_HEADER]: 'f'.repeat(64) },
        });
        const rejected = await handlePaymentWebhook(forged, {
          secret: SECRET,
          getRepository: () => repo,
        });
        assert.equal(rejected.status, 401);
        assert.equal(await statusOf(orderId), 'PENDING');
        assert.deepEqual(await historyOf(orderId), before);

        // A callback may not assert a fulfilment status at all.
        const fulfilment = await handlePaymentWebhook(
          callbackRequest({ orderId, status: 'PROCESSING' }),
          { secret: SECRET, getRepository: () => repo },
        );
        assert.equal(fulfilment.status, 400);
        assert.equal(((await fulfilment.json()) as { code: string }).code, 'INVALID_EVENT');
        assert.deepEqual(await historyOf(orderId), before);
      });

      it('converges CONCURRENT duplicate deliveries against real PostgreSQL: one row, one reference', async () => {
        await setStock('P4-BLK-S', 20);
        const orderId = await placeOrder('P4-BLK-S', 1);
        const deps = { secret: SECRET, getRepository: () => repo };

        // Four deliveries in flight together, each with its own event id: the
        // pre-read guard cannot separate them, so the arbiters have to be the row
        // lock in `updateOrderStatus` and the unique `(order_id, to_status)`
        // index. A loser must converge on success, not on a 409 the provider would
        // retry forever.
        const responses = await Promise.all(
          Array.from({ length: 4 }, (_, index) =>
            handlePaymentWebhook(
              callbackRequest({
                eventId: `evt-live-race-${index}`,
                orderId,
                status: 'PAID',
                reference: 'GW-LIVE-RACE',
              }),
              deps,
            ),
          ),
        );

        assert.deepEqual(
          responses.map((response) => response.status),
          [200, 200, 200, 200],
          'a converged duplicate must not be reported as a conflict',
        );
        await Promise.all(responses.map((response) => response.json()));

        const paid = (await historyOf(orderId)).filter((row) => row.to_status === 'PAID');
        assert.equal(paid.length, 1, 'the trail records one PAID transition, not four');
        assert.equal(paid[0]?.source, 'PAYMENT_CALLBACK');
        assert.equal(await statusOf(orderId), 'PAID');
        assert.equal((await repo.getOrderDetail(orderId))?.paymentRefId, 'GW-LIVE-RACE');
      });

      it('completes an order through the ZarinPal BROWSER RETURN against real PostgreSQL', async () => {
        await setStock('P4-BLK-S', 20);
        const orderId = await placeOrder('P4-BLK-S', 1);
        const order = await repo.getOrderDetail(orderId);
        assert.ok(order, 'the live order must exist');
        const authority = 'A000000000000000000000000000live1';

        // The durable half of the REQUEST step, exactly as the adapter writes it.
        assert.equal(
          await repo.recordPaymentAuthorization({
            orderId,
            provider: ZARINPAL_PROVIDER,
            authority,
            amount: order.totalAmount,
          }),
          true,
        );

        const calls: Array<{ url: string; amount: unknown }> = [];
        const gateway = createZarinPalGateway({
          config: {
            merchantId: 'live-merchant-test',
            callbackUrl: 'https://shop.example.test/api/payments/zarinpal/callback',
            sandbox: true,
          },
          transport: async (request) => {
            calls.push({ url: request.url, amount: request.body.amount });
            return { status: 200, body: { data: { code: 100, ref_id: 'ZP-LIVE-1' } } };
          },
          store: createRepositoryPaymentAuthorizationStore(() => repo),
        });
        const deps = { getRepository: () => repo, gateway };
        const returnUrl = (status: string) =>
          new Request(
            `http://localhost/api/payments/zarinpal/callback?Authority=${authority}&Status=${status}`,
          );

        const first = await handleZarinPalCallback(returnUrl('OK'), deps);
        assert.equal(first.status, 200, await first.clone().text());
        assert.deepEqual(await first.json(), {
          ok: true,
          orderId,
          status: 'PAID',
          duplicate: false,
          message: 'پرداخت با موفقیت تأیید شد.',
        });

        // The amount came from the ORDER ROW (Toman -> Rial once), never from the
        // query string the customer could edit.
        assert.equal(calls.length, 1);
        assert.match(calls[0]?.url ?? '', /\/pg\/v4\/payment\/verify\.json$/);
        assert.equal(calls[0]?.amount, order.totalAmount * 10);

        const history = await historyOf(orderId);
        assert.deepEqual(
          history.map((row) => [row.from_status, row.to_status, row.source]),
          [
            [null, 'PENDING', 'STOREFRONT'],
            ['PENDING', 'PAID', 'PAYMENT_CALLBACK'],
          ],
        );
        assert.deepEqual(history[1]?.metadata, {
          provider: ZARINPAL_PROVIDER,
          authority,
          verification: 'ZARINPAL_VERIFIED',
          reference: 'ZP-LIVE-1',
        });
        assert.equal((await repo.getOrderDetail(orderId))?.paymentRefId, 'ZP-LIVE-1');

        // A refresh of the SAME return is a duplicate: no second row, no second
        // status write, no second reference.
        const replay = await handleZarinPalCallback(returnUrl('OK'), deps);
        assert.equal(replay.status, 200, 'a provider that sees an error would retry forever');
        assert.equal(((await replay.json()) as { duplicate: boolean }).duplicate, true);
        assert.deepEqual(await historyOf(orderId), history);
      });
    });
  },
);
