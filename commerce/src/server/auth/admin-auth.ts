import { createHmac, randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';

/**
 * D-172 Phase 4 — the merchant panel's single-admin guard (pilot hardening).
 *
 * Scope is deliberately SMALL and stated:
 *  - ONE operator identity, supplied by the environment; there are no accounts,
 *    no roles, no password reset and no database table behind this. The fashion
 *    shop's pilot has exactly one merchant (the owner), so a multi-user identity
 *    model would add surface without adding a capability (D-172 §2).
 *  - auth is FAIL-CLOSED (D-171 §2.2): if `ADMIN_USERNAME`,
 *    `ADMIN_PASSWORD_HASH` or `ADMIN_SESSION_SECRET` is absent or malformed, the
 *    panel refuses every request with `ADMIN_NOT_CONFIGURED`/`ADMIN_INVALID`. No
 *    default credential, no "admin/admin" fallback, no unsigned cookie.
 *  - the session is a STATELESS signed cookie. Nothing is written to the
 *    database, so logging out cannot leave a stale session row behind and a
 *    restart does not sign anyone out.
 *
 * This module is pure (no Next.js imports, no I/O beyond Node crypto) so the
 * whole guard is unit tested offline: `admin-auth.test.ts`.
 *
 * WHAT THIS IS NOT: it is not the D-139 deployment authentication decision. It
 * is the minimum that makes loopback/pilot use defensible — it does not add
 * HTTPS, rate limiting at the edge, or multi-user audit. Those stay owner-gated.
 */

/* ------------------------------------------------------------------ config */

export const ADMIN_USERNAME_VAR = 'ADMIN_USERNAME';
export const ADMIN_PASSWORD_HASH_VAR = 'ADMIN_PASSWORD_HASH';
export const ADMIN_SESSION_SECRET_VAR = 'ADMIN_SESSION_SECRET';

/** Cookie name. Versioned so a future format change cannot be mistaken for this one. */
export const ADMIN_SESSION_COOKIE = 'commerce_admin_session';

/** Eight hours: one working day, then the operator signs in again. */
export const ADMIN_SESSION_TTL_MS = 8 * 60 * 60 * 1000;

/** A session secret shorter than this is refused rather than silently accepted. */
export const ADMIN_SESSION_SECRET_MIN_LENGTH = 32;

/** scrypt parameters, stored IN the hash so a future cost change stays verifiable. */
export const SCRYPT_N = 16_384;
export const SCRYPT_R = 8;
export const SCRYPT_P = 1;
export const SCRYPT_KEY_LENGTH = 32;
const SCRYPT_PREFIX = 'scrypt';

export interface AdminAuthConfig {
  username: string;
  /** `scrypt:N:r:p:saltHex:keyHex` (see `hashAdminPassword`). */
  passwordHash: string;
  sessionSecret: string;
}

export type AdminAuthProblem = 'ABSENT' | 'INVALID';

export type AdminAuthState =
  | { configured: true; config: AdminAuthConfig }
  | { configured: false; problem: AdminAuthProblem };

export const ADMIN_NOT_CONFIGURED_MESSAGE =
  'ورود به پنل مدیریت تنظیم نشده است: ADMIN_USERNAME، ADMIN_PASSWORD_HASH و ADMIN_SESSION_SECRET باید تنظیم شوند. تا آن زمان پنل هیچ درخواستی را نمی‌پذیرد.';

export const ADMIN_INVALID_CONFIG_MESSAGE =
  'تنظیمات ورود به پنل مدیریت معتبر نیست (هش گذرواژه یا کلید نشست). پنل تا اصلاح آن هیچ درخواستی را نمی‌پذیرد.';

/**
 * Deliberately COLON-delimited, not `$`-delimited.
 *
 * This value lives in `commerce/.env`, and BOTH layers that read that file expand
 * `$name` sequences in values (Docker Compose first, then Next.js's own env
 * loader, which writes the expanded value back over the correct one). A
 * `scrypt$16384$...` hash therefore arrives as `scrypt` — the guard would refuse,
 * correctly but confusingly. Colons carry no meaning to either expander.
 */
const PARSE_HASH_RE =
  /^scrypt:(\d{1,7}):(\d{1,3}):(\d{1,3}):([0-9a-f]{16,128}):([0-9a-f]{32,256})$/i;

/**
 * Reads the three variables and decides whether the guard can run at all.
 *
 * `ABSENT` (nothing set) and `INVALID` (set, but unusable) are reported
 * separately: the operator needs to know whether to configure or to fix.
 */
export function readAdminAuthState(env: NodeJS.ProcessEnv = process.env): AdminAuthState {
  const username = env[ADMIN_USERNAME_VAR]?.trim() ?? '';
  const passwordHash = env[ADMIN_PASSWORD_HASH_VAR]?.trim() ?? '';
  const sessionSecret = env[ADMIN_SESSION_SECRET_VAR]?.trim() ?? '';

  if (username === '' || passwordHash === '' || sessionSecret === '') {
    return { configured: false, problem: 'ABSENT' };
  }
  if (
    username.length > 64 ||
    !PARSE_HASH_RE.test(passwordHash) ||
    sessionSecret.length < ADMIN_SESSION_SECRET_MIN_LENGTH
  ) {
    return { configured: false, problem: 'INVALID' };
  }
  return { configured: true, config: { username, passwordHash, sessionSecret } };
}

export function adminAuthProblemMessage(problem: AdminAuthProblem): string {
  return problem === 'ABSENT' ? ADMIN_NOT_CONFIGURED_MESSAGE : ADMIN_INVALID_CONFIG_MESSAGE;
}

/* -------------------------------------------------------------- passwords */

function decodeHex(value: string): Buffer | null {
  if (value.length % 2 !== 0 || !/^[0-9a-f]+$/i.test(value)) {
    return null;
  }
  return Buffer.from(value, 'hex');
}

function safeEqual(left: Buffer, right: Buffer): boolean {
  return left.length === right.length && timingSafeEqual(left, right);
}

/**
 * `scrypt:N:r:p:salt:key` for the one operator password.
 *
 * scrypt is used (not a bare SHA) because the value lives in an environment
 * variable and environment variables leak into inspect output, crash dumps and
 * `printenv`; a slow KDF makes that leak expensive rather than free. Parameters
 * travel WITH the hash, so raising the cost later does not invalidate the
 * existing one.
 */
export function hashAdminPassword(password: string, salt: Buffer = randomBytes(16)): string {
  const key = scryptSync(password, salt, SCRYPT_KEY_LENGTH, {
    N: SCRYPT_N,
    r: SCRYPT_R,
    p: SCRYPT_P,
  });
  return [
    SCRYPT_PREFIX,
    SCRYPT_N,
    SCRYPT_R,
    SCRYPT_P,
    salt.toString('hex'),
    key.toString('hex'),
  ].join(':');
}

/**
 * Verifies a password against a stored hash. ANY malformed input answers
 * `false` — never an exception, never a pass.
 */
export function verifyAdminPassword(password: unknown, storedHash: string): boolean {
  if (typeof password !== 'string' || password.length === 0) {
    return false;
  }
  const match = PARSE_HASH_RE.exec(storedHash.trim());
  if (match === null) {
    return false;
  }
  const [, nRaw, rRaw, pRaw, saltHex, keyHex] = match;
  const salt = decodeHex(saltHex ?? '');
  const expected = decodeHex(keyHex ?? '');
  const n = Number(nRaw);
  const r = Number(rRaw);
  const p = Number(pRaw);
  if (salt === null || expected === null) {
    return false;
  }
  // The key length is FIXED, not read from the hash: scrypt's output is
  // prefix-stable, so a truncated hash would otherwise verify against a shorter
  // derived key. A hash that is not exactly the canonical length is refused.
  if (expected.length !== SCRYPT_KEY_LENGTH) {
    return false;
  }
  // Bound the cost parameters: an absurd N from a tampered hash would otherwise
  // let a malformed configuration stall the event loop.
  if (!Number.isInteger(n) || n < 1_024 || n > 1_048_576) {
    return false;
  }
  if (!Number.isInteger(r) || r < 1 || r > 32 || !Number.isInteger(p) || p < 1 || p > 16) {
    return false;
  }
  try {
    const actual = scryptSync(password, salt, expected.length, { N: n, r, p });
    return safeEqual(actual, expected);
  } catch {
    return false;
  }
}

/* --------------------------------------------------------------- sessions */

function base64url(value: Buffer): string {
  return value.toString('base64url');
}

function signSessionPayload(secret: string, payload: string): string {
  return base64url(createHmac('sha256', secret).update(payload).digest());
}

/**
 * `expiresAt.base64url(username).base64url(hmac)` where the HMAC covers the
 * version, the expiry AND the username. Binding the username means rotating the
 * operator name invalidates outstanding cookies instead of silently carrying the
 * old identity forward.
 */
export function createAdminSessionToken(
  config: AdminAuthConfig,
  options: { now?: number; ttlMs?: number } = {},
): { token: string; expiresAt: number } {
  const now = options.now ?? Date.now();
  const expiresAt = now + (options.ttlMs ?? ADMIN_SESSION_TTL_MS);
  const payload = `v1|${expiresAt}|${config.username}`;
  const token = [
    String(expiresAt),
    base64url(Buffer.from(config.username, 'utf8')),
    signSessionPayload(config.sessionSecret, payload),
  ].join('.');
  return { token, expiresAt };
}

export function verifyAdminSessionToken(
  token: unknown,
  config: AdminAuthConfig,
  now = Date.now(),
): boolean {
  if (typeof token !== 'string' || token.length === 0 || token.length > 4096) {
    return false;
  }
  const parts = token.split('.');
  if (parts.length !== 3) {
    return false;
  }
  const [expiresRaw, usernameRaw, signatureRaw] = parts as [string, string, string];
  if (!/^\d{1,16}$/.test(expiresRaw)) {
    return false;
  }
  const expiresAt = Number(expiresRaw);
  if (!Number.isFinite(expiresAt) || expiresAt <= now) {
    return false;
  }
  let username: string;
  try {
    username = Buffer.from(usernameRaw, 'base64url').toString('utf8');
  } catch {
    return false;
  }
  const expected = signSessionPayload(config.sessionSecret, `v1|${expiresAt}|${username}`);
  const expectedBuffer = Buffer.from(expected, 'utf8');
  const actualBuffer = Buffer.from(signatureRaw, 'utf8');
  if (!safeEqual(expectedBuffer, actualBuffer)) {
    return false;
  }
  // Compare identities through fixed-length digests: usernames of different
  // lengths must not leak through an early-exit comparison.
  const expectedName = Buffer.from(config.username, 'utf8');
  const actualName = Buffer.from(username, 'utf8');
  return safeEqual(
    Buffer.from(createHmac('sha256', config.sessionSecret).update(expectedName).digest()),
    Buffer.from(createHmac('sha256', config.sessionSecret).update(actualName).digest()),
  );
}

/* ------------------------------------------------------------------ access */

export type AdminAccessDecision =
  | { action: 'allow' }
  | { action: 'login'; next: string }
  | { action: 'unauthorized' }
  | { action: 'misconfigured'; problem: AdminAuthProblem };

/** The one path that must work BEFORE a session exists. */
export const ADMIN_LOGIN_PATH = '/admin/login';

export const ADMIN_REQUIRED_MESSAGE = 'برای دسترسی به پنل مدیریت ابتدا وارد شوید.';
export const ADMIN_SESSION_EXPIRED_MESSAGE = 'نشست شما منقضی شده است؛ دوباره وارد شوید.';

export function isAdminPath(pathname: string): boolean {
  return (
    pathname === '/admin' ||
    pathname.startsWith('/admin/') ||
    pathname === '/api/admin' ||
    pathname.startsWith('/api/admin/')
  );
}

/**
 * The ONE access rule, shared by the proxy (which enforces it) and the tests
 * (which state it). API answers 401 so a fetch fails loudly; a page redirects to
 * the login screen and remembers where it was going.
 */
export function decideAdminAccess(input: {
  pathname: string;
  search?: string;
  sessionToken?: string | undefined;
  state: AdminAuthState;
  now?: number;
}): AdminAccessDecision {
  const pathname = input.pathname;
  if (!isAdminPath(pathname)) {
    return { action: 'allow' };
  }
  if (pathname === ADMIN_LOGIN_PATH) {
    return { action: 'allow' };
  }

  const isApi = pathname.startsWith('/api/');
  if (!input.state.configured) {
    // The proxy renders this as a 503 for APIs and a login screen that states the
    // problem for pages: "misconfigured" is not the same answer as "not signed in".
    return { action: 'misconfigured', problem: input.state.problem };
  }
  if (verifyAdminSessionToken(input.sessionToken, input.state.config, input.now ?? Date.now())) {
    return { action: 'allow' };
  }
  if (isApi) {
    return { action: 'unauthorized' };
  }
  const search = input.search !== undefined && input.search !== '' ? input.search : '';
  return { action: 'login', next: `${pathname}${search}` };
}

/**
 * Only same-site absolute paths are accepted as a post-login destination.
 * `//evil.test` and `https://evil.test` are refused — an open redirect in a
 * login screen is a phishing primitive, not a convenience.
 */
export function safeAdminRedirect(next: unknown): string {
  if (typeof next !== 'string') {
    return '/admin';
  }
  const value = next.trim();
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return '/admin';
  }
  if (value === ADMIN_LOGIN_PATH || value.startsWith(`${ADMIN_LOGIN_PATH}?`)) {
    return '/admin';
  }
  if (!value.startsWith('/admin') && !value.startsWith('/api/admin')) {
    return '/admin';
  }
  return value;
}

/* ---------------------------------------------------------------- throttle */

export interface LoginThrottle {
  /** Records a failed attempt; returns the number of failures in the window. */
  recordFailure(now?: number): number;
  isBlocked(now?: number): boolean;
  reset(): void;
}

/**
 * A tiny in-process fixed-window limiter for the login form.
 *
 * It is NOT a substitute for edge rate limiting (see the module header): with
 * several app instances each one keeps its own window. It exists so a single
 * brute-force loop over loopback cannot guess freely, and it is deliberately
 * memory-only — a restart forgets it, which is acceptable for one operator.
 */
export function createLoginThrottle(options: {
  maxFailures?: number;
  windowMs?: number;
} = {}): LoginThrottle {
  const maxFailures = options.maxFailures ?? 8;
  const windowMs = options.windowMs ?? 5 * 60 * 1000;
  let failures: number[] = [];

  function prune(now: number): void {
    failures = failures.filter((at) => now - at < windowMs);
  }

  return {
    recordFailure(now = Date.now()) {
      prune(now);
      failures.push(now);
      return failures.length;
    },
    isBlocked(now = Date.now()) {
      prune(now);
      return failures.length >= maxFailures;
    },
    reset() {
      failures = [];
    },
  };
}

/** The one answer for a wrong username AND a wrong password (no enumeration). */
export const INVALID_CREDENTIALS_MESSAGE = 'نام کاربری یا گذرواژه نادرست است.';

export const LOGIN_THROTTLED_MESSAGE =
  'تلاش‌های ناموفق زیاد بوده است؛ چند دقیقه بعد دوباره امتحان کنید.';
