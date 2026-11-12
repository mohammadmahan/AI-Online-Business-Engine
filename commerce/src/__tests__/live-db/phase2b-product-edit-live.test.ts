import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { eq } from 'drizzle-orm';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import { Pool } from 'pg';

import { createCommerceDb, type CommerceDb } from '@/db';
import { categories, productImages, productVariants, products } from '@/db/schema';
import { validProductPayload, variant } from '@/lib/validation.fixtures';
import { createPostgresRepository, type CommerceRepository } from '@/server/repository';
import { createProduct, updateProduct } from '@/server/services/products';

/**
 * D-172 §2.1 — the admin EDIT path against REAL PostgreSQL.
 *
 * The service unit tests prove the rules with the memory double; this suite
 * proves the two facts only the server can: the duplicate-slug UNIQUE constraint
 * is translated into the same field message, and a product-row update really
 * leaves `product_variants` / `product_images` rows intact.
 *
 * Runs only against the disposable loopback harness (`COMMERCE_DATABASE_URL`);
 * an absent or non-loopback target SKIPS instead of guessing.
 */

const HARNESS_URL = process.env.COMMERCE_DATABASE_URL?.trim();
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

function skipReason(): string | undefined {
  if (!HARNESS_URL) {
    return 'COMMERCE_DATABASE_URL not set — live product-edit suite skipped (no target is guessed; fail-closed)';
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
  MEDIA_LOCAL_DIR: '/tmp/commerce-live-phase2b',
};

function reference(prefix: string, fill: string) {
  const hash = `${prefix}${fill.repeat(62)}`;
  const storagePath = `products/sha256/${prefix}/${hash}.jpg`;
  return { storagePath, publicUrl: `/media/${storagePath}` };
}

const IMAGE_A = reference('9d', 'c');

describe('D-172 §2.1 — live product edit (disposable harness)', { skip: skipReason() }, () => {
  let pool!: Pool;
  let db!: CommerceDb;
  let repo!: CommerceRepository;
  let categoryId = '';
  let productId = '';
  let otherProductId = '';

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
    assert.ok(existsSync(`${MIGRATIONS_FOLDER}/meta/_journal.json`));
    await migrate(db, { migrationsFolder: MIGRATIONS_FOLDER });

    const [category] = await db
      .insert(categories)
      .values({ name: 'مانتو', slug: 'manto', description: 'دستهٔ آزمایشی' })
      .returning({ id: categories.id });
    assert.ok(category);
    categoryId = category.id;

    const first = await createProduct(
      repo,
      validProductPayload({
        categoryId,
        slug: 'manto-katan-live',
        images: [
          {
            ...IMAGE_A,
            displayOrder: 0,
            isPrimary: true,
          },
        ],
      }),
      LOCAL_ENV,
    );
    assert.equal(first.ok, true);
    if (!first.ok) throw new Error('fixture product refused');
    productId = first.productId;

    const second = await createProduct(
      repo,
      validProductPayload({
        categoryId,
        slug: 'shomiz-abrisham-live',
        variants: [variant({ sku: 'SHOMIZ-LIVE-1', size: '40' })],
      }),
      LOCAL_ENV,
    );
    assert.equal(second.ok, true);
    if (!second.ok) throw new Error('fixture product refused');
    otherProductId = second.productId;
  });

  after(async () => {
    await pool.end();
  });

  it('updates the row and leaves variant, image and stock rows untouched', async () => {
    const variantsBefore = await db
      .select()
      .from(productVariants)
      .where(eq(productVariants.productId, productId));
    const imagesBefore = await db
      .select()
      .from(productImages)
      .where(eq(productImages.productId, productId));
    assert.equal(variantsBefore.length, 4);
    assert.equal(imagesBefore.length, 1);

    const result = await updateProduct(repo, productId, {
      categoryId,
      title: 'مانتو کتان تابستانی (ویرایش‌شده)',
      slug: 'manto-katan-live',
      basePrice: 2_600_000,
      discountPrice: 2_400_000,
      descriptionRaw: 'توضیح ویرایش‌شده.',
      fabricType: 'کتان',
      season: 'تابستانه',
      careInstructions: null,
      status: 'PUBLISHED',
    });
    assert.equal(result.ok, true);

    const [row] = await db.select().from(products).where(eq(products.id, productId));
    assert.equal(row?.title, 'مانتو کتان تابستانی (ویرایش‌شده)');
    assert.equal(row?.basePrice, 2_600_000);
    assert.equal(row?.discountPrice, 2_400_000);
    assert.equal(row?.status, 'PUBLISHED');
    assert.equal(row?.careInstructions, null);

    const variantsAfter = await db
      .select()
      .from(productVariants)
      .where(eq(productVariants.productId, productId));
    const imagesAfter = await db
      .select()
      .from(productImages)
      .where(eq(productImages.productId, productId));
    assert.deepEqual(
      variantsAfter.map((entry) => [entry.id, entry.sku, entry.stockQuantity, entry.priceOverride]),
      variantsBefore.map((entry) => [entry.id, entry.sku, entry.stockQuantity, entry.priceOverride]),
    );
    assert.deepEqual(
      imagesAfter.map((entry) => [entry.id, entry.storagePath, entry.displayOrder, entry.isPrimary]),
      imagesBefore.map((entry) => [entry.id, entry.storagePath, entry.displayOrder, entry.isPrimary]),
    );
  });

  it('turns the UNIQUE slug violation into the slug field message and writes nothing', async () => {
    const [before] = await db.select().from(products).where(eq(products.id, otherProductId));

    const result = await updateProduct(repo, otherProductId, {
      categoryId,
      title: before?.title ?? '',
      slug: 'manto-katan-live',
      basePrice: before?.basePrice ?? 0,
      discountPrice: null,
      descriptionRaw: before?.descriptionRaw ?? '',
      fabricType: before?.fabricType ?? '',
      season: before?.season ?? '',
      careInstructions: null,
      status: 'DRAFT',
    });

    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'VALIDATION_ERROR');
    assert.equal(result.issues[0]?.field, 'slug');

    const [after] = await db.select().from(products).where(eq(products.id, otherProductId));
    assert.deepEqual(after, before);
  });

  it('answers NOT_FOUND for an unknown product id', async () => {
    const result = await updateProduct(repo, '00000000-0000-4000-8000-000000000000', {
      categoryId,
      title: 'x',
      slug: 'x-live',
      basePrice: 1000,
      discountPrice: null,
      descriptionRaw: 'x',
      fabricType: 'x',
      season: 'x',
      careInstructions: null,
      status: 'DRAFT',
    });
    assert.equal(result.ok, false);
    if (!result.ok) assert.equal(result.code, 'NOT_FOUND');
  });
});
