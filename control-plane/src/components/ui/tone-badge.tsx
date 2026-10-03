import type { LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * Tone vocabulary for filled chips.
 *
 * Each tone pairs a status FILL with the foreground that is contrast-safe on
 * it (`text-on-*`), so a filled element can never pick an unreadable pairing.
 * Every combination below is enforced by `scripts/check-contrast.mjs`.
 */
export type Tone = 'neutral' | 'success' | 'warning' | 'danger';

const TONE_FILL: Record<Tone, string> = {
  // Neutral uses a control-strength border (≥ 3:1), not the decorative token.
  neutral: 'bg-surface-muted text-ink border border-edge-strong',
  success: 'bg-success text-on-success',
  warning: 'bg-warning text-on-warning',
  danger: 'bg-danger text-on-danger',
};

/**
 * A status chip that ALWAYS carries an icon and a Persian label, with the
 * English code as a secondary cue. Meaning never depends on colour alone
 * (`color-not-only`).
 */
export function ToneBadge({
  tone,
  label,
  code,
  Icon,
  detail,
  className,
}: {
  tone: Tone;
  label: string;
  code: string;
  Icon?: LucideIcon;
  detail?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'cp-target inline-flex items-center gap-2 rounded-full px-3 py-1',
        'text-cp-caption font-medium',
        TONE_FILL[tone],
        className,
      )}
    >
      {Icon ? <Icon aria-hidden="true" className="size-4 shrink-0" /> : null}
      <span>
        {label} <span className="opacity-80">({code})</span>
      </span>
      {detail ? <span className="opacity-80">· {detail}</span> : null}
    </span>
  );
}
