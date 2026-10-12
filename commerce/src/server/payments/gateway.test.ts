import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { createMockPaymentGateway, mockPaymentGateway } from '@/server/payments/gateway';

/**
 * D-172 §3.4 / AC-8 — the payment seam is fail-closed.
 *
 * The property that protects the business is the DEFAULT: the instance the app
 * wires must be incapable of reporting a payment it did not take. The other
 * outcomes exist so the order path's handling of a real gateway is testable.
 */
describe('payment gateway adapter (§3.4)', () => {
  it('refuses to authorize by default — an unselected provider is never a fake success', async () => {
    const attempt = await mockPaymentGateway.authorize({
      orderId: '11111111-1111-1111-1111-111111111111',
      amount: 2_345_000,
      description: 'سفارش فروشگاه',
    });

    assert.equal(attempt.status, 'UNAVAILABLE');
    assert.equal(attempt.code, 'PROVIDER_NOT_SELECTED');
    assert.equal(attempt.reference, null);
    assert.match(attempt.message, /درگاه پرداخت/);
    assert.match(attempt.message, /در انتظار پرداخت/, 'the customer is told the order stays unpaid');
    assert.equal(mockPaymentGateway.id, 'mock');
  });

  it('reports a decline without a reference', async () => {
    const gateway = createMockPaymentGateway({ outcome: 'DECLINED' });
    const attempt = await gateway.authorize({
      orderId: 'o1',
      amount: 100_000,
      description: 'سفارش',
    });
    assert.equal(attempt.status, 'DECLINED');
    assert.equal(attempt.reference, null);
    assert.equal(attempt.code, 'MOCK_DECLINED');
  });

  it('marks a deliberate test authorization as a mock, never as a provider reference', async () => {
    const gateway = createMockPaymentGateway({ outcome: 'AUTHORIZED' });
    const attempt = await gateway.authorize({
      orderId: 'order-42',
      amount: 100_000,
      description: 'سفارش',
    });
    assert.equal(attempt.status, 'AUTHORIZED');
    assert.equal(attempt.reference, 'MOCK-order-42');
    assert.match(attempt.message, /آزمایشی/);
  });

  it('refuses malformed authorisation input rather than passing it to a future provider', async () => {
    const gateway = createMockPaymentGateway({ outcome: 'AUTHORIZED' });
    for (const amount of [-1, 1.5, Number.NaN]) {
      const attempt = await gateway.authorize({ orderId: 'o1', amount, description: 'سفارش' });
      assert.equal(attempt.status, 'DECLINED', `amount ${amount} must not authorize`);
    }
    const noOrder = await gateway.authorize({ orderId: '  ', amount: 1, description: 'سفارش' });
    assert.equal(noOrder.status, 'DECLINED');
  });

  it('refuses a callback that carries no reference', async () => {
    const gateway = createMockPaymentGateway({ outcome: 'AUTHORIZED' });
    const attempt = await gateway.verifyCallback({ reference: null });
    assert.equal(attempt.status, 'DECLINED');
    assert.equal(attempt.reference, null);
    assert.match(attempt.message, /شناسهٔ پرداخت/);

    const blank = await gateway.verifyCallback({ reference: '   ' });
    assert.equal(blank.status, 'DECLINED');
  });
});
