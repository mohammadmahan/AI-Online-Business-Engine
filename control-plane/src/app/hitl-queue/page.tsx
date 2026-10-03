import { FlaskConical, PlugZap } from 'lucide-react';
import type { Metadata } from 'next';

import { QueueWorkspace } from '@/components/hitl/queue-workspace';
import { PageHeader } from '@/components/page-shell';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatTimeUtc } from '@/lib/format';
import { activeHitlScenario, createMockHitlSource } from '@/lib/mock/hitl-data';

export const metadata: Metadata = {
  title: 'صف تأیید انسانی',
};

/**
 * HITL review queue (D-171 §5.2, Phase 27.4).
 *
 * Renders entirely from a `HitlQueueDataSource`. Today that source is the
 * deterministic mock provider — the only implementation in this phase — so the
 * page states its provenance before the first ticket is read: a mocked approval
 * is not an approval.
 *
 * The page is READ-ONLY by construction. It never mints a token, holds no
 * signing key, and every decision control is rendered disabled with its own
 * reason. Approving anything still requires the real HITL engine (D-106) and a
 * single-use owner token (D-146).
 */
export default async function Page() {
  const source = createMockHitlSource(activeHitlScenario());
  const snapshot = await source.load();
  const unavailable = snapshot.provenance === 'unavailable';

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader
        href="/hitl-queue"
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
              صف به موتور HITL متصل نیست و هیچ تیکتی بارگذاری نشده است؛ وضعیت
              صف <strong>نامشخص (UNKNOWN)</strong> است — نه خالی، نه تأییدشده.
            </>
          ) : (
            <>
              صف از <strong>داده‌ی نمونه‌ی قطعی</strong> پر شده است و هیچ تیکتی
              از موتور HITL خوانده نشده؛ هیچ کنشی روی این تیکت‌ها مجاز نیست.
            </>
          )}{' '}
          سناریو: <span className="font-mono text-cp-caption">{snapshot.scenario}</span>
        </p>
      </div>

      <QueueWorkspace snapshot={snapshot} />
    </div>
  );
}
