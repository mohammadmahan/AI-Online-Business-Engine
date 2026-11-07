import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { StorefrontProductCard } from '@/contracts/storefront';
import { EMPTY_CATALOG_FILTERS } from '@/contracts/storefront';
import {
  CATALOG_PAGE_SIZE,
  PRICE_SLIDER_STEP,
  applyFilters,
  countActiveFilters,
  deriveFacets,
  normaliseSearchText,
  paginate,
  priceStepFor,
  withCategory,
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

describe('price slider boundaries (§3.2)', () => {
  it('keeps the coarse step when the ceiling is a multiple of it', () => {
    assert.equal(PRICE_SLIDER_STEP, 50_000);
    assert.equal(priceStepFor(2_450_000), PRICE_SLIDER_STEP);
    assert.equal(priceStepFor(50_000), 50_000);
  });

  it('always lands exactly on a ceiling that does not divide the coarse step', () => {
    const ceiling = 2_449_000;
    const step = priceStepFor(ceiling);
    assert.ok(step > 0);
    assert.equal(ceiling % step, 0, 'the rail can reach the top product');
    assert.equal((ceiling / step) * step, ceiling);
    // The old fixed 50,000 step stopped at 2,400,000 and silently excluded the
    // most expensive product while the handle looked like it was at the end.
    assert.equal(ceiling % PRICE_SLIDER_STEP !== 0, true);
  });

  it('shrinks the step for a catalog cheaper than one coarse step', () => {
    // With min=0, max=30,000 and step=50,000 the ONLY reachable value is 0, so
    // any slider movement would filter the entire catalog out.
    const step = priceStepFor(30_000);
    assert.equal(step, 10_000);
    assert.equal(30_000 % step, 0);
    assert.ok(30_000 / step >= 1);
  });

  it('falls back to a single-unit step when there is no usable ceiling', () => {
    assert.equal(priceStepFor(0), 1);
    assert.equal(priceStepFor(-5), 1);
    assert.equal(priceStepFor(Number.POSITIVE_INFINITY), 1);
  });

  it('treats the bound itself as inside the range and the next Toman as outside', () => {
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, minPrice: 2_100_000 }).map((c) => c.slug),
      ['manto-katan'],
    );
    assert.deepEqual(applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, minPrice: 2_100_001 }), []);
    assert.deepEqual(
      applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, maxPrice: 1_200_000 }).map((c) => c.slug),
      ['shalvar-jean'],
    );
    assert.deepEqual(applyFilters(CATALOG, { ...EMPTY_CATALOG_FILTERS, maxPrice: 1_199_999 }), []);
  });
});

describe('category arriving from the URL (§3.2)', () => {
  it('replaces a stale category but keeps every other filter the customer set', () => {
    const filters = {
      ...EMPTY_CATALOG_FILTERS,
      category: 'مانتو',
      sizes: ['M'],
      colors: ['مشکی'],
      minPrice: 500_000,
      maxPrice: 2_000_000,
      onlyAvailable: true,
      query: 'کتان',
      sort: 'price-asc' as const,
    };

    const next = withCategory(filters, 'شلوار');

    assert.equal(next.category, 'شلوار', 'the URL wins over the previous selection');
    assert.deepEqual(next.sizes, ['M']);
    assert.deepEqual(next.colors, ['مشکی']);
    assert.equal(next.minPrice, 500_000);
    assert.equal(next.maxPrice, 2_000_000);
    assert.equal(next.onlyAvailable, true);
    assert.equal(next.query, 'کتان');
    assert.equal(next.sort, 'price-asc');
    assert.equal(filters.category, 'مانتو', 'the previous state is not mutated');
  });

  it('returns the same state when the category is unchanged or cleared', () => {
    const filters = { ...EMPTY_CATALOG_FILTERS, category: 'مانتو' };
    assert.equal(withCategory(filters, 'مانتو'), filters, 'no needless state churn');
    assert.equal(withCategory(filters, null).category, null);
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
