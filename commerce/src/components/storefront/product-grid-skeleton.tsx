import { Skeleton } from '@/components/ui/primitives';

/**
 * D-172 §3.3 — the product grid's loading state.
 *
 * A skeleton rather than a spinner: it reserves the space the cards will occupy,
 * so the page does not jump when the data arrives. It is marked `aria-busy` and
 * carries a single Persian status line for assistive technology instead of
 * twenty invisible boxes.
 */
export function ProductGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div aria-busy="true" className="mt-6">
      <p role="status" className="sr-only">
        در حال بارگذاری محصولات…
      </p>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: count }, (_, index) => (
          <li key={index} className="flex flex-col gap-2 rounded-[--radius-cp] border border-edge bg-surface p-3">
            <Skeleton className="aspect-square w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/3" />
            <Skeleton className="h-4 w-1/2" />
          </li>
        ))}
      </ul>
    </div>
  );
}
