/**
 * D-172 §2.1 — the byte-level gate for the local media backend (G-5).
 *
 * The browser compresses every chosen image to JPEG today, but the storage
 * contract accepts the three formats the roadmap's image uploader names:
 * JPEG, PNG and WebP. The declared `Content-Type` and the client filename are
 * NEVER trusted: the format is derived from the bytes themselves, because both
 * are attacker-controlled strings and both are trivially wrong.
 *
 * This module is pure (no I/O) so the same rules are used by the adapter, the
 * upload handler and their tests, and so a future second adapter cannot quietly
 * disagree about what an image is.
 */

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export type ImageMime = 'image/jpeg' | 'image/png' | 'image/webp';
export type ImageExtension = 'jpg' | 'png' | 'webp';

export interface DetectedImage {
  mime: ImageMime;
  extension: ImageExtension;
}

export type MediaValidationCode = 'INVALID_IMAGE' | 'UNSUPPORTED_IMAGE' | 'IMAGE_TOO_LARGE';

/** A refusal the HTTP edge can map without inspecting an error's message. */
export class MediaValidationError extends Error {
  readonly code: MediaValidationCode;
  readonly status: 400 | 413 | 415;

  constructor(code: MediaValidationCode, message: string, status: 400 | 413 | 415) {
    super(message);
    this.name = 'MediaValidationError';
    this.code = code;
    this.status = status;
  }
}

function startsWith(bytes: Uint8Array, signature: readonly number[]): boolean {
  if (bytes.length < signature.length) {
    return false;
  }
  return signature.every((value, index) => bytes[index] === value);
}

/**
 * JPEG: SOI marker + first segment marker (`FF D8 FF`).
 * PNG: the full 8-byte PNG signature.
 * WebP: RIFF container with the `WEBP` form type at offset 8.
 *
 * An SVG is deliberately NOT an image here: it is active content and cannot be
 * served from a catalog bucket without a sanitizer this track does not have.
 */
export function detectImageFormat(bytes: Uint8Array): DetectedImage | null {
  if (startsWith(bytes, [0xff, 0xd8, 0xff])) {
    return { mime: 'image/jpeg', extension: 'jpg' };
  }
  if (startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) {
    return { mime: 'image/png', extension: 'png' };
  }
  if (
    bytes.length >= 12 &&
    startsWith(bytes, [0x52, 0x49, 0x46, 0x46]) &&
    bytes[8] === 0x57 &&
    bytes[9] === 0x45 &&
    bytes[10] === 0x42 &&
    bytes[11] === 0x50
  ) {
    return { mime: 'image/webp', extension: 'webp' };
  }
  return null;
}

/**
 * Validates size BEFORE format so an oversized payload is refused as `413`
 * rather than being scanned further, then validates the magic bytes.
 *
 * `INVALID_IMAGE` (400) covers empty/absent content; `UNSUPPORTED_IMAGE` (415)
 * covers a non-image or an unsupported image; `IMAGE_TOO_LARGE` (413) covers the
 * hard 5 MiB ceiling.
 */
export function validateImageBytes(bytes: Uint8Array): DetectedImage {
  if (bytes.length === 0) {
    throw new MediaValidationError('INVALID_IMAGE', 'تصویر خالی است.', 400);
  }
  if (bytes.length > MAX_IMAGE_BYTES) {
    throw new MediaValidationError(
      'IMAGE_TOO_LARGE',
      'حجم تصویر بیش از حد مجاز (۵ مگابایت) است.',
      413,
    );
  }
  const format = detectImageFormat(bytes);
  if (format === null) {
    throw new MediaValidationError(
      'UNSUPPORTED_IMAGE',
      'فقط تصویرهای JPEG، PNG و WebP پذیرفته می‌شوند.',
      415,
    );
  }
  return format;
}
