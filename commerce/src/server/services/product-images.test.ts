import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { updateProductImages } from '@/server/services/product-images';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §2.1 — editing an existing product's gallery (offline half).
 *
 * What these tests protect, in order of how much damage a regression would do:
 *  - the catalog AROUND the gallery is untouched (variants, stock, prices,
 *    status, orders) — the editor is scoped to `product_images`;
 *  - a submitted reference cannot point the store at an arbitrary origin;
 *  - one product's photo cannot be moved into (or deleted from) another product;
 *  - a refused edit writes nothing at all.
 *
 * The SQL itself is proven separately against real PostgreSQL
 * (`__tests__/live-db/phase5-product-images-live.test.ts`); this suite runs on
 * every `npm test` so the rules cannot regress between live passes.
 */

/** `products/sha256/<first2>/<64 hex>.<ext>` — the key shape both writers emit. */
function reference(prefix: string, fill: string, extension = 'jpg') {
  const hash = `${prefix}${fill.repeat(62)}`; // 2 + 62 = a 64-hex content address
  const storagePath = `products/sha256/${prefix}/${hash}.${extension}`;
  return { storagePath, publicUrl: `/media/${storagePath}` };
}

const LOCAL_ENV = {
  NODE_ENV: 'development',
  MEDIA_PROVIDER: 'local',
  MEDIA_LOCAL_DIR: '/tmp/commerce-product-images-test',
};

const FIRST = reference('9d', 'c');
const SECOND = reference('4a', 'b');
const THIRD = reference('7f', 'e');

function payload(overrides: Partial<ProductCreatePayload> = {}): ProductCreatePayload {
  return {
    categoryId: 'cat-1',
    title: 'شال ترمه',
    slug: 'shal-terme-edit',
    basePrice: 1_250_000,
    discountPrice: 990_000,
    descriptionRaw: 'شال ترمه با حاشیه دوخته‌شده.',
    descriptionHtml: '',
    fabricType: 'ترمه',
    season: 'پاییز و زمستان',
    status: 'PUBLISHED',
    variants: [
      { sku: 'EDIT-BLK-FS', colorName: 'مشکی', colorHex: '#111111', size: 'FreeSize', stockQuantity: 5 },
    ],
    images: [
      { ...FIRST, displayOrder: 0, isPrimary: true },
      { ...SECOND, displayOrder: 1, isPrimary: false },
    ],
    ...overrides,
  };
}

interface Harness {
  repository: CommerceRepository;
  productId: string;
  slug: string;
}

async function harness(): Promise<Harness> {
  const repository = createMemoryRepository();
  const created = await createProduct(repository, payload(), LOCAL_ENV);
  assert.ok(created.ok, `fixture product must be written: ${JSON.stringify(created)}`);
  return { repository, productId: created.productId, slug: 'shal-terme-edit' };
}

async function editorOf(repository: CommerceRepository, productId: string) {
  const editor = await repository.getProductImageEditor(productId);
  assert.ok(editor, 'the product must exist');
  return editor;
}

describe('updateProductImages — the edit itself', () => {
  it('adds, reorders, marks a primary and removes associations in one write', async () => {
    const { repository, productId } = await harness();
    const before = await editorOf(repository, productId);
    const [firstRow, secondRow] = before.images;
    assert.ok(firstRow && secondRow);

    const result = await updateProductImages(
      repository,
      productId,
      [
        { id: secondRow.id },
        { id: firstRow.id, isPrimary: true },
        { storagePath: THIRD.storagePath, publicUrl: THIRD.publicUrl },
      ],
      LOCAL_ENV,
    );
    assert.equal(result.ok, true, JSON.stringify(result));

    const after = await editorOf(repository, productId);
    assert.deepEqual(
      after.images.map((row) => ({ path: row.storagePath, order: row.displayOrder, primary: row.isPrimary })),
      [
        { path: SECOND.storagePath, order: 0, primary: false },
        { path: FIRST.storagePath, order: 1, primary: true },
        { path: THIRD.storagePath, order: 2, primary: false },
      ],
    );
  });

  it('keeps the storefront gallery in primary-first order after the edit', async () => {
    const { repository, productId, slug } = await harness();
    const before = await editorOf(repository, productId);
    const first = before.images[0]!;

    const result = await updateProductImages(
      repository,
      productId,
      [{ id: first.id }, { id: before.images[1]!.id, isPrimary: true }],
      LOCAL_ENV,
    );
    assert.equal(result.ok, true);

    const detail = await repository.getStorefrontProduct(slug);
    assert.ok(detail);
    assert.equal(detail.images[0]?.url, SECOND.publicUrl);
    assert.equal(detail.imageUrls[0], SECOND.publicUrl);
  });

  it('accepts an empty gallery: every association removed, the product kept', async () => {
    const { repository, productId } = await harness();
    const result = await updateProductImages(repository, productId, [], LOCAL_ENV);
    assert.equal(result.ok, true);
    const after = await editorOf(repository, productId);
    assert.deepEqual(after.images, []);
    assert.equal((await repository.listProducts()).length, 1);
  });

  it('preserves variants, stock, prices, status and the storefront read', async () => {
    const { repository, productId, slug } = await harness();
    const inventoryBefore = await repository.listInventory();
    const listBefore = await repository.listProducts();
    const storefrontBefore = await repository.getStorefrontProduct(slug);
    assert.ok(storefrontBefore);

    const before = await editorOf(repository, productId);
    const result = await updateProductImages(
      repository,
      productId,
      [{ id: before.images[0]!.id }, { storagePath: THIRD.storagePath, publicUrl: THIRD.publicUrl }],
      LOCAL_ENV,
    );
    assert.equal(result.ok, true);

    assert.deepEqual(await repository.listInventory(), inventoryBefore);

    const listAfter = await repository.listProducts();
    assert.deepEqual(
      listAfter.map((row) => ({ ...row, imageCount: 0 })),
      listBefore.map((row) => ({ ...row, imageCount: 0 })),
    );

    const storefrontAfter = await repository.getStorefrontProduct(slug);
    assert.ok(storefrontAfter);
    assert.deepEqual(storefrontAfter.variants, storefrontBefore.variants);
    assert.equal(storefrontAfter.title, storefrontBefore.title);
    assert.equal(storefrontAfter.basePrice, storefrontBefore.basePrice);
    assert.equal(storefrontAfter.discountPrice, storefrontBefore.discountPrice);
    assert.equal(storefrontAfter.descriptionRaw, storefrontBefore.descriptionRaw);
    assert.equal(storefrontAfter.fabricType, storefrontBefore.fabricType);
    assert.equal(storefrontAfter.season, storefrontBefore.season);
    assert.equal(storefrontAfter.availability, storefrontBefore.availability);
    assert.equal((await editorOf(repository, productId)).status, 'PUBLISHED');
  });
});

describe('updateProductImages — refusals', () => {
  it('refuses an arbitrary or malformed reference and writes nothing', async () => {
    const { repository, productId } = await harness();
    const before = await editorOf(repository, productId);

    const offenders = [
      { storagePath: THIRD.storagePath, publicUrl: 'https://evil.example/x.jpg' },
      { storagePath: THIRD.storagePath, publicUrl: `${THIRD.publicUrl}?v=2` },
      { storagePath: '../etc/passwd', publicUrl: '/media/../etc/passwd' },
      { storagePath: THIRD.storagePath.replace('7f', 'ff'), publicUrl: THIRD.publicUrl },
      { storagePath: THIRD.storagePath, publicUrl: `data:image/png;base64,AAAA` },
    ];

    for (const offender of offenders) {
      const result = await updateProductImages(repository, productId, [offender], LOCAL_ENV);
      assert.equal(result.ok, false, JSON.stringify(offender));
      if (result.ok) continue;
      assert.equal(result.code, 'VALIDATION_ERROR');
      assert.deepEqual(await editorOf(repository, productId), before);
    }
  });

  it('refuses a reference id that belongs to another product, leaving both galleries intact', async () => {
    const repository = createMemoryRepository();
    const alpha = await createProduct(repository, payload(), LOCAL_ENV);
    const beta = await createProduct(
      repository,
      payload({ slug: 'shal-terme-other', title: 'شال دیگر', variants: [
        { sku: 'OTHER-BLK-FS', colorName: 'مشکی', colorHex: '#111111', size: 'FreeSize', stockQuantity: 1 },
      ] }),
      LOCAL_ENV,
    );
    assert.ok(alpha.ok && beta.ok);

    const alphaBefore = await editorOf(repository, alpha.productId);
    const betaBefore = await editorOf(repository, beta.productId);
    const foreignId = betaBefore.images[0]!.id;

    const result = await updateProductImages(
      repository,
      alpha.productId,
      [{ id: alphaBefore.images[0]!.id }, { id: foreignId }],
      LOCAL_ENV,
    );
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'VALIDATION_ERROR');

    assert.deepEqual(await editorOf(repository, alpha.productId), alphaBefore);
    assert.deepEqual(await editorOf(repository, beta.productId), betaBefore);
  });

  it('refuses a new reference when no media provider is configured', async () => {
    const { repository, productId } = await harness();
    const before = await editorOf(repository, productId);

    const result = await updateProductImages(
      repository,
      productId,
      [{ storagePath: THIRD.storagePath, publicUrl: THIRD.publicUrl }],
      {},
    );
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'MEDIA_NOT_CONFIGURED');
    assert.deepEqual(await editorOf(repository, productId), before);
  });

  it('still allows a reorder or removal with no provider configured (it touches no bytes)', async () => {
    const { repository, productId } = await harness();
    const before = await editorOf(repository, productId);
    const result = await updateProductImages(
      repository,
      productId,
      [{ id: before.images[1]!.id, isPrimary: true }, { id: before.images[0]!.id }],
      {},
    );
    assert.equal(result.ok, true);
    assert.equal((await editorOf(repository, productId)).images[0]?.isPrimary, true);
  });

  it('answers NOT_FOUND for an unknown product and VALIDATION_ERROR for a malformed id', async () => {
    const { repository } = await harness();
    const missing = await updateProductImages(
      repository,
      '00000000-0000-4000-8000-000000000000',
      [],
      LOCAL_ENV,
    );
    assert.equal(missing.ok, false);
    if (!missing.ok) assert.equal(missing.code, 'NOT_FOUND');

    const malformed = await updateProductImages(repository, 'not-a-uuid', [], LOCAL_ENV);
    assert.equal(malformed.ok, false);
    if (!malformed.ok) assert.equal(malformed.code, 'VALIDATION_ERROR');
  });
});
