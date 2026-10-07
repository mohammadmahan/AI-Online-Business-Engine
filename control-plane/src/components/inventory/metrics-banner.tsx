import { AlertTriangle, Boxes, GitCompareArrows, PackageX } from 'lucide-react';

import { Card } from '@/components/ui/card';
import { VIEW_GATE_CLASS } from '@/components/ui/view-gate';
import { formatNumber } from '@/lib/format';
import type { InventorySummary } from '@/types/inventory';

/**
 * Metrics banner (D-171 §5.3): Total SKUs, Low Stock Warnings, Out of Stock and
 * the active WooCommerce Drift Count.
 *
 * The counts are DERIVED from the rendered rows (`summarizeInventory` in the
 * mock provider) and the build-time guard rejects a banner that disagrees with
 * its own table, so the headline can never drift from the data.
 *
 * A non-zero warning count turns its own figure into the warning/danger ink;
 * zero stays neutral ink — an absence of alerts is not painted green, because
 * nothing here is evidence of health, only a count of open items.
 */
export function MetricsBanner({ summary }: { summary: InventorySummary }) {
  const metrics = [
    {
      key: 'total',
      label: 'کل SKUها',
      code: 'TOTAL_SKUS',
      value: summary.totalSkus,
      Icon: Boxes,
      ink: 'text-ink',
    },
    {
      key: 'low',
      label: 'هشدار موجودی کم',
      code: 'LOW_STOCK',
      value: summary.lowStockCount,
      Icon: AlertTriangle,
      ink: summary.lowStockCount > 0 ? 'text-warning' : 'text-ink',
    },
    {
      key: 'out',
      label: 'ناموجود',
      code: 'OUT_OF_STOCK',
      value: summary.outOfStockCount,
      Icon: PackageX,
      ink: summary.outOfStockCount > 0 ? 'text-danger' : 'text-ink',
    },
    {
      key: 'drift',
      label: 'واگرایی WooCommerce',
      code: 'DRIFT_DETECTED',
      value: summary.driftCount,
      Icon: GitCompareArrows,
      ink: summary.driftCount > 0 ? 'text-danger' : 'text-ink',
    },
  ];

  return (
    <section aria-label="شاخص‌های موجودی" className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.map((metric) => (
          <Card key={metric.key} className="p-3 sm:p-4">
            <div className="flex items-center gap-2">
              <metric.Icon aria-hidden="true" className={`size-4 shrink-0 ${metric.ink}`} />
              <p className="text-cp-caption text-ink-muted">
                {metric.label}{' '}
                {/* Metric machine key (TOTAL_SKUS, DRIFT_DETECTED, …): console
                    asset — the Business view keeps the label and the count. */}
                <span
                  data-view-gate="technical"
                  data-surface="inventory-metrics-codes"
                  className={`font-mono opacity-80 ${VIEW_GATE_CLASS.technical}`}
                >
                  ({metric.code})
                </span>
              </p>
            </div>
            <p
              className={`mt-2 text-cp-display font-bold tabular-nums ${metric.ink}`}
            >
              {formatNumber(metric.value)}
            </p>
          </Card>
        ))}
      </div>
      {/* Plain-Persian stock totals stay readable in both views; only the
          machine metric keys above are console assets. */}
      <p className="text-cp-caption text-ink-muted">
        مجموع موجودی انبار: <span className="tabular-nums">{formatNumber(summary.totalStockUnits)}</span>{' '}
        واحد · شمار در انتظار همگام‌سازی:{' '}
        <span className="tabular-nums">{formatNumber(summary.pendingSyncCount)}</span> · شمار
        خطای همگام‌سازی: <span className="tabular-nums">{formatNumber(summary.syncErrorCount)}</span>
      </p>
    </section>
  );
}
