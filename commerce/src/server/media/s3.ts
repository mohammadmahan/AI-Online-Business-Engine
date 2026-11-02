/**
 * D-172 §2.1 / G-5 — the LOCAL S3-compatible adapter (MinIO).
 *
 * The adapter is the only module that knows about S3. It never reads the
 * environment itself (the resolver in `../media.ts` owns that decision), never
 * derives a key from a filename or a client `Content-Type`, and never deletes an
 * object. Bytes are validated first, hashed, and stored under a content address:
 *
 *   products/sha256/<first two hex>/<sha256>.<jpg|png|webp>
 *
 * Identical bytes therefore map to the same key on every machine and every run;
 * `HeadObject` makes a repeated upload an idempotent no-op. Metadata is derived
 * from the verified format, never from the request.
 */
import { createHash } from 'node:crypto';

import {
  HeadObjectCommand,
  PutObjectCommand,
  S3Client,
} from '@aws-sdk/client-s3';

import type { MediaStoreAdapter, MediaUploadRequest, StoredMedia } from '../media';
import { validateImageBytes } from './formats';

export interface S3MediaAdapterConfig {
  endpoint: string;
  region: string;
  bucket: string;
  accessKeyId: string;
  secretAccessKey: string;
  publicBaseUrl: string;
}

/** A storage failure the HTTP edge reports as `STORAGE_UNAVAILABLE` (503). */
export class MediaStorageError extends Error {
  readonly code = 'STORAGE_UNAVAILABLE';

  constructor(message: string) {
    super(message);
    this.name = 'MediaStorageError';
  }
}

function httpStatus(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null || !('$metadata' in error)) {
    return undefined;
  }
  const metadata = (error as { $metadata?: { httpStatusCode?: number } }).$metadata;
  return metadata?.httpStatusCode;
}

function isMissingObject(error: unknown): boolean {
  if (httpStatus(error) === 404) {
    return true;
  }
  if (typeof error !== 'object' || error === null || !('name' in error)) {
    return false;
  }
  const name = String((error as { name: unknown }).name);
  return name === 'NotFound' || name === 'NoSuchKey';
}

export function createS3MediaAdapter(
  config: S3MediaAdapterConfig,
  injectedClient?: S3Client,
): MediaStoreAdapter {
  const client =
    injectedClient ??
    new S3Client({
      endpoint: config.endpoint,
      region: config.region,
      forcePathStyle: true,
      credentials: {
        accessKeyId: config.accessKeyId,
        secretAccessKey: config.secretAccessKey,
      },
    });

  return {
    async put(request: MediaUploadRequest, bytes: Uint8Array): Promise<StoredMedia> {
      // The adapter re-validates even though the route already did: a future
      // caller must not be able to store a non-image by bypassing the route.
      const format = validateImageBytes(bytes);
      if (request.byteLength !== bytes.byteLength) {
        throw new MediaStorageError('طول اعلام‌شدهٔ تصویر با محتوای واقعی یکسان نیست.');
      }

      const hash = createHash('sha256').update(bytes).digest('hex');
      const key = `products/sha256/${hash.slice(0, 2)}/${hash}.${format.extension}`;
      const publicUrl = `${config.publicBaseUrl}/${key}`;

      try {
        await client.send(new HeadObjectCommand({ Bucket: config.bucket, Key: key }));
        return { storagePath: key, publicUrl, duplicate: true };
      } catch (error) {
        if (!isMissingObject(error)) {
          throw new MediaStorageError('بررسی وجود تصویر در ذخیره‌سازی انجام نشد.');
        }
      }

      try {
        await client.send(
          new PutObjectCommand({
            Bucket: config.bucket,
            Key: key,
            Body: bytes,
            ContentType: format.mime,
            CacheControl: 'public, max-age=31536000, immutable',
          }),
        );
      } catch {
        // Deliberately swallowed: the SDK error can carry request metadata and
        // endpoint details, and neither belongs in an HTTP response or a log.
        throw new MediaStorageError('ذخیرهٔ تصویر در ذخیره‌سازی محلی انجام نشد.');
      }

      return { storagePath: key, publicUrl, duplicate: false };
    },
  };
}
