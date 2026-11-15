import { SectionEyebrow } from './storefront-primitives';

/**
 * The catalog's static header, shared by the page and its `loading.tsx`
 * boundary. Keeping one definition means the skeleton reserves the exact same
 * type and rule as the loaded page instead of approximating them (and drifting).
 */
export function CatalogPageHeader() {
  return (
    <header className="border-b border-sf-edge pb-8">
      <SectionEyebrow>فروشگاه پوشاک · کاتالوگ</SectionEyebrow>
      <h1 className="mt-2 font-display text-sf-title font-semibold text-sf-ink">
        همهٔ محصولات
      </h1>
      <p className="mt-3 max-w-2xl text-sf-caption leading-relaxed text-sf-ink-muted">
        فیلترها بی‌درنگ روی محصولات منتشرشده اعمال می‌شوند؛ تعداد محصولات هر دسته از همین فهرست
        محاسبه شده است.
      </p>
    </header>
  );
}