import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type {
  StockLevel,
  StorefrontProductDetail,
  StorefrontVariantView,
} from '@/contracts/storefront';
import { MAX_LINE_QUANTITY } from '@/lib/checkout-rules';
import { LOW_STOCK_THRESHOLD } from '@/lib/inventory-rules';
import {
  canAddVariant,
  colorOptions,
  defaultColor,
  findVariant,
  selectionCap,
  selectionGallery,
  selectionLevel,
  selectionPrice,
  sizeOptions,
  toCartLine,
} from '@/lib/variant-selection';

/**
 * D-172 §3.3 — the colour × size matrix rules.
 *
 * These are the decisions a customer sees and cannot debug: which colour opens,
 * which cells are disabled, what the badge claims before a size is picked, and
 * what quantity the cart line actually carries. They live in a pure module for
 * exactly this reason.
 */

function variant(overrides: Partial<StorefrontVariantView> = {}): StorefrontVariantView {
  return {
    variantId: 'v1',
    size: 'M',
    colorName: 'مشکی',
    colorHex: '#111111',
    level: 'IN',
    effectivePrice: 2_100_000,
    ...overrides,
  };
}

function product(overrides: Partial<StorefrontProductDetail> = {}): StorefrontProductDetail {
  return {
    id: 'p1',
    slug: 'manto-katan',
    title: 'مانتو کتان',
    categoryName: 'مانتو',
    basePrice: 2_450_000,
    discountPrice: 2_100_000,
    effectivePrice: 2_100_000,
    hasDiscount: true,
    primaryImageUrl: 'https://example.invalid/main.jpg',
    imageUrls: ['https://example.invalid/main.jpg'],
    sizes: ['S', 'M'],
    colors: [],
    availability: 'IN',
    createdAt: new Date('2026-10-01T00:00:00.000Z'),
    descriptionRaw: 'مانتو کتان.',
    descriptionHtml: '<p>مانتو کتان.</p>',
    fabricType: 'کتان',
    season: 'تابستان',
    careInstructions: null,
    images: [
      { url: 'https://example.invalid/main.jpg', variantId: null },
      { url: 'https://example.invalid/detail.jpg', variantId: null },
    ],
    variants: [variant()],
    ...overrides,
  };
}

describe('colour options (§3.3)', () => {
  it('keeps catalog order, deduplicates by name and marks a colour only when a cell is sellable', () => {
    const options = colorOptions([
      variant({ variantId: 'v1', colorName: 'مشکی' }),
      variant({ variantId: 'v2', colorName: 'مشکی', size: 'L' }),
      variant({ variantId: 'v3', colorName: 'سفید', colorHex: '#FFFFFF' }),
      variant({ variantId: 'v4', colorName: 'سبز', colorHex: '#00AA00', level: 'OUT' }),
    ]);

    assert.deepEqual(
      options.map((option) => option.name),
      ['مشکی', 'سفید', 'سبز'],
    );
    assert.equal(options[0]?.hex, '#111111');
    assert.equal(options[1]?.sellable, true);
    assert.equal(options[2]?.sellable, false, 'a colour with only OUT cells is not sellable');
  });

  it('marks a colour sellable when ANY of its sizes can be bought', () => {
    const options = colorOptions([
      variant({ variantId: 'v1', colorName: 'مشکی', size: 'S', level: 'OUT' }),
      variant({ variantId: 'v2', colorName: 'مشکی', size: 'M', level: 'LOW' }),
    ]);
    assert.equal(options[0]?.sellable, true);
  });

  it('has no options for a product with no variants', () => {
    assert.deepEqual(colorOptions([]), []);
    assert.equal(defaultColor([]), null);
  });
});

describe('the colour the page opens on (§3.3)', () => {
  it('preselects the first SELLABLE colour, not merely the first', () => {
    const variants = [
      variant({ variantId: 'v1', colorName: 'مشکی', level: 'OUT' }),
      variant({ variantId: 'v2', colorName: 'سفید', colorHex: '#FFFFFF', level: 'IN' }),
    ];
    assert.equal(defaultColor(variants), 'سفید');
  });

  it('falls back to the first colour when nothing is sellable, so a sold-out product still shows its selector', () => {
    const variants = [
      variant({ variantId: 'v1', colorName: 'مشکی', level: 'OUT' }),
      variant({ variantId: 'v2', colorName: 'سفید', colorHex: '#FFFFFF', level: 'OUT' }),
    ];
    assert.equal(defaultColor(variants), 'مشکی');
  });
});

describe('size cells (§3.3)', () => {
  it('lists every published size of the product and disables the cells this colour lacks', () => {
    const cells = sizeOptions(
      ['S', 'M', 'L'],
      [
        variant({ variantId: 'v-s', colorName: 'مشکی', size: 'S', level: 'IN' }),
        variant({ variantId: 'v-m', colorName: 'مشکی', size: 'M', level: 'OUT' }),
      ],
      'مشکی',
    );

    assert.deepEqual(
      cells.map((cell) => [cell.size, cell.variant?.variantId ?? null, cell.available]),
      [
        ['S', 'v-s', true],
        ['M', 'v-m', false],
        ['L', null, false],
      ],
      'L stays visible but disabled — the customer learns this colour has no L',
    );
  });

  it('finds the cell for a colour + size, and nothing for a half-finished selection', () => {
    const variants = [variant({ variantId: 'v1', colorName: 'مشکی', size: 'M' })];
    assert.equal(findVariant(variants, 'مشکی', 'M')?.variantId, 'v1');
    assert.equal(findVariant(variants, 'مشکی', 'L'), null);
    assert.equal(findVariant(variants, null, 'M'), null);
    assert.equal(findVariant(variants, 'مشکی', null), null);
  });
});

describe('the level the badge may claim (§3.3)', () => {
  const variants = [
    variant({ variantId: 'v1', colorName: 'مشکی', size: 'S', level: 'OUT' }),
    variant({ variantId: 'v2', colorName: 'مشکی', size: 'M', level: 'LOW' }),
    variant({ variantId: 'v3', colorName: 'سفید', colorHex: '#FFFFFF', size: 'M', level: 'OUT' }),
  ];

  it('answers with the chosen cell’s own level once a size is picked', () => {
    assert.equal(selectionLevel(variants, 'مشکی', 'M'), 'LOW');
    assert.equal(selectionLevel(variants, 'مشکی', 'S'), 'OUT');
  });

  it('answers about the colour as a whole before a size is picked', () => {
    assert.equal(selectionLevel(variants, 'مشکی', null), 'IN', 'that colour has a sellable cell');
    assert.equal(selectionLevel(variants, 'سفید', null), 'OUT', 'this one does not');
    assert.equal(selectionLevel(variants, null, null), 'OUT');
  });

  it('caps the quantity from the level: 0 for OUT, the low-stock threshold for LOW', () => {
    assert.equal(selectionCap('OUT' as StockLevel), 0);
    assert.equal(selectionCap('LOW'), LOW_STOCK_THRESHOLD);
    assert.equal(selectionCap('IN'), MAX_LINE_QUANTITY);
    assert.equal(canAddVariant(null), false);
    assert.equal(canAddVariant(variant({ level: 'OUT' })), false);
    assert.equal(canAddVariant(variant({ level: 'LOW' })), true);
  });
});

describe('gallery, price and the cart line (§3.3/§3.4)', () => {
  it('shows this colour’s photos first, unbound photos after, and the whole gallery when it has none', () => {
    const withBinding = product({
      images: [
        { url: 'bound-1.jpg', variantId: 'v2' },
        { url: 'unbound.jpg', variantId: null },
        { url: 'bound-other.jpg', variantId: 'v9' },
      ],
      variants: [variant({ variantId: 'v2' })],
    });
    assert.deepEqual(
      selectionGallery(withBinding, 'مشکی').map((image) => image.url),
      ['bound-1.jpg', 'unbound.jpg'],
    );

    const otherColourOnly = product({
      images: [
        { url: 'a.jpg', variantId: 'other-colour' },
        { url: 'b.jpg', variantId: 'other-colour' },
      ],
    });
    assert.deepEqual(
      selectionGallery(otherColourOnly, 'مشکی').map((image) => image.url),
      ['a.jpg', 'b.jpg'],
      'a colour with no photos of its own falls back to the whole gallery, never an empty viewer',
    );
  });

  it('prices the chosen cell, falling back to the product price', () => {
    const withOverride = product({
      variants: [variant({ variantId: 'v1', effectivePrice: 1_900_000 })],
    });
    assert.equal(selectionPrice(withOverride, findVariant(withOverride.variants, 'مشکی', 'M')), 1_900_000);
    assert.equal(selectionPrice(withOverride, null), withOverride.effectivePrice);
  });

  it('builds a cart line clamped to the level’s cap, never below one piece', () => {
    const target = product();
    const low = variant({ variantId: 'v-low', size: 'M', colorName: 'مشکی', level: 'LOW', effectivePrice: 2_100_000 });

    const line = toCartLine(target, low, MAX_LINE_QUANTITY);
    assert.deepEqual(line, {
      variantId: 'v-low',
      productSlug: 'manto-katan',
      productTitle: 'مانتو کتان',
      size: 'M',
      colorName: 'مشکی',
      colorHex: '#111111',
      unitPrice: 2_100_000,
      quantity: LOW_STOCK_THRESHOLD,
      imageUrl: 'https://example.invalid/main.jpg',
    });

    assert.equal(toCartLine(target, low, 0).quantity, 1, 'a nonsense quantity still buys one');
    assert.equal(toCartLine(target, low, 2.7).quantity, 2, 'fractions are truncated, not rounded up');
    assert.equal(
      toCartLine(target, variant({ level: 'IN' }), MAX_LINE_QUANTITY).quantity,
      MAX_LINE_QUANTITY,
    );
  });
});
