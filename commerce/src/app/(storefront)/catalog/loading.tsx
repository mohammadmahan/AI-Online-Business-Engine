import { CatalogPageHeader } from '@/components/storefront/catalog-page-header';
import { ProductGridSkeleton } from '@/components/storefront/product-grid-skeleton';

/**
 * D-177 Phase 3 — the catalog's route-level loading state.
 *
 * The static header is shared with the page, so the display type and hairline
 * rule do not move when the data arrives. The filter rail's geometry is reserved
 * on desktop (so the grid does not jump from full-width to beside a rail) and the
 * phone disclosure's 44px row is reserved too. The skeleton shows three cards,
 * the seeded first screen, and `ProductGridSkeleton` keeps the editorial 3:4
 * card shape.
 *
 * The animation is disabled under `prefers-reduced-motion` both here and in the
 * skeleton's blocks. The visible status line is the only live announcement;
 * `announce={false}` prevents a second announcement from the grid.
 */
export default function CatalogLoading() {
  return (
    <div aria-busy="true">
      <CatalogPageHeader />

      <div className="mt-10 flex flex-col gap-8 lg:flex-row lg:items-start">
        <div className="flex flex-wrap items-center gap-3 lg:hidden" aria-hidden="true">
          <span className="h-11 flex-1 rounded-sf border border-sf-edge-strong" />
        </div>

        <div
          aria-hidden="true"
          className="hidden w-80 shrink-0 flex-col gap-6 rounded-sf border border-sf-edge bg-sf-surface p-5 lg:flex lg:min-h-[61rem]"
        >
          <span className="block h-9 animate-pulse rounded-sf bg-sf-muted motion-reduce:animate-none" />
          <span className="block h-11 animate-pulse rounded-sf bg-sf-muted motion-reduce:animate-none" />
          <span className="block h-5 w-2/3 animate-pulse rounded-sf bg-sf-muted motion-reduce:animate-none" />
          <span className="block h-11 animate-pulse rounded-sf bg-sf-muted motion-reduce:animate-none" />
          <span className="block h-11 w-11 animate-pulse rounded-sf bg-sf-muted motion-reduce:animate-none" />
        </div>

        <div className="min-w-0 flex-1">
          <p role="status" className="text-sf-caption text-sf-ink-muted">
            در حال بارگذاری محصولات…
          </p>
          <ProductGridSkeleton count={3} announce={false} />
        </div>
      </div>
    </div>
  );
}