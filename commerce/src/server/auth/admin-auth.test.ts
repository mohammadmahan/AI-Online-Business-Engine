import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { describe, it } from 'node:test';

import {
  ADMIN_LOGIN_PATH,
  ADMIN_SESSION_COOKIE,
  ADMIN_SESSION_TTL_MS,
  adminAuthProblemMessage,
  createAdminSessionToken,
  createLoginThrottle,
  decideAdminAccess,
  hashAdminPassword,
  readAdminAuthState,
  safeAdminRedirect,
  verifyAdminPassword,
  verifyAdminSessionToken,
  type AdminAuthConfig,
} from '@/server/auth/admin-auth';

/**
 * D-172 Phase 4 — the admin guard's whole rule surface, offline.
 *
 * The properties that matter for a pilot are stated as tests: absent/malformed
 * configuration REFUSES (never a default credential), a session is signed,
 * expiring and bound to the operator name, and the access decision separates a
 * page redirect from an API 401.
 */

const PASSWORD = 'pilot-only-password';
const SECRET = 'a'.repeat(48);

function config(overrides: Partial<AdminAuthConfig> = {}): AdminAuthConfig {
  return {
    username: 'owner',
    passwordHash: hashAdminPassword(PASSWORD, Buffer.from('00112233445566778899aabbccddeeff', 'hex')),
    sessionSecret: SECRET,
    ...overrides,
  };
}

function env(values: Record<string, string | undefined>): NodeJS.ProcessEnv {
  return values as NodeJS.ProcessEnv;
}

describe('admin auth — configuration is fail-closed', () => {
  it('reports ABSENT when any of the three variables is missing', () => {
    assert.deepEqual(readAdminAuthState(env({})), { configured: false, problem: 'ABSENT' });
    assert.deepEqual(
      readAdminAuthState(env({ ADMIN_USERNAME: 'owner', ADMIN_PASSWORD_HASH: config().passwordHash })),
      { configured: false, problem: 'ABSENT' },
    );
    assert.deepEqual(
      readAdminAuthState(env({ ADMIN_USERNAME: 'owner', ADMIN_SESSION_SECRET: SECRET })),
      { configured: false, problem: 'ABSENT' },
    );
  });

  it('reports INVALID for a short session secret, a bad hash format or a long username', () => {
    const passwordHash = config().passwordHash;
    assert.equal(
      readAdminAuthState(
        env({ ADMIN_USERNAME: 'owner', ADMIN_PASSWORD_HASH: passwordHash, ADMIN_SESSION_SECRET: 'short' }),
      ).configured,
      false,
    );
    assert.deepEqual(
      readAdminAuthState(
        env({ ADMIN_USERNAME: 'owner', ADMIN_PASSWORD_HASH: 'hunter2', ADMIN_SESSION_SECRET: SECRET }),
      ),
      { configured: false, problem: 'INVALID' },
    );
    assert.deepEqual(
      readAdminAuthState(
        env({
          ADMIN_USERNAME: 'x'.repeat(65),
          ADMIN_PASSWORD_HASH: passwordHash,
          ADMIN_SESSION_SECRET: SECRET,
        }),
      ),
      { configured: false, problem: 'INVALID' },
    );
  });

  it('accepts a fully formed configuration and trims the username', () => {
    const state = readAdminAuthState(
      env({
        ADMIN_USERNAME: '  owner ',
        ADMIN_PASSWORD_HASH: config().passwordHash,
        ADMIN_SESSION_SECRET: SECRET,
      }),
    );
    assert.equal(state.configured, true);
    assert.equal(state.configured ? state.config.username : null, 'owner');
  });

  it('names the variables to set but never echoes a configured value', () => {
    const absent = adminAuthProblemMessage('ABSENT');
    // Naming the variables is the point: the operator has to know WHAT to set.
    assert.match(absent, /ADMIN_USERNAME/);
    assert.match(absent, /ADMIN_PASSWORD_HASH/);
    assert.match(absent, /تنظیم نشده/);
    // A configured secret or hash must never travel through a user-facing string.
    assert.doesNotMatch(absent, /scrypt\$/);
    assert.doesNotMatch(adminAuthProblemMessage('INVALID'), /scrypt\$/);
    assert.doesNotMatch(adminAuthProblemMessage('INVALID'), new RegExp(SECRET));
  });
});

describe('admin auth — password hashing', () => {
  it('verifies the password it hashed and rejects everything else', () => {
    const stored = hashAdminPassword(PASSWORD);
    assert.equal(verifyAdminPassword(PASSWORD, stored), true);
    assert.equal(verifyAdminPassword(`${PASSWORD} `, stored), false);
    assert.equal(verifyAdminPassword('', stored), false);
    assert.equal(verifyAdminPassword(undefined, stored), false);
  });

  it('never accepts a malformed or tampered hash', () => {
    const stored = hashAdminPassword(PASSWORD);
    assert.equal(verifyAdminPassword(PASSWORD, 'hunter2'), false);
    assert.equal(verifyAdminPassword(PASSWORD, stored.replace('scrypt', 'sha256')), false);
    assert.equal(verifyAdminPassword(PASSWORD, stored.slice(0, -2)), false);
    // The key half is what authenticates: altering one nibble must fail even
    // though the format is still valid.
    const [prefix, n, r, p, salt, key] = stored.split(':') as [string, string, string, string, string, string];
    const flipped = key.startsWith('0') ? `1${key.slice(1)}` : `0${key.slice(1)}`;
    assert.equal(verifyAdminPassword(PASSWORD, [prefix, n, r, p, salt, flipped].join(':')), false);
  });

  it('refuses absurd cost parameters instead of stalling', () => {
    const stored = hashAdminPassword(PASSWORD);
    const [, , r, p, salt, key] = stored.split(':') as [string, string, string, string, string, string];
    assert.equal(verifyAdminPassword(PASSWORD, ['scrypt', '99999999', r, p, salt, key].join(':')), false);
  });

  it('agrees with scripts/hash-admin-password.mjs (one hash format, two producers)', () => {
    const script = spawnSync(
      process.execPath,
      ['scripts/hash-admin-password.mjs', 'script-produced-password'],
      { cwd: process.cwd(), encoding: 'utf8' },
    );
    assert.equal(script.status, 0, script.stderr);
    const hash = script.stdout.trim();
    assert.equal(verifyAdminPassword('script-produced-password', hash), true);
    assert.equal(verifyAdminPassword('another-password', hash), false);
  });
});

describe('admin auth — signed session cookie', () => {
  it('round-trips a token and rejects it once expired', () => {
    const admin = config();
    const now = 1_700_000_000_000;
    const { token, expiresAt } = createAdminSessionToken(admin, { now });
    assert.equal(expiresAt, now + ADMIN_SESSION_TTL_MS);
    assert.equal(verifyAdminSessionToken(token, admin, now), true);
    assert.equal(verifyAdminSessionToken(token, admin, now + 1), true);
    assert.equal(verifyAdminSessionToken(token, admin, expiresAt), false);
  });

  it('rejects tampering, a different secret and a rotated username', () => {
    const admin = config();
    const { token } = createAdminSessionToken(admin, { now: 1_700_000_000_000 });
    const [expiry, username, signature] = token.split('.') as [string, string, string];

    assert.equal(verifyAdminSessionToken(`${expiry}.${username}.${signature.slice(0, -2)}aa`, admin), false);
    assert.equal(verifyAdminSessionToken(`${Number(expiry) + 1}.${username}.${signature}`, admin), false);
    assert.equal(verifyAdminSessionToken(token, { ...admin, sessionSecret: 'b'.repeat(48) }), false);
    assert.equal(verifyAdminSessionToken(token, { ...admin, username: 'other' }), false);
    assert.equal(verifyAdminSessionToken(`1.${username}.${signature}`, admin, 10), false);
  });

  it('rejects structurally invalid tokens without throwing', () => {
    const admin = config();
    for (const value of [undefined, null, '', 'x', 'a.b', 'notanumber.a.b', '123.a.b', 42]) {
      assert.equal(verifyAdminSessionToken(value, admin), false, String(value));
    }
  });
});

describe('admin auth — access decisions', () => {
  const admin = config();
  const configured = { configured: true as const, config: admin };
  const absent = { configured: false as const, problem: 'ABSENT' as const };

  it('leaves the storefront and the login screen alone', () => {
    for (const pathname of ['/', '/catalog', '/checkout', '/products/x', '/api/payments/mock/callback']) {
      assert.deepEqual(decideAdminAccess({ pathname, state: absent }), { action: 'allow' });
    }
    assert.deepEqual(decideAdminAccess({ pathname: ADMIN_LOGIN_PATH, state: absent }), {
      action: 'allow',
    });
  });

  it('redirects an anonymous page request to login and remembers the destination', () => {
    assert.deepEqual(
      decideAdminAccess({ pathname: '/admin/orders', search: '?page=2', state: configured }),
      { action: 'login', next: '/admin/orders?page=2' },
    );
  });

  it('answers 401-shaped decisions for API routes', () => {
    assert.deepEqual(
      decideAdminAccess({ pathname: '/api/admin/media', state: configured }),
      { action: 'unauthorized' },
    );
    assert.deepEqual(
      decideAdminAccess({ pathname: '/api/admin/media', state: absent }),
      { action: 'misconfigured', problem: 'ABSENT' },
    );
  });

  it('allows a valid session and refuses an expired or foreign one', () => {
    const now = 1_700_000_000_000;
    const { token } = createAdminSessionToken(admin, { now });
    assert.deepEqual(
      decideAdminAccess({ pathname: '/admin', sessionToken: token, state: configured, now }),
      { action: 'allow' },
    );
    assert.equal(
      decideAdminAccess({
        pathname: '/admin',
        sessionToken: token,
        state: configured,
        now: now + ADMIN_SESSION_TTL_MS + 1,
      }).action,
      'login',
    );
  });

  it('states the configuration problem for pages rather than showing a login form', () => {
    assert.deepEqual(decideAdminAccess({ pathname: '/admin', state: absent }), {
      action: 'misconfigured',
      problem: 'ABSENT',
    });
  });

  it('names the cookie it reads', () => {
    assert.equal(ADMIN_SESSION_COOKIE, 'commerce_admin_session');
  });
});

describe('admin auth — post-login redirect is never open', () => {
  it('keeps only same-site admin paths', () => {
    assert.equal(safeAdminRedirect('/admin/orders'), '/admin/orders');
    assert.equal(safeAdminRedirect('/admin'), '/admin');
    assert.equal(safeAdminRedirect('//evil.test'), '/admin');
    assert.equal(safeAdminRedirect('https://evil.test/admin'), '/admin');
    assert.equal(safeAdminRedirect('/\\evil.test'), '/admin');
    assert.equal(safeAdminRedirect('/admin/login'), '/admin');
    assert.equal(safeAdminRedirect('/catalog'), '/admin');
    assert.equal(safeAdminRedirect(undefined), '/admin');
    assert.equal(safeAdminRedirect(7), '/admin');
  });
});

describe('admin auth — login throttle', () => {
  it('blocks after the configured number of failures inside the window and forgets on reset', () => {
    const throttle = createLoginThrottle({ maxFailures: 3, windowMs: 1_000 });
    assert.equal(throttle.isBlocked(0), false);
    throttle.recordFailure(0);
    throttle.recordFailure(10);
    assert.equal(throttle.isBlocked(20), false);
    throttle.recordFailure(30);
    assert.equal(throttle.isBlocked(40), true);
    // The window is fixed: all three failures age out together.
    assert.equal(throttle.isBlocked(1_100), false);
    throttle.recordFailure(2_000);
    throttle.reset();
    assert.equal(throttle.isBlocked(2_010), false);
  });
});
