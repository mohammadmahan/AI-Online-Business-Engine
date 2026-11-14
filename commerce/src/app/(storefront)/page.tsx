import type { Metadata } from 'next';
import Link from 'next/link';

import { ProductRail } from '@/components/storefront/product-rail';
import { SectionEyebrow, sfButton } from '@/components/storefront/storefront-primitives';
import { StorefrontUnavailable } from '@/components/storefront/storefront-unavailable';
import { formatCountFa } from '@/lib/format';
import {
  HOME_RAIL_SIZE,
  buildHomeCollections,
  categoryCircleHref,
} from '@/lib/storefront-home';
import { getRepository } from '@/server/db-context';
import {
  listBestSellers,
  listPublishedProducts,
  listStorefrontCategories,
} from '@/server/services/storefront';

/**
 * D-172 §3.1 — the storefront homepage.
 *
 * A server component: it reads the published catalog once and renders the hero,
 * the category circles and the rails. Every rail is derived from real data and
 * HIDES ITSELF when it has nothing to show:
 *
 *  - «جدیدها» is the newest published products (the read path's own order);
 *  - «پیشنهادهای تخفیف‌دار» are the published products that actually carry a
 *    discount price — a "featured" badge is never invented;
 *  - «پرفروش‌ها» is quantity shipped, cancelled orders excluded.
 *
 * With an empty catalog the page says so and offers nothing else, rather than
 * rendering rails of placeholders. With no configured connection it refuses to
 * render an empty shop at all (D-171 §2.2).
 *
 * Presentation is the editorial storefront system (D-172 §3): a full-bleed
 * masthead statement instead of a boxed admin card, hairline rules, and the
 * display face for headings. Copy, link labels and the data contract are
 * unchanged, so the storefront E2E script still drives the same page.
 */

export const metadata: Metadata = {
  // `absolute` on purpose: the root template would otherwise append the shop
  // name to the shop name and the tab would read «فروشگاه پوشاک · فروشگاه پوشاک».
  title: { absolute: 'فروشگاه پوشاک' },
  description: 'فهرست محصولات پوشاک، انتخاب رنگ و اندازه و تسویهٔ خرید.',
};

// A shop's front page is per-request by definition: stock and prices move.
export const dynamic = 'force-dynamic';

export default async function StorefrontHomePage() {
  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <StorefrontUnavailable what="فهرست محصولات" />
      </>
    );
  }

  const [cards, categories, bestSellers] = await Promise.all([
    listPublishedProducts(repository),
    listStorefrontCategories(repository),
    listBestSellers(repository, HOME_RAIL_SIZE),
  ]);

  const collections = buildHomeCollections({ cards, bestSellers });

  return (
    <>
      <section className="border-b border-sf-edge pb-12 pt-2 sm:pb-16 sm:pt-6">
        <SectionEyebrow>پوشاک زنانه — انتخاب رنگ و اندازه</SectionEyebrow>
        <h1 className="mt-5 max-w-4xl font-display text-sf-hero font-semibold leading-[1.12] text-sf-ink">
          اندازهٔ درست، رنگ دلخواه، سفارش در یک مرحله
        </h1>
        <p className="mt-6 max-w-2xl text-sf-body leading-relaxed text-sf-ink-muted">
          موجودی هر ترکیب رنگ و اندازه پیش از ثبت سفارش بررسی می‌شود و مبلغ نهایی روی سرور محاسبه
          می‌گردد. کد پستی و شمارهٔ تماس فقط برای همین سفارش استفاده می‌شود.
        </p>
        <p className="mt-8 flex flex-wrap items-center gap-3">
          <Link className={sfButton.primary} href="/catalog">
            دیدن همهٔ محصولات
          </Link>
          <Link className={sfButton.quiet} href="/checkout">
            تسویهٔ سبد خرید
          </Link>
        </p>
      </section>

      {collections.isEmpty ? (
        <div className="mt-12 border border-sf-edge bg-sf-surface p-6 text-sf-caption leading-relaxed text-sf-ink-muted">
          هنوز محصول منتشرشده‌ای در فروشگاه وجود ندارد. پس از انتشار محصول در پنل مدیریت، در همین صفحه
          نمایش داده می‌شود.
        </div>
      ) : (
        <>
          {categories.length > 0 ? (
            <section aria-labelledby="storefront-categories" className="mt-14">
              <h2
                id="storefront-categories"
                className="font-display text-sf-title font-semibold text-sf-ink"
              >
                دسته‌بندی‌ها
              </h2>
              <ul className="mt-6 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-5">
                {categories.map((category) => (
                  <li key={category.slug}>
                    <Link href={categoryCircleHref(category.name)} className="group block">
                      <span
                        aria-hidden="true"
                        className="mx-auto flex aspect-square w-full max-w-[8.5rem] flex-col items-center justify-center rounded-full border border-sf-edge bg-sf-surface transition-colors group-hover:bg-sf-muted"
                      >
                        <span className="font-display text-2xl font-semibold text-sf-ink">
                          {formatCountFa(category.productCount)}
                        </span>
                        <span className="mt-0.5 text-sf-caption text-sf-ink-muted">محصول</span>
                      </span>
                      <span className="mt-3 block text-center text-sf-caption font-medium text-sf-ink">
                        {category.name}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <ProductRail
            id="storefront-new-arrivals"
            title="جدیدها"
            description="تازه‌ترین محصولات منتشرشده در فروشگاه."
            cards={collections.newArrivals}
          />

          <ProductRail
            id="storefront-discounted"
            title="پیشنهادهای تخفیف‌دار"
            description="محصولاتی که قیمت تخفیف‌دار فعال دارند."
            cards={collections.discounted}
          />

          <ProductRail
            id="storefront-best-sellers"
            title="پرفروش‌ها"
            description="بر پایهٔ تعداد فروخته‌شده؛ سفارش‌های لغوشده حساب نمی‌شوند."
            cards={bestSellers}
          />

          <p className="mt-14">
            <Link className={sfButton.quiet} href="/catalog">
              دیدن همهٔ محصولات با فیلتر اندازه، رنگ و قیمت
            </Link>
          </p>
        </>
      )}
    </>
  );
}
