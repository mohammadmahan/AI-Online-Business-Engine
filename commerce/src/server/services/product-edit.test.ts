import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductUpdatePayload } from '@/contracts/catalog';
import { toDescriptionHtml } from '@/lib/variant-matrix';
import { validProductPayload } from '@/lib/validation.fixtures';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { createProduct, updateProduct } from '@/server/services/products';

const LOCAL_ENV = {
  NODE_ENV: 'development',
  MEDIA_PROVIDER: 'local',
  MEDIA_LOCAL_DIR: '/tmp/commerce-product-edit-test',
};

function reference(prefix: string, fill: string) {
  const hash = `${prefix}${fill.repeat(62)}`;
  const storagePath = `products/sha256/${prefix}/${hash}.jpg`;
  return { storagePath, publicUrl: `/media/${storagePath}` };
}

const IMAGE_A = reference('9d', 'c');
const IMAGE_B = reference('4a', 'b');
const IMAGE_C = reference('7f', 'e');

/**
 * D-172 §2.1 — the admin EDIT write.
 *
 * The service may change ONE product row. These tests pin that boundary: a
 * successful edit keeps variants, SKUs, stock, overrides and media exactly as
 * they were, and every refusal (validation, duplicate slug, unknown product)
 * leaves the catalog untouched.
 */

function editPayload(overrides: Partial<ProductUpdatePayload> = {}): ProductUpdatePayload {
  return {
    categoryId: 'cat-2',
    title: 'مانتو کتی لنین تابستانه',
    slug: 'manto-keti-lenin-tabestane',
    basePrice: 1_400_000,
    discountPrice: 1_300_000,
    descriptionRaw: 'نسخهٔ ویرایش‌شدهٔ توضیح محصول.',
    fabricType: 'کرپ',
    season: 'تابستانه',
    careInstructions: 'شست‌وشوی دستی',
    status: 'PUBLISHED',
    ...overrides,
  };
}

async function seedProduct(
  repository: CommerceRepository,
  slug = 'manto-keti-lenin',
): Promise<string> {
  const created = await createProduct(
    repository,
    validProductPayload({
      slug,
      images: [
        {
          ...IMAGE_A,
          displayOrder: 0,
          isPrimary: true,
        },
        {
          ...IMAGE_B,
          displayOrder: 1,
          isPrimary: false,
        },
      ],
    }),
    LOCAL_ENV,
  );
  assert.equal(created.ok, true);
  if (!created.ok) {
    throw new Error('fixture product was refused');
  }
  return created.productId;
}

/** The memory repository plus a count of the product-row writes it received. */
function countingRepository(): { repository: CommerceRepository; writes: () => number } {
  const inner = createMemoryRepository();
  let count = 0;
  return {
    writes: () => count,
    repository: {
      ...inner,
      async updateProductDetails(productId, input) {
        count += 1;
        return inner.updateProductDetails(productId, input);
      },
      async updateProductDetailsWithImages(productId, input, images) {
        count += 1;
        return inner.updateProductDetailsWithImages(productId, input, images);
      },
    },
  };
}

describe('product edit service (§2.1)', () => {
  it('updates the product-level fields and leaves variants, stock and media untouched', async () => {
    const repository = createMemoryRepository();
    const productId = await seedProduct(repository);

    const before = await repository.listInventory();
    const beforeImages = await repository.getProductImageEditor(productId);

    const result = await updateProduct(repository, productId, editPayload());
    assert.deepEqual(result, { ok: true, productId });

    const product = await repository.getProductForEdit(productId);
    assert.equal(product?.title, 'مانتو کتی لنین تابستانه');
    assert.equal(product?.slug, 'manto-keti-lenin-tabestane');
    assert.equal(product?.categoryId, 'cat-2');
    assert.equal(product?.basePrice, 1_400_000);
    assert.equal(product?.discountPrice, 1_300_000);
    assert.equal(product?.fabricType, 'کرپ');
    assert.equal(product?.season, 'تابستانه');
    assert.equal(product?.careInstructions, 'شست‌وشوی دستی');
    assert.equal(product?.status, 'PUBLISHED');
    assert.equal(product?.descriptionRaw, 'نسخهٔ ویرایش‌شدهٔ توضیح محصول.');

    const after = await repository.listInventory();
    assert.equal(after.length, before.length);
    assert.deepEqual(
      after.map((row) => [row.sku, row.size, row.colorName, row.stockQuantity, row.priceOverride]),
      before.map((row) => [row.sku, row.size, row.colorName, row.stockQuantity, row.priceOverride]),
    );
    assert.equal(after.find((row) => row.sku === 'MANTO-KETI-38-1')?.stockQuantity, 2);
    assert.equal(after.find((row) => row.sku === 'MANTO-KETI-38-1')?.priceOverride, 1_200_000);

    const afterImages = await repository.getProductImageEditor(productId);
    assert.deepEqual(afterImages?.images, beforeImages?.images);
    assert.equal(afterImages?.images.length, 2);
  });

  it('maps a duplicate slug to the slug field and writes nothing', async () => {
    const repository = createMemoryRepository();
    const firstId = await seedProduct(repository);
    const secondId = await seedProduct(repository, 'shomiz-abrisham');
    const beforeSecond = await repository.getProductForEdit(secondId);
    const beforeFirst = await repository.getProductForEdit(firstId);
    assert.ok(beforeSecond && beforeFirst);

    const result = await updateProduct(
      repository,
      secondId,
      editPayload({ slug: beforeFirst.slug }),
    );

    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'VALIDATION_ERROR');
    assert.equal(result.issues[0]?.field, 'slug');
    assert.match(result.issues[0]?.message ?? '', /نشانی محصول قبلاً استفاده شده/);

    assert.deepEqual(await repository.getProductForEdit(secondId), beforeSecond);
    assert.deepEqual(await repository.getProductForEdit(firstId), beforeFirst);
  });

  it('rejects an invalid base price or discount without writing', async () => {
    const { repository, writes } = countingRepository();
    const productId = await seedProduct(repository);
    const before = await repository.getProductForEdit(productId);

    const badPrice = await updateProduct(repository, productId, editPayload({ basePrice: 0 }));
    assert.equal(badPrice.ok, false);
    if (!badPrice.ok && badPrice.code === 'VALIDATION_ERROR') {
      assert.ok(badPrice.issues.some((entry) => entry.field === 'basePrice'));
    } else {
      assert.fail('a zero base price must be a field error');
    }

    const badDiscount = await updateProduct(
      repository,
      productId,
      editPayload({ basePrice: 500_000, discountPrice: 700_000 }),
    );
    assert.equal(badDiscount.ok, false);
    if (!badDiscount.ok && badDiscount.code === 'VALIDATION_ERROR') {
      assert.ok(badDiscount.issues.some((entry) => entry.field === 'discountPrice'));
    } else {
      assert.fail('a discount above the base price must be a field error');
    }

    const fractional = await updateProduct(repository, productId, editPayload({ basePrice: 1000.5 }));
    assert.equal(fractional.ok, false);

    assert.equal(writes(), 0);
    assert.deepEqual(await repository.getProductForEdit(productId), before);
  });

  it('rejects a status outside the schema enum', async () => {
    const { repository, writes } = countingRepository();
    const productId = await seedProduct(repository);

    const result = await updateProduct(
      repository,
      productId,
      editPayload({ status: 'SOLD' as unknown as ProductUpdatePayload['status'] }),
    );

    assert.equal(result.ok, false);
    if (!result.ok && result.code === 'VALIDATION_ERROR') {
      assert.equal(result.issues[0]?.field, 'status');
    } else {
      assert.fail('an unknown status must be refused');
    }
    assert.equal(writes(), 0);
  });

  it('reports an unknown product as not found, malformed id included', async () => {
    const repository = createMemoryRepository();

    const missing = await updateProduct(
      repository,
      '00000000-0000-4000-8000-000000000000',
      editPayload(),
    );
    assert.equal(missing.ok, false);
    if (!missing.ok) assert.equal(missing.code, 'NOT_FOUND');

    const malformed = await updateProduct(repository, 'not-a-uuid', editPayload());
    assert.equal(malformed.ok, false);
    if (!malformed.ok) assert.equal(malformed.code, 'NOT_FOUND');
  });

  it('refuses an external or mismatched image reference during update and writes nothing', async () => {
    const { repository, writes } = countingRepository();
    const productId = await seedProduct(repository);
    const beforeProduct = await repository.getProductForEdit(productId);
    const beforeImages = await repository.getProductImageEditor(productId);

    const offenders = [
      { ...IMAGE_C, publicUrl: 'https://evil.example/x.jpg' },
      { ...IMAGE_C, publicUrl: `${IMAGE_C.publicUrl}?v=2` },
      { ...IMAGE_C, storagePath: IMAGE_C.storagePath.replace('7f', 'ff') },
    ];

    for (const offender of offenders) {
      const result = await updateProduct(
        repository,
        productId,
        editPayload({ title: 'عنوان نباید ذخیره شود', images: [offender] }),
        LOCAL_ENV,
      );
      assert.equal(result.ok, false, JSON.stringify(offender));
      if (result.ok) return;
      assert.equal(result.code, 'VALIDATION_ERROR');
      assert.equal(result.issues[0]?.field, 'images.0.publicUrl');
      assert.deepEqual(await repository.getProductForEdit(productId), beforeProduct);
      assert.deepEqual(await repository.getProductImageEditor(productId), beforeImages);
    }
    assert.equal(writes(), 0);
  });

  it('refuses an incomplete image slot during update and writes nothing', async () => {
    const { repository, writes } = countingRepository();
    const productId = await seedProduct(repository);
    const beforeProduct = await repository.getProductForEdit(productId);
    const beforeImages = await repository.getProductImageEditor(productId);

    const result = await updateProduct(
      repository,
      productId,
      editPayload({
        title: 'عنوان نباید ذخیره شود',
        images: [{ storagePath: IMAGE_C.storagePath, publicUrl: '' }],
      }),
      LOCAL_ENV,
    );

    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'VALIDATION_ERROR');
    assert.equal(result.issues[0]?.field, 'images.0');
    assert.equal(writes(), 0);
    assert.deepEqual(await repository.getProductForEdit(productId), beforeProduct);
    assert.deepEqual(await repository.getProductImageEditor(productId), beforeImages);
  });

  it('refuses a new image reference during update when no media provider is configured', async () => {
    const { repository, writes } = countingRepository();
    const productId = await seedProduct(repository);
    const beforeProduct = await repository.getProductForEdit(productId);
    const beforeImages = await repository.getProductImageEditor(productId);

    const result = await updateProduct(
      repository,
      productId,
      editPayload({ title: 'عنوان نباید ذخیره شود', images: [IMAGE_C] }),
      {},
    );

    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'VALIDATION_ERROR');
    assert.equal(result.issues[0]?.field, 'images');
    assert.match(result.message, /ذخیره‌سازی محلی رسانه|نشانی بیرونی/);
    assert.equal(writes(), 0);
    assert.deepEqual(await repository.getProductForEdit(productId), beforeProduct);
    assert.deepEqual(await repository.getProductImageEditor(productId), beforeImages);
  });

  it('updates product fields and gallery together with valid content-addressed references', async () => {
    const repository = createMemoryRepository();
    const productId = await seedProduct(repository);
    const before = await repository.getProductImageEditor(productId);
    assert.ok(before);
    const [first, second] = before.images;
    assert.ok(first && second);

    const result = await updateProduct(
      repository,
      productId,
      editPayload({
        title: 'عنوان هم‌زمان با گالری',
        images: [
          { id: second.id },
          { storagePath: IMAGE_C.storagePath, publicUrl: IMAGE_C.publicUrl },
          { id: first.id, isPrimary: true },
        ],
      }),
      LOCAL_ENV,
    );
    assert.deepEqual(result, { ok: true, productId });

    const product = await repository.getProductForEdit(productId);
    assert.equal(product?.title, 'عنوان هم‌زمان با گالری');

    const after = await repository.getProductImageEditor(productId);
    assert.ok(after);
    assert.deepEqual(
      after.images.map((row) => ({
        path: row.storagePath,
        order: row.displayOrder,
        primary: row.isPrimary,
      })),
      [
        { path: IMAGE_B.storagePath, order: 0, primary: false },
        { path: IMAGE_C.storagePath, order: 1, primary: false },
        { path: IMAGE_A.storagePath, order: 2, primary: true },
      ],
    );
  });

  it('rolls the product fields back when the update references another product image', async () => {
    const repository = createMemoryRepository();
    const firstId = await seedProduct(repository);
    const secondId = await seedProduct(repository, 'shomiz-abrisham');
    const firstBefore = await repository.getProductForEdit(firstId);
    const firstImages = await repository.getProductImageEditor(firstId);
    const secondImages = await repository.getProductImageEditor(secondId);
    assert.ok(firstBefore && firstImages && secondImages);

    const result = await updateProduct(
      repository,
      firstId,
      editPayload({
        title: 'عنوان نباید ذخیره شود',
        images: [{ id: secondImages.images[0]!.id }],
      }),
      LOCAL_ENV,
    );

    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'VALIDATION_ERROR');
    assert.equal(result.issues[0]?.field, 'images');
    assert.deepEqual(await repository.getProductForEdit(firstId), firstBefore);
    assert.deepEqual(await repository.getProductImageEditor(firstId), firstImages);
    assert.deepEqual(await repository.getProductImageEditor(secondId), secondImages);
  });

  it('rejects a category that does not exist, before touching the row', async () => {
    const { repository, writes } = countingRepository();
    const productId = await seedProduct(repository);
    const before = await repository.getProductForEdit(productId);

    const result = await updateProduct(
      repository,
      productId,
      editPayload({ categoryId: '00000000-0000-4000-8000-000000000000' }),
    );

    assert.equal(result.ok, false);
    if (!result.ok && result.code === 'VALIDATION_ERROR') {
      assert.equal(result.issues[0]?.field, 'categoryId');
    } else {
      assert.fail('an unknown category must be a field error');
    }
    assert.equal(writes(), 0);
    assert.deepEqual(await repository.getProductForEdit(productId), before);
  });

  it('preserves the stored HTML body when the raw text is unchanged and re-derives it when edited', async () => {
    const repository = createMemoryRepository();
    const productId = await seedProduct(repository);
    const before = await repository.getProductForEdit(productId);
    assert.ok(before);

    await updateProduct(repository, productId, editPayload({ descriptionRaw: before.descriptionRaw }));
    const unchanged = await repository.getProductForEdit(productId);
    assert.equal(unchanged?.descriptionHtml, before.descriptionHtml);

    await updateProduct(
      repository,
      productId,
      editPayload({ descriptionRaw: 'توضیح تازه\n\n<b>خام</b>' }),
    );
    const changed = await repository.getProductForEdit(productId);
    assert.equal(changed?.descriptionHtml, toDescriptionHtml('توضیح تازه\n\n<b>خام</b>'));
    assert.equal(changed?.descriptionHtml.includes('<b>'), false);
  });
});
