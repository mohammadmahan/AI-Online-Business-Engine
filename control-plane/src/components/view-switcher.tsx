'use client';

import { Store, Terminal } from 'lucide-react';

import { Tooltip } from '@/components/ui/tooltip';
import { useViewMode, type ViewMode } from '@/lib/context/view-mode-context';
import { cn } from '@/lib/utils';

interface ViewOption {
  mode: ViewMode;
  /** Persian label — the primary carrier of meaning. */
  label: string;
  /** English code, kept for traceability (D-171 §3.5). */
  code: string;
  /** Micro-help: what switching to this view gives the operator (27.11). */
  tip: string;
  Icon: typeof Store;
}

const OPTIONS: readonly ViewOption[] = [
  {
    mode: 'business',
    label: 'مدیریت فروشگاه',
    code: 'BUSINESS',
    tip: 'نمای سادهٔ مدیریت روزمره فروشگاه — بدون اصطلاح فنی.',
    Icon: Store,
  },
  {
    mode: 'technical',
    label: 'کنسول زیرساخت',
    code: 'TECHNICAL',
    // Plain Persian: this control is visible in BOTH views, so its own copy may
    // not carry console vocabulary (Phase 27.13 isolation gate).
    tip: 'نمای تخصصی برای عیب‌یابی و دیدن جزئیات کامل فنی همین صفحه.',
    Icon: Terminal,
  },
];

/**
 * D-171 §2.3 — header dual-view switcher (Phase 27.9; micro-help in 27.11).
 *
 * An accessible two-option segmented control. Meaning never depends on colour
 * alone: every segment carries an icon plus a Persian label and an English
 * code, and the active segment is exposed with `aria-pressed` AND announced
 * through a polite live region. Both options are always rendered, so switching
 * never changes the control's size (zero layout shift), and RTL order is
 * inherited from the document rather than hardcoded.
 *
 * Each segment also carries a keyboard-focusable micro-help tooltip
 * (`aria-describedby`, hover + focus triggered, token-only) explaining what
 * the view is for, so neither view has to be discovered by trial.
 *
 * Active/inactive colours use only gate-enforced token pairs: the active fill
 * is `bg-primary text-surface` (the same contrast-checked pairing as the active
 * sidebar link), and inactive text sits on the muted/surface tokens.
 */
export function ViewSwitcher() {
  const { mode, setMode } = useViewMode();

  return (
    <div
      role="group"
      aria-label="انتخاب نمای صفحه"
      className={cn(
        'cp-target inline-flex items-center gap-1 rounded-[--radius-cp]',
        'border border-edge-strong bg-surface-muted p-1',
      )}
    >
      {OPTIONS.map((option) => {
        const active = mode === option.mode;
        const Icon = option.Icon;
        const id = `view-tip-${option.mode}`;
        return (
          <Tooltip key={option.mode} id={id} text={option.tip}>
            <button
              type="button"
              aria-pressed={active}
              aria-label={`${option.label} (${option.code})`}
              aria-describedby={id}
              onClick={() => setMode(option.mode)}
              className={cn(
                'cp-target inline-flex items-center gap-2 rounded-[--radius-cp]',
                'px-3 py-1.5 text-cp-label font-medium transition-colors',
                active
                  ? 'bg-primary text-surface'
                  : 'text-ink hover:bg-surface',
              )}
            >
              <Icon aria-hidden="true" className="size-4 shrink-0" />
              <span aria-hidden="true" className="hidden sm:inline">
                {option.label}
              </span>
            </button>
          </Tooltip>
        );
      })}
      <span aria-live="polite" className="sr-only">
        {mode === 'business'
          ? 'نمای مدیریت فروشگاه فعال است'
          : 'کنسول زیرساخت فعال است'}
      </span>
    </div>
  );
}
