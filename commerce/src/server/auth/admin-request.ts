import { cookies } from 'next/headers';

import {
  ADMIN_SESSION_COOKIE,
  readAdminAuthState,
  verifyAdminSessionToken,
} from './admin-auth';

/**
 * D-172 Phase 4 — request-side glue for the admin guard.
 *
 * The rules live in `./admin-auth` (pure, unit tested); this module is the only
 * place that touches Next.js request/response state, and it is the one import
 * admin server actions need. Keeping the split means the guard's behaviour can
 * be tested without a request context.
 */

export interface AdminSession {
  username: string;
}

/** The verified operator for THIS request, or `null`. Never trusts the cookie blindly. */
export async function getAdminSession(): Promise<AdminSession | null> {
  const state = readAdminAuthState();
  if (!state.configured) {
    return null;
  }
  let token: string | undefined;
  try {
    token = (await cookies()).get(ADMIN_SESSION_COOKIE)?.value;
  } catch {
    // No request scope (a CLI call, or a unit test): there is no cookie jar, so
    // there is no session. This is an absence, not a hidden failure.
    return null;
  }
  if (!verifyAdminSessionToken(token, state.config)) {
    return null;
  }
  return { username: state.config.username };
}

export async function hasAdminSession(): Promise<boolean> {
  return (await getAdminSession()) !== null;
}

/** Sets the signed session cookie. Only callable from a Server Action / Route Handler. */
export async function setAdminSessionCookie(token: string, expiresAt: number): Promise<void> {
  const store = await cookies();
  store.set(ADMIN_SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    // Local runs are plain HTTP on loopback; a Secure cookie would never be sent
    // there. A production deployment terminates TLS, so the flag is on.
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    expires: new Date(expiresAt),
  });
}

export async function clearAdminSessionCookie(): Promise<void> {
  const store = await cookies();
  store.set(ADMIN_SESSION_COOKIE, '', {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 0,
  });
}
