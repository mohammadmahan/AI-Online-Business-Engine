/**
 * D-172 §2.1 — media storage seam.
 *
 * The roadmap's image uploader needs somewhere to PUT bytes, and **G-5 is still
 * OPEN**: the owner has not selected a storage provider (D-049/D-056, Phase 24
 * `MediaStoreContract`, D-129–D-132 swappability). Rather than inventing a
 * provider — or quietly writing catalog rows that point at images which do not
 * exist — the seam is declared here and currently resolves to `null`.
 *
 * Consequences, and they are deliberate:
 *  - the client-side uploader still compresses, previews, orders and
 *    primary-flags the selection (that is real work, and it is what the merchant
 *    reviews before submitting);
 *  - the server action REFUSES a submission that carries pending image bytes and
 *    says why, instead of creating a product whose gallery is broken;
 *  - a product with no images is created normally, because §1.4 media is
 *    optional.
 *
 * When G-5 is ruled, one adapter implementation is bound below and the refusal
 * disappears — no other code changes.
 */

export interface MediaUploadRequest {
  fileName: string;
  contentType: string;
  byteLength: number;
}

export interface StoredMedia {
  storagePath: string;
  publicUrl: string;
}

export interface MediaStoreAdapter {
  put(request: MediaUploadRequest, bytes: Uint8Array): Promise<StoredMedia>;
}

export const MEDIA_NOT_CONFIGURED_MESSAGE =
  'ذخیره‌سازی رسانهٔ فروشگاه هنوز تعیین نشده است (تصمیم باز G-5). تصویر انتخاب‌شده ذخیره نمی‌شود؛ می‌توانید محصول را بدون تصویر ثبت کنید یا منتظر تصویب مالک بمانید.';

/** `null` = not ruled yet. This is the whole gate. */
export function resolveMediaAdapter(): MediaStoreAdapter | null {
  return null;
}

export function mediaUploadAllowed(): boolean {
  return resolveMediaAdapter() !== null;
}
