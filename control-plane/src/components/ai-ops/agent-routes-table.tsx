import { HelpCircle } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import { formatNumber, formatTimeUtc } from '@/lib/format';
import type { AgentRouteObservability } from '@/types/ai-ops';

/**
 * Agent observability (D-171 §5.5 `/ai-engine`).
 *
 * Reports the three canonical execution routes (task types) with their
 * invocation counts, success rate, p95 latency and the canonical
 * `ai.observe.v1` pipeline stages each route touched.
 *
 * HONEST LIMIT, STATED RATHER THAN INVENTED: the canonical observability schema
 * records pipeline STAGES — the engine has no tool-calling registry, so no
 * "tools invoked" list exists to show. An unmeasured route renders `—`
 * everywhere, never a zero that could read as a reading (D-171 §2.2).
 */
function RouteRow({ route }: { route: AgentRouteObservability }) {
  const rate = route.successRatePercent;

  return (
    <tr className="border-b border-edge last:border-b-0">
      <th scope="row" className="px-3 py-2 text-start align-top">
        <span className="block font-medium text-ink">{route.titleFa}</span>
        <span className="block font-mono text-cp-caption text-ink-muted" dir="ltr">
          {route.id}
        </span>
      </th>
      <td className="px-3 py-2 text-start align-top tabular-nums text-ink" dir="ltr">
        {route.invocations === null ? '—' : formatNumber(route.invocations)}
      </td>
      <td className="px-3 py-2 text-start align-top tabular-nums" dir="ltr">
        {route.succeeded === null || route.failed === null ? (
          <span className="text-ink-muted">—</span>
        ) : (
          <span className="text-ink">
            {formatNumber(route.succeeded)}
            <span className="text-ink-muted"> / {formatNumber(route.failed)}</span>
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-start align-top">
        {rate === null ? (
          <span className="inline-flex items-center gap-1 text-cp-caption text-ink-muted">
            <HelpCircle aria-hidden="true" className="size-3.5" />
            بدون خوانش
          </span>
        ) : (
          <ToneBadge
            tone={rate >= 95 ? 'success' : rate >= 80 ? 'warning' : 'danger'}
            label={`${rate}%`}
            code="SUCCESS_RATE"
          />
        )}
      </td>
      <td className="px-3 py-2 text-start align-top tabular-nums text-ink" dir="ltr">
        {route.p95LatencyMs === null ? <span className="text-ink-muted">—</span> : `${formatNumber(route.p95LatencyMs)} ms`}
      </td>
      <td className="px-3 py-2 text-start align-top text-ink-muted">
        {route.lastRunUtc === null ? (
          'هرگز'
        ) : (
          <>
            <time dateTime={route.lastRunUtc} className="tabular-nums">
              {formatTimeUtc(route.lastRunUtc)}
            </time>{' '}
            UTC
          </>
        )}
      </td>
      <td className="px-3 py-2 text-start align-top">
        {route.stages.length === 0 ? (
          <span className="text-cp-caption text-ink-muted">بدون مرحلهٔ ثبت‌شده</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {route.stages.map((usage) => (
              <li key={usage.stage} className="font-mono text-cp-caption text-ink-muted" dir="ltr">
                {usage.stage} · {formatNumber(usage.invocations)}
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

export function AgentRoutesTable({ routes }: { routes: AgentRouteObservability[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-cp-label">
        <caption className="sr-only">
          مشاهده‌پذیری مسیرهای اجرای هوش مصنوعی: تعداد اجرا، موفق و ناموفق، نرخ موفقیت، تأخیر
          صدک ۹۵ و مراحل ثبت‌شدهٔ هر مسیر
        </caption>
        <thead>
          <tr className="border-b border-edge-strong text-cp-caption text-ink-muted">
            <th scope="col" className="px-3 py-2 text-start">
              مسیر اجرا
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              اجراها
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              موفق / ناموفق
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              نرخ موفقیت
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              تأخیر p95
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              آخرین اجرا
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              مراحل ثبت‌شده
            </th>
          </tr>
        </thead>
        <tbody>
          {routes.map((route) => (
            <RouteRow key={route.id} route={route} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
