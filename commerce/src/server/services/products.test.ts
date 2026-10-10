import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { validProductPayload, variant } from '@/lib/validation.fixtures';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository, NewProductGraph } from '@/server/repository';
import { createProduct, listProducts } from '@/server/services/products';

/**
 * D-172 §2.1 — the ingestion WRITE, exercised against the deterministic memory
 * repository. A refusal must leave the catalog exactly as it was: no partial
 * product, no orphan variants (the single-transaction rule the Postgres
 * implementation carries via `db.transaction`).
 */

/** The memory repository plus a record of the graph the service handed it. */
function recordingRepository(): {
  repository: CommerceRepository;
  graphs: NewProductGraph[];
} {
  const inner = createMemoryRepository();
  const graphs: NewProductGraph[] = [];
  return {
    graphs,
    repository: {
      ...inner,
      async createProductGraph(graph) {
        graphs.push(graph);
        return inner.createProductGraph(graph);
      },
    },
  };
}

describe('product ingestion service (§2.1)', () => {
  it('persists the product with its whole matrix and media', async () => {
    const repository = createMemoryRepository();

    const result = await createProduct(
      repository,
      validProductPayload({
        images: [
          {
            storagePath: 'products/manto/1.jpg',
            publicUrl: 'https://cdn.example/manto/1.jpg',
            displayOrder: 0,
            isPrimary: true,
          },
          {
            storagePath: 'products/manto/2.jpg',
            publicUrl: 'https://cdn.example/manto/2.jpg',
            displayOrder: 1,
            isPrimary: false,
          },
        ],
      }),
    );

    assert.equal(result.ok, true);
    if (!result.ok) {
      return;
    }
    assert.equal(result.variantIds.length, 4);

    const products = await listProducts(repository);
    assert.equal(products.length, 1);
    assert.equal(products[0]?.variantCount, 4);
    assert.equal(products[0]?.imageCount, 2);
    assert.equal(products[0]?.basePrice, 1_250_000);
    assert.equal(products[0]?.status, 'DRAFT');

    const inventory = await repository.listInventory();
    assert.equal(inventory.length, 4);
    assert.equal(
      inventory.find((row) => row.sku === 'MANTO-KETI-38-1')?.priceOverride,
      1_200_000,
    );
    assert.equal(inventory.find((row) => row.sku === 'MANTO-KETI-38-2')?.stockQuantity, 0);
  });

  it('normalises SKUs and colour hex before they reach the database', async () => {
    const { repository, graphs } = recordingRepository();

    const result = await createProduct(
      repository,
      validProductPayload({
        variants: [variant({ sku: ' manto-keti-36-1 ', colorHex: '#f5f5dc', colorName: 'کرم' })],
      }),
    );

    assert.equal(result.ok, true);
    assert.equal(graphs.length, 1);
    assert.equal(graphs[0]?.variants[0]?.sku, 'MANTO-KETI-36-1');
    assert.equal(graphs[0]?.variants[0]?.colorHex, '#F5F5DC');
    assert.equal(graphs[0]?.variants[0]?.colorName, 'کرم');

    const [row] = await repository.listInventory();
    assert.equal(row?.sku, 'MANTO-KETI-36-1');
  });

  it('derives escaped HTML from the raw text when the AI copy is not available yet', async () => {
    const { repository, graphs } = recordingRepository();

    const result = await createProduct(
      repository,
      validProductPayload({ descriptionRaw: 'لنین درجه یک\n\n<b>دست‌دوز</b>' }),
    );

    assert.equal(result.ok, true);
    const html = graphs[0]?.product.descriptionHtml ?? '';
    assert.equal(html, '<p>لنین درجه یک</p><p>&lt;b&gt;دست‌دوز&lt;/b&gt;</p>');
    assert.equal(graphs[0]?.product.descriptionRaw, 'لنین درجه یک\n\n<b>دست‌دوز</b>');
  });

  it('keeps a merchant-supplied HTML body instead of regenerating it', async () => {
    const { repository, graphs } = recordingRepository();

    const result = await createProduct(
      repository,
      validProductPayload({ descriptionHtml: '<p>متن تأییدشده</p>' }),
    );

    assert.equal(result.ok, true);
    assert.equal(graphs[0]?.product.descriptionHtml, '<p>متن تأییدشده</p>');
  });

  it('flattens media order and marks the first image primary by default', async () => {
    const { repository, graphs } = recordingRepository();

    const result = await createProduct(
      repository,
      validProductPayload({
        images: [
          { storagePath: 'a/1.jpg', publicUrl: 'https://cdn.example/1.jpg' },
          { storagePath: 'a/2.jpg', publicUrl: 'https://cdn.example/2.jpg' },
        ],
      }),
    );

    assert.equal(result.ok, true);
    const images = graphs[0]?.images ?? [];
    assert.deepEqual(
      images.map((image) => [image.displayOrder, image.isPrimary, image.variantIndex]),
      [
        [0, true, null],
        [1, false, null],
      ],
    );
  });

  it('accepts a product with no images (§1.4 media is optional)', async () => {
    const repository = createMemoryRepository();

    const result = await createProduct(repository, validProductPayload({ images: [] }));

    assert.equal(result.ok, true);
    const products = await listProducts(repository);
    assert.equal(products[0]?.imageCount, 0);
  });

  it('refuses an invalid payload and writes nothing at all', async () => {
    const { repository, graphs } = recordingRepository();

    const result = await createProduct(repository, validProductPayload({ slug: 'غیرمجاز' }));

    assert.equal(result.ok, false);
    if (result.ok) {
      return;
    }
    assert.equal(result.code, 'VALIDATION_ERROR');
    assert.ok(result.issues.length > 0);
    assert.equal(graphs.length, 0);
    assert.deepEqual(await listProducts(repository), []);
    assert.deepEqual(await repository.listInventory(), []);
  });

  it('refuses a matrix whose SKUs collide rather than writing a partial graph', async () => {
    const { repository, graphs } = recordingRepository();

    const result = await createProduct(
      repository,
      validProductPayload({
        variants: [variant({ sku: 'DUPLICATE' }), variant({ size: '38', sku: 'DUPLICATE' })],
      }),
    );

    assert.equal(result.ok, false);
    assert.equal(graphs.length, 0);
    assert.deepEqual(await listProducts(repository), []);
  });
});
