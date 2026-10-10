import { BUDGET_PRESSURE_META } from '@/components/ai-ops/status-meta';
import { MeterBar } from '@/components/telemetry/meter-bar';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatNumber } from '@/lib/format';
import type { TokenCostAnalytics } from '@/types/ai-ops';

/**
 * Token and cost analytics (D-171 §5.5 `/ai-engine`) under the D-063/D-127
 * ceilings.
 *
 * Two canonical ceilings are reported: the D-127 window allowance this screen
 * meters (`llm_tokens` per logical day, shown as a consumption ratio with the
 * canonical 0.8 soft ratio deciding the warning) and the D-063 per-run budget of
 * the route target, rendered in integer micro-USD exactly as the canonical
 * `cost_usd` precision records it.
 *
 * HONEST LIMIT: the canonical tariff table prices only the free deterministic
 * mock provider, so a non-zero spend would be a fabricated reading. The cost
 * column therefore reads 0.00 USD while the mock provider is active, and the
 * guard refuses any (provider, model) pair outside that table instead of
 * inventing a price.
 */

/** Integer micro-USD as a fixed 6-decimal USD string (deterministic, no locale). */
function microUsd(value: number): string {
  const whole = Math.floor(value / 1_000_000);
  const fraction = String(value % 1_000_000).padStart(6, '0');
  return `${formatNumber(whole)}.${fraction}`;
}

function CostRow({ row }: { row: TokenCostAnalytics }) {
  const measured = row.totalTokens !== null;
  const meta = BUDGET_PRESSURE_META[row.pressure];

  return (
    <tr className="border-b border-edge last:border-b-0">
      <th scope="row" className="px-3 py-2 text-start align-top">
        <span className="block font-medium text-ink" dir="ltr">
          {row.routeId}
        </span>
        <span className="block font-mono text-cp-caption text-ink-muted" dir="ltr">
          {row.provider}/{row.model} · {row.resource} · {row.window}
        </span>
      </th>
      <td className="px-3 py-2 text-start align-top tabular-nums text-ink" dir="ltr">
        {row.promptTokens === null ? '—' : formatNumber(row.promptTokens)}
      </td>
      <td className="px-3 py-2 text-start align-top tabular-nums text-ink" dir="ltr">
        {row.completionTokens === null ? '—' : formatNumber(row.completionTokens)}
      </td>
      <td className="px-3 py-2 text-start align-top">
        {measured ? (
          <div className="flex min-w-48 flex-col gap-1">
            <MeterBar
              label="مصرف از سقف پنجره"
              value={Math.min(row.consumedRatio ?? 0, 1) * 100}
              max={100}
              valueText={`${((row.consumedRatio ?? 0) * 100).toFixed(1)}% از ${formatNumber(row.tokenCeiling)}`}
              fillClass={row.pressure === 'OK' ? 'bg-success' : row.pressure === 'WARNING' ? 'bg-warning' : 'bg-danger'}
            />
            <ToneBadge tone={meta.tone} label={meta.label} code={meta.code} Icon={meta.Icon} />
          </div>
        ) : (
          <span className="text-cp-caption text-ink-muted">بدون خوانش</span>
        )}
      </td>
      <td className="px-3 py-2 text-start align-top">
        <span className="block tabular-nums text-ink" dir="ltr">
          {row.costMicroUsd === null ? '—' : `${microUsd(row.costMicroUsd)} USD`}
        </span>
        <span className="block text-cp-caption text-ink-muted" dir="ltr">
          سقف هر اجرا: {microUsd(row.runBudgetMicroUsd)} USD
        </span>
      </td>
    </tr>
  );
}

export function TokenCostTable({ cost }: { cost: TokenCostAnalytics[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-cp-label">
        <caption className="sr-only">
          مصرف توکن و هزینهٔ مسیرهای هوش مصنوعی در برابر سقف پنجرهٔ روزانه و سقف هر اجرا
        </caption>
        <thead>
          <tr className="border-b border-edge-strong text-cp-caption text-ink-muted">
            <th scope="col" className="px-3 py-2 text-start">
              مسیر / ارائه‌دهنده
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              توکن ورودی
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              توکن خروجی
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              مصرف و سقف
            </th>
            <th scope="col" className="px-3 py-2 text-start">
              هزینه
            </th>
          </tr>
        </thead>
        <tbody>
          {cost.map((row) => (
            <CostRow key={row.routeId} row={row} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
