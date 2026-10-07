import { FlaskConical, PlugZap } from 'lucide-react';
import type { Metadata } from 'next';

import { BusinessStatusCard } from '@/components/business/business-status-card';
import { OrdersWorkspace } from '@/components/commerce/orders-workspace';
import { RevenueKpiStrip } from '@/components/commerce/revenue-kpi-strip';
import { PageHeader } from '@/components/page-shell';
import { Card, Placeholder } from '@/components/ui/card';
import { ToneBadge } from '@/components/ui/tone-badge';
import { TechnicalOnly } from '@/components/ui/view-gate';
import { ordersBusinessCard } from '@/lib/business-summary';
import { formatTimeUtc } from '@/lib/format';
import { activeCommerceScenario, createMockCommerceSource } from '@/lib/mock/commerce-data';

export const metadata: Metadata = {
  title: 'سفارش‌ها',
};

/**
 * Commerce, orders & revenue control plane (D-171 §5.6, Phase 27.8).
 *
 * Renders entirely from a `CommerceDataSource` — today the deterministic mock
 * provider, the only implementation in this phase — so the page states its
 * provenance before the first order is read: a mocked revenue picture is not
 * evidence of business.
 *
 * Payment and fulfillment are DRY-RUN by construction: no payment provider
 * (open decision 10) and no shipping provider (open decision 11) is selected,
 * so the page never presents a real payment or shipping path. An unrecognised
 * `CP_COMMERCE_SCENARIO` falls back to NO_DATA, and then nothing is rendered as
 * zero — an unreachable order book must not look like zero revenue.
 *
 * The page is READ-ONLY. It never mints a token, holds no signing key and owns
 * no write path; every fulfillment/payment control is rendered disabled with
 * its own reason. Writing an order state still requires a single-use owner
 * token (D-146) over the signed write path (D-171 §6).
 */
export default async function Page() {
  const source = createMockCommerceSource(activeCommerceScenario());
  const snapshot = await source.load();
  const unavailable = snapshot.provenance === 'unavailable';

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader
        href="/orders"
        meta={
          <TechnicalOnly surface="orders-page-meta">
            <p className="mt-1 text-cp-caption text-ink-muted">
              تصویر لحظه‌ای:{' '}
              <time dateTime={snapshot.generatedAt} className="tabular-nums">
                {formatTimeUtc(snapshot.generatedAt)}
              </time>{' '}
              UTC · منبع: <span className="font-mono">{snapshot.provenance}</span>
            </p>
          </TechnicalOnly>
        }
      />

      <BusinessStatusCard model={ordersBusinessCard(snapshot)} />

      <TechnicalOnly surface="orders-notice">
      <div
        className={
          unavailable
            ? 'flex flex-wrap items-center gap-3 rounded-[--radius-cp] border border-danger bg-surface p-3'
            : 'flex flex-wrap items-center gap-3 rounded-[--radius-cp] border border-warning bg-surface p-3'
        }
        role="note"
      >
        {unavailable ? (
          <ToneBadge tone="danger" label="بدون داده" code="NO_DATA" Icon={PlugZap} />
        ) : (
          <ToneBadge tone="warning" label="دادهٔ نمونه" code="MOCK" Icon={FlaskConical} />
        )}
        <p className="text-cp-label text-ink">
          {unavailable ? (
            <>
              دفتر سفارش‌ها به هیچ منبعی متصل نیست و هیچ سفارشی بارگذاری نشده است؛ درآمد و همهٔ
              شاخص‌ها <strong>نامشخص (UNKNOWN)</strong> می‌مانند — نه صفر، نه سالم.
            </>
          ) : (
            <>
              سفارش‌ها، پرداخت و درآمد از <strong>دادهٔ نمونهٔ قطعی</strong> خوانده شده‌اند و هیچ
              خوانش زنده‌ای از WooCommerce، درگاه یا OMS انجام نشده؛ پرداخت و ارسال در حالت{' '}
              <strong>تمرینی (DRY-RUN)</strong> است — نه درگاه پرداخت انتخاب شده (تصمیم باز ۱۰) و
              نه ارائه‌دهندهٔ ارسال (تصمیم باز ۱۱) — پس هیچ کنش نوشتنی مجاز نیست.
            </>
          )}{' '}
          سناریو: <span className="font-mono text-cp-caption">{snapshot.scenario}</span>
        </p>
      </div>
      </TechnicalOnly>

      {unavailable ? (
        <Card>
          <Placeholder>
            هیچ سفارشی برای نمایش وجود ندارد. اتصال زنده در فاز سیم‌کشی زنده (Live Wiring) انجام
            می‌شود؛ تا آن زمان هیچ درآمد، شمار سفارش یا بج سبزی نمایش داده نمی‌شود — نه صفر، نه
            سالم.
          </Placeholder>
        </Card>
      ) : (
        <>
          <RevenueKpiStrip summary={snapshot.summary} />
          <OrdersWorkspace snapshot={snapshot} />
        </>
      )}
    </div>
  );
}
