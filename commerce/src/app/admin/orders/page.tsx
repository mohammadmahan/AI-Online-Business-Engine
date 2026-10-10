import type { Metadata } from 'next';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { OrderWorkspace } from '@/components/admin/order-workspace';
import { PageHeader } from '@/components/ui/primitives';
import { getRepository } from '@/server/db-context';
import { listOrders } from '@/server/services/orders';

/**
 * D-172 §2.3 — order fulfillment & shipping.
 *
 * The list is read on the server; the transitions, the tracking-code modal and
 * the print link are the client workspace. The allowed transitions come from
 * `@/lib/order-rules`, which the server re-checks on every write.
 */

export const metadata: Metadata = { title: 'سفارش‌ها' };
export const dynamic = 'force-dynamic';

export default async function OrdersPage() {
  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <PageHeader title="سفارش‌ها" description="وضعیت سفارش، کد رهگیری و فاکتور بسته‌بندی." />
        <ConnectionMissing what="فهرست سفارش‌ها" />
      </>
    );
  }

  const orders = await listOrders(repository);

  return (
    <>
      <PageHeader
        title="سفارش‌ها"
        description="تغییر وضعیت فقط در مسیرهای مجاز، ثبت کد رهگیری و چاپ فاکتور بسته‌بندی."
      />
      <OrderWorkspace orders={orders} />
    </>
  );
}
