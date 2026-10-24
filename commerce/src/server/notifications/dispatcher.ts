import {
  MAX_SMS_ATTEMPTS,
  ORDER_CONFIRMED_KIND,
  SMS_CHANNEL,
  maskSmsRecipient,
  normalizeSmsRecipient,
  orderReference,
  renderNotificationBody,
  smsBackoffSeconds,
} from '@/lib/notification-rules';

import type { CommerceRepository, NotificationWorkItem } from '../repository';
import type { SmsChannel, SmsSendResult } from './sms';

/**
 * D-172 §6.2 — the dispatcher: what turns a queue row into a delivered SMS.
 *
 * Deliberately separate from the payment path. `applyPaymentCallback` (and the
 * transition it shares with the webhook and the merchant panel) only ENQUEUES;
 * this module reads the queue, resolves the recipient from the customer record,
 * renders the body, calls the channel and records the outcome. Two consequences:
 *
 *  - a provider outage cannot fail a payment that has already been taken, and a
 *    payment write cannot be slowed down by an SMS;
 *  - the dispatcher is a plain function of `(repository, channel, clock)`, so
 *    every branch — sent, retried, terminal, refused-before-send — is unit
 *    tested without a network, a database or a timer.
 *
 * Idempotency has three layers and none of them is a flag:
 *  1. the outbox row is unique per `(order, kind, channel)` — a second callback
 *     cannot create a second message;
 *  2. the CLAIM moves `PENDING → SENDING` atomically, so two dispatchers cannot
 *     deliver the same row (the loser skips it: `SKIP LOCKED`);
 *  3. a `SENT` row is never claimable again, so a later run has nothing to do.
 *
 * Crash windows are stated rather than hidden: a claimant that dies between the
 * provider call and `markNotificationSent` leaves a `SENDING` row whose lease
 * expires and which is then retried — at-least-once in that window, which is the
 * correct trade for a notification (a duplicate "order confirmed" is a nuisance;
 * a missing one is a support ticket).
 */

export interface NotificationDispatchOptions {
  /** Upper bound on rows claimed in one run. Defaults to 50. */
  limit?: number;
  /** Injected clock, so a retry test never sleeps. */
  now?: () => Date;
}

export interface NotificationDispatchReport {
  /** Rows this run claimed. Nothing else is touched. */
  claimed: number;
  sent: number;
  /** Rescheduled after a transient provider failure (still `PENDING`). */
  retried: number;
  /** Terminal provider refusal, or the attempt budget spent. */
  failed: number;
  /** Refused BEFORE any provider call (missing order, bad recipient, no body). */
  skipped: number;
}

const DEFAULT_LIMIT = 50;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** The channel's outcome, with a throwing adapter treated as transient. */
async function deliver(
  channel: SmsChannel,
  message: Parameters<SmsChannel['send']>[0],
): Promise<SmsSendResult> {
  try {
    return await channel.send(message);
  } catch {
    // A custom adapter that throws must not abort the batch: the remaining rows
    // still deserve their attempt, and this one is retryable by definition.
    return { ok: false, code: 'transport_error', retryable: true };
  }
}

export async function dispatchNotifications(
  repository: CommerceRepository,
  channel: SmsChannel,
  options: NotificationDispatchOptions = {},
): Promise<NotificationDispatchReport> {
  const now = options.now?.() ?? new Date();
  const limit = options.limit ?? DEFAULT_LIMIT;
  const report: NotificationDispatchReport = {
    claimed: 0,
    sent: 0,
    retried: 0,
    failed: 0,
    skipped: 0,
  };

  const batch = await repository.claimNotificationBatch(limit, now);
  report.claimed = batch.length;

  for (const item of batch) {
    const outcome = await dispatchOne(repository, channel, item, now);
    report[outcome.kind] += 1;
    if (outcome.kind === 'sent' && channel.mode === 'MOCK') {
      // Local mode is the D-045 state: nothing is sent, so the payload is what an
      // operator can actually inspect. No full phone number is ever logged.
      console.info('[commerce] sms delivered (mock)', {
        orderId: outcome.orderId,
        kind: item.kind,
        recipient: maskSmsRecipient(outcome.recipient),
        body: outcome.body,
        providerMessageId: outcome.providerMessageId,
      });
    }
  }

  return report;
}

type DispatchOutcome =
  | {
      kind: 'sent';
      orderId: string;
      recipient: string;
      body: string;
      providerMessageId: string | null;
    }
  | { kind: 'retried' | 'failed' | 'skipped' };

/**
 * One claimed row. The order of the checks is the contract:
 *
 *  1. an unknown kind/channel is refused before anything is read (a row from a
 *     future migration must not be sent by this build's body table);
 *  2. a missing order, an unusable recipient or an unrenderable body is
 *     PERMANENT — retrying cannot fix a bad number, and burning three attempts
 *     on it would delay every message behind it;
 *  3. a provider refusal is classified by the adapter: retryable outcomes are
 *     rescheduled with the backoff table, terminal ones are recorded and dropped.
 */
async function dispatchOne(
  repository: CommerceRepository,
  channel: SmsChannel,
  item: NotificationWorkItem,
  now: Date,
): Promise<DispatchOutcome> {
  if (item.kind !== ORDER_CONFIRMED_KIND || item.channel !== SMS_CHANNEL) {
    await repository.markNotificationFailed(item.id, 'unsupported_kind', null, now);
    return { kind: 'skipped' };
  }

  const order = await repository.getOrderDetail(item.orderId);
  if (order === null) {
    await repository.markNotificationFailed(item.id, 'order_missing', null, now);
    return { kind: 'skipped' };
  }

  const recipient = normalizeSmsRecipient(order.customerPhone);
  if (recipient === null) {
    await repository.markNotificationFailed(item.id, 'invalid_recipient', null, now);
    return { kind: 'skipped' };
  }

  const orderRef = isRecord(item.payload) && typeof item.payload.orderRef === 'string'
    ? item.payload.orderRef
    : orderReference(order.id);
  const body = renderNotificationBody(item.kind, { orderRef });
  if (body === null) {
    await repository.markNotificationFailed(item.id, 'body_unavailable', null, now);
    return { kind: 'skipped' };
  }

  const result = await deliver(channel, { to: recipient, kind: item.kind, body });

  if (result.ok) {
    await repository.markNotificationSent(item.id, result.providerMessageId, now);
    return {
      kind: 'sent',
      orderId: order.id,
      recipient,
      body,
      providerMessageId: result.providerMessageId,
    };
  }

  const retryAt =
    result.retryable && item.attempts < MAX_SMS_ATTEMPTS
      ? new Date(
          now.getTime() +
            (result.retryAfterSeconds ?? smsBackoffSeconds(item.attempts)) * 1_000,
        )
      : null;

  await repository.markNotificationFailed(item.id, result.code, retryAt, now);
  return { kind: retryAt === null ? 'failed' : 'retried' };
}

