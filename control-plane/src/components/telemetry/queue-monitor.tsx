import { Activity, AlertTriangle, Inbox, Timer } from 'lucide-react';

import { MeterBar } from '@/components/telemetry/meter-bar';
import { QUEUE_PRESSURE_META } from '@/components/telemetry/status-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatNumber, formatTimeUtc } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { QueueTelemetry } from '@/types/telemetry';

const FILL: Record<'OK' | 'WARN' | 'CRITICAL', string> = {
  OK: 'bg-success',
  WARN: 'bg-warning',
  CRITICAL: 'bg-danger',
};

/** Severity of one reading against its own thresholds (mirrors the provider). */
function severityOf(value: number, warnAt: number, criticalAt: number): 'OK' | 'WARN' | 'CRITICAL' {
  if (value >= criticalAt) return 'CRITICAL';
  if (value >= warnAt) return 'WARN';
  return 'OK';
}

/**
 * Queue & throughput monitor (D-171 §5.4).
 *
 * Two readings panels: the Redis work queue (depth + throughput) and n8n
 * workflow executions (active / waiting / failed in the last 24h). Pressure is
 * DERIVED from the readings against the provider's thresholds, and an unread
 * value renders as "نامشخص" with no bar — a broker that does not answer is
 * never shown as an empty queue (fail-closed).
 *
 * The n8n overall pressure is the worse of waiting-backlog and recent failures,
 * so any failed execution in the window prevents an OK reading; that is stated
 * below the readings rather than hidden in a colour.
 */
export function QueueMonitor({ queues }: { queues: QueueTelemetry }) {
  const { redis, n8n } = queues;
  const redisMeta = QUEUE_PRESSURE_META[redis.pressure];
  const n8nMeta = QUEUE_PRESSURE_META[n8n.pressure];

  const redisSeverity =
    redis.depth === null
      ? null
      : severityOf(redis.depth, redis.warnAtDepth, redis.criticalAtDepth);
  const waitingSeverity =
    n8n.waiting === null
      ? null
      : severityOf(n8n.waiting, n8n.warnAtWaiting, n8n.criticalAtWaiting);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section
        className="flex flex-col gap-3 rounded-[--radius-cp] border border-edge bg-surface p-4"
        aria-label="صف کار Redis"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
            <Inbox aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
            صف کار (Redis)
          </h3>
          <ToneBadge tone={redisMeta.tone} label={redisMeta.label} code={redisMeta.code} Icon={redisMeta.Icon} />
        </div>

        {redis.depth !== null && redis.throughputPerMin !== null ? (
          <>
            <dl className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-cp-caption text-ink-muted">عمق صف</dt>
                <dd className="text-cp-label font-medium text-ink tabular-nums">
                  {formatNumber(redis.depth)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-cp-caption text-ink-muted">نرخ پردازش</dt>
                <dd className="text-cp-label font-medium text-ink tabular-nums">
                  {formatNumber(redis.throughputPerMin)} کار در دقیقه
                </dd>
              </div>
            </dl>
            {redisSeverity !== null ? (
              <MeterBar
                label="عمق صف نسبت به آستانهٔ بحران"
                value={redis.depth}
                max={redis.criticalAtDepth}
                valueText={`${formatNumber(redis.depth)} از ${formatNumber(redis.criticalAtDepth)}`}
                fillClass={FILL[redisSeverity]}
              />
            ) : null}
          </>
        ) : (
          <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
            کارگزار پاسخ نمی‌دهد؛ عمق صف و نرخ پردازش خوانده نشده‌اند. «خوانده‌نشده» هرگز
            «صفر» یا «سالم» نمایش داده نمی‌شود (fail-closed).
          </p>
        )}

        {queues.probe.redis !== null ? (
          <p className="text-cp-caption text-ink-muted">
            کاوش زنده: تأخیر{' '}
            <span className="tabular-nums text-ink">
              {queues.probe.redis.latencyMs !== null
                ? `${formatNumber(queues.probe.redis.latencyMs)} ms`
                : 'بدون پاسخ'}
            </span>
            {' · '}
            <time dateTime={queues.probe.redis.probedAtUtc} className="tabular-nums text-ink">
              {formatTimeUtc(queues.probe.redis.probedAtUtc)}
            </time>{' '}
            UTC
            {queues.probe.redis.payloadDigest !== null ? (
              <>
                {' · '}
                <span dir="ltr" className="font-mono">
                  sha256:{queues.probe.redis.payloadDigest.slice(0, 12)}…
                </span>
              </>
            ) : null}
          </p>
        ) : null}

        <p className="text-cp-caption text-ink-muted">
          آستانه‌ها: هشدار از{' '}
          <span className="tabular-nums text-ink">{formatNumber(redis.warnAtDepth)}</span> · بحران از{' '}
          <span className="tabular-nums text-ink">{formatNumber(redis.criticalAtDepth)}</span> کار
        </p>
      </section>

      <section
        className="flex flex-col gap-3 rounded-[--radius-cp] border border-edge bg-surface p-4"
        aria-label="اجرای جریان‌های کاری n8n"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
            <Activity aria-hidden="true" className="size-4 shrink-0 text-ink-muted" />
            اجرای جریان‌های کاری (n8n)
          </h3>
          <ToneBadge tone={n8nMeta.tone} label={n8nMeta.label} code={n8nMeta.code} Icon={n8nMeta.Icon} />
        </div>

        {n8n.active !== null && n8n.waiting !== null && n8n.failedLast24h !== null ? (
          <>
            <dl className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-cp-caption text-ink-muted">در حال اجرا</dt>
                <dd className="text-cp-label font-medium text-ink tabular-nums">
                  {formatNumber(n8n.active)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-cp-caption text-ink-muted">در انتظار</dt>
                <dd className="text-cp-label font-medium text-ink tabular-nums">
                  {formatNumber(n8n.waiting)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <dt className="text-cp-caption text-ink-muted">شکست‌خورده (۲۴ ساعت)</dt>
                <dd
                  className={cn(
                    'text-cp-label font-medium tabular-nums',
                    n8n.failedLast24h > 0 ? 'text-danger' : 'text-ink',
                  )}
                >
                  {formatNumber(n8n.failedLast24h)}
                </dd>
              </div>
            </dl>
            {waitingSeverity !== null ? (
              <MeterBar
                label="صف انتظار نسبت به آستانهٔ بحران"
                value={n8n.waiting}
                max={n8n.criticalAtWaiting}
                valueText={`${formatNumber(n8n.waiting)} از ${formatNumber(n8n.criticalAtWaiting)}`}
                fillClass={FILL[waitingSeverity]}
              />
            ) : null}
            {n8n.failedLast24h > 0 ? (
              <p className="flex items-start gap-2 text-cp-caption text-danger">
                <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                شکست اجرا در بازهٔ اخیر ثبت شده است؛ فشار کلی از بدترینِ «انتظار» و «شکست» محاسبه
                می‌شود و OK نیست.
              </p>
            ) : null}
          </>
        ) : (
          <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
            خوانش‌های n8n در دسترس نیستند؛ شمار اجراها نامشخص است — نه صفر (fail-closed).
          </p>
        )}

        {queues.probe.n8n !== null ? (
          <p className="text-cp-caption text-ink-muted">
            کاوش زنده: تأخیر{' '}
            <span className="tabular-nums text-ink">
              {queues.probe.n8n.latencyMs !== null
                ? `${formatNumber(queues.probe.n8n.latencyMs)} ms`
                : 'بدون پاسخ'}
            </span>
            {' · '}
            <time dateTime={queues.probe.n8n.probedAtUtc} className="tabular-nums text-ink">
              {formatTimeUtc(queues.probe.n8n.probedAtUtc)}
            </time>{' '}
            UTC
            {queues.probe.n8n.payloadDigest !== null ? (
              <>
                {' · '}
                <span dir="ltr" className="font-mono">
                  sha256:{queues.probe.n8n.payloadDigest.slice(0, 12)}…
                </span>
              </>
            ) : null}
          </p>
        ) : null}

        <p className="flex items-center gap-2 text-cp-caption text-ink-muted">
          <Timer aria-hidden="true" className="size-4 shrink-0" />
          آستانهٔ انتظار: هشدار از{' '}
          <span className="tabular-nums text-ink">{formatNumber(n8n.warnAtWaiting)}</span> · بحران از{' '}
          <span className="tabular-nums text-ink">{formatNumber(n8n.criticalAtWaiting)}</span>
        </p>
      </section>
    </div>
  );
}
