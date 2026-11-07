import type { Metadata } from 'next';
import Link from 'next/link';

import { logoutAction } from '@/server/actions/admin-auth';
import { getAdminSession } from '@/server/auth/admin-request';
import { isDatabaseConfigured } from '@/server/db-context';

/**
 * D-172 §2 — the merchant panel's chrome.
 *
 * This moved out of the root layout when Phase 3 added a customer storefront:
 * the panel's navigation and its connection badge belong to `/admin` alone, and
 * the storefront must not inherit either. The badge is rendered once for the
 * whole admin shell, so when the canonical connection is absent the panel says
 * so up front instead of failing page by page (D-171 §2.2).
 *
 * `robots: noindex` lives here too: a merchant back office must never be
 * indexed, while the storefront is a public shop.
 *
 * Phase 4 added the sign-out control and made the navigation conditional: on the
 * login screen there is no session and therefore no panel to navigate, so the
 * shell renders a bare header instead of links a visitor cannot use.
 */

export const metadata: Metadata = {
  title: {
    default: 'پنل مدیریت فروشگاه — D-172',
    template: '%s · پنل فروشگاه',
  },
  robots: { index: false, follow: false },
};

const NAV = [
  { href: '/admin', label: 'نمای کلی' },
  { href: '/admin/products/new', label: 'افزودن محصول' },
  { href: '/admin/categories', label: 'دسته‌بندی‌ها' },
  { href: '/admin/inventory', label: 'موجودی و قیمت' },
  { href: '/admin/orders', label: 'سفارش‌ها' },
  { href: '/admin/promotions', label: 'تخفیف‌ها' },
] as const;

export default async function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const connected = isDatabaseConfigured();
  const session = await getAdminSession();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="cp-no-print border-b border-edge bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <p className="text-cp-label font-semibold text-ink">پنل مدیریت فروشگاه</p>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={
                connected
                  ? 'rounded-[--radius-cp] border border-success bg-success px-2 py-0.5 text-cp-caption text-on-success'
                  : 'rounded-[--radius-cp] border border-warning bg-warning px-2 py-0.5 text-cp-caption text-on-warning'
              }
            >
              {connected ? 'اتصال به پایگاهِ داده: تنظیم‌شده' : 'اتصال به پایگاهِ داده: تنظیم‌نشده'}
            </span>
            {session === null ? null : (
              <>
                <span className="text-cp-caption text-ink-muted">
                  کاربر: <span className="cp-code">{session.username}</span>
                </span>
                <form action={logoutAction}>
                  <button type="submit" className="cp-target rounded-[--radius-cp] border border-edge-strong bg-surface px-3 py-1.5 text-cp-caption text-ink">
                    خروج
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
        {session === null ? null : (
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
        )}
      </header>
      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">
        {children}
      </main>
    </div>
  );
}
