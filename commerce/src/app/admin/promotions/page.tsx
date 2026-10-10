import type { Metadata } from 'next';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { CouponManager } from '@/components/admin/coupon-manager';
import { PageHeader } from '@/components/ui/primitives';
import { getRepository } from '@/server/db-context';
import { listCoupons } from '@/server/services/coupons';

/**
 * D-172 §2.4 — promotions & discounts.
 *
 * Coupons are read on the server and their display state is derived there from
 * the current instant (`@/lib/coupon-rules`), so an expired or exhausted code
 * cannot render as usable.
 */

export const metadata: Metadata = { title: 'تخفیف‌ها' };
export const dynamic = 'force-dynamic';

export default async function PromotionsPage() {
  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <PageHeader
          title="کدهای تخفیف"
          description="کدهای درصدی و مبلغ ثابت با تاریخ انقضا و حداقل خرید."
        />
        <ConnectionMissing what="فهرست کدهای تخفیف" />
      </>
    );
  }

  const coupons = await listCoupons(repository);

  return (
    <>
      <PageHeader
        title="کدهای تخفیف"
        description="کدهای درصدی و مبلغ ثابت با تاریخ انقضا، حداقل خرید و سقف استفاده."
      />
      <CouponManager coupons={coupons} />
    </>
  );
}
