'use client';

import Link from 'next/link';
import { useRef, useState } from 'react';

import type { CheckoutTotals, PlaceOrderResult } from '@/contracts/storefront';
import { type CheckoutFieldErrors, submitCheckout } from '@/lib/checkout-submit';
import { MAX_LINE_QUANTITY, computeCheckoutTotals } from '@/lib/checkout-rules';
import { fieldA11y } from '@/lib/field-a11y';
import { formatCountFa, formatToman } from '@/lib/format';
import { DEFAULT_SHIPPING_METHOD_ID, SHIPPING_METHODS, shippingAmountFor } from '@/lib/shipping';
import {
  CHECKOUT_TOTAL_LABELS,
  PAYMENT_STATUS_LABELS,
  PAYMENT_STATUS_TONE,
} from '@/lib/storefront-display';
import { Badge, Banner, Card, CardHeader, Field, Table, Td, Th, buttonClass, inputClass } from '@/components/ui/primitives';
import { checkCartAvailabilityAction, placeOrderAction } from '@/server/actions/storefront';

import { useCart } from './cart-provider';

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
export function CheckoutForm() {
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

  const shipping = shippingAmountFor(shippingMethodId) ?? 0;
  const preview: CheckoutTotals = computeCheckoutTotals({ subtotal, discount: 0, shipping });

  if (!hydrated) {
    return (
      <p className="mt-6 text-cp-label text-ink-muted" role="status">
        در حال خواندن سبد خرید…
      </p>
    );
  }

  if (lines.length === 0 && !(result?.ok ?? false)) {
    return (
      <div className="mt-6 flex flex-col items-start gap-3 rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-4">
        <p className="text-cp-label text-ink-muted">
          سبد خرید خالی است؛ برای ثبت سفارش ابتدا یک محصول، رنگ و اندازه انتخاب کنید.
        </p>
        <Link className={buttonClass.primary} href="/catalog">
          رفتن به فهرست محصولات
        </Link>
      </div>
    );
  }

  async function submit() {
    // One submission at a time. The lock is taken BEFORE any await, so a second
    // invocation in the same tick cannot reach the write path — `busy` alone
    // only disables the button on the next render.
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setErrors({});
    setNotes([]);
    setResult(null);
    setSubmitError(null);

    try {
      const outcome = await submitCheckout(
        {
          customer: { fullName, phoneNumber, address, postalCode },
          couponCode,
          shippingMethodId,
          cartLines: lines,
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

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <Card>
        <CardHeader
          title="اطلاعات گیرنده"
          description="شمارهٔ موبایل و نشانی دقیق پستی. این اطلاعات فقط برای همین سفارش استفاده می‌شود."
        />
        <form
          aria-label="فرم تسویهٔ خرید"
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <Field
            label="نام و نام خانوادگی"
            htmlFor="checkout-name"
            required
            error={errors.fullName}
            errorId={nameA11y.errorId}
          >
            <input
              id="checkout-name"
              className={inputClass}
              value={fullName}
              autoComplete="name"
              {...nameA11y.inputProps}
              onChange={(event) => setFullName(event.target.value)}
            />
          </Field>

          <Field
            label="شمارهٔ موبایل"
            htmlFor="checkout-phone"
            required
            hint="۱۱ رقم و با ۰۹ شروع شود"
            error={errors.phoneNumber}
            errorId={phoneA11y.errorId}
          >
            <input
              id="checkout-phone"
              className={inputClass}
              inputMode="numeric"
              dir="ltr"
              autoComplete="tel"
              value={phoneNumber}
              {...phoneA11y.inputProps}
              onChange={(event) => setPhoneNumber(event.target.value)}
            />
          </Field>

          <Field
            label="نشانی"
            htmlFor="checkout-address"
            required
            hint="استان، شهر، خیابان، پلاک و واحد"
            error={errors.address}
            errorId={addressA11y.errorId}
          >
            <textarea
              id="checkout-address"
              className={inputClass}
              rows={3}
              value={address}
              {...addressA11y.inputProps}
              onChange={(event) => setAddress(event.target.value)}
            />
          </Field>

          <Field
            label="کد پستی"
            htmlFor="checkout-postal"
            required
            hint="۱۰ رقم"
            error={errors.postalCode}
            errorId={postalA11y.errorId}
          >
            <input
              id="checkout-postal"
              className={inputClass}
              inputMode="numeric"
              dir="ltr"
              value={postalCode}
              {...postalA11y.inputProps}
              onChange={(event) => setPostalCode(event.target.value)}
            />
          </Field>

          <Field
            label="کد تخفیف"
            htmlFor="checkout-coupon"
            hint="اختیاری — اعتبار کد روی سرور بررسی می‌شود"
          >
            <input
              id="checkout-coupon"
              className={`${inputClass} cp-code`}
              dir="ltr"
              value={couponCode}
              onChange={(event) => setCouponCode(event.target.value.toUpperCase())}
            />
          </Field>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-medium text-ink">روش ارسال</legend>
            {SHIPPING_METHODS.map((method) => (
              <label
                key={method.id}
                className="flex items-start gap-2 rounded-[--radius-cp] border border-edge p-2 text-cp-label text-ink"
              >
                <input
                  type="radio"
                  name="checkout-shipping"
                  value={method.id}
                  checked={shippingMethodId === method.id}
                  onChange={() => setShippingMethodId(method.id)}
                />
                <span>
                  <span className="font-medium">{method.label}</span>
                  <span className="cp-code block text-cp-caption text-ink-muted">
                    {method.amount === 0 ? 'هزینه با گیرنده' : formatToman(method.amount)}
                  </span>
                  <span className="block text-cp-caption text-ink-muted">
                    {method.description}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>

          <div>
            <button type="submit" className={buttonClass.primary} disabled={busy} aria-busy={busy}>
              {busy ? 'در حال ثبت سفارش…' : 'ثبت سفارش'}
            </button>
          </div>
        </form>
      </Card>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader title="سبد خرید" description="هر قلم در یک سطر، با قیمت سرور." />
          <ul className="flex flex-col gap-2">
            {lines.map((line) => (
              <li
                key={line.variantId}
                className="flex items-start justify-between gap-2 border-b border-edge pb-2 last:border-b-0"
              >
                <span className="text-cp-label text-ink">
                  {line.productTitle}
                  <span className="block text-cp-caption text-ink-muted">
                    {line.colorName} · اندازه <span className="cp-code">{line.size}</span> · تعداد{' '}
                    <span className="cp-code">{formatCountFa(line.quantity)}</span> (حداکثر{' '}
                    <span className="cp-code">{formatCountFa(MAX_LINE_QUANTITY)}</span>)
                  </span>
                </span>
                <span className="shrink-0 text-cp-label text-ink">
                  {formatToman(line.unitPrice * line.quantity)}
                </span>
              </li>
            ))}
          </ul>

          <dl className="mt-3 flex flex-col gap-1 text-cp-label">
            <div className="flex items-center justify-between">
              <dt className="text-ink-muted">{CHECKOUT_TOTAL_LABELS.subtotal}</dt>
              <dd className="text-ink">{formatToman(preview.subtotal)}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-ink-muted">{CHECKOUT_TOTAL_LABELS.shipping}</dt>
              <dd className="text-ink">{formatToman(preview.shipping)}</dd>
            </div>
            <div className="flex items-center justify-between border-t border-edge pt-1">
              <dt className="font-medium text-ink">{CHECKOUT_TOTAL_LABELS.total}</dt>
              <dd className="font-semibold text-ink">{formatToman(preview.total)}</dd>
            </div>
          </dl>
          <p className="mt-2 text-cp-caption text-ink-muted">
            تخفیف کد تخفیف پس از بررسی روی سرور اعمال می‌شود و در همین صفحه نمایش داده خواهد شد.
          </p>
        </Card>

        {notes.map((note) => (
          <Banner key={note} tone="warning" title="قیمت روی سرور به‌روز است">
            {note}
          </Banner>
        ))}

        {result !== null && !result.ok ? (
          <Banner tone="danger" title="سفارش ثبت نشد">
            {result.message}
            {result.field ? <span className="cp-code"> [{result.field}]</span> : null}
          </Banner>
        ) : null}

        {submitError !== null ? (
          <Banner tone="danger" title="نتیجهٔ ثبت سفارش تأیید نشد">
            {submitError}
          </Banner>
        ) : null}

        {result !== null && result.ok ? (
          <Card>
            <CardHeader
              title="سفارش ثبت شد"
              description="سفارش با وضعیت «در انتظار پرداخت» ثبت شده است."
            />
            <p className="text-cp-label text-ink">
              شناسهٔ سفارش: <span className="cp-code">{result.orderId}</span>
            </p>
            <p className="mt-2">
              <Badge tone={PAYMENT_STATUS_TONE[result.payment.status]}>
                {PAYMENT_STATUS_LABELS[result.payment.status]}{' '}
                <span className="cp-code">{result.payment.status}</span>
              </Badge>
            </p>
            <p className="mt-2 text-cp-label text-ink-muted">{result.payment.message}</p>
            {result.payment.redirectUrl ? (
              <a className={`${buttonClass.primary} mt-3`} href={result.payment.redirectUrl}>
                ادامهٔ پرداخت در درگاه
              </a>
            ) : null}
            <Table
              caption="جمع نهایی سفارش"
              head={
                <tr>
                  <Th>شرح</Th>
                  <Th>مبلغ</Th>
                </tr>
              }
            >
              <tr>
                <Td>{CHECKOUT_TOTAL_LABELS.subtotal}</Td>
                <Td>{formatToman(result.totals.subtotal)}</Td>
              </tr>
              <tr>
                <Td>
                  {CHECKOUT_TOTAL_LABELS.discount}
                  {result.couponApplied ? <span className="cp-code"> (اعمال شد)</span> : null}
                </Td>
                <Td>{formatToman(result.totals.discount)}</Td>
              </tr>
              <tr>
                <Td>{CHECKOUT_TOTAL_LABELS.shipping}</Td>
                <Td>{formatToman(result.totals.shipping)}</Td>
              </tr>
              <tr>
                <Td>{CHECKOUT_TOTAL_LABELS.total}</Td>
                <Td>{formatToman(result.totals.total)}</Td>
              </tr>
            </Table>
            <Link className={`${buttonClass.neutral} mt-3`} href="/catalog">
              بازگشت به فهرست محصولات
            </Link>
          </Card>
        ) : null}

        {lines.length > 0 && result?.ok !== true ? (
          <p className="text-cp-caption text-ink-muted">
            با ثبت سفارش، سفارش شما با وضعیت «در انتظار پرداخت» برای بررسی فروشگاه ثبت می‌شود.
          </p>
        ) : null}
      </div>
    </div>
  );
}
