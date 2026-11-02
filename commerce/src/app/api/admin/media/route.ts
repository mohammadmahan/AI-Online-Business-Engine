import { handleMediaUploadRequest } from '@/server/media/upload';

/**
 * D-172 §2.1 / G-5 — LOCAL-ONLY media upload edge.
 *
 * A three-line shim, like the payment and notification routes: every rule lives
 * in `@/server/media/upload`, where it is exercised offline with an injected
 * adapter. This route only binds it to HTTP.
 *
 * `runtime = 'nodejs'` because the adapter uses the S3 SDK and Node's crypto.
 * `dynamic = 'force-dynamic'` because the guard reads the environment at CALL
 * time; a build has no media configuration and must not freeze that answer.
 *
 * No GET export: an upload is a state change, so Next answers other methods with
 * 405 and an image can never be "uploaded" by following a link.
 *
 * NOT AUTHENTICATED. The Commerce admin surface has no session/role guard; the
 * only safe boundary is a loopback-bound process. Do not deploy this route.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request): Promise<Response> {
  return handleMediaUploadRequest(request);
}
