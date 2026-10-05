import { cn } from '@/lib/utils';

/**
 * A measured bar with its value stated as text next to it.
 *
 * The visual fill is derived from a real reading only; a surface without
 * readings renders NO bar at all, because a zero-length bar would read as
 * "measured, and empty" (D-171 §2.2). `role="meter"` carries the numeric value
 * to assistive technology, and the fill is never the only carrier of meaning.
 */
export function MeterBar({
  label,
  value,
  max,
  valueText,
  fillClass,
}: {
  label: string;
  value: number;
  max: number;
  valueText: string;
  fillClass: string;
}) {
  const ratio = max <= 0 ? 0 : Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-cp-caption text-ink-muted">{label}</span>
        <span className="text-cp-caption font-medium text-ink tabular-nums">{valueText}</span>
      </div>
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-label={`${label} — ${valueText}`}
        className={cn('h-2 overflow-hidden rounded-full border border-edge bg-surface-muted')}
      >
        <div aria-hidden="true" className={cn('h-full', fillClass)} style={{ width: `${ratio}%` }} />
      </div>
    </div>
  );
}
