import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type {
  CartAvailabilityLine,
  CartLine,
  CheckoutDraft,
  OrderPlaced,
  OrderRefused,
} from '@/contracts/storefront';
import {
  CHECKOUT_TRANSPORT_ERROR_MESSAGE,
  type CheckoutPorts,
  type CheckoutSubmissionInput,
  normalizeCouponInput,
  submitCheckout,
} from '@/lib/checkout-submit';
import { formatToman } from '@/lib/format';

/**
 * D-172 §3.4 — the checkout submission pipeline.
 *
 * The case that motivated extracting this from the component is the LAST
 * describe block: a submission that THREW used to vanish into an unhandled
 * promise rejection, leaving the customer with no message and no way to know
 * whether an order existed. Every branch is asserted here because the component
 * can now only render what this function says.
 */

function cartLine(overrides: Partial<CartLine> = {}): CartLine {
  return {
    variantId: 'v1',
    productSlug: 'manto-katan',
    productTitle: 'مانتو کتان',
    size: 'M',
    colorName: 'مشکی',
    colorHex: '#111111',
    unitPrice: 2_000_000,
    quantity: 1,
    imageUrl: null,
    ...overrides,
  };
}

function availability(overrides: Partial<CartAvailabilityLine> = {}): CartAvailabilityLine {
  return {
    variantId: 'v1',
    productTitle: 'مانتو کتان',
    size: 'M',
    colorName: 'مشکی',
    level: 'IN',
    available: true,
    effectivePrice: 2_000_000,
    ...overrides,
  };
}

const CUSTOMER = {
  fullName: 'زهرا محمدی',
  phoneNumber: '09123456789',
  address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
  postalCode: '1999999999',
};

const PLACED: OrderPlaced = {
  ok: true,
  orderId: 'order-1',
  totals: { subtotal: 2_000_000, discount: 0, shipping: 45_000, total: 2_045_000 },
  payment: {
    status: 'UNAVAILABLE',
    code: 'ZARINPAL_NOT_CONFIGURED',
    message: 'درگاه پرداخت تنظیم نشده است.',
    reference: null,
  },
  couponApplied: false,
  status: 'PENDING',
};

interface Calls {
  preflight: Array<Array<{ variantId: string; quantity: number }>>;
  orders: CheckoutDraft[];
}

function ports(overrides: Partial<CheckoutPorts> = {}): { ports: CheckoutPorts; calls: Calls } {
  const calls: Calls = { preflight: [], orders: [] };
  const base: CheckoutPorts = {
    checkAvailability: async (lines) => {
      calls.preflight.push(lines);
      return { ok: true, lines: lines.map((line) => availability({ variantId: line.variantId })) };
    },
    placeOrder: async (draft) => {
      calls.orders.push(draft);
      return PLACED;
    },
  };
  return { ports: { ...base, ...overrides }, calls };
}

function input(overrides: Partial<CheckoutSubmissionInput> = {}): CheckoutSubmissionInput {
  return {
    customer: CUSTOMER,
    couponCode: '',
    shippingMethodId: 'POST_PISHTAZ',
    cartLines: [cartLine({ quantity: 2 })],
    ...overrides,
  };
}

describe('checkout submission — the server verdict (§3.4)', () => {
  it('reports a placed order as PENDING and keeps any price note', async () => {
    const { ports: p } = ports({
      checkAvailability: async () => ({
        ok: true,
        lines: [availability({ effectivePrice: 2_100_000 })],
      }),
    });
    const outcome = await submitCheckout(input({ couponCode: ' live25 ' }), p);

    assert.ok(outcome.status === 'placed');
    assert.equal(outcome.result.orderId, 'order-1');
    assert.equal(outcome.result.status, 'PENDING');
    assert.equal(outcome.result.payment.status, 'UNAVAILABLE');
    assert.equal(outcome.notes.length, 1, 'the warning survives a successful write');
  });

  it('keeps the price note when the server refuses the order', async () => {
    const refusal: OrderRefused = {
      ok: false,
      code: 'COUPON_INVALID',
      message: 'کد تخفیف معتبر نیست.',
      field: 'couponCode',
    };
    const { ports: p } = ports({
      checkAvailability: async () => ({
        ok: true,
        lines: [availability({ effectivePrice: 2_100_000 })],
      }),
      placeOrder: async () => refusal,
    });
    const outcome = await submitCheckout(input(), p);

    assert.ok(outcome.status === 'refused');
    assert.equal(outcome.result.code, 'COUPON_INVALID');
    assert.equal(outcome.notes.length, 1, 'the customer keeps the warning they already read');
  });

  it('normalises the coupon once: blank is null, anything else is upper-cased', async () => {
    assert.equal(normalizeCouponInput(''), null);
    assert.equal(normalizeCouponInput('   '), null);
    assert.equal(normalizeCouponInput(' live25 '), 'LIVE25');

    const { ports: p, calls } = ports();
    await submitCheckout(input({ couponCode: ' live25 ' }), p);
    assert.equal(calls.orders[0]?.couponCode, 'LIVE25');
  });
});

describe('checkout submission — a thrown call is UNKNOWN, never a success', () => {
  it('reports status "error" with a message that claims nothing about the order', async () => {
    let attempts = 0;
    const { ports: p } = ports({
      placeOrder: async () => {
        attempts += 1;
        throw new Error('network down');
      },
    });
    const outcome = await submitCheckout(input(), p);

    assert.equal(outcome.status, 'error');
    assert.ok(outcome.status === 'error');
    assert.equal(outcome.message, CHECKOUT_TRANSPORT_ERROR_MESSAGE);
    assert.ok(
      !outcome.message.includes('سفارش ثبت شد'),
      'an unknown outcome must never read like a successful order',
    );
    assert.equal(attempts, 1, 'the submission really did reach the write path');
  });

  it('treats a thrown pre-flight the same way, without claiming a refusal', async () => {
    const { ports: p, calls } = ports({
      checkAvailability: async () => {
        throw new Error('socket hang up');
      },
    });
    const outcome = await submitCheckout(input(), p);

    assert.equal(outcome.status, 'error');
    assert.equal(calls.orders.length, 0, 'nothing was attempted at the write path');
  });
});

describe('checkout submission — validation first (§3.4)', () => {
  it('refuses an invalid customer block without touching the server', async () => {
    const { ports: p, calls } = ports();
    const outcome = await submitCheckout(
      input({ customer: { ...CUSTOMER, phoneNumber: '12345' } }),
      p,
    );

    assert.equal(outcome.status, 'invalid');
    assert.ok(outcome.status === 'invalid' && outcome.errors.phoneNumber);
    assert.equal(calls.preflight.length, 0, 'no round trip for a typo');
    assert.equal(calls.orders.length, 0);
  });
});

describe('checkout submission — the pre-flight gates the write (§3.3/§3.4)', () => {
  it('passes the refusal through and never places the order', async () => {
    const refusal: OrderRefused = {
      ok: false,
      code: 'DB_NOT_CONFIGURED',
      message: 'اتصال به پایگاه داده تنظیم نشده است.',
    };
    const { ports: p, calls } = ports({ checkAvailability: async () => refusal });
    const outcome = await submitCheckout(input(), p);

    assert.equal(outcome.status, 'refused');
    assert.ok(outcome.status === 'refused');
    assert.deepEqual(outcome.result, refusal);
    assert.equal(calls.orders.length, 0, 'a refused pre-flight must not reach the write path');
  });

  it('names a vanished line VARIANT_UNAVAILABLE and a short line STOCK_INSUFFICIENT', async () => {
    const gone = ports({
      checkAvailability: async () => ({
        ok: true,
        lines: [availability({ available: false, level: 'OUT', effectivePrice: null })],
      }),
    });
    const goneOutcome = await submitCheckout(input(), gone.ports);
    assert.ok(goneOutcome.status === 'refused');
    assert.equal(goneOutcome.result.code, 'VARIANT_UNAVAILABLE');
    assert.equal(gone.calls.orders.length, 0);

    const short = ports({
      checkAvailability: async () => ({
        ok: true,
        lines: [availability({ available: false, level: 'LOW' })],
      }),
    });
    const shortOutcome = await submitCheckout(input(), short.ports);
    assert.ok(shortOutcome.status === 'refused');
    assert.equal(shortOutcome.result.code, 'STOCK_INSUFFICIENT');
    assert.match(shortOutcome.result.message, /هیچ سفارشی ثبت نشد/);
    assert.equal(short.calls.orders.length, 0);
  });

  it('warns about a changed server price instead of silently using it', async () => {
    const { ports: p, calls } = ports({
      checkAvailability: async () => ({
        ok: true,
        lines: [availability({ effectivePrice: 2_100_000 })],
      }),
    });
    const outcome = await submitCheckout(input(), p);

    assert.ok(outcome.status === 'placed');
    assert.equal(outcome.notes.length, 1);
    assert.ok(outcome.notes[0]?.includes(formatToman(2_100_000)));
    assert.equal(
      calls.orders[0]?.lines[0]?.quantity,
      2,
      'the draft carries the cart’s own quantities',
    );
  });
});

