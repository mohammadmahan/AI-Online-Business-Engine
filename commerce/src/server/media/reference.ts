import { mediaPublicPrefix, type MediaEnvironment } from '../media';

/**
 * D-172 §2.1 — what a STORED image reference may look like.
 *
 * The upload edge (and therefore every writer) derives the key from the bytes:
 * `products/sha256/<first2>/<sha256>.<jpg|png|webp>` (see `./local` and `./s3`).
 * A gallery edit submits paths and urls from the browser, so without a check a
 * forged request could point `product_images.public_url` at any origin — an
 * off-site hotlink at best, a tracking pixel or a phishing image at worst, and a
 * storefront that renders merchant-controlled third-party content.
 *
 * The rule is deliberately structural rather than "looks like a URL":
 *
 *  - `storagePath` must be EXACTLY a content-addressed key this store produces,
 *    with the two-character directory equal to the hash prefix (so the two halves
 *    of the key cannot disagree);
 *  - `publicUrl` must be EXACTLY `<configured prefix>/<storagePath>` — the prefix
 *    comes from the provider that is actually configured (`/media` for the local
 *    filesystem store, the bucket's public base for S3/MinIO), never from a
 *    default or from the submitted value.
 *
 * No query string, no fragment, no absolute foreign URL, no `data:` uri and no
 * traversal can satisfy that equality, and the check needs no network call — so
 * it behaves the same for both providers.
 *
 * It intentionally does NOT check that the bytes still exist: S3 cannot answer
 * that without a network round-trip, and the local reader answers 404 for a
 * missing object. A reference that passes here is a reference THIS store wrote.
 */

const STORED_IMAGE_PATH_RE =
  /^products\/sha256\/([0-9a-f]{2})\/([0-9a-f]{64})\.(jpg|png|webp)$/;

export type StoredImageReferenceVerdict =
  | { ok: true }
  | { ok: false; message: string };

export function storedImagePathProblem(storagePath: string): string | null {
  const match = STORED_IMAGE_PATH_RE.exec(storagePath);
  if (match === null) {
    return 'مسیر ذخیره‌سازی تصویر با قالب انبار رسانه نمی‌خواند.';
  }
  if (!match[2]!.startsWith(match[1]!)) {
    return 'مسیر ذخیره‌سازی تصویر با هش محتوای آن هم‌خوان نیست.';
  }
  return null;
}

/** The public URL this provider would publish for `storagePath`, or `null`. */
export function expectedPublicUrl(
  storagePath: string,
  env: MediaEnvironment = process.env,
): string | null {
  const prefix = mediaPublicPrefix(env);
  if (prefix === null) {
    return null;
  }
  return `${prefix}/${storagePath}`;
}

export function validateStoredImageReference(
  storagePath: string,
  publicUrl: string,
  env: MediaEnvironment = process.env,
): StoredImageReferenceVerdict {
  const problem = storedImagePathProblem(storagePath);
  if (problem !== null) {
    return { ok: false, message: problem };
  }
  const expected = expectedPublicUrl(storagePath, env);
  if (expected === null) {
    return { ok: false, message: 'ذخیره‌سازی رسانه در این نصب فعال نیست.' };
  }
  if (publicUrl !== expected) {
    return {
      ok: false,
      message: 'نشانی تصویر با انبار رسانهٔ تنظیم‌شده هم‌خوان نیست؛ تصویر باید از همین سامانه بارگذاری شده باشد.',
    };
  }
  return { ok: true };
}
