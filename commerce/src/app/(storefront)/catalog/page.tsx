import type { Metadata } from 'next';

import { CatalogBrowser } from '@/components/storefront/catalog-browser';
import { StorefrontUnavailable } from '@/components/storefront/storefront-unavailable';
import { Placeholder } from '@/components/ui/primitives';
import { getRepository } from '@/server/db-context';
import { listPublishedProducts, listStorefrontCategories } from '@/server/services/storefront';

/**
 * D-172 §3.2 — the catalog.
 *
 * The server reads the PUBLISHED cards and the category counts; the facets, the
 * search and the paging all run in the browser (`CatalogBrowser`), which is what
 * makes a filter instant. The only server-side input is `?category=`, used by the
 * homepage's category circles to open the catalog already narrowed.
 *
 * A category that matches nothing is NOT corrected or silently dropped: the
 * browser says nothing matched and offers to clear the filters, because quietly
 * showing the whole catalog would answer a question the customer did not ask.
 */

export const metadata: Metadata = {
  title: 'همهٔ محصولات',
  description: 'فیلتر محصولات بر پایهٔ اندازه، رنگ، محدودهٔ قیمت و موجودی.',
};

export const dynamic = 'force-dynamic';

function readCategory(value: string | string[] | undefined): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

export default async function CatalogPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const initialCategory = readCategory(params.category);

  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <h1 className="text-cp-display font-bold text-ink">همهٔ محصولات</h1>
        <div className="mt-4">
          <StorefrontUnavailable what="فهرست محصولات" />
        </div>
      </>
    );
  }

  const [cards, categories] = await Promise.all([
    listPublishedProducts(repository),
    listStorefrontCategories(repository),
  ]);

  return (
    <>
      <h1 className="text-cp-display font-bold text-ink">همهٔ محصولات</h1>
      <p className="mt-1 text-cp-label text-ink-muted">
        فیلترها بی‌درنگ روی محصولات منتشرشده اعمال می‌شوند؛ تعداد محصولات هر دسته از همین فهرست
        محاسبه شده است.
      </p>

      {cards.length === 0 ? (
        <div className="mt-6">
          <Placeholder>
            هنوز محصول منتشرشده‌ای وجود ندارد. محصول‌های پیش‌نویس در فروشگاه نمایش داده نمی‌شوند.
          </Placeholder>
        </div>
      ) : (
        <CatalogBrowser cards={cards} categories={categories} initialCategory={initialCategory} />
      )}
    </>
  );
}
