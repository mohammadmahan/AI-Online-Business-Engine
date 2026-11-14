import { cn } from '@/lib/utils';

/**
 * D-172 §3.3 — the product grid's loading state.
 *
 * A skeleton rather than a spinner: it reserves the space the cards will occupy,
 * so the page does not jump when the data arrives. It is marked `aria-busy` and
 * carries a single Persian status line for assistive technology instead of
 * twenty invisible boxes.
 *
 * Phase 2B (D-177): the geometry is the EDITORIAL card's, not a generic square —
 * a 3:4 image block, caption, display-face title line, price line and stock line,
 * with the same `gap-x-6 gap-y-10` rhythm and no card chrome. A square skeleton
 * against a 3:4 card is a guaranteed layout shift on load, which is the defect
 * this shape prevents.
 */
/** One animated placeholder block on the storefront's muted token.
 * The shared panel Skeleton hard-codes the panel's cool muted fill; using it here
 * painted blue-grey blocks on the ivory page, so the catalog owns its own
 * primitive instead of fighting the panel's colour with a second class. */
function Block({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('block animate-pulse rounded-sf bg-sf-muted', className)}
    />
  );
}

export function ProductGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div aria-busy="true" className="mt-6">
      <p role="status" className="sr-only">
        در حال بارگذاری محصولات…
      </p>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-8 sm:gap-x-6 sm:gap-y-10 lg:grid-cols-3">
        {Array.from({ length: count }, (_, index) => (
          <li key={index} className="flex h-full flex-col">
            <Block className="aspect-[3/4] w-full" />
            <div className="flex flex-col gap-2 pt-4">
              <Block className="h-3 w-1/3" />
              <Block className="h-5 w-3/4" />
              <Block className="h-4 w-1/2" />
              <Block className="mt-2 h-3 w-2/3" />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
