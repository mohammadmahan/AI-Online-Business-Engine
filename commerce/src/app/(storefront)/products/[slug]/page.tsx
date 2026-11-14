import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ProductExperience } from '@/components/storefront/product-experience';
import { ProductRail } from '@/components/storefront/product-rail';
import { SectionEyebrow } from '@/components/storefront/storefront-primitives';
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
 *
 * Phase 2C (D-177): the shell is editorial — link breadcrumb, eyebrow, display
 * face, hairline section rules and prose/spacing on the `--sf-*` layer. The
 * purchase controls still come BEFORE the long description in document order, so
 * a phone does not have to scroll through the story to reach the CTA.
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
    // Resolve the missing product BEFORE streaming starts. Returning a title
    // alone lets the loading boundary flush a 200 shell, producing a soft 404.
    notFound();
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
        <header className="border-b border-sf-edge pb-8">
          <SectionEyebrow>فروشگاه پوشاک · محصول</SectionEyebrow>
          <h1 className="mt-2 font-display text-sf-title font-semibold text-sf-ink">
            صفحهٔ محصول
          </h1>
        </header>
        <div className="mt-8">
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
      <nav aria-label="مسیر صفحه" className="text-sf-caption text-sf-ink-muted">
        <Link href="/" className="sf-link">
          خانه
        </Link>
        <span aria-hidden="true"> / </span>
        <Link href="/catalog" className="sf-link">
          همهٔ محصولات
        </Link>
        <span aria-hidden="true"> / </span>
        <span className="text-sf-ink">{product.title}</span>
      </nav>

      <header className="mt-6 border-b border-sf-edge pb-8">
        <SectionEyebrow>
          {product.categoryName} · {product.fabricType} · {product.season}
        </SectionEyebrow>
        <h1 className="mt-3 max-w-3xl font-display text-sf-title font-semibold leading-tight text-sf-ink">
          {product.title}
        </h1>
      </header>

      <ProductExperience product={product} />

      <section aria-labelledby="pdp-description" className="mt-16 border-t border-sf-edge pt-10">
        <h2
          id="pdp-description"
          className="font-display text-sf-title font-semibold text-sf-ink"
        >
          توضیحات
        </h2>
        {paragraphs.length === 0 ? (
          <p className="mt-3 max-w-2xl text-sf-body leading-relaxed text-sf-ink-muted">
            برای این محصول توضیحی ثبت نشده است.
          </p>
        ) : (
          paragraphs.map((paragraph, index) => (
            <p
              key={index}
              className="mt-3 max-w-2xl whitespace-pre-line text-sf-body leading-relaxed text-sf-ink"
            >
              {paragraph}
            </p>
          ))
        )}

        <dl className="mt-10 grid gap-6 border-t border-sf-edge pt-6 sm:grid-cols-3">
          <div>
            <dt className="text-sf-caption text-sf-ink-muted">پارچه</dt>
            <dd className="mt-1 text-sf-body text-sf-ink">{product.fabricType}</dd>
          </div>
          <div>
            <dt className="text-sf-caption text-sf-ink-muted">فصل</dt>
            <dd className="mt-1 text-sf-body text-sf-ink">{product.season}</dd>
          </div>
          <div>
            <dt className="text-sf-caption text-sf-ink-muted">نگه‌داری و شست‌وشو</dt>
            <dd className="mt-1 text-sf-body text-sf-ink">
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
