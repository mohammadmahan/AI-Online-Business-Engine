import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { ProductEditForm } from '@/components/admin/product-edit-form';
import type { Tone } from '@/components/ui/primitives';
import { Badge, PageHeader, Placeholder, buttonClass } from '@/components/ui/primitives';
import { PRODUCT_STATUS_LABELS } from '@/lib/product-status';
import { isUuid } from '@/lib/validation';
import { getRepository } from '@/server/db-context';

/**
 * D-172 §2.1 — the edit page for an EXISTING product.
 *
 * The route loads the product SERVER-SIDE and 404s for a malformed or unknown id,
 * so the form is only ever rendered with stored values. It edits the product row
 * and nothing else: variants/stock live in `/admin/inventory`, photos in
 * `/admin/products/[id]/images`, and both are linked from this page.
 */

export const metadata: Metadata = { title: 'ویرایش محصول' };
export const dynamic = 'force-dynamic';

const STATUS_TONES: Record<string, Tone> = {
  DRAFT: 'neutral',
  PUBLISHED: 'success',
  ARCHIVED: 'warning',
};

export default async function ProductEditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const repository = getRepository();

  return (
    <>
      <PageHeader
        title="ویرایش محصول"
        description="اصلاح عنوان، نشانی، توضیح، قیمت، دسته و وضعیت محصول (D-172 §2.1)."
        action={
          <Link className={buttonClass.neutral} href="/admin">
            بازگشت به فهرست محصولات
          </Link>
        }
      />

      {repository === null ? (
        <>
          <ConnectionMissing what="ویرایش محصول" />
          <Placeholder>
            برای ویرایش محصول، ابتدا متغیر محیطی{' '}
            <span className="cp-code">DATABASE_URL</span> را تنظیم کنید.
          </Placeholder>
        </>
      ) : (
        <ProductEditor id={id} repository={repository} />
      )}
    </>
  );
}

async function ProductEditor({
  id,
  repository,
}: {
  id: string;
  repository: NonNullable<ReturnType<typeof getRepository>>;
}) {
  // A malformed id is a 404 before the driver sees it — `products.id` is a uuid.
  if (!isUuid(id)) {
    notFound();
  }
  const product = await repository.getProductForEdit(id);
  if (product === null) {
    notFound();
  }
  const categories = await repository.listCategories();

  return (
    <div className="flex flex-col gap-4">
      <p className="flex flex-wrap items-center gap-2 rounded-[--radius-cp] border border-edge bg-surface-muted p-3 text-cp-label text-ink-muted">
        <span className="font-semibold text-ink">{product.title}</span>
        <span className="cp-code">{product.slug}</span>
        <Badge tone={STATUS_TONES[product.status] ?? 'neutral'}>
          {PRODUCT_STATUS_LABELS[product.status]}{' '}
          <span className="cp-code">{product.status}</span>
        </Badge>
      </p>

      <ProductEditForm
        product={{
          id: product.id,
          categoryId: product.categoryId,
          title: product.title,
          slug: product.slug,
          basePrice: product.basePrice,
          discountPrice: product.discountPrice,
          descriptionRaw: product.descriptionRaw,
          fabricType: product.fabricType,
          season: product.season,
          careInstructions: product.careInstructions,
          status: product.status,
        }}
        categories={categories.map((category) => ({ id: category.id, name: category.name }))}
      />
    </div>
  );
}
