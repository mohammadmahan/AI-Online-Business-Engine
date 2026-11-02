/**
 * D-172 §2.1 — media storage seam.
 *
 * The roadmap's image uploader needs somewhere to PUT bytes. **G-5 is still open
 * for the production provider**, but the owner approved the existing local MinIO
 * service as the **local-only** backend (D-172 §4.4 amendment 2026-10-25), behind
 * this provider-neutral adapter. The production provider remains unselected, so
 * this resolver is deliberately narrow:
 *
 *  - only loopback endpoints on the local MinIO port (19000) are accepted;
 *  - every value is required — there is no partial configuration, no guessed
 *    bucket and no default credential;
 *  - `NODE_ENV=production` always resolves to `null`, even if every local value
 *    is present, so a production build can never write to the demo store;
 *  - anything unrecognised resolves to `null`, which leaves the existing refusal
 *    in place (the action refuses pending bytes; the upload route refuses with
 *    `MEDIA_NOT_CONFIGURED`).
 *
 * When G-5 is ruled for production, one adapter implementation is bound here and
 * the refusal disappears — no caller changes.
 */
import { createS3MediaAdapter, type S3MediaAdapterConfig } from './media/s3';

/**
 * What this seam actually reads: string-valued variables. Deliberately NOT
 * `NodeJS.ProcessEnv`, whose `NODE_ENV` is narrowed to Node's literal union —
 * the guard normalises case and whitespace itself, so a misspelled or padded
 * value must be expressible (and testable) rather than rejected by the type.
 */
export type MediaEnvironment = Record<string, string | undefined>;

export interface MediaUploadRequest {
  fileName: string;
  contentType: string;
  byteLength: number;
}

export interface StoredMedia {
  storagePath: string;
  publicUrl: string;
  /** True when the content-addressed object already existed (idempotent put). */
  duplicate?: boolean;
}

export interface MediaStoreAdapter {
  put(request: MediaUploadRequest, bytes: Uint8Array): Promise<StoredMedia>;
}

export const MEDIA_NOT_CONFIGURED_MESSAGE =
  'ذخیره‌سازی محلی رسانه در این نصب فعال نیست؛ تصویر انتخاب‌شده ذخیره نمی‌شود. می‌توانید محصول را بدون تصویر ثبت کنید یا تصویرِ میزبانی‌شدهٔ خودتان را با نشانی بیرونی پیوست کنید.';

/** Case-insensitive so a padded/uppercase build flag cannot relax a guard. */
export function isProductionEnvironment(env: MediaEnvironment = process.env): boolean {
  return env.NODE_ENV?.trim().toLowerCase() === 'production';
}

/** The variables the local adapter cannot run without. */
export const MEDIA_REQUIRED_ENV = [
  'MEDIA_S3_ENDPOINT',
  'MEDIA_S3_BUCKET',
  'MEDIA_S3_ACCESS_KEY',
  'MEDIA_S3_SECRET_KEY',
  'MEDIA_PUBLIC_BASE_URL',
] as const;

const LOCAL_MEDIA_PORT = '19000';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);
// MinIO's own bucket rules are close enough to S3's for a local store; this
// rejects empty/space/uppercase names before the SDK or the bucket ARN sees them.
const BUCKET_RE = /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/;

function parseLoopbackUrl(raw: string | undefined): URL | null {
  if (!raw) {
    return null;
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return null;
  }
  if (!LOOPBACK_HOSTS.has(url.hostname.toLowerCase())) {
    return null;
  }
  if (url.port !== LOCAL_MEDIA_PORT) {
    return null;
  }
  if (url.username !== '' || url.password !== '') {
    return null;
  }
  return url;
}

function isBucketName(value: string | undefined): value is string {
  return typeof value === 'string' && BUCKET_RE.test(value) && !value.includes('..');
}

/**
 * Resolves the ONE local adapter, or `null`. `env` is injectable so the guard is
 * testable without mutating the process environment.
 */
export function resolveMediaAdapter(env: MediaEnvironment = process.env): MediaStoreAdapter | null {
  if (isProductionEnvironment(env)) {
    return null;
  }

  const endpoint = parseLoopbackUrl(env.MEDIA_S3_ENDPOINT);
  if (endpoint === null || (endpoint.pathname !== '/' && endpoint.pathname !== '')) {
    return null;
  }

  const bucket = env.MEDIA_S3_BUCKET?.trim();
  if (!isBucketName(bucket)) {
    return null;
  }

  const accessKeyId = env.MEDIA_S3_ACCESS_KEY?.trim();
  const secretAccessKey = env.MEDIA_S3_SECRET_KEY?.trim();
  if (!accessKeyId || !secretAccessKey) {
    return null;
  }

  const publicBase = parseLoopbackUrl(env.MEDIA_PUBLIC_BASE_URL);
  if (publicBase === null || publicBase.search !== '' || publicBase.hash !== '') {
    return null;
  }
  // The public base is the BUCKET url, not the endpoint root: a misconfigured
  // base would otherwise serve 404s that look like missing uploads.
  const basePath = publicBase.pathname.replace(/\/+$/, '');
  if (basePath !== `/${bucket}`) {
    return null;
  }

  const config: S3MediaAdapterConfig = {
    endpoint: endpoint.origin,
    region: env.MEDIA_S3_REGION?.trim() || 'us-east-1',
    bucket,
    accessKeyId,
    secretAccessKey,
    publicBaseUrl: publicBase.origin + basePath,
  };
  return createS3MediaAdapter(config);
}

/**
 * True only when the local adapter resolves AND its HTTP edge is switched on.
 * The two are separate on purpose (the adapter has no request handling), but a
 * caller that is about to upload needs both — otherwise the seller panel would
 * hide its "media unavailable" notice while every upload answers 404.
 */
export function mediaUploadAllowed(env: MediaEnvironment = process.env): boolean {
  return env.MEDIA_LOCAL_UPLOAD_ENABLED === 'true' && resolveMediaAdapter(env) !== null;
}
