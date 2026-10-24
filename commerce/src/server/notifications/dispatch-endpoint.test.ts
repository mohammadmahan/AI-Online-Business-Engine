import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { ORDER_CONFIRMED_KIND, SMS_CHANNEL } from '@/lib/notification-rules';
import { POST as dispatchRoute } from '@/app/api/internal/notifications/dispatch/route';
import {
  DISPATCH_TOKEN_ENV,
  handleNotificationDispatchRequest,
} from '@/server/notifications/dispatch-endpoint';
import { MockSmsChannel, createSmsChannelFromEnv } from '@/server/notifications/sms';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';

/**
 * D-172 §6.2 — the operator entry point, `POST /api/internal/notifications/dispatch`.
 *
 * Two properties matter more than the happy path, and both are asserted here:
 *
 *  - FAIL CLOSED. With no token configured the endpoint answers 503 and claims
 *    nothing; with a wrong token it answers 401 and claims nothing; with live SMS
 *    requested but no credential it answers 503 and claims nothing. In every one
 *    of those cases the queue row is still `PENDING`, i.e. deliverable later —
 *    never silently "delivered" into a log and never stuck `SENDING`.
 *  - NO LEAK. Neither the token nor the recipient appears in a response body.
 *
 * The route module is a shim over `handleNotificationDispatchRequest`, so the
 * shim's own surface is asserted too (exactly one exported handler, and no `GET`:
 * a delivery run must not be triggerable by a link).
 */

const TOKEN = 'dispatch-token-for-tests-0123456789';

const ORDER_ID = 'order-dispatch-endpoint';

/** A paid order with one queued confirmation, seeded without a provider. */
async function paidOrder(): Promise<CommerceRepository> {
  const repository = createMemoryRepository({
    orders: [
      {
        id: ORDER_ID,
        customerName: 'زهرا محمدی',
        customerPhone: '09123456789',
        postalCode: '1999999999',
        status: 'PENDING',
        totalAmount: 1_450_000,
        discountAmount: 0,
        shippingAmount: 0,
        trackingCode: null,
        shippingAddress: 'تهران، خیابان ولیعصر، پلاک ۱۲',
        paymentRefId: null,
        createdAt: new Date('2026-06-01T00:00:00.000Z'),
        items: [
          {
            sku: 'dispatch-S',
            productTitle: 'مانتو کتان',
            size: 'S',
            colorName: 'مشکی',
            quantity: 1,
            unitPrice: 1_450_000,
          },
        ],
      },
    ],
  });

  const moved = await transitionOrder(repository, ORDER_ID, 'PAID', MERCHANT_TRANSITION, [
    { kind: ORDER_CONFIRMED_KIND, channel: SMS_CHANNEL },
  ]);
  assert.deepEqual(moved, { ok: true });
  return repository;
}

function bearer(token: string): Request {
  return new Request('https://commerce.test/api/internal/notifications/dispatch', {
    method: 'POST',
    headers: { authorization: `Bearer ${token}` },
  });
}

describe('§6.2 dispatch endpoint authentication', () => {
  it('answers 503 and claims NOTHING when no token is configured', async () => {
    const repository = await paidOrder();
    const response = await handleNotificationDispatchRequest(bearer(TOKEN), {
      token: null,
      getRepository: () => repository,
    });

    assert.equal(response.status, 503);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const body = await response.json();
    assert.equal(body.code, 'DISPATCH_NOT_CONFIGURED');
    assert.equal((await repository.listOrderNotifications(ORDER_ID))[0]?.status, 'PENDING');
  });

  it('answers 401 for a missing or wrong bearer token', async () => {
    const repository = await paidOrder();

    for (const request of [
      new Request('https://commerce.test/x', { method: 'POST' }),
      bearer('wrong-token'),
      new Request('https://commerce.test/x', {
        method: 'POST',
        headers: { authorization: `Basic ${TOKEN}` },
      }),
    ]) {
      const response = await handleNotificationDispatchRequest(request, {
        token: TOKEN,
        getRepository: () => repository,
      });
      assert.equal(response.status, 401);
      const body = await response.json();
      assert.equal(body.code, 'UNAUTHORIZED');
      assert.ok(!JSON.stringify(body).includes(TOKEN));
    }

    assert.equal((await repository.listOrderNotifications(ORDER_ID))[0]?.status, 'PENDING');
  });

  it('accepts a case-insensitive bearer scheme and drains one batch', async () => {
    const repository = await paidOrder();
    const channel = new MockSmsChannel();
    const request = new Request('https://commerce.test/x', {
      method: 'POST',
      headers: { authorization: `bEaReR ${TOKEN}` },
    });

    const response = await handleNotificationDispatchRequest(request, {
      token: TOKEN,
      getRepository: () => repository,
      channel: { ok: true, channel, mode: 'MOCK' },
    });

    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const body = await response.json();
    assert.deepEqual(body, {
      ok: true,
      mode: 'MOCK',
      report: { claimed: 1, sent: 1, retried: 0, failed: 0, skipped: 0 },
    });
    assert.equal(channel.calls.length, 1);

    // The response is a report, not a message: no number, no body, no token.
    const text = JSON.stringify(body);
    assert.ok(!text.includes('09123456789'));
    assert.ok(!text.includes(TOKEN));
    assert.equal((await repository.listOrderNotifications(ORDER_ID))[0]?.status, 'SENT');
  });

  it('answers 503 when the database is not configured, without touching the queue', async () => {
    const response = await handleNotificationDispatchRequest(bearer(TOKEN), {
      token: TOKEN,
      getRepository: () => null,
    });

    assert.equal(response.status, 503);
    const body = await response.json();
    assert.equal(body.code, 'DB_NOT_CONFIGURED');
  });

  it('answers 503 and claims NOTHING when live SMS is requested without a credential', async () => {
    const repository = await paidOrder();
    const resolution = createSmsChannelFromEnv({ SMS_LIVE_ENABLED: 'true' });

    const response = await handleNotificationDispatchRequest(bearer(TOKEN), {
      token: TOKEN,
      getRepository: () => repository,
      channel: resolution,
    });

    assert.equal(response.status, 503);
    const body = await response.json();
    assert.equal(body.code, 'SMS_LIVE_MODE_MISSING_CREDENTIAL');
    assert.equal((await repository.listOrderNotifications(ORDER_ID))[0]?.status, 'PENDING');
  });

  it('reads the token from the environment when the dependency is not injected', async () => {
    const repository = await paidOrder();
    const previous = process.env[DISPATCH_TOKEN_ENV];
    process.env[DISPATCH_TOKEN_ENV] = TOKEN;
    try {
      const response = await handleNotificationDispatchRequest(bearer(TOKEN), {
        getRepository: () => repository,
        channel: { ok: true, channel: new MockSmsChannel(), mode: 'MOCK' },
      });
      assert.equal(response.status, 200);

      const wrong = await handleNotificationDispatchRequest(bearer('nope'), {
        getRepository: () => repository,
        channel: { ok: true, channel: new MockSmsChannel(), mode: 'MOCK' },
      });
      assert.equal(wrong.status, 401);
    } finally {
      if (previous === undefined) {
        delete process.env[DISPATCH_TOKEN_ENV];
      } else {
        process.env[DISPATCH_TOKEN_ENV] = previous;
      }
    }
  });
});

describe('§6.2 dispatch route module', () => {
  it('exposes exactly one handler and no read method', async () => {
    const routeModule = await import('@/app/api/internal/notifications/dispatch/route');
    assert.equal(typeof routeModule.POST, 'function');
    assert.equal('GET' in routeModule, false);
  });

  it('answers 503 through the shim when the token is not configured', async () => {
    const previous = process.env[DISPATCH_TOKEN_ENV];
    delete process.env[DISPATCH_TOKEN_ENV];
    try {
      const response = await dispatchRoute(bearer(TOKEN));
      assert.equal(response.status, 503);
      const body = await response.json();
      assert.equal(body.code, 'DISPATCH_NOT_CONFIGURED');
    } finally {
      if (previous !== undefined) {
        process.env[DISPATCH_TOKEN_ENV] = previous;
      }
    }
  });
});

