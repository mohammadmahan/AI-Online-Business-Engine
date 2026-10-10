import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { OrderStatus } from '@/db/schema';
import {
  ORDER_STATUS_LABELS,
  ORDER_TRANSITIONS,
  TRACKING_ALLOWED_STATUSES,
  canSetTracking,
  canTransition,
  computeTotals,
  isTerminal,
  nextStatuses,
  transitionConfirmation,
} from '@/lib/order-rules';
import type { OrderDetail } from '@/server/repository';

/**
 * D-172 §2.3 — the lifecycle map. It is the single source of truth for both the
 * dropdown the merchant sees and the refusal the server returns, so these tests
 * pin the edges (not just the states) that the roadmap left to be inferred.
 */
describe('order lifecycle (§2.3)', () => {
  const ALL_STATUSES: OrderStatus[] = ['PENDING', 'PAID', 'PROCESSING', 'SHIPPED', 'CANCELLED'];

  it('covers every status in the schema enum', () => {
    assert.deepEqual(Object.keys(ORDER_TRANSITIONS).sort(), [...ALL_STATUSES].sort());
    for (const status of ALL_STATUSES) {
      assert.ok(ORDER_STATUS_LABELS[status].length > 0);
    }
  });

  it('moves money before the parcel and stops at the shipped/ cancelled ends', () => {
    assert.deepEqual(nextStatuses('PENDING'), ['PAID', 'CANCELLED']);
    assert.deepEqual(nextStatuses('PAID'), ['PROCESSING', 'CANCELLED']);
    assert.deepEqual(nextStatuses('PROCESSING'), ['SHIPPED', 'CANCELLED']);
    assert.deepEqual(nextStatuses('SHIPPED'), []);
    assert.deepEqual(nextStatuses('CANCELLED'), []);
  });

  it('never allows a self-transition or a skip-forward', () => {
    for (const status of ALL_STATUSES) {
      assert.equal(canTransition(status, status), false);
    }
    assert.equal(canTransition('PENDING', 'PROCESSING'), false);
    assert.equal(canTransition('PENDING', 'SHIPPED'), false);
    assert.equal(canTransition('PAID', 'SHIPPED'), false);
    assert.equal(canTransition('CANCELLED', 'PAID'), false);
    assert.equal(canTransition('SHIPPED', 'CANCELLED'), false);
    assert.equal(canTransition('PENDING', 'PAID'), true);
  });

  it('treats shipped and cancelled as terminal', () => {
    assert.equal(isTerminal('SHIPPED'), true);
    assert.equal(isTerminal('CANCELLED'), true);
    assert.equal(isTerminal('PROCESSING'), false);
  });

  it('accepts a tracking code only once the order is moving', () => {
    assert.deepEqual(TRACKING_ALLOWED_STATUSES, ['PROCESSING', 'SHIPPED']);
    assert.equal(canSetTracking('PENDING'), false);
    assert.equal(canSetTracking('PAID'), false);
    assert.equal(canSetTracking('PROCESSING'), true);
    assert.equal(canSetTracking('SHIPPED'), true);
    assert.equal(canSetTracking('CANCELLED'), false);
  });
});

describe('transition confirmations (§2.3 / irreversible actions)', () => {
  it('styles cancellation as destructive and states it is final', () => {
    const cancel = transitionConfirmation('CANCELLED');
    assert.equal(cancel.danger, true);
    assert.match(cancel.title, /بازگشت‌پذیر نیست/);
    assert.match(cancel.body, /پایانی/);
  });

  it('confirms a forward move without the destructive style, naming the target', () => {
    const ship = transitionConfirmation('SHIPPED');
    assert.equal(ship.danger, false);
    assert.match(ship.title, /ارسال‌شده/);
    assert.match(ship.body, /یک‌طرفه/);
  });

  it('never implies an audit record that does not exist', () => {
    for (const status of Object.keys(ORDER_TRANSITIONS) as OrderStatus[]) {
      const copy = transitionConfirmation(status);
      assert.ok(copy.title.length > 0);
      assert.ok(copy.body.length > 0);
      assert.match(copy.body, /تاریخ آخرین ویرایش/);
      assert.doesNotMatch(copy.body, /دفتر رویداد|audit/i);
    }
  });

  it('has a confirmation for every status the panel can reach', () => {
    const reachable = new Set(Object.values(ORDER_TRANSITIONS).flat());
    assert.ok(reachable.size > 0);
    for (const status of reachable) {
      const copy = transitionConfirmation(status);
      if (status === 'CANCELLED') {
        // Cancellation is worded as the ACTION (لغو), not as the resulting state
        // (لغوشده) — the resulting state and its code are shown in the dialog's
        // badge, which the component renders.
        assert.match(copy.title, /لغو/);
        assert.equal(copy.danger, true);
      } else {
        assert.match(copy.title, new RegExp(ORDER_STATUS_LABELS[status]));
        assert.equal(copy.danger, false);
      }
    }
  });
});

function order(overrides: Partial<OrderDetail> = {}): OrderDetail {
  return {
    id: 'order-1',
    customerName: 'زهرا محمدی',
    customerPhone: '09120000000',
    status: 'PAID',
    totalAmount: 1_000_000,
    discountAmount: 0,
    shippingAmount: 50_000,
    trackingCode: null,
    createdAt: new Date('2026-10-01T10:00:00.000Z'),
    itemCount: 2,
    shippingAddress: 'تهران، خیابان ولیعصر',
    postalCode: '1234567890',
    paymentRefId: 'zp-1',
    items: [
      {
        id: 'item-1',
        sku: 'MANTO-KETI-36-1',
        productTitle: 'مانتو کتی لنین',
        size: '36',
        colorName: 'مشکی',
        quantity: 2,
        unitPrice: 475_000,
      },
    ],
    ...overrides,
  };
}

describe('packing slip arithmetic (§2.3)', () => {
  it('recomputes the payable amount from the lines', () => {
    const totals = computeTotals(order());
    assert.equal(totals.itemsTotal, 950_000);
    assert.equal(totals.payable, 1_000_000);
    assert.equal(totals.discountAmount, 0);
    assert.equal(totals.shippingAmount, 50_000);
    assert.equal(totals.consistent, true);
  });

  it('subtracts a discount and reports inconsistency against the stored total', () => {
    const totals = computeTotals(
      order({ discountAmount: 100_000, totalAmount: 900_000 }),
    );
    assert.equal(totals.payable, 900_000);
    assert.equal(totals.consistent, true);

    const drifted = computeTotals(
      order({ discountAmount: 100_000, totalAmount: 1_000_000 }),
    );
    assert.equal(drifted.payable, 900_000);
    assert.equal(drifted.storedTotal, 1_000_000);
    assert.equal(drifted.consistent, false);
  });

  it('sums multiple lines', () => {
    const totals = computeTotals(
      order({
        shippingAmount: 0,
        totalAmount: 1_250_000,
        items: [
          {
            id: 'item-1',
            sku: 'A',
            productTitle: 'مانتو',
            size: '36',
            colorName: 'مشکی',
            quantity: 1,
            unitPrice: 1_000_000,
          },
          {
            id: 'item-2',
            sku: 'B',
            productTitle: 'شال',
            size: 'FreeSize',
            colorName: 'کرم',
            quantity: 5,
            unitPrice: 50_000,
          },
        ],
      }),
    );
    assert.equal(totals.itemsTotal, 1_250_000);
    assert.equal(totals.consistent, true);
  });
});
