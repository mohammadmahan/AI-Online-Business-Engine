import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { CartDrawer } from '@/components/storefront/cart-drawer';
import { CartProvider } from '@/components/storefront/cart-provider';
import { StorefrontHeader } from '@/components/storefront/storefront-header';

/**
 * D-172 §3 — the customer storefront's chrome.
 *
 * The cart provider wraps the header, the pages and the drawer, so the badge, the
 * add-to-cart buttons and the checkout form all read ONE basket. The root layout
 * (D-172 Phase 3) no longer carries the admin navigation, so this shell is the
 * whole public surface.
 *
 * `data-surface="storefront"` marks the editorial visual system (see the `--sf-*`
 * block in `globals.css`): the merchant panel keeps the D-171 §3 measured tokens
 * untouched, and no storefront utility leaks into an admin page.
 */

export const metadata: Metadata = {
  title: {
    default: 'فروشگاه پوشاک',
    template: '%s · فروشگاه پوشاک',
  },
};

export default function StorefrontLayout({ children }: { children: ReactNode }) {
  return (
    <CartProvider>
      <div
        data-surface="storefront"
        className="flex min-h-dvh flex-col bg-sf-canvas text-sf-ink"
      >
        <StorefrontHeader />
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto w-full max-w-6xl flex-1 px-5 py-8 sm:px-8 sm:py-12"
        >
          {children}
        </main>
        <footer className="mt-16 border-t border-sf-edge">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-5 py-10 sm:px-8 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="font-display text-lg font-semibold text-sf-ink">فروشگاه پوشاک</p>
              <p className="mt-1 text-sf-caption text-sf-ink-muted">
                انتخاب رنگ و اندازه، بررسی موجودی و ثبت سفارش در یک مرحله.
              </p>
            </div>
            <p className="max-w-md text-sf-caption leading-relaxed text-sf-ink-muted">
              پرداخت آنلاین هنوز متصل نیست؛ سفارش‌ها با وضعیت «در انتظار پرداخت» ثبت می‌شوند و توسط
              فروشگاه بررسی می‌گردند.
            </p>
          </div>
        </footer>
        <CartDrawer />
      </div>
    </CartProvider>
  );
}
