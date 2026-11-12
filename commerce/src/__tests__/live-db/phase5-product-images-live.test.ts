import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import { Pool } from 'pg';

import type { ProductCreatePayload } from '@/contracts/catalog';
import { createCommerceDb, type CommerceDb } from '@/db';
import { categories } from '@/db/schema';
import { createPostgresRepository, type CommerceRepository } from '@/server/repository';
import { updateProductImages } from '@/server/services/product-images';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §2.1 — the gallery edit against REAL PostgreSQL (disposable harness).
 *
 * Replacing a gallery is a multi-statement transaction (delete the omitted rows,
 * update the kept ones, insert the new ones) with an ownership check in the
 * middle. The in-memory double models the BEHAVIOUR; only a real server proves
 * the SQL, the transaction and the constraint interactions — which is exactly the
 * class of defect the Phase 3 live pass found and no unit test could have.
 *
 * The assertions read the rows back with SQL rather than trusting the service's
 * reply, and every refusal is checked against the database state as well.
 *
 * Target and gates match the other live suites: the disposable loopback harness
 * only; SKIP with a named reason when `COMMERCE_DATABASE_URL` is absent or not
 * loopback (D-171 §2.2 — an absent configuration is a refusal, never a pass); a
 * full schema reset plus the COMMITTED migrations on every run.
 */

const HARNESS_URL = process.env.COMMERCE_DATABASE_URL?.trim();
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function skipReason(): string | undefined {
  if (!HARNESS_URL) {
    return 'COMMERCE_DATABASE_URL not set — live PostgreSQL gallery suite skipped (no target is guessed; fail-closed)';
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

const LOCAL_ENV = {
  NODE_ENV: 'development',
  MEDIA_PROVIDER: 'local',
  MEDIA_LOCAL_DIR: '/tmp/commerce-live-product-images',
};

function reference(prefix: string, fill: string) {
  const hash = `${prefix}${fill.repeat(62)}`;
  const storagePath = `products/sha256/${prefix}/${hash}.jpg`;
  return { storagePath, publicUrl: `/media/${storagePath}` };
}

const IMAGES = [reference('9d', 'c'), reference('4a', 'b'), reference('7f', 'e')];
const EXTRA = reference('aa', '1');

const SLUG = 'shal-terme-images-live';
const OTHER_SLUG = 'shal-terme-images-other';

interface ImageRow {
  id: string;
  storage_path: string;
  public_url: string;
  display_order: number;
  is_primary: boolean;
}

describe('D-172 §2.1 — live PostgreSQL gallery edit (disposable harness)', { skip: skipReason() }, () => {
  let pool!: Pool;
  let db!: CommerceDb;
  let repo!: CommerceRepository;
  let categoryId = '';
  let productId = '';
  let otherProductId = '';

  async function galleryOf(id: string): Promise<ImageRow[]> {
    const rows = await pool.query<ImageRow>(
      `select id, storage_path, public_url, display_order, is_primary
         from commerce.product_images where product_id = $1
        order by display_order, id`,
      [id],
    );
    return rows.rows;
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
      .values({ name: 'شال', slug: 'shal-images' })
      .returning({ id: categories.id });
    categoryId = category?.id as string;

    const payload = (slug: string, title: string, sku: string, images: typeof IMAGES): ProductCreatePayload => ({
      categoryId,
      title,
      slug,
      basePrice: 1_250_000,
      discountPrice: 990_000,
      descriptionRaw: 'شال ترمه برای آزمون ویرایش تصویر.',
      descriptionHtml: '<p>شال ترمه</p>',
      fabricType: 'ترمه',
      season: 'پاییز و زمستان',
      status: 'PUBLISHED',
      variants: [
        { sku, colorName: 'مشکی', colorHex: '#111111', size: 'FreeSize', stockQuantity: 7 },
      ],
      images: images.map((image, index) => ({
        ...image,
        displayOrder: index,
        isPrimary: index === 0,
      })),
    });

    const product = await createProduct(
      repo,
      payload(SLUG, 'شال ترمه', 'LIVE-IMG-FS', IMAGES),
      LOCAL_ENV,
    );
    assert.ok(product.ok, JSON.stringify(product));
    productId = product.productId;

    const other = await createProduct(
      repo,
      payload(OTHER_SLUG, 'شال دیگر', 'LIVE-IMG-OTH', [EXTRA]),
      LOCAL_ENV,
    );
    assert.ok(other.ok, JSON.stringify(other));
    otherProductId = other.productId;
  });

  after(async () => {
    await pool.end();
  });

  it('persists order, primary flag, additions and removals in one transaction', async () => {
    const before = await galleryOf(productId);
    assert.equal(before.length, 3);
    const [first, second, third] = before;

    const result = await updateProductImages(
      repo,
      productId,
      [
        { id: third!.id },
        { id: first!.id, isPrimary: true },
        { storagePath: EXTRA.storagePath, publicUrl: EXTRA.publicUrl },
      ],
      LOCAL_ENV,
    );
    assert.equal(result.ok, true, JSON.stringify(result));

    const after = await galleryOf(productId);
    assert.deepEqual(
      after.map((row) => ({ path: row.storage_path, order: row.display_order, primary: row.is_primary })),
      [
        { path: IMAGES[2]!.storagePath, order: 0, primary: false },
        { path: IMAGES[0]!.storagePath, order: 1, primary: true },
        { path: EXTRA.storagePath, order: 2, primary: false },
      ],
    );
    // The removed association is gone from the table, and the kept rows are the
    // SAME rows (ids preserved) rather than delete-and-reinsert.
    assert.equal(after.some((row) => row.storage_path === second!.storage_path), false);
    assert.equal(after[0]?.id, third!.id);
    assert.equal(after[1]?.id, first!.id);

    const detail = await repo.getStorefrontProduct(SLUG);
    assert.ok(detail);
    assert.equal(detail.images[0]?.url, IMAGES[0]!.publicUrl);
  });

  it('preserves the product columns and its variants exactly', async () => {
    const productBefore = await pool.query(
      `select title, slug, base_price, discount_price, description_raw, fabric_type, season,
              care_instructions, status, category_id, created_at
         from commerce.products where id = $1`,
      [productId],
    );
    const variantsBefore = await pool.query(
      `select sku, stock_quantity, price_override, is_active, color_name, size
         from commerce.product_variants where product_id = $1 order by sku`,
      [productId],
    );
    const ordersBefore = await pool.query('select count(*)::int as count from commerce.orders');

    const gallery = await galleryOf(productId);
    const result = await updateProductImages(
      repo,
      productId,
      [{ id: gallery[0]!.id, isPrimary: true }, { id: gallery[1]!.id }],
      LOCAL_ENV,
    );
    assert.equal(result.ok, true);

    const productAfter = await pool.query(
      `select title, slug, base_price, discount_price, description_raw, fabric_type, season,
              care_instructions, status, category_id, created_at
         from commerce.products where id = $1`,
      [productId],
    );
    const variantsAfter = await pool.query(
      `select sku, stock_quantity, price_override, is_active, color_name, size
         from commerce.product_variants where product_id = $1 order by sku`,
      [productId],
    );
    const ordersAfter = await pool.query('select count(*)::int as count from commerce.orders');

    assert.deepEqual(productAfter.rows, productBefore.rows);
    assert.deepEqual(variantsAfter.rows, variantsBefore.rows);
    assert.deepEqual(ordersAfter.rows, ordersBefore.rows);
    assert.equal((await galleryOf(productId)).length, 2);
  });

  it('refuses another product’s image id and commits nothing', async () => {
    const ownBefore = await galleryOf(productId);
    const foreign = await galleryOf(otherProductId);
    assert.equal(foreign.length, 1);

    const result = await updateProductImages(
      repo,
      productId,
      [{ id: ownBefore[0]!.id }, { id: foreign[0]!.id }],
      LOCAL_ENV,
    );
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'VALIDATION_ERROR');

    assert.deepEqual(await galleryOf(productId), ownBefore);
    assert.deepEqual(await galleryOf(otherProductId), foreign);
  });

  it('refuses a reference that is not from the configured store, writing nothing', async () => {
    const before = await galleryOf(productId);
    const result = await updateProductImages(
      repo,
      productId,
      [{ storagePath: EXTRA.storagePath, publicUrl: 'https://evil.example/x.jpg' }],
      LOCAL_ENV,
    );
    assert.equal(result.ok, false);
    assert.deepEqual(await galleryOf(productId), before);
  });

  it('empties a gallery without deleting the product or its variants', async () => {
    const result = await updateProductImages(repo, productId, [], LOCAL_ENV);
    assert.equal(result.ok, true);
    assert.deepEqual(await galleryOf(productId), []);

    const product = await pool.query('select count(*)::int as count from commerce.products where id = $1', [
      productId,
    ]);
    const variants = await pool.query(
      'select count(*)::int as count from commerce.product_variants where product_id = $1',
      [productId],
    );
    assert.equal(product.rows[0].count, 1);
    assert.equal(variants.rows[0].count, 1);
    assert.equal((await repo.getStorefrontProduct(SLUG))?.images.length, 0);
  });
});
