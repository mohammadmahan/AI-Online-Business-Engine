import { FlaskConical, PlugZap } from 'lucide-react';
import type { Metadata } from 'next';

import { InventoryWorkspace } from '@/components/inventory/inventory-workspace';
import { MetricsBanner } from '@/components/inventory/metrics-banner';
import { PageHeader } from '@/components/page-shell';
import { Card, Placeholder } from '@/components/ui/card';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatTimeUtc } from '@/lib/format';
import { activeInventoryScenario, createMockInventorySource } from '@/lib/mock/inventory-data';

export const metadata: Metadata = {
  title: 'موجودی و محصولات',
};

/**
 * Inventory & canonical SKU control plane (D-171 §5.3, Phase 27.5).
 *
 * Renders entirely from an `InventoryDataSource`. Today that source is the
 * deterministic mock provider — the only implementation in this phase — so the
 * page states its provenance before the first SKU is read: a mocked catalog is
 * not evidence of stock.
 *
 * The page is READ-ONLY by construction. It never mints a token, holds no
 * signing key and owns no write path; every sync/override control is rendered
 * disabled with its own reason. Writing stock or price still requires the
 * canonical service or the signed webhook (D-171 §6) and a single-use owner
 * token (D-146).
 */
export default async function Page() {
  const source = createMockInventorySource(activeInventoryScenario());
  const snapshot = await source.load();
  const unavailable = snapshot.provenance === 'unavailable';

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader
        href="/inventory"
        meta={
          <p className="mt-1 text-cp-caption text-ink-muted">
            تصویر لحظه‌ای:{' '}
            <time dateTime={snapshot.generatedAt} className="tabular-nums">
              {formatTimeUtc(snapshot.generatedAt)}
            </time>{' '}
            UTC · منبع: <span className="font-mono">{snapshot.provenance}</span>
          </p>
        }
      />

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
          <ToneBadge tone="warning" label="داده‌ی نمونه" code="MOCK" Icon={FlaskConical} />
        )}
        <p className="text-cp-label text-ink">
          {unavailable ? (
            <>
              موجودی به منبع canonical متصل نیست و هیچ SKUی بارگذاری نشده است؛ وضعیت{' '}
              <strong>نامشخص (UNKNOWN)</strong> است — نه صفر، نه سالم.
            </>
          ) : (
            <>
              فهرست از <strong>داده‌ی نمونه‌ی قطعی</strong> پر شده است و هیچ مقدار زنده‌ای از
              canonical یا WooCommerce خوانده نشده؛ هیچ اندازه‌گیری‌ای شاهد محسوب نمی‌شود و
              هیچ کنش نوشتنی مجاز نیست.
            </>
          )}{' '}
          سناریو: <span className="font-mono text-cp-caption">{snapshot.scenario}</span>
        </p>
      </div>

      {unavailable ? (
        <Card>
          <Placeholder>
            هیچ SKUی برای نمایش وجود ندارد. اتصال زنده در فاز سیم‌کشی زنده (Live Wiring)
            انجام می‌شود؛ تا آن زمان هیچ شمار، بج سبز یا «سالم»ی نمایش داده نمی‌شود.
          </Placeholder>
        </Card>
      ) : (
        <>
          <MetricsBanner summary={snapshot.summary} />
          <InventoryWorkspace snapshot={snapshot} />
        </>
      )}
    </div>
  );
}
