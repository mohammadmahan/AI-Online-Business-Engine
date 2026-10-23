import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  createZarinPalGateway,
  tomanToRial,
  zarinpalConfigFromEnv,
  zarinpalEndpoints,
  type ZarinPalHttpRequest,
  type ZarinPalHttpResponse,
} from '@/server/payments/zarinpal';

/**
 * D-172 §6.1 — the ZarinPal adapter, exercised entirely offline.
 *
 * The transport is injected, so nothing here opens a socket: these tests prove
 * the SHAPE of what the adapter sends, what it refuses, and what it will and
 * will not call "paid" — which is the part that protects the order ledger.
 */

const CONFIG = {
  merchantId: 'merchant-test-uuid',
  callbackUrl: 'https://shop.example/api/webhooks/payment',
  sandbox: true,
};

/** Records every call and replays a scripted answer in order. */
function scripted(answers: Array<ZarinPalHttpResponse | Error>) {
  const calls: ZarinPalHttpRequest[] = [];
  let index = 0;
  const transport = async (request: ZarinPalHttpRequest): Promise<ZarinPalHttpResponse> => {
    calls.push(request);
    const next = answers[index];
    index += 1;
    if (next === undefined) {
      return { status: 200, body: { data: { code: 100, authority: 'A-default' } } };
    }
    if (next instanceof Error) {
      throw next;
    }
    return next;
  };
  return { transport, calls };
}

/** A documented ZarinPal success envelope. */
function envelope(data: Record<string, unknown>): ZarinPalHttpResponse {
  return { status: 200, body: { data, errors: [] } };
}

const ORDER = {
  orderId: '11111111-1111-1111-1111-111111111111',
  amount: 2_345_000,
  description: 'سفارش فروشگاه',
};

describe('ZarinPal adapter (§6.1)', () => {
  it('refuses to start a payment when the owner supplied no merchant id — without a network call', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({
      config: { ...CONFIG, merchantId: null },
      transport,
    });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.status, 'UNAVAILABLE');
    assert.equal(attempt.code, 'ZARINPAL_NOT_CONFIGURED');
    assert.equal(attempt.reference, null);
    assert.equal(attempt.redirectUrl, undefined);
    assert.equal(calls.length, 0, 'an unconfigured gateway must not contact anyone');
  });

  it('refuses when the callback URL is missing, for the same reason', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({
      config: { ...CONFIG, callbackUrl: null },
      transport,
    });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.code, 'ZARINPAL_NOT_CONFIGURED');
    assert.equal(calls.length, 0);
  });

  it('requests a sandbox payment and returns the authority plus a redirect URL', async () => {
    const { transport, calls } = scripted([envelope({ code: 100, authority: 'A000000000000000000000000000001' })]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.status, 'UNAVAILABLE', 'a payment REQUEST is not a payment');
    assert.equal(attempt.code, 'ZARINPAL_REDIRECT_REQUIRED');
    assert.equal(attempt.reference, null, 'no provider reference exists before verification');
    assert.equal(attempt.authority, 'A000000000000000000000000000001');
    assert.equal(
      attempt.redirectUrl,
      `https://sandbox.zarinpal.com/pg/StartPay/A000000000000000000000000000001`,
    );
    assert.match(attempt.message, /در انتظار پرداخت/, 'the order is stated as still unpaid');

    assert.equal(calls.length, 1);
    const sent = calls[0];
    assert.ok(sent);
    assert.equal(sent.url, 'https://sandbox.zarinpal.com/pg/v4/payment/request.json');
    assert.equal(sent.body.merchant_id, CONFIG.merchantId);
    assert.equal(sent.body.amount, 23_450_000, 'Toman is converted to Rial');
    assert.equal(sent.body.currency, 'IRR');
    assert.equal(sent.body.callback_url, CONFIG.callbackUrl);
    assert.equal(sent.body.description, ORDER.description);
  });

  it('converts Toman to Rial by ten, in one place', () => {
    assert.equal(tomanToRial(1), 10);
    assert.equal(tomanToRial(2_345_000), 23_450_000);
  });

  it('uses the production hosts only when the sandbox flag is explicitly off', () => {
    assert.match(zarinpalEndpoints(true).request, /sandbox\.zarinpal\.com/);
    const production = zarinpalEndpoints(false);
    assert.match(production.request, /^https:\/\/payment\.zarinpal\.com\//);
    assert.match(production.verify, /^https:\/\/payment\.zarinpal\.com\//);
    assert.match(production.startPay, /^https:\/\/payment\.zarinpal\.com\/pg\/StartPay\/$/);

    const gateway = createZarinPalGateway({
      config: { ...CONFIG, sandbox: false },
      transport: scripted([]).transport,
    });
    assert.equal(gateway.id, 'zarinpal');
    assert.equal(createZarinPalGateway({ config: CONFIG, transport: scripted([]).transport }).id, 'zarinpal-sandbox');
  });

  it('refuses malformed authorisation input before it reaches the gateway', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    for (const amount of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      const attempt = await gateway.authorize({ ...ORDER, amount });
      assert.equal(attempt.status, 'DECLINED', `amount ${amount} must not be sent`);
      assert.equal(attempt.code, 'ZARINPAL_INVALID_AMOUNT');
    }

    const blankOrder = await gateway.authorize({ ...ORDER, orderId: '   ' });
    assert.equal(blankOrder.code, 'ZARINPAL_INVALID_ORDER');
    assert.equal(calls.length, 0);
  });

  it('maps a provider refusal to a decline and never echoes the merchant id', async () => {
    const { transport } = scripted([envelope({ code: -9, message: 'validation error' })]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.status, 'DECLINED');
    assert.equal(attempt.code, 'ZARINPAL_REQUEST_REFUSED');
    assert.match(attempt.message, /-9/, 'the provider code is kept for support');
    assert.ok(!attempt.message.includes(CONFIG.merchantId), 'no credential material in a customer message');
    assert.equal(attempt.redirectUrl, undefined);
  });

  it('treats a transport failure as unavailable rather than throwing into the order path', async () => {
    const gateway = createZarinPalGateway({
      config: CONFIG,
      transport: scripted([new Error('ECONNREFUSED')]).transport,
    });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.status, 'UNAVAILABLE');
    assert.equal(attempt.code, 'ZARINPAL_TRANSPORT_ERROR');
    assert.equal(attempt.reference, null);
  });

  it('refuses an unreadable response instead of inferring success', async () => {
    const gateway = createZarinPalGateway({
      config: CONFIG,
      transport: scripted([{ status: 200, body: 'not json' }]).transport,
    });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.status, 'UNAVAILABLE');
    assert.equal(attempt.code, 'ZARINPAL_MALFORMED_RESPONSE');
  });

  it('verifies a callback with the amount it authorised, and reports the provider reference', async () => {
    const { transport, calls } = scripted([
      envelope({ code: 100, authority: 'A-1' }),
      envelope({ code: 100, ref_id: 123_456 }),
    ]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    const started = await gateway.authorize(ORDER);
    assert.equal(started.authority, 'A-1');
    const verified = await gateway.verifyCallback({ reference: 'A-1' });

    assert.equal(verified.status, 'AUTHORIZED');
    assert.equal(verified.code, 'ZARINPAL_VERIFIED');
    assert.equal(verified.reference, '123456');

    assert.equal(calls.length, 2);
    const verifyCall = calls[1];
    assert.ok(verifyCall);
    assert.equal(verifyCall.url, 'https://sandbox.zarinpal.com/pg/v4/payment/verify.json');
    assert.equal(verifyCall.body.authority, 'A-1');
    assert.equal(verifyCall.body.amount, 23_450_000, 'verify must use the authorised amount');
  });

  it('treats "already verified" (101) as success, not as a failure to retry', async () => {
    const { transport } = scripted([
      envelope({ code: 100, authority: 'A-2' }),
      envelope({ code: 101, ref_id: 777 }),
    ]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    await gateway.authorize(ORDER);
    const verified = await gateway.verifyCallback({ reference: 'A-2' });

    assert.equal(verified.status, 'AUTHORIZED');
    assert.equal(verified.code, 'ZARINPAL_ALREADY_VERIFIED');
    assert.equal(verified.reference, '777');
  });

  it('is idempotent: a replayed callback returns the same verdict without a second call', async () => {
    const { transport, calls } = scripted([
      envelope({ code: 100, authority: 'A-3' }),
      envelope({ code: 100, ref_id: 42 }),
    ]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    await gateway.authorize(ORDER);
    const first = await gateway.verifyCallback({ reference: 'A-3' });
    const second = await gateway.verifyCallback({ reference: 'A-3' });

    assert.equal(calls.length, 2, 'authorise + exactly one verify');
    assert.equal(first, second, 'the same verdict object is returned, not a new verification');
    assert.equal(second.reference, '42');
  });

  it('refuses an authority it never issued, without contacting the gateway', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    const attempt = await gateway.verifyCallback({ reference: 'A-forged' });

    assert.equal(attempt.status, 'DECLINED');
    assert.equal(attempt.code, 'ZARINPAL_UNKNOWN_AUTHORITY');
    assert.equal(calls.length, 0, 'no amount is known, so no verification may be attempted');
  });

  it('refuses a blank or missing authority', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    for (const reference of [null, '', '   ']) {
      const attempt = await gateway.verifyCallback({ reference });
      assert.equal(attempt.status, 'DECLINED');
      assert.equal(attempt.code, 'ZARINPAL_INVALID_AUTHORITY');
    }
    assert.equal(calls.length, 0);
  });

  it('does not cache a decline, so a genuine retry can still verify', async () => {
    const { transport, calls } = scripted([
      envelope({ code: 100, authority: 'A-4' }),
      envelope({ code: -51, message: 'failed' }),
      envelope({ code: 100, ref_id: 9 }),
    ]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport });

    await gateway.authorize(ORDER);
    const declined = await gateway.verifyCallback({ reference: 'A-4' });
    assert.equal(declined.status, 'DECLINED');
    assert.equal(declined.code, 'ZARINPAL_VERIFY_REFUSED');

    const retried = await gateway.verifyCallback({ reference: 'A-4' });
    assert.equal(retried.status, 'AUTHORIZED');
    assert.equal(retried.reference, '9');
    assert.equal(calls.length, 3, 'the retry really did call the gateway again');
  });

  it('bounds how many authorities it remembers', async () => {
    const { transport } = scripted([
      envelope({ code: 100, authority: 'A-old' }),
      envelope({ code: 100, authority: 'A-new' }),
      envelope({ code: 100, ref_id: 5 }),
    ]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport, maxTrackedAuthorities: 1 });

    await gateway.authorize(ORDER);
    await gateway.authorize({ ...ORDER, orderId: 'second-order' });

    const evicted = await gateway.verifyCallback({ reference: 'A-old' });
    assert.equal(evicted.code, 'ZARINPAL_UNKNOWN_AUTHORITY');

    const remembered = await gateway.verifyCallback({ reference: 'A-new' });
    assert.equal(remembered.status, 'AUTHORIZED');
  });

  it('reads configuration from the environment, defaulting to sandbox and refusing empty values', () => {
    const empty = zarinpalConfigFromEnv({});
    assert.equal(empty.merchantId, null);
    assert.equal(empty.callbackUrl, null);
    assert.equal(empty.sandbox, true, 'sandbox is the safe default');

    const configured = zarinpalConfigFromEnv({
      ZARINPAL_MERCHANT_ID: '  merchant-uuid  ',
      ZARINPAL_CALLBACK_URL: 'https://shop.example/api/webhooks/payment',
      ZARINPAL_SANDBOX: 'false',
    });
    assert.equal(configured.merchantId, 'merchant-uuid');
    assert.equal(configured.callbackUrl, 'https://shop.example/api/webhooks/payment');
    assert.equal(configured.sandbox, false);

    const blank = zarinpalConfigFromEnv({ ZARINPAL_MERCHANT_ID: '   ' });
    assert.equal(blank.merchantId, null, 'whitespace is not a credential');
  });
});
