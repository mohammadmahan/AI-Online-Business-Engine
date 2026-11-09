import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { ProductImageEditor } from '@/components/admin/product-image-editor';
import { Badge, PageHeader, Placeholder, buttonClass } from '@/components/ui/primitives';
import { isUuid } from '@/lib/validation';
import { getRepository } from '@/server/db-context';
import { mediaUploadAllowed } from '@/server/media';

/**
 * D-172 §2.1 — the gallery editor for an EXISTING product.
 *
 * Until this page existed, the roadmap's multi-image uploader only ran inside
 * the ingestion form: a product's photos were fixed at creation. The editor is
 * the merchant path to add, reorder, re-primary and remove associations, and it
 * is deliberately the ONLY thing it touches — no title, price, variant or stock
 * field appears here.
 *
 * Two gates resolved server-side and passed down as props, so the UI and the
 * server's refusal are decided by the same fact:
 *  - the connection (`DATABASE_URL`), which otherwise renders as a stated
 *    refusal rather than an empty gallery;
 *  - whether the LOCAL media backend and its upload edge are both configured
 *    (G-5's production provider is still an open decision).
 *
 * An unknown or malformed id is a 404, never an empty editor for a product that
 * does not exist.
 */

export const metadata: Metadata = { title: 'تصویرهای محصول' };
export const dynamic = 'force-dynamic';

export default async function ProductImagesPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const repository = getRepository();

  return (
    <>
      <PageHeader
        title="تصویرهای محصول"
        description="افزودن، جابه‌جایی، انتخاب تصویر اصلی و حذف پیوست تصویرها (D-172 §2.1)."
        action={
          <Link className={buttonClass.neutral} href="/admin">
            بازگشت به فهرست محصولات
          </Link>
        }
      />

      {repository === null ? (
        <>
          <ConnectionMissing what="ویرایش تصویرهای محصول" />
          <Placeholder>
            برای ویرایش تصویرها، ابتدا متغیر محیطی{' '}
            <span className="cp-code">DATABASE_URL</span> را تنظیم کنید.
          </Placeholder>
        </>
      ) : (
        <ProductEditor id={id} repository={repository} mediaUploadBlocked={!mediaUploadAllowed()} />
      )}
    </>
  );
}

async function ProductEditor({
  id,
  repository,
  mediaUploadBlocked,
}: {
  id: string;
  repository: NonNullable<ReturnType<typeof getRepository>>;
  mediaUploadBlocked: boolean;
}) {
  // A malformed id is a 404 before the driver sees it — `products.id` is a uuid,
  // so passing a random segment through would raise a SQL error (a 500) instead
  // of the honest "no such product".
  if (!isUuid(id)) {
    notFound();
  }
  const product = await repository.getProductImageEditor(id);
  if (product === null) {
    notFound();
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="flex flex-wrap items-center gap-2 rounded-[--radius-cp] border border-edge bg-surface-muted p-3 text-cp-label text-ink-muted">
        <span className="font-semibold text-ink">{product.title}</span>
        <span className="cp-code">{product.slug}</span>
        <Badge tone={product.status === 'PUBLISHED' ? 'success' : 'neutral'}>
          {product.status === 'PUBLISHED' ? 'منتشرشده' : 'پیش‌نویس'}{' '}
          <span className="cp-code">{product.status}</span>
        </Badge>
      </p>

      <ProductImageEditor
        productId={product.productId}
        initialImages={product.images}
        uploadBlocked={mediaUploadBlocked}
      />
    </div>
  );
}
