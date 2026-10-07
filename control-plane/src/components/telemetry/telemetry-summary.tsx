import { Server, ShieldCheck } from 'lucide-react';

import {
  CONTAINER_STATUS_META,
  GATE_STATUS_META,
  QUEUE_PRESSURE_META,
} from '@/components/telemetry/status-meta';
import { Card } from '@/components/ui/card';
import { ToneBadge } from '@/components/ui/tone-badge';
import { cn } from '@/lib/utils';
import type { TelemetryOverview } from '@/types/telemetry';

/**
 * Snapshot roll-up (D-171 §5.4): one row of counts per surface kind.
 *
 * The counts are DERIVED from the rendered rows (`summarizeTelemetry` in the
 * mock provider), and the build-time guard rejects a strip that disagrees with
 * the data it summarises — the headline can never drift from the matrix.
 *
 * "Worst case" is stated as text with its canonical code, never as a colour
 * swatch: UNKNOWN is not painted green, and an OK queue reading is not painted
 * as evidence of health.
 */
export function TelemetrySummaryStrip({ summary }: { summary: TelemetryOverview }) {
  const containerCounts = [
    { count: summary.containersHealthy, meta: CONTAINER_STATUS_META.HEALTHY },
    { count: summary.containersDegraded, meta: CONTAINER_STATUS_META.DEGRADED },
    { count: summary.containersDown, meta: CONTAINER_STATUS_META.DOWN },
    { count: summary.containersUnknown, meta: CONTAINER_STATUS_META.UNKNOWN },
  ];
  const gateCounts = [
    { count: summary.gatesPass, meta: GATE_STATUS_META.PASS },
    { count: summary.gatesBlocked, meta: GATE_STATUS_META.BLOCKED },
    { count: summary.gatesEvaluating, meta: GATE_STATUS_META.EVALUATING },
    { count: summary.gatesBypassPrevented, meta: GATE_STATUS_META.BYPASS_PREVENTED },
  ];
  const worstContainer = CONTAINER_STATUS_META[summary.worstContainer];
  const worstPressure = QUEUE_PRESSURE_META[summary.worstQueuePressure];

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card className="p-3 sm:p-4">
        <h2 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
          <Server aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
          کانتینرها
        </h2>
        <ul
          className="mt-2 flex flex-wrap items-center gap-2"
          aria-label="شمار کانتینرها بر پایهٔ وضعیت"
        >
          {containerCounts.map(({ count, meta }) => (
            <li key={meta.code}>
              <ToneBadge
                tone={meta.tone}
                label={meta.label}
                code={meta.code}
                Icon={meta.Icon}
                detail={`${count}`}
              />
            </li>
          ))}
        </ul>
        <p className="mt-2 text-cp-caption text-ink-muted">
          بدترین وضعیت کانتینر:{' '}
          <span className={cn('font-medium', worstContainer.ink)}>
            {worstContainer.label} ({worstContainer.code})
          </span>{' '}
          · فشار صف:{' '}
          <span className={cn('font-medium', worstPressure.ink)}>
            {worstPressure.label} ({worstPressure.code})
          </span>
        </p>
      </Card>

      <Card className="p-3 sm:p-4">
        <h2 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
          <ShieldCheck aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
          گیت‌های خط لوله (V-01..V-10)
        </h2>
        <ul
          className="mt-2 flex flex-wrap items-center gap-2"
          aria-label="شمار گیت‌ها بر پایهٔ وضعیت"
        >
          {gateCounts.map(({ count, meta }) => (
            <li key={meta.code}>
              <ToneBadge
                tone={meta.tone}
                label={meta.label}
                code={meta.code}
                Icon={meta.Icon}
                detail={`${count}`}
              />
            </li>
          ))}
        </ul>
        <p className="mt-2 text-cp-caption text-ink-muted">
          «گذر» تنها با شواهد تازه معتبر است؛ «عبور رد شد» یعنی تلاش برای دور زدن گیت مالک
          مسدود شده است — نه اینکه گیت باز شده باشد (D-146).
        </p>
      </Card>
    </div>
  );
}
