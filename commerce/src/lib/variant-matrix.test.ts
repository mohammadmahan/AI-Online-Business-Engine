import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  MATRIX_MAX_ROWS,
  buildVariantMatrix,
  toDescriptionHtml,
  validateMatrixRequest,
} from '@/lib/variant-matrix';

/** D-172 §2.1 — the cartesian product the merchant reviews before submitting. */
describe('variant matrix (§2.1)', () => {
  const request = {
    skuPrefix: 'manto keti',
    colors: [
      { name: 'مشکی', hex: '#111111' },
      { name: 'کرم', hex: '#F5F5DC' },
    ],
    sizes: ['36', '38', '40'],
    defaultStock: 4,
    defaultPriceOverride: 1_200_000,
  };

  it('produces one row per colour × size pair', () => {
    const rows = buildVariantMatrix(request);
    assert.equal(rows.length, 6);
    assert.deepEqual(
      rows.map((row) => `${row.colorName}/${row.size}`),
      ['مشکی/36', 'مشکی/38', 'مشکی/40', 'کرم/36', 'کرم/38', 'کرم/40'],
    );
  });

  it('proposes a normalised, unique SKU per row', () => {
    const rows = buildVariantMatrix(request);
    const skus = rows.map((row) => row.sku);
    assert.equal(new Set(skus).size, skus.length);
    assert.equal(skus[0], 'MANTO-KETI-36-1');
    assert.equal(skus[5], 'MANTO-KETI-40-2');
  });

  it('carries the defaults into every row and normalises the colour hex', () => {
    const rows = buildVariantMatrix({ ...request, sizes: ['FreeSize'] });
    assert.equal(rows[0]?.stockQuantity, 4);
    assert.equal(rows[0]?.priceOverride, 1_200_000);
    assert.equal(rows[0]?.sku, 'MANTO-KETI-FREESIZE-1');
  });

  it('defaults to zero stock and no price override', () => {
    const rows = buildVariantMatrix({
      skuPrefix: request.skuPrefix,
      colors: request.colors,
      sizes: ['38'],
    });
    assert.equal(rows[0]?.stockQuantity, 0);
    assert.equal(rows[0]?.priceOverride, null);
  });

  it('refuses an empty selection, a missing prefix and an oversized matrix', () => {
    assert.equal(validateMatrixRequest({ ...request, colors: [] }).length, 1);
    assert.equal(validateMatrixRequest({ ...request, sizes: [] }).length, 1);
    assert.equal(validateMatrixRequest({ ...request, skuPrefix: '  ' }).length, 1);

    const oversized = {
      ...request,
      colors: Array.from({ length: 16 }, (_, index) => ({
        name: `رنگ ${index}`,
        hex: '#111111',
      })),
      sizes: Array.from({ length: 16 }, (_, index) => `${index}`),
    };
    const issues = validateMatrixRequest(oversized);
    assert.equal(issues.length, 1);
    assert.equal(issues[0]?.field, 'matrix');
    assert.ok(oversized.colors.length * oversized.sizes.length > MATRIX_MAX_ROWS);
  });

  it('accepts a matrix exactly at the row ceiling', () => {
    const atCeiling = {
      ...request,
      colors: Array.from({ length: 16 }, (_, index) => ({ name: `رنگ ${index}`, hex: '#111111' })),
      sizes: Array.from({ length: 15 }, (_, index) => `${index}`),
    };
    assert.deepEqual(validateMatrixRequest(atCeiling), []);
  });

  it('escapes merchant text before it becomes HTML', () => {
    const html = toDescriptionHtml('لنین درجه یک\n\n<script>alert(1)</script>');
    assert.equal(
      html,
      '<p>لنین درجه یک</p><p>&lt;script&gt;alert(1)&lt;/script&gt;</p>',
    );
  });
});
