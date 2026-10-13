import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import { mockPaymentGateway } from '@/server/payments/gateway';
import {
  WEBHOOK_SECRET_ENV,
  WEBHOOK_SIGNATURE_HEADER,
  signWebhookBody,
  verifyWebhookSignature,
  webhookSecret,
} from '@/server/payments/webhook-signature';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import {
  MAX_WEBHOOK_BODY_BYTES,
  handlePaymentWebhook,
  parsePaymentWebhookPayload,
} from '@/server/services/payment-webhook';
import { createProduct } from '@/server/services/products';
import { MERCHANT_TRANSITION, getOrder, transitionOrder } from '@/server/services/orders';

/**
 * D-172 Phase 4 transition / §6.1 — the async callback seam, offline.
 *
 * The endpoint is the ONLY request in this track that arrives without a session,
 * so these tests concentrate on the thing that makes it safe: every refusal, in
 * the order the pipeline applies them, and the fact that a refusal leaves the
 * order, its stock and its audit trail byte-for-byte untouched. The authenticated
 * happy path is asserted through the same memory repository the rest of the
 * offline suite uses, so a callback drives the SAME transition service the
 * merchant panel does rather than a parallel write path of its own.
 */

const SECRET = 'unit-webhook-secret-value';
const REFERENCE = 'GW-REF-0001';
const BASE_PRICE = 2_450_000;
const DEFAULT_SHIPPING = DEFAULT_SHIPPING_METHOD_ID;

const PRODUCT_PAYLOAD: ProductCreatePayload = {
  categoryId: 'cat-1',
  title: 'مانتو کتان بازگشت',
  slug: 'manto-katan-callback',
  basePrice: BASE_PRICE,
  discountPrice: null,
  descriptionRaw: 'مانتو کتان برای آزمون بازگشت پرداخت.',
  descriptionHtml: '<p>مانتو کتان</p>',
  fabricType: 'کتان',
  season: 'تابستان',
  status: 'PUBLISHED',
  variants: [
    { sku: 'CB-BLK-S', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 3 },
  ],
  images: [],
};

interface Harness {
  repository: CommerceRepository;
  orderId: string;
  variantId: string;
  stockOf: () => Promise<number>;
  trail: () => Promise<Array<{ fromStatus: string | null; toStatus: string; source: string }>>;
}

/**
 * A REAL checkout, not a seeded order: the callback then runs against an audit
 * trail that begins with the storefront's own opening row, which is what the
 * production sequence looks like.
 */
async function harness(): Promise<Harness> {
  const repository = createMemoryRepository();
  const created = await createProduct(repository, PRODUCT_PAYLOAD);
  assert.ok(created.ok, `the fixture product must be written: ${JSON.stringify(created)}`);
  const variantId = created.variantIds[0] as string;

  const draft: CheckoutDraft = {
    customer: {
      fullName: 'زهرا محمدی',
      phoneNumber: '09123456789',
      address: 'تهران، خیابان ولیعصر، پلاک ۱۲',
      postalCode: '1999999999',
    },
    couponCode: null,
    shippingMethodId: DEFAULT_SHIPPING,
    lines: [{ variantId, quantity: 2 }],
  };
  const placed = await placeCheckoutOrder(repository, mockPaymentGateway, draft);
  assert.ok(placed.ok, `the fixture order must be written: ${JSON.stringify(placed)}`);

  return {
    repository,
    orderId: placed.orderId,
    variantId,
    stockOf: async () => {
      const row = (await repository.listInventory()).find((entry) => entry.variantId === variantId);
      assert.ok(row, 'the variant must exist in the inventory read');
      return row.stockQuantity;
    },
    trail: async () =>
      (await repository.listOrderStatusHistory(placed.orderId)).map((row) => ({
        fromStatus: row.fromStatus,
        toStatus: row.toStatus,
        source: row.source,
      })),
  };
}

const ENDPOINT = 'http://localhost/api/webhooks/payment';

function callback(payload: unknown, secret: string | null = SECRET): Request {
  const rawBody = JSON.stringify(payload);
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (secret !== null) {
    headers[WEBHOOK_SIGNATURE_HEADER] = signWebhookBody(rawBody, secret);
  }
  return new Request(ENDPOINT, { method: 'POST', body: rawBody, headers });
}

function paidPayload(orderId: string, overrides: Record<string, unknown> = {}) {
  return { eventId: 'evt-1', orderId, status: 'PAID', reference: REFERENCE, ...overrides };
}

async function bodyOf(response: Response): Promise<Record<string, unknown>> {
  return (await response.json()) as Record<string, unknown>;
}

afterEach(() => {
  delete process.env[WEBHOOK_SECRET_ENV];
});

describe('payment webhook — the signature gate (Phase 4 transition §6.1)', () => {
  it('refuses EVERYTHING when no secret is configured, before looking at the request', () => {
    const signed = signWebhookBody('{"a":1}', SECRET);

    // Unset, empty and whitespace-only are all "not configured" — there is no
    // development mode in which an unsigned callback would be accepted.
    for (const secret of [null, '', '   ']) {
      const verdict = verifyWebhookSignature({
        rawBody: '{"a":1}',
        header: signed,
        secret,
      });
      assert.equal(verdict.ok, false);
      assert.ok(!verdict.ok && verdict.code === 'WEBHOOK_NOT_CONFIGURED');
    }
  });

  it('distinguishes a missing, a malformed and a mismatched signature', () => {
    const cases: Array<{ header: string | null; code: string }> = [
      { header: null, code: 'SIGNATURE_MISSING' },
      { header: '   ', code: 'SIGNATURE_MISSING' },
      { header: 'abc123', code: 'SIGNATURE_MALFORMED' },
      { header: 'sha256=not-a-digest', code: 'SIGNATURE_MALFORMED' },
      { header: 'f'.repeat(64), code: 'SIGNATURE_MISMATCH' },
    ];
    for (const entry of cases) {
      const verdict = verifyWebhookSignature({ rawBody: '{"a":1}', header: entry.header, secret: SECRET });
      assert.equal(verdict.ok, false, `header ${String(entry.header)} must be refused`);
      assert.ok(!verdict.ok && verdict.code === entry.code);
    }
  });

  it('accepts the correct digest, with or without the algorithm prefix, and only over the RAW body', () => {
    const rawBody = '{"orderId":"x","status":"PAID"}';
    const digest = signWebhookBody(rawBody, SECRET);

    assert.deepEqual(verifyWebhookSignature({ rawBody, header: digest, secret: SECRET }), {
      ok: true,
      algorithm: 'sha256',
    });
    assert.equal(
      verifyWebhookSignature({ rawBody, header: `sha256=${digest}`, secret: SECRET }).ok,
      true,
    );

    // Same JSON, different bytes: a parser-equivalent body must NOT verify,
    // which is what proves the signature covers the raw request rather than a
    // re-serialisation of it.
    const respaced = '{ "orderId" : "x", "status" : "PAID" }';
    assert.deepEqual(JSON.parse(respaced), JSON.parse(rawBody));
    const respacedVerdict = verifyWebhookSignature({
      rawBody: respaced,
      header: digest,
      secret: SECRET,
    });
    assert.ok(!respacedVerdict.ok && respacedVerdict.code === 'SIGNATURE_MISMATCH');

    // A different secret can never produce the accepted digest.
    assert.equal(signWebhookBody(rawBody, SECRET), digest);
    assert.notEqual(signWebhookBody(rawBody, `${SECRET}-other`), digest);
  });
});

describe('POST /api/webhooks/payment — the fail-closed pipeline', () => {
  it('answers 503 and processes nothing when the seam is not configured', async () => {
    const order = await harness();
    assert.equal(webhookSecret(), null, 'the fixture must not rely on an ambient secret');

    // No dependencies injected: this is the REAL production wiring, where the
    // secret comes from the environment and the repository from `DATABASE_URL`.
    const response = await handlePaymentWebhook(callback(paidPayload(order.orderId)));
    assert.equal(response.status, 503);
    const body = await bodyOf(response);
    assert.equal(body.code, 'WEBHOOK_NOT_CONFIGURED');

    assert.equal((await getOrder(order.repository, order.orderId))?.status, 'PENDING');
    assert.equal(await order.stockOf(), 1, 'the stock the checkout took is untouched');
  });

  it('takes the secret from the environment when none is injected', async () => {
    const order = await harness();
    process.env[WEBHOOK_SECRET_ENV] = SECRET;
    assert.equal(webhookSecret(), SECRET);

    // The secret is ambient now; the repository is injected so the run stays
    // hermetic. `secret: undefined` is exactly what the route handler passes.
    const response = await handlePaymentWebhook(callback(paidPayload(order.orderId)), {
      getRepository: () => order.repository,
    });
    assert.equal(response.status, 200, await response.clone().text());
    assert.equal((await getOrder(order.repository, order.orderId))?.status, 'PAID');
  });

  it('rejects a forged, missing or body-swapped signature with 401 and writes nothing', async () => {
    const order = await harness();
    const before = await order.trail();

    const attempts: Request[] = [
      // Unsigned.
      new Request(ENDPOINT, { method: 'POST', body: JSON.stringify(paidPayload(order.orderId)) }),
      // Signed with the wrong secret.
      callback(paidPayload(order.orderId), 'not-the-secret'),
      // A real signature, but the body was replaced afterwards.
      new Request(ENDPOINT, {
        method: 'POST',
        body: JSON.stringify(paidPayload(order.orderId, { status: 'CANCELLED' })),
        headers: {
          [WEBHOOK_SIGNATURE_HEADER]: signWebhookBody(
            JSON.stringify(paidPayload(order.orderId)),
            SECRET,
          ),
        },
      }),
    ];

    for (const request of attempts) {
      const response = await handlePaymentWebhook(request, {
        secret: SECRET,
        getRepository: () => order.repository,
      });
      assert.equal(response.status, 401, await response.clone().text());
      assert.equal((await bodyOf(response)).ok, false);
    }

    assert.equal((await getOrder(order.repository, order.orderId))?.status, 'PENDING');
    assert.equal((await getOrder(order.repository, order.orderId))?.paymentRefId, null);
    assert.deepEqual(await order.trail(), before, 'only the checkout row exists');
    assert.equal(await order.stockOf(), 1);
  });

  it('refuses a body it cannot read, and a payload it cannot act on', async () => {
    const order = await harness();
    const deps = { secret: SECRET, getRepository: () => order.repository };

    const withBody = (rawBody: string): Request =>
      new Request(ENDPOINT, {
        method: 'POST',
        body: rawBody,
        headers: { [WEBHOOK_SIGNATURE_HEADER]: signWebhookBody(rawBody, SECRET) },
      });

    const malformed = await handlePaymentWebhook(withBody('{"orderId":'), deps);
    assert.equal(malformed.status, 400);
    assert.equal((await bodyOf(malformed)).code, 'INVALID_JSON');

    // An oversized body is refused BEFORE it is parsed — and only after the
    // signature proved the sender is entitled to our attention.
    const huge = JSON.stringify({ orderId: order.orderId, status: 'PAID', filler: 'x'.repeat(MAX_WEBHOOK_BODY_BYTES) });
    const tooLarge = await handlePaymentWebhook(withBody(huge), deps);
    assert.equal(tooLarge.status, 413);
    assert.equal((await bodyOf(tooLarge)).code, 'BODY_TOO_LARGE');

    const invalid: unknown[] = [
      paidPayload(order.orderId, { orderId: '   ' }),
      paidPayload(order.orderId, { status: 'PROCESSING' }),
      paidPayload(order.orderId, { status: 42 }),
      paidPayload(order.orderId, { status: 'SHIPPED' }),
      [paidPayload(order.orderId)],
    ];
    for (const payload of invalid) {
      const response = await handlePaymentWebhook(callback(payload), deps);
      assert.equal(response.status, 400, JSON.stringify(payload));
      assert.equal((await bodyOf(response)).code, 'INVALID_EVENT');
    }

    assert.equal((await getOrder(order.repository, order.orderId))?.status, 'PENDING');
    assert.equal((await order.trail()).length, 1);
  });

  it('answers 503 when no canonical connection exists, and 404 for an unknown order', async () => {
    const order = await harness();

    const unconfigured = await handlePaymentWebhook(callback(paidPayload(order.orderId)), {
      secret: SECRET,
      getRepository: () => null,
    });
    assert.equal(unconfigured.status, 503);
    assert.equal((await bodyOf(unconfigured)).code, 'DB_NOT_CONFIGURED');

    const unknown = await handlePaymentWebhook(
      callback(paidPayload('00000000-0000-0000-0000-000000000000')),
      { secret: SECRET, getRepository: () => order.repository },
    );
    assert.equal(unknown.status, 404);
    assert.equal((await bodyOf(unknown)).code, 'ORDER_NOT_FOUND');
  });

  it('moves the order, records the reference and appends the callback’s audit row', async () => {
    const order = await harness();
    const deps = { secret: SECRET, getRepository: () => order.repository };

    const response = await handlePaymentWebhook(callback(paidPayload(order.orderId)), deps);
    assert.equal(response.status, 200, await response.clone().text());
    assert.deepEqual(await bodyOf(response), {
      ok: true,
      orderId: order.orderId,
      status: 'PAID',
      duplicate: false,
    });

    const stored = await getOrder(order.repository, order.orderId);
    assert.equal(stored?.status, 'PAID');
    assert.equal(stored?.paymentRefId, REFERENCE);

    const trail = await order.trail();
    assert.deepEqual(trail, [
      { fromStatus: null, toStatus: 'PENDING', source: 'STOREFRONT' },
      { fromStatus: 'PENDING', toStatus: 'PAID', source: 'PAYMENT_CALLBACK' },
    ]);

    const rows = await order.repository.listOrderStatusHistory(order.orderId);
    const callbackRow = rows[rows.length - 1];
    assert.deepEqual(
      callbackRow?.metadata,
      { eventId: 'evt-1', reference: REFERENCE },
      'the provider ids live with the transition they describe',
    );
  });

  it('treats a replay as a success that changes nothing, rather than an error a provider would retry', async () => {
    const order = await harness();
    const deps = { secret: SECRET, getRepository: () => order.repository };

    assert.equal((await handlePaymentWebhook(callback(paidPayload(order.orderId)), deps)).status, 200);
    const afterFirst = await order.trail();

    const replay = await handlePaymentWebhook(
      callback(paidPayload(order.orderId, { eventId: 'evt-1-retry' })),
      deps,
    );
    assert.equal(replay.status, 200, 'an error here is what makes a provider retry forever');
    assert.deepEqual(await bodyOf(replay), {
      ok: true,
      orderId: order.orderId,
      status: 'PAID',
      duplicate: true,
    });

    assert.deepEqual(await order.trail(), afterFirst, 'no second audit row');
    assert.equal((await getOrder(order.repository, order.orderId))?.paymentRefId, REFERENCE);
  });

  it('returns the stock on a cancelled callback, exactly once', async () => {
    const order = await harness();
    const deps = { secret: SECRET, getRepository: () => order.repository };

    assert.equal(await order.stockOf(), 1, 'two of the three pieces were taken by the checkout');

    const cancelled = await handlePaymentWebhook(
      callback({ orderId: order.orderId, status: 'CANCELLED' }),
      deps,
    );
    assert.equal(cancelled.status, 200);
    assert.equal((await bodyOf(cancelled)).status, 'CANCELLED');
    assert.equal(await order.stockOf(), 3, 'the reservation came back');

    const replay = await handlePaymentWebhook(
      callback({ orderId: order.orderId, status: 'CANCELLED' }),
      deps,
    );
    assert.equal((await bodyOf(replay)).duplicate, true);
    assert.equal(await order.stockOf(), 3, 'a replayed cancellation returns nothing twice');

    assert.deepEqual(await order.trail(), [
      { fromStatus: null, toStatus: 'PENDING', source: 'STOREFRONT' },
      { fromStatus: 'PENDING', toStatus: 'CANCELLED', source: 'PAYMENT_CALLBACK' },
    ]);
  });

  it('refuses a transition the lifecycle forbids, and a callback cannot drive fulfilment', async () => {
    const order = await harness();
    const deps = { secret: SECRET, getRepository: () => order.repository };

    // The merchant ships the parcel: the order is terminal for this lifecycle.
    assert.equal((await order.repository.updateOrderStatus(order.orderId, 'PAID', MERCHANT_TRANSITION)), true);
    assert.equal(
      (await transitionOrder(order.repository, order.orderId, 'PROCESSING', MERCHANT_TRANSITION)).ok,
      true,
    );
    assert.equal(
      (await transitionOrder(order.repository, order.orderId, 'SHIPPED', MERCHANT_TRANSITION)).ok,
      true,
    );
    const before = await order.trail();

    const late = await handlePaymentWebhook(callback(paidPayload(order.orderId)), deps);
    assert.equal(late.status, 409);
    assert.equal((await bodyOf(late)).code, 'ILLEGAL_TRANSITION');
    assert.deepEqual(await order.trail(), before, 'a refused callback writes nothing');
    assert.equal((await getOrder(order.repository, order.orderId))?.paymentRefId, null);
  });

  it('reports an unexpected repository failure by name and code only, never by its message', async () => {
    const order = await harness();
    const boom = new Error('connection string postgres://user:secret@host/db leaked here');
    boom.name = 'ConnectionError';
    (boom as Error & { code?: string }).code = 'ECONNREFUSED';

    const exploding: CommerceRepository = {
      ...order.repository,
      getOrderDetail: async () => {
        throw boom;
      },
    };

    const response = await handlePaymentWebhook(callback(paidPayload(order.orderId)), {
      secret: SECRET,
      getRepository: () => exploding,
    });
    assert.equal(response.status, 500);
    const body = await bodyOf(response);
    assert.equal(body.code, 'UNEXPECTED');
    assert.ok(!String(body.message).includes('secret'), 'the driver message must not be echoed');
  });
});

describe('payment webhook — payload parsing', () => {
  it('normalises the fields it uses and refuses everything else', () => {
    const ok = parsePaymentWebhookPayload({
      orderId: '  abc  ',
      status: 'paid',
      reference: '  REF  ',
      eventId: ' evt ',
    });
    assert.deepEqual(ok, {
      ok: true,
      payload: { orderId: 'abc', status: 'PAID', reference: 'REF', eventId: 'evt' },
    });

    const noReference = parsePaymentWebhookPayload({ orderId: 'abc', status: 'CANCELLED' });
    assert.deepEqual(noReference, {
      ok: true,
      payload: { orderId: 'abc', status: 'CANCELLED', reference: null },
    });

    for (const value of [null, 'text', 7, [], {}]) {
      assert.equal(parsePaymentWebhookPayload(value).ok, false, JSON.stringify(value));
    }
  });
});
