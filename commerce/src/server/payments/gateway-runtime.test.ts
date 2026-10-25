import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  getPaymentGateway,
  isProductionConfig,
  MOCK_CALLBACK_URL_TEMPLATE,
  MOCK_PAYMENT_MODE,
  PAYMENT_MODE_ENV,
} from '@/server/payments/gateway-runtime';

/**
 * D-172 §6.1 — the runtime selector, offline.
 *
 * The property that matters is the DEFAULT: with no variable, or with a value
 * nobody recognises, the ZarinPal adapter is constructed and an unconfigured
 * environment refuses. The mock is reachable only by asking for it by name.
 */

test('default (no env) selects the ZarinPal adapter', () => {
  const gateway = getPaymentGateway({});
  assert.equal(gateway.id, 'zarinpal-sandbox');
});

test('an unrecognised mode falls through to ZarinPal, never the mock', () => {
  for (const value of ['mockk', 'demo', 'MOCK ', 'mock-ish', 'zarinpal']) {
    const gateway = getPaymentGateway({ [PAYMENT_MODE_ENV]: value });
    if (value.trim().toLowerCase() === MOCK_PAYMENT_MODE) continue;
    assert.notEqual(gateway.id, 'mock', `value ${JSON.stringify(value)} reached the mock`);
  }
});

test('PAYMENT_MODE=mock selects the mock adapter, case-insensitively', async () => {
  for (const value of ['mock', 'MOCK', '  Mock  ']) {
    const gateway = getPaymentGateway({ [PAYMENT_MODE_ENV]: value });
    assert.equal(gateway.id, 'mock');
    const attempt = await gateway.authorize({
      orderId: 'ORD-MOCK-1',
      amount: 250_000,
      description: 'سفارش ORD-MOCK-1',
    });
    assert.equal(attempt.status, 'AUTHORIZED');
    assert.equal(attempt.code, 'MOCK_AUTHORIZED');
    // Prefixed so it can never pass for a provider reference.
    assert.equal(attempt.reference, 'MOCK-ORD-MOCK-1');
    // The demo return is addressed, not granted: the route re-checks the mode.
    assert.equal(
      attempt.redirectUrl,
      MOCK_CALLBACK_URL_TEMPLATE.replace('{reference}', 'MOCK-ORD-MOCK-1'),
    );
  }
});

test('ZarinPal mode never returns a demo redirect', async () => {
  const gateway = getPaymentGateway({});
  const attempt = await gateway.authorize({
    orderId: 'ORD-NO-REDIRECT',
    amount: 1_000,
    description: 'x',
  });
  assert.equal(attempt.status, 'UNAVAILABLE');
  assert.equal(attempt.redirectUrl, undefined);
});

test('a production build refuses the demo adapter, whatever PAYMENT_MODE says', () => {
  const gateway = getPaymentGateway({ PAYMENT_MODE: 'mock', NODE_ENV: 'production' });
  assert.equal(gateway.id, 'zarinpal-sandbox');
});

test('production detection is exact and case-insensitive', () => {
  assert.equal(isProductionConfig({ NODE_ENV: 'production' }), true);
  assert.equal(isProductionConfig({ NODE_ENV: '  PRODUCTION  ' }), true);
  assert.equal(isProductionConfig({ NODE_ENV: 'development' }), false);
  assert.equal(isProductionConfig({}), false);
});

test('mock mode does not need a database or a credential', () => {
  // `getRepository()` is null without DATABASE_URL; constructing must not throw.
  assert.doesNotThrow(() => getPaymentGateway({ [PAYMENT_MODE_ENV]: 'mock' }));
});

test('mock verify refuses an empty reference and approves a mock one', async () => {
  const gateway = getPaymentGateway({ [PAYMENT_MODE_ENV]: 'mock' });
  const empty = await gateway.verifyCallback({ reference: null });
  assert.equal(empty.status, 'DECLINED');
  assert.equal(empty.code, 'MOCK_DECLINED');

  const approved = await gateway.verifyCallback({ reference: 'MOCK-ORD-1' });
  assert.equal(approved.status, 'AUTHORIZED');
  assert.equal(approved.reference, 'MOCK-MOCK-ORD-1');
});

test('mock mode rejects a malformed amount before anything else', async () => {
  const gateway = getPaymentGateway({ [PAYMENT_MODE_ENV]: 'mock' });
  const attempt = await gateway.authorize({
    orderId: 'ORD-1',
    amount: 12.5,
    description: 'x',
  });
  assert.equal(attempt.status, 'DECLINED');
  assert.equal(attempt.code, 'MOCK_DECLINED');
});

test('ZarinPal mode without credentials refuses without charging', async () => {
  const gateway = getPaymentGateway({});
  const attempt = await gateway.authorize({
    orderId: 'ORD-UNCONFIGURED',
    amount: 250_000,
    description: 'سفارش ORD-UNCONFIGURED',
  });
  assert.equal(attempt.status, 'UNAVAILABLE');
  assert.equal(attempt.reference, null);
});
