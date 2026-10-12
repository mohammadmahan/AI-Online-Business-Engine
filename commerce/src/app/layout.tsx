import type { Metadata, Viewport } from 'next';
import { Vazirmatn } from 'next/font/google';

import './globals.css';

/**
 * D-172 — the document shell, shared by both surfaces.
 *
 * This file owns only what is true for EVERY page: the language and direction,
 * the self-hosted font, the design tokens and the skip link. The merchant panel
 * and the customer storefront each render their own chrome, in
 * `app/admin/layout.tsx` and `app/(storefront)/layout.tsx` respectively — so a
 * customer never sees the admin navigation and a merchant never sees the cart.
 *
 * Vazirmatn is self-hosted at build time by `next/font`, so neither surface makes
 * an external request for typography (D-171 §3.1). RTL is the default and
 * `lang="fa"` is declared once here.
 */
const vazirmatn = Vazirmatn({
  subsets: ['arabic', 'latin'],
  display: 'swap',
  variable: '--font-vazirmatn',
});

export const metadata: Metadata = {
  title: {
    default: 'فروشگاه پوشاک',
    template: '%s · فروشگاه پوشاک',
  },
  description:
    'فروشگاه پوشاک (D-172): فهرست محصولات، صفحهٔ محصول و تسویهٔ خرید — با اتصال fail-closed به پایگاهِ دادهٔ مرجع.',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // `suppressHydrationWarning` on BOTH top-level tags is deliberate and
    // applies only to these two elements (React does not suppress their
    // subtree). Browser extensions — ColorZilla's `cz-shortcut-listen`, ad
    // blockers, password managers — inject attributes into `<html>`/`<body>`
    // before hydration, which React reports as an attribute mismatch it
    // cannot reconcile: the injected attribute exists in no server render and
    // in no source file, so there is nothing for the app to fix. Warning is
    // suppressed here instead of leaving a permanent false alarm that would
    // mask genuine mismatches deeper in the tree.
    <html
      lang="fa"
      dir="rtl"
      data-theme="light"
      className={vazirmatn.variable}
      suppressHydrationWarning
    >
      <body className="min-h-dvh" suppressHydrationWarning>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:start-2 focus:z-50 focus:rounded-[--radius-cp] focus:bg-primary focus:px-4 focus:py-2 focus:text-on-primary"
        >
          پرش به محتوای اصلی
        </a>
        {children}
      </body>
    </html>
  );
}
