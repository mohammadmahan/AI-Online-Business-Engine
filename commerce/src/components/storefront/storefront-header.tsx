'use client';

import { ShoppingBag } from 'lucide-react';
import Link from 'next/link';

import { formatCountFa } from '@/lib/format';

import { useCart } from './cart-provider';
import { sfButton } from './storefront-primitives';

/**
 * D-172 §3 — the customer header.
 *
 * The cart count appears only after the stored basket has been read
 * (`hydrated`), so the server-rendered markup and the first client render agree
 * and no zero silently turns into a real number.
 *
 * Editorial treatment: a single hairline, the wordmark in the display face and a
 * quiet navigation row. Labels, roles and the accessible cart name are unchanged
 * from the pre-redesign header, so the storefront's E2E script keeps driving the
 * same contract.
 */
export function StorefrontHeader() {
  const { count, hydrated, openCart } = useCart();

  return (
    <header className="border-b border-sf-edge bg-sf-canvas">
      <div className="mx-auto flex w-full max-w-6xl flex-nowrap items-center justify-between gap-3 px-5 py-4 sm:gap-4 sm:px-8 sm:py-5">
        <Link href="/" className="group inline-flex shrink-0 flex-col gap-0.5">
          <span className="font-display text-lg font-semibold leading-none text-sf-ink sm:text-2xl">
            فروشگاه پوشاک
          </span>
          <span className="sf-eyebrow sf-eyebrow-latin text-[0.625rem] font-medium">
            Wardrobe Edit
          </span>
        </Link>

        <nav aria-label="بخش‌های فروشگاه" className="flex shrink-0 items-center gap-3 sm:gap-5">
          <Link className="sf-link whitespace-nowrap text-sf-caption font-medium" href="/catalog">
            همهٔ محصولات
          </Link>
          <button
            type="button"
            className={`${sfButton.quiet} px-4 sm:px-6`}
            onClick={openCart}
            aria-haspopup="dialog"
            aria-label={
              hydrated && count > 0 ? `سبد خرید، ${formatCountFa(count)} کالا` : 'سبد خرید'
            }
          >
            <ShoppingBag aria-hidden="true" size={15} />
            سبد خرید
            {hydrated && count > 0 ? (
              <span className="cp-code ms-1 text-sf-caption">({formatCountFa(count)})</span>
            ) : null}
          </button>
        </nav>
      </div>
    </header>
  );
}
