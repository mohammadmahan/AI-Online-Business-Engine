import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { PackingSlip } from '@/components/admin/packing-slip';
import { PrintButton } from '@/components/admin/print-button';
import { PageHeader, buttonClass } from '@/components/ui/primitives';
import { getRepository } from '@/server/db-context';
import { getOrder } from '@/server/services/orders';

/**
 * D-172 §2.3 — printable packing slip (فاکتور استاندارد بسته‌بندی).
 *
 * A missing order is a 404, an unusual id is a 404, and an unconfigured database
 * is a stated refusal — never an empty invoice with zeroed totals, which would
 * be a document with the authority of a printed page and no data behind it.
 */

export const metadata: Metadata = { title: 'فاکتور بسته‌بندی' };
export const dynamic = 'force-dynamic';

export default async function PackingSlipPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const repository = getRepository();

  return (
    <>
      <div className="cp-no-print">
        <PageHeader
          title="فاکتور بسته‌بندی"
          description="برای چاپ، دکمهٔ «چاپ فاکتور» یا Ctrl/⌘+P را بزنید."
          action={
            <span className="flex gap-2">
              <Link className={buttonClass.neutral} href="/admin/orders">
                بازگشت به سفارش‌ها
              </Link>
              <PrintButton />
            </span>
          }
        />
      </div>

      {repository === null ? (
        <ConnectionMissing what="فاکتور بسته‌بندی" />
      ) : (
        <OrderSlip id={id} repository={repository} />
      )}
    </>
  );
}

async function OrderSlip({
  id,
  repository,
}: {
  id: string;
  repository: NonNullable<ReturnType<typeof getRepository>>;
}) {
  const order = await getOrder(repository, id);
  if (order === null) {
    notFound();
  }
  return <PackingSlip order={order} />;
}
