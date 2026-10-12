import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { MAX_LINE_QUANTITY, computeCheckoutTotals } from '@/lib/checkout-rules';
import { DEFAULT_SHIPPING_METHOD_ID, shippingAmountFor } from '@/lib/shipping';
import { createMockPaymentGateway, mockPaymentGateway } from '@/server/payments/gateway';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { normalizeCheckoutLines, placeCheckoutOrder } from '@/server/services/checkout';
import { createProduct } from '@/server/services/products';
import { getOrder, listOrders, transitionOrder } from '@/server/services/orders';

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

async function harness(): Promise<Harness> {
  const repository = createMemoryRepository({
    coupons: [{ code: COUPON_CODE, discountType: 'PERCENT', discountValue: 25, usageLimit: 3 }],
  });
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

    assert.deepEqual(await transitionOrder(repository, placed.orderId, 'CANCELLED'), { ok: true });
    assert.equal(await stockOf(repository, blackSmall), 4, 'the line is back on the shelf');

    const again = await transitionOrder(repository, placed.orderId, 'CANCELLED');
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
