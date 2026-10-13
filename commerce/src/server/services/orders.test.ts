import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { OrderStatus } from '@/db/schema';
import { createMemoryRepository } from '@/server/repository-memory';
import type { MemoryRepositorySeed } from '@/server/repository-memory';
import {
  MERCHANT_TRANSITION,
  getOrder,
  listOrderStatusHistory,
  listOrders,
  setTrackingCode,
  transitionOrder,
} from '@/server/services/orders';

/**
 * D-172 §2.3 — fulfillment writes. The dropdown in the panel offers only legal
 * transitions; these tests are the reason that courtesy is not the guarantee.
 */

const ORDER_ID = '11111111-1111-4111-8111-111111111111';

function seed(status: OrderStatus = 'PENDING'): MemoryRepositorySeed {
  return {
    orders: [
      {
        id: ORDER_ID,
        customerName: 'زهرا محمدی',
        customerPhone: '09120000000',
        postalCode: '1234567890',
        status,
        totalAmount: 1_000_000,
        discountAmount: 0,
        shippingAmount: 50_000,
        trackingCode: null,
        shippingAddress: 'تهران، خیابان ولیعصر',
        paymentRefId: null,
        createdAt: new Date('2026-10-01T10:00:00.000Z'),
        items: [
          {
            sku: 'MANTO-KETI-36-1',
            productTitle: 'مانتو کتی لنین',
            size: '36',
            colorName: 'مشکی',
            quantity: 2,
            unitPrice: 475_000,
          },
        ],
      },
    ],
  };
}

describe('order service — reads (§2.3)', () => {
  it('lists orders with their line count', async () => {
    const orders = await listOrders(createMemoryRepository(seed()));

    assert.equal(orders.length, 1);
    assert.equal(orders[0]?.itemCount, 2);
    assert.equal(orders[0]?.customerPhone, '09120000000');
  });

  it('returns null for an unknown order instead of an empty shell', async () => {
    const repository = createMemoryRepository(seed());
    assert.equal(await getOrder(repository, 'nope'), null);
    assert.notEqual(await getOrder(repository, ORDER_ID), null);
  });
});

describe('order service — status transitions (§2.3)', () => {
  it('walks the legal chain PENDING → PAID → PROCESSING → SHIPPED', async () => {
    const repository = createMemoryRepository(seed('PENDING'));

    assert.equal((await transitionOrder(repository, ORDER_ID, 'PAID', MERCHANT_TRANSITION)).ok, true);
    assert.equal((await getOrder(repository, ORDER_ID))?.status, 'PAID');

    assert.equal((await transitionOrder(repository, ORDER_ID, 'PROCESSING', MERCHANT_TRANSITION)).ok, true);
    assert.equal((await transitionOrder(repository, ORDER_ID, 'SHIPPED', MERCHANT_TRANSITION)).ok, true);
    assert.equal((await getOrder(repository, ORDER_ID))?.status, 'SHIPPED');
  });

  it('cancels while the parcel is still in hand', async () => {
    const repository = createMemoryRepository(seed('PROCESSING'));

    assert.equal((await transitionOrder(repository, ORDER_ID, 'CANCELLED', MERCHANT_TRANSITION)).ok, true);
    assert.equal((await getOrder(repository, ORDER_ID))?.status, 'CANCELLED');
  });

  it('refuses a skip-forward, a repeat and an exit from a terminal state', async () => {
    const pending = createMemoryRepository(seed('PENDING'));
    const skip = await transitionOrder(pending, ORDER_ID, 'SHIPPED', MERCHANT_TRANSITION);
    assert.equal(skip.ok, false);
    assert.ok(!skip.ok && skip.code === 'ILLEGAL_TRANSITION');
    assert.equal((await getOrder(pending, ORDER_ID))?.status, 'PENDING');

    const paid = createMemoryRepository(seed('PAID'));
    const repeat = await transitionOrder(paid, ORDER_ID, 'PAID', MERCHANT_TRANSITION);
    assert.equal(repeat.ok, false);
    assert.ok(!repeat.ok && repeat.code === 'ILLEGAL_TRANSITION');

    const shipped = createMemoryRepository(seed('SHIPPED'));
    const reopen = await transitionOrder(shipped, ORDER_ID, 'CANCELLED', MERCHANT_TRANSITION);
    assert.equal(reopen.ok, false);
    assert.equal((await getOrder(shipped, ORDER_ID))?.status, 'SHIPPED');
  });

  it('reports a missing order', async () => {
    const repository = createMemoryRepository(seed());

    const result = await transitionOrder(repository, 'missing', 'PAID', MERCHANT_TRANSITION);

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'NOT_FOUND');
  });
});

describe('order service — the audit trail (Phase 4 transition)', () => {
  it('appends exactly one row per transition, naming the actor and the status it left', async () => {
    const repository = createMemoryRepository(seed('PENDING'));
    assert.deepEqual(
      await listOrderStatusHistory(repository, ORDER_ID),
      [],
      'a fixture that was never walked through the lifecycle has no trail to invent',
    );

    assert.equal((await transitionOrder(repository, ORDER_ID, 'PAID', MERCHANT_TRANSITION)).ok, true);
    assert.equal(
      (await transitionOrder(repository, ORDER_ID, 'PROCESSING', MERCHANT_TRANSITION)).ok,
      true,
    );

    const trail = await listOrderStatusHistory(repository, ORDER_ID);
    assert.deepEqual(
      trail.map((row) => [row.fromStatus, row.toStatus, row.source]),
      [
        ['PENDING', 'PAID', 'MERCHANT_PANEL'],
        ['PAID', 'PROCESSING', 'MERCHANT_PANEL'],
      ],
      'the previous status is read from the order, never supplied by the caller',
    );
    assert.ok(
      trail.every((row) => row.createdAt instanceof Date),
      'every row is stamped',
    );
  });

  it('records the metadata the caller attaches, and nothing it did not attach', async () => {
    const repository = createMemoryRepository(seed('PENDING'));

    const moved = await transitionOrder(repository, ORDER_ID, 'CANCELLED', {
      source: 'SYSTEM',
      metadata: { reason: 'timeout', sweep: 'nightly' },
    });
    assert.equal(moved.ok, true);

    const [row] = await listOrderStatusHistory(repository, ORDER_ID);
    assert.equal(row?.source, 'SYSTEM');
    assert.deepEqual(row?.metadata, { reason: 'timeout', sweep: 'nightly' });
  });

  it('writes NO row for a refused transition, a repeat, or a refusal before any write', async () => {
    const repository = createMemoryRepository(seed('PENDING'));

    // A skip-forward is refused by the lifecycle map.
    assert.equal((await transitionOrder(repository, ORDER_ID, 'SHIPPED', MERCHANT_TRANSITION)).ok, false);
    // A transition to the status the order is already in is refused too.
    assert.equal((await transitionOrder(repository, ORDER_ID, 'PENDING', MERCHANT_TRANSITION)).ok, false);
    assert.deepEqual(await listOrderStatusHistory(repository, ORDER_ID), []);

    // A legal move writes one row; the same move asked for again writes none.
    assert.equal((await transitionOrder(repository, ORDER_ID, 'PAID', MERCHANT_TRANSITION)).ok, true);
    assert.equal((await transitionOrder(repository, ORDER_ID, 'PAID', MERCHANT_TRANSITION)).ok, false);
    assert.equal((await listOrderStatusHistory(repository, ORDER_ID)).length, 1);
  });

  it('keys the trail by order and stays empty for an order that does not exist', async () => {
    const repository = createMemoryRepository(seed('PENDING'));

    assert.equal((await transitionOrder(repository, 'missing', 'PAID', MERCHANT_TRANSITION)).ok, false);
    assert.deepEqual(await listOrderStatusHistory(repository, 'missing'), []);
  });
});

describe('order service — postal tracking code (§2.3)', () => {
  it('records a valid code once the order is processing or shipped', async () => {
    const repository = createMemoryRepository(seed('PROCESSING'));

    const result = await setTrackingCode(repository, ORDER_ID, ' 24IR1234567890 ');

    assert.equal(result.ok, true);
    assert.equal((await getOrder(repository, ORDER_ID))?.trackingCode, '24IR1234567890');
  });

  it('refuses a code while the order is still pending payment or processing-ineligible', async () => {
    for (const status of ['PENDING', 'PAID', 'CANCELLED'] as const) {
      const repository = createMemoryRepository(seed(status));
      const result = await setTrackingCode(repository, ORDER_ID, '24IR1234567890');
      assert.equal(result.ok, false);
      assert.ok(!result.ok && result.code === 'ILLEGAL_STATE');
      assert.equal((await getOrder(repository, ORDER_ID))?.trackingCode, null);
    }
  });

  it('refuses a malformed code and leaves the stored value untouched', async () => {
    const repository = createMemoryRepository(seed('SHIPPED'));

    for (const bad of ['123', 'not a tracking code!', 'کد۱۲۳۴۵۶۷۸']) {
      const result = await setTrackingCode(repository, ORDER_ID, bad);
      assert.equal(result.ok, false);
      assert.ok(!result.ok && result.code === 'VALIDATION_ERROR');
    }
    assert.equal((await getOrder(repository, ORDER_ID))?.trackingCode, null);
  });

  it('reports a missing order', async () => {
    const repository = createMemoryRepository(seed('SHIPPED'));

    const result = await setTrackingCode(repository, 'missing', '24IR1234567890');

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'NOT_FOUND');
  });
});
