import { NextResponse, type NextRequest } from 'next/server';

import {
  ADMIN_LOGIN_PATH,
  ADMIN_REQUIRED_MESSAGE,
  ADMIN_SESSION_COOKIE,
  adminAuthProblemMessage,
  decideAdminAccess,
  readAdminAuthState,
} from '@/server/auth/admin-auth';

/**
 * D-172 Phase 4 — the merchant panel's gate.
 *
 * Next 16 calls this file `proxy.ts` (its predecessor was `middleware.ts`) and
 * runs it on the Node.js runtime, which is why the guard can use Node's crypto
 * directly. The RULES live in `@/server/auth/admin-auth` so they are unit tested
 * independently; this file only turns a decision into a response.
 *
 * It covers BOTH surfaces the panel exposes:
 *  - `/admin/**` pages (including the printable packing slip) → redirect to login;
 *  - `/admin/**` API routes such as the local media upload edge → 401 JSON, so a
 *    script fails loudly instead of receiving an HTML login page.
 *
 * When the guard itself is not configured the answer is a refusal, never an open
 * door (D-171 §2.2): pages land on the login screen with the configuration
 * problem stated, APIs answer 503.
 */

export default function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  const state = readAdminAuthState();
  const decision = decideAdminAccess({
    pathname,
    search,
    sessionToken: request.cookies.get(ADMIN_SESSION_COOKIE)?.value,
    state,
  });

  switch (decision.action) {
    case 'allow':
      return NextResponse.next();

    case 'login': {
      const url = request.nextUrl.clone();
      url.pathname = ADMIN_LOGIN_PATH;
      url.search = '';
      url.searchParams.set('next', decision.next);
      return NextResponse.redirect(url);
    }

    case 'misconfigured': {
      if (pathname.startsWith('/api/')) {
        return NextResponse.json(
          {
            ok: false,
            code: decision.problem === 'ABSENT' ? 'ADMIN_NOT_CONFIGURED' : 'ADMIN_CONFIG_INVALID',
            message: adminAuthProblemMessage(decision.problem),
          },
          { status: 503 },
        );
      }
      const url = request.nextUrl.clone();
      url.pathname = ADMIN_LOGIN_PATH;
      url.search = '';
      return NextResponse.redirect(url);
    }

    case 'unauthorized':
      return NextResponse.json(
        { ok: false, code: 'ADMIN_UNAUTHORIZED', message: ADMIN_REQUIRED_MESSAGE },
        { status: 401 },
      );
  }
}

export const config = {
  matcher: ['/admin', '/admin/:path*', '/api/admin', '/api/admin/:path*'],
};
