import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { CouponRow } from '@/contracts/promotions';
import {
  COUPON_STATE_LABELS,
  COUPON_STATE_TONE,
  couponState,
  describeDiscount,
  listCouponViews,
  toCouponView,
} from '@/lib/coupon-rules';

/**
 * D-172 §2.4 — state is DERIVED, never stored. These tests are the reason an
 * expired or exhausted code can never render as usable in the panel
 * (fail-closed display, D-171 §2.2).
 */

const NOW = new Date('2026-10-10T00:00:00.000Z');

function coupon(overrides: Partial<CouponRow> = {}): CouponRow {
  return {
    id: 'coupon-1',
    code: 'NOROOZ1405',
    discountType: 'PERCENT',
    discountValue: 20,
    minSpend: 500_000,
    expiresAt: null,
    usageLimit: null,
    usedCount: 0,
    isActive: true,
    description: null,
    createdAt: NOW,
    updatedAt: NOW,
    ...overrides,
  };
}

describe('coupon state (§2.4)', () => {
  it('is ACTIVE for an enabled, unexpired, unexhausted coupon', () => {
    assert.equal(couponState(coupon(), NOW), 'ACTIVE');
    assert.equal(couponState(coupon({ expiresAt: new Date('2027-01-01T00:00:00.000Z') }), NOW), 'ACTIVE');
    assert.equal(couponState(coupon({ usageLimit: 10, usedCount: 9 }), NOW), 'ACTIVE');
  });

  it('is INACTIVE when switched off, and that wins over expiry', () => {
    assert.equal(couponState(coupon({ isActive: false }), NOW), 'INACTIVE');
    assert.equal(
      couponState(
        coupon({ isActive: false, expiresAt: new Date('2026-01-01T00:00:00.000Z') }),
        NOW,
      ),
      'INACTIVE',
    );
  });

  it('is EXPIRED at the instant of expiry, not a second later', () => {
    assert.equal(couponState(coupon({ expiresAt: NOW }), NOW), 'EXPIRED');
    assert.equal(couponState(coupon({ expiresAt: new Date('2026-10-09T23:59:59.000Z') }), NOW), 'EXPIRED');
  });

  it('is EXHAUSTED once the usage limit is reached', () => {
    assert.equal(couponState(coupon({ usageLimit: 10, usedCount: 10 }), NOW), 'EXHAUSTED');
    assert.equal(couponState(coupon({ usageLimit: 10, usedCount: 11 }), NOW), 'EXHAUSTED');
  });

  it('exposes a Persian label and a tone for every state', () => {
    for (const state of ['ACTIVE', 'INACTIVE', 'EXPIRED', 'EXHAUSTED'] as const) {
      assert.ok(COUPON_STATE_LABELS[state].length > 0);
      assert.ok(['success', 'neutral', 'warning'].includes(COUPON_STATE_TONE[state]));
    }
  });

  it('projects rows and never mutates the stored row', () => {
    const row = coupon({ isActive: false });
    const view = toCouponView(row, NOW);
    assert.equal(view.state, 'INACTIVE');
    assert.equal('state' in row, false);
    assert.equal(listCouponViews([row, coupon({ id: 'c2' })], NOW).length, 2);
  });
});

describe('coupon description (§2.4)', () => {
  it('describes a percentage coupon', () => {
    assert.deepEqual(describeDiscount(coupon()), { code: 'PERCENT', label: '٪20' });
  });

  it('describes a fixed-amount coupon in Toman', () => {
    assert.deepEqual(
      describeDiscount(coupon({ discountType: 'FIXED', discountValue: 150_000 })),
      { code: 'FIXED', label: '150000 تومان' },
    );
  });
});
