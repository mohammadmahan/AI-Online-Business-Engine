import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { buildVariantMatrix } from '@/lib/variant-matrix';
import {
  MATRIX_MAX_ROWS,
  variantMatrixRequestSchema,
  variantRowSchema,
  variantRowsSchema,
} from '@/lib/variant-matrix-schema';

/** D-172 §2.1 — the Zod contract the generator and the submit path share. */
describe('variant matrix schema (§2.1)', () => {
  const valid = {
    skuPrefix: 'manto-keti',
    colors: [
      { name: 'مشکی', hex: '#111111' },
      { name: 'کرم', hex: '#f5f5dc' },
    ],
    sizes: ['36', '38', '40'],
    defaultStock: 4,
    defaultPriceOverride: 1_200_000,
  };

  it('accepts a well-formed selection and normalises the colour hex', () => {
    const parsed = variantMatrixRequestSchema.safeParse(valid);
    assert.equal(parsed.success, true);
    if (!parsed.success) return;
    assert.equal(parsed.data.colors[1]?.hex, '#F5F5DC');
    assert.equal(parsed.data.sizes.length, 3);
  });

  it('refuses an empty palette, an empty size range and a blank prefix', () => {
    const noColors = variantMatrixRequestSchema.safeParse({ ...valid, colors: [] });
    assert.equal(noColors.success, false);
    assert.equal(noColors.error?.issues[0]?.path.join('.'), 'colors');

    const noSizes = variantMatrixRequestSchema.safeParse({ ...valid, sizes: [] });
    assert.equal(noSizes.success, false);
    assert.equal(noSizes.error?.issues[0]?.path.join('.'), 'sizes');

    const noPrefix = variantMatrixRequestSchema.safeParse({ ...valid, skuPrefix: '   ' });
    assert.equal(noPrefix.success, false);
    assert.equal(noPrefix.error?.issues[0]?.path.join('.'), 'skuPrefix');
  });

  it('refuses a malformed colour hex instead of storing it', () => {
    for (const hex of ['111111', '#GGGGGG', '#12345', 'rgb(0,0,0)']) {
      const parsed = variantMatrixRequestSchema.safeParse({
        ...valid,
        colors: [{ name: 'مشکی', hex }],
      });
      assert.equal(parsed.success, false, `${hex} must be refused`);
      assert.equal(parsed.error?.issues[0]?.path.join('.'), 'colors.0.hex');
    }
  });

  it('refuses a duplicate colour name and a duplicate size', () => {
    const repeatedColor = variantMatrixRequestSchema.safeParse({
      ...valid,
      colors: [
        { name: 'مشکی', hex: '#111111' },
        { name: 'مشکی', hex: '#222222' },
      ],
    });
    assert.equal(repeatedColor.success, false);
    assert.equal(repeatedColor.error?.issues[0]?.path.join('.'), 'colors');

    const repeatedSize = variantMatrixRequestSchema.safeParse({ ...valid, sizes: ['38', '38'] });
    assert.equal(repeatedSize.success, false);
    assert.equal(repeatedSize.error?.issues[0]?.path.join('.'), 'sizes');
  });

  it('refuses a matrix above the row ceiling and accepts one exactly at it', () => {
    const colors = (count: number) =>
      Array.from({ length: count }, (_, index) => ({ name: `رنگ ${index}`, hex: '#111111' }));
    const sizes = (count: number) => Array.from({ length: count }, (_, index) => `${index}`);

    const over = variantMatrixRequestSchema.safeParse({
      ...valid,
      colors: colors(16),
      sizes: sizes(16),
    });
    assert.equal(over.success, false);
    assert.equal(over.error?.issues[0]?.path.join('.'), 'matrix');

    const atCeiling = variantMatrixRequestSchema.safeParse({
      ...valid,
      colors: colors(16),
      sizes: sizes(15),
    });
    assert.equal(atCeiling.success, true);
    assert.equal(16 * 15, MATRIX_MAX_ROWS);
  });

  it('refuses a negative or fractional stock and an out-of-range price override', () => {
    for (const defaultStock of [-1, 1.5, 1_000_001]) {
      const parsed = variantMatrixRequestSchema.safeParse({ ...valid, defaultStock });
      assert.equal(parsed.success, false, `stock ${defaultStock} must be refused`);
      assert.equal(parsed.error?.issues[0]?.path.join('.'), 'defaultStock');
    }
    for (const defaultPriceOverride of [-1, 1.5, 1_000_000_000_001]) {
      const parsed = variantMatrixRequestSchema.safeParse({ ...valid, defaultPriceOverride });
      assert.equal(parsed.success, false, `price ${defaultPriceOverride} must be refused`);
      assert.equal(parsed.error?.issues[0]?.path.join('.'), 'defaultPriceOverride');
    }
    // Null means "no override" and must stay accepted.
    assert.equal(
      variantMatrixRequestSchema.safeParse({ ...valid, defaultPriceOverride: null }).success,
      true,
    );
  });

  it('accepts every row the generator produces (contract parity)', () => {
    const parsed = variantMatrixRequestSchema.safeParse(valid);
    assert.equal(parsed.success, true);
    if (!parsed.success) return;

    const rows = buildVariantMatrix(parsed.data);
    assert.equal(rows.length, 6);
    for (const row of rows) {
      assert.equal(variantRowSchema.safeParse(row).success, true, `row ${row.sku} must validate`);
    }
    assert.equal(variantRowsSchema.safeParse(rows).success, true);
  });

  it('refuses duplicate SKUs and duplicate colour × size cells in a matrix', () => {
    const rows = [
      {
        sku: 'MANTO-38-1',
        colorName: 'مشکی',
        colorHex: '#111111',
        size: '38',
        stockQuantity: 1,
      },
    ];
    const duplicateSku = variantRowsSchema.safeParse([
      ...rows,
      { ...rows[0]!, colorName: 'کرم' },
    ]);
    assert.equal(duplicateSku.success, false);

    const duplicateCell = variantRowsSchema.safeParse([
      ...rows,
      { ...rows[0]!, sku: 'MANTO-38-2' },
    ]);
    assert.equal(duplicateCell.success, false);

    assert.equal(variantRowsSchema.safeParse(rows).success, true);
    assert.equal(variantRowsSchema.safeParse([]).success, false);
  });
});
