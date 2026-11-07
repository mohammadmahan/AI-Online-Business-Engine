'use server';

import { createHash, timingSafeEqual } from 'node:crypto';

import type { Route } from 'next';
import { redirect } from 'next/navigation';

import {
  ADMIN_LOGIN_PATH,
  INVALID_CREDENTIALS_MESSAGE,
  LOGIN_THROTTLED_MESSAGE,
  adminAuthProblemMessage,
  createAdminSessionToken,
  createLoginThrottle,
  readAdminAuthState,
  safeAdminRedirect,
  verifyAdminPassword,
} from '../auth/admin-auth';
import { clearAdminSessionCookie, setAdminSessionCookie } from '../auth/admin-request';

/**
 * D-172 Phase 4 — sign in / sign out for the single merchant identity.
 *
 * The credentials are checked HERE (server side) and the only thing that leaves
 * is an HttpOnly signed cookie. Failure answers one message for both a wrong
 * username and a wrong password, so the form cannot be used to enumerate the
 * operator name.
 *
 * The failure counter is per process and memory-only (see `createLoginThrottle`);
 * it slows a loop from one connection without pretending to be edge rate
 * limiting.
 */

export interface AdminLoginInput {
  username: unknown;
  password: unknown;
  /** Where the proxy was taking the operator before it asked for a sign-in. */
  next?: unknown;
}

export type AdminLoginResult = { ok: true } | { ok: false; message: string };

const throttle = createLoginThrottle();

function digest(value: string): Buffer {
  return createHash('sha256').update(value, 'utf8').digest();
}

/** Constant-time identity check: unequal lengths must not answer faster. */
function sameIdentity(left: string, right: string): boolean {
  return timingSafeEqual(digest(left), digest(right));
}

export async function loginAction(input: AdminLoginInput): Promise<AdminLoginResult> {
  const state = readAdminAuthState();
  if (!state.configured) {
    return { ok: false, message: adminAuthProblemMessage(state.problem) };
  }
  if (throttle.isBlocked()) {
    return { ok: false, message: LOGIN_THROTTLED_MESSAGE };
  }

  const username = typeof input.username === 'string' ? input.username.trim() : '';
  const password = typeof input.password === 'string' ? input.password : '';
  if (username === '' || password === '') {
    return { ok: false, message: 'نام کاربری و گذرواژه را وارد کنید.' };
  }

  // Both checks always run: an unknown username must cost the same as a wrong
  // password for the operator's configured identity.
  const passwordMatches = verifyAdminPassword(password, state.config.passwordHash);
  const usernameMatches = sameIdentity(username, state.config.username);

  if (!usernameMatches || !passwordMatches) {
    throttle.recordFailure();
    return { ok: false, message: INVALID_CREDENTIALS_MESSAGE };
  }

  throttle.reset();
  const { token, expiresAt } = createAdminSessionToken(state.config);
  await setAdminSessionCookie(token, expiresAt);
  // Validated to be a same-site /admin path (see `safeAdminRedirect`); the cast
  // only satisfies Next's generated route union, which cannot know a runtime value.
  redirect(safeAdminRedirect(input.next) as Route);
}

export async function logoutAction(): Promise<void> {
  await clearAdminSessionCookie();
  redirect(ADMIN_LOGIN_PATH);
}
