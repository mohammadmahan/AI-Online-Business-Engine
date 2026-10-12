import type {
  StorefrontProductCard,
  StorefrontProductDetail,
} from '@/contracts/storefront';

import type { CommerceRepository, StorefrontCategory } from '../repository';

/**
 * D-172 §3.1 — the storefront READ service (server half).
 *
 * Thin on purpose: the rules that decide what a customer may see live in the
 * repository's public read path (PUBLISHED only, no raw quantities, D-024 price
 * resolution) and in `@/lib/catalog-filters` (faceting/search, shared with the
 * browser). This module exists so a page never calls the repository directly for
 * storefront data — the same seam the admin pages use — and so the reads are
 * unit-testable against the in-memory double.
 *
 * Nothing here fabricates a fallback: an empty catalog is an empty array, which
 * the UI renders as an empty state, never as invented sample products.
 */

export async function listPublishedProducts(
  repo: CommerceRepository,
): Promise<StorefrontProductCard[]> {
  return repo.listStorefrontProducts();
}

export async function getPublishedProduct(
  repo: CommerceRepository,
  slug: string,
): Promise<StorefrontProductDetail | null> {
  return repo.getStorefrontProduct(slug.trim());
}

/** A rail, not a ranking claim: best sellers are ordered by quantity shipped. */
export async function listBestSellers(
  repo: CommerceRepository,
  limit = 4,
): Promise<StorefrontProductCard[]> {
  return repo.listBestSellers(limit);
}

/** Category chips with a count of PUBLISHED products only. */
export async function listStorefrontCategories(
  repo: CommerceRepository,
): Promise<StorefrontCategory[]> {
  return repo.listStorefrontCategories();
}
