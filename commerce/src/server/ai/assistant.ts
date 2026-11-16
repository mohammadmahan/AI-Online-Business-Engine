/**
 * D-172 §4.1 / D-176 — server-only client for the local commerce AI bridge.
 *
 * This module deliberately imports NO database, repository, order or customer
 * code. The assistant receives only the merchant's own product facts, never a
 * customer row, an order, a phone number or an address. That is a structural
 * boundary, not a prompt instruction.
 *
 * Fail-closed rules:
 *  - both `AI_ASSISTANT_URL` and `AI_ASSISTANT_TOKEN` are required;
 *  - the URL must be plain HTTP on 127.0.0.1/localhost/[::1], with an explicit
 *    port and no credentials/path/query;
 *  - unauthenticated server actions never reach the bridge;
 *  - the bridge's response is shape-checked and PII-scanned again here;
 *  - provider messages, tokens and prompts are never logged or returned.
 *
 * The bridge itself runs the canonical Python fashion engine in dry-run mode
 * over local Ollama. This client cannot persist, publish or write an order.
 */

export const ASSISTANT_URL_ENV = 'AI_ASSISTANT_URL';
export const ASSISTANT_TOKEN_ENV = 'AI_ASSISTANT_TOKEN';
export const ASSISTANT_TIMEOUT_MS = 125_000;
export const ASSISTANT_MAX_RESPONSE_BYTES = 64 * 1024;

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);
const CHANNELS = ['seo_copy', 'instagram_caption', 'telegram_announcement'] as const;
const TONES = ['luxury', 'casual', 'trendy'] as const;

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;
const PHONE_RE = /(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)/;
const LONG_DIGITS_RE = /\d{10,}/;
const URL_RE = /\b(?:https?:\/\/|www\.|t\.me\/)/i;

export type AssistantChannel = (typeof CHANNELS)[number];
export type AssistantTone = (typeof TONES)[number];

export interface AssistantInput {
  channel: AssistantChannel;
  title: string;
  fabricType: string;
  season: string;
  notes?: string;
  tone?: AssistantTone;
}

export type AssistantFailureCode =
  | 'UNAUTHORIZED'
  | 'AI_NOT_CONFIGURED'
  | 'AI_UNAUTHORIZED'
  | 'AI_UNAVAILABLE'
  | 'AI_TIMEOUT'
  | 'AI_REFUSED'
  | 'AI_INVALID_RESPONSE'
  | 'VALIDATION_ERROR';

export type AssistantResult =
  | {
      ok: true;
      channel: AssistantChannel;
      mode: 'dry-run';
      proposal: Record<string, unknown>;
      provider: string;
      model: string;
      usage: Record<string, unknown>;
      warnings: string[];
    }
  | { ok: false; code: AssistantFailureCode; message: string; field?: string };

interface AssistantConfig {
  endpoint: string;
  token: string;
}

export interface AssistantDeps {
  /** Re-checked inside the action; a Server Action id is its own entry point. */
  authorized: boolean;
  env?: NodeJS.ProcessEnv;
  fetch?: typeof fetch;
}

function fail(
  code: AssistantFailureCode,
  message: string,
  field?: string,
): Extract<AssistantResult, { ok: false }> {
  return { ok: false, code, message, ...(field ? { field } : {}) };
}

function text(value: unknown, label: string, min: number, max: number): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const clean = value.trim();
  if (clean.length < min || clean.length > max) {
    return null;
  }
  return clean;
}

function hasPii(value: string): boolean {
  return (
    EMAIL_RE.test(value) ||
    PHONE_RE.test(value) ||
    LONG_DIGITS_RE.test(value) ||
    URL_RE.test(value)
  );
}

export function validateAssistantInput(
  input: unknown,
): { ok: true; value: AssistantInput } | { ok: false; field: string } {
  if (typeof input !== 'object' || input === null || Array.isArray(input)) {
    return { ok: false, field: 'form' };
  }
  const record = input as Record<string, unknown>;
  const allowed = new Set(['channel', 'title', 'fabricType', 'season', 'notes', 'tone']);
  if (Object.keys(record).some((key) => !allowed.has(key))) {
    return { ok: false, field: 'form' };
  }

  const channel = record.channel;
  if (typeof channel !== 'string' || !CHANNELS.includes(channel as AssistantChannel)) {
    return { ok: false, field: 'channel' };
  }
  const title = text(record.title, 'title', 2, 200);
  if (title === null) return { ok: false, field: 'title' };
  const fabricType = text(record.fabricType, 'fabricType', 2, 60);
  if (fabricType === null) return { ok: false, field: 'fabricType' };
  const season = text(record.season, 'season', 1, 40);
  if (season === null) return { ok: false, field: 'season' };
  const notes = text(record.notes ?? '', 'notes', 0, 1000);
  if (notes === null) return { ok: false, field: 'notes' };
  const tone = record.tone ?? 'luxury';
  if (typeof tone !== 'string' || !TONES.includes(tone as AssistantTone)) {
    return { ok: false, field: 'tone' };
  }

  for (const [field, value] of [
    ['title', title],
    ['fabricType', fabricType],
    ['season', season],
    ['notes', notes],
  ] as const) {
    if (hasPii(value)) return { ok: false, field };
  }

  return {
    ok: true,
    value: {
      channel: channel as AssistantChannel,
      title,
      fabricType,
      season,
      notes,
      tone: tone as AssistantTone,
    },
  };
}

export function resolveAssistantConfig(
  env: NodeJS.ProcessEnv = process.env,
): AssistantConfig | null {
  const rawUrl = (env[ASSISTANT_URL_ENV] ?? '').trim();
  const token = (env[ASSISTANT_TOKEN_ENV] ?? '').trim();
  if (!rawUrl || token.length < 16) {
    return null;
  }
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }
  if (
    url.protocol !== 'http:' ||
    !LOOPBACK_HOSTS.has(url.hostname) ||
    url.port === '' ||
    url.username !== '' ||
    url.password !== '' ||
    url.pathname !== '/' ||
    url.search !== '' ||
    url.hash !== ''
  ) {
    return null;
  }
  return { endpoint: new URL('/assistant', url).toString(), token };
}

const PROPOSAL_KEYS: Record<AssistantChannel, { required: string[]; optional: string[] }> = {
  seo_copy: {
    required: ['meta_description_fa', 'web_copy_fa', 'seo_keywords', 'rationale'],
    optional: [],
  },
  instagram_caption: {
    required: ['caption_fa', 'hashtags', 'alt_text'],
    optional: ['media_ref'],
  },
  telegram_announcement: {
    required: ['announcement_fa', 'hashtags'],
    optional: ['cta_fa'],
  },
};

function validateProposal(
  channel: AssistantChannel,
  proposal: unknown,
): Record<string, unknown> | null {
  if (typeof proposal !== 'object' || proposal === null || Array.isArray(proposal)) {
    return null;
  }
  const record = proposal as Record<string, unknown>;
  const keys = PROPOSAL_KEYS[channel];
  const allowed = new Set([...keys.required, ...keys.optional]);
  if (
    Object.keys(record).some((key) => !allowed.has(key)) ||
    keys.required.some((key) => !(key in record))
  ) {
    return null;
  }
  for (const [key, value] of Object.entries(record)) {
    if (Array.isArray(value)) {
      if (value.length > 30 || value.some((item) => typeof item !== 'string')) {
        return null;
      }
      if (value.some((item) => hasPii(item as string))) return null;
    } else if (typeof value === 'string') {
      if (value.length > 8_000 || hasPii(value)) return null;
    } else {
      return null;
    }
    void key;
  }
  return record;
}

/**
 * Pure request handler used by both the Server Action and its tests.
 * `authorized` is mandatory so there is no code path that forgets auth.
 */
export async function handleAssistantRequest(
  input: unknown,
  deps: AssistantDeps,
): Promise<AssistantResult> {
  if (!deps.authorized) {
    return fail('UNAUTHORIZED', 'دسترسی به دستیار هوش مصنوعی مجاز نیست.');
  }

  const validated = validateAssistantInput(input);
  if (!validated.ok) {
    return fail('VALIDATION_ERROR', 'مشخصات ورودی معتبر نیست.', validated.field);
  }

  const config = resolveAssistantConfig(deps.env);
  if (config === null) {
    return fail(
      'AI_NOT_CONFIGURED',
      'پل هوش مصنوعی محلی تنظیم نشده است؛ هیچ درخواستی ارسال نشد.',
    );
  }

  const value = validated.value;
  const payload = {
    channel: value.channel,
    title: value.title,
    fabric_type: value.fabricType,
    season: value.season,
    notes: value.notes ?? '',
    tone: value.tone ?? 'luxury',
  };

  let response: Response;
  try {
    response = await (deps.fetch ?? fetch)(config.endpoint, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${config.token}`,
        'content-type': 'application/json',
        accept: 'application/json',
      },
      body: JSON.stringify(payload),
      cache: 'no-store',
      signal: AbortSignal.timeout(ASSISTANT_TIMEOUT_MS),
    });
  } catch (error) {
    const name = error instanceof Error ? error.name : 'UnknownError';
    return name === 'TimeoutError' || name === 'AbortError'
      ? fail('AI_TIMEOUT', 'پل هوش مصنوعی در زمان مجاز پاسخ نداد.')
      : fail('AI_UNAVAILABLE', 'پل هوش مصنوعی محلی در دسترس نیست.');
  }

  const raw = await response.text().catch(() => '');
  if (raw.length > ASSISTANT_MAX_RESPONSE_BYTES) {
    return fail('AI_INVALID_RESPONSE', 'پاسخ پل هوش مصنوعی بیش از حد بزرگ بود.');
  }
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return fail('AI_INVALID_RESPONSE', 'پاسخ پل هوش مصنوعی JSON معتبر نیست.');
  }
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return fail('AI_INVALID_RESPONSE', 'پاسخ پل هوش مصنوعی شکل معتبر ندارد.');
  }
  const record = body as Record<string, unknown>;

  if (!response.ok || record.ok !== true) {
    switch (response.status) {
      case 401:
        return fail('AI_UNAUTHORIZED', 'توکن پل هوش مصنوعی پذیرفته نشد.');
      case 422:
        return fail('AI_REFUSED', 'پیشنهاد هوش مصنوعی از قواعد محتوا عبور نکرد.');
      case 503:
        return fail('AI_UNAVAILABLE', 'موتور هوش مصنوعی محلی آماده نیست.');
      default:
        return fail('AI_INVALID_RESPONSE', 'پل هوش مصنوعی پاسخ قابل‌قبولی نداد.');
    }
  }

  const proposal = validateProposal(value.channel, record.proposal);
  if (proposal === null) {
    return fail('AI_INVALID_RESPONSE', 'ساختار پیشنهاد هوش مصنوعی معتبر نیست.');
  }
  if (record.channel !== value.channel || record.mode !== 'dry-run') {
    return fail('AI_INVALID_RESPONSE', 'پاسخ پل با درخواست هم‌خوان نیست.');
  }

  return {
    ok: true,
    channel: value.channel,
    mode: 'dry-run',
    proposal,
    provider: typeof record.provider === 'string' ? record.provider.slice(0, 40) : 'ollama',
    model: typeof record.model === 'string' ? record.model.slice(0, 80) : '',
    usage:
      typeof record.usage === 'object' && record.usage !== null
        ? (record.usage as Record<string, unknown>)
        : {},
    warnings: Array.isArray(record.warnings)
      ? record.warnings.filter((item): item is string => typeof item === 'string').slice(0, 20)
      : [],
  };
}
