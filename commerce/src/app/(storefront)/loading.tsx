import { ProductGridSkeleton } from '@/components/storefront/product-grid-skeleton';
import { Skeleton } from '@/components/ui/primitives';

/**
 * D-172 §3.3 — the storefront's loading state.
 *
 * The hero and the grid reserve their space while the server reads the catalog,
 * so the layout does not jump when the products arrive. Deliberately no spinner:
 * a spinner communicates \"something is happening\" and nothing about what.
 */
export default function StorefrontLoading() {
  return (
    <div>
      <Skeleton className="h-40 w-full" />
      <ProductGridSkeleton count={6} />
    </div>
  );
}
