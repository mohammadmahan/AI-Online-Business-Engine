#!/usr/bin/env node
/**
 * D-172 §6.2 / Phase 6 B5 — the LOCAL notification dispatch scheduler.
 *
 * `POST /api/internal/notifications/dispatch` drains ONE bounded batch of the
 * durable outbox and reports what happened. Nothing calls it on a timer, so the
 * queue only moves when an operator (or this runner) asks. This script is that
 * timer, for a development machine or the local compose environment — it is not
 * a production worker and does not pretend to be one (B5's operational half
 * stays owner-gated with the rest of the cutover items).
 *
 * Contract, deliberately the same fail-closed shape as the endpoint it calls:
 *
 *  - NO TOKEN, NO REQUEST. `NOTIFICATIONS_DISPATCH_TOKEN` unset/blank is a
 *    refusal (exit 2) BEFORE anything is sent; there is no unauthenticated mode
 *    and no way to run "just this once" without it.
 *  - LOOPBACK ONLY. `NOTIFICATIONS_DISPATCH_URL` must be an absolute http(s) URL
 *    on 127.0.0.1 / localhost / ::1, with no userinfo. A runner aimed at a shared
 *    host would deliver a real customer's notification from a developer machine,
 *    so the target is validated rather than trusted, and there is no override.
 *  - AUTH REFUSAL IS FATAL (exit 3). A wrong or rotated token never fixes itself;
 *    retrying it would only hammer the endpoint. Configuration refusals from the
 *    endpoint (`DISPATCH_NOT_CONFIGURED`, `DB_NOT_CONFIGURED`,
 *    `SMS_LIVE_MODE_MISSING_CREDENTIAL`) are treated the same way.
 *  - TRANSIENT FAILURES BACK OFF AND STOP (exit 4). Network errors and 5xx
 *    answers retry with 250ms → 500ms → 1s → 2s, then give up so a supervisor
 *    sees a non-zero exit instead of an endless quiet loop.
 *  - EMPTY BATCHES ARE NORMAL. `claimed=0` sleeps a full interval; a non-empty
 *    batch is drained again immediately (bounded per tick) so a backlog empties
 *    without waiting a whole interval between batches.
 *  - NOTHING SECRET IS LOGGED. Only counts, the mode, HTTP status and the
 *    endpoint's own error CODE. The token and any URL userinfo are never printed.
 *
 * Usage:
 *   npm run scheduler:notifications              # interval loop (default 60s)
 *   npm run scheduler:notifications -- --once    # one pass, for cron
 *   NOTIFICATIONS_DISPATCH_INTERVAL_MS=5000 npm run scheduler:notifications
 *
 * Exit codes: 0 ok/stopped · 2 configuration refusal · 3 authentication or
 * endpoint-configuration refusal · 4 transient failures exhausted.
 */
import { setTimeout as delay } from 'node:timers/promises';

const TOKEN_ENV = 'NOTIFICATIONS_DISPATCH_TOKEN';
const URL_ENV = 'NOTIFICATIONS_DISPATCH_URL';
const INTERVAL_ENV = 'NOTIFICATIONS_DISPATCH_INTERVAL_MS';
const TIMEOUT_ENV = 'NOTIFICATIONS_DISPATCH_HTTP_TIMEOUT_MS';

/** The local dev server's own origin; `next dev` defaults to this port. */
const DEFAULT_URL = 'http://127.0.0.1:3000/api/internal/notifications/dispatch';
const DEFAULT_INTERVAL_MS = 60_000;
const MIN_INTERVAL_MS = 1_000;
const MAX_INTERVAL_MS = 3_600_000;
const DEFAULT_TIMEOUT_MS = 15_000;
const MIN_TIMEOUT_MS = 500;
const MAX_TIMEOUT_MS = 120_000;

const BACKOFF_BASE_MS = 250;
const BACKOFF_MAX_MS = 30_000;
const MAX_CONSECUTIVE_FAILURES = 5;
const MAX_BATCHES_PER_TICK = 5;

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);

const EXIT_OK = 0;
const EXIT_CONFIG = 2;
const EXIT_REFUSED = 3;
const EXIT_UNAVAILABLE = 4;

/** Endpoint refusals that mean "the configuration is incomplete", not "retry". */
const FATAL_CODES = new Set([
  'DISPATCH_NOT_CONFIGURED',
  'DB_NOT_CONFIGURED',
  'SMS_LIVE_MODE_MISSING_CREDENTIAL',
]);

/**
 * A refusal is a decision, not an error to shrug at: report the reason by name
 * (never the token, never a URL's userinfo) and exit with a distinct code.
 */
function fatal(code, message) {
  console.error(`[commerce] dispatch scheduler refused — ${message}`);
  process.exit(code);
}

const args = process.argv.slice(2);
const unknown = args.filter((arg) => arg !== '--once' && arg !== '--watch');
if (unknown.length > 0) {
  fatal(EXIT_CONFIG, `unknown argument(s): ${unknown.join(', ')} — use --once or --watch`);
}
const once = args.includes('--once');

const token = (process.env[TOKEN_ENV] ?? '').trim();
if (token === '') {
  fatal(
    EXIT_CONFIG,
    `${TOKEN_ENV} is not set — the operator endpoint is called with a bearer token or not at all; nothing was sent`,
  );
}

let target;
try {
  target = new URL((process.env[URL_ENV] ?? DEFAULT_URL).trim());
} catch {
  fatal(EXIT_CONFIG, `${URL_ENV} is not a parseable absolute URL`);
}

if (target.protocol !== 'http:' && target.protocol !== 'https:') {
  fatal(EXIT_CONFIG, `${URL_ENV} must be http(s)`);
}
if (!LOOPBACK_HOSTS.has(target.hostname)) {
  fatal(
    EXIT_CONFIG,
    `endpoint host "${target.hostname}" is not loopback — this scheduler is local/mock only ` +
      'and never delivers a real notification (D-045/D-139)',
  );
}
if (target.username !== '' || target.password !== '') {
  fatal(EXIT_CONFIG, `${URL_ENV} carries credentials in the URL — the bearer token is the only credential this runner sends`);
}

/** Bounded integer env parsing: a malformed value is refused, never guessed. */
function integerFromEnv(name, fallback, min, max) {
  const raw = process.env[name]?.trim();
  if (raw === undefined || raw === '') {
    return fallback;
  }
  if (!/^\d+$/.test(raw)) {
    fatal(EXIT_CONFIG, `${name} must be a whole number of milliseconds (got "${raw}")`);
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    fatal(EXIT_CONFIG, `${name} must be between ${min} and ${max} ms`);
  }
  return value;
}

const intervalMs = integerFromEnv(INTERVAL_ENV, DEFAULT_INTERVAL_MS, MIN_INTERVAL_MS, MAX_INTERVAL_MS);
const timeoutMs = integerFromEnv(TIMEOUT_ENV, DEFAULT_TIMEOUT_MS, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS);

const controller = new AbortController();
let stopping = false;

function stop(signal) {
  if (stopping) {
    return;
  }
  stopping = true;
  controller.abort();
  console.log(`[commerce] dispatch scheduler: ${signal} received — stopping after the current step`);
}

process.on('SIGINT', () => stop('SIGINT'));
process.on('SIGTERM', () => stop('SIGTERM'));

async function sleep(ms) {
  if (stopping) {
    return;
  }
  try {
    // Abortable sleep: Ctrl-C must not wait out a 60s interval.
    await delay(ms, undefined, { signal: controller.signal });
  } catch {
    /* aborted by a signal; the loop condition ends the run */
  }
}

function describe(report) {
  const value = report ?? {};
  return [
    `claimed=${value.claimed ?? 0}`,
    `sent=${value.sent ?? 0}`,
    `retried=${value.retried ?? 0}`,
    `failed=${value.failed ?? 0}`,
    `skipped=${value.skipped ?? 0}`,
  ].join(' ');
}

const endpoint = target.toString();
console.log(
  `[commerce] dispatch scheduler: target=${target.origin}${target.pathname} mode=${once ? 'once' : `watch/${intervalMs}ms`}`,
);

let consecutiveFailures = 0;

while (!stopping) {
  let batches = 0;
  let claimedThisTick = 0;
  let lastAttemptSucceeded = false;

  while (!stopping && batches < MAX_BATCHES_PER_TICK) {
    batches += 1;

    let response;
    try {
      response = await fetch(endpoint, {
        method: 'POST',
        headers: { authorization: `Bearer ${token}`, accept: 'application/json' },
        cache: 'no-store',
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      const name = error instanceof Error ? error.name : 'Error';
      consecutiveFailures += 1;
      console.error(
        `[commerce] dispatch scheduler: request failed (${name}) — attempt ${consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES}`,
      );
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        fatal(
          EXIT_UNAVAILABLE,
          `endpoint unreachable after ${consecutiveFailures} attempts; this run claimed nothing`,
        );
      }
      await sleep(Math.min(BACKOFF_BASE_MS * 2 ** (consecutiveFailures - 1), BACKOFF_MAX_MS));
      break;
    }

    let body = {};
    try {
      body = await response.json();
    } catch {
      body = {};
    }

    if (response.ok && body.ok === true) {
      consecutiveFailures = 0;
      lastAttemptSucceeded = true;
      const report = body.report ?? {};
      claimedThisTick += Number(report.claimed ?? 0);
      console.log(`[commerce] dispatch scheduler: run ok (${body.mode ?? 'UNKNOWN'}) ${describe(report)}`);
      if (once) {
        console.log('[commerce] dispatch scheduler: --once complete');
        process.exit(EXIT_OK);
      }
      if (claimedThisTick === 0) {
        // Idle: nothing was due, so wait the whole interval rather than spin.
        break;
      }
      continue;
    }

    const code = typeof body.code === 'string' ? body.code : null;
    if (response.status === 401 || response.status === 403) {
      fatal(
        EXIT_REFUSED,
        `the endpoint refused the bearer token (HTTP ${response.status}) — fix ${TOKEN_ENV}; retrying cannot help`,
      );
    }
    if (code !== null && FATAL_CODES.has(code)) {
      fatal(
        EXIT_REFUSED,
        `the endpoint reports "${code}" (HTTP ${response.status}) — configuration is incomplete and nothing was claimed`,
      );
    }

    consecutiveFailures += 1;
    console.error(
      `[commerce] dispatch scheduler: endpoint error (HTTP ${response.status}${code === null ? '' : `, ${code}`}) ` +
        `— attempt ${consecutiveFailures}/${MAX_CONSECUTIVE_FAILURES}`,
    );
    if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
      fatal(EXIT_UNAVAILABLE, `endpoint still failing after ${consecutiveFailures} attempts`);
    }
    await sleep(Math.min(BACKOFF_BASE_MS * 2 ** (consecutiveFailures - 1), BACKOFF_MAX_MS));
    break;
  }

  if (once && lastAttemptSucceeded === false) {
    // A failed single pass retries (with backoff) instead of reporting success.
    continue;
  }
  if (consecutiveFailures === 0 && claimedThisTick > 0) {
    // A drained backlog may still have rows; go again without idling.
    continue;
  }
  await sleep(intervalMs);
}

console.log('[commerce] dispatch scheduler: stopped');
process.exit(EXIT_OK);
