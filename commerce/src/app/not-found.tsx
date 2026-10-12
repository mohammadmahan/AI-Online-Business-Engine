import Link from 'next/link';

import { buttonClass } from '@/components/ui/primitives';

/**
 * D-172 — the 404 page.
 *
 * It lives at the app root so both surfaces use it: a product slug that is not
 * published (or was archived) lands here rather than on an empty page, which
 * matters because the storefront's `notFound()` is the honest answer for a
 * product that exists but is not for sale.
 */
export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col items-start justify-center gap-4 p-6">
      <p className="cp-code text-cp-caption text-ink-muted">404</p>
      <h1 className="text-cp-display font-bold text-ink">این صفحه پیدا نشد</h1>
      <p className="text-cp-body text-ink-muted">
        نشانی وارد‌شده وجود ندارد یا محصول مورد نظر دیگر در فروشگاه منتشر نشده است.
      </p>
      <p className="flex flex-wrap gap-2">
        <Link className={buttonClass.primary} href="/">
          بازگشت به فروشگاه
        </Link>
        <Link className={buttonClass.neutral} href="/catalog">
          فهرست محصولات
        </Link>
      </p>
    </div>
  );
}
