import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { createMemoryRepository } from '@/server/repository-memory';
import { createCategory, listCategoryAdminRows } from '@/server/services/categories';

/**
 * D-172 §1.1 — the merchant's category write path.
 *
 * Before Phase 4 the only way to create a category was the demo seed script,
 * which refuses any target outside the throwaway harness — so a merchant could
 * not open their own catalog. These tests state the replacement's contract:
 * validated input only, a duplicate slug is a field-level refusal (not a crash),
 * and a new category is immediately visible to both the panel AND the product
 * form's dropdown (one read path, `listCategories`).
 */

const valid = { name: 'مانتو کتانی', slug: 'manto-ketani', description: 'کتانی و راحتی' };

describe('category service — creation (§1.1)', () => {
  it('creates a category and shows it to the product form immediately', async () => {
    const repository = createMemoryRepository();

    const result = await createCategory(repository, valid);

    assert.equal(result.ok, true);
    if (!result.ok) {
      return;
    }
    assert.equal(result.category.name, 'مانتو کتانی');
    assert.equal(result.category.slug, 'manto-ketani');
    assert.equal(result.category.description, 'کتانی و راحتی');

    const forProductForm = await repository.listCategories();
    assert.ok(forProductForm.some((category) => category.slug === 'manto-ketani'));

    const adminRows = await listCategoryAdminRows(repository);
    const row = adminRows.find((entry) => entry.slug === 'manto-ketani');
    assert.ok(row);
    assert.equal(row.productCount, 0, 'a new category holds no products yet');
  });

  it('trims the name and stores a blank description as NULL', async () => {
    const repository = createMemoryRepository();

    const result = await createCategory(repository, {
      name: '  دامن  ',
      slug: 'daman',
      description: '   ',
    });

    assert.equal(result.ok, true);
    if (!result.ok) {
      return;
    }
    assert.equal(result.category.name, 'دامن');
    assert.equal(result.category.description, null);
  });

  it('refuses a duplicate slug against the field, not as an unexpected error', async () => {
    const repository = createMemoryRepository({ categories: [{ id: 'cat-9', name: 'مانتو', slug: 'manto' }] });

    const result = await createCategory(repository, { ...valid, slug: 'manto' });

    assert.equal(result.ok, false);
    if (result.ok) {
      return;
    }
    assert.equal(result.code, 'CONFLICT');
    assert.equal(result.issues?.[0]?.field, 'slug');
    assert.match(result.message, /manto/);
    assert.equal((await repository.listCategories()).length, 1, 'nothing was written');
  });

  it('refuses a malformed slug, a short name and a parent category', async () => {
    const repository = createMemoryRepository();

    const badSlug = await createCategory(repository, { name: 'مانتو', slug: 'Manto Ketani' });
    assert.equal(badSlug.ok, false);
    if (!badSlug.ok) {
      assert.equal(badSlug.code, 'VALIDATION_ERROR');
      assert.equal(badSlug.issues?.[0]?.field, 'slug');
    }

    const shortName = await createCategory(repository, { name: 'م', slug: 'm' });
    assert.equal(shortName.ok, false);
    if (!shortName.ok) {
      assert.equal(shortName.issues?.[0]?.field, 'name');
    }

    const withParent = await createCategory(repository, {
      ...valid,
      slug: 'child',
      parentId: 'cat-1',
    });
    assert.equal(withParent.ok, false);
    if (!withParent.ok) {
      assert.equal(withParent.issues?.[0]?.field, 'parentId');
    }

    assert.equal((await repository.listCategories()).length, 2, 'only the seeded categories');
  });

  it('counts the products already attached to a category', async () => {
    const repository = createMemoryRepository({
      categories: [{ id: 'cat-1', name: 'مانتو', slug: 'manto' }],
      productGraphs: [
        {
          product: {
            categoryId: 'cat-1',
            title: 'مانتو کتان',
            slug: 'manto-katan',
            basePrice: 1_850_000,
            discountPrice: null,
            descriptionRaw: 'مانتو کتان جلو بسته',
            descriptionHtml: '<p>مانتو کتان جلو بسته</p>',
            fabricType: 'کتان',
            season: 'بهار',
            careInstructions: null,
            status: 'PUBLISHED',
          },
          variants: [
            {
              sku: 'MNT-KTN-BLK-M',
              colorName: 'مشکی',
              colorHex: '#111111',
              size: 'M',
              stockQuantity: 3,
              priceOverride: null,
            },
          ],
          images: [],
        },
      ],
    });

    const rows = await listCategoryAdminRows(repository);
    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.productCount, 1);
  });
});
