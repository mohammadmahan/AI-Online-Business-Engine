'use client';

import * as RadixDialog from '@radix-ui/react-dialog';
import type { ReactNode } from 'react';

/**
 * D-172 §2 — the panel's only modal primitive.
 *
 * Radix is used (not hand-rolled) because focus trapping, `aria-modal`, escape
 * handling and returning focus to the trigger are accessibility requirements,
 * not decoration — the same reason the control plane depends on it (D-171 §3).
 */
/**
 * Two chromes, one behaviour.
 *
 * `panel` is the merchant panel's D-171 §3 chrome and is the DEFAULT, so every
 * existing admin dialog renders exactly as before. `storefront` is the editorial
 * customer chrome (D-177): ivory surface, hairlines, display-face heading and the
 * warm-ink focus ring. It also carries `data-surface="storefront"` because Radix
 * portals the content OUTSIDE the storefront layout wrapper — without it the
 * scoped focus ring would never reach a drawer control.
 *
 * Only appearance changes between the two: focus trap, escape handling, focus
 * return, heading level and the close button's accessible name are shared.
 */
const SURFACE = {
  panel: {
    overlay: 'fixed inset-0 z-40 bg-ink/40',
    content:
      'fixed left-1/2 top-1/2 z-50 w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[--radius-cp] border border-edge bg-surface p-6 shadow-lg',
    title: 'text-cp-heading font-semibold text-ink',
    description: 'mt-1 text-cp-label text-ink-muted',
    close:
      'cp-target absolute start-4 top-4 rounded-[--radius-cp] border border-edge-strong px-2 py-1 text-cp-caption text-ink',
  },
  storefront: {
    overlay: 'fixed inset-0 z-40 bg-sf-inverse/35',
    content:
      // The drawer is fixed and vertically centred, so it must never grow past
      // the viewport: without a cap, a full basket pushed the checkout CTA below
      // the screen with no way to scroll to it.
      'fixed left-1/2 top-1/2 z-50 max-h-[calc(100dvh-2rem)] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-sf border border-sf-edge bg-sf-surface p-6 text-sf-ink shadow-xl',
    // `pe-12` reserves the inline-end gap the storefront close button occupies,
    // so a longer heading can never run underneath it (measured overlap at 390).
    title: 'pe-12 font-display text-sf-title font-semibold leading-snug text-sf-ink',
    description: 'mt-1.5 text-sf-caption leading-relaxed text-sf-ink-muted',
    close:
      'absolute end-4 top-4 inline-flex min-h-11 min-w-11 items-center justify-center rounded-sf border border-sf-edge-strong px-3 py-2 text-sf-caption text-sf-ink transition-colors hover:bg-sf-muted',
  },
} as const;

export function Modal({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  children,
  surface = 'panel',
  onOpenAutoFocus,
  onCloseAutoFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger?: ReactNode;
  title: string;
  description?: string;
  children: ReactNode;
  /** Visual chrome only. Defaults to the merchant panel's, so admin is untouched. */
  surface?: keyof typeof SURFACE;
  /**
   * Radix's own focus-lifecycle events, forwarded unchanged. They exist so the
   * storefront drawer — whose trigger is NOT a `Dialog.Trigger` — can remember
   * and restore its opener. Admin dialogs pass neither, so their focus behaviour
   * is exactly Radix's default.
   */
  onOpenAutoFocus?: (event: Event) => void;
  onCloseAutoFocus?: (event: Event) => void;
}) {
  const chrome = SURFACE[surface];
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger> : null}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className={chrome.overlay} />
        <RadixDialog.Content
          // Centring is PHYSICAL on purpose: `start-1/2` resolves to `right: 50%`
          // in RTL, which the physical `-translate-x-1/2` then pushes further
          // left — measured, that put the dialog at `left: -128px`, clipping it
          // off-screen. Physical `left` + a negative physical translate centres
          // it the same way in both writing directions.
          className={chrome.content}
          dir="rtl"
          data-surface={surface === 'storefront' ? 'storefront' : undefined}
          onOpenAutoFocus={onOpenAutoFocus}
          onCloseAutoFocus={onCloseAutoFocus}
        >
          <RadixDialog.Title className={chrome.title}>{title}</RadixDialog.Title>
          {description ? (
            <RadixDialog.Description className={chrome.description}>
              {description}
            </RadixDialog.Description>
          ) : null}
          <div className="mt-4">{children}</div>
          <RadixDialog.Close aria-label="بستن" className={chrome.close}>
            بستن
          </RadixDialog.Close>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
