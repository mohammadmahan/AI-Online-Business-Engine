import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { StorefrontProductCard } from '@/contracts/storefront';
import { EMPTY_CATALOG_FILTERS } from '@/contracts/storefront';
import {
  CATALOG_PAGE_SIZE,
  applyFilters,
  countActiveFilters,
  deriveFacets,
  normaliseSearchText,
  paginate,
} from '@/lib/catalog-filters';

/**
 * D-172 §3.2 — faceting and instant filtering.
 *
 * Facets must be DERIVED from what is published (a filter that matches nothing
 * is worse than no filter), search must tolerate the Persian orthography a
 * customer actually types, and pagination must never claim there is more than
 * there is.
 */

function card(overrides: Partial<StorefrontProductCard> = {}): StorefrontProductCard {
  return {
    id: 'p1',
    slug: 'manto-katan',
    title: 'مانتو کتان تابستانی',
    categoryName: 'مانتو',
    basePrice: 2_450_000,
    discountPrice: 2_100_000,
    effectivePrice: 2_100_000,
    hasDiscount: true,
    primaryImageUrl: null,
    imageUrls: [],
    sizes: ['S', 'M'],
    colors: [{ name: 'مشکی', hex: '#111111' }],
    availability: 'IN',
    createdAt: new Date('2026-10-01T00:00:00.000Z'),
    ...overrides,
  };
}

const CATALOG = [
  card(),
  card({
    id: 'p2',
    slug: 'shalvar-jean',
    title: 'شلوار جین',
    categoryName: 'شلوار',
    sizes: ['M', 'L'],
    colors: [{ name: 'سرمه‌ای', hex: '#1E3A8A' }],
    effectivePrice: 1_200_000,
    discountPrice: null,
    hasDiscount: false,
    availability: 'OUT',
    createdAt: new Date('2026-10-05T00:00:00.000Z'),
  }),
];

describe('catalog facets (§3.2)', () => {
  it('derives sizes, colours and the price range from the published cards', () => {
    const facets = deriveFacets(CATALOG);
    assert.deepEqual(facets.sizes, ['S', 'M', 'L']);
    assert.deepEqual(facets.colors, [
      { name: 'مشکی', hex: '#111111' },
      { name: 'سرمه‌ای', hex: '#1E3A8A' },
    ]);
    assert.equal(facets.minPrice, 1_200_000);
    assert.equal(facets.maxPrice, 2_100_000);
  });

  it('reports an empty range for an empty catalog instead of inventing one', () => {
    assert.deepEqual(deriveFacets([]), { sizes: [], colors: [], minPrice: 0, maxPrice: 0 });
  });
});

describe('search normalisation (§3.2)', () => {
  it('treats Arabic yeh/kaf, zero-width joiners and case as the same text', () => {
    const typed = normaliseSearchText('مانتو علي');
    assert.equal(typed, normaliseSearchText('مانتو علی'));
    assert.equal(normaliseSearchText('Manto  Katan'), 'manto katan');
    assert.equal(normaliseSearchText('كتاب'), normaliseSearchText('کتاب'));
    assert.equal(normaliseSearchText('  '), '');
  });
});

describe('filtering (§3.2)', () => {
  it('returns everything, newest first, when nothing is selected', () => {
    const result = applyFilters(CATALOG, EMPTY_CATALOG_FILTERS);
    assert.deepEqual(
      result.map((entry) => entry.slug),
      ['shalvar-jean', 'manto-katan'],
    );
  });

  it('filters by size, colour, price and availability together', () => {
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, sizes: ['S'] }).map((c) => c.slug),
      ['manto-katan'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, colors: ['سرمه‌ای'] }).map((c) => c.slug),
      ['shalvar-jean'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, maxPrice: 1_500_000 }).map((c) => c.slug),
      ['shalvar-jean'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, onlyAvailable: true }).map((c) => c.slug),
      ['manto-katan'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, {
        ...EMPTY_CATALOG_FILTERS,
        sizes: ['S'],
        onlyAvailable: true,
      }).map((c) => c.slug),
      ['manto-katan'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, sizes: ['L'], onlyAvailable: true }),
      [],
      'a combination that matches nothing yields nothing, not everything',
    );
  });

  it('filters by category name, exactly as the published card reports it', () => {
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, category: 'شلوار' }).map((c) => c.slug),
      ['shalvar-jean'],
    );
    // A category that exists on no PUBLISHED product selects nothing.
    assert.deepEqual(applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, category: 'کیف' }), []);
    // Combined with a size that category does not carry: still nothing.
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, category: 'شلوار', sizes: ['S'] }),
      [],
    );
    assert.equal(
      countActiveFilters({ ...EMPTY_CATALOG_FILTERS, category: 'شلوار' }),
      1,
      'the selected category counts as one active filter',
    );
  });

  it('searches the title and category, and sorts by price on request', () => {
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, query: 'جین' }).map((c) => c.slug),
      ['shalvar-jean'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, query: 'مانتو' }).map((c) => c.slug),
      ['manto-katan'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, query: 'پیراهن' }),
      [],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, sort: 'price-asc' }).map((c) => c.slug),
      ['shalvar-jean', 'manto-katan'],
    );
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, sort: 'price-desc' }).map((c) => c.slug),
      ['manto-katan', 'shalvar-jean'],
    );
  });

  it('counts only the filters that are actually set', () => {
    assert.equal(countActiveFilters(EMPTY_CATALOG_FILTERS), 0);
    assert.equal(
      countActiveFilters({
        ...EMPTY_CATALOG_FILTERS,
        sizes: ['M'],
        colors: ['مشکی'],
        maxPrice: 2_000_000,
        onlyAvailable: true,
        query: 'مانتو',
      }),
      5,
    );
  });
});

describe('pagination (§3.2)', () => {
  it('grows a page at a time and stops advertising more once exhausted', () => {
    const items = Array.from({ length: 10 }, (_, index) => index);
    const first = paginate(items, 1, 4);
    assert.deepEqual(first.items, [0, 1, 2, 3]);
    assert.equal(first.hasMore, true);
    assert.equal(first.total, 10);

    const last = paginate(items, 3, 4);
    assert.deepEqual(last.items, items);
    assert.equal(last.hasMore, false);
  });

  it('treats a nonsense page number as the first page', () => {
    assert.equal(paginate([1, 2, 3], 0, 2).page, 1);
    assert.equal(paginate([1, 2, 3], -5, 2).page, 1);
    assert.equal(CATALOG_PAGE_SIZE, 9);
  });
});
