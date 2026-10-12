import type {
  CatalogFilters,
  ColorSwatch,
  StorefrontProductCard,
} from '@/contracts/storefront';

/**
 * D-172 §3.2 — catalog faceting, filtering and pagination, as a PURE module.
 *
 * The storefront renders the PUBLISHED catalog on the server and hands the
 * cards to this module in the browser, so filtering is instant and never costs
 * a page reload (the roadmap's requirement for §3.2). One definition means the
 * facet counts the customer sees and the filter that runs are the same code.
 *
 * Nothing is fabricated: the facets are DERIVED from the products that are
 * actually published, so a size that no published product carries never appears
 * as a filter, and an empty facet list means the catalog is empty rather than
 * "no data yet".
 */

export const CATALOG_PAGE_SIZE = 9;

export interface CatalogFacets {
  sizes: string[];
  colors: ColorSwatch[];
  minPrice: number;
  maxPrice: number;
}

/**
 * Persian/Arabic text normalisation for search: the same product must match
 * whether the customer types «مانتو» or «مانتو» with an Arabic yeh/kaf, and
 * regardless of extra spaces. Case folding matters for the Latin part of a
 * title ("Manto" vs "manto").
 */
export function normaliseSearchText(input: string): string {
  return input
    .replace(/[\u064A\u0649]/g, '\u06CC') // Arabic yeh → Persian yeh
    .replace(/\u0643/g, '\u06A9') // Arabic kaf → Persian kaf
    .replace(/[\u200C\u200F\u200E]/g, ' ') // zero-width joiners/marks → space
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

function intersects(left: string[], right: string[]): boolean {
  return left.some((value) => right.includes(value));
}

/**
 * Garment sizes in the order a customer reads them.
 *
 * Sorting sizes alphabetically puts «L» before «M» — and a boutique's sizes are
 * not text, they are a scale. Anything numeric (38, 40, 42) sorts by value after
 * the lettered sizes, and an unrecognised label keeps its place at the end
 * rather than being dropped: a size that exists in the catalog is never hidden
 * from the customer just because this list has not heard of it.
 */
const LETTERED_SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL'];

export function sortSizes(sizes: string[]): string[] {
  const rank = (size: string): [number, number, string] => {
    const lettered = LETTERED_SIZE_ORDER.indexOf(size.trim().toUpperCase());
    if (lettered >= 0) {
      return [0, lettered, size];
    }
    const numeric = Number(size.trim());
    if (Number.isFinite(numeric)) {
      return [1, numeric, size];
    }
    return [2, 0, size];
  };

  return [...sizes].sort((left, right) => {
    const a = rank(left);
    const b = rank(right);
    if (a[0] !== b[0]) {
      return a[0] - b[0];
    }
    if (a[1] !== b[1]) {
      return a[1] - b[1];
    }
    return a[2].localeCompare(b[2], 'fa');
  });
}

/** Facets present in the published catalog, in a stable order. */
export function deriveFacets(cards: StorefrontProductCard[]): CatalogFacets {
  const sizes = new Set<string>();
  const colors = new Map<string, string>();
  let minPrice = Number.POSITIVE_INFINITY;
  let maxPrice = 0;

  for (const card of cards) {
    for (const size of card.sizes) {
      sizes.add(size);
    }
    for (const color of card.colors) {
      colors.set(color.name, color.hex);
    }
    minPrice = Math.min(minPrice, card.effectivePrice);
    maxPrice = Math.max(maxPrice, card.effectivePrice);
  }

  return {
    sizes: sortSizes([...sizes]),
    colors: [...colors.entries()].map(([name, hex]) => ({ name, hex })),
    minPrice: Number.isFinite(minPrice) ? minPrice : 0,
    maxPrice,
  };
}

export function countActiveFilters(filters: CatalogFilters): number {
  return (
    (filters.category === null ? 0 : 1) +
    filters.sizes.length +
    filters.colors.length +
    (filters.minPrice === null ? 0 : 1) +
    (filters.maxPrice === null ? 0 : 1) +
    (filters.onlyAvailable ? 1 : 0) +
    (filters.query.trim().length > 0 ? 1 : 0)
  );
}

export function applyFilters(
  cards: StorefrontProductCard[],
  filters: CatalogFilters,
): StorefrontProductCard[] {
  const query = normaliseSearchText(filters.query);

  const filtered = cards.filter((card) => {
    if (filters.category !== null && card.categoryName !== filters.category) {
      return false;
    }
    if (filters.sizes.length > 0 && !intersects(card.sizes, filters.sizes)) {
      return false;
    }
    if (
      filters.colors.length > 0 &&
      !intersects(
        card.colors.map((color) => color.name),
        filters.colors,
      )
    ) {
      return false;
    }
    if (filters.minPrice !== null && card.effectivePrice < filters.minPrice) {
      return false;
    }
    if (filters.maxPrice !== null && card.effectivePrice > filters.maxPrice) {
      return false;
    }
    if (filters.onlyAvailable && card.availability !== 'IN') {
      return false;
    }
    if (query.length > 0) {
      const haystack = normaliseSearchText(`${card.title} ${card.categoryName}`);
      if (!haystack.includes(query)) {
        return false;
      }
    }
    return true;
  });

  return [...filtered].sort((left, right) => {
    switch (filters.sort) {
      case 'price-asc':
        return left.effectivePrice - right.effectivePrice;
      case 'price-desc':
        return right.effectivePrice - left.effectivePrice;
      case 'newest':
      default:
        return right.createdAt.getTime() - left.createdAt.getTime();
    }
  });
}

/**
 * Responsive pagination. Chosen over scroll-triggered infinite loading on
 * purpose: a button works with a keyboard, a screen reader and an interrupted
 * network, and it makes the "there is more" state explicit instead of implied
 * by a scroll position (§3.2 allows either).
 */
export function paginate<T>(
  items: T[],
  page: number,
  pageSize = CATALOG_PAGE_SIZE,
): { items: T[]; hasMore: boolean; total: number; page: number } {
  const safePage = Number.isInteger(page) && page > 0 ? page : 1;
  const end = safePage * pageSize;
  return {
    items: items.slice(0, end),
    hasMore: items.length > end,
    total: items.length,
    page: safePage,
  };
}
