import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  HelpCircle,
  Minus,
  XCircle,
} from 'lucide-react';
import Link from 'next/link';

import { ToneBadge, type Tone } from '@/components/ui/tone-badge';
import { formatPercent } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { KpiCard, KpiState } from '@/types/dashboard';
import type { Trend } from '@/types/telemetry';

const STATE_META: Record<KpiState, { tone: Tone; Icon: typeof CheckCircle2; label: string }> = {
  ok: { tone: 'success', Icon: CheckCircle2, label: 'در محدوده' },
  warn: { tone: 'warning', Icon: AlertTriangle, label: 'نیازمند توجه' },
  alert: { tone: 'danger', Icon: XCircle, label: 'هشدار' },
  unknown: { tone: 'neutral', Icon: HelpCircle, label: 'نامشخص' },
};

/**
 * Trend indicator.
 *
 * Colour follows `goodWhen` (the rule declared by the data, not a guess), and
 * direction is ALSO carried by an arrow icon and a sign, so the reading does
 * not depend on colour (`color-not-only`).
 */
function TrendLine({ trend, goodWhen }: { trend: Trend; goodWhen: 'up' | 'down' }) {
  const rising = trend.direction === 'up';
  const falling = trend.direction === 'down';
  const good = (rising && goodWhen === 'up') || (falling && goodWhen === 'down');

  const Icon = rising ? ArrowUpRight : falling ? ArrowDownRight : Minus;
  const ink = trend.direction === 'flat' ? 'text-ink-muted' : good ? 'text-success' : 'text-danger';

  return (
    <p className={cn('flex items-center gap-1 text-cp-caption font-medium', ink)}>
      <Icon aria-hidden="true" className="size-4 shrink-0" />
      <span className="tabular-nums">
        {trend.direction === 'flat' ? '' : rising ? '+' : '−'}
        {formatPercent(trend.deltaPercent)}
      </span>
      <span className="text-ink-muted">{trend.comparison}</span>
      <span className="sr-only">
        {rising ? 'افزایش' : falling ? 'کاهش' : 'بدون تغییر'} —{' '}
        {good ? 'مطلوب' : 'نامطلوب'}
      </span>
    </p>
  );
}

function KpiTile({ kpi }: { kpi: KpiCard }) {
  const meta = STATE_META[kpi.state];

  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-cp-label font-semibold text-ink">{kpi.title}</h3>
          <p className="font-mono text-cp-caption text-ink-muted">{kpi.code}</p>
        </div>
        <ToneBadge tone={meta.tone} label={meta.label} code={kpi.state.toUpperCase()} Icon={meta.Icon} />
      </div>

      <p className="flex items-baseline gap-2">
        <span className="text-cp-display font-bold tabular-nums text-ink">{kpi.value}</span>
        {kpi.unit ? <span className="text-cp-label text-ink-muted">{kpi.unit}</span> : null}
      </p>

      {kpi.secondary ? (
        <p className="text-cp-caption text-ink-muted">{kpi.secondary}</p>
      ) : null}

      {kpi.trend ? <TrendLine trend={kpi.trend} goodWhen={kpi.goodWhen} /> : null}

      <p className="mt-auto text-cp-caption text-ink-muted">{kpi.detail}</p>
    </>
  );

  const classes = cn(
    'flex flex-col gap-3 rounded-[--radius-cp] border border-edge bg-surface p-4',
    kpi.href ? 'transition-colors hover:bg-surface-muted' : null,
  );

  if (kpi.href) {
    return (
      <Link href={kpi.href} className={classes} aria-label={`${kpi.title} — رفتن به صف تأیید`}>
        {body}
      </Link>
    );
  }

  return <article className={classes}>{body}</article>;
}

/** The responsive 4-column executive KPI grid. */
export function KpiGrid({ kpis }: { kpis: KpiCard[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {kpis.map((kpi) => (
        <KpiTile key={kpi.id} kpi={kpi} />
      ))}
    </div>
  );
}
