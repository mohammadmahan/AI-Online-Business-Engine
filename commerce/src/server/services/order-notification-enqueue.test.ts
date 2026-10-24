import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { ORDER_CONFIRMED_KIND, SMS_CHANNEL, orderReference } from '@/lib/notification-rules';
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import { mockPaymentGateway } from '@/server/payments/gateway';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';
import { applyPaymentCallback } from '@/server/services/payment-webhook';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §6.2 — the ENQUEUE side: which status moves queue a message, and how many.
 *
 * The claim under test is the one a concurrent payment makes easy to get wrong:
 * the payment pipeline may run three times for one order (a browser return plus
 * two provider retries), and the customer must still receive ONE confirmation.
 * The guarantee is structural — `(order_id, kind, channel)` is unique and the row
 * is written in the same transaction as the `PAID` move — so these tests assert
 * row COUNTS and a clean absence of PII rather than a boolean a caller could set.
 *
 * Everything runs on the in-memory double through the REAL checkout and REAL
 * callback pipeline; the storage-level concurrency is proven against PostgreSQL in
 * `smoke:db`.
 */

let fixtureSequence = 0;

function productPayload(slug: string): ProductCreatePayload {
  return {
    categoryId: 'cat-1',
    title: 'مانتو کتان اطلاع‌رسانی',
    slug,
    basePrice: 1_850_000,
    discountPrice: null,
    descriptionRaw: 'مانتو کتان برای آزمون صفِ اطلاع‌رسانی.',
    descriptionHtml: '<p>مانتو کتان</p>',
    fabricType: 'کتان',
    season: 'تابستان',
    status: 'PUBLISHED',
    variants: [
      {
        sku: `${slug}-S`,
        colorName: 'مشکی',
        colorHex: '#111111',
        size: 'S',
        stockQuantity: 5,
      },
    ],
    images: [],
  };
}

function checkoutDraft(variantId: string): CheckoutDraft {
  return {
    customer: {
      fullName: 'زهرا محمدی',
      phoneNumber: '09123456789',
      address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
      postalCode: '1999999999',
    },
    couponCode: null,
    shippingMethodId: DEFAULT_SHIPPING_METHOD_ID,
    lines: [{ variantId, quantity: 1 }],
  };
}

/** A real PENDING order from the production checkout path. */
async function placeOrder(repository: CommerceRepository): Promise<string> {
  fixtureSequence += 1;
  const created = await createProduct(repository, productPayload(`notify-${fixtureSequence}`));
  assert.ok(created.ok, `fixture product must be written: ${JSON.stringify(created)}`);

  const placed = await placeCheckoutOrder(
    repository,
    mockPaymentGateway,
    checkoutDraft(created.variantIds[0] as string),
  );
  assert.ok(placed.ok, `fixture order must be written: ${JSON.stringify(placed)}`);
  return placed.orderId;
}

describe('§6.2 a PAID transition queues the confirmation SMS', () => {
  it('writes exactly one PENDING row, atomically with the status move', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository);

    const result = await applyPaymentCallback(repository, {
      orderId,
      status: 'PAID',
      reference: 'ZP-REF-6001',
    });
    assert.equal(result.ok, true);

    const rows = await repository.listOrderNotifications(orderId);
    assert.equal(rows.length, 1);
    const row = rows[0];
    assert.ok(row);
    assert.equal(row.kind, ORDER_CONFIRMED_KIND);
    assert.equal(row.channel, SMS_CHANNEL);
    assert.equal(row.status, 'PENDING');
    assert.equal(row.attempts, 0);
    assert.equal(row.sentAt, null);
    assert.equal(row.providerMessageId, null);
    assert.deepEqual(row.payload, { orderRef: orderReference(orderId) });

    // The queue holds NO customer data: the recipient is resolved from the
    // customer record at dispatch time, not copied here (see the schema note).
    assert.ok(!JSON.stringify(row).includes('09123456789'));
    assert.ok(!JSON.stringify(row).includes('زهرا'));
  });

  it('queues ONE row for concurrent duplicate deliveries of the same payment', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository);

    const verdicts = await Promise.all(
      Array.from({ length: 3 }, () =>
        applyPaymentCallback(repository, {
          orderId,
          status: 'PAID',
          reference: 'ZP-REF-6002',
        }),
      ),
    );

    assert.equal(verdicts.filter((verdict) => verdict.ok).length, 3);
    const rows = await repository.listOrderNotifications(orderId);
    assert.equal(rows.length, 1);

    // …and the audit trail still holds exactly one PAID row, so "one SMS" is the
    // same fact as "one transition" rather than a second counter.
    const trail = await repository.listOrderStatusHistory(orderId);
    assert.equal(trail.filter((entry) => entry.toStatus === 'PAID').length, 1);
  });

  it('is idempotent across a replay of an already-PAID order', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository);

    await applyPaymentCallback(repository, { orderId, status: 'PAID', reference: 'ZP-REF-6003' });
    const replay = await applyPaymentCallback(repository, {
      orderId,
      status: 'PAID',
      reference: 'ZP-REF-6003',
    });

    assert.equal(replay.ok, true);
    assert.equal(replay.ok && replay.duplicate, true);
    assert.equal((await repository.listOrderNotifications(orderId)).length, 1);
  });
});

describe('§6.2 transitions that queue nothing', () => {
  it('a cancellation writes no notification', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository);

    const result = await applyPaymentCallback(repository, {
      orderId,
      status: 'CANCELLED',
      reference: null,
    });
    assert.equal(result.ok, true);
    assert.deepEqual(await repository.listOrderNotifications(orderId), []);
  });

  it('a merchant fulfilment move writes no notification', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository);

    assert.deepEqual(await transitionOrder(repository, orderId, 'PAID', MERCHANT_TRANSITION), {
      ok: true,
    });
    assert.deepEqual(await transitionOrder(repository, orderId, 'PROCESSING', MERCHANT_TRANSITION), {
      ok: true,
    });
    assert.deepEqual(await repository.listOrderNotifications(orderId), []);
  });

  it('a FORBIDDEN edge (PAID on a shipped order) writes no notification', async () => {
    const repository = createMemoryRepository();
    const orderId = await placeOrder(repository);

    await applyPaymentCallback(repository, { orderId, status: 'PAID', reference: 'ZP-REF-6004' });
    await transitionOrder(repository, orderId, 'PROCESSING', MERCHANT_TRANSITION);
    await transitionOrder(repository, orderId, 'SHIPPED', MERCHANT_TRANSITION);

    const late = await applyPaymentCallback(repository, {
      orderId,
      status: 'PAID',
      reference: 'ZP-REF-6004',
    });
    assert.equal(late.ok, false);
    assert.equal(late.ok === false ? late.code : '', 'ILLEGAL_TRANSITION');

    // The row from the FIRST payment is still the only one: the refusal added
    // neither a transition nor an announcement.
    const rows = await repository.listOrderNotifications(orderId);
    assert.equal(rows.length, 1);
  });
});

