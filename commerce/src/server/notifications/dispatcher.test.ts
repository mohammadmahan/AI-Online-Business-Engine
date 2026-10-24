import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import {
  MAX_SMS_ATTEMPTS,
  ORDER_CONFIRMED_KIND,
  SMS_CHANNEL,
  orderReference,
} from '@/lib/notification-rules';
import { DEFAULT_SHIPPING_METHOD_ID } from '@/lib/shipping';
import { MockSmsChannel, type SmsChannel, type SmsSendResult } from '@/server/notifications/sms';
import { dispatchNotifications } from '@/server/notifications/dispatcher';
import { mockPaymentGateway } from '@/server/payments/gateway';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { placeCheckoutOrder } from '@/server/services/checkout';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';
import { applyPaymentCallback } from '@/server/services/payment-webhook';
import { createProduct } from '@/server/services/products';

/**
 * D-172 §6.2 — the DISPATCHER.
 *
 * Every branch is asserted with an injected clock and an injected channel, so no
 * test sleeps and none reaches a network:
 *
 *   - a claimed row becomes `SENT` and carries the provider's own id;
 *   - a second run (and a second CONCURRENT run) delivers nothing;
 *   - a transient refusal reschedules with the backoff table and is retried when
 *     its time comes;
 *   - a permanent refusal, a spent budget, a bad recipient and a missing order are
 *     terminal and never call the provider;
 *   - a channel that throws cannot abort the batch.
 *
 * The recipient is resolved from the CUSTOMER at dispatch time — the queue itself
 * stores no phone number — so `channel.calls[0].to` is also an assertion about
 * where that value came from.
 */

let fixtureSequence = 0;

function productPayload(slug: string): ProductCreatePayload {
  return {
    categoryId: 'cat-1',
    title: 'شومیز ابریشمی ارسال پیامک',
    slug,
    basePrice: 1_250_000,
    discountPrice: null,
    descriptionRaw: 'شومیز ابریشمی برای آزمون ارسال پیامک.',
    descriptionHtml: '<p>شومیز ابریشمی</p>',
    fabricType: 'ابریشم',
    season: 'بهار',
    status: 'PUBLISHED',
    variants: [
      {
        sku: `${slug}-M`,
        colorName: 'سفید',
        colorHex: '#ffffff',
        size: 'M',
        stockQuantity: 4,
      },
    ],
    images: [],
  };
}

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

/** A paid order with exactly one queued confirmation, built through the real paths. */
async function paidOrderWithQueue(
  repository: CommerceRepository = createMemoryRepository(),
): Promise<{ repository: CommerceRepository; orderId: string }> {
  fixtureSequence += 1;
  const created = await createProduct(repository, productPayload(`dispatch-${fixtureSequence}`));
  assert.ok(created.ok, `fixture product must be written: ${JSON.stringify(created)}`);

  const placed = await placeCheckoutOrder(
    repository,
    mockPaymentGateway,
    checkoutDraft(created.variantIds[0] as string),
  );
  assert.ok(placed.ok, `fixture order must be written: ${JSON.stringify(placed)}`);

  const paid = await applyPaymentCallback(repository, {
    orderId: placed.orderId,
    status: 'PAID',
    reference: 'ZP-REF-7001',
  });
  assert.equal(paid.ok, true);
  return { repository, orderId: placed.orderId };
}

/** A channel that answers with whatever the test scripts, and counts calls. */
function scriptedChannel(
  results: SmsSendResult[],
  fallback: SmsSendResult = { ok: true, providerMessageId: 'SCRIPTED-1' },
) {
  const calls: Array<{ to: string; body: string }> = [];
  const channel: SmsChannel = {
    id: 'mock',
    mode: 'MOCK',
    async send(message) {
      calls.push({ to: message.to, body: message.body });
      return results.shift() ?? fallback;
    },
  };
  return { calls, channel };
}

const T0 = new Date('2026-10-24T09:00:00.000Z');
const minutes = (count: number) => new Date(T0.getTime() + count * 60_000);


describe('§6.2 dispatch delivers a queued confirmation', () => {
  it('sends once, records the provider id and moves the row to SENT', async () => {
    const { repository, orderId } = await paidOrderWithQueue();
    const channel = new MockSmsChannel();

    const report = await dispatchNotifications(repository, channel, { now: () => T0 });

    assert.deepEqual(report, { claimed: 1, sent: 1, retried: 0, failed: 0, skipped: 0 });
    assert.equal(channel.calls.length, 1);
    assert.equal(channel.calls[0]?.to, '09123456789');
    assert.equal(
      channel.calls[0]?.body,
      `سفارش ${orderReference(orderId)} ثبت شد. از خرید شما سپاسگزاریم.`,
    );

    const [row] = await repository.listOrderNotifications(orderId);
    assert.ok(row);
    assert.equal(row.status, 'SENT');
    assert.equal(row.attempts, 1);
    assert.equal(row.providerMessageId, 'MOCK-SMS-1');
    assert.equal(row.sentAt?.toISOString(), T0.toISOString());
    assert.equal(row.lastError, null);
  });

  it('delivers nothing on a second run (claim only, no re-send)', async () => {
    const { repository } = await paidOrderWithQueue();
    const channel = new MockSmsChannel();

    await dispatchNotifications(repository, channel, { now: () => T0 });
    const second = await dispatchNotifications(repository, channel, { now: () => minutes(5) });

    assert.deepEqual(second, { claimed: 0, sent: 0, retried: 0, failed: 0, skipped: 0 });
    assert.equal(channel.calls.length, 1);
  });

  it('delivers ONE message when two dispatchers run concurrently', async () => {
    const { repository, orderId } = await paidOrderWithQueue();
    const channel = new MockSmsChannel();

    const [left, right] = await Promise.all([
      dispatchNotifications(repository, channel, { now: () => T0 }),
      dispatchNotifications(repository, channel, { now: () => T0 }),
    ]);

    assert.equal(left.claimed + right.claimed, 1);
    assert.equal(left.sent + right.sent, 1);
    assert.equal(channel.calls.length, 1);
    assert.equal((await repository.listOrderNotifications(orderId))[0]?.status, 'SENT');
  });
});

describe('§6.2 transient failures are retried, permanent ones are not', () => {
  it('reschedules a retryable refusal with the backoff table', async () => {
    const { repository, orderId } = await paidOrderWithQueue();
    const { channel, calls } = scriptedChannel([
      { ok: false, code: 'provider_unavailable', retryable: true },
    ]);

    const first = await dispatchNotifications(repository, channel, { now: () => T0 });
    assert.deepEqual(first, { claimed: 1, sent: 0, retried: 1, failed: 0, skipped: 0 });
    assert.equal(calls.length, 1);

    const [afterFailure] = await repository.listOrderNotifications(orderId);
    assert.ok(afterFailure);
    assert.equal(afterFailure.status, 'PENDING');
    assert.equal(afterFailure.attempts, 1);
    assert.equal(afterFailure.lastError, 'provider_unavailable');
    assert.equal(afterFailure.nextAttemptAt.toISOString(), minutes(1).toISOString());

    // Not due yet: a dispatcher run before the backoff must not deliver.
    const early = await dispatchNotifications(repository, channel, {
      now: () => new Date(T0.getTime() + 30_000),
    });
    assert.equal(early.claimed, 0);

    // Due now: the SAME message goes out, and the row is sent exactly once.
    const retry = await dispatchNotifications(repository, channel, {
      now: () => minutes(2),
    });
    assert.deepEqual(retry, { claimed: 1, sent: 1, retried: 0, failed: 0, skipped: 0 });
    assert.equal(calls.length, 2);
    const [sent] = await repository.listOrderNotifications(orderId);
    assert.equal(sent?.status, 'SENT');
    assert.equal(sent?.attempts, 2);
  });

  it('honours a provider-indicated wait over the local backoff', async () => {
    const { repository, orderId } = await paidOrderWithQueue();
    const { channel } = scriptedChannel([
      { ok: false, code: 'rate_limited', retryable: true, retryAfterSeconds: 3_600 },
    ]);

    await dispatchNotifications(repository, channel, { now: () => T0 });
    const [row] = await repository.listOrderNotifications(orderId);
    assert.equal(row?.nextAttemptAt.toISOString(), minutes(60).toISOString());
  });
});

describe('§6.2 the attempt budget ends a stuck message', () => {
  it('gives up after MAX_SMS_ATTEMPTS and never claims the row again', async () => {
    const { repository, orderId } = await paidOrderWithQueue();
    const { channel, calls } = scriptedChannel([], {
      ok: false,
      code: 'provider_unavailable',
      retryable: true,
    });

    const clocks = [T0, minutes(2), minutes(10), minutes(120)];
    const reports = [];
    for (const clock of clocks) {
      reports.push(await dispatchNotifications(repository, channel, { now: () => clock }));
    }

    assert.deepEqual(
      reports.map((report) => `${report.claimed}/${report.retried}/${report.failed}`),
      ['1/1/0', '1/1/0', '1/0/1', '0/0/0'],
    );
    assert.equal(calls.length, MAX_SMS_ATTEMPTS);

    const [row] = await repository.listOrderNotifications(orderId);
    assert.ok(row);
    assert.equal(row.status, 'FAILED');
    assert.equal(row.attempts, MAX_SMS_ATTEMPTS);
    assert.equal(row.sentAt, null);
  });

  it('records a permanent provider refusal immediately', async () => {
    const { repository, orderId } = await paidOrderWithQueue();
    const { channel, calls } = scriptedChannel([
      { ok: false, code: 'invalid_recipient', retryable: false },
    ]);

    const report = await dispatchNotifications(repository, channel, { now: () => T0 });

    assert.deepEqual(report, { claimed: 1, sent: 0, retried: 0, failed: 1, skipped: 0 });
    assert.equal(calls.length, 1);
    const [row] = await repository.listOrderNotifications(orderId);
    assert.equal(row?.status, 'FAILED');
    assert.equal(row?.lastError, 'invalid_recipient');
  });

  it('treats a throwing channel as transient and keeps the batch alive', async () => {
    const { repository, orderId } = await paidOrderWithQueue();
    const channel: SmsChannel = {
      id: 'mock',
      mode: 'MOCK',
      async send() {
        throw new Error('socket hang up');
      },
    };

    const report = await dispatchNotifications(repository, channel, { now: () => T0 });

    assert.equal(report.retried, 1);
    const [row] = await repository.listOrderNotifications(orderId);
    assert.equal(row?.status, 'PENDING');
    assert.equal(row?.lastError, 'transport_error');
  });
});

describe('§6.2 rows that cannot be sent are skipped, not retried', () => {
  it('refuses an unusable customer phone before calling the provider', async () => {
    const repository = createMemoryRepository({
      orders: [
        {
          id: 'order-no-phone',
          customerName: 'مشتری بدون شماره',
          customerPhone: 'user-42-sms',
          postalCode: '1999999999',
          status: 'PENDING',
          totalAmount: 900_000,
          discountAmount: 0,
          shippingAmount: 0,
          trackingCode: null,
          shippingAddress: 'تهران',
          paymentRefId: null,
          createdAt: new Date('2026-06-01T00:00:00.000Z'),
          items: [
            {
              sku: 'no-phone-S',
              productTitle: 'مانتو',
              size: 'S',
              colorName: 'مشکی',
              quantity: 1,
              unitPrice: 900_000,
            },
          ],
        },
      ],
    });

    const moved = await transitionOrder(repository, 'order-no-phone', 'PAID', MERCHANT_TRANSITION, [
      { kind: ORDER_CONFIRMED_KIND, channel: SMS_CHANNEL },
    ]);
    assert.deepEqual(moved, { ok: true });

    const channel = new MockSmsChannel();
    const report = await dispatchNotifications(repository, channel, { now: () => T0 });

    assert.deepEqual(report, { claimed: 1, sent: 0, retried: 0, failed: 0, skipped: 1 });
    assert.equal(channel.calls.length, 0);
    const [row] = await repository.listOrderNotifications('order-no-phone');
    assert.equal(row?.status, 'FAILED');
    assert.equal(row?.lastError, 'invalid_recipient');
  });
});


