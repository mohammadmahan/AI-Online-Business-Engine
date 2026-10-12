import { Skeleton } from '@/components/ui/primitives';

/**
 * D-172 §3.3 — the product page's loading state.
 *
 * Two columns, mirroring the real layout: the gallery square on one side and the
 * price, badge and selector blocks on the other. The skeleton keeps the page from
 * reflowing when the product arrives.
 */
export default function ProductLoading() {
  return (
    <div aria-busy="true">
      <p role="status" className="sr-only">
        در حال بارگذاری صفحهٔ محصول…
      </p>
      <Skeleton className="h-4 w-64" />
      <Skeleton className="mt-3 h-10 w-2/3" />
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Skeleton className="aspect-square w-full" />
        <div className="flex flex-col gap-3">
          <Skeleton className="h-8 w-1/2" />
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-12 w-1/2" />
        </div>
      </div>
    </div>
  );
}
