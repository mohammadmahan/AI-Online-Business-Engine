import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { eq } from 'drizzle-orm';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import { Pool } from 'pg';

import type { ProductCreatePayload } from '@/contracts/catalog';
import { createCommerceDb, type CommerceDb } from '@/db';
import { categories, coupons, customers, orderItems, orders } from '@/db/schema';
import { couponState } from '@/lib/coupon-rules';
import { inventorySummary, stockState } from '@/lib/inventory-rules';
import { computeTotals } from '@/lib/order-rules';
import { createPostgresRepository, type CommerceRepository } from '@/server/repository';
import { createCoupon, listCoupons, setCouponActive } from '@/server/services/coupons';
import { updatePrice, updateStock } from '@/server/services/inventory';
import { setTrackingCode, transitionOrder } from '@/server/services/orders';
import { createProduct } from '@/server/services/products';

/**
 * D-172 Phase 2 hardening — the LIVE PostgreSQL smoke suite.
 *
 * Closes the evidence gap §5.2 recorded: Phase 2's admin writes were verified
 * against the in-memory repository and against unit-level rules, but never
 * against a real server. Everything below is a REAL write to a REAL PostgreSQL
 * 16 instance through the REAL Postgres repository (never the test double), and
 * the assertions read the rows back from the database rather than trusting the
 * service's return value — a service that reported success without writing
 * would fail here.
 *
 * Target: the disposable harness of `docker-compose.db.yml` (PostgreSQL 16.x,
 * loopback only). This suite NEVER runs by accident:
 *
 *   - `COMMERCE_DATABASE_URL` absent  → the whole suite SKIPS with a named
 *     reason. It does not fall back to a guessed host, a default port, the
 *     canonical instance or the in-memory double (D-171 §2.2: an absent
 *     configuration is a refusal, never a pass).
 *   - present but not loopback        → SKIPS: staging/production are out of
 *     scope for this harness and the suite will not touch them.
 *
 * Re-runnability: `before()` resets the `commerce` namespace and re-applies the
 * committed migrations, so every run starts from the same empty schema and
 * re-proves that 0000 + 0001 apply cleanly. That is also why the fixtures below
 * may use fixed slugs/SKUs — there is no state to collide with.
 *
 * Scope honesty: two fixtures have no Phase 2 admin write path and are inserted
 * through the schema instead — a CATEGORY (roadmap §2 has no category CRUD;
 * `products.category_id` needs one) and an ORDER (orders arrive from the
 * storefront, Phase 3/6; §2.3 only mutates their status/tracking). Neither
 * insert bypasses a rule this phase claims to enforce.
 */

const HARNESS_URL = process.env.COMMERCE_DATABASE_URL?.trim();
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function skipReason(): string | undefined {
  if (!HARNESS_URL) {
    return 'COMMERCE_DATABASE_URL not set — live PostgreSQL smoke suite skipped (no target is guessed; fail-closed)';
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

/**
 * The COMMITTED migration folder. This file is compiled to
 * `.test-build/__tests__/live-db/*.js`, so the source of truth sits three
 * directories up — assert that rather than let drizzle report a missing
 * journal from deep inside its own loader.
 */
const MIGRATIONS_FOLDER = fileURLToPath(new URL('../../../drizzle', import.meta.url));

/** Locate the Drizzle journal wherever Drizzle placed it in this database. */
async function journalTable(pool: Pool): Promise<string | null> {
  const found = await pool.query<{ schema: string; table: string }>(
    `select schemaname as schema, tablename as table
       from pg_tables
      where tablename = '__drizzle_migrations'
      order by schemaname
      limit 1`,
  );
  const row = found.rows[0];
  return row ? `"${row.schema}"."${row.table}"` : null;
}

/**
 * Runs a statement that MUST be refused and reports the SQLSTATE + the object
 * that refused it. Unwraps the cause chain because a driver error may arrive
 * wrapped; a 5-character code is the SQLSTATE, and it is preferred over any
 * wrapper code.
 */
async function refusalOf(run: () => Promise<unknown>): Promise<{
  state: string;
  constraint?: string;
  message: string;
}> {
  try {
    await run();
  } catch (error) {
    let current: unknown = error;
    let state = 'unknown';
    let constraint: string | undefined;
    let message = error instanceof Error ? error.message : String(error);

    for (let depth = 0; depth < 6 && current !== null && typeof current === 'object'; depth += 1) {
      const candidate = current as {
        code?: unknown;
        constraint?: unknown;
        message?: unknown;
        cause?: unknown;
      };
      if (typeof candidate.code === 'string' && /^[0-9A-Z]{5}$/.test(candidate.code)) {
        state = candidate.code;
      }
      if (constraint === undefined && typeof candidate.constraint === 'string') {
        constraint = candidate.constraint;
      }
      if (typeof candidate.message === 'string' && candidate.message.length > 0) {
        message = candidate.message;
      }
      current = candidate.cause;
    }
    return { state, constraint, message };
  }
  assert.fail('the database ACCEPTED a statement that must be refused');
}

const PRODUCT_SLUG = 'manto-katan-live';
const VARIANT_SKUS = ['MK-LIVE-BLK-S', 'MK-LIVE-BLK-M', 'MK-LIVE-WHT-S', 'MK-LIVE-WHT-M'];
const COUPON_CODE = 'LIVE25';

describe('D-172 Phase 2 — live PostgreSQL smoke suite (disposable harness)', { skip: skipReason() }, () => {
  let pool!: Pool;
  let db!: CommerceDb;
  let repo!: CommerceRepository;

  let categoryId = '';
  let productId = '';
  const variantIds: Record<string, string> = {};
  let couponId = '';
  let orderId = '';
  let driftOrderId = '';

  before(async () => {
    const handle = createCommerceDb(HARNESS_URL as string);
    pool = handle.pool;
    db = handle.db;
    repo = createPostgresRepository(db);

    // ── reset, then apply the COMMITTED migrations ────────────────────────────
    // Re-runnable by construction, and the migration evidence is produced on
    // every run rather than assumed.
    await pool.query('drop schema if exists "commerce" cascade');
    const journal = await journalTable(pool);
    if (journal) {
      await pool.query(`delete from ${journal}`);
    }
    assert.ok(
      existsSync(`${MIGRATIONS_FOLDER}/meta/_journal.json`),
      `the committed migrations must be readable at ${MIGRATIONS_FOLDER}`,
    );
    await migrate(db, { migrationsFolder: MIGRATIONS_FOLDER });
  });

  after(async () => {
    await pool.end();
  });

  describe('migrations 0000 + 0001', () => {
    it('applies to PostgreSQL 16.x and records both migrations in the Drizzle journal', async () => {
      const version = await pool.query<{ v: string }>('select version() as v');
      assert.match(version.rows[0]?.v ?? '', /PostgreSQL 16\./, 'expected a PostgreSQL 16 server');

      const tables = await pool.query<{ n: string }>(
        `select table_name as n from information_schema.tables
          where table_schema = 'commerce' order by table_name`,
      );
      assert.deepEqual(
        tables.rows.map((row) => row.n),
        [
          'categories',
          'coupons',
          'customers',
          'order_items',
          'orders',
          'product_images',
          'product_variants',
          'products',
        ],
        'the seven roadmap tables (0000) plus the §2.4 coupons table (0001) must exist',
      );

      const enums = await pool.query<{ n: string }>(
        `select t.typname as n from pg_type t
           join pg_namespace ns on ns.oid = t.typnamespace
          where ns.nspname = 'commerce' and t.typtype = 'e'
          order by t.typname`,
      );
      assert.deepEqual(
        enums.rows.map((row) => row.n),
        ['discount_type', 'order_status', 'product_status'],
      );

      const journal = await journalTable(pool);
      assert.notEqual(journal, null, 'the Drizzle migration journal must exist after migrate()');
      const applied = await pool.query<{ n: number }>(`select count(*)::int as n from ${journal}`);
      assert.equal(applied.rows[0]?.n, 2, 'exactly migrations 0000 and 0001 must be recorded');
    });

    it('materialises the constraints the refusal cases rely on', async () => {
      const checks = await pool.query<{ n: string }>(
        `select conname as n from pg_constraint
           join pg_namespace ns on ns.oid = connamespace
          where ns.nspname = 'commerce' and contype = 'c' order by conname`,
      );
      const names = checks.rows.map((row) => row.n);
      for (const expected of [
        'products_base_price_non_negative',
        'product_variants_stock_non_negative',
        'product_variants_price_override_non_negative',
        'coupons_discount_value_positive',
        'coupons_percent_within_range',
        'coupons_used_count_non_negative',
        'order_items_quantity_positive',
      ]) {
        assert.ok(names.includes(expected), `CHECK ${expected} must exist`);
      }

      const indexes = await pool.query<{ n: string }>(
        `select indexname as n from pg_indexes
          where schemaname = 'commerce' and indexname = 'product_variants_matrix_unique'`,
      );
      assert.equal(indexes.rows.length, 1, 'the matrix uniqueness index must exist');
    });
  });

  describe('§2.1 — CreateCategory + CreateProduct (variant matrix + images)', () => {
    it('persists a category the catalog can reference', async () => {
      const [row] = await db
        .insert(categories)
        .values({ name: 'مانتو', slug: 'manto', description: 'دستهٔ آزمایشی' })
        .returning({ id: categories.id });
      assert.ok(row, 'the category insert must return a row');
      categoryId = row.id;
    });

    it('writes the whole product graph in one transaction — 4 variants and 2 images', async () => {
      const payload: ProductCreatePayload = {
        categoryId,
        title: 'مانتو کتان تابستانی',
        slug: PRODUCT_SLUG,
        basePrice: 2_450_000,
        discountPrice: 2_100_000,
        descriptionRaw: 'مانتو کتان با دوخت ساده؛ مناسب فصل گرم.',
        descriptionHtml: '<p>مانتو کتان با دوخت ساده؛ مناسب فصل گرم.</p>',
        fabricType: 'کتان',
        season: 'تابستان',
        careInstructions: 'شست‌وشوی ملایم با آب سرد',
        status: 'PUBLISHED',
        variants: [
          { sku: VARIANT_SKUS[0] as string, colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 4 },
          { sku: VARIANT_SKUS[1] as string, colorName: 'مشکی', colorHex: '#111111', size: 'M', stockQuantity: 0 },
          { sku: VARIANT_SKUS[2] as string, colorName: 'سفید', colorHex: '#ffffff', size: 'S', stockQuantity: 2 },
          { sku: VARIANT_SKUS[3] as string, colorName: 'سفید', colorHex: '#ffffff', size: 'M', stockQuantity: 12 },
        ],
        images: [
          {
            storagePath: 'commerce/live/main.jpg',
            publicUrl: 'https://example.invalid/live/main.jpg',
            displayOrder: 0,
            isPrimary: true,
          },
          {
            storagePath: 'commerce/live/detail.jpg',
            publicUrl: 'https://example.invalid/live/detail.jpg',
            displayOrder: 1,
          },
        ],
      };

      const created = await createProduct(repo, payload);
      assert.ok(created.ok, `createProduct refused a valid payload: ${JSON.stringify(created)}`);
      productId = created.productId;
      assert.equal(created.variantIds.length, 4);

      // Read back from PostgreSQL: the service's word is not evidence.
      const product = await pool.query<{
        base_price: string;
        status: string;
        discount_price: string | null;
      }>('select base_price, status, discount_price from commerce.products where id = $1', [
        productId,
      ]);
      assert.equal(product.rows.length, 1);
      assert.equal(Number(product.rows[0]?.base_price), 2_450_000);
      assert.equal(Number(product.rows[0]?.discount_price), 2_100_000);
      assert.equal(product.rows[0]?.status, 'PUBLISHED');

      const variants = await pool.query<{
        id: string;
        sku: string;
        size: string;
        color_hex: string;
        stock_quantity: number;
      }>(
        `select id, sku, size, color_hex, stock_quantity from commerce.product_variants
          where product_id = $1 order by sku`,
        [productId],
      );
      assert.equal(variants.rows.length, 4);
      assert.deepEqual(
        variants.rows.map((row) => row.sku),
        [...VARIANT_SKUS].sort(),
        'SKUs are stored normalised (upper-cased) exactly once each',
      );
      // The payload sent '#ffffff' in lower case, so the WHT rows prove the
      // normalisation while the BLK rows prove nothing else was rewritten.
      const EXPECTED_HEX: Record<string, string> = {
        'MK-LIVE-BLK-S': '#111111',
        'MK-LIVE-BLK-M': '#111111',
        'MK-LIVE-WHT-S': '#FFFFFF',
        'MK-LIVE-WHT-M': '#FFFFFF',
      };
      for (const row of variants.rows) {
        variantIds[row.sku] = row.id;
        assert.equal(row.color_hex, EXPECTED_HEX[row.sku], `colour hex for ${row.sku}`);
      }

      const images = await pool.query<{ n: number; primaries: number; bound: number }>(
        `select count(*)::int as n,
                count(*) filter (where is_primary)::int as primaries,
                count(*) filter (where variant_id is not null)::int as bound
           from commerce.product_images where product_id = $1`,
        [productId],
      );
      assert.equal(images.rows[0]?.n, 2);
      assert.equal(images.rows[0]?.primaries, 1, 'exactly one primary image');
      assert.equal(images.rows[0]?.bound, 0, 'Phase 2 binds images to the product, not to variants');

      // The read models the panel renders, computed by PostgreSQL.
      const listed = await repo.listProducts();
      const mine = listed.find((row) => row.slug === PRODUCT_SLUG);
      assert.ok(mine, 'listProducts must see the product');
      assert.equal(mine.variantCount, 4);
      assert.equal(mine.imageCount, 2);

      const inventory = (await repo.listInventory()).filter((row) => row.productId === productId);
      assert.equal(inventory.length, 4);
      const summary = inventorySummary(inventory);
      assert.deepEqual(
        { total: summary.total, low: summary.low, out: summary.out },
        { total: 4, low: 1, out: 1 },
        'live stock levels drive the panel badges (2 → LOW, 0 → OUT)',
      );
      const out = inventory.find((row) => row.stockQuantity === 0);
      assert.ok(out && stockState(out).code === 'OUT_OF_STOCK');
    });
  });

  describe('refusals — the fail-closed half of §2.1/§2.2', () => {
    it('refuses a duplicate (product_id, size, color_name) cell at the database', async () => {
      const refused = await refusalOf(() =>
        pool.query(
          `insert into commerce.product_variants (product_id, sku, color_name, color_hex, size, stock_quantity)
           values ($1, 'MK-LIVE-DUP-1', 'مشکی', '#111111', 'S', 1)`,
          [productId],
        ),
      );
      assert.equal(refused.state, '23505', 'unique violation expected');
      assert.equal(refused.constraint, 'product_variants_matrix_unique');
    });

    it('refuses a duplicate SKU across the catalog', async () => {
      const refused = await refusalOf(() =>
        pool.query(
          `insert into commerce.product_variants (product_id, sku, color_name, color_hex, size, stock_quantity)
           values ($1, $2, 'سبز', '#00AA00', 'L', 1)`,
          [productId, VARIANT_SKUS[0]],
        ),
      );
      assert.equal(refused.state, '23505');
      assert.equal(refused.constraint, 'product_variants_sku_unique');
    });

    it('refuses base_price < 0 in the service AND at the database', async () => {
      const payload: ProductCreatePayload = {
        categoryId,
        title: 'محصول نامعتبر',
        slug: 'invalid-price-live',
        basePrice: -1,
        descriptionRaw: 'توضیح',
        descriptionHtml: '<p>توضیح</p>',
        fabricType: 'کتان',
        season: 'تابستان',
        variants: [
          { sku: 'BAD-PRICE-1', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 1 },
        ],
      };

      const refused = await createProduct(repo, payload);
      assert.equal(refused.ok, false);
      assert.ok(!refused.ok && refused.code === 'VALIDATION_ERROR');
      assert.ok(!refused.ok && refused.issues.some((issue) => issue.field === 'basePrice'));

      const survivors = await pool.query<{ n: number }>(
        `select count(*)::int as n from commerce.products where slug = 'invalid-price-live'`,
      );
      assert.equal(survivors.rows[0]?.n, 0, 'a refused payload must write nothing at all');

      const constraint = await refusalOf(() =>
        pool.query(
          `insert into commerce.products (category_id, title, slug, base_price, description_raw, description_html, fabric_type, season)
           values ($1, 'نامعتبر', 'invalid-price-raw', -5, 't', '<p>t</p>', 'کتان', 'تابستان')`,
          [categoryId],
        ),
      );
      assert.equal(constraint.state, '23514', 'CHECK violation expected');
      assert.equal(constraint.constraint, 'products_base_price_non_negative');
    });

    it('refuses stock < 0 on creation, on update, and at the database', async () => {
      const payload: ProductCreatePayload = {
        categoryId,
        title: 'محصول نامعتبر',
        slug: 'invalid-stock-live',
        basePrice: 100_000,
        descriptionRaw: 'توضیح',
        descriptionHtml: '<p>توضیح</p>',
        fabricType: 'کتان',
        season: 'تابستان',
        variants: [
          { sku: 'BAD-STOCK-1', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: -3 },
        ],
      };
      const refused = await createProduct(repo, payload);
      assert.ok(!refused.ok && refused.code === 'VALIDATION_ERROR');
      assert.ok(
        !refused.ok && refused.issues.some((issue) => issue.field === 'variants.0.stockQuantity'),
      );

      const skuS = VARIANT_SKUS[0] as string;
      const target = variantIds[skuS] as string;
      const ok = await updateStock(repo, target, 7);
      assert.ok(ok.ok, 'a valid stock value must be accepted');
      const afterValid = await pool.query<{ stock_quantity: number }>(
        'select stock_quantity from commerce.product_variants where id = $1',
        [target],
      );
      assert.equal(afterValid.rows[0]?.stock_quantity, 7, 'the accepted value must be persisted');

      for (const bad of [-1, 1.5, 'x']) {
        const invalid = await updateStock(repo, target, bad);
        assert.ok(!invalid.ok && invalid.code === 'VALIDATION_ERROR', `stock ${bad} must be refused`);
        assert.ok(!invalid.ok && invalid.issues?.[0]?.field === 'stockQuantity');
      }
      const afterInvalid = await pool.query<{ stock_quantity: number }>(
        'select stock_quantity from commerce.product_variants where id = $1',
        [target],
      );
      assert.equal(
        afterInvalid.rows[0]?.stock_quantity,
        7,
        'a refused update must leave the stored value untouched',
      );

      const constraint = await refusalOf(() =>
        pool.query(`update commerce.product_variants set stock_quantity = -1 where id = $1`, [target]),
      );
      assert.equal(constraint.state, '23514');
      assert.equal(constraint.constraint, 'product_variants_stock_non_negative');
    });

    it('refuses a negative price override in the service AND at the database', async () => {
      const target = variantIds[VARIANT_SKUS[2] as string] as string;

      const accepted = await updatePrice(repo, target, 1_900_000);
      assert.ok(accepted.ok);
      const stored = await pool.query<{ price_override: string | null }>(
        'select price_override from commerce.product_variants where id = $1',
        [target],
      );
      assert.equal(Number(stored.rows[0]?.price_override), 1_900_000);

      const invalid = await updatePrice(repo, target, -5);
      assert.ok(!invalid.ok && invalid.code === 'VALIDATION_ERROR');
      assert.ok(!invalid.ok && invalid.issues?.[0]?.field === 'priceOverride');

      const constraint = await refusalOf(() =>
        pool.query(`update commerce.product_variants set price_override = -5 where id = $1`, [target]),
      );
      assert.equal(constraint.state, '23514');
      assert.equal(constraint.constraint, 'product_variants_price_override_non_negative');

      const cleared = await updatePrice(repo, target, null);
      assert.ok(cleared.ok, 'null clears the override (§2.2)');
      const clearedRow = await pool.query<{ price_override: string | null }>(
        'select price_override from commerce.product_variants where id = $1',
        [target],
      );
      assert.equal(clearedRow.rows[0]?.price_override, null);
    });
  });

  describe('§2.4 — coupons and their DERIVED state on live rows', () => {
    it('creates a coupon, normalising the code', async () => {
      const created = await createCoupon(repo, {
        code: 'live25',
        discountType: 'PERCENT',
        discountValue: 25,
        minSpend: 1_000_000,
        expiresAt: new Date(Date.now() + 86_400_000).toISOString(),
        usageLimit: 3,
        description: 'کد آزمایشی زنده',
      });
      assert.ok(created.ok, `createCoupon refused a valid payload: ${JSON.stringify(created)}`);
      couponId = created.coupon.id;
      assert.equal(created.coupon.code, COUPON_CODE);
      assert.equal(created.coupon.usedCount, 0);
      assert.equal(created.coupon.isActive, true);
      assert.equal(couponState(created.coupon), 'ACTIVE');
    });

    it('refuses a duplicate code in the service AND at the database', async () => {
      const refused = await createCoupon(repo, {
        code: 'LIVE25',
        discountType: 'FIXED',
        discountValue: 50_000,
      });
      assert.ok(!refused.ok && refused.code === 'CONFLICT');

      const constraint = await refusalOf(() =>
        pool.query(
          `insert into commerce.coupons (code, discount_type, discount_value)
           values ('LIVE25', 'FIXED', 1000)`,
        ),
      );
      assert.equal(constraint.state, '23505');
      assert.equal(constraint.constraint, 'coupons_code_unique');
    });

    it('refuses out-of-range discounts in the service AND at the database', async () => {
      for (const [type, value, field] of [
        ['PERCENT', 0, 'discountValue'],
        ['PERCENT', 150, 'discountValue'],
        ['FIXED', 0, 'discountValue'],
      ] as const) {
        const refused = await createCoupon(repo, { code: 'RANGE-X', discountType: type, discountValue: value });
        assert.ok(!refused.ok && refused.code === 'VALIDATION_ERROR', `${type} ${value} must be refused`);
        assert.ok(!refused.ok && refused.issues?.some((issue) => issue.field === field));
      }

      const past = await createCoupon(repo, {
        code: 'EXPIRED-X',
        discountType: 'PERCENT',
        discountValue: 10,
        expiresAt: new Date(Date.now() - 3_600_000).toISOString(),
      });
      assert.ok(!past.ok && past.code === 'VALIDATION_ERROR');
      assert.ok(!past.ok && past.issues?.some((issue) => issue.field === 'expiresAt'));

      const percent = await refusalOf(() =>
        pool.query(
          `insert into commerce.coupons (code, discount_type, discount_value)
           values ('RANGE-RAW', 'PERCENT', 150)`,
        ),
      );
      assert.equal(percent.state, '23514');
      assert.equal(percent.constraint, 'coupons_percent_within_range');

      const usedCount = await refusalOf(() =>
        pool.query(`update commerce.coupons set used_count = -1 where id = $1`, [couponId]),
      );
      assert.equal(usedCount.state, '23514');
      assert.equal(usedCount.constraint, 'coupons_used_count_non_negative');
    });

    it('derives ACTIVE → INACTIVE → ACTIVE → EXHAUSTED from the STORED row, and EXPIRED takes precedence', async () => {
      const read = async () => {
        const rows = await repo.listCoupons();
        const row = rows.find((entry) => entry.id === couponId);
        assert.ok(row, 'the coupon must be readable');
        return row;
      };

      assert.equal(couponState(await read()), 'ACTIVE');

      const off = await setCouponActive(repo, couponId, false);
      assert.ok(off.ok);
      assert.equal(couponState(await read()), 'INACTIVE');

      const on = await setCouponActive(repo, couponId, true);
      assert.ok(on.ok);
      assert.equal(couponState(await read()), 'ACTIVE');

      // Redemption is Phase 3/6 (the checkout write path); the usage counter is
      // set directly here so the DERIVED state can be observed on a live row.
      await pool.query(`update commerce.coupons set used_count = usage_limit where id = $1`, [couponId]);
      assert.equal(couponState(await read()), 'EXHAUSTED');

      await pool.query(
        `update commerce.coupons set expires_at = now() - interval '1 minute' where id = $1`,
        [couponId],
      );
      assert.equal(couponState(await read()), 'EXPIRED', 'an expired coupon is never shown as usable');

      const views = (await listCoupons(repo)).filter((view) => view.id === couponId);
      assert.equal(views[0]?.state, 'EXPIRED', 'the table view agrees with the rule');

      const forcibly = await refusalOf(() =>
        pool.query(`update commerce.coupons set is_active = 'maybe' where id = $1`, [couponId]),
      );
      assert.equal(forcibly.state, '22P02', 'a non-boolean literal is refused by PostgreSQL');
    });
  });

  describe('§2.3 — order lifecycle: legal transitions only, refusals write nothing', () => {
    const phone = '+989120000001';
    let variantId = '';

    before(async () => {
      variantId = variantIds[VARIANT_SKUS[3] as string] as string;

      const [customer] = await db
        .insert(customers)
        .values({
          phoneNumber: phone,
          fullName: 'مشتری آزمایشی',
          address: 'تهران، خیابان آزمایشی',
          postalCode: '1234567890',
        })
        .returning({ id: customers.id });

      const [order] = await db
        .insert(orders)
        .values([
          {
            customerId: customer?.id as string,
            totalAmount: 4_800_000,
            discountAmount: 150_000,
            shippingAmount: 50_000,
            status: 'PENDING',
            shippingAddress: 'تهران، خیابان آزمایشی',
          },
        ])
        .returning({ id: orders.id });
      orderId = order?.id as string;

      const [drift] = await db
        .insert(orders)
        .values({
          customerId: customer?.id as string,
          totalAmount: 999,
          shippingAddress: 'تهران، خیابان آزمایشی',
        })
        .returning({ id: orders.id });
      driftOrderId = drift?.id as string;

      await db.insert(orderItems).values({
        orderId,
        variantId,
        quantity: 2,
        unitPrice: 2_450_000,
      });
    });

    const statusOf = async (id: string) => {
      const rows = await pool.query<{ status: string }>(
        'select status from commerce.orders where id = $1',
        [id],
      );
      return rows.rows[0]?.status;
    };

    it('refuses an illegal transition (PENDING → SHIPPED) and writes nothing', async () => {
      const refused = await transitionOrder(repo, orderId, 'SHIPPED');
      assert.ok(!refused.ok && refused.code === 'ILLEGAL_TRANSITION');
      assert.equal(await statusOf(orderId), 'PENDING', 'a refused transition must not move the row');
    });

    it('refuses a self-transition and an unknown order', async () => {
      const same = await transitionOrder(repo, orderId, 'PENDING');
      assert.ok(!same.ok && same.code === 'ILLEGAL_TRANSITION');

      const missing = await transitionOrder(repo, '00000000-0000-0000-0000-000000000000', 'PAID');
      assert.ok(!missing.ok && missing.code === 'NOT_FOUND');
    });

    it('refuses tracking in a state that cannot carry it, then accepts it once PROCESSING', async () => {
      const early = await setTrackingCode(repo, orderId, 'IR1234567890');
      assert.ok(!early.ok && early.code === 'ILLEGAL_STATE');

      const paid = await transitionOrder(repo, orderId, 'PAID');
      assert.ok(paid.ok, `PENDING → PAID must be allowed: ${JSON.stringify(paid)}`);
      assert.equal(await statusOf(orderId), 'PAID');

      const stillEarly = await setTrackingCode(repo, orderId, 'IR1234567890');
      assert.ok(!stillEarly.ok && stillEarly.code === 'ILLEGAL_STATE');

      const processing = await transitionOrder(repo, orderId, 'PROCESSING');
      assert.ok(processing.ok);
      const bad = await setTrackingCode(repo, orderId, 'ab');
      assert.ok(!bad.ok && bad.code === 'VALIDATION_ERROR');

      const tracked = await setTrackingCode(repo, orderId, 'IR1234567890');
      assert.ok(tracked.ok);
      const stored = await pool.query<{ tracking_code: string | null }>(
        'select tracking_code from commerce.orders where id = $1',
        [orderId],
      );
      assert.equal(stored.rows[0]?.tracking_code, 'IR1234567890');
    });

    it('treats SHIPPED as terminal and leaves the packing-slip arithmetic reconcilable', async () => {
      const shipped = await transitionOrder(repo, orderId, 'SHIPPED');
      assert.ok(shipped.ok);
      assert.equal(await statusOf(orderId), 'SHIPPED');

      const backwards = await transitionOrder(repo, orderId, 'CANCELLED');
      assert.ok(!backwards.ok && backwards.code === 'ILLEGAL_TRANSITION');
      assert.equal(await statusOf(orderId), 'SHIPPED');

      const detail = await repo.getOrderDetail(orderId);
      assert.ok(detail, 'the order must be readable');
      assert.equal(detail.items.length, 1);
      const totals = computeTotals(detail);
      assert.equal(totals.payable, 4_800_000);
      assert.equal(totals.consistent, true, 'stored total must equal the recomputed lines');

      const drifted = await repo.getOrderDetail(driftOrderId);
      assert.ok(drifted);
      assert.equal(computeTotals(drifted).consistent, false, 'a drifted total is reported, not hidden');
    });

    it('allows PENDING → CANCELLED and then refuses everything from a terminal state', async () => {
      const cancelled = await transitionOrder(repo, driftOrderId, 'CANCELLED');
      assert.ok(cancelled.ok, `PENDING → CANCELLED must be allowed: ${JSON.stringify(cancelled)}`);
      assert.equal(await statusOf(driftOrderId), 'CANCELLED');

      const revive = await transitionOrder(repo, driftOrderId, 'PAID');
      assert.ok(!revive.ok && revive.code === 'ILLEGAL_TRANSITION');
      assert.equal(await statusOf(driftOrderId), 'CANCELLED');
    });

    it('refuses a status the enum does not define', async () => {
      const refused = await refusalOf(() =>
        pool.query(`update commerce.orders set status = 'REFUNDED' where id = $1`, [orderId]),
      );
      assert.equal(refused.state, '22P02', 'PostgreSQL refuses an unknown enum label');
      assert.equal(await statusOf(orderId), 'SHIPPED');
    });

    it('refuses an order line with quantity 0', async () => {
      const refused = await refusalOf(() =>
        pool.query(
          `insert into commerce.order_items (order_id, variant_id, quantity, unit_price)
           values ($1, $2, 0, 1000)`,
          [orderId, variantId],
        ),
      );
      assert.equal(refused.state, '23514');
      assert.equal(refused.constraint, 'order_items_quantity_positive');
    });

    it('reports line counts in the order list read model', async () => {
      // Regression guard: the raw-`sql` form of this aggregate rendered
      // `where "order_id" = "id"` — both names bound to `order_items` — and
      // every order reported 0 lines. Measured live, fixed, pinned here.
      const listed = await repo.listOrders();
      const mine = listed.find((row) => row.id === orderId);
      assert.ok(mine, 'the order must appear in the list read model');
      assert.equal(mine.itemCount, 2, 'two units on one line');

      const drift = listed.find((row) => row.id === driftOrderId);
      assert.ok(drift);
      assert.equal(drift.itemCount, 0, 'an order without lines reports 0, not NULL');
    });

    it('holds the catalog/coupon/order state in one readable snapshot', async () => {
      const tables = await pool.query<{ table_name: string; n: number }>(
        `select 'products' as table_name, count(*)::int as n from commerce.products
          union all select 'product_variants', count(*)::int from commerce.product_variants
          union all select 'product_images', count(*)::int from commerce.product_images
          union all select 'coupons', count(*)::int from commerce.coupons
          union all select 'orders', count(*)::int from commerce.orders
          union all select 'order_items', count(*)::int from commerce.order_items
          order by 1`,
      );
      assert.deepEqual(
        Object.fromEntries(tables.rows.map((row) => [row.table_name, row.n])),
        {
          coupons: 1,
          order_items: 1,
          orders: 2,
          product_images: 2,
          product_variants: 4,
          products: 1,
        },
        'every refusal above left the accepted state exactly as written',
      );
      assert.equal((await db.select().from(coupons).where(eq(coupons.id, couponId))).length, 1);
    });
  });
});
