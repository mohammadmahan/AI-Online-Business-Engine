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
 * Phase 5 added a SECOND local provider — `MEDIA_PROVIDER=local`, a plain
 * directory on this machine — because requiring a MinIO container just to add a
 * product photo was friction without a benefit for a one-shop pilot. The two
 * local providers are the same seam with the same byte gate and the same
 * content-addressed key; only the write target differs (filesystem vs S3).
 *
 * `MEDIA_PROVIDER` unset keeps the previous behaviour exactly (the MinIO/S3
 * branch), so every existing instruction and test still describes the default.
 * An unrecognised provider is a REFUSAL — never a guess.
 *
 * When G-5 is ruled for production, one adapter implementation is bound here and
 * the refusal disappears — no caller changes.
 */
import path from 'node:path';

import { LOCAL_MEDIA_PUBLIC_BASE, createLocalMediaAdapter } from './media/local';
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
  'ذخیره‌سازی محلی رسانه در این نصب فعال نیست؛ تصویر انتخاب‌شده ذخیره نمی‌شود. محصول را بدون تصویر ثبت کنید یا نخست ذخیره‌سازی رسانه را فعال کنید؛ پیوست نشانی بیرونی مجاز نیست.';

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

export const MEDIA_PROVIDER_S3 = 's3';
export const MEDIA_PROVIDER_LOCAL = 'local';

/**
 * `s3` when unset (the pre-Phase-5 default), otherwise the normalised value.
 * Anything that is not a known provider is returned as-is and refused later.
 */
export function resolveMediaProvider(env: MediaEnvironment = process.env): string {
  const raw = env.MEDIA_PROVIDER?.trim().toLowerCase();
  return raw === undefined || raw === '' ? MEDIA_PROVIDER_S3 : raw;
}

/**
 * The filesystem store's absolute directory, or `null` when it is not the
 * selected provider or the path is missing/unusable.
 *
 * A relative value is resolved against the process CWD (the app directory in the
 * container). The filesystem root itself is refused: `MEDIA_LOCAL_DIR=/` would
 * turn the reader and the writer loose on the whole machine.
 */
export function resolveLocalMediaDirectory(env: MediaEnvironment = process.env): string | null {
  if (resolveMediaProvider(env) !== MEDIA_PROVIDER_LOCAL) {
    return null;
  }
  const raw = env.MEDIA_LOCAL_DIR?.trim();
  if (!raw) {
    return null;
  }
  const resolved = path.resolve(raw);
  if (resolved === path.parse(resolved).root) {
    return null;
  }
  return resolved;
}

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
 * The S3/MinIO configuration, or `null` when any part of it is missing, wrong or
 * not loopback. Extracted so the adapter and the public-URL derivation below
 * cannot drift apart: both read the SAME validated config.
 */
function resolveS3Config(env: MediaEnvironment): S3MediaAdapterConfig | null {
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

  return {
    endpoint: endpoint.origin,
    region: env.MEDIA_S3_REGION?.trim() || 'us-east-1',
    bucket,
    accessKeyId,
    secretAccessKey,
    publicBaseUrl: publicBase.origin + basePath,
  };
}

/**
 * Resolves the ONE local adapter, or `null`. `env` is injectable so the guard is
 * testable without mutating the process environment.
 */
export function resolveMediaAdapter(env: MediaEnvironment = process.env): MediaStoreAdapter | null {
  if (isProductionEnvironment(env)) {
    return null;
  }

  const provider = resolveMediaProvider(env);
  if (provider === MEDIA_PROVIDER_LOCAL) {
    const directory = resolveLocalMediaDirectory(env);
    return directory === null ? null : createLocalMediaAdapter({ directory });
  }
  if (provider !== MEDIA_PROVIDER_S3) {
    // A typo (`MEDIA_PROVIDER=files`) must not silently fall back to S3 or to an
    // unwritable default; the panel then shows its "uploads unavailable" notice.
    return null;
  }

  const config = resolveS3Config(env);
  return config === null ? null : createS3MediaAdapter(config);
}

/**
 * The prefix every stored object's PUBLIC url starts with, for the provider that
 * is actually configured — or `null` when no provider resolves.
 *
 * This is what makes a submitted image reference checkable: a gallery row is only
 * accepted when `publicUrl` is exactly `<prefix>/<storagePath>`, so a merchant
 * (or a forged request) cannot point `product_images` at an arbitrary origin.
 * Note the asymmetry with the adapter: on the local provider the url is
 * site-relative (`/media/...`) because the app serves it itself, while the S3
 * provider serves from the bucket's own public base.
 */
export function mediaPublicPrefix(env: MediaEnvironment = process.env): string | null {
  if (isProductionEnvironment(env)) {
    return null;
  }
  const provider = resolveMediaProvider(env);
  if (provider === MEDIA_PROVIDER_LOCAL) {
    return resolveLocalMediaDirectory(env) === null ? null : LOCAL_MEDIA_PUBLIC_BASE;
  }
  if (provider !== MEDIA_PROVIDER_S3) {
    return null;
  }
  return resolveS3Config(env)?.publicBaseUrl ?? null;
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
