import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4 text-center">
      <h1 className="text-cp-display font-bold text-ink">صفحه یافت نشد</h1>
      <p className="text-cp-label text-ink-muted">
        مسیر درخواستی در صفحه‌ی کنترل وجود ندارد. (NOT_FOUND)
      </p>
      <Link
        href="/dashboard"
        className="cp-target mx-auto rounded-[--radius-cp] bg-primary px-4 py-2 text-cp-label font-medium text-surface"
      >
        بازگشت به نمای فرماندهی
      </Link>
    </div>
  );
}
