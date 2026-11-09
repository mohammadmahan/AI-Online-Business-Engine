import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import type { MediaStoreAdapter, MediaUploadRequest, StoredMedia } from '../media';
import { validateImageBytes } from './formats';
import { MediaStorageError } from './s3';

/**
 * D-172 §2.1 — the FILESYSTEM media adapter (Phase 5, local-first).
 *
 * The owner approved local MinIO (G-5 amendment 2026-10-25), but requiring a
 * second container to add a product image was friction with no benefit for a
 * single-shop pilot. This adapter writes the same content-addressed layout
 * locally:
 *
 *   <MEDIA_LOCAL_DIR>/products/sha256/<first two hex>/<sha256>.<jpg|png|webp>
 *
 * and the public URL is SITE-RELATIVE (`/media/…`), served by
 * `GET /media/[...path]` (`src/app/media/[...path]/route.ts`). That route is why
 * the files must NOT live under `public/`: Next snapshots `public/` at build
 * time, so a runtime write would be invisible to a production build and
 * unreachable through the CDN-less pilot image; a route reads the directory at
 * request time in both `next dev` and `next start`.
 *
 * The same invariants as the S3 adapter hold, so the two backends cannot
 * disagree about what was stored:
 *  - bytes are validated by magic bytes first (JPEG/PNG/WebP, ≤ 5 MiB);
 *  - the key is a hash of the CONTENT, never the filename or client MIME type;
 *  - an identical upload is an idempotent no-op (`duplicate: true`);
 *  - a storage failure is a coarse `MediaStorageError` (503), never a driver
 *    message that could echo a path or a permission detail.
 *
 * The adapter never deletes and never lists: an upload is a write, and removal
 * is a separate decision the panel does not make yet.
 */

/** Where `GET /media/[...path]` is mounted (see `serve.ts`). */
export const LOCAL_MEDIA_PUBLIC_BASE = '/media';

export interface LocalMediaAdapterConfig {
  /** Absolute directory. The resolver in `../media.ts` owns that decision. */
  directory: string;
}

function contentAddress(bytes: Uint8Array): string {
  return createHash('sha256').update(bytes).digest('hex');
}

function isAlreadyExists(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    (error as { code: unknown }).code === 'EEXIST'
  );
}

export function createLocalMediaAdapter(config: LocalMediaAdapterConfig): MediaStoreAdapter {
  return {
    async put(request: MediaUploadRequest, bytes: Uint8Array): Promise<StoredMedia> {
      // Validated here too, not only at the HTTP edge: the adapter is the last
      // module before a write, and a future caller must not be able to store a
      // non-image by skipping the handler.
      const format = validateImageBytes(bytes);
      if (request.byteLength !== bytes.byteLength) {
        throw new MediaStorageError('media: declared length does not match the received bytes');
      }

      const hash = contentAddress(bytes);
      const storagePath = `products/sha256/${hash.slice(0, 2)}/${hash}.${format.extension}`;
      const absolute = path.join(config.directory, storagePath);
      const publicUrl = `${LOCAL_MEDIA_PUBLIC_BASE}/${storagePath}`;

      try {
        await mkdir(path.dirname(absolute), { recursive: true });
        // `wx` makes the existence check part of the write: two concurrent
        // uploads of the same bytes cannot both report a fresh store.
        await writeFile(absolute, bytes, { flag: 'wx' });
        return { storagePath, publicUrl, duplicate: false };
      } catch (error) {
        if (isAlreadyExists(error)) {
          return { storagePath, publicUrl, duplicate: true };
        }
        throw new MediaStorageError('media: the local store rejected the write');
      }
    },
  };
}
