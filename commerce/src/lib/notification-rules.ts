/**
 * D-172 §6.2 — notification rules, as a PURE module.
 *
 * Three facts live here because all three must be decided in exactly one place:
 *
 *  1. WHAT may be announced (`ORDER_NOTIFICATION_KINDS`). The set is closed:
 *     a kind that is not listed cannot be enqueued, and adding one is a schema
 *     migration (`notification_outbox_kind_known`) plus a body, not a free-text
 *     string at a call site. The owner's §6.2 wish list — OTP login, order
 *     confirmation, postal tracking — is NOT copied in wholesale: only
 *     `order.confirmed` has a trigger and a provider path the commerce app can
 *     honour today, and tracking belongs to the shipping provider that decision
 *     row 11 has not selected.
 *  2. WHAT the message says. The Persian bodies MIRROR
 *     `local/canonical/sms_adapter.py::_BODY_TEMPLATES` word for word, so the
 *     same order reads the same whether the canonical engine or this app sends
 *     it. The rendered length is bounded by `MAX_SMS_CHARS` (280 characters, the
 *     same bound the adapter enforces) — an over-long body is a refusal, never a
 *     silently truncated SMS.
 *  3. WHO it may be sent to. `normalizeSmsRecipient` is the adapter's
 *     `normalize_recipient` rule: an Iranian MSISDN in `09xxxxxxxxx` form, or
 *     `null`. A symbolic reference can never reach a provider.
 *
 * Nothing here reads the environment, the clock or the database, so it is
 * unit-testable on its own and safe to import from either side of the app.
 */

/* ------------------------------------------------------------- vocabulary */

/** The one message kind that has a trigger today (§6.2 buyer messages). */
export const ORDER_CONFIRMED_KIND = 'order.confirmed' as const;

/** The only channel Kavenegar serves here (decision row 74). */
export const SMS_CHANNEL = 'SMS' as const;

export const ORDER_NOTIFICATION_KINDS = [ORDER_CONFIRMED_KIND] as const;
export const ORDER_NOTIFICATION_CHANNELS = [SMS_CHANNEL] as const;

export type OrderNotificationKind = (typeof ORDER_NOTIFICATION_KINDS)[number];
export type OrderNotificationChannel = (typeof ORDER_NOTIFICATION_CHANNELS)[number];

/** Attempt budget for one queued SMS, and the backoff between attempts. */
export const MAX_SMS_ATTEMPTS = 3;

/**
 * How long a claimed row may stay `SENDING` before another dispatcher may take
 * it. A claimant that crashes mid-send leaves the row claimed; this lease is
 * what makes that recoverable instead of permanent (at-least-once delivery in
 * the crash window, which is the correct trade for a notification).
 */
export const NOTIFICATION_LEASE_MS = 5 * 60_000;

/** Seconds to wait before the next attempt, by the attempt just made. */
export const SMS_BACKOFF_SECONDS = [60, 300, 1_800] as const;

/** Bound on a plain SMS, mirroring `sms_adapter.MAX_MESSAGE_CHARS`. */
export const MAX_SMS_CHARS = 280;

/* ----------------------------------------------------------------- bodies */

/**
 * Locally rendered Persian bodies (D-171: Persian prose, Latin identifiers).
 *
 * `order.tracking` is intentionally absent: a tracking SMS needs the carrier's
 * code and the shipping provider is still unselected (decision row 11). Writing
 * a body for it now would be inventing a message nothing can trigger.
 */
const SMS_BODIES: Record<OrderNotificationKind, string> = {
  [ORDER_CONFIRMED_KIND]: 'سفارش {order_ref} ثبت شد. از خرید شما سپاسگزاریم.',
};

/**
 * A short, human-readable reference for an order, derived from its id.
 *
 * Deterministic and collision-adequate for a message body (the first eight
 * characters of the UUID), and never the customer's — a body is read aloud on a
 * phone, so a full order id is noise. Every internal correlation keeps using the
 * full id.
 */
export function orderReference(orderId: string): string {
  const compact = orderId.replace(/[^0-9a-zA-Z]/g, '');
  return compact.length === 0 ? 'UNKNOWN' : compact.slice(0, 8).toUpperCase();
}

/**
 * The body for `kind`, or `null` when it cannot be rendered. `null` is a
 * refusal (`body_unavailable`), never an empty SMS: an unrenderable template is
 * a deployment mistake and the queue records it as a permanent failure.
 */
export function renderNotificationBody(
  kind: OrderNotificationKind,
  variables: { orderRef: string },
): string | null {
  const template = SMS_BODIES[kind];
  if (template === undefined) {
    return null;
  }
  const body = template.replace('{order_ref}', variables.orderRef);
  const length = countCharacters(body);
  if (length === 0 || length > MAX_SMS_CHARS) {
    return null;
  }
  return body;
}

/** Code points, not UTF-16 units: a Persian body is measured the way a phone shows it. */
export function countCharacters(text: string): number {
  return Array.from(text).length;
}


/* ------------------------------------------------------------- recipient */

/**
 * Normalise a phone number to the `09xxxxxxxxx` MSISDN form, or `null`.
 *
 * Mirrors `sms_adapter.normalize_recipient`: `+98912…`, `0098912…` and `0912…`
 * all collapse to one value, while a short code, a landline or a symbolic
 * reference is refused before any provider call.
 */
export function normalizeSmsRecipient(raw: string | null | undefined): string | null {
  const text = String(raw ?? '').trim();
  if (text.length === 0) {
    return null;
  }
  let digits = text.replace(/\D/g, '');
  if (digits.length === 0) {
    return null;
  }
  if (digits.length === 12 && digits.startsWith('98')) {
    digits = `0${digits.slice(2)}`;
  }
  if (digits.length !== 11 || !digits.startsWith('09')) {
    return null;
  }
  return digits;
}

/**
 * A recipient as it may appear in a LOG line: never the whole number. The queue
 * stores no number at all, and an operator reading a log needs to know a message
 * went somewhere, not where the customer lives.
 */
export function maskSmsRecipient(recipient: string): string {
  const digits = recipient.replace(/\D/g, '');
  if (digits.length < 7) {
    return '***';
  }
  return `${digits.slice(0, 4)}***${digits.slice(-3)}`;
}

/* ---------------------------------------------------------------- backoff */

/**
 * Seconds before the next attempt, given the attempt that just failed. Bounded
 * by the table above — a retry schedule is policy, and a policy read from a
 * table is reviewable. An attempt past the table retries at the last interval
 * (the budget, not the clock, is what ends a stuck message).
 */
export function smsBackoffSeconds(attempt: number): number {
  const index = Math.min(Math.max(attempt, 1), SMS_BACKOFF_SECONDS.length) - 1;
  return SMS_BACKOFF_SECONDS[index] as number;
}
