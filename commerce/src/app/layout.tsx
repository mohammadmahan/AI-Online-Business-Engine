import type { Metadata, Viewport } from 'next';
import { Vazirmatn } from 'next/font/google';
import Link from 'next/link';

import { isDatabaseConfigured } from '@/server/db-context';

import './globals.css';

/**
 * D-172 §2 — merchant admin shell.
 *
 * Vazirmatn is self-hosted at build time by `next/font`, so the running panel
 * makes no external request for typography (D-171 §3.1); RTL is the default and
 * `lang="fa"` is declared once here.
 */
const vazirmatn = Vazirmatn({
  subsets: ['arabic', 'latin'],
  display: 'swap',
  variable: '--font-vazirmatn',
});

export const metadata: Metadata = {
  title: {
    default: 'پنل مدیریت فروشگاه — D-172',
    template: '%s · پنل فروشگاه',
  },
  description:
    'پنل مدیریت فروشگاهی (D-172): محصولات، موجودی، سفارش‌ها و تخفیف‌ها. fail-closed و بدون اعتبارنامهٔ داخلی.',
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
};

const NAV = [
  { href: '/admin', label: 'نمای کلی' },
  { href: '/admin/products/new', label: 'افزودن محصول' },
  { href: '/admin/inventory', label: 'موجودی و قیمت' },
  { href: '/admin/orders', label: 'سفارش‌ها' },
  { href: '/admin/promotions', label: 'تخفیف‌ها' },
] as const;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Rendered once for the whole shell: when the canonical connection is absent
  // the panel says so up front instead of failing page by page (D-171 §2.2).
  const connected = isDatabaseConfigured();

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
        <div className="flex min-h-dvh flex-col">
          <header className="cp-no-print border-b border-edge bg-surface">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
              <p className="text-cp-label font-semibold text-ink">پنل مدیریت فروشگاه</p>
              <span
                className={
                  connected
                    ? 'rounded-[--radius-cp] border border-success bg-success px-2 py-0.5 text-cp-caption text-on-success'
                    : 'rounded-[--radius-cp] border border-warning bg-warning px-2 py-0.5 text-cp-caption text-on-warning'
                }
              >
                {connected ? 'اتصال به پایگاهِ داده: تنظیم‌شده' : 'اتصال به پایگاهِ داده: تنظیم‌نشده'}
              </span>
            </div>
            <nav aria-label="بخش‌های پنل" className="mx-auto max-w-6xl px-4 pb-3">
              <ul className="flex flex-wrap gap-2">
                {NAV.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="cp-target inline-flex items-center rounded-[--radius-cp] border border-edge-strong bg-surface px-3 py-2 text-cp-label text-ink"
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </header>
          <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
