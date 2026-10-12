'use client';

import { ShoppingBag } from 'lucide-react';
import Link from 'next/link';

import { formatCountFa } from '@/lib/format';
import { buttonClass } from '@/components/ui/primitives';

import { useCart } from './cart-provider';

/**
 * D-172 §3 — the customer header.
 *
 * The cart count appears only after the stored basket has been read
 * (`hydrated`), so the server-rendered markup and the first client render agree
 * and no zero silently turns into a real number.
 */
export function StorefrontHeader() {
  const { count, hydrated, openCart } = useCart();

  return (
    <header className="border-b border-edge bg-surface">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Link href="/" className="text-cp-heading font-bold text-ink">
          فروشگاه پوشاک
        </Link>
        <nav aria-label="بخش‌های فروشگاه" className="flex items-center gap-2">
          <Link className={buttonClass.neutral} href="/catalog">
            همهٔ محصولات
          </Link>
          <button
            type="button"
            className={buttonClass.primary}
            onClick={openCart}
            aria-haspopup="dialog"
            aria-label={
              hydrated && count > 0 ? `سبد خرید، ${formatCountFa(count)} کالا` : 'سبد خرید'
            }
          >
            <ShoppingBag aria-hidden="true" size={16} />
            سبد خرید
            {hydrated && count > 0 ? (
              <span className="cp-code rounded-[--radius-cp] border border-on-primary px-1.5 text-cp-caption">
                {formatCountFa(count)}
              </span>
            ) : null}
          </button>
        </nav>
      </div>
    </header>
  );
}
