import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { ProductRail } from '@/components/storefront/product-rail';
import type { StorefrontProductCard } from '@/contracts/storefront';
import { DOCUMENT_DIRECTION, DOCUMENT_LANGUAGE } from '@/lib/document';
import { HOME_RAIL_SIZE, buildHomeCollections, categoryCircleHref } from '@/lib/storefront-home';

/**
 * D-172 §3.1 — homepage collections.
 *
 * The page is a server component, so these tests assert the two halves that can
 * regress without a database: the collection rules (which cards land in which
 * rail, and when the page is empty) and the rendered rail markup (an empty rail
 * prints nothing; a populated one prints one link per product on a responsive
 * scroll-snap track).
 */

function card(overrides: Partial<StorefrontProductCard> = {}): StorefrontProductCard {
  return {
    id: 'p-1',
    slug: 'manto-keti',
    title: 'مانتو کتی',
    categoryName: 'مانتو',
    basePrice: 1_850_000,
    discountPrice: null,
    effectivePrice: 1_850_000,
    hasDiscount: false,
    primaryImageUrl: null,
    imageUrls: [],
    sizes: ['36', '38'],
    colors: [{ name: 'مشکی', hex: '#111111' }],
    availability: 'IN',
    createdAt: new Date('2026-10-01T00:00:00.000Z'),
    ...overrides,
  };
}

describe('homepage collections (§3.1)', () => {
  it('reports an empty catalog so the page shows a sentence, not rails', () => {
    const collections = buildHomeCollections({ cards: [], bestSellers: [] });

    assert.equal(collections.isEmpty, true);
    assert.deepEqual(collections.newArrivals, []);
    assert.deepEqual(collections.discounted, []);
    assert.deepEqual(collections.bestSellers, []);
  });

  it('caps every rail at the rail size and keeps the read order', () => {
    const cards = Array.from({ length: HOME_RAIL_SIZE + 3 }, (_, index) =>
      card({ id: `p-${index}`, slug: `product-${index}` }),
    );

    const collections = buildHomeCollections({ cards, bestSellers: cards.slice(0, 2) });

    assert.equal(collections.isEmpty, false);
    assert.equal(collections.newArrivals.length, HOME_RAIL_SIZE);
    assert.deepEqual(
      collections.newArrivals.map((entry) => entry.slug),
      ['product-0', 'product-1', 'product-2', 'product-3', 'product-4', 'product-5'],
    );
    // Best sellers keep the repository's own order; the module never re-sorts.
    assert.deepEqual(
      collections.bestSellers.map((entry) => entry.slug),
      ['product-0', 'product-1'],
    );
  });

  it('fills the discounted rail only from products that carry a discount', () => {
    const collections = buildHomeCollections({
      cards: [
        card({ id: 'a', slug: 'full-price' }),
        card({ id: 'b', slug: 'on-sale', hasDiscount: true, discountPrice: 1_400_000 }),
        card({ id: 'c', slug: 'also-sale', hasDiscount: true, discountPrice: 1_200_000 }),
      ],
      bestSellers: [],
    });

    assert.deepEqual(
      collections.discounted.map((entry) => entry.slug),
      ['on-sale', 'also-sale'],
    );
    // An all-full-price catalog yields an EMPTY discounted rail, not a fake one.
    const none = buildHomeCollections({ cards: [card()], bestSellers: [] });
    assert.deepEqual(none.discounted, []);
  });

  it('honours an explicit limit so a caller can size a rail differently', () => {
    const cards = Array.from({ length: 5 }, (_, index) => card({ id: `p-${index}` }));
    const collections = buildHomeCollections({ cards, bestSellers: cards, limit: 2 });

    assert.equal(collections.newArrivals.length, 2);
    assert.equal(collections.bestSellers.length, 2);
  });
});

describe('category circles (§3.1)', () => {
  it('links to the catalog filtered by the category name the filter reads', () => {
    assert.deepEqual(categoryCircleHref('مانتو'), {
      pathname: '/catalog',
      query: { category: 'مانتو' },
    });
    assert.deepEqual(categoryCircleHref('شلوار'), {
      pathname: '/catalog',
      query: { category: 'شلوار' },
    });
  });

  it('passes the raw name as a query VAL, so encoding is Next\u2019s job and cannot be doubled', () => {
    const href = categoryCircleHref('مانتو کتان & لنین');
    assert.equal(href.pathname, '/catalog');
    // The value reaches the router untouched; a hand-encoded value would be
    // encoded TWICE and the catalog would filter on a name nobody has.
    assert.equal(href.query.category, 'مانتو کتان & لنین');
  });

  it('trims surrounding whitespace and falls back to the whole catalog when blank', () => {
    assert.deepEqual(categoryCircleHref('  شومیز  '), categoryCircleHref('شومیز'));
    assert.deepEqual(categoryCircleHref('   '), { pathname: '/catalog', query: {} });
  });
});

describe('homepage rail rendering (§3.1)', () => {
  it('renders nothing at all for an empty collection', () => {
    const html = renderToStaticMarkup(
      createElement(ProductRail, { id: 'rail-empty', title: 'پرفروش‌ها', cards: [] }),
    );
    assert.equal(html, '', 'an empty rail must not print a heading');
  });

  it('renders the heading and one product link per card', () => {
    const html = renderToStaticMarkup(
      createElement(ProductRail, {
        id: 'rail-new',
        title: 'جدیدها',
        description: 'تازه‌ترین محصولات',
        cards: [card({ slug: 'first-one' }), card({ id: 'p-2', slug: 'second-one' })],
      }),
    );

    assert.ok(html.includes('جدیدها'));
    assert.ok(html.includes('id="rail-new"'), 'the heading is the section label');
    assert.ok(html.includes('/products/first-one'));
    assert.ok(html.includes('/products/second-one'));
    assert.equal(html.includes('/products/third-one'), false);
  });

  it('keeps the horizontal scroll-snap track responsive at both breakpoints', () => {
    const html = renderToStaticMarkup(
      createElement(ProductRail, { id: 'rail', title: 'جدیدها', cards: [card()] }),
    );

    assert.ok(html.includes('snap-x'), 'native scroll-snap, not a JS carousel');
    assert.ok(html.includes('overflow-x-auto'));
    assert.ok(html.includes('auto-cols-[minmax(13rem,1fr)]'), 'mobile card width');
    assert.ok(html.includes('sm:auto-cols-[minmax(16rem,1fr)]'), 'wider cards from the sm breakpoint');
  });
});

describe('document direction (§3.1)', () => {
  it('is a right-to-left Persian document', () => {
    assert.equal(DOCUMENT_LANGUAGE, 'fa');
    assert.equal(DOCUMENT_DIRECTION, 'rtl');
  });
});
