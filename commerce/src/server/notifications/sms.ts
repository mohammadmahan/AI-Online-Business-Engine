import {
  MAX_SMS_CHARS,
  countCharacters,
  normalizeSmsRecipient,
  type OrderNotificationKind,
} from '@/lib/notification-rules';

/**
 * D-172 §6.2 — the SMS channel, behind a PORT.
 *
 * The owner selected Kavenegar (decision row 74), and this module is its
 * adapter — not a second dispatch path. Two implementations of one interface:
 *
 *  - `MockSmsChannel` is the DEFAULT. It records the call and sends NOTHING, so
 *    `npm test`, local runs and any deployment without credentials never touch a
 *    network. This is the D-045 state: no SMS credential exists, none is
 *    requested, and the app still exercises the whole queue.
 *  - `KavenegarSmsChannel` is the LIVE one. It is construction-gated (see
 *    `createSmsChannelFromEnv`) and every network effect goes through an
 *    INJECTED transport, exactly like the ZarinPal adapter — no test reaches the
 *    internet, and swapping to MelliSMS later means writing another object of
 *    this shape rather than editing a caller.
 *
 * Deliberately NOT here: the registry. The canonical `NotificationWorker`
 * (`local/canonical/sms_adapter.py`) carries the sealed template registry, and
 * admitting `order.confirmed.v1` to it moves the sealed D-168 phase-18 chain
 * digest — an owner re-attestation. This app's queue is its OWN storage (the
 * `commerce` namespace, G-1/G-2) and its own body table, so it sends the same
 * text without touching that registry, that digest or the canonical worker.
 * When the owner admits the template there, the two paths converge on the same
 * wording; until then this one is the only path that can actually deliver an
 * order confirmation.
 *
 * Secrets: the API key is read from the environment at construction, used as a
 * URL path segment, and never returned, logged, stored or echoed in a failure.
 * Errors cross this boundary as a CODE only (D-114/D-124).
 */

/* ------------------------------------------------------------------- port */

export type SmsFailureCode =
  | 'invalid_recipient'
  | 'body_unavailable'
  | 'invalid_sender'
  | 'invalid_api_key'
  | 'template_not_registered'
  | 'no_credit'
  | 'rate_limited'
  | 'provider_unavailable'
  | 'provider_refused'
  | 'transport_error'
  | 'malformed_response';

export interface SmsMessage {
  /** The recipient as it appears on the order; normalised here, never by the caller. */
  to: string;
  kind: OrderNotificationKind;
  body: string;
}

export type SmsSendResult =
  | { ok: true; providerMessageId: string | null }
  | {
      ok: false;
      code: SmsFailureCode;
      /** `true` only when retrying the SAME message can succeed. */
      retryable: boolean;
      /** Provider-indicated wait, when it gave one. */
      retryAfterSeconds?: number;
    };

export interface SmsChannel {
  readonly id: 'mock' | 'kavenegar';
  /** `MOCK` never leaves the process; `LIVE` performs a provider call. */
  readonly mode: 'MOCK' | 'LIVE';
  send(message: SmsMessage): Promise<SmsSendResult>;
}

/* ------------------------------------------------------------------- mock */

export interface MockSmsCall {
  to: string;
  kind: OrderNotificationKind;
  body: string;
  providerMessageId: string;
}

/**
 * The default channel: deterministic, offline, and honest about it.
 *
 * It validates exactly what the live one validates (recipient and body), so a
 * deployment that has not been given credentials still exercises the refusal
 * paths — a mock that accepts anything would hide the bug until go-live.
 */
export class MockSmsChannel implements SmsChannel {
  readonly id = 'mock' as const;
  readonly mode = 'MOCK' as const;

  /** Every accepted message, in order. Tests assert against this. */
  readonly calls: MockSmsCall[] = [];

  async send(message: SmsMessage): Promise<SmsSendResult> {
    const to = normalizeSmsRecipient(message.to);
    if (to === null) {
      return { ok: false, code: 'invalid_recipient', retryable: false };
    }
    const length = countCharacters(message.body);
    if (length === 0 || length > MAX_SMS_CHARS) {
      return { ok: false, code: 'body_unavailable', retryable: false };
    }
    const providerMessageId = `MOCK-SMS-${this.calls.length + 1}`;
    this.calls.push({ to, kind: message.kind, body: message.body, providerMessageId });
    return { ok: true, providerMessageId };
  }
}

/* --------------------------------------------------------------- live env */

export const SMS_LIVE_ENABLED_ENV = 'SMS_LIVE_ENABLED';
export const KAVENEGAR_API_KEY_ENV = 'KAVENEGAR_API_KEY';
export const KAVENEGAR_SENDER_ENV = 'KAVENEGAR_SENDER';

/** Kavenegar's versioned API root; the key is a PATH segment, not a header. */
export const KAVENEGAR_API_BASE = 'https://api.kavenegar.com/v1';

export const SMS_TIMEOUT_MS = 15_000;

export interface SmsHttpRequest {
  url: string;
  /** `application/x-www-form-urlencoded`, which is what Kavenegar documents. */
  form: Record<string, string>;
}

export interface SmsHttpResponse {
  status: number;
  /** Parsed JSON, or `null` when the body was not JSON at all. */
  body: unknown;
}

/** The only place a socket exists. Tests inject a fake and never call this. */
export type SmsTransport = (request: SmsHttpRequest) => Promise<SmsHttpResponse>;

/**
 * The default transport: the app's only socket. It is injected like ZarinPal's,
 * so no test ever reaches it, and it is exported so the composition root can
 * hand the SAME one to the gate without a dynamic import.
 */
export const defaultSmsTransport: SmsTransport = async ({ url, form }) => {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/x-www-form-urlencoded; charset=utf-8',
      accept: 'application/json',
    },
    body: new URLSearchParams(form).toString(),
    signal: AbortSignal.timeout(SMS_TIMEOUT_MS),
  });

  let parsed: unknown = null;
  try {
    parsed = await response.json();
  } catch {
    parsed = null;
  }

  return { status: response.status, body: parsed };
};

/* --------------------------------------------------------------- provider */

/**
 * Kavenegar's `return.status` → this adapter's outcome.
 *
 * Mirrors `sms_adapter.classify_kavenegar_status`, including the direction that
 * matters: an UNKNOWN 4xx fails CLOSED as permanent (a bad request will not fix
 * itself by retrying), while an unknown 5xx is transient. 426–429 mean "slow
 * down" and are the only codes that carry a wait.
 */
export function classifyKavenegarStatus(status: number): SmsSendResult {
  const code = Number(status);
  const rateLimits: Record<number, number> = { 426: 60, 427: 3_600, 428: 3_600, 429: 60 };
  const limited = rateLimits[code];
  if (limited !== undefined) {
    return { ok: false, code: 'rate_limited', retryable: true, retryAfterSeconds: limited };
  }
  if ([500, 501, 502, 503, 504, 507].includes(code)) {
    return { ok: false, code: 'provider_unavailable', retryable: true };
  }
  const permanent: Record<number, SmsFailureCode> = {
    400: 'provider_refused',
    401: 'invalid_api_key',
    402: 'provider_refused',
    403: 'provider_refused',
    404: 'provider_refused',
    405: 'provider_refused',
    406: 'provider_refused',
    407: 'provider_refused',
    409: 'provider_refused',
    411: 'invalid_sender',
    412: 'invalid_recipient',
    413: 'provider_refused',
    414: 'body_unavailable',
    415: 'body_unavailable',
    416: 'provider_refused',
    417: 'provider_refused',
    418: 'provider_refused',
    419: 'provider_refused',
    420: 'provider_refused',
    422: 'template_not_registered',
    424: 'provider_refused',
    431: 'provider_refused',
    432: 'template_not_registered',
    451: 'no_credit',
  };
  const mapped = permanent[code];
  if (mapped !== undefined) {
    return { ok: false, code: mapped, retryable: false };
  }
  if (code >= 400 && code < 500) {
    return { ok: false, code: 'provider_refused', retryable: false };
  }
  return { ok: false, code: 'provider_unavailable', retryable: true };
}

interface KavenegarEnvelope {
  providerStatus: number | null;
  messageId: string | null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * Kavenegar answers `{ return: { status, message }, entries: [{ messageid }] }`.
 * Narrowed field by field: a 200 without a usable envelope is
 * `malformed_response`, never an invented success (D-052 shape).
 */
function readKavenegarEnvelope(body: unknown): KavenegarEnvelope {
  const root = asRecord(body);
  if (root === null) {
    return { providerStatus: null, messageId: null };
  }
  const header = asRecord(root.return);
  const rawStatus = header?.status;
  const providerStatus =
    typeof rawStatus === 'number'
      ? rawStatus
      : typeof rawStatus === 'string' && rawStatus.trim() !== ''
        ? Number(rawStatus)
        : null;
  const entries = root.entries;
  let messageId: string | null = null;
  if (Array.isArray(entries) && entries.length > 0) {
    const first = asRecord(entries[0]);
    const value = first?.messageid;
    if (typeof value === 'string' && value.trim() !== '') {
      messageId = value.trim();
    } else if (typeof value === 'number' && Number.isFinite(value)) {
      messageId = String(value);
    }
  }
  return {
    providerStatus: Number.isFinite(providerStatus) ? providerStatus : null,
    messageId,
  };
}

/**
 * The live Kavenegar adapter — construction-gated, injected transport.
 *
 * Only the PLAIN-TEXT route (`sms/send.json`) is used: the canonical adapter's
 * OTP route (`verify/lookup.json`) belongs to an OTP flow this app has no login
 * path for yet, and an order confirmation is exactly what a locally rendered
 * body is for.
 */
export class KavenegarSmsChannel implements SmsChannel {
  readonly id = 'kavenegar' as const;
  readonly mode = 'LIVE' as const;

  private readonly transport: SmsTransport;
  private readonly apiKey: string;
  private readonly sender: string;

  constructor(transport: SmsTransport, credentials: { apiKey: string; sender: string }) {
    const apiKey = credentials.apiKey.trim();
    const sender = credentials.sender.trim();
    if (apiKey.length === 0) {
      throw new Error('KavenegarSmsChannel requires a non-empty API key');
    }
    if (sender.length === 0) {
      throw new Error('KavenegarSmsChannel requires a non-empty sender line');
    }
    this.transport = transport;
    this.apiKey = apiKey;
    this.sender = sender;
  }

  async send(message: SmsMessage): Promise<SmsSendResult> {
    const to = normalizeSmsRecipient(message.to);
    if (to === null) {
      return { ok: false, code: 'invalid_recipient', retryable: false };
    }
    const length = countCharacters(message.body);
    if (length === 0 || length > MAX_SMS_CHARS) {
      return { ok: false, code: 'body_unavailable', retryable: false };
    }

    let response: SmsHttpResponse;
    try {
      response = await this.transport({
        url: `${KAVENEGAR_API_BASE}/${this.apiKey}/sms/send.json`,
        form: { receptor: to, sender: this.sender, message: message.body },
      });
    } catch {
      // The thrown value can carry a URL — which carries the key. Report the
      // outcome, never the error (D-114/D-124).
      return { ok: false, code: 'transport_error', retryable: true };
    }

    const envelope = readKavenegarEnvelope(response.body);
    if (response.status === 200 && envelope.providerStatus === 200) {
      return { ok: true, providerMessageId: envelope.messageId };
    }
    if (envelope.providerStatus !== null && envelope.providerStatus !== 200) {
      return classifyKavenegarStatus(envelope.providerStatus);
    }
    if (response.status === 200) {
      return { ok: false, code: 'malformed_response', retryable: false };
    }
    if (response.status === 429) {
      return { ok: false, code: 'rate_limited', retryable: true, retryAfterSeconds: 60 };
    }
    if (response.status >= 500) {
      return { ok: false, code: 'provider_unavailable', retryable: true };
    }
    return { ok: false, code: 'provider_refused', retryable: false };
  }
}

/* ----------------------------------------------------------- construction */

export type SmsChannelResolution =
  | { ok: true; channel: SmsChannel; mode: 'MOCK' | 'LIVE' }
  | {
      ok: false;
      code: 'SMS_LIVE_MODE_MISSING_CREDENTIAL';
      /** A static Persian explanation; never echoes a credential. */
      message: string;
    };

/**
 * The ONE place a channel is chosen (D-075-shaped construction gate).
 *
 *  - flag off (default)         → the mock. Local mode, no network, D-045 holds:
 *    no Kavenegar credential exists and none is requested;
 *  - flag on, key/sender missing → a REFUSAL, not a silent mock: an operator who
 *    asked for live SMS and did not get it must see that, and the queue rows stay
 *    `PENDING` rather than being quietly "delivered" into a log;
 *  - flag on, credentials present → the live adapter over the injected transport
 *    (the default transport is `fetch`, and no test ever reaches it).
 */
export function createSmsChannelFromEnv(
  env: Record<string, string | undefined> = process.env,
  transport: SmsTransport = defaultSmsTransport,
): SmsChannelResolution {
  const live = (env[SMS_LIVE_ENABLED_ENV] ?? '').trim().toLowerCase() === 'true';
  if (!live) {
    return { ok: true, channel: new MockSmsChannel(), mode: 'MOCK' };
  }

  const apiKey = (env[KAVENEGAR_API_KEY_ENV] ?? '').trim();
  const sender = (env[KAVENEGAR_SENDER_ENV] ?? '').trim();
  if (apiKey.length === 0 || sender.length === 0) {
    return {
      ok: false,
      code: 'SMS_LIVE_MODE_MISSING_CREDENTIAL',
      message:
        'ارسالِ پیامکِ زنده درخواست شده است اما کلیدِ کاوه‌نگار یا خطِ فرستنده تنظیم نشده؛ هیچ پیامکی ارسال نمی‌شود.',
    };
  }

  return {
    ok: true,
    channel: new KavenegarSmsChannel(transport, { apiKey, sender }),
    mode: 'LIVE',
  };
}
