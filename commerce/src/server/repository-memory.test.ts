import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import { mockPaymentGateway } from '@/server/payments/gateway';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §6.1 — the memory double's payment-authorisation storage.
 *
 * The ZarinPal adapter keeps NO state: it persists the authority on the order and
 * reads it back at callback time. The double therefore has to behave like the
 * `commerce.orders` columns it stands in for, or an adapter test would prove a
 * rule the real database rejects. What is asserted here is the STORAGE contract
 * (`recordPaymentAuthorization` / `findPaymentAuthorization`), not the adapter.
 *
 * Orders come from the REAL checkout service: a hand-built fixture could claim a
 * `PENDING` order that no checkout would ever produce.
 */

const AMOUNT = 2_450_000;
const SHIPPING = DEFAULT_SHIPPING_METHOD_ID;
const PROVIDER = 'zarinpal';

function productPayload(slug: string): ProductCreatePayload {
  return {
    categoryId: 'cat-1',
    title: 'مانتو کتان پرداخت',
    slug,
    basePrice: AMOUNT,
    discountPrice: null,
    descriptionRaw: 'مانتو کتان برای آزمون ثبت شناسهٔ پرداخت.',
    descriptionHtml: '<p>مانتو کتان</p>',
    fabricType: 'کتان',
    season: 'تابستان',
    status: 'PUBLISHED',
    variants: [
      { sku: `${slug}-S`, colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 5 },
    ],
    images: [],
  };
}

/** Places one PENDING order through the production checkout path. */
async function placeOrder(
  repository: CommerceRepository,
  slug: string,
  quantity = 1,
): Promise<string> {
  const created = await createProduct(repository, productPayload(slug));
  assert.ok(created.ok, `the fixture product must be written: ${JSON.stringify(created)}`);

  const draft: CheckoutDraft = {
    customer: {
      fullName: 'زهرا محمدی',
      phoneNumber: '09123456789',
      address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
      postalCode: '1999999999',
    },
    couponCode: null,
    shippingMethodId: SHIPPING,
    lines: [{ variantId: created.variantIds[0] as string, quantity }],
  };

  const placed = await placeCheckoutOrder(repository, mockPaymentGateway, draft);
  assert.ok(placed.ok, `the fixture order must be written: ${JSON.stringify(placed)}`);
  return placed.orderId;
}

describe('memory repository — payment authorisations (§6.1)', () => {
  it('stores the authorisation on the order and reads it back by provider + authority', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository, 'auth-store-1');

    const written = await repository.recordPaymentAuthorization({
      orderId,
      provider: PROVIDER,
      authority: 'A-1',
      amount: AMOUNT,
    });
    assert.equal(written, true);

    assert.deepEqual(await repository.findPaymentAuthorization(PROVIDER, 'A-1'), {
      orderId,
      provider: PROVIDER,
      authority: 'A-1',
      amount: AMOUNT,
    });

    // Requesting a payment moves no money: no reference is stamped and the
    // status is untouched (AC-8).
    const order = await repository.getOrderDetail(orderId);
    assert.equal(order?.status, 'PENDING');
    assert.equal(order?.paymentRefId, null);
  });

  it('does not resolve an authority through the wrong provider', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository, 'auth-store-2');
    await repository.recordPaymentAuthorization({
      orderId,
      provider: PROVIDER,
      authority: 'A-2',
      amount: AMOUNT,
    });

    assert.equal(await repository.findPaymentAuthorization('zibal', 'A-2'), null);
    assert.equal(await repository.findPaymentAuthorization(PROVIDER, 'A-other'), null);
  });

  it('refuses an unknown order, writing nothing', async () => {
    const repository = createMemoryRepository();

    const written = await repository.recordPaymentAuthorization({
      orderId: 'no-such-order',
      provider: PROVIDER,
      authority: 'A-3',
      amount: AMOUNT,
    });

    assert.equal(written, false);
    assert.equal(await repository.findPaymentAuthorization(PROVIDER, 'A-3'), null);
  });

  it('refuses an order that is no longer PENDING, writing nothing', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository, 'auth-store-4');
    const cancelled = await transitionOrder(repository, orderId, 'CANCELLED', MERCHANT_TRANSITION);
    assert.ok(cancelled.ok, `the fixture order must be cancellable: ${JSON.stringify(cancelled)}`);

    const written = await repository.recordPaymentAuthorization({
      orderId,
      provider: PROVIDER,
      authority: 'A-4',
      amount: AMOUNT,
    });

    assert.equal(written, false);
    assert.equal(await repository.findPaymentAuthorization(PROVIDER, 'A-4'), null);
  });
});

describe('memory repository — payment authorisation invariants (§6.1)', () => {
  it('supersedes the previous authorisation when the customer retries', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository, 'auth-store-5');

    await repository.recordPaymentAuthorization({
      orderId,
      provider: PROVIDER,
      authority: 'A-old',
      amount: AMOUNT,
    });
    await repository.recordPaymentAuthorization({
      orderId,
      provider: PROVIDER,
      authority: 'A-new',
      amount: AMOUNT + 1,
    });

    assert.equal(
      await repository.findPaymentAuthorization(PROVIDER, 'A-old'),
      null,
      'the superseded authority must not remain resolvable',
    );
    assert.deepEqual(await repository.findPaymentAuthorization(PROVIDER, 'A-new'), {
      orderId,
      provider: PROVIDER,
      authority: 'A-new',
      amount: AMOUNT + 1,
    });
  });

  it('refuses to record one authority against two different orders', async () => {
    const repository = createMemoryRepository();
    const first = await placeOrder(repository, 'auth-store-6');
    const second = await placeOrder(repository, 'auth-store-7');

    await repository.recordPaymentAuthorization({
      orderId: first,
      provider: PROVIDER,
      authority: 'A-shared',
      amount: AMOUNT,
    });

    // Mirrors `orders_payment_authority_unique`: a callback that resolves to two
    // orders is not a representable state, so the write is refused rather than
    // guessed at.
    await assert.rejects(
      repository.recordPaymentAuthorization({
        orderId: second,
        provider: PROVIDER,
        authority: 'A-shared',
        amount: AMOUNT,
      }),
    );

    assert.equal((await repository.findPaymentAuthorization(PROVIDER, 'A-shared'))?.orderId, first);
  });
});
