'use client';

import { OctagonAlert } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * Emergency kill-switch PLACEHOLDER.
 *
 * D-171 §6 forbids the UI from activating anything: the real kill switch is
 * the owner-gated D-139 runtime halt, reached through the canonical service
 * boundary, not from this surface. This control is deliberately inert and
 * says so — a control that looks live but does nothing is exactly the
 * anti-pattern the design rules call out ("Controls that look tappable but
 * do nothing"). It becomes functional only in the phase that wires the
 * owner-gated action.
 */
export function KillSwitchPlaceholder() {
  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      title="کلید اضطراری در این فاز غیرفعال است — فعال‌سازی فقط از مسیر مجاز مالک (D-139) انجام می‌شود"
      className={cn(
        'cp-target inline-flex items-center gap-2 rounded-[--radius-cp]',
        'border border-danger bg-surface px-3 py-2',
        'text-cp-label font-medium text-danger',
        'disabled:cursor-not-allowed disabled:opacity-60',
      )}
    >
      <OctagonAlert aria-hidden="true" className="size-4" />
      <span className="hidden lg:inline">توقف اضطراری</span>
      <span className="sr-only lg:hidden">توقف اضطراری (غیرفعال)</span>
    </button>
  );
}
