import { BadgePercent, CircleX, Coins, Gauge, Hourglass, PackageCheck } from 'lucide-react';

import { cn } from '@/lib/utils';
import { formatNumber, formatToman } from '@/lib/format';
import type { RevenueSummary } from '@/types/commerce';

/**
 * Revenue KPI strip (D-171 §5.6).
 *
 * Every figure is DERIVED from the same rows the table renders
 * (`summarizeRevenue` in the mock provider), and the build-time guard recomputes
 * the roll-up from those rows and rejects any disagreement — the headline can
 * never drift from the orders beneath it.
 *
 * Amounts are integer Toman with no decimals anywhere (D-010). A failed payment
 * is money that never settled, so it is counted separately as a COUNT, never
 * folded into GMV.
 *
 * Each KPI is a plain `<div>` group inside the `<dl>`: a `<section>` there
 * would make the description list invalid HTML and could break the term /
 * definition association for assistive tech.
 */
export function RevenueKpiStrip({ summary }: { summary: RevenueSummary }) {
  const kpis = [
    {
      key: 'dailyGmv',
      title: 'GMV امروز',
      value: formatToman(summary.dailyGmvToman),
      detail: `GMV هفتگی: ${formatToman(summary.weeklyGmvToman)}`,
      Icon: Coins,
      danger: false,
    },
    {
      key: 'aov',
      title: 'میانگین سبد خرید (AOV)',
      value: formatToman(summary.aovToman),
      detail: `بر پایه‌ی ${formatNumber(summary.paidOrderCount)} سفارش پرداخت‌شده`,
      Icon: BadgePercent,
      danger: false,
    },
    {
      key: 'pendingSettlement',
      title: 'در انتظار تسویه',
      value: formatToman(summary.pendingSettlementToman),
      detail: 'پول دریافت‌شده‌ای که هنوز تسویه نشده است',
      Icon: Hourglass,
      danger: false,
    },
    {
      key: 'failedPayments',
      title: 'پرداخت‌های ناموفق',
      value: formatNumber(summary.failedPaymentCount),
      detail: 'سفارش‌هایی که پرداختشان شکست خورده — هرگز بخشی از GMV نیستند',
      Icon: CircleX,
      danger: true,
    },
    {
      key: 'completed',
      title: 'سفارش‌های تکمیل‌شده',
      value: formatNumber(summary.completedOrderCount),
      detail: 'چرخه‌ی D-081 تا COMPLETED رسیده است',
      Icon: PackageCheck,
      danger: false,
    },
    {
      key: 'pendingProcessing',
      title: 'در حال پردازش',
      value: formatNumber(summary.pendingProcessingCount),
      detail: 'تأمین آغاز شده اما چرخه هنوز تکمیل نشده است',
      Icon: Gauge,
      danger: false,
    },
  ];

  return (
    <section className="flex flex-col gap-2" aria-label="شاخص‌های درآمد">
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {kpis.map(({ key, title, value, detail, Icon, danger }) => (
          <div key={key} className="rounded-[--radius-cp] border border-edge bg-surface p-3 sm:p-4">
            <dt className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <Icon aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
              {title}
            </dt>
            <dd
              className={cn(
                'mt-2 text-cp-heading font-semibold tabular-nums',
                danger ? 'text-danger' : 'text-ink',
              )}
            >
              {value}
            </dd>
            <dd className="mt-1 text-cp-caption text-ink-muted">{detail}</dd>
          </div>
        ))}
      </dl>
      <p className="text-cp-caption text-ink-muted">
        همه‌ی مبالغ، عدد صحیح تومان‌اند و هیچ اعشاری نمایش داده نمی‌شود (D-010)؛ این اعداد از
        همان ردیف‌هایی مشتق شده‌اند که در جدول پایین دیده می‌شوند و گارد ساخت، واگرایی آن‌ها را رد
        می‌کند.
      </p>
    </section>
  );
}
