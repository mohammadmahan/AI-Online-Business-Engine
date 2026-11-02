import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { describe, it } from 'node:test';

import type { S3Client } from '@aws-sdk/client-s3';

import {
  MAX_IMAGE_BYTES,
  MediaValidationError,
  detectImageFormat,
  validateImageBytes,
} from '@/server/media/formats';
import {
  MEDIA_REQUIRED_ENV,
  mediaUploadAllowed,
  resolveMediaAdapter,
  type MediaEnvironment,
  type MediaStoreAdapter,
} from '@/server/media';
import {
  MediaStorageError,
  createS3MediaAdapter,
  type S3MediaAdapterConfig,
} from '@/server/media/s3';
import { handleMediaUploadRequest } from '@/server/media/upload';

/**
 * D-172 §2.1 / G-5 — local media backend, entirely offline.
 *
 * Three properties are asserted here and nowhere else:
 *   1. the format gate accepts exactly JPEG/PNG/WebP from MAGIC BYTES;
 *   2. the resolver refuses anything that is not the local loopback MinIO, and
 *      refuses unconditionally in production;
 *   3. an upload stores a content-addressed object, is idempotent, and maps a
 *      storage failure to a stable code without leaking driver detail.
 *
 * No test opens a socket: the S3 client is injected and the handler receives an
 * in-memory adapter or a fake env.
 */

const LOOPBACK_ENV: MediaEnvironment = {
  MEDIA_S3_ENDPOINT: 'http://127.0.0.1:19000',
  MEDIA_S3_BUCKET: 'commerce-media',
  MEDIA_S3_ACCESS_KEY: 'local-access-key',
  MEDIA_S3_SECRET_KEY: 'local-secret-key',
  MEDIA_S3_REGION: 'us-east-1',
  MEDIA_PUBLIC_BASE_URL: 'http://127.0.0.1:19000/commerce-media',
  MEDIA_LOCAL_UPLOAD_ENABLED: 'true',
  NODE_ENV: 'development',
};

const JPEG = Uint8Array.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46]);
const PNG = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00]);
const WEBP = Uint8Array.from([
  0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x45, 0x42, 0x50, 0x56, 0x50, 0x38, 0x20,
]);

function imageOf(prefix: Uint8Array, total = 24): Uint8Array {
  const bytes = new Uint8Array(Math.max(total, prefix.length));
  bytes.set(prefix);
  return bytes;
}

function sha256(bytes: Uint8Array): string {
  return createHash('sha256').update(bytes).digest('hex');
}

/** Minimal S3 client double: only `send` is used by the adapter. */
function fakeClient(script: Array<(command: unknown) => unknown>) {
  const seen: Array<{ name: string; input: Record<string, unknown> }> = [];
  const client = {
    async send(command: unknown) {
      const name = (command as { constructor: { name: string } }).constructor.name;
      seen.push({ name, input: (command as { input: Record<string, unknown> }).input });
      const next = script.shift();
      if (!next) {
        throw new Error(`unexpected S3 call: ${name}`);
      }
      return next(command);
    },
  };
  return { client: client as unknown as S3Client, seen };
}

function notFound(): never {
  const error = new Error('not found');
  error.name = 'NotFound';
  throw Object.assign(error, { $metadata: { httpStatusCode: 404 } });
}

const ADAPTER_CONFIG: S3MediaAdapterConfig = {
  endpoint: 'http://127.0.0.1:19000',
  region: 'us-east-1',
  bucket: 'commerce-media',
  accessKeyId: 'local-access-key',
  secretAccessKey: 'local-secret-key',
  publicBaseUrl: 'http://127.0.0.1:19000/commerce-media',
};

describe('D-172 G-5 — magic-byte format gate', () => {
  it('accepts JPEG, PNG and WebP and reports the canonical extension', () => {
    assert.deepEqual(detectImageFormat(JPEG), { mime: 'image/jpeg', extension: 'jpg' });
    assert.deepEqual(detectImageFormat(PNG), { mime: 'image/png', extension: 'png' });
    assert.deepEqual(detectImageFormat(WEBP), { mime: 'image/webp', extension: 'webp' });
  });

  it('does not accept a RIFF container that is not WebP', () => {
    const wav = Uint8Array.from([0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45]);
    assert.equal(detectImageFormat(wav), null);
  });

  it('refuses SVG, GIF, spoofed headers and other non-accepted content', () => {
    const svg = new TextEncoder().encode('<svg xmlns="http://www.w3.org/2000/svg"></svg>');
    const gif = Uint8Array.from([0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x00, 0x00]);
    for (const bytes of [svg, gif, Uint8Array.from([0x25, 0x50, 0x44, 0x46])]) {
      assert.throws(
        () => validateImageBytes(bytes),
        (error: unknown) =>
          error instanceof MediaValidationError &&
          error.status === 415 &&
          error.code === 'UNSUPPORTED_IMAGE',
      );
    }
  });

  it('refuses empty content as a 400 and content over 5 MiB as a 413', () => {
    assert.throws(
      () => validateImageBytes(new Uint8Array(0)),
      (error: unknown) => error instanceof MediaValidationError && error.status === 400,
    );

    assert.throws(
      () => validateImageBytes(imageOf(JPEG, MAX_IMAGE_BYTES + 1)),
      (error: unknown) =>
        error instanceof MediaValidationError &&
        error.status === 413 &&
        error.code === 'IMAGE_TOO_LARGE',
    );

    assert.doesNotThrow(() => validateImageBytes(imageOf(JPEG, MAX_IMAGE_BYTES)));
  });
});

describe('D-172 G-5 — resolver is loopback-only and fails closed', () => {
  it('resolves for the complete local loopback configuration', () => {
    assert.notEqual(resolveMediaAdapter(LOOPBACK_ENV), null);
    assert.equal(mediaUploadAllowed(LOOPBACK_ENV), true);
  });

  it('reports uploads blocked while the adapter resolves but the edge is off', () => {
    const env: MediaEnvironment = { ...LOOPBACK_ENV };
    delete env.MEDIA_LOCAL_UPLOAD_ENABLED;
    assert.notEqual(resolveMediaAdapter(env), null);
    assert.equal(mediaUploadAllowed(env), false);
    assert.equal(mediaUploadAllowed({ ...env, MEDIA_LOCAL_UPLOAD_ENABLED: 'false' }), false);
  });

  it('never resolves in production, whatever the local values say', () => {
    for (const NODE_ENV of ['production', ' Production ', 'PRODUCTION']) {
      assert.equal(resolveMediaAdapter({ ...LOOPBACK_ENV, NODE_ENV }), null);
      assert.equal(mediaUploadAllowed({ ...LOOPBACK_ENV, NODE_ENV }), false);
    }
  });

  it('refuses a non-loopback host or the standard MinIO port', () => {
    const targets = [
      'http://minio.internal:19000',
      'http://192.168.1.20:19000',
      'https://storage.example.com:19000',
      'http://127.0.0.1:9000',
      'http://127.0.0.1',
    ];
    for (const endpoint of targets) {
      const adapter = resolveMediaAdapter({ ...LOOPBACK_ENV, MEDIA_S3_ENDPOINT: endpoint });
      assert.equal(adapter, null, `endpoint ${endpoint} must not resolve`);
    }
  });

  it('refuses a malformed endpoint, a path, or embedded credentials', () => {
    const targets = [
      'not a url',
      'ftp://127.0.0.1:19000',
      'http://127.0.0.1:19000/minio',
      'http://user:pass@127.0.0.1:19000',
    ];
    for (const endpoint of targets) {
      assert.equal(resolveMediaAdapter({ ...LOOPBACK_ENV, MEDIA_S3_ENDPOINT: endpoint }), null);
    }
  });

  it('requires every value — no default bucket, region or credential', () => {
    for (const name of MEDIA_REQUIRED_ENV) {
      const env: MediaEnvironment = { ...LOOPBACK_ENV };
      delete env[name];
      assert.equal(resolveMediaAdapter(env), null, `${name} must be required`);
    }
  });

  it('requires the public base to be the bucket url on the same local origin', () => {
    const bases = [
      'http://127.0.0.1:19000',
      'http://127.0.0.1:19000/other-bucket',
      'http://127.0.0.1:19000/commerce-media?token=x',
      'http://cdn.example.com:19000/commerce-media',
      'http://127.0.0.1:9000/commerce-media',
    ];
    for (const base of bases) {
      assert.equal(resolveMediaAdapter({ ...LOOPBACK_ENV, MEDIA_PUBLIC_BASE_URL: base }), null);
    }
  });

  it('requires a valid lowercase bucket name', () => {
    for (const bucket of ['Commerce-Media', 'ab', 'bucket name', 'bucket..name', '']) {
      assert.equal(resolveMediaAdapter({ ...LOOPBACK_ENV, MEDIA_S3_BUCKET: bucket }), null);
    }
  });
});

describe('D-172 G-5 — content-addressed adapter', () => {
  it('writes products/sha256/<prefix>/<hash>.<ext> with a verified content type', async () => {
    const { client, seen } = fakeClient([
      () => notFound(),
      () => ({}),
    ]);
    const adapter = createS3MediaAdapter(ADAPTER_CONFIG, client);

    const stored = await adapter.put(
      { fileName: 'photo.png', contentType: 'image/png', byteLength: PNG.byteLength },
      PNG,
    );

    const hash = sha256(PNG);
    assert.equal(stored.storagePath, `products/sha256/${hash.slice(0, 2)}/${hash}.png`);
    assert.equal(stored.publicUrl, `${ADAPTER_CONFIG.publicBaseUrl}/${stored.storagePath}`);
    assert.equal(stored.duplicate, false);

    assert.equal(seen[0]?.name, 'HeadObjectCommand');
    assert.equal(seen[1]?.name, 'PutObjectCommand');
    assert.equal(seen[1]?.input.Bucket, 'commerce-media');
    assert.equal(seen[1]?.input.Key, stored.storagePath);
    assert.equal(seen[1]?.input.ContentType, 'image/png');
  });

  it('derives the extension from the bytes, not from the client name or content type', async () => {
    const { client, seen } = fakeClient([() => notFound(), () => ({})]);
    const adapter = createS3MediaAdapter(ADAPTER_CONFIG, client);

    const stored = await adapter.put(
      { fileName: 'evil.html', contentType: 'text/html', byteLength: WEBP.byteLength },
      WEBP,
    );

    assert.match(stored.storagePath, /\.webp$/);
    assert.equal(seen[1]?.input.ContentType, 'image/webp');
  });

  it('is idempotent: identical bytes that already exist are not rewritten', async () => {
    const { client, seen } = fakeClient([() => ({})]);
    const adapter = createS3MediaAdapter(ADAPTER_CONFIG, client);

    const stored = await adapter.put(
      { fileName: 'photo.jpg', contentType: 'image/jpeg', byteLength: JPEG.byteLength },
      JPEG,
    );

    assert.equal(stored.duplicate, true);
    assert.deepEqual(seen.map((call) => call.name), ['HeadObjectCommand']);
  });

  it('refuses non-image bytes before it contacts storage', async () => {
    const { client, seen } = fakeClient([]);
    const adapter = createS3MediaAdapter(ADAPTER_CONFIG, client);

    await assert.rejects(
      adapter.put(
        { fileName: 'note.txt', contentType: 'text/plain', byteLength: 4 },
        Uint8Array.from([0x74, 0x65, 0x78, 0x74]),
      ),
      (error: unknown) => error instanceof MediaValidationError && error.status === 415,
    );
    assert.deepEqual(seen, []);
  });

  it('refuses a declared length that does not match the bytes', async () => {
    const { client } = fakeClient([]);
    const adapter = createS3MediaAdapter(ADAPTER_CONFIG, client);
    await assert.rejects(
      adapter.put({ fileName: 'a.jpg', contentType: 'image/jpeg', byteLength: 1 }, JPEG),
      MediaStorageError,
    );
  });

  it('maps a storage failure to a stable code without leaking driver detail', async () => {
    const failingHead = fakeClient([
      () =>
        Promise.reject(
          Object.assign(new Error('connect ECONNREFUSED 127.0.0.1:19000'), {
            name: 'NetworkingError',
            $metadata: { httpStatusCode: 500 },
          }),
        ),
    ]);
    await assert.rejects(
      createS3MediaAdapter(ADAPTER_CONFIG, failingHead.client).put(
        { fileName: 'a.jpg', contentType: 'image/jpeg', byteLength: JPEG.byteLength },
        JPEG,
      ),
      (error: unknown) =>
        error instanceof MediaStorageError &&
        !error.message.includes('ECONNREFUSED') &&
        !error.message.includes('19000'),
    );

    const failingPut = fakeClient([
      () => notFound(),
      () => Promise.reject(Object.assign(new Error('secret-internal-detail'), { name: 'S3ServiceException' })),
    ]);
    await assert.rejects(
      createS3MediaAdapter(ADAPTER_CONFIG, failingPut.client).put(
        { fileName: 'a.jpg', contentType: 'image/jpeg', byteLength: JPEG.byteLength },
        JPEG,
      ),
      (error: unknown) =>
        error instanceof MediaStorageError && !error.message.includes('secret-internal-detail'),
    );
  });
});

describe('D-172 G-5 — upload edge', () => {
  // Lets a request reach the format checks; a valid upload would call it.
  const unusedAdapter: MediaStoreAdapter = {
    async put() {
      throw new Error('the adapter must not be called by this test');
    },
  };

  function uploadRequest(bytes: Uint8Array, name = 'photo.png'): Request {
    // Copied into a fresh ArrayBuffer-backed view so the BlobPart type is exact.
    const payload = new Uint8Array(bytes.byteLength);
    payload.set(bytes);
    const form = new FormData();
    form.set('file', new File([payload], name, { type: 'application/octet-stream' }));
    return new Request('http://127.0.0.1:3000/api/admin/media', { method: 'POST', body: form });
  }

  it('answers 404 when the local switch is off or the build is production', async () => {
    const disabled = await handleMediaUploadRequest(uploadRequest(PNG), {
      env: { ...LOOPBACK_ENV, MEDIA_LOCAL_UPLOAD_ENABLED: 'false' },
      adapter: null,
    });
    assert.equal(disabled.status, 404);

    const production = await handleMediaUploadRequest(uploadRequest(PNG), {
      env: { ...LOOPBACK_ENV, NODE_ENV: ' PRODUCTION ' },
      adapter: null,
    });
    assert.equal(production.status, 404);
  });

  it('answers 404 for a non-POST method', async () => {
    const response = await handleMediaUploadRequest(
      new Request('http://127.0.0.1:3000/api/admin/media'),
      { env: LOOPBACK_ENV, adapter: null },
    );
    assert.equal(response.status, 405);
  });

  it('refuses with 503 when no adapter resolves', async () => {
    const response = await handleMediaUploadRequest(uploadRequest(PNG), {
      env: { ...LOOPBACK_ENV, MEDIA_S3_SECRET_KEY: '' },
    });
    assert.equal(response.status, 503);
    const body = (await response.json()) as { code: string };
    assert.equal(body.code, 'MEDIA_NOT_CONFIGURED');
  });

  it('stores a valid image and returns its path and url', async () => {
    const calls: Array<{ contentType: string; byteLength: number }> = [];
    const response = await handleMediaUploadRequest(uploadRequest(PNG), {
      env: LOOPBACK_ENV,
      adapter: {
        async put(request, bytes) {
          calls.push({ contentType: request.contentType, byteLength: bytes.byteLength });
          return {
            storagePath: 'products/sha256/ab/abcd.png',
            publicUrl: 'http://127.0.0.1:19000/commerce-media/products/sha256/ab/abcd.png',
            duplicate: false,
          };
        },
      },
    });

    assert.equal(response.status, 200);
    const body = (await response.json()) as Record<string, unknown>;
    assert.equal(body.ok, true);
    assert.equal(body.storagePath, 'products/sha256/ab/abcd.png');
    assert.equal(body.duplicate, false);
    // The declared type was application/octet-stream; the verified one wins.
    assert.deepEqual(calls, [{ contentType: 'image/png', byteLength: PNG.byteLength }]);
  });

  it('refuses a missing file and a malformed multipart body with 400', async () => {
    const empty = new FormData();
    const noFile = await handleMediaUploadRequest(
      new Request('http://127.0.0.1:3000/api/admin/media', { method: 'POST', body: empty }),
      { env: LOOPBACK_ENV, adapter: unusedAdapter },
    );
    assert.equal(noFile.status, 400);

    const malformed = await handleMediaUploadRequest(
      new Request('http://127.0.0.1:3000/api/admin/media', {
        method: 'POST',
        headers: { 'content-type': 'multipart/form-data; boundary=nope' },
        body: 'not-a-form',
      }),
      { env: LOOPBACK_ENV, adapter: unusedAdapter },
    );
    assert.equal(malformed.status, 400);
  });

  it('refuses an unsupported format with 415', async () => {
    const response = await handleMediaUploadRequest(
      uploadRequest(new TextEncoder().encode('<html>not an image</html>'), 'x.html'),
      { env: LOOPBACK_ENV, adapter: unusedAdapter },
    );
    assert.equal(response.status, 415);
    const body = (await response.json()) as { code: string };
    assert.equal(body.code, 'UNSUPPORTED_IMAGE');
  });

  it('refuses a file over 5 MiB with 413', async () => {
    const response = await handleMediaUploadRequest(uploadRequest(imageOf(JPEG, MAX_IMAGE_BYTES + 1)), {
      env: LOOPBACK_ENV,
      adapter: unusedAdapter,
    });
    assert.equal(response.status, 413);
    const body = (await response.json()) as { code: string };
    assert.equal(body.code, 'IMAGE_TOO_LARGE');
  });

  it('maps an unexpected storage failure to 503 without exposing detail', async () => {
    const response = await handleMediaUploadRequest(uploadRequest(PNG), {
      env: LOOPBACK_ENV,
      adapter: {
        async put() {
          throw new Error('S3 endpoint 127.0.0.1:19000 rejected the credential');
        },
      },
    });
    assert.equal(response.status, 503);
    const text = await response.text();
    assert.equal(text.includes('S3'), false);
    assert.equal(text.includes('credential'), false);
    assert.equal(response.headers.get('cache-control'), 'no-store');
  });
});
