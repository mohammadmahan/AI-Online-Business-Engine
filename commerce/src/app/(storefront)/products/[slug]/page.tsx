import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ProductExperience } from '@/components/storefront/product-experience';
import { ProductRail } from '@/components/storefront/product-rail';
import { StorefrontUnavailable } from '@/components/storefront/storefront-unavailable';
import { getRepository } from '@/server/db-context';
import { getPublishedProduct, listPublishedProducts } from '@/server/services/storefront';

/**
 * D-172 §3.3 — the product detail page.
 *
 * The page itself is a server component: it resolves the product by slug and
 * renders the copy. The interactive part (gallery, colour × size matrix, stock
 * level, add to cart, size chart) is `ProductExperience`, the one client
 * component that owns the selection.
 *
 * Two deliberate choices:
 *
 *  - the DESCRIPTION is rendered from `descriptionRaw` as plain text (React
 *    escapes it), never from the `descriptionHtml` column, which is accepted
 *    verbatim from the merchant form and would need a sanitizer before it could
 *    be published to customers;
 *  - related products are the OTHER published products of the same category,
 *    computed from the same public read path — never a "you may also like"
 *    guess, and the rail hides itself when there is nothing to show.
 *
 * `generateMetadata` re-reads the product: one extra indexed lookup by slug for a
 * correct title, which is a trade this page accepts rather than shipping an
 * untitled product page.
 */

export const dynamic = 'force-dynamic';

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const repository = getRepository();
  if (repository === null) {
    return { title: 'صفحهٔ محصول' };
  }
  const product = await getPublishedProduct(repository, slug);
  if (product === null) {
    return { title: 'محصول پیدا نشد' };
  }
  return {
    title: product.title,
    description: product.descriptionRaw.replace(/\s+/g, ' ').trim().slice(0, 160),
  };
}

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <h1 className="text-cp-display font-bold text-ink">صفحهٔ محصول</h1>
        <div className="mt-4">
          <StorefrontUnavailable what="صفحهٔ محصول" />
        </div>
      </>
    );
  }

  const product = await getPublishedProduct(repository, slug);
  if (product === null) {
    notFound();
  }

  const cards = await listPublishedProducts(repository);
  const related = cards
    .filter((card) => card.categoryName === product.categoryName && card.slug !== product.slug)
    .slice(0, 4);

  const paragraphs = product.descriptionRaw
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter((paragraph) => paragraph.length > 0);

  return (
    <article>
      <nav aria-label="مسیر صفحه" className="text-cp-caption text-ink-muted">
        <Link href="/">خانه</Link>
        {' / '}
        <Link href="/catalog">همهٔ محصولات</Link>
        {' / '}
        <span>{product.title}</span>
      </nav>

      <header className="mt-2">
        <h1 className="text-cp-display font-bold text-ink">{product.title}</h1>
        <p className="mt-1 text-cp-label text-ink-muted">
          {product.categoryName} — پارچه: {product.fabricType} — فصل: {product.season}
        </p>
      </header>

      <ProductExperience product={product} />

      <section aria-labelledby="pdp-description" className="mt-10">
        <h2 id="pdp-description" className="text-cp-heading font-semibold text-ink">
          توضیحات
        </h2>
        {paragraphs.length === 0 ? (
          <p className="mt-2 text-cp-label text-ink-muted">برای این محصول توضیحی ثبت نشده است.</p>
        ) : (
          paragraphs.map((paragraph, index) => (
            <p
              key={index}
              className="mt-2 whitespace-pre-line text-cp-body text-ink"
            >
              {paragraph}
            </p>
          ))
        )}

        <dl className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-[--radius-cp] border border-edge bg-surface p-3">
            <dt className="text-cp-caption text-ink-muted">پارچه</dt>
            <dd className="text-cp-label text-ink">{product.fabricType}</dd>
          </div>
          <div className="rounded-[--radius-cp] border border-edge bg-surface p-3">
            <dt className="text-cp-caption text-ink-muted">فصل</dt>
            <dd className="text-cp-label text-ink">{product.season}</dd>
          </div>
          <div className="rounded-[--radius-cp] border border-edge bg-surface p-3">
            <dt className="text-cp-caption text-ink-muted">نگه‌داری و شست‌وشو</dt>
            <dd className="text-cp-label text-ink">
              {product.careInstructions ?? 'توضیحی ثبت نشده است.'}
            </dd>
          </div>
        </dl>
      </section>

      <ProductRail
        id="pdp-related"
        title="محصولات مرتبط"
        description={`محصولات منتشرشدهٔ دیگر در دستهٔ ${product.categoryName}.`}
        cards={related}
      />
    </article>
  );
}
