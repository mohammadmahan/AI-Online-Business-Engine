/**
 * D-172 §2.1 / G-5 — `POST /api/admin/media` (LOCAL ONLY).
 *
 * SECURITY BOUNDARY — this is NOT authentication. The Commerce admin surface has
 * no session/role guard, so the only safe deployment of this endpoint is a
 * process bound to loopback. The handler adds defence in depth:
 *
 *  - `NODE_ENV=production` and `MEDIA_LOCAL_UPLOAD_ENABLED!=="true"` answer 404;
 *  - the adapter only resolves for a loopback MinIO endpoint (see ../media.ts);
 *  - the body is capped before parsing, and the file is validated by magic bytes;
 *  - responses carry static codes/messages, never driver or stack details.
 *
 * None of these makes the route safe to expose. A seller auth/role decision is
 * required before any non-loopback binding or deployment.
 */
import {
  MEDIA_NOT_CONFIGURED_MESSAGE,
  isProductionEnvironment,
  resolveMediaAdapter,
  type MediaEnvironment,
  type MediaStoreAdapter,
} from '../media';
import {
  MAX_IMAGE_BYTES,
  MediaValidationError,
  validateImageBytes,
} from './formats';

/** Multipart boundaries and headers need room; the file itself is capped at 5 MiB. */
const MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + 1024 * 1024;

export interface MediaUploadDeps {
  /** Injected in tests; `undefined` means resolve from `env`. */
  adapter?: MediaStoreAdapter | null;
  env?: MediaEnvironment;
}

function json(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
    },
  });
}

function failure(status: number, code: string, message: string): Response {
  return json(status, { ok: false, code, message });
}

function isFileLike(value: unknown): value is File {
  return (
    typeof value === 'object' &&
    value !== null &&
    'arrayBuffer' in value &&
    'size' in value &&
    'type' in value &&
    'name' in value
  );
}

export async function handleMediaUploadRequest(
  request: Request,
  deps: MediaUploadDeps = {},
): Promise<Response> {
  const env = deps.env ?? process.env;

  if (request.method !== 'POST') {
    return failure(405, 'METHOD_NOT_ALLOWED', 'فقط POST پذیرفته می‌شود.');
  }

  // 404 rather than 403: a disabled local endpoint should not advertise itself.
  if (isProductionEnvironment(env) || env.MEDIA_LOCAL_UPLOAD_ENABLED !== 'true') {
    return failure(404, 'NOT_FOUND', 'نشانی پیدا نشد.');
  }

  const adapter = deps.adapter === undefined ? resolveMediaAdapter(env) : deps.adapter;
  if (adapter === null) {
    return failure(503, 'MEDIA_NOT_CONFIGURED', MEDIA_NOT_CONFIGURED_MESSAGE);
  }

  const declaredLength = Number(request.headers.get('content-length') ?? '');
  if (Number.isFinite(declaredLength) && declaredLength > MAX_REQUEST_BYTES) {
    return failure(413, 'IMAGE_TOO_LARGE', 'حجم درخواست بیش از حد مجاز است.');
  }

  const contentType = request.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().startsWith('multipart/form-data')) {
    return failure(400, 'INVALID_REQUEST', 'بدنهٔ درخواست باید multipart/form-data باشد.');
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return failure(400, 'INVALID_REQUEST', 'بدنهٔ درخواست خوانده نشد.');
  }

  const file = form.get('file');
  if (!isFileLike(file)) {
    return failure(400, 'INVALID_IMAGE', 'یک فایل تصویر با نام file لازم است.');
  }

  if (file.size === 0) {
    return failure(400, 'INVALID_IMAGE', 'تصویر خالی است.');
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return failure(413, 'IMAGE_TOO_LARGE', 'حجم تصویر بیش از حد مجاز (۵ مگابایت) است.');
  }

  let bytes: Uint8Array;
  try {
    bytes = new Uint8Array(await file.arrayBuffer());
  } catch {
    return failure(400, 'INVALID_IMAGE', 'محتوای تصویر خوانده نشد.');
  }

  let mime: string;
  try {
    // Validated here for the HTTP status; the adapter validates again before
    // it derives an extension or writes anything.
    mime = validateImageBytes(bytes).mime;
  } catch (error) {
    if (error instanceof MediaValidationError) {
      return failure(error.status, error.code, error.message);
    }
    return failure(400, 'INVALID_IMAGE', 'تصویر معتبر نیست.');
  }

  try {
    const stored = await adapter.put(
      { fileName: file.name, contentType: mime, byteLength: bytes.byteLength },
      bytes,
    );
    return json(200, {
      ok: true,
      storagePath: stored.storagePath,
      publicUrl: stored.publicUrl,
      duplicate: stored.duplicate === true,
    });
  } catch (error) {
    if (error instanceof MediaValidationError) {
      return failure(error.status, error.code, error.message);
    }
    return failure(
      503,
      'STORAGE_UNAVAILABLE',
      'ذخیره‌سازی محلی رسانه پاسخ نداد؛ تصویر ذخیره نشد.',
    );
  }
}
