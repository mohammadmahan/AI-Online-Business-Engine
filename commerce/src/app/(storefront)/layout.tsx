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
      <div className="flex min-h-dvh flex-col">
        <StorefrontHeader />
        <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
          {children}
        </main>
        <footer className="border-t border-edge bg-surface px-4 py-6">
          <p className="mx-auto max-w-6xl text-cp-caption text-ink-muted">
            فروشگاه پوشاک — پرداخت آنلاین هنوز متصل نیست؛ سفارش‌ها با وضعیت «در انتظار پرداخت» ثبت
            می‌شوند و توسط فروشگاه بررسی می‌گردند.
          </p>
        </footer>
        <CartDrawer />
      </div>
    </CartProvider>
  );
}
