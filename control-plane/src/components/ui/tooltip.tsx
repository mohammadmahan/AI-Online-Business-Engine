import { Info } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * D-171 §3.5 / §10 (Phase 27.11) — accessible micro-help tooltip.
 *
 * Visibility is pure CSS: the panel stays `invisible` until its trigger is
 * hovered OR keyboard-focused (`group-focus-within`), so a help text needs no
 * client state, no hydration work and no anchor measurement — and it cannot
 * shift the layout, because it is an absolutely positioned overlay.
 *
 * The caller points the FOCUSABLE trigger at the panel with
 * `aria-describedby={id}`: screen readers then announce the explanation when
 * the trigger receives focus, even while the panel is visually hidden (a
 * hidden node referenced by `aria-describedby` still yields the description).
 * The panel itself carries an SVG icon plus a Persian sentence — never an
 * emoji (§3.5) — and uses only gate-enforced token pairs: `bg-surface`
 * + `text-ink` text and the control-strength `border-edge-strong` boundary.
 * The global `prefers-reduced-motion` rule collapses its fade to instant.
 */
export function Tooltip({
  id,
  text,
  className,
  children,
}: {
  /** Referenced by the trigger's `aria-describedby`. Must be unique per page. */
  id: string;
  /** One plain sentence — what this control does, in this view's vocabulary. */
  text: string;
  /** Layout of the wrapper (e.g. `flex w-full` for a full-width nav row). */
  className?: string;
  children: ReactNode;
}) {
  return (
    <span className={cn('group/tip relative inline-flex', className)}>
      {children}
      <span
        role="tooltip"
        id={id}
        className={cn(
          'pointer-events-none invisible absolute start-0 top-full z-20 mt-1',
          'w-max max-w-64 rounded-[--radius-cp] border border-edge-strong bg-surface p-2',
          'text-start text-cp-label text-ink shadow-sm opacity-0 transition-opacity duration-150',
          'group-hover/tip:visible group-hover/tip:opacity-100',
          'group-focus-within/tip:visible group-focus-within/tip:opacity-100',
        )}
      >
        <Info
          aria-hidden="true"
          className="me-1 inline size-3.5 shrink-0 align-[-2px] text-ink-muted"
        />
        {text}
      </span>
    </span>
  );
}
