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
export function Modal({
  open,
  onOpenChange,
  trigger,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger?: ReactNode;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger> : null}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <RadixDialog.Content
          // Centring is PHYSICAL on purpose: `start-1/2` resolves to `right: 50%`
          // in RTL, which the physical `-translate-x-1/2` then pushes further
          // left — measured, that put the dialog at `left: -128px`, clipping it
          // off-screen. Physical `left` + a negative physical translate centres
          // it the same way in both writing directions.
          className="fixed left-1/2 top-1/2 z-50 w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-[--radius-cp] border border-edge bg-surface p-6 shadow-lg"
          dir="rtl"
        >
          <RadixDialog.Title className="text-cp-heading font-semibold text-ink">
            {title}
          </RadixDialog.Title>
          {description ? (
            <RadixDialog.Description className="mt-1 text-cp-label text-ink-muted">
              {description}
            </RadixDialog.Description>
          ) : null}
          <div className="mt-4">{children}</div>
          <RadixDialog.Close
            aria-label="بستن"
            className="cp-target absolute start-4 top-4 rounded-[--radius-cp] border border-edge-strong px-2 py-1 text-cp-caption text-ink"
          >
            بستن
          </RadixDialog.Close>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
