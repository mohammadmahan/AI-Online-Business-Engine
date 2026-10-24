import { createHash, timingSafeEqual } from 'node:crypto';

import { DB_NOT_CONFIGURED_MESSAGE, getRepository } from '../db-context';
import type { CommerceRepository } from '../repository';

import {
  dispatchNotifications,
  type NotificationDispatchReport,
} from './dispatcher';
import {
  createSmsChannelFromEnv,
  defaultSmsTransport,
  type SmsChannelResolution,
  type SmsTransport,
} from './sms';

/**
 * D-172 §6.2 — the queue's OPERATOR entry point: `POST /api/internal/notifications/dispatch`.
 *
 * Why a route and not a background loop: the app has no worker process, and
 * inventing one inside a Next server would make delivery depend on a request
 * that never comes. The queue is durable (PostgreSQL, G-1) and this endpoint is
 * the one trigger an operator or a scheduler calls: it drains ONE bounded batch
 * and answers with what happened. Calling it twice is safe (the claim is atomic),
 * and calling it never is safe too (rows simply wait).
 *
 * Authentication is a shared bearer token in `NOTIFICATIONS_DISPATCH_TOKEN`.
 * Fail-closed in the strongest sense available:
 *  - token unset          → 503, nothing is claimed. An endpoint that could be
 *    called unauthenticated because the environment forgot a variable is exactly
 *    the hole this shape prevents (D-171 §2.2: an absent configuration is a
 *    refusal, never a pass);
 *  - token set, header wrong → 401, and the comparison is constant-time over
 *    digests so the answer cannot be used to guess the token;
 *  - database unset       → 503, and the queue is untouched;
 *  - live SMS requested but credentials missing → 503 with the gate's own code,
 *    and NOTHING is claimed — otherwise the rows would be stuck `SENDING` in a
 *    log-only "delivery" that no operator would notice.
 *
 * The response never echoes the token, the database URL or a provider message
 * (D-114/D-124), and it is `no-store` because a delivery report is a fact about
 * a moment, not a cacheable resource.
 */

export const DISPATCH_TOKEN_ENV = 'NOTIFICATIONS_DISPATCH_TOKEN';

/** Rows per call. A bounded batch keeps one HTTP request inside its timeout. */
export const DISPATCH_BATCH_LIMIT = 50;

export interface NotificationDispatchDeps {
  /** Overrides the environment (tests). `null`/`''` means "not configured". */
  token?: string | null;
  getRepository?: () => CommerceRepository | null;
  channel?: SmsChannelResolution;
  now?: () => Date;
  limit?: number;
  transport?: SmsTransport;
}

interface DispatchResponseBody {
  ok: boolean;
  code?: string;
  message?: string;
  mode?: 'MOCK' | 'LIVE';
  report?: NotificationDispatchReport;
}

function jsonResponse(status: number, body: DispatchResponseBody): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}

/**
 * Constant-time bearer comparison.
 *
 * Both sides are hashed first: `timingSafeEqual` throws on length mismatch, and
 * a length check would itself leak the token's length. Hashing equalises the
 * lengths without weakening the comparison.
 */
function authorized(header: string | null, expected: string): boolean {
  const presented = (header ?? '').trim();
  if (!presented.toLowerCase().startsWith('bearer ')) {
    return false;
  }
  const supplied = presented.slice('bearer '.length).trim();
  const left = createHash('sha256').update(supplied, 'utf8').digest();
  const right = createHash('sha256').update(expected, 'utf8').digest();
  return timingSafeEqual(left, right);
}

export async function handleNotificationDispatchRequest(
  request: Request,
  deps: NotificationDispatchDeps = {},
): Promise<Response> {
  const expected =
    (deps.token === undefined
      ? (process.env[DISPATCH_TOKEN_ENV] ?? '')
      : (deps.token ?? '')
    ).trim() || null;

  if (expected === null) {
    return jsonResponse(503, {
      ok: false,
      code: 'DISPATCH_NOT_CONFIGURED',
      message:
        'توکنِ اجرای صفِ اطلاع‌رسانی تنظیم نشده است؛ هیچ اطلاع‌رسانی‌ای پردازش نمی‌شود.',
    });
  }

  if (!authorized(request.headers.get('authorization'), expected)) {
    return jsonResponse(401, {
      ok: false,
      code: 'UNAUTHORIZED',
      message: 'دسترسی به این مسیر مجاز نیست.',
    });
  }

  const repository = (deps.getRepository ?? getRepository)();
  if (repository === null) {
    return jsonResponse(503, {
      ok: false,
      code: 'DB_NOT_CONFIGURED',
      message: DB_NOT_CONFIGURED_MESSAGE,
    });
  }

  const resolution =
    deps.channel ??
    createSmsChannelFromEnv(process.env, deps.transport ?? defaultSmsTransport);
  if (!resolution.ok) {
    return jsonResponse(503, {
      ok: false,
      code: resolution.code,
      message: resolution.message,
    });
  }

  try {
    const report = await dispatchNotifications(repository, resolution.channel, {
      limit: deps.limit ?? DISPATCH_BATCH_LIMIT,
      now: deps.now,
    });
    return jsonResponse(200, { ok: true, mode: resolution.mode, report });
  } catch (error) {
    // Reported by NAME and CODE only: a driver message can echo a connection
    // string and a provider message can echo a recipient (D-114/D-124).
    const name = error instanceof Error ? error.name : 'UnknownError';
    const code =
      typeof error === 'object' && error !== null && 'code' in error
        ? String((error as { code: unknown }).code)
        : 'n/a';
    console.error('[commerce] notification dispatch failed', { name, code });
    return jsonResponse(500, {
      ok: false,
      code: 'UNEXPECTED',
      message: 'پردازش صفِ اطلاع‌رسانی با خطای غیرمنتظره روبه‌رو شد.',
    });
  }
}
