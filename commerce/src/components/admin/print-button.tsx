'use client';

import { Printer } from 'lucide-react';

import { buttonClass } from '@/components/ui/primitives';

/**
 * The slip itself is a server component (it must render a stored order), so the
 * one browser-only affordance — `window.print()` — lives in this small client
 * sibling. It is marked `cp-no-print`, so the button never appears on the sheet
 * it produces.
 */
export function PrintButton() {
  return (
    <button
      type="button"
      className={`${buttonClass.primary} cp-no-print`}
      onClick={() => window.print()}
    >
      <Printer aria-hidden="true" size={16} /> چاپ فاکتور
    </button>
  );
}
