import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { GET as zarinPalCallbackRoute } from '@/app/api/payments/zarinpal/callback/route';
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import { createRepositoryPaymentAuthorizationStore } from '@/server/payments/authority-store';
import { mockPaymentGateway } from '@/server/payments/gateway';
import {
  ZARINPAL_PROVIDER,
  createZarinPalGateway,
  tomanToRial,
  type ZarinPalTransport,
} from '@/server/payments/zarinpal';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';
import { handleZarinPalCallback } from '@/server/services/payment-callback';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §6.1 — ZarinPal's BROWSER RETURN (`GET /api/payments/zarinpal/callback`).
 *
 * This route is the only way an order becomes `PAID` in the storefront, and it
 * accepts a request that carries no session and no signature — only
 * `?Authority=&Status=`. The tests therefore concentrate on what must NOT happen:
 * a `NOK` return must not verify and must not write, an authority this
 * deployment never issued must not verify, and an authority recorded for a
 * DIFFERENT provider must not be honoured. The happy path is asserted through the
 * same `applyPaymentCallback` pipeline the signed webhook uses, so a callback
 * cannot reach a second write path.
 *
 * Everything is offline: the repository is the in-memory double, the gateway is
 * the real adapter over an injected transport, and the transport counts its calls
 * so "did not verify" is an assertion rather than a hope.
 */

const AUTHORITY = 'A000000000000000000000000000abcd1';
const REF_ID = 'ZP-REF-1001';
const AMOUNT = 2_450_000;

/** Unique per harness without a clock: two fixtures must never share a slug. */
let fixtureSequence = 0;

function productPayload(slug: string): ProductCreatePayload {
  return {
    categoryId: 'cat-1',
    title: 'مانتو کتان بازگشت درگاه',
    slug,
    basePrice: AMOUNT,
    discountPrice: null,
    descriptionRaw: 'مانتو کتان برای آزمون بازگشت مرورگر از درگاه.',
    descriptionHtml: '<p>مانتو کتان</p>',
    fabricType: 'کتان',
    season: 'تابستان',
    status: 'PUBLISHED',
    variants: [
      { sku: `${slug}-S`, colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 5 },
    ],
    images: [],
  };
}

interface VerifyCall {
  url: string;
  body: Record<string, unknown>;
}

interface Harness {
  repository: CommerceRepository;
  orderId: string;
  gateway: ReturnType<typeof createZarinPalGateway>;
  /** Every request the adapter sent to the provider, in order. */
  calls: VerifyCall[];
  order: () => Promise<{ status: string; paymentRefId: string | null }>;
  trail: () => Promise<Array<{ fromStatus: string | null; toStatus: string; source: string }>>;
  callback: (params: Record<string, string>) => Request;
}

/**
 * A REAL order from the production checkout path, then an authorisation recorded
 * the way `authorize()` records it (order row, provider, authority, amount).
 * `recordProvider` lets a test store the authority under another provider, which
 * is the mismatch the route must refuse.
 */
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

/** The order a fixture works on, placed through the real storefront path. */
async function placeFixtureOrder(repository: CommerceRepository): Promise<string> {
  fixtureSequence += 1;
  const created = await createProduct(repository, productPayload(`zarinpal-cb-${fixtureSequence}`));
  assert.ok(created.ok, `the fixture product must be written: ${JSON.stringify(created)}`);

  const placed = await placeCheckoutOrder(
    repository,
    mockPaymentGateway,
    checkoutDraft(created.variantIds[0] as string),
  );
  assert.ok(placed.ok, `the fixture order must be written: ${JSON.stringify(placed)}`);

  return placed.orderId;
}

async function harness(options?: {
  verifyCode?: number;
  recordProvider?: string;
  record?: boolean;
}): Promise<Harness> {
  const repository = createMemoryRepository();
  const orderId = await placeFixtureOrder(repository);
  const calls: VerifyCall[] = [];
  const transport: ZarinPalTransport = async (request) => {
    calls.push({ url: request.url, body: request.body });
    return {
      status: 200,
      body: { data: { code: options?.verifyCode ?? 100, ref_id: REF_ID, message: 'OK' } },
    };
  };

  const gateway = createZarinPalGateway({
    config: {
      merchantId: 'merchant-test-only',
      callbackUrl: 'https://shop.example.test/api/payments/zarinpal/callback',
      sandbox: true,
    },
    transport,
    store: createRepositoryPaymentAuthorizationStore(() => repository),
  });

  if (options?.record !== false) {
    const written = await repository.recordPaymentAuthorization({
      orderId,
      provider: options?.recordProvider ?? ZARINPAL_PROVIDER,
      authority: AUTHORITY,
      amount: AMOUNT,
    });
    assert.equal(written, true, 'the fixture authorisation must be recorded');
  }

  return {
    repository,
    orderId,
    gateway,
    calls,
    order: async () => {
      const detail = await repository.getOrderDetail(orderId);
      assert.ok(detail, 'the order must exist');
      return { status: detail.status, paymentRefId: detail.paymentRefId };
    },
    trail: async () =>
      (await repository.listOrderStatusHistory(orderId)).map((row) => ({
        fromStatus: row.fromStatus,
        toStatus: row.toStatus,
        source: row.source,
      })),
    callback: (params) => {
      const query = new URLSearchParams(params).toString();
      return new Request(`http://localhost/api/payments/zarinpal/callback?${query}`, {
        method: 'GET',
      });
    },
  };
}

describe('GET /api/payments/zarinpal/callback — the browser return', () => {
  it('Status=OK: verifies with the provider, moves the order to PAID and records the reference', async () => {
    const h = await harness();
    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: h.gateway,
    });

    assert.equal(response.status, 200);
    const body = (await response.json()) as Record<string, unknown>;
    assert.deepEqual(
      { ok: body.ok, orderId: body.orderId, status: body.status, duplicate: body.duplicate },
      { ok: true, orderId: h.orderId, status: 'PAID', duplicate: false },
    );

    // The provider was asked exactly the question only it can answer, with the
    // amount PERSISTED at request time (Toman -> Rial, once).
    assert.equal(h.calls.length, 1, 'the return must verify exactly once');
    assert.match(h.calls[0]?.url ?? '', /\/pg\/v4\/payment\/verify\.json$/);
    assert.equal(h.calls[0]?.body.authority, AUTHORITY);
    assert.equal(h.calls[0]?.body.amount, tomanToRial(AMOUNT));
    assert.equal(h.calls[0]?.body.merchant_id, 'merchant-test-only');

    assert.deepEqual(await h.order(), { status: 'PAID', paymentRefId: REF_ID });
    assert.deepEqual(await h.trail(), [
      { fromStatus: null, toStatus: 'PENDING', source: 'STOREFRONT' },
      { fromStatus: 'PENDING', toStatus: 'PAID', source: 'PAYMENT_CALLBACK' },
    ]);

    // The audit row is where the correlation ids survive, even if the order's
    // own reference write were lost.
    const history = await h.repository.listOrderStatusHistory(h.orderId);
    assert.deepEqual(history[1]?.metadata, {
      provider: ZARINPAL_PROVIDER,
      authority: AUTHORITY,
      verification: 'ZARINPAL_VERIFIED',
      reference: REF_ID,
    });
  });

  it('is idempotent: a refresh of the same return writes no second transition', async () => {
    const h = await harness();
    const deps = { getRepository: () => h.repository, gateway: h.gateway };

    const first = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), deps);
    const second = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), deps);

    assert.equal(first.status, 200);
    assert.equal(second.status, 200);
    const refreshed = (await second.json()) as Record<string, unknown>;
    assert.equal(refreshed.ok, true);
    assert.equal(refreshed.duplicate, true);

    assert.deepEqual(await h.order(), { status: 'PAID', paymentRefId: REF_ID });
    assert.equal((await h.trail()).length, 2, 'a replay must not write a second audit row');
  });

  it('Status=NOK: does NOT verify and does NOT mutate the order', async () => {
    const h = await harness();
    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'NOK' }), {
      getRepository: () => h.repository,
      gateway: h.gateway,
    });

    assert.equal(response.status, 200);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.ok, false);
    assert.equal(body.code, 'PAYMENT_NOT_COMPLETED');

    assert.equal(h.calls.length, 0, 'a cancelled payment must not be sent to verify');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
    assert.equal((await h.trail()).length, 1);
  });

  it('a missing or unrecognised Status is treated as NOT paid: no verify, no write', async () => {
    const cases: Array<Record<string, string>> = [
      { Authority: AUTHORITY },
      { Authority: AUTHORITY, Status: 'MAYBE' },
    ];
    for (const params of cases) {
      const h = await harness();
      const response = await handleZarinPalCallback(h.callback(params), {
        getRepository: () => h.repository,
        gateway: h.gateway,
      });

      const body = (await response.json()) as Record<string, unknown>;
      assert.equal(body.code, 'PAYMENT_NOT_COMPLETED', JSON.stringify(params));
      assert.equal(h.calls.length, 0, JSON.stringify(params));
      assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
    }
  });

  it('an authority this deployment never issued is refused without verifying', async () => {
    const h = await harness({ record: false });
    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: h.gateway,
    });

    assert.equal(response.status, 404);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.ok, false);
    assert.equal(body.code, 'UNKNOWN_AUTHORITY');
    assert.equal(h.calls.length, 0, 'an unknown authority must never reach the provider');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
    assert.equal((await h.trail()).length, 1);
  });

  it('an authority recorded for ANOTHER provider is refused (provider mismatch)', async () => {
    const h = await harness({ recordProvider: 'zibal' });

    // The record exists — under a provider this route does not speak for.
    assert.ok(await h.repository.findPaymentAuthorization('zibal', AUTHORITY));

    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: h.gateway,
    });

    assert.equal(response.status, 404);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'UNKNOWN_AUTHORITY');
    assert.equal(h.calls.length, 0, 'a foreign authority must not be verified here');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
  });

  it('a return without Authority is refused before anything is read or written', async () => {
    const h = await harness();
    const response = await handleZarinPalCallback(h.callback({ Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: h.gateway,
    });

    assert.equal(response.status, 400);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'AUTHORITY_MISSING');
    assert.equal(h.calls.length, 0);
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
  });

  it('a declined verification leaves the order PENDING (the money did not arrive)', async () => {
    const h = await harness({ verifyCode: -50 });
    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: h.gateway,
    });

    assert.equal(response.status, 402);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.ok, false);
    assert.equal(body.code, 'VERIFICATION_FAILED');
    assert.equal(h.calls.length, 1, 'the provider WAS asked — that is how it was declined');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
    assert.equal((await h.trail()).length, 1);
  });

  it('with no canonical connection the return refuses and writes nothing', async () => {
    const h = await harness();
    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => null,
      gateway: h.gateway,
    });

    assert.equal(response.status, 503);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'DB_NOT_CONFIGURED');
    assert.equal(h.calls.length, 0);
  });

  it('a store read that FAILS is a retryable 503 — never a refusal, never a verify', async () => {
    const h = await harness();
    const leaking = new Error('connect failed for postgres://commerce:secret@db:5432/app');
    const broken: CommerceRepository = {
      ...h.repository,
      findPaymentAuthorization: async () => {
        throw leaking;
      },
    };

    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => broken,
      gateway: h.gateway,
    });

    assert.equal(response.status, 503);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'STORE_UNAVAILABLE');
    // The driver's message can echo a connection string (D-114/D-124).
    assert.doesNotMatch(JSON.stringify(body), /postgres:\/\/|secret/);
    assert.equal(h.calls.length, 0, 'an unreadable store must not become a provider call');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
    assert.equal((await h.trail()).length, 1);
  });

  it('an unreachable provider is a retryable 503: the money may still arrive, so nothing is written', async () => {
    const h = await harness();
    const unreachable = createZarinPalGateway({
      config: {
        merchantId: 'merchant-test-only',
        callbackUrl: 'https://shop.example.test/api/payments/zarinpal/callback',
        sandbox: true,
      },
      transport: async () => {
        throw new Error('ETIMEDOUT');
      },
      store: createRepositoryPaymentAuthorizationStore(() => h.repository),
    });

    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: unreachable,
    });

    assert.equal(response.status, 503);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'VERIFY_UNAVAILABLE');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
    assert.equal((await h.trail()).length, 1);
  });

  it('an adapter that THROWS is still a 503, never an unhandled 500', async () => {
    const h = await harness();
    const exploding = {
      ...mockPaymentGateway,
      verifyCallback: async () => {
        throw new Error('adapter bug');
      },
    };

    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: exploding,
    });

    assert.equal(response.status, 503);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'VERIFY_UNAVAILABLE');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
  });

  it('a duplicate return arriving CONCURRENTLY moves the order exactly once and never reports a conflict', async () => {
    const h = await harness();
    const deps = { getRepository: () => h.repository, gateway: h.gateway };
    const request = () => h.callback({ Authority: AUTHORITY, Status: 'OK' });

    // Three deliveries in flight at once: the guard in `applyPaymentCallback` is
    // a read, so all three can pass it before any write lands. The losers must
    // converge on "already done" (200, duplicate) rather than 409 — a conflict
    // would make the browser retry a payment that already succeeded.
    const responses = await Promise.all(
      [request(), request(), request()].map((delivery) => handleZarinPalCallback(delivery, deps)),
    );
    const bodies = (await Promise.all(responses.map((response) => response.json()))) as Array<
      Record<string, unknown>
    >;

    assert.deepEqual(
      responses.map((response) => response.status),
      [200, 200, 200],
      'a converged duplicate is not a conflict',
    );
    assert.equal(
      bodies.filter((body) => body.duplicate === false).length,
      1,
      'exactly one delivery performed the move',
    );
    assert.equal(
      (await h.trail()).filter((row) => row.toStatus === 'PAID').length,
      1,
      'one audit row for one transition',
    );
    assert.deepEqual(await h.order(), { status: 'PAID', paymentRefId: REF_ID });
  });

  it('refuses a late PAID on a SHIPPED order (409) and writes neither status nor reference', async () => {
    const h = await harness();
    for (const next of ['PAID', 'PROCESSING', 'SHIPPED'] as const) {
      const moved = await transitionOrder(h.repository, h.orderId, next, MERCHANT_TRANSITION);
      assert.ok(moved.ok, `the fixture must reach ${next}`);
    }
    const before = await h.trail();

    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => h.repository,
      gateway: h.gateway,
    });

    assert.equal(response.status, 409);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'ILLEGAL_TRANSITION');
    assert.deepEqual(await h.trail(), before, 'a refused return writes no audit row');
    assert.deepEqual(await h.order(), { status: 'SHIPPED', paymentRefId: null });
  });

  it('an authority whose order has disappeared is a 404, and the return writes nothing', async () => {
    const h = await harness();
    const orphaned: CommerceRepository = {
      ...h.repository,
      findPaymentAuthorization: async () => ({
        orderId: 'order-that-no-longer-exists',
        provider: ZARINPAL_PROVIDER,
        authority: AUTHORITY,
        amount: AMOUNT,
      }),
    };

    const response = await handleZarinPalCallback(h.callback({ Authority: AUTHORITY, Status: 'OK' }), {
      getRepository: () => orphaned,
      gateway: h.gateway,
    });

    assert.equal(response.status, 404);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'ORDER_NOT_FOUND');
    // The provider WAS asked — the record named an amount, which is the only
    // question the adapter can answer — but no order exists to move.
    assert.equal(h.calls.length, 1);
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
  });

  it('accepts a lower-cased Status and a padded Authority, and lets no cache keep a payment return', async () => {
    const h = await harness();
    const deps = { getRepository: () => h.repository, gateway: h.gateway };

    const response = await handleZarinPalCallback(
      h.callback({ Authority: ` ${AUTHORITY} `, Status: 'ok' }),
      deps,
    );
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.status, 'PAID');

    const refused = await handleZarinPalCallback(h.callback({ Status: 'OK' }), deps);
    assert.equal(refused.status, 400);
    assert.equal(refused.headers.get('cache-control'), 'no-store', 'a refusal is never cached either');
  });

  it('the checkout request charges nothing; the verified return alone completes THAT order', async () => {
    const repository = createMemoryRepository();
    fixtureSequence += 1;
    const created = await createProduct(repository, productPayload(`zarinpal-chain-${fixtureSequence}`));
    assert.ok(created.ok, `the fixture product must be written: ${JSON.stringify(created)}`);

    const calls: VerifyCall[] = [];
    const transport: ZarinPalTransport = async (request) => {
      calls.push({ url: request.url, body: request.body });
      return request.url.endsWith('/request.json')
        ? { status: 200, body: { data: { code: 100, authority: AUTHORITY } } }
        : { status: 200, body: { data: { code: 100, ref_id: REF_ID } } };
    };
    const gateway = createZarinPalGateway({
      config: {
        merchantId: 'merchant-test-only',
        callbackUrl: 'https://shop.example.test/api/payments/zarinpal/callback',
        sandbox: true,
      },
      transport,
      store: createRepositoryPaymentAuthorizationStore(() => repository),
    });

    const placed = await placeCheckoutOrder(
      repository,
      gateway,
      checkoutDraft(created.variantIds[0] as string),
    );
    assert.ok(placed.ok, `the order must be written: ${JSON.stringify(placed)}`);
    const orderId = placed.orderId;

    // Request ≠ paid (AC-8): an authority and a redirect, no reference, no
    // status change — the order row is exactly where the customer left it.
    assert.equal(placed.status, 'PENDING');
    assert.deepEqual(
      {
        status: placed.payment.status,
        code: placed.payment.code,
        authority: placed.payment.authority,
        redirectUrl: placed.payment.redirectUrl,
        reference: placed.payment.reference,
      },
      {
        status: 'UNAVAILABLE',
        code: 'ZARINPAL_REDIRECT_REQUIRED',
        authority: AUTHORITY,
        redirectUrl: `https://sandbox.zarinpal.com/pg/StartPay/${AUTHORITY}`,
        reference: null,
      },
    );
    const beforePayment = await repository.getOrderDetail(orderId);
    assert.deepEqual(
      { status: beforePayment?.status, paymentRefId: beforePayment?.paymentRefId },
      { status: 'PENDING', paymentRefId: null },
    );
    assert.equal(
      calls[0]?.body.amount,
      tomanToRial(placed.totals.total),
      'the provider is asked in Rial, converted once',
    );

    // What the return resolves is the row written at request time — read from the
    // repository, not remembered by the adapter.
    assert.deepEqual(await repository.findPaymentAuthorization(ZARINPAL_PROVIDER, AUTHORITY), {
      orderId,
      provider: ZARINPAL_PROVIDER,
      authority: AUTHORITY,
      amount: placed.totals.total,
    });

    const response = await handleZarinPalCallback(
      new Request(`http://localhost/api/payments/zarinpal/callback?Authority=${AUTHORITY}&Status=OK`),
      { getRepository: () => repository, gateway },
    );
    assert.equal(response.status, 200);
    const body = (await response.json()) as Record<string, unknown>;
    assert.deepEqual(
      { ok: body.ok, orderId: body.orderId, status: body.status, duplicate: body.duplicate },
      { ok: true, orderId, status: 'PAID', duplicate: false },
    );

    const paid = await repository.getOrderDetail(orderId);
    assert.deepEqual(
      { status: paid?.status, paymentRefId: paid?.paymentRefId },
      { status: 'PAID', paymentRefId: REF_ID },
    );
    assert.equal(calls.length, 2, 'one request, one verify — no extra provider call');
  });

  it('the route file is a shim: GET delegates to the pipeline with no dependency of its own', async () => {
    // The real route handler, with NO injected dependencies and no database: a
    // return that carries no Authority is refused before either is touched, so
    // this proves the wiring without pretending a connection exists.
    const response = await zarinPalCallbackRoute(
      new Request('http://localhost/api/payments/zarinpal/callback?Status=OK'),
    );

    assert.equal(response.status, 400);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'AUTHORITY_MISSING');
    assert.equal(response.headers.get('cache-control'), 'no-store');
  });
});

