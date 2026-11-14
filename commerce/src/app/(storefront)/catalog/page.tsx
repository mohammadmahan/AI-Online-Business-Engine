import type { Metadata } from 'next';

import { CatalogBrowser } from '@/components/storefront/catalog-browser';
import { SectionEyebrow } from '@/components/storefront/storefront-primitives';
import { StorefrontUnavailable } from '@/components/storefront/storefront-unavailable';
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
 *
 * Phase 2B (D-177): the page header and empty state join the editorial layer —
 * eyebrow, display-face title, hairline rule and `--sf-*` spacing — so the
 * catalog reads as the same publication as the homepage and the drawer.
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
        <header className="border-b border-sf-edge pb-8">
          <SectionEyebrow>فروشگاه پوشاک · کاتالوگ</SectionEyebrow>
          <h1 className="mt-2 font-display text-sf-title font-semibold text-sf-ink">
            همهٔ محصولات
          </h1>
        </header>
        <div className="mt-8">
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
      <header className="border-b border-sf-edge pb-8">
        <SectionEyebrow>فروشگاه پوشاک · کاتالوگ</SectionEyebrow>
        <h1 className="mt-2 font-display text-sf-title font-semibold text-sf-ink">
          همهٔ محصولات
        </h1>
        <p className="mt-3 max-w-2xl text-sf-caption leading-relaxed text-sf-ink-muted">
          فیلترها بی‌درنگ روی محصولات منتشرشده اعمال می‌شوند؛ تعداد محصولات هر دسته از همین فهرست
          محاسبه شده است.
        </p>
      </header>

      {cards.length === 0 ? (
        <div className="mt-8 border border-sf-edge bg-sf-surface p-8">
          <p className="font-display text-xl font-semibold text-sf-ink">هنوز محصولی نیست</p>
          <p className="mt-2 max-w-md text-sf-caption leading-relaxed text-sf-ink-muted">
            هنوز محصول منتشرشده‌ای وجود ندارد. محصول‌های پیش‌نویس در فروشگاه نمایش داده نمی‌شوند.
          </p>
        </div>
      ) : (
        <CatalogBrowser cards={cards} categories={categories} initialCategory={initialCategory} />
      )}
    </>
  );
}
