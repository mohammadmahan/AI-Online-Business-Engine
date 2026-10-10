import type { Metadata } from 'next';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { ProductIngestionForm } from '@/components/admin/product-ingestion-form';
import { PageHeader, Placeholder } from '@/components/ui/primitives';
import { getRepository } from '@/server/db-context';
import { mediaUploadAllowed } from '@/server/media';

/**
 * D-172 §2.1 — smart product ingestion.
 *
 * Two independent gates are resolved on the server and passed down as props, so
 * the form's UI and the server's refusal are decided by the same fact:
 *  - `categories` comes from the database (an empty list is stated, not faked);
 *  - `mediaUploadBlocked` reports the still-open G-5 media-storage decision.
 */

export const metadata: Metadata = { title: 'افزودن محصول' };
export const dynamic = 'force-dynamic';

export default async function NewProductPage() {
  const repository = getRepository();
  const mediaUploadBlocked = !mediaUploadAllowed();

  return (
    <>
      <PageHeader
        title="افزودن محصول"
        description="«ورودی محصول هوشمند» (D-172 §2.1): مشخصات، ماتریس رنگ و سایز، و تصویرها."
      />

      {repository === null ? (
        <div className="mb-4">
          <ConnectionMissing what="فرم افزودن محصول" />
        </div>
      ) : null}

      {repository === null ? (
        <Placeholder>
          برای ثبت محصول، ابتدا متغیر محیطی <span className="cp-code">DATABASE_URL</span> را تنظیم
          کنید. فرم در همین صفحه و بدون تغییر کد فعال می‌شود.
        </Placeholder>
      ) : (
        <ProductIngestionForm
          categories={await repository.listCategories()}
          mediaUploadBlocked={mediaUploadBlocked}
        />
      )}
    </>
  );
}
