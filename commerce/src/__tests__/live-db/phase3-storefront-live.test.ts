import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import { Pool } from 'pg';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CatalogFilters, CheckoutDraft } from '@/contracts/storefront';
import { EMPTY_CATALOG_FILTERS } from '@/contracts/storefront';
import { createCommerceDb, type CommerceDb } from '@/db';
import { categories } from '@/db/schema';
import { applyFilters, deriveFacets } from '@/lib/catalog-filters';
import { MAX_LINE_QUANTITY, computeCheckoutTotals } from '@/lib/checkout-rules';
import { LOW_STOCK_THRESHOLD } from '@/lib/inventory-rules';
import { DEFAULT_SHIPPING_METHOD_ID, shippingAmountFor } from '@/lib/shipping';
import { createMockPaymentGateway, mockPaymentGateway } from '@/server/payments/gateway';
import { createPostgresRepository, type CommerceRepository } from '@/server/repository';
import { checkAvailability, placeCheckoutOrder } from '@/server/services/checkout';
import { createCoupon } from '@/server/services/coupons';
import { updateStock } from '@/server/services/inventory';
import { transitionOrder } from '@/server/services/orders';
import { createProduct } from '@/server/services/products';
import {
  getPublishedProduct,
  listBestSellers,
  listPublishedProducts,
  listStorefrontCategories,
} from '@/server/services/storefront';

/**
 * D-172 Phase 3 — the LIVE customer-storefront suite (disposable harness).
 *
 * Phase 3's storefront was verified against the in-memory double and the pure
 * rules, which left one evidence gap: the whole customer funnel — catalog read,
 * PDP levels, the checkout write and the stock it consumes — had never been
 * exercised against a REAL PostgreSQL server. Everything below drives the real
 * repository and asserts against rows read BACK from the database, because a
 * service that reports success without writing would fail here.
 *
 * Target: the disposable harness of `docker-compose.db.yml` (PostgreSQL 16.x,
 * loopback only), same gates as `phase2-live.test.ts`:
 *
 *   - `COMMERCE_DATABASE_URL` absent  → the whole suite SKIPS with a named
 *     reason. It never guesses a host, a port, the canonical instance or the
 *     in-memory double (D-171 §2.2: an absent configuration is a refusal,
 *     never a pass).
 *   - present but not loopback        → SKIPS: staging and production are out
 *     of scope for this harness and the suite will not touch them.
 *
 * Re-runnability: `before()` drops the `commerce` schema and re-applies the
 * COMMITTED migrations, so every run starts from the same empty schema, the
 * migration evidence is produced on every run rather than assumed, and the fixed
 * slugs/SKUs below have no state to collide with.
 *
 * THIS FILE AND `phase2-live.test.ts` SHARE ONE DATABASE and both reset it, so
 * `npm run smoke:db` runs the live directory with `--test-concurrency=1`. Without
 * that flag node:test runs the two files in parallel processes and the second
 * `drop schema` would truncate the first suite's fixtures mid-run.
 *
 * Scope honesty: two fixture states have no write path in the product and are
 * produced another way — a CATEGORY (§1.1 has no CRUD UI; `products.category_id`
 * needs one) and `is_active = false` on a variant (the panel edits stock and
 * price, but has no activate/deactivate control). Stock changes go through the
 * REAL §2.2 service (`updateStock`), and nothing below reaches around a rule the
 * storefront or the database claims to enforce.
 */

const HARNESS_URL = process.env.COMMERCE_DATABASE_URL?.trim();
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function skipReason(): string | undefined {
  if (!HARNESS_URL) {
    return 'COMMERCE_DATABASE_URL not set — live PostgreSQL storefront suite skipped (no target is guessed; fail-closed)';
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

const MANTO_SLUG = 'manto-katan-p3';
const DRAFT_SLUG = 'manto-draft-p3';
const SHOMIZ_SLUG = 'shomiz-p3';
const COUPON_CODE = 'LIVE3-25';

const BASE_PRICE = 2_450_000;
const DISCOUNT_PRICE = 2_100_000;
const OVERRIDE_PRICE = 1_900_000;
const SHOMIZ_PRICE = 890_000;

/** SKU → fixture stock, in the order the variants are submitted. */
const FIXTURE_STOCK: Record<string, number> = {
  'P3-BLK-S': 4,
  'P3-BLK-M': 0,
  'P3-WHT-S': 2,
  'P3-WHT-M': 12,
  'P3-GRN-L': 5,
  'P3-SHZ-38': 3,
};

const SKU_ORDER = Object.keys(FIXTURE_STOCK);

/** The shipping amount the order must carry, taken from the shared table. */
const SHIPPING_AMOUNT = shippingAmountFor(DEFAULT_SHIPPING_METHOD_ID);

describe(
  'D-172 Phase 3 — live storefront suite: catalog, PDP, checkout and the stock it consumes',
  { skip: skipReason() },
  () => {
    let pool!: Pool;
    let db!: CommerceDb;
    let repo!: CommerceRepository;

    let mantoCategoryId = '';
    let shomizCategoryId = '';
    const variantIds: Record<string, string> = {};

    /** First successful storefront order (with the coupon), cancelled last. */
    let couponOrderId = '';
    /** Second order: the last pieces of one variant, then cancelled. */
    let lastPieceOrderId = '';

    async function stockOf(variantId: string): Promise<number> {
      const { rows } = await pool.query<{ stock_quantity: number }>(
        'select stock_quantity from commerce.product_variants where id = $1',
        [variantId],
      );
      assert.equal(rows.length, 1, 'the variant row must exist');
      return rows[0]?.stock_quantity as number;
    }

    async function orderRows(): Promise<number> {
      const { rows } = await pool.query<{ n: number }>(
        'select count(*)::int as n from commerce.orders',
      );
      return rows[0]?.n as number;
    }

    async function stockOfSku(sku: string): Promise<number> {
      return stockOf(variantIds[sku] as string);
    }

    function draft(overrides: Partial<CheckoutDraft> = {}): CheckoutDraft {
      return {
        // Persian digits on purpose: the service normalises them before storing,
        // and the assertions below read the STORED value back.
        customer: {
          fullName: 'زهرا محمدی',
          phoneNumber: '۰۹۱۲۳۴۵۶۷۸۹',
          address: 'تهران، خیابان ولیعصر، پلاک ۱۲، واحد ۳',
          postalCode: '۱۹۹۹۹۹۹۹۹۹',
        },
        couponCode: null,
        shippingMethodId: DEFAULT_SHIPPING_METHOD_ID,
        lines: [{ variantId: variantIds['P3-BLK-S'] as string, quantity: 1 }],
        ...overrides,
      };
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

      // ── §1.1 categories (no CRUD path exists) ────────────────────────────────
      const inserted = await db
        .insert(categories)
        .values([
          { name: 'مانتو', slug: 'manto-live-p3', description: 'دستهٔ زندهٔ مانتو' },
          { name: 'شومیز', slug: 'shomiz-live-p3', description: 'دستهٔ زندهٔ شومیز' },
        ])
        .returning({ id: categories.id, slug: categories.slug });
      mantoCategoryId = inserted.find((row) => row.slug === 'manto-live-p3')?.id as string;
      shomizCategoryId = inserted.find((row) => row.slug === 'shomiz-live-p3')?.id as string;

      // ── §2.1 products, through the real ingestion service ───────────────────
      const manto: ProductCreatePayload = {
        categoryId: mantoCategoryId,
        title: 'مانتو کتان تابستانی زنده',
        slug: MANTO_SLUG,
        basePrice: BASE_PRICE,
        discountPrice: DISCOUNT_PRICE,
        descriptionRaw: 'مانتو کتان با دوخت ساده.\n\nمناسب فصل گرم.',
        descriptionHtml: '<p>مانتو کتان با دوخت ساده.</p>',
        fabricType: 'کتان',
        season: 'تابستان',
        careInstructions: 'شست‌وشوی ملایم با آب سرد',
        status: 'PUBLISHED',
        variants: [
          { sku: 'P3-BLK-S', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 4 },
          { sku: 'P3-BLK-M', colorName: 'مشکی', colorHex: '#111111', size: 'M', stockQuantity: 0 },
          { sku: 'P3-WHT-S', colorName: 'سفید', colorHex: '#ffffff', size: 'S', stockQuantity: 2 },
          {
            sku: 'P3-WHT-M',
            colorName: 'سفید',
            colorHex: '#ffffff',
            size: 'M',
            stockQuantity: 12,
            // An override must win over the product's discount price (D-024).
            priceOverride: OVERRIDE_PRICE,
          },
          { sku: 'P3-GRN-L', colorName: 'سبز', colorHex: '#00AA00', size: 'L', stockQuantity: 5 },
        ],
        images: [
          {
            storagePath: 'commerce/live-p3/main.jpg',
            publicUrl: 'https://example.invalid/live-p3/main.jpg',
            displayOrder: 0,
            isPrimary: true,
          },
          {
            storagePath: 'commerce/live-p3/detail.jpg',
            publicUrl: 'https://example.invalid/live-p3/detail.jpg',
            displayOrder: 1,
          },
        ],
      };
      const createdManto = await createProduct(repo, manto);
      assert.ok(createdManto.ok, `createProduct refused the manto fixture: ${JSON.stringify(createdManto)}`);
      SKU_ORDER.slice(0, 5).forEach((sku, index) => {
        const id = createdManto.variantIds[index];
        assert.ok(id, `the fixture variant ${sku} must have been created`);
        variantIds[sku] = id;
      });

      const shomiz: ProductCreatePayload = {
        categoryId: shomizCategoryId,
        title: 'شومیز آبی زنده',
        slug: SHOMIZ_SLUG,
        basePrice: SHOMIZ_PRICE,
        discountPrice: null,
        descriptionRaw: 'شومیز ساده.',
        descriptionHtml: '<p>شومیز ساده.</p>',
        fabricType: 'کرپ',
        season: 'بهار',
        status: 'PUBLISHED',
        variants: [
          { sku: 'P3-SHZ-38', colorName: 'آبی', colorHex: '#0000ff', size: '38', stockQuantity: 3 },
        ],
        images: [],
      };
      const createdShomiz = await createProduct(repo, shomiz);
      assert.ok(createdShomiz.ok, 'createProduct refused the shomiz fixture');
      variantIds['P3-SHZ-38'] = createdShomiz.variantIds[0] as string;

      // A DRAFT product: it must be invisible to every storefront read path.
      const draftProduct: ProductCreatePayload = {
        ...manto,
        title: 'مانتو منتشرنشده',
        slug: DRAFT_SLUG,
        status: 'DRAFT',
        variants: [
          { sku: 'P3-DRAFT-1', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 9 },
        ],
        images: [],
      };
      const createdDraft = await createProduct(repo, draftProduct);
      assert.ok(createdDraft.ok, 'createProduct refused the draft fixture');
      variantIds['P3-DRAFT-1'] = createdDraft.variantIds[0] as string;

      // ── §2.4 a real coupon, through the real service ────────────────────────
      const coupon = await createCoupon(repo, {
        code: COUPON_CODE,
        discountType: 'PERCENT',
        discountValue: 25,
        minSpend: 0,
        usageLimit: 3,
        description: 'کد زندهٔ مرحلهٔ ۳',
      });
      assert.ok(coupon.ok, 'createCoupon refused the fixture coupon');

      // ── the two states no write path can produce ────────────────────────────
      // (a) a variant the merchant has deactivated: it must disappear from the
      //     storefront's sizes, colours and PDP matrix.
      await pool.query(
        'update commerce.product_variants set is_active = false where id = $1',
        [variantIds['P3-GRN-L']],
      );
    });

    after(async () => {
      await pool.end();
    });

    describe('§3.1 categories & rails', () => {
      it('counts only PUBLISHED products per category', async () => {
        const cats = await listStorefrontCategories(repo);
        const manto = cats.find((row) => row.name === 'مانتو');
        const shomiz = cats.find((row) => row.name === 'شومیز');
        assert.ok(manto && shomiz, 'both fixture categories must be listed');
        assert.equal(manto.productCount, 1, 'the DRAFT product is never counted');
        assert.equal(shomiz.productCount, 1);
      });

      it('renders rails from real reads only — the draft product is nowhere', async () => {
        const cards = await listPublishedProducts(repo);
        assert.deepEqual(
          cards.map((card) => card.slug).sort(),
          [MANTO_SLUG, SHOMIZ_SLUG].sort(),
          'exactly the two published products',
        );

        const discounted = cards.filter((card) => card.hasDiscount);
        assert.deepEqual(discounted.map((card) => card.slug), [MANTO_SLUG]);

        const draft = await getPublishedProduct(repo, DRAFT_SLUG);
        assert.equal(draft, null, 'a DRAFT product must not be readable by slug either');
        const unknown = await getPublishedProduct(repo, 'no-such-product-p3');
        assert.equal(unknown, null);
      });
    });

    describe('§3.2 catalog filtering over the live read model', () => {
      it('derives facets from the published, ACTIVE variants only', async () => {
        const facets = deriveFacets(await listPublishedProducts(repo));
        assert.deepEqual(
          facets.sizes,
          ['S', 'M', '38'],
          'lettered sizes first, then numeric; the deactivated L is absent',
        );
        assert.deepEqual(
          facets.colors.map((color) => color.name).sort(),
          ['آبی', 'سفید', 'مشکی'].sort(),
        );
        assert.equal(facets.minPrice, SHOMIZ_PRICE);
        assert.equal(facets.maxPrice, DISCOUNT_PRICE);
      });

      it('filters by category, size, colour, price range and availability', async () => {
        const cards = await listPublishedProducts(repo);
        const withFilters = (patch: Partial<CatalogFilters>) => {
          const found = applyFilters(cards, { ...EMPTY_CATALOG_FILTERS, ...patch });
          return found.map((card) => card.slug).sort();
        };

        assert.deepEqual(withFilters({ category: 'مانتو' }), [MANTO_SLUG]);
        assert.deepEqual(withFilters({ category: 'شومیز' }), [SHOMIZ_SLUG]);
        assert.deepEqual(withFilters({ sizes: ['M'] }), [MANTO_SLUG], 'only the manto has M');
        assert.deepEqual(withFilters({ sizes: ['38'] }), [SHOMIZ_SLUG]);
        assert.deepEqual(withFilters({ colors: ['آبی'] }), [SHOMIZ_SLUG]);
        assert.deepEqual(
          withFilters({ maxPrice: SHOMIZ_PRICE }),
          [SHOMIZ_SLUG],
          'a ceiling at the cheaper product excludes the other',
        );
        assert.deepEqual(
          withFilters({ minPrice: DISCOUNT_PRICE }),
          [MANTO_SLUG],
          'a floor above the cheaper product excludes it',
        );
        assert.deepEqual(withFilters({ query: 'شومیز' }), [SHOMIZ_SLUG]);
        assert.deepEqual(
          withFilters({ query: 'شومیز', sizes: ['M'] }),
          [],
          'an impossible combination yields nothing rather than everything',
        );
        assert.deepEqual(
          applyFilters(cards, { ...EMPTY_CATALOG_FILTERS, sort: 'price-asc' }).map((c) => c.slug),
          [SHOMIZ_SLUG, MANTO_SLUG],
        );
      });

      it('answers availability from real stock, and hides nothing it cannot sell', async () => {
        const before = await listPublishedProducts(repo);
        // The read path orders newest-first, so compare by slug rather than by
        // position — the assertion is about availability, not ordering.
        assert.deepEqual(
          before
            .map((card) => [card.slug, card.availability] as const)
            .sort((left, right) => left[0].localeCompare(right[0])),
          [
            [MANTO_SLUG, 'IN'],
            [SHOMIZ_SLUG, 'IN'],
          ],
          'both products have at least one stocked active variant',
        );

        // The merchant empties the shomiz through the REAL §2.2 service.
        const emptied = await updateStock(repo, variantIds['P3-SHZ-38'] as string, 0);
        assert.ok(emptied.ok, 'updateStock must accept zero ("sold out" is a state)');

        const after = await listPublishedProducts(repo);
        const shomiz = after.find((card) => card.slug === SHOMIZ_SLUG);
        assert.equal(shomiz?.availability, 'OUT');
        assert.deepEqual(
          shomiz?.sizes,
          ['38'],
          'the size facet survives a sold-out product: the piece still exists',
        );
        assert.deepEqual(
          applyFilters(after, { ...EMPTY_CATALOG_FILTERS, onlyAvailable: true }).map((c) => c.slug),
          [MANTO_SLUG],
          '"only available" hides the sold-out product',
        );

        const pdp = await getPublishedProduct(repo, SHOMIZ_SLUG);
        assert.deepEqual(pdp?.variants.map((variant) => variant.level), ['OUT']);
      });
    });

    describe('§3.3 product detail — levels, prices and what must not leak', () => {
      it('derives IN / LOW / OUT from the stored quantities', async () => {
        const product = await getPublishedProduct(repo, MANTO_SLUG);
        assert.ok(product, 'the published product must be readable by slug');

        const levelOf = (sku: string) =>
          product.variants.find((variant) => variant.variantId === variantIds[sku])?.level;
        assert.equal(levelOf('P3-BLK-S'), 'IN', '4 units is above the threshold');
        assert.equal(
          levelOf('P3-WHT-S'),
          'LOW',
          `2 units is at/below the low-stock threshold ${LOW_STOCK_THRESHOLD}`,
        );
        assert.equal(levelOf('P3-WHT-M'), 'IN', 'the 12-unit variant is IN');
        assert.equal(levelOf('P3-BLK-M'), 'OUT', 'the zero-stock variant is OUT (a state, not an error)');
        assert.equal(product.variants.length, 4, 'every ACTIVE variant is offered, stocked or not');
      });

      it('excludes a deactivated variant from the matrix and the card facets', async () => {
        const product = await getPublishedProduct(repo, MANTO_SLUG);
        assert.ok(product);
        assert.ok(
          !product.variants.some((variant) => variant.variantId === variantIds['P3-GRN-L']),
          'an inactive variant is not offered',
        );
        assert.ok(!product.sizes.includes('L'), 'nor does its size appear as a filter');
        assert.ok(!product.colors.some((color) => color.name === 'سبز'));
      });

      it('resolves the effective price server-side (override > discount > base)', async () => {
        const product = await getPublishedProduct(repo, MANTO_SLUG);
        assert.ok(product);
        const override = product.variants.find((v) => v.variantId === variantIds['P3-WHT-M']);
        const inherited = product.variants.find((v) => v.variantId === variantIds['P3-BLK-S']);
        assert.equal(override?.effectivePrice, OVERRIDE_PRICE);
        assert.equal(inherited?.effectivePrice, DISCOUNT_PRICE, 'the product discount applies');
        assert.equal(product.effectivePrice, DISCOUNT_PRICE, 'the card prices the product, not a variant');
      });

      it('never exposes a raw stock quantity to the customer surface', async () => {
        const product = await getPublishedProduct(repo, MANTO_SLUG);
        assert.ok(product);
        assert.ok(product.variants.length > 0);
        for (const variant of product.variants) {
          assert.ok(
            !('stockQuantity' in variant),
            'the storefront read model must carry a LEVEL, never the number',
          );
        }
      });

      it('keeps the gallery in display order with the primary first', async () => {
        const product = await getPublishedProduct(repo, MANTO_SLUG);
        assert.ok(product);
        assert.deepEqual(
          product.images.map((image) => image.url),
          [
            'https://example.invalid/live-p3/main.jpg',
            'https://example.invalid/live-p3/detail.jpg',
          ],
        );
        assert.equal(product.primaryImageUrl, 'https://example.invalid/live-p3/main.jpg');
        assert.deepEqual(
          product.images.map((image) => image.variantId),
          [null, null],
          'Phase 2 binds photos to the product, not to a colour (G-5)',
        );
      });
    });

    describe('§3.3/§3.4 pre-flight — the optimistic check, and the stock it consumes', () => {
      it('reports a level per requested line without becoming authoritative', async () => {
        const checked = await checkAvailability(repo, [
          { variantId: variantIds['P3-BLK-S'] as string, quantity: 2 },
          { variantId: variantIds['P3-BLK-M'] as string, quantity: 1 },
          { variantId: '00000000-0000-0000-0000-000000000000', quantity: 1 },
        ]);
        assert.ok(checked.ok, 'the pre-flight must answer, not refuse');

        const [stocked, soldOut, unknown] = checked.lines;
        assert.equal(stocked?.available, true);
        assert.equal(stocked?.level, 'IN');
        assert.equal(stocked?.effectivePrice, DISCOUNT_PRICE);
        assert.equal(soldOut?.available, false, 'zero stock cannot satisfy a quantity');
        assert.equal(soldOut?.level, 'OUT');
        assert.equal(unknown?.effectivePrice, null, 'no price is invented for a missing variant');
        assert.equal(unknown?.productTitle, '');
      });

      it('does not write: the check leaves stock and orders untouched', async () => {
        assert.equal(await stockOfSku('P3-BLK-S'), 4);
        assert.equal(await orderRows(), 0);
      });
    });

    describe('§3.4 checkout — the real order, its totals and its stock', () => {
      it('persists a PENDING order with items, the coupon applied and the stock consumed', async () => {
        const before = await stockOfSku('P3-BLK-S');
        const placed = await placeCheckoutOrder(
          repo,
          mockPaymentGateway,
          draft({
            couponCode: COUPON_CODE,
            lines: [{ variantId: variantIds['P3-BLK-S'] as string, quantity: 2 }],
          }),
        );

        assert.ok(placed.ok, `the checkout was refused: ${JSON.stringify(placed)}`);
        couponOrderId = placed.orderId;
        assert.equal(placed.status, 'PENDING');

        // Totals recomputed from the live unit price, not hard-coded.
        const subtotal = DISCOUNT_PRICE * 2;
        const expected = computeCheckoutTotals({
          subtotal,
          discount: Math.floor(subtotal / 4),
          shipping: SHIPPING_AMOUNT as number,
        });
        assert.deepEqual(placed.totals, expected);
        assert.equal(placed.couponApplied, true);

        // The ROOT: the order row as PostgreSQL holds it.
        const order = await pool.query<{
          status: string;
          total_amount: string;
          discount_amount: string;
          shipping_amount: string;
          payment_ref_id: string | null;
          shipping_address: string;
        }>(
          `select status, total_amount, discount_amount, shipping_amount, payment_ref_id, shipping_address
             from commerce.orders where id = $1`,
          [placed.orderId],
        );
        assert.equal(order.rows.length, 1);
        const row = order.rows[0];
        assert.equal(row?.status, 'PENDING');
        assert.equal(Number(row?.total_amount), expected.total);
        assert.equal(Number(row?.discount_amount), expected.discount);
        assert.equal(Number(row?.shipping_amount), expected.shipping);
        assert.equal(row?.payment_ref_id, null, 'nothing was charged, so nothing is recorded');
        assert.equal(row?.shipping_address, 'تهران، خیابان ولیعصر، پلاک ۱۲، واحد ۳');

        const items = await pool.query<{ quantity: number; unit_price: string }>(
          'select quantity, unit_price from commerce.order_items where order_id = $1',
          [placed.orderId],
        );
        assert.equal(items.rows.length, 1);
        assert.equal(items.rows[0]?.quantity, 2);
        assert.equal(
          Number(items.rows[0]?.unit_price),
          DISCOUNT_PRICE,
          'the order line carries the server-resolved price',
        );

        // Persian digits in, ASCII in the database (the customer identity).
        const customer = await pool.query<{ phone_number: string; postal_code: string }>(
          'select phone_number, postal_code from commerce.customers',
        );
        assert.equal(customer.rows.length, 1);
        assert.equal(customer.rows[0]?.phone_number, '09123456789');
        assert.equal(customer.rows[0]?.postal_code, '1999999999');

        // The coupon counter moved exactly once, atomically with the order.
        const coupon = await pool.query<{ used_count: number }>(
          'select used_count from commerce.coupons where code = $1',
          [COUPON_CODE],
        );
        assert.equal(coupon.rows[0]?.used_count, 1);

        // §3.4 payment: the shipped adapter can only refuse, so the customer is
        // told nothing was charged and the order does not move (AC-8).
        assert.equal(placed.payment.status, 'UNAVAILABLE');
        assert.equal(placed.payment.code, 'PROVIDER_NOT_SELECTED');
        assert.equal(placed.payment.reference, null);

        // The stock the order consumed, read from the row.
        assert.equal(await stockOfSku('P3-BLK-S'), before - 2);
      });

      it('refuses the oversell: the last pieces sell once, then the line is refused', async () => {
        const remaining = await stockOfSku('P3-BLK-S');
        assert.equal(remaining, 2);

        const last = await placeCheckoutOrder(
          repo,
          mockPaymentGateway,
          draft({ lines: [{ variantId: variantIds['P3-BLK-S'] as string, quantity: remaining }] }),
        );
        assert.ok(last.ok, 'the remaining pieces are still sellable');
        lastPieceOrderId = last.orderId;
        assert.equal(await stockOfSku('P3-BLK-S'), 0);

        const ordersBefore = await orderRows();
        const refused = await placeCheckoutOrder(
          repo,
          mockPaymentGateway,
          draft({ lines: [{ variantId: variantIds['P3-BLK-S'] as string, quantity: 1 }] }),
        );
        assert.ok(!refused.ok);
        assert.equal(refused.code, 'STOCK_INSUFFICIENT');
        assert.equal(await orderRows(), ordersBefore, 'a refused checkout writes no order row');
        assert.equal(await stockOfSku('P3-BLK-S'), 0, 'and never drives stock negative');

        // The same conditional statement the write path uses, run by hand at the
        // database: with nothing on the shelf it updates ZERO rows rather than
        // failing the CHECK, which is what makes check-and-consume one atomic step.
        const decremented = await pool.query(
          `update commerce.product_variants
              set stock_quantity = stock_quantity - 1
            where id = $1 and stock_quantity >= 1`,
          [variantIds['P3-BLK-S']],
        );
        assert.equal(decremented.rowCount, 0, 'the WHERE is the oversell guard');
      });

      it('serialises two simultaneous buyers of the LAST piece: exactly one wins', async () => {
        // The property the double cannot demonstrate (it has no row locks), and
        // the reason the reservation lives inside the transaction: both requests
        // lock the same variant row, so the loser re-reads the committed stock
        // and is refused instead of overselling.
        const contested = variantIds['P3-WHT-M'] as string;
        const set = await updateStock(repo, contested, 1);
        assert.ok(set.ok, 'the merchant can leave exactly one piece on the shelf');

        const ordersBefore = await orderRows();
        const [left, right] = await Promise.all([
          placeCheckoutOrder(
            repo,
            mockPaymentGateway,
            draft({ lines: [{ variantId: contested, quantity: 1 }] }),
          ),
          placeCheckoutOrder(
            repo,
            mockPaymentGateway,
            draft({ lines: [{ variantId: contested, quantity: 1 }] }),
          ),
        ]);

        const outcomes = [left, right];
        assert.equal(
          outcomes.filter((outcome) => outcome.ok).length,
          1,
          'exactly one concurrent order may take the last piece',
        );
        const refused = outcomes.filter((outcome) => !outcome.ok);
        assert.equal(refused.length, 1);
        assert.equal(refused[0]?.code, 'STOCK_INSUFFICIENT');
        assert.equal(await stockOf(contested), 0, 'the piece was sold once, not twice');
        assert.equal(await orderRows(), ordersBefore + 1, 'and exactly one order was written');

        // The winner is cancelled here so the rails assertions below start from
        // a catalog with no live orders — and it proves the restock holds for a
        // reservation taken under contention too.
        const winner = outcomes.find((outcome) => outcome.ok);
        assert.ok(winner, 'the winning order must be identifiable');
        assert.deepEqual(await transitionOrder(repo, winner.orderId, 'CANCELLED'), { ok: true });
        assert.equal(await stockOf(contested), 1, 'cancelling the winner puts the piece back');
      });

      it('returns the stock when an order is cancelled, exactly once', async () => {
        const cancelled = await transitionOrder(repo, lastPieceOrderId, 'CANCELLED');
        assert.deepEqual(cancelled, { ok: true });

        const status = await pool.query<{ status: string }>(
          'select status from commerce.orders where id = $1',
          [lastPieceOrderId],
        );
        assert.equal(status.rows[0]?.status, 'CANCELLED');
        assert.equal(await stockOfSku('P3-BLK-S'), 2, 'the cancelled order restocked its line');

        const again = await transitionOrder(repo, lastPieceOrderId, 'CANCELLED');
        assert.ok(!again.ok, 'CANCELLED is terminal, so it cannot be cancelled twice');
        assert.equal(await stockOfSku('P3-BLK-S'), 2, 'a refused second cancellation restocks nothing');

        // The coupon order's stock comes back too — the reservation round-trips.
        const cancelledCoupon = await transitionOrder(repo, couponOrderId, 'CANCELLED');
        assert.deepEqual(cancelledCoupon, { ok: true });
        assert.equal(await stockOfSku('P3-BLK-S'), 4, 'back to the fixture quantity exactly');

        // Stated, not hidden: usage is NOT refunded — a redeemed code stays
        // redeemed, which is the conservative direction for a discount counter.
        const coupon = await pool.query<{ used_count: number }>(
          'select used_count from commerce.coupons where code = $1',
          [COUPON_CODE],
        );
        assert.equal(coupon.rows[0]?.used_count, 1);
      });

      it('counts shipped quantity for best sellers and excludes cancelled orders', async () => {
        assert.deepEqual(
          (await listBestSellers(repo, 4)).map((card) => card.slug),
          [],
          'both fixture orders are cancelled, so neither product has shipped anything',
        );

        const paid = await placeCheckoutOrder(
          repo,
          mockPaymentGateway,
          draft({
            lines: [{ variantId: variantIds['P3-BLK-S'] as string, quantity: 1 }],
          }),
        );
        assert.ok(paid.ok);
        const moved = await transitionOrder(repo, paid.orderId, 'PAID');
        assert.deepEqual(moved, { ok: true });

        assert.deepEqual(
          (await listBestSellers(repo, 4)).map((card) => card.slug),
          [MANTO_SLUG],
          'a live (non-cancelled) order makes the product a best seller',
        );
      });

      it('refuses every malformed submission before touching the database', async () => {
        const ordersBefore = await orderRows();
        const stockBefore = await stockOfSku('P3-BLK-S');

        const cases: Array<{ draft: CheckoutDraft; code: string }> = [
          {
            draft: draft({ lines: [] }),
            code: 'EMPTY_CART',
          },
          {
            draft: draft({
              customer: { ...draft().customer, phoneNumber: '12345' },
            }),
            code: 'VALIDATION_ERROR',
          },
          {
            draft: draft({ shippingMethodId: 'SAME_DAY_DRONE' }),
            code: 'SHIPPING_UNKNOWN',
          },
          { draft: draft({ couponCode: 'NO-SUCH-CODE' }), code: 'COUPON_INVALID' },
          {
            draft: draft({
              lines: [
                { variantId: variantIds['P3-BLK-S'] as string, quantity: MAX_LINE_QUANTITY + 1 },
              ],
            }),
            code: 'VALIDATION_ERROR',
          },
        ];

        for (const testCase of cases) {
          const result = await placeCheckoutOrder(repo, mockPaymentGateway, testCase.draft);
          assert.ok(!result.ok, `expected a refusal for ${testCase.code}`);
          assert.equal(result.code, testCase.code, `refusal code for ${testCase.code}`);
          assert.ok(result.message.length > 0, 'every refusal explains itself');
        }

        assert.equal(await orderRows(), ordersBefore, 'no refusal wrote an order');
        assert.equal(await stockOfSku('P3-BLK-S'), stockBefore, 'no refusal consumed stock');
      });
    });

    describe('§3.4 payment seam', () => {
      it('leaves the order PENDING when the gateway authorizes a mock reference', async () => {
        // An explicit AUTHORIZED mock proves the write path records a reference
        // if a provider ever issues one — and still does not mark the order paid.
        const authorized = createMockPaymentGateway({ outcome: 'AUTHORIZED' });
        const placed = await placeCheckoutOrder(
          repo,
          authorized,
          draft({ lines: [{ variantId: variantIds['P3-WHT-S'] as string, quantity: 1 }] }),
        );
        assert.ok(placed.ok, 'the order must still be written');
        assert.equal(placed.payment.status, 'AUTHORIZED');
        assert.equal(placed.status, 'PENDING', 'Phase 6 moves an order to PAID, not this path');

        const row = await pool.query<{ status: string; payment_ref_id: string | null }>(
          'select status, payment_ref_id from commerce.orders where id = $1',
          [placed.orderId],
        );
        assert.equal(row.rows[0]?.status, 'PENDING');
        assert.match(row.rows[0]?.payment_ref_id ?? '', /^MOCK-/);
      });
    });
  },
);
