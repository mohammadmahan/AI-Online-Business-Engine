import type { Metadata } from 'next';
import Link from 'next/link';

import { ProductRail } from '@/components/storefront/product-rail';
import { StorefrontUnavailable } from '@/components/storefront/storefront-unavailable';
import { Placeholder, buttonClass } from '@/components/ui/primitives';
import { formatCountFa } from '@/lib/format';
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
 */

export const metadata: Metadata = {
  title: 'فروشگاه پوشاک',
  description: 'فهرست محصولات پوشاک، انتخاب رنگ و اندازه و تسویهٔ خرید.',
};

// A shop's front page is per-request by definition: stock and prices move.
export const dynamic = 'force-dynamic';

const RAIL_SIZE = 6;

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
    listBestSellers(repository, RAIL_SIZE),
  ]);

  const newArrivals = cards.slice(0, RAIL_SIZE);
  const discounted = cards.filter((card) => card.hasDiscount).slice(0, RAIL_SIZE);

  return (
    <>
      <section className="rounded-[--radius-cp] border border-edge bg-surface p-6 sm:p-10">
        <p className="text-cp-caption text-ink-muted">پوشاک زنانه — انتخاب رنگ و اندازه</p>
        <h1 className="mt-2 text-cp-display font-bold text-ink">
          اندازهٔ درست، رنگ دلخواه، سفارش در یک مرحله
        </h1>
        <p className="mt-3 max-w-2xl text-cp-body text-ink-muted">
          موجودی هر ترکیب رنگ و اندازه پیش از ثبت سفارش بررسی می‌شود و مبلغ نهایی روی سرور محاسبه
          می‌گردد. کد پستی و شمارهٔ تماس فقط برای همین سفارش استفاده می‌شود.
        </p>
        <p className="mt-5 flex flex-wrap gap-2">
          <Link className={buttonClass.primary} href="/catalog">
            دیدن همهٔ محصولات
          </Link>
          <Link className={buttonClass.neutral} href="/checkout">
            تسویهٔ سبد خرید
          </Link>
        </p>
      </section>

      {cards.length === 0 ? (
        <div className="mt-8">
          <Placeholder>
            هنوز محصول منتشرشده‌ای در فروشگاه وجود ندارد. پس از انتشار محصول در پنل مدیریت، در همین
            صفحه نمایش داده می‌شود.
          </Placeholder>
        </div>
      ) : (
        <>
          {categories.length > 0 ? (
            <section aria-labelledby="storefront-categories" className="mt-8">
              <h2 id="storefront-categories" className="text-cp-heading font-semibold text-ink">
                دسته‌بندی‌ها
              </h2>
              <ul className="mt-4 flex flex-wrap gap-6">
                {categories.map((category) => (
                  <li key={category.slug}>
                    <Link
                      href={{ pathname: '/catalog', query: { category: category.name } }}
                      className="flex w-28 flex-col items-center gap-2 text-center"
                    >
                      <span
                        aria-hidden="true"
                        className="flex size-24 flex-col items-center justify-center rounded-full border-2 border-primary bg-surface-muted"
                      >
                        <span className="text-cp-heading font-bold text-ink">
                          {formatCountFa(category.productCount)}
                        </span>
                        <span className="text-cp-caption text-ink-muted">محصول</span>
                      </span>
                      <span className="text-cp-label font-medium text-ink">{category.name}</span>
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
            cards={newArrivals}
          />

          <ProductRail
            id="storefront-discounted"
            title="پیشنهادهای تخفیف‌دار"
            description="محصولاتی که قیمت تخفیف‌دار فعال دارند."
            cards={discounted}
          />

          <ProductRail
            id="storefront-best-sellers"
            title="پرفروش‌ها"
            description="بر پایهٔ تعداد فروخته‌شده؛ سفارش‌های لغوشده حساب نمی‌شوند."
            cards={bestSellers}
          />

          <p className="mt-10">
            <Link className={buttonClass.neutral} href="/catalog">
              دیدن همهٔ محصولات با فیلتر اندازه، رنگ و قیمت
            </Link>
          </p>
        </>
      )}
    </>
  );
}
