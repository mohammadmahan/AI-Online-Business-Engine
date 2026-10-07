import {
  AlertTriangle,
  CheckCircle2,
  Database,
  HelpCircle,
  Network,
  Server,
  Workflow,
  XCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { ToneBadge, type Tone } from '@/components/ui/tone-badge';
import { formatTimeUtc } from '@/lib/format';
import { cn } from '@/lib/utils';
import type {
  HealthState,
  ServiceHealth,
  ServiceId,
  TelemetrySummary,
} from '@/types/telemetry';

const SERVICE_ICON: Record<ServiceId, LucideIcon> = {
  postgres: Database,
  dokploy: Server,
  n8n: Workflow,
  walrus: Network,
};

/**
 * Health state → presentation. Every state carries an icon, a Persian label and
 * an English code, so meaning survives without colour (`color-not-only`).
 *
 * `unknown` and `unavailable` are rendered as neutral/alert, never as success:
 * the UI has no way to show "not measured" as green.
 */
const STATE_META: Record<
  HealthState,
  { label: string; code: string; tone: Tone; Icon: typeof CheckCircle2; ink: string }
> = {
  ok: { label: 'سالم', code: 'OK', tone: 'success', Icon: CheckCircle2, ink: 'text-success' },
  degraded: {
    label: 'تنزل‌یافته',
    code: 'DEGRADED',
    tone: 'warning',
    Icon: AlertTriangle,
    ink: 'text-warning',
  },
  unavailable: {
    label: 'در دسترس نیست',
    code: 'UNAVAILABLE',
    tone: 'danger',
    Icon: XCircle,
    ink: 'text-danger',
  },
  unknown: {
    label: 'نامشخص',
    code: 'UNKNOWN',
    tone: 'neutral',
    Icon: HelpCircle,
    ink: 'text-ink-muted',
  },
};

/** Persian + English status summary above the grid. */
export function HealthSummary({ summary }: { summary: TelemetrySummary }) {
  return (
    <ul
      className="flex flex-wrap items-center gap-2"
      aria-label="خلاصهٔ وضعیت سرویس‌ها"
    >
      <li>
        <ToneBadge tone="success" label="سالم" code="OK" detail={`${summary.ok}`} />
      </li>
      <li>
        <ToneBadge
          tone="warning"
          label="تنزل‌یافته"
          code="DEGRADED"
          detail={`${summary.degraded}`}
        />
      </li>
      <li>
        <ToneBadge
          tone="danger"
          label="در دسترس نیست"
          code="UNAVAILABLE"
          detail={`${summary.unavailable}`}
        />
      </li>
      <li>
        <ToneBadge
          tone="neutral"
          label="نامشخص"
          code="UNKNOWN"
          detail={`${summary.unknown}`}
        />
      </li>
    </ul>
  );
}

function ServiceCard({ service }: { service: ServiceHealth }) {
  const meta = STATE_META[service.state];
  const Icon = SERVICE_ICON[service.id];

  return (
    <article
      className="flex flex-col gap-3 rounded-[--radius-cp] border border-edge bg-surface p-4"
      aria-label={`${service.title} — ${meta.label} (${meta.code})`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={cn('shrink-0', meta.ink)}>
            <Icon aria-hidden="true" className="size-5" />
          </span>
          <div>
            <h3 className="text-cp-label font-semibold text-ink">{service.title}</h3>
            <p className="font-mono text-cp-caption text-ink-muted">{service.code}</p>
          </div>
        </div>
        <ToneBadge tone={meta.tone} label={meta.label} code={meta.code} Icon={meta.Icon} />
      </div>

      <dl className="flex flex-col gap-1">
        {service.metrics.map((metric) => (
          <div key={metric.code} className="flex items-baseline justify-between gap-3">
            <dt className="text-cp-caption text-ink-muted">{metric.label}</dt>
            <dd
              className={cn(
                'text-cp-label font-medium tabular-nums',
                metric.value === null ? 'text-ink-muted' : 'text-ink',
              )}
            >
              {metric.value === null ? (
                <>
                  <span aria-hidden="true">—</span>
                  <span className="sr-only">اندازه‌گیری نشده</span>
                </>
              ) : (
                metric.value
              )}
            </dd>
          </div>
        ))}
      </dl>

      <p className="text-cp-caption text-ink-muted">{service.detail}</p>
      <p className="text-cp-caption text-ink-muted">
        {service.lastMeasuredAt ? (
          <>
            آخرین اندازه‌گیری:{' '}
            <span className="tabular-nums">{formatTimeUtc(service.lastMeasuredAt)}</span> UTC
          </>
        ) : (
          'هیچ اندازه‌گیری‌ای ثبت نشده است'
        )}
      </p>
    </article>
  );
}

/** The 4-card infrastructure health grid (D-171 §5.1). */
export function HealthGrid({ services }: { services: ServiceHealth[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {services.map((service) => (
        <ServiceCard key={service.id} service={service} />
      ))}
    </div>
  );
}
