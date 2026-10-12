'use client';

import { Minus, Plus, Trash2 } from 'lucide-react';
import Link from 'next/link';

import { MAX_LINE_QUANTITY } from '@/lib/checkout-rules';
import { formatCountFa, formatToman } from '@/lib/format';
import { Modal } from '@/components/ui/dialog';
import { buttonClass } from '@/components/ui/primitives';
import { cn } from '@/lib/utils';

import { useCart } from './cart-provider';

/**
 * D-172 §3.4 — the slide-over cart drawer.
 *
 * Radix's dialog primitive supplies the focus trap, escape handling and focus
 * return, so the drawer is usable with a keyboard and a screen reader rather
 * than merely looking modal. Quantities are stepped with real buttons (a number
 * input with spinner arrows is unusable on a phone), and each control's
 * accessible name says which line it affects.
 *
 * The subtotal here is explicitly labelled as display-only: the authoritative
 * totals are computed on the server at checkout.
 */
export function CartDrawer() {
  const { isOpen, openCart, closeCart, lines, subtotal, hydrated, setQuantity, remove } = useCart();

  return (
    <Modal
      open={isOpen}
      onOpenChange={(next) => (next ? openCart() : closeCart())}
      title="سبد خرید"
      description="تعداد هر قلم را می‌توانید همین‌جا تغییر دهید. مبلغ نهایی در مرحلهٔ پرداخت روی سرور محاسبه می‌شود."
    >
      {!hydrated ? (
        <p className="text-cp-label text-ink-muted">در حال خواندن سبد خرید…</p>
      ) : lines.length === 0 ? (
        <div className="flex flex-col gap-3">
          <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
            سبد خرید خالی است. از فهرست محصولات یک رنگ و اندازه انتخاب کنید.
          </p>
          <Link className={buttonClass.primary} href="/catalog" onClick={closeCart}>
            رفتن به فهرست محصولات
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <ul className="flex max-h-80 flex-col gap-3 overflow-y-auto">
            {lines.map((line) => (
              <li
                key={line.variantId}
                className="flex gap-3 border-b border-edge pb-3 last:border-b-0"
              >
                {line.imageUrl ? (
                  /* eslint-disable-next-line @next/next/no-img-element -- the media host is an open owner decision (D-172 G-5); next/image would need a remotePatterns entry for a host that does not exist yet. Same call as the admin uploader. */
                  <img
                    src={line.imageUrl}
                    alt={line.productTitle}
                    className="size-16 shrink-0 rounded-[--radius-cp] border border-edge object-cover"
                  />
                ) : (
                  <span className="flex size-16 shrink-0 items-center justify-center rounded-[--radius-cp] border border-edge bg-surface-muted text-cp-caption text-ink-muted">
                    بدون تصویر
                  </span>
                )}

                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <Link
                    href={`/products/${line.productSlug}`}
                    className="text-cp-label font-semibold text-ink"
                    onClick={closeCart}
                  >
                    {line.productTitle}
                  </Link>
                  <p className="text-cp-caption text-ink-muted">
                    اندازه <span className="cp-code">{line.size}</span> · رنگ {line.colorName}
                  </p>
                  <p className="text-cp-caption text-ink-muted">
                    قیمت واحد: {formatToman(line.unitPrice)}
                  </p>

                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className={cn(buttonClass.neutral, 'px-2')}
                        aria-label={`کاهش تعداد ${line.productTitle}`}
                        onClick={() => setQuantity(line.variantId, line.quantity - 1)}
                      >
                        <Minus aria-hidden="true" size={16} />
                      </button>
                      <span
                        className="min-w-8 text-center text-cp-label text-ink"
                        aria-live="polite"
                      >
                        {formatCountFa(line.quantity)}
                      </span>
                      <button
                        type="button"
                        className={cn(buttonClass.neutral, 'px-2')}
                        aria-label={`افزودن یک عدد به ${line.productTitle}`}
                        disabled={line.quantity >= MAX_LINE_QUANTITY}
                        onClick={() => setQuantity(line.variantId, line.quantity + 1)}
                      >
                        <Plus aria-hidden="true" size={16} />
                      </button>
                    </div>
                    <button
                      type="button"
                      className={cn(buttonClass.danger, 'px-2')}
                      aria-label={`حذف ${line.productTitle} از سبد خرید`}
                      onClick={() => remove(line.variantId)}
                    >
                      <Trash2 aria-hidden="true" size={16} />
                      حذف
                    </button>
                  </div>
                </div>

                <p className="shrink-0 text-cp-label font-semibold text-ink">
                  {formatToman(line.unitPrice * line.quantity)}
                </p>
              </li>
            ))}
          </ul>

          <dl className="flex items-center justify-between border-t border-edge pt-3 text-cp-label">
            <dt className="text-ink-muted">جمع کالاها (نمایشی)</dt>
            <dd className="font-semibold text-ink">{formatToman(subtotal)}</dd>
          </dl>

          <p className="rounded-[--radius-cp] border border-edge bg-surface-muted p-2 text-cp-caption text-ink-muted">
            هزینهٔ ارسال، تخفیف و مبلغ نهایی پس از بررسی سبد روی سرور محاسبه می‌شود.
          </p>

          <Link className={buttonClass.primary} href="/checkout" onClick={closeCart}>
            ادامهٔ خرید و پرداخت
          </Link>
        </div>
      )}
    </Modal>
  );
}
