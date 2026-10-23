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
import type { PaymentAuthorizationStore } from '@/server/payments/authority-store';

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

interface StoredAuthorization {
  orderId: string;
  provider: string;
  authority: string;
  amount: number;
}

interface StoreDouble extends PaymentAuthorizationStore {
  /** When true, `save` throws — the "database is down" branch. */
  failSave: boolean;
  /** When true, `find` throws — the "cannot read the SSOT" branch. */
  failFind: boolean;
}

/**
 * The store double, standing in for the `payment_*` columns on
 * `commerce.orders`.
 *
 * It is a Map, NOT the adapter's memory: a test that hands the same double to a
 * SECOND adapter is proving what the old LRU cache could not do — a fresh
 * process verifying a callback it never issued. `failSave`/`failFind` let a test
 * drive the store-error path without a database.
 */
function memoryStore(seed: StoredAuthorization[] = []) {
  const rows = new Map<string, StoredAuthorization>(seed.map((row) => [row.orderId, row]));
  const store: StoreDouble = {
    failSave: false,
    failFind: false,
    async save(record) {
      if (store.failSave) {
        throw new Error('store unavailable');
      }
      rows.set(record.orderId, { ...record });
    },
    async find(provider, authority) {
      if (store.failFind) {
        throw new Error('store unavailable');
      }
      for (const row of rows.values()) {
        if (row.provider === provider && row.authority === authority) {
          return { ...row };
        }
      }
      return null;
    },
  };
  return { store, rows };
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
      store: memoryStore().store,
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
      store: memoryStore().store,
    });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.code, 'ZARINPAL_NOT_CONFIGURED');
    assert.equal(calls.length, 0);
  });

  it('requests a sandbox payment and returns the authority plus a redirect URL', async () => {
    const { transport, calls } = scripted([envelope({ code: 100, authority: 'A000000000000000000000000000001' })]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

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
      store: memoryStore().store,
    });
    assert.equal(gateway.id, 'zarinpal');
    assert.equal(
      createZarinPalGateway({
        config: CONFIG,
        transport: scripted([]).transport,
        store: memoryStore().store,
      }).id,
      'zarinpal-sandbox',
    );
  });

  it('refuses malformed authorisation input before it reaches the gateway', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

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
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

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
      store: memoryStore().store,
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
      store: memoryStore().store,
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
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

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
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

    await gateway.authorize(ORDER);
    const verified = await gateway.verifyCallback({ reference: 'A-2' });

    assert.equal(verified.status, 'AUTHORIZED');
    assert.equal(verified.code, 'ZARINPAL_ALREADY_VERIFIED');
    assert.equal(verified.reference, '777');
  });

  it('re-asks the provider on a replay instead of keeping a verdict in memory', async () => {
    const { transport, calls } = scripted([
      envelope({ code: 100, authority: 'A-3' }),
      envelope({ code: 100, ref_id: 42 }),
      envelope({ code: 101, ref_id: 42 }),
    ]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

    await gateway.authorize(ORDER);
    const first = await gateway.verifyCallback({ reference: 'A-3' });
    const second = await gateway.verifyCallback({ reference: 'A-3' });

    assert.equal(first.code, 'ZARINPAL_VERIFIED');
    assert.equal(
      second.code,
      'ZARINPAL_ALREADY_VERIFIED',
      'the provider is the replay oracle, not this process',
    );
    assert.equal(second.status, 'AUTHORIZED');
    assert.equal(second.reference, '42');
    assert.equal(calls.length, 3, 'authorise + two verifies: no verdict is cached in the adapter');
  });

  it('refuses an authority it never issued, without contacting the gateway', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

    const attempt = await gateway.verifyCallback({ reference: 'A-forged' });

    assert.equal(attempt.status, 'DECLINED');
    assert.equal(attempt.code, 'ZARINPAL_UNKNOWN_AUTHORITY');
    assert.equal(calls.length, 0, 'no amount is known, so no verification may be attempted');
  });

  it('refuses a blank or missing authority', async () => {
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

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
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store: memoryStore().store });

    await gateway.authorize(ORDER);
    const declined = await gateway.verifyCallback({ reference: 'A-4' });
    assert.equal(declined.status, 'DECLINED');
    assert.equal(declined.code, 'ZARINPAL_VERIFY_REFUSED');

    const retried = await gateway.verifyCallback({ reference: 'A-4' });
    assert.equal(retried.status, 'AUTHORIZED');
    assert.equal(retried.reference, '9');
    assert.equal(calls.length, 3, 'the retry really did call the gateway again');
  });

  it('persists the authority against its order before redirecting — never into its own memory', async () => {
    const { transport } = scripted([envelope({ code: 100, authority: 'A-5' })]);
    const { store, rows } = memoryStore();
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store });

    const attempt = await gateway.authorize(ORDER);
    assert.equal(attempt.code, 'ZARINPAL_REDIRECT_REQUIRED');

    const persisted = rows.get(ORDER.orderId);
    assert.deepEqual(
      persisted,
      {
        orderId: ORDER.orderId,
        provider: 'zarinpal',
        authority: 'A-5',
        amount: ORDER.amount,
      },
      'Toman, the amount requested — not Rial, not the order total by another route',
    );
  });

  it('verifies a callback in an instance that never issued the authority', async () => {
    // ONE store, TWO adapters: the second one is a different process (or a
    // different replica) that only has the database. The old LRU cache could not
    // answer this callback at all.
    const { store } = memoryStore();
    const issuer = createZarinPalGateway({
      config: CONFIG,
      transport: scripted([envelope({ code: 100, authority: 'A-6' })]).transport,
      store,
    });
    await issuer.authorize(ORDER);

    const { transport, calls } = scripted([envelope({ code: 100, ref_id: 5_001 })]);
    const verifier = createZarinPalGateway({ config: CONFIG, transport, store });

    const verified = await verifier.verifyCallback({ reference: 'A-6' });

    assert.equal(verified.status, 'AUTHORIZED');
    assert.equal(verified.reference, '5001');
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.body.amount, 23_450_000, 'the persisted Toman amount, converted once');
    assert.equal(calls[0]?.body.authority, 'A-6');
  });

  it('refuses to redirect when the authorisation could not be persisted', async () => {
    const { transport, calls } = scripted([envelope({ code: 100, authority: 'A-7' })]);
    const { store } = memoryStore();
    store.failSave = true;
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store });

    const attempt = await gateway.authorize(ORDER);

    assert.equal(attempt.status, 'UNAVAILABLE', 'nothing was charged, so this is a retryable outage');
    assert.equal(attempt.code, 'ZARINPAL_STORE_ERROR');
    assert.equal(attempt.redirectUrl, undefined, 'the customer must not pay for an unrecorded authority');
    assert.equal(attempt.authority, undefined);
    assert.equal(calls.length, 1);
  });

  it('distinguishes "cannot read the store" (retryable) from "no such authority" (refused)', async () => {
    const { store } = memoryStore([
      { orderId: ORDER.orderId, provider: 'zarinpal', authority: 'A-8', amount: ORDER.amount },
    ]);
    store.failFind = true;
    const outOfOrder = createZarinPalGateway({
      config: CONFIG,
      transport: scripted([]).transport,
      store,
    });

    const unavailable = await outOfOrder.verifyCallback({ reference: 'A-8' });
    assert.equal(unavailable.status, 'UNAVAILABLE');
    assert.equal(unavailable.code, 'ZARINPAL_STORE_ERROR');

    store.failFind = false;
    const readable = createZarinPalGateway({
      config: CONFIG,
      transport: scripted([]).transport,
      store,
    });
    const unknown = await readable.verifyCallback({ reference: 'A-never-issued' });
    assert.equal(unknown.status, 'DECLINED');
    assert.equal(unknown.code, 'ZARINPAL_UNKNOWN_AUTHORITY');
  });

  it('refuses a persisted amount that is not a positive integer, without calling the provider', async () => {
    const { store } = memoryStore([
      { orderId: ORDER.orderId, provider: 'zarinpal', authority: 'A-9', amount: 0 },
    ]);
    const { transport, calls } = scripted([]);
    const gateway = createZarinPalGateway({ config: CONFIG, transport, store });

    const attempt = await gateway.verifyCallback({ reference: 'A-9' });

    assert.equal(attempt.status, 'DECLINED');
    assert.equal(attempt.code, 'ZARINPAL_UNKNOWN_AUTHORITY');
    assert.equal(calls.length, 0, 'a zero amount would be a fabricated verification request');
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
