import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { GET as mockCallbackRoute } from '@/app/api/payments/mock/callback/route';
import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import {
  createMockPaymentGateway,
  mockPaymentGateway,
  type PaymentGateway,
} from '@/server/payments/gateway';
import type { CommerceRepository } from '@/server/repository';
import { createMemoryRepository } from '@/server/repository-memory';
import { placeCheckoutOrder } from '@/server/services/checkout';
import {
  handleMockCallback,
  MOCK_REFERENCE_PREFIX,
  mockModeEnabled,
  orderIdFromMockReference,
  type MockCallbackDeps,
} from '@/server/services/mock-payment-callback';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §6.1 (demo) — the OFFLINE mock return.
 *
 * The tests concentrate on the mode guard, because that is the whole safety
 * argument: outside `PAYMENT_MODE=mock` this route must answer 404, verify
 * nothing and write nothing. Inside it, the order becomes `PAID` through the
 * same `applyPaymentCallback` pipeline the real returns use — so a replay is a
 * duplicate, not a second transition.
 */

const AMOUNT = 1_800_000;
let fixtureSequence = 0;

function productPayload(slug: string): ProductCreatePayload {
  return {
    categoryId: 'cat-1',
    title: 'شومیز کتان بازگشت آزمایشی',
    slug,
    basePrice: AMOUNT,
    discountPrice: null,
    descriptionRaw: 'شومیز کتان برای آزمون بازگشت آزمایشی درگاه.',
    descriptionHtml: '<p>شومیز کتان</p>',
    fabricType: 'کتان',
    season: 'تابستان',
    status: 'PUBLISHED',
    variants: [
      { sku: `${slug}-M`, colorName: 'مشکی', colorHex: '#111111', size: 'M', stockQuantity: 4 },
    ],
    images: [],
  };
}

function checkoutDraft(variantId: string): CheckoutDraft {
  return {
    customer: {
      fullName: 'مینا رضایی',
      phoneNumber: '09121234567',
      address: 'تهران، خیابان انقلاب، پلاک ۵',
      postalCode: '1999999999',
    },
    couponCode: null,
    shippingMethodId: DEFAULT_SHIPPING_METHOD_ID,
    lines: [{ variantId, quantity: 1 }],
  };
}

async function placePendingOrder(repository: CommerceRepository): Promise<string> {
  fixtureSequence += 1;
  const created = await createProduct(repository, productPayload(`mock-cb-${fixtureSequence}`));
  assert.ok(created.ok, `fixture product must be written: ${JSON.stringify(created)}`);
  const placed = await placeCheckoutOrder(
    repository,
    mockPaymentGateway, // UNAVAILABLE: the order is written but unpaid
    checkoutDraft(created.variantIds[0] as string),
  );
  assert.ok(placed.ok, `fixture order must be written: ${JSON.stringify(placed)}`);
  assert.equal(placed.payment.status, 'UNAVAILABLE');
  return placed.orderId;
}

interface Call {
  reference: string | null;
}

function countingGateway(outcome?: 'AUTHORIZED' | 'UNAVAILABLE'): {
  gateway: PaymentGateway;
  calls: Call[];
} {
  const base =
    outcome === 'UNAVAILABLE'
      ? createMockPaymentGateway({ outcome: 'UNAVAILABLE' })
      : createMockPaymentGateway({ outcome: 'AUTHORIZED' });
  const calls: Call[] = [];
  return {
    calls,
    gateway: {
      id: base.id,
      authorize: (request) => base.authorize(request),
      verifyCallback: async (payload) => {
        calls.push({ reference: payload.reference });
        return base.verifyCallback(payload);
      },
    },
  };
}

interface Harness {
  repository: CommerceRepository;
  orderId: string;
  calls: Call[];
  deps: MockCallbackDeps;
  request: (reference?: string | null) => Request;
  order: () => Promise<{ status: string; paymentRefId: string | null }>;
  trail: () => Promise<Array<{ toStatus: string; source: string }>>;
}

async function harness(
  options: { mode?: string | null; gateway?: PaymentGateway } = {},
): Promise<Harness> {
  const repository = createMemoryRepository();
  const orderId = await placePendingOrder(repository);
  const counted = options.gateway === undefined ? countingGateway() : null;

  const env: Record<string, string | undefined> = {};
  const mode = options.mode === undefined ? 'mock' : options.mode;
  if (mode !== null) {
    env.PAYMENT_MODE = mode;
  }

  return {
    repository,
    orderId,
    calls: counted?.calls ?? [],
    deps: {
      env,
      getRepository: () => repository,
      gateway: options.gateway ?? counted?.gateway,
    },
    request: (reference) => {
      const query =
        reference === undefined
          ? ''
          : reference === null
            ? '?'
            : `?reference=${encodeURIComponent(reference)}`;
      return new Request(`http://localhost/api/payments/mock/callback${query}`, {
        method: 'GET',
      });
    },
    order: async () => {
      const detail = await repository.getOrderDetail(orderId);
      assert.ok(detail, 'the order must exist');
      return { status: detail.status, paymentRefId: detail.paymentRefId };
    },
    trail: async () =>
      (await repository.listOrderStatusHistory(orderId)).map((row) => ({
        toStatus: row.toStatus,
        source: row.source,
      })),
  };
}

describe('mock return — the mode guard', () => {
  it('PAYMENT_MODE unset: 404, nothing verified, nothing written', async () => {
    const h = await harness({ mode: null });
    const response = await handleMockCallback(
      h.request(`${MOCK_REFERENCE_PREFIX}${h.orderId}`),
      h.deps,
    );

    assert.equal(response.status, 404);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.code, 'MOCK_MODE_DISABLED');
    assert.equal(h.calls.length, 0, 'a disabled surface must verify nothing');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
  });

  it('a near-miss mode is disabled', async () => {
    for (const mode of ['MOCKK', 'demo', 'zarinpal', ' mock-ish ']) {
      const h = await harness({ mode });
      const response = await handleMockCallback(
        h.request(`${MOCK_REFERENCE_PREFIX}${h.orderId}`),
        h.deps,
      );
      assert.equal(response.status, 404, `mode ${JSON.stringify(mode)} must be disabled`);
      assert.equal(h.calls.length, 0);
    }
  });

  it('mockModeEnabled is exact and case-insensitive', () => {
    assert.equal(mockModeEnabled({}), false);
    assert.equal(mockModeEnabled({ PAYMENT_MODE: 'mock' }), true);
    assert.equal(mockModeEnabled({ PAYMENT_MODE: '  MOCK  ' }), true);
    assert.equal(mockModeEnabled({ PAYMENT_MODE: 'mockk' }), false);
  });

  it('a production build refuses the demo route even with PAYMENT_MODE=mock', async () => {
    const h = await harness();
    const response = await handleMockCallback(
      h.request(`${MOCK_REFERENCE_PREFIX}${h.orderId}`),
      { ...h.deps, env: { PAYMENT_MODE: 'mock', NODE_ENV: 'production' } },
    );

    assert.equal(response.status, 404);
    assert.equal(
      ((await response.json()) as Record<string, unknown>).code,
      'MOCK_MODE_DISABLED',
    );
    assert.equal(h.calls.length, 0, 'production must verify nothing');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
  });

  it('mockModeEnabled is false in production, regardless of the mode value', () => {
    assert.equal(mockModeEnabled({ NODE_ENV: 'production', PAYMENT_MODE: 'mock' }), false);
    assert.equal(mockModeEnabled({ NODE_ENV: 'production' }), false);
    assert.equal(mockModeEnabled({ NODE_ENV: 'development', PAYMENT_MODE: 'mock' }), true);
  });
});

describe('mock return — the reference shape', () => {
  it('missing reference is refused before any verify', async () => {
    const h = await harness();
    const response = await handleMockCallback(h.request(), h.deps);
    assert.equal(response.status, 400);
    assert.equal(((await response.json()) as Record<string, unknown>).code, 'REFERENCE_MISSING');
    assert.equal(h.calls.length, 0);
  });

  it('a non-MOCK reference is refused', async () => {
    for (const reference of ['ORD-1', 'A000000000000000000000000000abcd1', 'MOCK-', 'MOCK-   ']) {
      const h = await harness();
      const response = await handleMockCallback(h.request(reference), h.deps);
      assert.equal(response.status, 400, `reference ${JSON.stringify(reference)}`);
      assert.equal(
        ((await response.json()) as Record<string, unknown>).code,
        'REFERENCE_INVALID',
      );
      assert.equal(h.calls.length, 0);
    }
  });

  it('orderIdFromMockReference strips exactly one prefix', () => {
    assert.equal(orderIdFromMockReference('MOCK-ORD-9'), 'ORD-9');
    assert.equal(orderIdFromMockReference('MOCK-MOCK-ORD-9'), 'MOCK-ORD-9');
    assert.equal(orderIdFromMockReference('ORD-9'), null);
    assert.equal(orderIdFromMockReference('MOCK-'), null);
  });
});

describe('mock return — the PAID transition', () => {
  it('confirms the order, records the MOCK- reference and audits PAYMENT_CALLBACK', async () => {
    const h = await harness();
    const reference = `${MOCK_REFERENCE_PREFIX}${h.orderId}`;
    const response = await handleMockCallback(h.request(reference), h.deps);

    assert.equal(response.status, 200);
    const body = (await response.json()) as Record<string, unknown>;
    assert.deepEqual(
      { ok: body.ok, orderId: body.orderId, status: body.status, duplicate: body.duplicate },
      { ok: true, orderId: h.orderId, status: 'PAID', duplicate: false },
    );

    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0]?.reference, reference);
    assert.deepEqual(await h.order(), {
      status: 'PAID',
      paymentRefId: reference,
    });
    const trail = await h.trail();
    assert.deepEqual(trail[trail.length - 1], {
      toStatus: 'PAID',
      source: 'PAYMENT_CALLBACK',
    });

    // §6.2 — the confirmation is QUEUED once by the transition, not sent.
    const queued = await h.repository.listOrderNotifications(h.orderId);
    assert.equal(queued.length, 1, 'exactly one confirmation job must be queued');
  });

  it('a replay is a duplicate and writes no second transition', async () => {
    const h = await harness();
    const reference = `${MOCK_REFERENCE_PREFIX}${h.orderId}`;

    assert.equal((await handleMockCallback(h.request(reference), h.deps)).status, 200);
    const lengthAfterFirst = (await h.trail()).length;

    const replay = await handleMockCallback(h.request(reference), h.deps);
    assert.equal(replay.status, 200);
    const body = (await replay.json()) as Record<string, unknown>;
    assert.equal(body.duplicate, true);
    assert.equal((await h.trail()).length, lengthAfterFirst);
    assert.deepEqual(await h.order(), { status: 'PAID', paymentRefId: reference });
    // No second SMS job: the replay never re-enters the transition.
    assert.equal((await h.repository.listOrderNotifications(h.orderId)).length, 1);
  });

  it('an unknown order is refused by the shared pipeline', async () => {
    const h = await harness();
    const response = await handleMockCallback(
      h.request(`${MOCK_REFERENCE_PREFIX}ORD-DOES-NOT-EXIST`),
      h.deps,
    );
    assert.equal(response.status, 404);
    assert.equal(((await response.json()) as Record<string, unknown>).code, 'ORDER_NOT_FOUND');
  });
});

describe('mock return — fail-closed edges', () => {
  it('an unavailable gateway answers 503 and the order stays PENDING', async () => {
    const unavailable = countingGateway('UNAVAILABLE');
    const h = await harness({ gateway: unavailable.gateway });
    const response = await handleMockCallback(
      h.request(`${MOCK_REFERENCE_PREFIX}${h.orderId}`),
      h.deps,
    );
    assert.equal(response.status, 503);
    assert.equal(((await response.json()) as Record<string, unknown>).code, 'VERIFY_UNAVAILABLE');
    assert.deepEqual(await h.order(), { status: 'PENDING', paymentRefId: null });
  });

  it('no repository is a 503, not a write', async () => {
    const h = await harness();
    const response = await handleMockCallback(h.request(`${MOCK_REFERENCE_PREFIX}${h.orderId}`), {
      ...h.deps,
      getRepository: () => null,
    });
    assert.equal(response.status, 503);
    assert.equal(((await response.json()) as Record<string, unknown>).code, 'DB_NOT_CONFIGURED');
    assert.equal(h.calls.length, 0);
  });
});

describe('GET /api/payments/mock/callback — the shim', () => {
  it('is inert without the mode, even for a valid-looking reference', async () => {
    const previous = process.env.PAYMENT_MODE;
    delete process.env.PAYMENT_MODE;
    try {
      const response = await mockCallbackRoute(
        new Request('http://localhost/api/payments/mock/callback?reference=MOCK-ORD-1'),
      );
      assert.equal(response.status, 404);
      assert.equal(
        ((await response.json()) as Record<string, unknown>).code,
        'MOCK_MODE_DISABLED',
      );
    } finally {
      if (previous === undefined) delete process.env.PAYMENT_MODE;
      else process.env.PAYMENT_MODE = previous;
    }
  });

  it('reads the mode at REQUEST time, not at import time', async () => {
    const previous = process.env.PAYMENT_MODE;
    const previousDb = process.env.DATABASE_URL;
    delete process.env.DATABASE_URL;
    try {
      const disabled = await mockCallbackRoute(
        new Request('http://localhost/api/payments/mock/callback?reference=MOCK-ORD-1'),
      );
      assert.equal(disabled.status, 404);

      process.env.PAYMENT_MODE = 'mock';
      const enabled = await mockCallbackRoute(
        new Request('http://localhost/api/payments/mock/callback?reference=MOCK-ORD-1'),
      );
      // Guard passed; with no DATABASE_URL the repository gate is the next refusal.
      assert.equal(enabled.status, 503);
      assert.equal(
        ((await enabled.json()) as Record<string, unknown>).code,
        'DB_NOT_CONFIGURED',
      );
    } finally {
      if (previous === undefined) delete process.env.PAYMENT_MODE;
      else process.env.PAYMENT_MODE = previous;
      if (previousDb !== undefined) process.env.DATABASE_URL = previousDb;
    }
  });
});
