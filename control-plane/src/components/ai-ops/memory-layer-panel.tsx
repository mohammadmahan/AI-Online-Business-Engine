import { Network } from 'lucide-react';

import { MEMORY_STATE_META } from '@/components/ai-ops/status-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatNumber, formatTimeUtc } from '@/lib/format';
import type { MemoryLayerStatus } from '@/types/ai-ops';

/**
 * Shared-memory layer panel (D-171 §5.5 `/ai-engine`).
 *
 * The layer is PLANNED behind the D-045 owner gate (D-142), so this panel's
 * steady state is `NOT_CONNECTED` with NO namespaces and NO counts: an
 * unconnected layer has nothing to enumerate, and rendering `0` would read as a
 * measurement (D-171 §2.2). Namespaces appear only when the state is a
 * connected one, and the panel states which seam produced the reading.
 */
export function MemoryLayerPanel({ memory }: { memory: MemoryLayerStatus }) {
  const meta = MEMORY_STATE_META[memory.state];
  const connected = memory.state === 'CONNECTED' || memory.state === 'DEGRADED';

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge tone={meta.tone} label={meta.label} code={meta.code} Icon={meta.Icon} />
        <span className="text-cp-caption text-ink-muted">
          منبع:{' '}
          <span className="font-mono" dir="ltr">
            {memory.provenance}
          </span>
        </span>
      </div>

      <p className="text-cp-label text-ink">{memory.detailFa}</p>

      {connected ? (
        <div className="flex flex-col gap-2">
          <dl className="grid gap-2 sm:grid-cols-3">
            <div className="rounded-[--radius-cp] border border-edge bg-surface-muted p-3">
              <dt className="text-cp-caption text-ink-muted">تعداد بردارها</dt>
              <dd className="text-cp-heading font-bold tabular-nums text-ink" dir="ltr">
                {memory.totalVectors === null ? '—' : formatNumber(memory.totalVectors)}
              </dd>
            </div>
            <div className="rounded-[--radius-cp] border border-edge bg-surface-muted p-3">
              <dt className="text-cp-caption text-ink-muted">حجم ذخیره‌شده (بایت)</dt>
              <dd className="text-cp-heading font-bold tabular-nums text-ink" dir="ltr">
                {memory.totalBytes === null ? '—' : formatNumber(memory.totalBytes)}
              </dd>
            </div>
            <div className="rounded-[--radius-cp] border border-edge bg-surface-muted p-3">
              <dt className="text-cp-caption text-ink-muted">آخرین اندازه‌گیری</dt>
              <dd className="text-cp-heading font-bold tabular-nums text-ink">
                {memory.lastMeasuredUtc === null ? (
                  'هرگز'
                ) : (
                  <>
                    <time dateTime={memory.lastMeasuredUtc}>
                      {formatTimeUtc(memory.lastMeasuredUtc)}
                    </time>{' '}
                    UTC
                  </>
                )}
              </dd>
            </div>
          </dl>

          <ul className="flex flex-col gap-1">
            {memory.namespaces.map((namespace) => (
              <li
                key={namespace.name}
                className="flex items-baseline justify-between gap-2 rounded-[--radius-cp] border border-edge bg-surface p-2 text-cp-caption"
              >
                <span className="font-mono text-ink" dir="ltr">
                  {namespace.name}
                </span>
                <span className="text-ink-muted" dir="ltr">
                  {formatNumber(namespace.vectors)} · {formatNumber(namespace.bytes)} B
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3">
          <p className="font-mono text-cp-caption text-ink-muted" dir="ltr">
            NAMESPACES: UNAVAILABLE
          </p>
          <p className="mt-1 flex items-start gap-2 text-cp-caption text-ink-muted">
            <Network aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            هیچ نام‌فضا و هیچ شمارشی گزارش نمی‌شود، زیرا هیچ اتصالی برقرار نشده است؛ نمایش «صفر» به‌جای
            اندازه‌گیری ممنوع است (fail-closed).
          </p>
        </div>
      )}
    </div>
  );
}
