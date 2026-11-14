/**
 * D-172 §3 — the storefront's fail-closed notice (D-171 §2.2).
 *
 * The merchant panel names the missing environment variable, because the owner
 * fixes it. A customer must not be told about `DATABASE_URL`: what they need to
 * know is that nothing is being shown and nothing can be ordered — and that is
 * exactly what it says, instead of rendering an empty shop that would read as
 * "this boutique sells nothing".
 *
 * Phase 2B (D-177): this is a CUSTOMER surface, so it uses the editorial notice
 * (hairline on ivory, display-face title, `role="status"` so the failure is
 * announced) rather than the panel's blue-on-muted warning Banner. The text is
 * unchanged — the message was already right; only the chrome was the panel's.
 */
export function StorefrontUnavailable({ what }: { what: string }) {
  return (
    <div role="status" className="rounded-sf border border-sf-edge bg-sf-surface p-6">
      <p className="font-display text-lg font-semibold text-sf-ink">
        {what} در این لحظه نمایش داده نمی‌شود
      </p>
      <p className="mt-2 max-w-2xl text-sf-caption leading-relaxed text-sf-ink-muted">
        فروشگاه به پایگاهِ دادهٔ خود متصل نیست؛ بنابراین هیچ محصولی نمایش داده نمی‌شود و سفارشی ثبت
        نمی‌شود. لطفاً کمی بعد دوباره تلاش کنید.
      </p>
    </div>
  );
}
