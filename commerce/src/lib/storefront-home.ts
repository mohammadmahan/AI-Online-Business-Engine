import type { StorefrontProductCard } from '@/contracts/storefront';

/**
 * D-172 §3.1 — homepage collection rules, as a PURE module.
 *
 * The homepage is a server component, so its decisions have to be testable
 * without a database, a request or a browser. Three facts live here:
 *
 *  1. WHICH products each rail shows. «جدیدها» is the newest published products
 *     (the read path's order, truncated); «پیشنهادهای تخفیف‌دار» are the products
 *     that actually carry a discount — a "featured" badge is never invented; the
 *     best-seller list arrives pre-ordered from the repository because it is the
 *     only rail whose order comes from shipped quantities.
 *  2. WHEN the page is empty. An empty published catalog renders one honest
 *     sentence, not three rails of placeholders, so `isEmpty` is derived here
 *     rather than re-tested in the JSX.
 *  3. WHERE a category circle links. The catalog filters by the category NAME
 *     (that is what its filter reads). The target is returned as a `UrlObject`
 *     rather than a hand-built query string: the app uses typed routes, and Next
 *     serialises and encodes the query, so a Persian name with a space cannot
 *     break the URL and the link stays type-checked.
 */

/** Cards per rail. Six fits one screen of the horizontal track at every width. */
export const HOME_RAIL_SIZE = 6;

export interface HomeCollections {
  newArrivals: StorefrontProductCard[];
  discounted: StorefrontProductCard[];
  bestSellers: StorefrontProductCard[];
  /** No published product at all: the page shows its empty state, not rails. */
  isEmpty: boolean;
}

export function buildHomeCollections(input: {
  cards: StorefrontProductCard[];
  bestSellers: StorefrontProductCard[];
  limit?: number;
}): HomeCollections {
  const limit = input.limit ?? HOME_RAIL_SIZE;
  return {
    newArrivals: input.cards.slice(0, limit),
    discounted: input.cards.filter((card) => card.hasDiscount).slice(0, limit),
    bestSellers: input.bestSellers.slice(0, limit),
    isEmpty: input.cards.length === 0,
  };
}

export interface CategoryCircleHref {
  pathname: '/catalog';
  /** Absent for a blank name — that links to the whole catalog, unfiltered. */
  query: { category?: string };
}

/**
 * A category circle's target. A blank name is not a filter — it links to the
 * whole catalog rather than to `?category=` (which would filter everything out).
 */
export function categoryCircleHref(name: string): CategoryCircleHref {
  const trimmed = name.trim();
  return {
    pathname: '/catalog',
    query: trimmed.length === 0 ? {} : { category: trimmed },
  };
}
