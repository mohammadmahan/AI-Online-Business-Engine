import type { Metadata } from 'next';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { InventoryWorkspace } from '@/components/admin/inventory-workspace';
import { PageHeader, Placeholder } from '@/components/ui/primitives';
import { getRepository } from '@/server/db-context';

/**
 * D-172 §2.2 — inventory & inline management.
 *
 * The rows are read on the server and the editable grid is a client component;
 * every edit round-trips through a server action that re-validates the value, so
 * the browser can never write a quantity the service would refuse.
 */

export const metadata: Metadata = { title: 'موجودی و قیمت' };
export const dynamic = 'force-dynamic';

export default async function InventoryPage() {
  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <PageHeader title="موجودی و قیمت" description="ویرایش درجای موجودی و قیمت گونه‌ها." />
        <ConnectionMissing what="فهرست موجودی" />
      </>
    );
  }

  const rows = await repository.listInventory();

  return (
    <>
      <PageHeader
        title="موجودی و قیمت"
        description="ویرایش درجای موجودی و قیمت گونه‌ها، با نشان هشدار موجودی کم."
      />
      {rows.length === 0 ? (
        <Placeholder>
          هنوز گونه‌ای ثبت نشده است. با «افزودن محصول» و ساخت ماتریس رنگ و سایز، سطرهای موجودی
          همین‌جا ساخته می‌شوند.
        </Placeholder>
      ) : (
        <InventoryWorkspace rows={rows} />
      )}
    </>
  );
}
