import { Banner } from '@/components/ui/primitives';

/**
 * D-172 §3 — the storefront's fail-closed notice (D-171 §2.2).
 *
 * The merchant panel names the missing environment variable, because the owner
 * fixes it. A customer must not be told about `DATABASE_URL`: what they need to
 * know is that nothing is being shown and nothing can be ordered — and that is
 * exactly what it says, instead of rendering an empty shop that would read as
 * "this boutique sells nothing".
 */
export function StorefrontUnavailable({ what }: { what: string }) {
  return (
    <Banner tone="warning" title={`${what} در این لحظه نمایش داده نمی‌شود`}>
      فروشگاه به پایگاهِ دادهٔ خود متصل نیست؛ بنابراین هیچ محصولی نمایش داده نمی‌شود و سفارشی ثبت
      نمی‌شود. لطفاً کمی بعد دوباره تلاش کنید.
    </Banner>
  );
}
