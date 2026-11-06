import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { CouponRuleInput } from '@/contracts/storefront';
import {
  MAX_LINE_QUANTITY,
  computeCheckoutTotals,
  evaluateCoupon,
  quantityProblem,
} from '@/lib/checkout-rules';
import { MAX_MONEY_TOMAN } from '@/lib/validation';

/**
 * D-172 §3.4 — money arithmetic and coupon eligibility.
 *
 * The properties that matter are the ones a customer would notice: a discount
 * can never exceed the basket, a total can never go negative, and an
 * ineligible coupon is refused with a reason instead of silently ignored.
 */

const now = new Date('2026-10-10T12:00:00.000Z');

function coupon(overrides: Partial<CouponRuleInput> = {}): CouponRuleInput {
  return {
    id: 'c1',
    code: 'LIVE25',
    discountType: 'PERCENT',
    discountValue: 25,
    minSpend: 0,
    expiresAt: null,
    usageLimit: null,
    usedCount: 0,
    isActive: true,
    ...overrides,
  };
}

describe('checkout arithmetic (§3.4)', () => {
  it('subtracts the discount and adds shipping', () => {
    assert.deepEqual(
      computeCheckoutTotals({ subtotal: 2_450_000, discount: 150_000, shipping: 45_000 }),
      { subtotal: 2_450_000, discount: 150_000, shipping: 45_000, total: 2_345_000 },
    );
  });

  it('never lets a discount exceed the basket or a total go negative', () => {
    assert.deepEqual(
      computeCheckoutTotals({ subtotal: 100_000, discount: 500_000, shipping: 0 }),
      { subtotal: 100_000, discount: 100_000, shipping: 0, total: 0 },
    );
    const negative = computeCheckoutTotals({ subtotal: -5, discount: -10, shipping: -1 });
    assert.deepEqual(negative, { subtotal: 0, discount: 0, shipping: 0, total: 0 });
  });
});

describe('coupon eligibility (§3.4)', () => {
  it('floors a percentage discount so it can never round up past the basket', () => {
    const decision = evaluateCoupon(coupon({ discountValue: 33 }), 10_001, now);
    assert.ok(decision.ok);
    assert.equal(decision.discount, 3_300);
  });

  it('caps a fixed discount at the subtotal', () => {
    const decision = evaluateCoupon(
      coupon({ discountType: 'FIXED', discountValue: 900_000 }),
      250_000,
      now,
    );
    assert.ok(decision.ok);
    assert.equal(decision.discount, 250_000);
  });

  it('refuses inactive, expired, exhausted and below-minimum coupons, each by name', () => {
    const inactive = evaluateCoupon(coupon({ isActive: false }), 1_000_000, now);
    assert.ok(!inactive.ok && inactive.code === 'INACTIVE');

    const expired = evaluateCoupon(coupon({ expiresAt: new Date(now.getTime() - 1) }), 1_000_000, now);
    assert.ok(!expired.ok && expired.code === 'EXPIRED');

    const exhausted = evaluateCoupon(coupon({ usageLimit: 3, usedCount: 3 }), 1_000_000, now);
    assert.ok(!exhausted.ok && exhausted.code === 'EXHAUSTED');

    const belowMinimum = evaluateCoupon(coupon({ minSpend: 5_000_000 }), 1_000_000, now);
    assert.ok(!belowMinimum.ok && belowMinimum.code === 'MIN_SPEND');

    for (const decision of [inactive, expired, exhausted, belowMinimum]) {
      assert.ok(!decision.ok && decision.message.length > 0, 'every refusal explains itself');
    }
  });

  it('checks expiry before exhaustion, agreeing with the coupon table state', () => {
    const both = evaluateCoupon(
      coupon({ expiresAt: new Date(now.getTime() - 1), usageLimit: 1, usedCount: 1 }),
      1_000_000,
      now,
    );
    assert.ok(!both.ok && both.code === 'EXPIRED');
  });

  it('accepts a coupon exactly at its expiry instant boundary and minimum spend', () => {
    const decision = evaluateCoupon(
      coupon({ expiresAt: new Date(now.getTime() + 1), minSpend: 1_000_000 }),
      1_000_000,
      now,
    );
    assert.ok(decision.ok, 'at-or-above the minimum spend is eligible');
    assert.equal(decision.code, 'LIVE25');
  });

  it('bills a 100% coupon as shipping only, never as a credit', () => {
    const decision = evaluateCoupon(coupon({ discountValue: 100 }), 870_000, now);
    assert.ok(decision.ok);
    assert.equal(decision.discount, 870_000);

    const totals = computeCheckoutTotals({
      subtotal: 870_000,
      discount: decision.discount,
      shipping: 45_000,
    });
    assert.deepEqual(totals, {
      subtotal: 870_000,
      discount: 870_000,
      shipping: 45_000,
      total: 45_000,
    });
  });

  it('yields a zero discount on a zero-subtotal basket instead of a negative one', () => {
    const percent = evaluateCoupon(coupon({ discountValue: 25 }), 0, now);
    assert.ok(percent.ok);
    assert.equal(percent.discount, 0);

    const fixed = evaluateCoupon(
      coupon({ discountType: 'FIXED', discountValue: 500_000 }),
      0,
      now,
    );
    assert.ok(fixed.ok);
    assert.equal(fixed.discount, 0);

    // Even a hand-built discount larger than the basket cannot produce a total
    // below zero (the totals function clamps as a last line of defence).
    assert.deepEqual(computeCheckoutTotals({ subtotal: 0, discount: 500_000, shipping: 0 }), {
      subtotal: 0,
      discount: 0,
      shipping: 0,
      total: 0,
    });
  });

  it('clamps a ceiling-sized fixed discount to a one-Toman basket', () => {
    const decision = evaluateCoupon(
      coupon({ discountType: 'FIXED', discountValue: MAX_MONEY_TOMAN }),
      1,
      now,
    );
    assert.ok(decision.ok);
    assert.equal(decision.discount, 1);
  });

  it('floors a percentage that lands below one Toman to no discount at all', () => {
    const decision = evaluateCoupon(coupon({ discountValue: 1 }), 99, now);
    assert.ok(decision.ok);
    assert.equal(decision.discount, 0, '0.99 Toman is floored, never rounded up');
  });

  it('computes a percentage exactly once the product leaves the safe-integer range', () => {
    // `huge × 100` is past 2^53, where a double starts dropping whole Tomans.
    const huge = 90_071_992_547_400;

    const full = evaluateCoupon(coupon({ discountValue: 100 }), huge, now);
    assert.ok(full.ok);
    assert.equal(full.discount, huge);

    const onePercent = evaluateCoupon(coupon({ discountValue: 1 }), huge, now);
    assert.ok(onePercent.ok);
    assert.equal(onePercent.discount, 900_719_925_474);
    assert.equal(Number.isSafeInteger(onePercent.discount), true);
  });
});

describe('quantity bounds (§3.4)', () => {
  it('accepts 1..MAX and refuses everything else with a Persian reason', () => {
    assert.equal(quantityProblem(1), null);
    assert.equal(quantityProblem(MAX_LINE_QUANTITY), null);
    assert.ok(quantityProblem(0)?.includes('حداقل'));
    assert.ok(quantityProblem(MAX_LINE_QUANTITY + 1)?.includes('حداکثر'));
    assert.ok(quantityProblem(1.5) !== null);
    assert.ok(quantityProblem('2') !== null);
    assert.ok(quantityProblem(null) !== null);
  });
});
