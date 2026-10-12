import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  DEFAULT_SHIPPING_METHOD_ID,
  SHIPPING_METHODS,
  shippingAmountFor,
  shippingMethodById,
} from '@/lib/shipping';

/**
 * D-172 §3.4 — shipping selection.
 *
 * The load-bearing rule is the refusal: an unknown method id is never priced as
 * zero and never silently replaced by the default, because a bug that quietly
 * ships for free is worse than a bug that refuses to order.
 */
describe('shipping methods (§3.4)', () => {
  it('offers the three roadmap choices with integer Toman amounts', () => {
    assert.deepEqual(
      SHIPPING_METHODS.map((method) => method.id),
      ['POST_PISHTAZ', 'EXPRESS_COURIER', 'TIPAX_PAY_ON_DELIVERY'],
    );
    for (const method of SHIPPING_METHODS) {
      assert.equal(Number.isInteger(method.amount), true, `${method.id} amount must be integer Toman`);
      assert.ok(method.label.length > 0);
      assert.ok(method.description.length > 0);
    }
    assert.ok(shippingMethodById(DEFAULT_SHIPPING_METHOD_ID), 'the default must exist');
  });

  it('prices a known method and refuses an unknown one instead of guessing', () => {
    assert.equal(shippingAmountFor('POST_PISHTAZ'), 45_000);
    assert.equal(shippingAmountFor('EXPRESS_COURIER'), 90_000);
    assert.equal(shippingAmountFor('TIPAX_PAY_ON_DELIVERY'), 0);
    assert.equal(shippingAmountFor('SAME_DAY_DRONE'), null);
    assert.equal(shippingMethodById('same_day_drone'), undefined);
  });

  it('says out loud that the pay-on-delivery route costs nothing in the order', () => {
    const tipax = shippingMethodById('TIPAX_PAY_ON_DELIVERY');
    assert.equal(tipax?.amount, 0);
    assert.match(tipax?.description ?? '', /تحویل|گیرنده/);
  });
});
