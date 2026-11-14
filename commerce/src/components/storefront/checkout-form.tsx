'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';
import type { ReactNode } from 'react';

import type { CheckoutTotals, OrderPlaced, PlaceOrderResult } from '@/contracts/storefront';
import {
  checkoutIdempotencyKey,
  clearCheckoutIdempotencyKey,
  type CheckoutIntent,
  type CheckoutKeyStorage,
} from '@/lib/checkout-idempotency';
import { type CheckoutFieldErrors, submitCheckout } from '@/lib/checkout-submit';
import { MAX_LINE_QUANTITY, computeCheckoutTotals } from '@/lib/checkout-rules';
import { fieldA11y } from '@/lib/field-a11y';
import { formatCountFa, formatToman } from '@/lib/format';
import {
  DEFAULT_SHIPPING_METHOD_ID,
  NO_ELIGIBLE_CARRIER_MESSAGE,
  eligibleShippingOptions,
  estimateParcel,
  type ShippingConfig,
} from '@/lib/shipping';
import {
  CHECKOUT_TOTAL_LABELS,
  PAYMENT_STATUS_LABELS,
} from '@/lib/storefront-display';
import { cn } from '@/lib/utils';
import { checkCartAvailabilityAction, placeOrderAction } from '@/server/actions/storefront';

import { useCart } from './cart-provider';
import { SectionEyebrow, sfButton, sfField } from './storefront-primitives';

/**
 * `sessionStorage` when the browser allows it; otherwise an in-page fallback so
 * a blocked storage costs reusable keys, never the ability to checkout.
 */
const fallbackKeyStorage = new Map<string, string>();
const noopKeyStorage: CheckoutKeyStorage = {
  getItem: (key) => fallbackKeyStorage.get(key) ?? null,
  setItem: (key, value) => {
    fallbackKeyStorage.set(key, value);
  },
  removeItem: (key) => {
    fallbackKeyStorage.delete(key);
  },
};

function checkoutKeyStorage(): CheckoutKeyStorage {
  try {
    return window.sessionStorage;
  } catch {
    return noopKeyStorage;
  }
}

/**
 * D-172 §3.4 — one-step checkout.
 *
 * The order of operations is the point:
 *
 *  1. the CUSTOMER BLOCK is validated with the very same rules the server will
 *     apply (`@/lib/validation`), so a typo is caught before a round trip;
 *  2. the cart is PRE-FLIGHTED (`checkCartAvailabilityAction`) — an optimistic,
 *     non-authoritative read that warns about a sold-out line BEFORE an order is
 *     created, and shows the server's price when it differs from the stored one;
 *  3. the order is placed by `placeOrderAction`, which re-resolves prices, stock,
 *     the coupon and the totals inside the database transaction.
 *
 * Nothing here computes an authoritative number. The subtotal shown while typing
 * is the cart's display sum, the shipping amount comes from the same method table
 * the server uses, and the discount is NOT predicted client-side: a coupon's
 * eligibility depends on the SSOT, so the breakdown says the discount is applied
 * on the server rather than inventing one.
 *
 * The success state reports the gateway's own answer. Until a provider is chosen
 * the answer is `UNAVAILABLE` and the customer is told nothing was charged — the
 * order exists as `PENDING` for the boutique to handle (AC-8: never a faked
 * status).
 *
 * D-177 Phase 2D changes only the presentation: the checkout shell and its
 * inline order result use the storefront `--sf-*` layer. Submission order,
 * validation, idempotency, shipping, totals, payment status and focus behavior
 * are unchanged.
 *
 * Phone-number OTP (roadmap §3.4) is deliberately absent: the SMS provider is
 * now selected (decision row 74, Kavenegar) and its channel adapter exists in
 * `local/canonical/sms_adapter.py`, but no OTP issue/verify endpoint is built
 * yet, and a fake code entry would be worse than none. The number is validated
 * here and stored as the customer identity.
 */

/**
 * The form owns ONLY state and markup. The rules it applies (validation, the
 * pre-flight refusal, the price-change notice, and what a failed submission
 * means) live in `@/lib/checkout-submit`, where they are exercised without a
 * browser — the same split the PDP's selection rules use.
 */
export function CheckoutForm({ shippingConfig }: { shippingConfig: ShippingConfig }) {
  const { lines, subtotal, hydrated, clear } = useCart();

  const [fullName, setFullName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [address, setAddress] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [couponCode, setCouponCode] = useState('');
  const [shippingMethodId, setShippingMethodId] = useState(DEFAULT_SHIPPING_METHOD_ID);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<CheckoutFieldErrors>({});
  const [notes, setNotes] = useState<string[]>([]);
  const [result, setResult] = useState<PlaceOrderResult | null>(null);
  /**
   * A submission whose outcome is UNKNOWN (the call threw). Kept apart from
   * `result` on purpose: `result` is the server's own verdict, and a transport
   * failure has no verdict to report.
   */
  const [submitError, setSubmitError] = useState<string | null>(null);
  /**
   * The in-flight lock. `busy` re-renders the button as disabled, but React
   * commits that after the handler returns, so two submissions in the same tick
   * (a double click, or Enter plus a click) would otherwise both reach the
   * server — and the write path has no idempotency key, so that is two orders.
   */
  const inFlight = useRef(false);

  const totalQuantity = lines.reduce((total, line) => total + line.quantity, 0);
  const parcel = estimateParcel(shippingConfig.parcelPolicy, totalQuantity);
  const eligible = parcel
    ? eligibleShippingOptions(shippingConfig, { address, parcel })
    : [];
  const selected = eligible.find((option) => option.carrierId === shippingMethodId) ?? eligible[0];
  const selectedCarrierId = selected?.carrierId ?? '';

  // Address/cart changes can invalidate the previous choice. Deriving the
  // effective selection (instead of syncing it in an effect) keeps the first
  // eligible option authoritative without a cascading render.
  const shipping = selected?.amount ?? 0;
  const preview: CheckoutTotals = computeCheckoutTotals({ subtotal, discount: 0, shipping });

  if (!hydrated) {
    return (
      <p className="mt-8 text-sf-body text-sf-ink-muted" role="status">
        در حال خواندن سبد خرید…
      </p>
    );
  }

  if (lines.length === 0 && !(result?.ok ?? false)) {
    return (
      <section
        aria-labelledby="checkout-empty-title"
        className="mt-8 mx-auto flex max-w-2xl flex-col items-start gap-4 border border-sf-edge bg-sf-surface p-6 sm:p-8"
      >
        <SectionEyebrow>سبد خرید</SectionEyebrow>
        <h2
          id="checkout-empty-title"
          className="font-display text-sf-title font-semibold text-sf-ink"
        >
          سبد خرید خالی است
        </h2>
        <p className="text-sf-body leading-relaxed text-sf-ink-muted">
          برای ثبت سفارش ابتدا یک محصول، رنگ و اندازه انتخاب کنید.
        </p>
        <Link className={sfButton.primary} href="/catalog">
          رفتن به فهرست محصولات
        </Link>
      </section>
    );
  }

  async function submit() {
    // One submission at a time. The lock is taken BEFORE any await, so a second
    // invocation in the same tick cannot reach the write path — `busy` alone
    // only disables the button on the next render.
    if (inFlight.current) {
      return;
    }
    if (selectedCarrierId === '') {
      setSubmitError(NO_ELIGIBLE_CARRIER_MESSAGE);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setNotes([]);
    setResult(null);
    setSubmitError(null);

    const keyStorage = checkoutKeyStorage();
    const intent: CheckoutIntent = {
      lines: lines.map((line) => ({ variantId: line.variantId, quantity: line.quantity })),
      customer: { fullName, phoneNumber, address, postalCode },
      couponCode: couponCode.trim() === '' ? null : couponCode,
      shippingMethodId: selectedCarrierId,
    };

    try {
      const outcome = await submitCheckout(
        {
          customer: { fullName, phoneNumber, address, postalCode },
          couponCode,
          shippingMethodId: selectedCarrierId,
          cartLines: lines,
          idempotencyKey: checkoutIdempotencyKey(intent, keyStorage),
        },
        { checkAvailability: checkCartAvailabilityAction, placeOrder: placeOrderAction },
      );

      if (outcome.status === 'invalid') {
        setErrors(outcome.errors);
        return;
      }
      if (outcome.status === 'error') {
        // No verdict was received: say so, and claim nothing about the order.
        setSubmitError(outcome.message);
        return;
      }

      setNotes(outcome.notes);
      setResult(outcome.result);

      if (outcome.status === 'placed') {
        // The order exists (fresh or replayed): this intent must never be
        // resubmitted. The cart is cleared through the ordinary success path.
        clearCheckoutIdempotencyKey(keyStorage);
        clear();
        // §6.1 — a redirect-based provider: the adapter issued an authority and
        // persisted it on the order, and the customer pays on ZarinPal's page.
        // The order is still `PENDING` until the browser comes back and the
        // callback verifies; nothing here can mark it paid.
        if (outcome.result.payment.redirectUrl) {
          window.location.assign(outcome.result.payment.redirectUrl);
        }
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  // Visible errors must also be announced: each pair is decided in one place so
  // the message id, `aria-invalid` and `aria-describedby` cannot drift apart.
  const nameA11y = fieldA11y(errors.fullName, 'checkout-name-error');
  const phoneA11y = fieldA11y(errors.phoneNumber, 'checkout-phone-error');
  const addressA11y = fieldA11y(errors.address, 'checkout-address-error');
  const postalA11y = fieldA11y(errors.postalCode, 'checkout-postal-error');

  // The order result is the whole surface once the order exists. Keeping the
  // now-cleared form and its zero-total summary beside it would read as a second,
  // contradictory checkout rather than a completed sandbox result.
  if (result !== null && result.ok) {
    return (
      <div className="mt-10 mx-auto max-w-3xl">
        {notes.map((note) => (
          <CheckoutNotice key={note} title="قیمت روی سرور به‌روز است">
            {note}
          </CheckoutNotice>
        ))}
        <CheckoutSuccess result={result} />
      </div>
    );
  }

  return (
    <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-start lg:gap-14">
      <section
        aria-labelledby="checkout-customer-title"
        className="border border-sf-edge bg-sf-surface p-5 sm:p-8"
      >
        <header className="border-b border-sf-edge pb-5">
          <SectionEyebrow>اطلاعات گیرنده</SectionEyebrow>
          <h2
            id="checkout-customer-title"
            className="mt-2 font-display text-sf-title font-semibold text-sf-ink"
          >
            اطلاعات گیرنده
          </h2>
          <p className="mt-2 max-w-2xl text-sf-caption leading-relaxed text-sf-ink-muted">
            شمارهٔ موبایل و نشانی دقیق پستی. این اطلاعات فقط برای همین سفارش استفاده می‌شود.
          </p>
        </header>

        <form
          aria-label="فرم تسویهٔ خرید"
          className="mt-6 flex flex-col gap-6"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <CheckoutField
            label="نام و نام خانوادگی"
            htmlFor="checkout-name"
            required
            error={errors.fullName}
            errorId={nameA11y.errorId}
          >
            <input
              id="checkout-name"
              className={sfField}
              value={fullName}
              autoComplete="name"
              {...nameA11y.inputProps}
              onChange={(event) => setFullName(event.target.value)}
            />
          </CheckoutField>

          <CheckoutField
            label="شمارهٔ موبایل"
            htmlFor="checkout-phone"
            required
            hint="۱۱ رقم و با ۰۹ شروع شود"
            error={errors.phoneNumber}
            errorId={phoneA11y.errorId}
          >
            <input
              id="checkout-phone"
              className={sfField}
              inputMode="numeric"
              dir="ltr"
              autoComplete="tel"
              value={phoneNumber}
              {...phoneA11y.inputProps}
              onChange={(event) => setPhoneNumber(event.target.value)}
            />
          </CheckoutField>

          <CheckoutField
            label="نشانی"
            htmlFor="checkout-address"
            required
            hint="استان، شهر، خیابان، پلاک و واحد"
            error={errors.address}
            errorId={addressA11y.errorId}
          >
            <textarea
              id="checkout-address"
              className={cn(sfField, 'min-h-24 py-3')}
              rows={3}
              value={address}
              {...addressA11y.inputProps}
              onChange={(event) => setAddress(event.target.value)}
            />
          </CheckoutField>

          <CheckoutField
            label="کد پستی"
            htmlFor="checkout-postal"
            required
            hint="۱۰ رقم"
            error={errors.postalCode}
            errorId={postalA11y.errorId}
          >
            <input
              id="checkout-postal"
              className={sfField}
              inputMode="numeric"
              dir="ltr"
              value={postalCode}
              {...postalA11y.inputProps}
              onChange={(event) => setPostalCode(event.target.value)}
            />
          </CheckoutField>

          <CheckoutField
            label="کد تخفیف"
            htmlFor="checkout-coupon"
            hint="اختیاری — اعتبار کد روی سرور بررسی می‌شود"
          >
            <input
              id="checkout-coupon"
              className={cn(sfField, 'sf-code')}
              dir="ltr"
              value={couponCode}
              onChange={(event) => setCouponCode(event.target.value.toUpperCase())}
            />
          </CheckoutField>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-sf-caption font-medium text-sf-ink">روش ارسال</legend>
            {eligible.length === 0 ? (
              <p className="border border-sf-edge bg-sf-surface p-4 text-sf-caption leading-relaxed text-sf-ink-muted">
                {NO_ELIGIBLE_CARRIER_MESSAGE}
              </p>
            ) : (
              eligible.map((option) => (
                <label
                  key={option.carrierId}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-sf border p-3 text-sf-caption text-sf-ink transition-colors',
                    selectedCarrierId === option.carrierId
                      ? 'border-sf-ink bg-sf-surface'
                      : 'border-sf-edge bg-sf-surface hover:border-sf-edge-strong',
                  )}
                >
                  <input
                    type="radio"
                    name="checkout-shipping"
                    className="mt-1 size-4 accent-sf-ink"
                    value={option.carrierId}
                    checked={selectedCarrierId === option.carrierId}
                    onChange={() => setShippingMethodId(option.carrierId)}
                  />
                  <span>
                    <span className="font-medium">{option.carrierName}</span>
                    <span className="sf-code mt-1 block text-sf-caption text-sf-ink-muted">
                      {option.amount === 0 ? 'هزینه با گیرنده' : formatToman(option.amount)}
                    </span>
                    <span className="mt-1 block text-sf-caption text-sf-ink-muted">
                      {option.deliveryEstimate.label}
                      {option.capabilities.pickupPoint ? ' · تحویل در نقطهٔ تحویل' : ''}
                    </span>
                  </span>
                </label>
              ))
            )}
          </fieldset>

          <div>
            <button
              type="submit"
              className={cn(sfButton.primary, 'w-full disabled:opacity-60 sm:w-auto')}
              disabled={busy || eligible.length === 0}
              aria-busy={busy}
            >
              {busy ? 'در حال ثبت سفارش…' : 'ثبت سفارش'}
            </button>
          </div>
        </form>
      </section>

      <div className="flex flex-col gap-6">
        <section
          aria-labelledby="checkout-summary-title"
          className="border border-sf-edge bg-sf-surface p-5 sm:p-6"
        >
          <header>
            <SectionEyebrow>خلاصهٔ سفارش</SectionEyebrow>
            <h2
              id="checkout-summary-title"
              className="mt-2 font-display text-sf-title font-semibold text-sf-ink"
            >
              سبد خرید
            </h2>
            <p className="mt-2 text-sf-caption leading-relaxed text-sf-ink-muted">
              هر قلم در یک سطر، با قیمت سرور.
            </p>
          </header>

          <ul className="mt-5 border-t border-sf-edge">
            {lines.map((line) => (
              <li
                key={line.variantId}
                className="flex items-start justify-between gap-3 border-b border-sf-edge py-3"
              >
                <span className="text-sf-caption text-sf-ink">
                  {line.productTitle}
                  <span className="mt-1 block text-sf-caption text-sf-ink-muted">
                    {line.colorName} · اندازه <span className="sf-code">{line.size}</span> · تعداد{' '}
                    <span className="sf-code">{formatCountFa(line.quantity)}</span> (حداکثر{' '}
                    <span className="sf-code">{formatCountFa(MAX_LINE_QUANTITY)}</span>)
                  </span>
                </span>
                <span className="shrink-0 text-sf-caption text-sf-ink">
                  {formatToman(line.unitPrice * line.quantity)}
                </span>
              </li>
            ))}
          </ul>

          <dl className="mt-4 flex flex-col gap-2 text-sf-caption">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-sf-ink-muted">{CHECKOUT_TOTAL_LABELS.subtotal}</dt>
              <dd className="text-sf-ink">{formatToman(preview.subtotal)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-sf-ink-muted">{CHECKOUT_TOTAL_LABELS.shipping}</dt>
              <dd className="text-sf-ink">{formatToman(preview.shipping)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4 border-t border-sf-edge pt-3">
              <dt className="font-medium text-sf-ink">{CHECKOUT_TOTAL_LABELS.total}</dt>
              <dd className="font-semibold text-sf-ink">{formatToman(preview.total)}</dd>
            </div>
          </dl>
          <p className="mt-3 text-sf-caption leading-relaxed text-sf-ink-muted">
            تخفیف کد تخفیف پس از بررسی روی سرور اعمال می‌شود و در همین صفحه نمایش داده خواهد شد.
          </p>
        </section>

        {notes.map((note) => (
          <CheckoutNotice key={note} title="قیمت روی سرور به‌روز است">
            {note}
          </CheckoutNotice>
        ))}

        {result !== null && !result.ok ? (
          <CheckoutNotice title="سفارش ثبت نشد" tone="danger">
            {result.message}
            {result.field ? <span className="sf-code"> [{result.field}]</span> : null}
          </CheckoutNotice>
        ) : null}

        {submitError !== null ? (
          <CheckoutNotice title="نتیجهٔ ثبت سفارش تأیید نشد" tone="danger">
            {submitError}
          </CheckoutNotice>
        ) : null}

        {lines.length > 0 ? (
          <p className="text-sf-caption leading-relaxed text-sf-ink-muted">
            با ثبت سفارش، سفارش شما با وضعیت «در انتظار پرداخت» برای بررسی فروشگاه ثبت می‌شود.
          </p>
        ) : null}
      </div>
    </div>
  );
}

/** The inline sandbox order result; it never claims a payment that did not occur. */
function CheckoutSuccess({ result }: { result: OrderPlaced }) {
  const paymentUnavailable = result.payment.status === 'UNAVAILABLE';
  const description = result.replayed
    ? 'این سبد پیش‌تر ثبت شده بود؛ سفارش تازه‌ای ایجاد نشد و موجودی یا تخفیف دوباره مصرف نشد.'
    : paymentUnavailable
      ? 'سفارش با وضعیت «در انتظار پرداخت» ثبت شده است؛ پرداخت آنلاین انجام نشده و هیچ مبلغی از مشتری دریافت نشده است.'
      : 'سفارش با وضعیت «در انتظار پرداخت» ثبت شده است.';

  return (
    <section
      role="status"
      aria-labelledby="checkout-result-title"
      className="border border-sf-ink bg-sf-surface p-5 sm:p-8"
    >
      <header>
        <SectionEyebrow>نتیجهٔ سفارش</SectionEyebrow>
        <h2
          id="checkout-result-title"
          className="mt-2 font-display text-sf-title font-semibold text-sf-ink"
        >
          سفارش ثبت شد
        </h2>
        <p className="mt-2 max-w-2xl text-sf-caption leading-relaxed text-sf-ink-muted">
          {description}
        </p>
      </header>

      <dl className="mt-6 flex flex-col gap-3 border-y border-sf-edge py-4 text-sf-caption">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <dt className="text-sf-ink-muted">شناسهٔ سفارش</dt>
          <dd className="sf-code break-all text-sf-ink">{result.orderId}</dd>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <dt className="text-sf-ink-muted">وضعیت پرداخت</dt>
          <dd>
            <span className="inline-flex items-center gap-2 border border-sf-edge-strong px-2 py-1 text-sf-caption text-sf-ink">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-sf-ink" />
              {PAYMENT_STATUS_LABELS[result.payment.status]}{' '}
              <span className="sf-code">{result.payment.status}</span>
            </span>
          </dd>
        </div>
      </dl>

      <p className="mt-3 text-sf-caption leading-relaxed text-sf-ink-muted">
        {result.payment.message}
      </p>
      {result.payment.redirectUrl ? (
        <a className={cn(sfButton.primary, 'mt-4')} href={result.payment.redirectUrl}>
          ادامهٔ پرداخت در درگاه
        </a>
      ) : null}

      <h3 className="mt-8 font-display text-lg font-semibold text-sf-ink">جمع نهایی سفارش</h3>
      <dl className="mt-3 flex flex-col gap-2 text-sf-caption">
        <div className="flex items-center justify-between gap-4">
          <dt className="text-sf-ink-muted">{CHECKOUT_TOTAL_LABELS.subtotal}</dt>
          <dd className="text-sf-ink">{formatToman(result.totals.subtotal)}</dd>
        </div>
        <div className="flex items-center justify-between gap-4">
          <dt className="text-sf-ink-muted">
            {CHECKOUT_TOTAL_LABELS.discount}
            {result.couponApplied ? <span className="sf-code"> (اعمال شد)</span> : null}
          </dt>
          <dd className="text-sf-ink">{formatToman(result.totals.discount)}</dd>
        </div>
        <div className="flex items-center justify-between gap-4">
          <dt className="text-sf-ink-muted">{CHECKOUT_TOTAL_LABELS.shipping}</dt>
          <dd className="text-sf-ink">{formatToman(result.totals.shipping)}</dd>
        </div>
        <div className="flex items-center justify-between gap-4 border-t border-sf-edge pt-3">
          <dt className="font-medium text-sf-ink">{CHECKOUT_TOTAL_LABELS.total}</dt>
          <dd className="font-semibold text-sf-ink">{formatToman(result.totals.total)}</dd>
        </div>
      </dl>

      <Link className={cn(sfButton.quiet, 'mt-6')} href="/catalog">
        بازگشت به فهرست محصولات
      </Link>
    </section>
  );
}

/** The checkout's field contract, on the storefront layer. */
function CheckoutField({
  label,
  hint,
  error,
  errorId,
  htmlFor,
  children,
  required,
}: {
  label: string;
  hint?: string;
  error?: string;
  errorId?: string;
  htmlFor?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={htmlFor} className="text-sf-caption font-medium text-sf-ink">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {children}
      {hint ? <p className="text-sf-caption leading-relaxed text-sf-ink-muted">{hint}</p> : null}
      {error ? (
        <p id={errorId} className="text-sf-caption font-medium text-sf-accent" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** The checkout's notice contract; tone is a border, never colour-only meaning. */
function CheckoutNotice({
  title,
  children,
  tone = 'quiet',
}: {
  title: string;
  children: ReactNode;
  tone?: 'quiet' | 'danger';
}) {
  return (
    <div
      role="status"
      className={cn(
        'border bg-sf-surface p-4',
        tone === 'danger' ? 'border-sf-accent' : 'border-sf-edge',
      )}
    >
      <p className="font-display text-base font-semibold text-sf-ink">{title}</p>
      <div className="mt-1 text-sf-caption leading-relaxed text-sf-ink-muted">{children}</div>
    </div>
  );
}
