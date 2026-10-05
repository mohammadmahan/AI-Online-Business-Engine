import { FlaskConical, PlugZap } from 'lucide-react';
import type { Metadata } from 'next';

import { PageHeader } from '@/components/page-shell';
import { ContainerHealthGrid } from '@/components/telemetry/container-health-grid';
import { OverridePanel } from '@/components/telemetry/override-panel';
import { PipelineGatesMatrix } from '@/components/telemetry/pipeline-gates-matrix';
import { QueueMonitor } from '@/components/telemetry/queue-monitor';
import { TelemetrySummaryStrip } from '@/components/telemetry/telemetry-summary';
import { Card, CardHeader } from '@/components/ui/card';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatTimeUtc } from '@/lib/format';
import { activeTelemetryScenario, createMockTelemetrySource } from '@/lib/mock/telemetry-data';

export const metadata: Metadata = {
  title: 'اتوماسیون‌ها',
};

/**
 * Telemetry, container health and pipeline gates (D-171 §5.4, Phase 27.6).
 *
 * Renders entirely from a `TelemetryDataSource`. Today that source is the
 * deterministic mock provider — the only implementation in this phase — so the
 * page states its provenance before any status is read: a mocked reading is not
 * evidence of health, and an unprobed surface is rendered as UNKNOWN rather
 * than zero (D-171 §2.2).
 *
 * The page is READ-ONLY by construction. It never evaluates a gate, never mints
 * a token, holds no signing key and owns no write path; every emergency control
 * is rendered disabled with its own reason. Forcing a gate still requires a
 * single-use owner token (D-146) and the signed write path (D-171 §6).
 */
export default async function Page() {
  const source = createMockTelemetrySource(activeTelemetryScenario());
  const snapshot = await source.load();
  const unavailable = snapshot.provenance === 'unavailable';
  const worstContainer = snapshot.summary.worstContainer;
  const worstPressure = snapshot.summary.worstQueuePressure;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader
        href="/automations"
        meta={
          <p className="mt-1 text-cp-caption text-ink-muted">
            تصویر لحظه‌ای:{' '}
            <time dateTime={snapshot.generatedAt} className="tabular-nums">
              {formatTimeUtc(snapshot.generatedAt)}
            </time>{' '}
            UTC · منبع: <span className="font-mono">{snapshot.provenance}</span> · بدترین وضعیت
            کانتینر: <span className="font-mono">{worstContainer}</span> · فشار صف:{' '}
            <span className="font-mono">{worstPressure}</span>
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
              تلمتری به هیچ منبع زنده‌ای متصل نیست؛ وضعیت همه‌ی کانتینرها{' '}
              <strong>نامشخص (UNKNOWN)</strong> و همه‌ی گیت‌ها <strong>در حال ارزیابی</strong> است — نه
              صفر، نه سالم.
            </>
          ) : (
            <>
              سلامت کانتینرها، گیت‌ها و صف‌ها از <strong>داده‌ی نمونه‌ی قطعی</strong> خوانده شده است و
              هیچ کاوش زنده‌ای انجام نشده؛ هیچ خوانشی شاهد محسوب نمی‌شود و هیچ کنش اضطراری مجاز
              نیست.
            </>
          )}{' '}
          سناریو: <span className="font-mono text-cp-caption">{snapshot.scenario}</span>
        </p>
      </div>

      <TelemetrySummaryStrip summary={snapshot.summary} />

      <Card>
        <CardHeader
          title="سلامت کانتینرها"
          description="پنج سطح کانتینری با خوانش CPU/حافظه و زمان کار؛ سطح بدون کاوش، «نامشخص» می‌ماند و هیچ میله‌ای برای آن رسم نمی‌شود."
        />
        <ContainerHealthGrid containers={snapshot.containers} />
      </Card>

      <Card>
        <PipelineGatesMatrix gates={snapshot.gates} />
      </Card>

      <Card>
        <CardHeader
          title="صف و نرخ پردازش"
          description="عمق صف Redis و اجراهای n8n با آستانه‌های هشدار/بحران؛ مقدار خوانده‌نشده «نامشخص» است، نه صفر."
        />
        <QueueMonitor queues={snapshot.queues} />
      </Card>

      <Card>
        <OverridePanel actions={snapshot.actions} writeGate={snapshot.writeGate} />
      </Card>
    </div>
  );
}
