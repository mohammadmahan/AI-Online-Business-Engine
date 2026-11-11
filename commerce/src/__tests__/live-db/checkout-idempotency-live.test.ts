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
import { createMockPaymentGateway, type PaymentGateway } from '@/server/payments/gateway';
import { createPostgresRepository, type CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import { createCoupon } from '@/server/services/coupons';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §3.3 hardening — checkout idempotency against REAL PostgreSQL.
 *
 * The unit suite proves the service/repository contract on the in-memory double;
 * this suite proves the properties only the database can: the unique index, the
 * transaction-scoped advisory lock that serialises concurrent same-key writers,
 * rollback of an uncommitted key, and exactly-once stock/coupon/history effects.
 *
 * Target is the disposable loopback harness (`docker-compose.db.yml`). An absent
 * or non-loopback `COMMERCE_DATABASE_URL` skips the whole suite rather than
 * guessing a target. The schema is dropped and the COMMITTED migrations are
 * re-applied so the run starts from the same empty state every time.
 */

const HARNESS_URL = process.env.COMMERCE_DATABASE_URL?.trim();
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function skipReason(): string | undefined {
  if (!HARNESS_URL) {
    return 'COMMERCE_DATABASE_URL not set — live checkout idempotency suite skipped (fail-closed)';
  }
  try {
    const target = new URL(HARNESS_URL);
    if (!LOOPBACK_HOSTS.has(target.hostname)) {
      return `COMMERCE_DATABASE_URL host "${target.hostname}" is not loopback — refusing to write to a non-local instance`;
    }
  } catch {
    return 'COMMERCE_DATABASE_URL is not a parseable URL — skipped';
  }
  return undefined;
}

const MIGRATIONS_FOLDER = fileURLToPath(new URL('../../../drizzle', import.meta.url));

const SLUG = 'idem-manto-live';
const COUPON_CODE = 'IDEM10';

const STOCK: Record<string, number> = {
  'IDEM-A': 4,
  'IDEM-B': 1,
  'IDEM-C': 3,
  'IDEM-D': 3,
};

describe(
  'checkout idempotency — live PostgreSQL exactly-once guarantees',
  { skip: skipReason() },
  () => {
    let pool!: Pool;
    let db!: CommerceDb;
    let repo!: CommerceRepository;
    const variantIds: Record<string, string> = {};

    function draft(
      variantId: string,
      quantity: number,
      idempotencyKey: string,
      couponCode: string | null = null,
    ): CheckoutDraft {
      return {
        customer: {
          fullName: 'زهرا محمدی',
          phoneNumber: '09123456789',
          address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
          postalCode: '1999999999',
        },
        couponCode,
        shippingMethodId: DEFAULT_SHIPPING_METHOD_ID,
        lines: [{ variantId, quantity }],
        idempotencyKey,
      };
    }

    async function stockOf(sku: string): Promise<number> {
      const { rows } = await pool.query<{ stock_quantity: number }>(
        'select stock_quantity from commerce.product_variants where id = $1',
        [variantIds[sku]],
      );
      assert.equal(rows.length, 1, 'the variant row must exist');
      return rows[0]?.stock_quantity as number;
    }

    async function orderCountForKey(key: string): Promise<number> {
      const { rows } = await pool.query<{ n: number }>(
        'select count(*)::int as n from commerce.orders where idempotency_key = $1',
        [key],
      );
      return rows[0]?.n as number;
    }

    async function orderCount(): Promise<number> {
      const { rows } = await pool.query<{ n: number }>(
        'select count(*)::int as n from commerce.orders',
      );
      return rows[0]?.n as number;
    }

    async function historyCount(orderId: string): Promise<number> {
      const { rows } = await pool.query<{ n: number }>(
        'select count(*)::int as n from commerce.order_status_history where order_id = $1',
        [orderId],
      );
      return rows[0]?.n as number;
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
        .values({ name: 'مانتو', slug: 'idem-live', description: 'دستهٔ آزمون idempotency' })
        .returning({ id: categories.id });
      assert.ok(category, 'the fixture category must be written');

      const product: ProductCreatePayload = {
        categoryId: category.id,
        title: 'مانتو آزمون idempotency',
        slug: SLUG,
        basePrice: 1_000_000,
        discountPrice: null,
        descriptionRaw: 'مانتو برای آزمون ثبت تکراری.',
        descriptionHtml: '<p>مانتو</p>',
        fabricType: 'کتان',
        season: 'تابستان',
        status: 'PUBLISHED',
        variants: Object.entries(STOCK).map(([sku, stockQuantity]) => ({
          sku,
          colorName: 'مشکی',
          colorHex: '#111111',
          size: sku.slice(-1),
          stockQuantity,
        })),
        images: [],
      };
      const created = await createProduct(repo, product);
      assert.ok(created.ok, `createProduct refused the fixture: ${JSON.stringify(created)}`);
      Object.keys(STOCK).forEach((sku, index) => {
        const id = created.variantIds[index];
        assert.ok(id, `the fixture variant ${sku} must have been created`);
        variantIds[sku] = id;
      });

      const coupon = await createCoupon(repo, {
        code: COUPON_CODE,
        discountType: 'PERCENT',
        discountValue: 10,
        minSpend: 0,
        usageLimit: 10,
        description: 'کد آزمون ثبت تکراری',
      });
      assert.ok(coupon.ok, 'createCoupon refused the fixture coupon');
    });

    after(async () => {
      await pool.end();
    });

    it('a. duplicate key returns the same order and writes stock/coupon/history once', async () => {
      const key = crypto.randomUUID();
      const orderDraft = draft(variantIds['IDEM-A'] as string, 1, key, COUPON_CODE);
      const beforeOrders = await orderCount();

      const first = await placeCheckoutOrder(repo, createMockPaymentGateway(), orderDraft);
      assert.ok(first.ok, `the first submission must be written: ${JSON.stringify(first)}`);
      assert.equal(first.replayed, false);
      assert.equal(await stockOf('IDEM-A'), 3);
      assert.equal((await repo.findCouponByCode(COUPON_CODE))?.usedCount, 1);

      const duplicate = await placeCheckoutOrder(repo, createMockPaymentGateway(), orderDraft);
      assert.ok(duplicate.ok);
      assert.equal(duplicate.orderId, first.orderId);
      assert.equal(duplicate.replayed, true);
      assert.equal(duplicate.totals.total, first.totals.total);
      assert.equal(duplicate.couponApplied, true);

      assert.equal(await orderCount(), beforeOrders + 1, 'one order, not two');
      assert.equal(await stockOf('IDEM-A'), 3, 'stock decremented exactly once');
      assert.equal((await repo.findCouponByCode(COUPON_CODE))?.usedCount, 1);
      assert.equal(await historyCount(first.orderId), 1, 'one opening status row');
      assert.equal(await orderCountForKey(key), 1);
    });

    it('b. concurrent submissions with one key resolve to one order', async () => {
      const key = crypto.randomUUID();
      const orderDraft = draft(variantIds['IDEM-B'] as string, 1, key);
      const beforeOrders = await orderCount();

      const results = await Promise.all([
        placeCheckoutOrder(repo, createMockPaymentGateway(), orderDraft),
        placeCheckoutOrder(repo, createMockPaymentGateway(), orderDraft),
      ]);

      assert.ok(results[0]?.ok, `first concurrent result refused: ${JSON.stringify(results[0])}`);
      assert.ok(results[1]?.ok, `second concurrent result refused: ${JSON.stringify(results[1])}`);
      assert.equal(results[0]?.orderId, results[1]?.orderId);
      assert.equal(results.filter((result) => result.ok && result.replayed).length, 1);
      assert.equal(await orderCount(), beforeOrders + 1);
      assert.equal(await stockOf('IDEM-B'), 0, 'the last piece was consumed once');
    });

    it('c. different keys create distinct orders', async () => {
      // Deliberately absent from the earlier suite: two writers race with the
      // SAME key but DIFFERENT payloads. Exactly one may create an order; the
      // other must be refused as a mismatch, with no second stock/coupon edit.
      const key = crypto.randomUUID();
      const firstPayload = draft(variantIds['IDEM-D'] as string, 1, key);
      const secondPayload = draft(variantIds['IDEM-D'] as string, 2, key);
      const beforeOrders = await orderCount();
      const beforeStock = await stockOf('IDEM-D');

      const results = await Promise.all([
        placeCheckoutOrder(repo, createMockPaymentGateway(), firstPayload),
        placeCheckoutOrder(repo, createMockPaymentGateway(), secondPayload),
      ]);
      const accepted = results.filter((result) => result.ok);
      const refused = results.filter((result) => !result.ok);
      assert.equal(accepted.length, 1, 'exactly one concurrent payload may create the order');
      assert.equal(refused.length, 1, 'the competing payload must be refused');
      assert.equal(refused[0]?.ok ? '' : refused[0]?.code, 'IDEMPOTENCY_MISMATCH');
      assert.equal(await orderCount(), beforeOrders + 1, 'exactly one order exists for the key');
      const winnerQuantity = results[0]?.ok ? 1 : 2;
      assert.equal(
        await stockOf('IDEM-D'),
        beforeStock - winnerQuantity,
        'stock moved only for the winning payload',
      );
    });

    it('c. different keys create distinct orders', async () => {
      const first = await placeCheckoutOrder(
        repo,
        createMockPaymentGateway(),
        draft(variantIds['IDEM-C'] as string, 1, crypto.randomUUID()),
      );
      const second = await placeCheckoutOrder(
        repo,
        createMockPaymentGateway(),
        draft(variantIds['IDEM-C'] as string, 1, crypto.randomUUID()),
      );
      assert.ok(first.ok && second.ok);
      assert.notEqual(first.orderId, second.orderId);
      assert.equal(first.replayed, false);
      assert.equal(second.replayed, false);
      assert.equal(await stockOf('IDEM-C'), 1);
    });

    it('d. a stock refusal rolls the key back and the same key can succeed later', async () => {
      const key = crypto.randomUUID();
      const refused = await placeCheckoutOrder(
        repo,
        createMockPaymentGateway(),
        draft(variantIds['IDEM-A'] as string, 4, key),
      );
      assert.equal(refused.ok, false);
      assert.equal(refused.ok ? '' : refused.code, 'STOCK_INSUFFICIENT');
      assert.equal(await orderCountForKey(key), 0, 'the key must not survive the rollback');
      assert.equal(await stockOf('IDEM-A'), 3, 'the refused write consumed nothing');

      const accepted = await placeCheckoutOrder(
        repo,
        createMockPaymentGateway(),
        draft(variantIds['IDEM-A'] as string, 1, key),
      );
      assert.ok(accepted.ok);
      assert.equal(accepted.replayed, false);
      assert.equal(await stockOf('IDEM-A'), 2);
      assert.equal(await orderCountForKey(key), 1);
    });

    it('f. a key reused with a different payload is refused without exposing the order', async () => {
      const key = crypto.randomUUID();
      const base = draft(variantIds['IDEM-A'] as string, 1, key);
      const beforeOrders = await orderCount();
      const first = await placeCheckoutOrder(repo, createMockPaymentGateway(), base);
      assert.ok(first.ok, `the first submission must be written: ${JSON.stringify(first)}`);
      const stockAfterFirst = await stockOf('IDEM-A');
      const couponUses = (await repo.findCouponByCode(COUPON_CODE))?.usedCount;

      const mismatches: CheckoutDraft[] = [
        { ...base, lines: [{ variantId: variantIds['IDEM-A'] as string, quantity: 2 }] },
        { ...base, customer: { ...base.customer, fullName: 'نام دیگری' } },
        { ...base, couponCode: COUPON_CODE },
        { ...base, shippingMethodId: 'EXPRESS_COURIER' },
      ];

      for (const mismatch of mismatches) {
        const result = await placeCheckoutOrder(repo, createMockPaymentGateway(), mismatch);
        assert.equal(result.ok, false, 'a mismatched payload must not replay');
        assert.equal(result.ok ? '' : result.code, 'IDEMPOTENCY_MISMATCH');
        assert.equal(result.ok ? '' : result.field, 'idempotencyKey');
        assert.ok(
          !(result.ok ? '' : result.message).includes(first.orderId),
          'the mismatch refusal must not disclose the existing order',
        );
      }

      assert.equal(await orderCount(), beforeOrders + 1, 'one order, not five');
      assert.equal(await stockOf('IDEM-A'), stockAfterFirst, 'no mismatch consumed stock');
      assert.equal((await repo.findCouponByCode(COUPON_CODE))?.usedCount, couponUses);
      assert.equal(await orderCountForKey(key), 1);
    });

    it('e. a replay never invokes the payment gateway a second time', async () => {
      const authorised = createMockPaymentGateway({ outcome: 'AUTHORIZED' });
      let calls = 0;
      const gateway: PaymentGateway = {
        id: 'counting',
        authorize: async (request) => {
          calls += 1;
          return authorised.authorize(request);
        },
        verifyCallback: authorised.verifyCallback.bind(authorised),
      };

      const key = crypto.randomUUID();
      const orderDraft = draft(variantIds['IDEM-C'] as string, 1, key);
      const first = await placeCheckoutOrder(repo, gateway, orderDraft);
      assert.ok(first.ok);
      assert.equal(calls, 1);
      assert.equal(first.payment.status, 'AUTHORIZED');

      const replay = await placeCheckoutOrder(repo, gateway, orderDraft);
      assert.ok(replay.ok);
      assert.equal(calls, 1, 'replay must not call gateway.authorize');
      assert.equal(replay.replayed, true);
      assert.equal(replay.payment.status, 'AUTHORIZED');
      assert.equal(replay.payment.reference, first.payment.reference);

      const { rows } = await pool.query<{ payment_ref_id: string | null }>(
        'select payment_ref_id from commerce.orders where id = $1',
        [first.orderId],
      );
      assert.equal(rows[0]?.payment_ref_id, first.payment.reference);
    });
  },
);
