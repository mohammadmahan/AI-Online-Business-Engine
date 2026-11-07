import { hasAdminSession } from '@/server/auth/admin-request';
import { handleMediaUploadRequest } from '@/server/media/upload';

/**
 * D-172 §2.1 / G-5 — LOCAL-ONLY media upload edge.
 *
 * A shim, like the payment and notification routes: every rule lives in
 * `@/server/media/upload`, where it is exercised offline with an injected
 * adapter. This route only binds it to HTTP.
 *
 * `runtime = 'nodejs'` because the adapter uses the S3 SDK and Node's crypto.
 * `dynamic = 'force-dynamic'` because the guard reads the environment at CALL
 * time; a build has no media configuration and must not freeze that answer.
 *
 * No GET export: an upload is a state change, so Next answers other methods with
 * 405 and an image can never be "uploaded" by following a link.
 *
 * AUTHENTICATION (Phase 4): the proxy already refuses anonymous `/api/admin/**`
 * requests, and the session check below states the same requirement at the
 * handler — an upload is a write, and the route should be safe even if its path
 * is ever excluded from the proxy matcher.
 *
 * The OTHER boundary is unchanged: `MEDIA_LOCAL_UPLOAD_ENABLED` must be exactly
 * `true` AND the process must not be a production build, so the local MinIO
 * adapter stays loopback-only.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request): Promise<Response> {
  if (!(await hasAdminSession())) {
    return Response.json(
      { ok: false, code: 'ADMIN_UNAUTHORIZED', message: 'برای بارگذاری تصویر ابتدا وارد شوید.' },
      { status: 401 },
    );
  }
  return handleMediaUploadRequest(request);
}
