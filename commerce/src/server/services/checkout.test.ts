import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { MAX_LINE_QUANTITY, computeCheckoutTotals } from '@/lib/checkout-rules';
import {
  DEFAULT_SHIPPING_METHOD_ID,
  VALIDATED_DEFAULT_SHIPPING_CONFIG,
  applyShippingOverrides,
  shippingAmountFor,
} from '@/lib/shipping';
import { createMockPaymentGateway, mockPaymentGateway } from '@/server/payments/gateway';
import { createMemoryRepository } from '@/server/repository-memory';
import type { MemoryRepositorySeed } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { normalizeCheckoutLines, placeCheckoutOrder } from '@/server/services/checkout';
import { createProduct } from '@/server/services/products';
import {
  MERCHANT_TRANSITION,
  getOrder,
  listOrders,
  transitionOrder,
} from '@/server/services/orders';

/**
 * D-172 §3.4 — the checkout service against the in-memory double.
 *
 * The live suite (`__tests__/live-db/phase3-storefront-live.test.ts`) proves the
 * same funnel on real PostgreSQL, including the SQL that consumes and returns
 * stock. These tests are the offline half, and they exist for one reason the
 * live suite cannot cover: they run on every `npm test`, so the reservation rule
 * (an order takes stock; a cancellation gives it back exactly once) cannot
 * regress unnoticed between live passes.
 */

const BASE_PRICE = 2_450_000;
const DISCOUNT_PRICE = 2_100_000;
const OVERRIDE_PRICE = 1_900_000;
const COUPON_CODE = 'UNIT25';
const SHIPPING = shippingAmountFor(DEFAULT_SHIPPING_METHOD_ID) ?? 0;

const PRODUCT_PAYLOAD: ProductCreatePayload = {
  categoryId: 'cat-1',
  title: 'مانتو کتان',
  slug: 'manto-katan',
  basePrice: BASE_PRICE,
  discountPrice: DISCOUNT_PRICE,
  descriptionRaw: 'مانتو کتان با دوخت ساده.',
  descriptionHtml: '<p>مانتو کتان</p>',
  fabricType: 'کتان',
  season: 'تابستان',
  status: 'PUBLISHED',
  variants: [
    { sku: 'UNIT-BLK-S', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 4 },
    {
      sku: 'UNIT-WHT-M',
      colorName: 'سفید',
      colorHex: '#FFFFFF',
      size: 'M',
      stockQuantity: 12,
      priceOverride: OVERRIDE_PRICE,
    },
  ],
  images: [],
};

interface Harness {
  repository: CommerceRepository;
  blackSmall: string;
  whiteMedium: string;
}

type SeedCoupon = NonNullable<MemoryRepositorySeed['coupons']>[number];

async function harness(
  coupons: SeedCoupon[] = [
    { code: COUPON_CODE, discountType: 'PERCENT', discountValue: 25, usageLimit: 3 },
  ],
): Promise<Harness> {
  const repository = createMemoryRepository({ coupons });
  const created = await createProduct(repository, PRODUCT_PAYLOAD);
  assert.ok(created.ok, `the fixture product must be written: ${JSON.stringify(created)}`);
  return {
    repository,
    blackSmall: created.variantIds[0] as string,
    whiteMedium: created.variantIds[1] as string,
  };
}

async function stockOf(repository: CommerceRepository, variantId: string): Promise<number> {
  const row = (await repository.listInventory()).find((entry) => entry.variantId === variantId);
  assert.ok(row, 'the variant must exist in the inventory read');
  return row.stockQuantity;
}

function draft(overrides: Partial<CheckoutDraft> = {}): CheckoutDraft {
  return {
    customer: {
      fullName: 'زهرا محمدی',
      phoneNumber: '09123456789',
      address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
      postalCode: '1999999999',
    },
    couponCode: null,
    shippingMethodId: DEFAULT_SHIPPING_METHOD_ID,
    lines: [{ variantId: 'placeholder', quantity: 1 }],
    idempotencyKey: crypto.randomUUID(),
    ...overrides,
  };
}

describe('checkout line normalisation (§3.4)', () => {
  it('refuses an empty cart', () => {
    const result = normalizeCheckoutLines([]);
    assert.ok(!result.ok && result.code === 'EMPTY_CART');
  });

  it('refuses a duplicated variant instead of silently summing the two lines', () => {
    const result = normalizeCheckoutLines([
      { variantId: 'v1', quantity: 1 },
      { variantId: 'v1', quantity: 2 },
    ]);
    assert.ok(!result.ok && result.code === 'VALIDATION_ERROR');
    assert.equal(result.field, 'lines');
  });

  it('refuses a blank id and a quantity outside 1..MAX with the rule’s own message', () => {
    const blank = normalizeCheckoutLines([{ variantId: '  ', quantity: 1 }]);
    assert.ok(!blank.ok && blank.code === 'VALIDATION_ERROR');

    const tooMany = normalizeCheckoutLines([
      { variantId: 'v1', quantity: MAX_LINE_QUANTITY + 1 },
    ]);
    assert.ok(!tooMany.ok && tooMany.field === 'quantity');
    assert.ok(!tooMany.ok && tooMany.message.includes('حداکثر'));

    const fractional = normalizeCheckoutLines([{ variantId: 'v1', quantity: 1.5 }]);
    assert.ok(!fractional.ok && fractional.code === 'VALIDATION_ERROR');
  });
});

describe('placeCheckoutOrder — the write path (§3.4)', () => {
  it('writes a PENDING order, resolves the price, applies the coupon and takes the stock', async () => {
    const { repository, blackSmall } = await harness();

    const placed = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({
        couponCode: COUPON_CODE.toLowerCase(),
        lines: [{ variantId: blackSmall, quantity: 2 }],
      }),
    );
    assert.ok(placed.ok, `the checkout must be accepted: ${JSON.stringify(placed)}`);

    const subtotal = DISCOUNT_PRICE * 2;
    assert.deepEqual(
      placed.totals,
      computeCheckoutTotals({
        subtotal,
        discount: Math.floor(subtotal / 4),
        shipping: SHIPPING,
      }),
      'the discount is computed here, not read from the browser',
    );
    assert.equal(placed.couponApplied, true);
    assert.equal(placed.status, 'PENDING');

    // The payment seam can only refuse: nothing was charged, nothing is faked.
    assert.equal(placed.payment.status, 'UNAVAILABLE');
    assert.equal(placed.payment.reference, null);

    const order = await getOrder(repository, placed.orderId);
    assert.equal(order?.status, 'PENDING');
    assert.equal(order?.paymentRefId, null);
    assert.equal(order?.items.length, 1);
    assert.equal(order?.items[0]?.unitPrice, DISCOUNT_PRICE);
    assert.equal(order?.items[0]?.quantity, 2);

    // The coupon counter moved once, and the stock is the order's.
    const coupon = await repository.findCouponByCode(COUPON_CODE);
    assert.equal(coupon?.usedCount, 1);
    assert.equal(await stockOf(repository, blackSmall), 2);
  });

  it('refuses the oversell: a second buyer cannot take stock that is already gone', async () => {
    const { repository, blackSmall } = await harness();

    const first = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ lines: [{ variantId: blackSmall, quantity: 4 }] }),
    );
    assert.ok(first.ok);
    assert.equal(await stockOf(repository, blackSmall), 0);

    const second = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );
    assert.ok(!second.ok);
    assert.equal(second.code, 'STOCK_INSUFFICIENT');
    assert.equal((await listOrders(repository)).length, 1, 'the refusal wrote no order');
    assert.equal(await stockOf(repository, blackSmall), 0, 'and never went negative');
  });

  it('returns the stock when the order is cancelled, exactly once', async () => {
    const { repository, blackSmall } = await harness();

    const placed = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ lines: [{ variantId: blackSmall, quantity: 3 }] }),
    );
    assert.ok(placed.ok);
    assert.equal(await stockOf(repository, blackSmall), 1);

    assert.deepEqual(await transitionOrder(repository, placed.orderId, 'CANCELLED', MERCHANT_TRANSITION), { ok: true });
    assert.equal(await stockOf(repository, blackSmall), 4, 'the line is back on the shelf');

    const again = await transitionOrder(repository, placed.orderId, 'CANCELLED', MERCHANT_TRANSITION);
    assert.ok(!again.ok, 'CANCELLED is terminal');
    assert.equal(await stockOf(repository, blackSmall), 4, 'a refused cancellation returns nothing');
  });

  it('consumes an override price, not the product price, when a variant has one', async () => {
    const { repository, whiteMedium } = await harness();

    const placed = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ lines: [{ variantId: whiteMedium, quantity: 2 }] }),
    );
    assert.ok(placed.ok);
    assert.equal(placed.totals.subtotal, OVERRIDE_PRICE * 2, 'the override wins (D-024)');
    assert.equal(placed.totals.total, OVERRIDE_PRICE * 2 + SHIPPING);
  });

  it('refuses every malformed submission and changes nothing', async () => {
    const { repository, blackSmall } = await harness();
    const draftWith = (overrides: Partial<CheckoutDraft>) =>
      draft({ lines: [{ variantId: blackSmall, quantity: 1 }], ...overrides });

    const cases: Array<{ input: CheckoutDraft; code: string }> = [
      {
        input: draftWith({ customer: { ...draft().customer, phoneNumber: '0912' } }),
        code: 'VALIDATION_ERROR',
      },
      {
        input: draftWith({ customer: { ...draft().customer, postalCode: '123' } }),
        code: 'VALIDATION_ERROR',
      },
      { input: draftWith({ shippingMethodId: 'SAME_DAY_DRONE' }), code: 'SHIPPING_UNKNOWN' },
      { input: draftWith({ couponCode: 'NO-SUCH-CODE' }), code: 'COUPON_INVALID' },
      { input: draftWith({ lines: [] }), code: 'EMPTY_CART' },
    ];

    for (const testCase of cases) {
      const result = await placeCheckoutOrder(repository, mockPaymentGateway, testCase.input);
      assert.ok(!result.ok, `expected a refusal for ${testCase.code}`);
      assert.equal(result.code, testCase.code);
      assert.ok(result.message.length > 0, 'every refusal explains itself');
    }

    assert.deepEqual(await listOrders(repository), [], 'no refusal wrote an order');
    assert.equal(await stockOf(repository, blackSmall), 4, 'no refusal consumed stock');
  });

  it('records a gateway reference when one is issued, and still leaves the order PENDING', async () => {
    const { repository, blackSmall } = await harness();

    const placed = await placeCheckoutOrder(
      repository,
      createMockPaymentGateway({ outcome: 'AUTHORIZED' }),
      draft({ lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );
    assert.ok(placed.ok);
    assert.equal(placed.payment.status, 'AUTHORIZED');
    assert.equal(placed.status, 'PENDING', 'marking an order paid belongs to Phase 6');
    assert.equal(
      (await getOrder(repository, placed.orderId))?.paymentRefId,
      placed.payment.reference,
    );
  });
});

describe('carrier eligibility and persistence (D-175)', () => {
  it('refuses an ineligible single-carrier destination and writes nothing', async () => {
    const { repository, blackSmall } = await harness();
    const localOnly = applyShippingOverrides(VALIDATED_DEFAULT_SHIPPING_CONFIG, {
      enabled: 'EXPRESS_COURIER',
    });

    const refused = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({
        customer: {
          ...draft().customer,
          address: 'مشهد، بلوار وکیل‌آباد، پلاک ۱',
        },
        shippingMethodId: 'EXPRESS_COURIER',
        lines: [{ variantId: blackSmall, quantity: 1 }],
      }),
      localOnly,
    );
    assert.equal(refused.ok, false);
    assert.equal(!refused.ok && refused.code, 'SHIPPING_INELIGIBLE');
    assert.deepEqual(await listOrders(repository), []);
    assert.equal(await stockOf(repository, blackSmall), 4);
  });

  it('refuses a carrier disabled by configuration, without fallback', async () => {
    const { repository, blackSmall } = await harness();
    const subset = applyShippingOverrides(VALIDATED_DEFAULT_SHIPPING_CONFIG, {
      enabled: 'POST_PISHTAZ,EXPRESS_COURIER',
    });

    const refused = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({
        shippingMethodId: 'TIPAX_PAY_ON_DELIVERY',
        lines: [{ variantId: blackSmall, quantity: 1 }],
      }),
      subset,
    );
    assert.equal(refused.ok, false);
    assert.equal(!refused.ok && refused.code, 'SHIPPING_DISABLED');
    assert.deepEqual(await listOrders(repository), []);
  });

  it('stores the chosen carrier snapshot, its server quote and keeps it across a transition', async () => {
    const { repository, blackSmall } = await harness();
    const placed = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({
        shippingMethodId: 'EXPRESS_COURIER',
        lines: [{ variantId: blackSmall, quantity: 1 }],
      }),
    );
    assert.ok(placed.ok);
    assert.equal(placed.totals.shipping, 90_000);

    const before = (await listOrders(repository))[0];
    assert.ok(before);
    assert.equal(before.carrierId, 'EXPRESS_COURIER');
    assert.equal(before.carrierName, 'پیک محلی');
    assert.equal(before.shippingAmount, placed.totals.shipping);
    assert.equal(before.totalAmount, placed.totals.total);

    assert.deepEqual(
      await transitionOrder(repository, placed.orderId, 'PAID', MERCHANT_TRANSITION),
      { ok: true },
    );
    const after = (await getOrder(repository, placed.orderId)) ?? null;
    assert.equal(after?.carrierId, 'EXPRESS_COURIER');
    assert.equal(after?.carrierName, 'پیک محلی');
    assert.equal(after?.shippingAmount, 90_000);
  });
});

describe('coupon application at the write path (§2.4)', () => {
  const EXPIRED_AT = new Date('2026-01-01T00:00:00.000Z');

  it('bills a 100% coupon as shipping only and counts exactly one use', async () => {
    const { repository, blackSmall } = await harness([
      { code: 'FREE100', discountType: 'PERCENT', discountValue: 100, usageLimit: 5 },
    ]);

    const placed = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ couponCode: 'FREE100', lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );

    assert.ok(placed.ok);
    assert.equal(placed.totals.discount, placed.totals.subtotal);
    assert.equal(placed.totals.total, placed.totals.shipping);
    assert.equal((await repository.findCouponByCode('FREE100'))?.usedCount, 1);
  });

  it('caps a fixed coupon larger than the basket at the basket value', async () => {
    const { repository, blackSmall } = await harness([
      { code: 'BIGFIX', discountType: 'FIXED', discountValue: 999_999_999, usageLimit: 5 },
    ]);

    const placed = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ couponCode: 'BIGFIX', lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );

    assert.ok(placed.ok);
    assert.equal(placed.totals.discount, placed.totals.subtotal);
    assert.equal(placed.totals.total, placed.totals.shipping);
    assert.equal((await repository.findCouponByCode('BIGFIX'))?.usedCount, 1);
  });

  it('refuses an expired, below-minimum or exhausted coupon and writes nothing', async () => {
    const cases: Array<{ code: string; coupon: SeedCoupon }> = [
      {
        code: 'EXPIRED20',
        coupon: {
          code: 'EXPIRED20',
          discountType: 'PERCENT',
          discountValue: 20,
          expiresAt: EXPIRED_AT,
        },
      },
      {
        code: 'MINSPEND10',
        coupon: {
          code: 'MINSPEND10',
          discountType: 'PERCENT',
          discountValue: 10,
          minSpend: 99_000_000,
        },
      },
      {
        code: 'USEDUP',
        coupon: {
          code: 'USEDUP',
          discountType: 'PERCENT',
          discountValue: 15,
          usageLimit: 1,
          usedCount: 1,
        },
      },
      {
        code: 'SWITCHEDOFF',
        coupon: {
          code: 'SWITCHEDOFF',
          discountType: 'PERCENT',
          discountValue: 15,
          isActive: false,
        },
      },
    ];

    for (const testCase of cases) {
      const { repository, blackSmall } = await harness([testCase.coupon]);

      const result = await placeCheckoutOrder(
        repository,
        mockPaymentGateway,
        draft({ couponCode: testCase.code, lines: [{ variantId: blackSmall, quantity: 1 }] }),
      );

      assert.equal(result.ok, false, `${testCase.code} must be refused`);
      assert.equal(result.ok ? '' : result.code, 'COUPON_INVALID');
      assert.deepEqual(await listOrders(repository), [], 'no refusal wrote an order');
      assert.equal(
        (await repository.findCouponByCode(testCase.code))?.usedCount,
        testCase.coupon.usedCount ?? 0,
        'no refusal counted a use',
      );
    }
  });

  it('accepts a code case-insensitively and refuses an unknown one', async () => {
    const { repository, blackSmall } = await harness([
      { code: 'LOWER10', discountType: 'PERCENT', discountValue: 10 },
    ]);

    const placed = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ couponCode: ' lower10 ', lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );
    assert.ok(placed.ok);
    assert.equal(placed.couponApplied, true);

    const unknown = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ couponCode: 'NOT-A-COUPON', lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );
    assert.equal(unknown.ok, false);
    assert.equal(unknown.ok ? '' : unknown.code, 'COUPON_INVALID');
  });
});

describe('checkout idempotency (§3.3 hardening)', () => {
  it('returns the same order for a duplicate key and consumes stock/coupon once', async () => {
    const { repository, blackSmall } = await harness();
    const key = crypto.randomUUID();
    const orderDraft = draft({
      idempotencyKey: key,
      couponCode: COUPON_CODE,
      lines: [{ variantId: blackSmall, quantity: 1 }],
    });

    const first = await placeCheckoutOrder(repository, mockPaymentGateway, orderDraft);
    assert.ok(first.ok);
    assert.equal(first.replayed, false);
    const stockAfterFirst = await stockOf(repository, blackSmall);

    const duplicate = await placeCheckoutOrder(repository, mockPaymentGateway, orderDraft);
    assert.ok(duplicate.ok);
    assert.equal(duplicate.orderId, first.orderId);
    assert.equal(duplicate.replayed, true);
    assert.equal(await stockOf(repository, blackSmall), stockAfterFirst);
    assert.equal((await repository.findCouponByCode(COUPON_CODE))?.usedCount, 1);
    assert.equal(await repository.listOrders().then((orders) => orders.length), 1);
  });

  it('resolves concurrent submissions with one key to one order', async () => {
    const { repository, whiteMedium } = await harness();
    const key = crypto.randomUUID();
    const orderDraft = draft({
      idempotencyKey: key,
      lines: [{ variantId: whiteMedium, quantity: 2 }],
    });

    const results = await Promise.all([
      placeCheckoutOrder(repository, mockPaymentGateway, orderDraft),
      placeCheckoutOrder(repository, mockPaymentGateway, orderDraft),
    ]);
    assert.ok(results.every((result) => result.ok));
    assert.equal(results[0]?.ok ? results[0].orderId : '', results[1]?.ok ? results[1].orderId : '');
    assert.equal(await stockOf(repository, whiteMedium), 10);
    assert.equal((await repository.listOrders()).length, 1);
  });

  it('creates distinct orders for distinct keys', async () => {
    const { repository, blackSmall } = await harness();
    const first = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );
    const second = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );
    assert.ok(first.ok && second.ok);
    assert.notEqual(first.orderId, second.orderId);
    assert.equal((await repository.listOrders()).length, 2);
    assert.equal(await stockOf(repository, blackSmall), 2);
  });

  it('leaves a refused key usable because nothing was committed', async () => {
    const { repository, blackSmall } = await harness();
    const key = crypto.randomUUID();
    const refused = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ idempotencyKey: key, lines: [{ variantId: blackSmall, quantity: 9 }] }),
    );
    assert.equal(refused.ok, false);
    assert.equal(await stockOf(repository, blackSmall), 4);

    const accepted = await placeCheckoutOrder(
      repository,
      mockPaymentGateway,
      draft({ idempotencyKey: key, lines: [{ variantId: blackSmall, quantity: 1 }] }),
    );
    assert.ok(accepted.ok);
    assert.equal(accepted.replayed, false);
  });

  it('refuses a key reused with a different cart, recipient, coupon or shipping choice', async () => {
    const { repository, blackSmall } = await harness();
    const key = crypto.randomUUID();
    const base = draft({
      idempotencyKey: key,
      lines: [{ variantId: blackSmall, quantity: 1 }],
    });

    const first = await placeCheckoutOrder(repository, mockPaymentGateway, base);
    assert.ok(first.ok);
    const stockAfterFirst = await stockOf(repository, blackSmall);

    const mismatches: CheckoutDraft[] = [
      { ...base, lines: [{ variantId: blackSmall, quantity: 2 }] },
      { ...base, customer: { ...base.customer, fullName: 'نام دیگری' } },
      { ...base, couponCode: COUPON_CODE },
      { ...base, shippingMethodId: 'EXPRESS_COURIER' },
    ];

    for (const mismatch of mismatches) {
      const result = await placeCheckoutOrder(repository, mockPaymentGateway, mismatch);
      assert.ok(!result.ok, 'a reused key must not replay a different payload');
      assert.equal(result.code, 'IDEMPOTENCY_MISMATCH');
      assert.equal(result.field, 'idempotencyKey');
      assert.ok(!result.message.includes(first.orderId), 'the refusal never exposes the order id');
    }

    assert.equal(await stockOf(repository, blackSmall), stockAfterFirst);
    assert.equal((await repository.findCouponByCode(COUPON_CODE))?.usedCount, 0);
    assert.equal((await repository.listOrders()).length, 1);
  });

  it('refuses a missing or malformed idempotency key before writing', async () => {
    const { repository, blackSmall } = await harness();
    const valid = draft({ lines: [{ variantId: blackSmall, quantity: 1 }] });

    for (const idempotencyKey of ['', 'not-a-uuid', undefined as unknown as string]) {
      const result = await placeCheckoutOrder(
        repository,
        mockPaymentGateway,
        { ...valid, idempotencyKey },
      );
      assert.ok(!result.ok);
      assert.equal(result.code, 'VALIDATION_ERROR');
      assert.equal(result.field, 'idempotencyKey');
    }

    assert.deepEqual(await listOrders(repository), []);
    assert.equal(await stockOf(repository, blackSmall), 4);
  });

  it('never authorises payment a second time for a replay', async () => {
    const { repository, blackSmall } = await harness();
    const authorised = createMockPaymentGateway({ outcome: 'AUTHORIZED' });
    let calls = 0;
    const gateway = {
      id: 'counting',
      authorize: async (request: Parameters<typeof authorised.authorize>[0]) => {
        calls += 1;
        return authorised.authorize(request);
      },
      verifyCallback: authorised.verifyCallback.bind(authorised),
    };

    const orderDraft = draft({ lines: [{ variantId: blackSmall, quantity: 1 }] });
    const first = await placeCheckoutOrder(repository, gateway, orderDraft);
    assert.ok(first.ok);
    assert.equal(calls, 1);
    assert.equal(first.payment.status, 'AUTHORIZED');

    const replay = await placeCheckoutOrder(repository, gateway, orderDraft);
    assert.ok(replay.ok);
    assert.equal(calls, 1, 'the replay must not call the gateway');
    assert.equal(replay.replayed, true);
    assert.equal(replay.payment.status, 'AUTHORIZED');
    assert.equal(replay.payment.reference, first.payment.reference);
  });
});
