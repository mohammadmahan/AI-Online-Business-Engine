'use client';

import { Minus, Plus, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRef } from 'react';

import { focusStorefrontLandmark, resolveFocusReturn } from '@/lib/focus-return';

import { canDecrementLine } from '@/lib/cart-rules';
import { MAX_LINE_QUANTITY } from '@/lib/checkout-rules';
import { formatCountFa, formatToman } from '@/lib/format';
import { Modal } from '@/components/ui/dialog';
import { sfButton } from '@/components/storefront/storefront-primitives';

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
 *
 * D-177 §Phase 2A — the drawer is a CUSTOMER surface, so it renders in the
 * storefront chrome (`surface="storefront"`): ivory surface, warm ink, hairlines,
 * display-face heading and the storefront focus ring. Every accessible name,
 * role, heading level, focus trap, Escape behaviour and live-region announcement
 * is unchanged by that restyle, and the admin `--cp-*` tokens are untouched.
 */
export function CartDrawer() {
  const { isOpen, openCart, closeCart, lines, subtotal, hydrated, setQuantity, remove } = useCart();
  /**
   * The element that had focus when the drawer opened (the header button in the
   * normal case, the PDP add button when adding opens the basket).
   *
   * Radix restores focus to a `Dialog.Trigger`, and the storefront has none —
   * the opener lives in the header — so without this the close dropped focus on
   * `<body>` (measured). `onOpenAutoFocus` runs BEFORE Radix moves focus into the
   * dialog, so the opener is still `document.activeElement` at that moment.
   */
  const openerRef = useRef<HTMLElement | null>(null);

  const rememberOpener = () => {
    const active = document.activeElement;
    openerRef.current = active instanceof HTMLElement && active !== document.body ? active : null;
  };

  const returnFocus = (event: Event) => {
    // Stop Radix's default (no trigger ⇒ focus falls to <body>), then restore.
    event.preventDefault();
    const opener = openerRef.current;
    openerRef.current = null;

    // 1) the element that opened the drawer, 2) the visible header cart
    // trigger, 3) the page's main heading — never <body>, never the unmounted
    // dialog, never an arbitrary hidden control.
    const trigger = document.querySelector<HTMLElement>('[data-cart-trigger]');
    const target = resolveFocusReturn(opener, trigger);
    if (target) {
      target.focus();
      return;
    }
    focusStorefrontLandmark(document);
  };

  return (
    <Modal
      open={isOpen}
      onOpenChange={(next) => (next ? openCart() : closeCart())}
      title="سبد خرید"
      description="تعداد هر قلم را می‌توانید همین‌جا تغییر دهید. مبلغ نهایی در مرحلهٔ پرداخت روی سرور محاسبه می‌شود."
      surface="storefront"
      onOpenAutoFocus={rememberOpener}
      onCloseAutoFocus={returnFocus}
    >
      {!hydrated ? (
        <p className="text-sf-caption text-sf-ink-muted">در حال خواندن سبد خرید…</p>
      ) : lines.length === 0 ? (
        <div className="flex flex-col gap-4">
          <p className="rounded-sf border border-dashed border-sf-edge-strong bg-sf-muted p-4 text-sf-caption leading-relaxed text-sf-ink-muted">
            سبد خرید خالی است. از فهرست محصولات یک رنگ و اندازه انتخاب کنید.
          </p>
          <Link className={`${sfButton.primary} w-full`} href="/catalog" onClick={closeCart}>
            رفتن به فهرست محصولات
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <ul className="flex max-h-80 flex-col gap-3 overflow-y-auto">
            {lines.map((line) => (
              <li
                key={line.variantId}
                className="flex gap-3 border-b border-sf-edge pb-3 last:border-b-0"
              >
                {line.imageUrl ? (
                  /* eslint-disable-next-line @next/next/no-img-element -- the media host is an open owner decision (D-172 G-5); next/image would need a remotePatterns entry for a host that does not exist yet. Same call as the admin uploader. */
                  <img
                    src={line.imageUrl}
                    alt={line.productTitle}
                    className="size-16 shrink-0 rounded-sf border border-sf-edge object-cover"
                  />
                ) : (
                  <span className="flex size-16 shrink-0 items-center justify-center rounded-sf border border-sf-edge bg-sf-muted text-sf-caption text-sf-ink-muted">
                    بدون تصویر
                  </span>
                )}

                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <Link
                    href={`/products/${line.productSlug}`}
                    className="font-display text-base font-semibold leading-snug text-sf-ink"
                    onClick={closeCart}
                  >
                    {line.productTitle}
                  </Link>
                  <p className="text-sf-caption text-sf-ink-muted">
                    اندازه <span className="sf-code">{line.size}</span> · رنگ {line.colorName}
                  </p>
                  <p className="text-sf-caption text-sf-ink-muted">
                    قیمت واحد: {formatToman(line.unitPrice)}
                  </p>

                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className={sfButton.icon}
                        aria-label={`کاهش تعداد ${line.productTitle}`}
                        /* At one piece the control is honest: lowering the
                           quantity is impossible, and deleting the line stays on
                           the labelled «حذف» button rather than behind a
                           decrement that silently removes the product. */
                        disabled={!canDecrementLine(line.quantity)}
                        onClick={() => setQuantity(line.variantId, line.quantity - 1)}
                      >
                        <Minus aria-hidden="true" size={16} />
                      </button>
                      <span
                        className="min-w-8 text-center text-sf-caption font-medium text-sf-ink"
                        aria-live="polite"
                      >
                        {formatCountFa(line.quantity)}
                      </span>
                      <button
                        type="button"
                        className={sfButton.icon}
                        aria-label={`افزودن یک عدد به ${line.productTitle}`}
                        disabled={line.quantity >= MAX_LINE_QUANTITY}
                        onClick={() => setQuantity(line.variantId, line.quantity + 1)}
                      >
                        <Plus aria-hidden="true" size={16} />
                      </button>
                    </div>
                    <button
                      type="button"
                      className={sfButton.compact}
                      aria-label={`حذف ${line.productTitle} از سبد خرید`}
                      onClick={() => remove(line.variantId)}
                    >
                      <Trash2 aria-hidden="true" size={16} />
                      حذف
                    </button>
                  </div>
                </div>

                <p className="shrink-0 text-sf-caption font-semibold text-sf-ink">
                  {formatToman(line.unitPrice * line.quantity)}
                </p>
              </li>
            ))}
          </ul>

          <dl className="flex items-center justify-between border-t border-sf-edge pt-3 text-sf-caption">
            <dt className="text-sf-ink-muted">جمع کالاها (نمایشی)</dt>
            <dd className="font-semibold text-sf-ink">{formatToman(subtotal)}</dd>
          </dl>

          <p className="rounded-sf border border-sf-edge bg-sf-muted p-2 text-sf-caption leading-relaxed text-sf-ink-muted">
            هزینهٔ ارسال، تخفیف و مبلغ نهایی پس از بررسی سبد روی سرور محاسبه می‌شود.
          </p>

          <Link className={`${sfButton.primary} w-full`} href="/checkout" onClick={closeCart}>
            ادامهٔ خرید و پرداخت
          </Link>
        </div>
      )}
    </Modal>
  );
}
