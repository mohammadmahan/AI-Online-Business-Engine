import { resolveLocalMediaDirectory } from '@/server/media';
import { readLocalMediaFile } from '@/server/media/serve';

/**
 * D-172 §2.1 — `GET /media/…`: the public read edge of the local media store.
 *
 * This route exists instead of writing into `public/` on purpose: Next treats
 * `public/` as BUILD INPUT, so an image uploaded while the server is running
 * would either be missing (production) or only accidentally visible (dev). A
 * route reads `MEDIA_LOCAL_DIR` at request time in both modes and keeps the
 * store outside the build entirely.
 *
 * It is PUBLIC (a customer's browser must load a product photo without a
 * session), but it is read-only by construction: there is no POST, the writer is
 * the authenticated `POST /api/admin/media`, and every stored key is a content
 * hash. `serve.ts` owns the path/extension restrictions and answers 404 for
 * everything else, including traversal attempts.
 *
 * `force-dynamic` because the directory comes from the environment at call time;
 * a build must not freeze which store it reads.
 */
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(
  _request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path: segments } = await context.params;
  const root = resolveLocalMediaDirectory();
  if (root === null) {
    return new Response(null, { status: 404 });
  }

  const file = await readLocalMediaFile(root, segments);
  if (file === null) {
    return new Response(null, { status: 404 });
  }

  return new Response(new Uint8Array(file.bytes), {
    status: 200,
    headers: {
      'content-type': file.contentType,
      'content-length': String(file.byteLength),
      // Content-addressed: the bytes behind a URL can never change.
      'cache-control': 'public, max-age=31536000, immutable',
      'x-content-type-options': 'nosniff',
    },
  });
}
