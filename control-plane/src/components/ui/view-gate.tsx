import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * D-171 §2.3 / §10 — Phase 27.13 view-isolation gate.
 *
 * ONE gate mechanism for the whole control plane: a Tailwind arbitrary variant
 * bound to the pre-paint `data-view-mode` attribute on `<html>` that Phase 27.9
 * writes before first paint (see `lib/context/view-mode-context.tsx`). The same
 * mechanism already gates the Phase 27.10 sidebar and the Phase 27.12 Business
 * card; 27.13 extends it to every technical/diagnostic surface instead of
 * inventing a second one.
 *
 * ── Why the attribute and not `useViewMode()` ───────────────────────────────
 * The active view is decided BEFORE the first paint, so gating in CSS means the
 * correct surface set is on screen in the very first frame: no hydration flash,
 * no flicker, no layout jump when the operator switches views, and no dependence
 * on JavaScript having hydrated. The rule the owner approved for 27.10 (recorded
 * in D-171 §10 and DECISIONS.md row 72) is applied unchanged — this module does
 * not read the view state in JS either.
 *
 * ── Two applications, one source of truth ──────────────────────────────────
 * - `<TechnicalOnly>` / `<BusinessOnly>` wrap a subtree. The wrapper renders
 *   `display: contents` while its view is active, so it generates NO box and the
 *   wrapped markup participates in the parent layout exactly as before
 *   (flex/grid item placement is unchanged); when the other view is active the
 *   wrapper is `display: none`, which removes the whole subtree from layout, from
 *   the tab order and from the accessibility tree.
 * - `VIEW_GATE_CLASS` is applied directly where a wrapper is impossible or wrong
 *   — a `<td>`/`<th>` (a row of a business table whose only machine-identifier
 *   column must not reach the Business view), or an element that already owns the
 *   layout.
 *
 * ── Census hooks ───────────────────────────────────────────────────────────
 * Every gated region carries `data-view-gate="business|technical"` and a stable
 * `data-surface` id. `scripts/check-view-isolation.mjs` reads those hooks to
 * produce the technical-asset census and to prove BOTH directions: a Business
 * surface is never present in the technical console, and every declared technical
 * asset is still rendered in full there (nothing removed, nothing mocked out).
 */
export const VIEW_GATE_CLASS = {
  /** Belongs to the Business view: hidden while the console is active. */
  business: '[[data-view-mode=technical]_&]:hidden',
  /** Belongs to the technical console: hidden while the Business view is active. */
  technical: '[[data-view-mode=business]_&]:hidden',
} as const;

export type GateView = keyof typeof VIEW_GATE_CLASS;

interface GateProps {
  /** Stable census id, read by `scripts/check-view-isolation.mjs`. */
  surface: string;
  children: ReactNode;
  /** Extra utilities for the wrapper itself (rarely needed: it is `contents`). */
  className?: string;
}

function Gate({ view, surface, children, className }: GateProps & { view: GateView }) {
  return (
    <div
      data-view-gate={view}
      data-surface={surface}
      className={cn('contents', VIEW_GATE_CLASS[view], className)}
    >
      {children}
    </div>
  );
}

/** Renders its children in the Business view only (the default view). */
export function BusinessOnly({ surface, children, className }: GateProps) {
  return (
    <Gate view="business" surface={surface} className={className}>
      {children}
    </Gate>
  );
}

/** Renders its children in the technical console only (never the default view). */
export function TechnicalOnly({ surface, children, className }: GateProps) {
  return (
    <Gate view="technical" surface={surface} className={className}>
      {children}
    </Gate>
  );
}
