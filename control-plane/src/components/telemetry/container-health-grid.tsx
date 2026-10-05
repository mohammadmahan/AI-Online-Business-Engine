import { AlertTriangle, Database, Layers, Network, Server, Workflow } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { MeterBar } from '@/components/telemetry/meter-bar';
import { CONTAINER_STATUS_META } from '@/components/telemetry/status-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatNumber, formatTimeUtc, formatUptimeSeconds } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { ContainerHealth, ContainerId } from '@/types/telemetry';

const CONTAINER_ICON: Record<ContainerId, LucideIcon> = {
  postgres: Database,
  n8n: Workflow,
  redis: Layers,
  dokploy: Server,
  walrus: Network,
};

/** Everything known — and unknown — about one container. */
function ContainerCard({ container }: { container: ContainerHealth }) {
  const meta = CONTAINER_STATUS_META[container.status];
  const Icon = CONTAINER_ICON[container.id];
  const metrics = container.metrics;
  const fillClass = container.status === 'DEGRADED' ? 'bg-warning' : 'bg-success';

  return (
    <article
      className="flex flex-col gap-3 rounded-[--radius-cp] border border-edge bg-surface p-4"
      aria-label={`${container.titleFa} — ${meta.label} (${meta.code})`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span className={cn('mt-0.5 shrink-0', meta.ink)}>
            <Icon aria-hidden="true" className="size-5" />
          </span>
          <div>
            <h3 className="text-cp-label font-semibold text-ink">{container.titleFa}</h3>
            <p className="font-mono text-cp-caption text-ink-muted">
              {container.containerRef !== null ? (
                <span dir="ltr">{container.containerRef}</span>
              ) : (
                'بدون سرویس در مانیفست'
              )}
            </p>
          </div>
        </div>
        <ToneBadge tone={meta.tone} label={meta.label} code={meta.code} Icon={meta.Icon} />
      </div>

      {metrics !== null ? (
        <div className="flex flex-col gap-3">
          <MeterBar
            label="مصرف CPU"
            value={metrics.cpuPercent}
            max={100}
            valueText={`${metrics.cpuPercent}%`}
            fillClass={fillClass}
          />
          <MeterBar
            label="حافظه"
            value={metrics.memoryUsedMb}
            max={metrics.memoryLimitMb}
            valueText={`${formatNumber(metrics.memoryUsedMb)} از ${formatNumber(metrics.memoryLimitMb)} MB`}
            fillClass={fillClass}
          />
          <p className="text-cp-caption text-ink-muted">
            زمان کار: <span className="text-ink">{formatUptimeSeconds(metrics.uptimeSeconds)}</span>
          </p>
        </div>
      ) : (
        <div className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-2">
          <p className="font-mono text-cp-caption text-ink-muted">
            <span dir="ltr">METRICS: {container.metricsState}</span>
          </p>
          <p className="mt-1 text-cp-caption text-ink-muted">
            هیچ خوانش زنده‌ای ثبت نشده است؛ نمایش «صفر» به‌جای اندازه‌گیری ممنوع است
            (fail-closed).
          </p>
        </div>
      )}

      <p className="text-cp-caption text-ink-muted">{container.detailFa}</p>

      {container.probe !== null ? (
        <div className="flex flex-col gap-2 rounded-[--radius-cp] border border-edge bg-surface-muted p-2">
          <ToneBadge
            tone="neutral"
            label="تأخیر کاوش"
            code="PROBE_LATENCY"
            detail={
              container.probe.latencyMs !== null
                ? `${formatNumber(container.probe.latencyMs)} ms`
                : 'بدون پاسخ'
            }
          />
          <p className="text-cp-caption text-ink-muted">
            کاوش در{' '}
            <time dateTime={container.probe.probedAtUtc} className="tabular-nums text-ink">
              {formatTimeUtc(container.probe.probedAtUtc)}
            </time>{' '}
            UTC
            {container.probe.endpointLabel !== null ? (
              <>
                {' · '}
                <span dir="ltr" className="font-mono">
                  {container.probe.endpointLabel}
                </span>
              </>
            ) : null}
          </p>
          {container.probe.payloadDigest !== null ? (
            <p className="font-mono text-cp-caption text-ink-muted">
              <span dir="ltr">sha256:{container.probe.payloadDigest.slice(0, 16)}…</span>
            </p>
          ) : null}
          {container.probe.reasonFa.length > 0 ? (
            <p className="text-cp-caption text-ink">{container.probe.reasonFa}</p>
          ) : null}
        </div>
      ) : null}

      {container.incident !== null ? (
        <div
          className={cn(
            'flex flex-col gap-1 rounded-[--radius-cp] border p-2',
            container.incident.severity === 'DOWN'
              ? 'border-danger bg-surface'
              : 'border-warning bg-surface',
          )}
        >
          <p className="flex items-center gap-2 text-cp-caption font-medium text-ink">
            <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
            رخداد فعال —{' '}
            <span className="font-mono">
              <span dir="ltr">{container.incident.severity}</span>
            </span>
          </p>
          <p className="text-cp-caption text-ink">{container.incident.noteFa}</p>
          <p className="text-cp-caption text-ink-muted">
            ثبت‌شده در{' '}
            <time dateTime={container.incident.raisedAtUtc} className="tabular-nums">
              {formatTimeUtc(container.incident.raisedAtUtc)}
            </time>{' '}
            UTC
          </p>
        </div>
      ) : null}

      <dl className="mt-auto flex flex-col gap-1 text-cp-caption">
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-ink-muted">انتشار پورت</dt>
          <dd className={cn('font-mono', container.portMapping === null ? 'text-ink-muted' : 'text-ink')}>
            {container.portMapping !== null ? (
              <span dir="ltr">{container.portMapping}</span>
            ) : (
              'منتشر نشده'
            )}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <dt className="text-ink-muted">آخرین کاوش</dt>
          <dd className={cn('tabular-nums', container.lastProbeUtc === null ? 'text-ink-muted' : 'text-ink')}>
            {container.lastProbeUtc !== null ? (
              <>
                <time dateTime={container.lastProbeUtc}>{formatTimeUtc(container.lastProbeUtc)}</time>{' '}
                UTC
              </>
            ) : (
              'هرگز کاوش نشده'
            )}
          </dd>
        </div>
      </dl>
    </article>
  );
}

/** The five-container health grid (D-171 §5.4). */
export function ContainerHealthGrid({ containers }: { containers: ContainerHealth[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {containers.map((container) => (
        <ContainerCard key={container.id} container={container} />
      ))}
    </div>
  );
}
