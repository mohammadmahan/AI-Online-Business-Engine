import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, it } from 'node:test';

import {
  MAX_IMAGE_BYTES,
  MediaValidationError,
} from '@/server/media/formats';
import {
  MEDIA_PROVIDER_LOCAL,
  mediaUploadAllowed,
  resolveLocalMediaDirectory,
  resolveMediaAdapter,
  type MediaEnvironment,
} from '@/server/media';
import { createLocalMediaAdapter } from '@/server/media/local';
import { readLocalMediaFile, resolveMediaFilePath } from '@/server/media/serve';
import { MediaStorageError } from '@/server/media/s3';
import { handleMediaUploadRequest } from '@/server/media/upload';

/**
 * D-172 §2.1 / Phase 5 — the filesystem media provider, entirely offline.
 *
 * What is asserted, and why each one matters for the pilot:
 *   1. `MEDIA_PROVIDER=local` resolves from `MEDIA_LOCAL_DIR` and needs no S3
 *      value; a missing directory, an unknown provider or a production build is a
 *      refusal (D-171 §2.2 — configuration gaps never become a pass).
 *   2. A stored file is content-addressed and idempotent, so re-uploading the
 *      same bytes cannot fill the disk with copies.
 *   3. Non-images and oversized files are refused BEFORE a write, and the
 *      `GET /media/…` reader cannot be walked out of its directory.
 *   4. The upload handler + adapter + reader agree end-to-end on a real
 *      temporary directory (no mocks between them).
 *
 * The tests use a throwaway `mkdtemp` directory: nothing outside it is read or
 * written.
 */

const PNG = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d]);
const JPEG = Uint8Array.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46]);
const WEBP = Uint8Array.from([
  0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x45, 0x42, 0x50, 0x56, 0x50, 0x38, 0x20,
]);

function env(directory: string, overrides: MediaEnvironment = {}): MediaEnvironment {
  return {
    MEDIA_PROVIDER: MEDIA_PROVIDER_LOCAL,
    MEDIA_LOCAL_DIR: directory,
    MEDIA_LOCAL_UPLOAD_ENABLED: 'true',
    NODE_ENV: 'development',
    ...overrides,
  };
}

function sha256(bytes: Uint8Array): string {
  return createHash('sha256').update(bytes).digest('hex');
}

let root = '';

before(async () => {
  root = await mkdtemp(path.join(tmpdir(), 'commerce-media-'));
});

after(async () => {
  await rm(root, { recursive: true, force: true });
});

describe('local media — resolver (§2.1)', () => {
  it('resolves a filesystem adapter without any S3 value', () => {
    const directory = path.join(root, 'resolve');
    const adapter = resolveMediaAdapter(env(directory));
    assert.notEqual(adapter, null);
    assert.equal(mediaUploadAllowed(env(directory)), true);
    assert.equal(resolveLocalMediaDirectory(env(directory)), directory);
  });

  it('requires the upload edge switch to be exactly "true"', () => {
    const directory = path.join(root, 'edge');
    assert.equal(mediaUploadAllowed(env(directory)), true);
    assert.equal(mediaUploadAllowed(env(directory, { MEDIA_LOCAL_UPLOAD_ENABLED: 'TRUE' })), false);
    assert.equal(mediaUploadAllowed(env(directory, { MEDIA_LOCAL_UPLOAD_ENABLED: 'false' })), false);
    assert.equal(mediaUploadAllowed(env(directory, { MEDIA_LOCAL_UPLOAD_ENABLED: undefined })), false);
  });

  it('refuses a missing directory, the filesystem root, an unknown provider or a production build', () => {
    assert.equal(resolveMediaAdapter(env('', { MEDIA_LOCAL_DIR: '' })), null);
    assert.equal(resolveMediaAdapter(env('/', { MEDIA_LOCAL_DIR: '/' })), null);
    assert.equal(resolveMediaAdapter(env(path.join(root, 'x'), { MEDIA_PROVIDER: 'files' })), null);
    assert.equal(resolveMediaAdapter(env(path.join(root, 'x'), { MEDIA_PROVIDER: undefined })), null);
    assert.equal(
      resolveMediaAdapter(env(path.join(root, 'x'), { NODE_ENV: ' Production ' })),
      null,
    );
    assert.equal(resolveLocalMediaDirectory(env(path.join(root, 'x'), { MEDIA_PROVIDER: 's3' })), null);
  });

  it('resolves a relative directory against the process cwd, never as a bare name', () => {
    const resolved = resolveLocalMediaDirectory(
      env('', { MEDIA_LOCAL_DIR: '.media-data' }),
    );
    assert.equal(resolved, path.resolve('.media-data'));
  });
});

describe('local media — content-addressed writes', () => {
  it('stores bytes under products/sha256/<prefix>/<hash>.<ext> and serves /media/…', async () => {
    const directory = path.join(root, 'store');
    const adapter = createLocalMediaAdapter({ directory });

    const stored = await adapter.put(
      { fileName: 'photo.png', contentType: 'image/png', byteLength: PNG.byteLength },
      PNG,
    );

    const hash = sha256(PNG);
    assert.equal(stored.storagePath, `products/sha256/${hash.slice(0, 2)}/${hash}.png`);
    assert.equal(stored.publicUrl, `/media/${stored.storagePath}`);
    assert.equal(stored.duplicate, false);

    const written = await readFile(path.join(directory, stored.storagePath));
    assert.deepEqual(new Uint8Array(written), PNG);
  });

  it('is idempotent for identical bytes and derives the extension from the bytes', async () => {
    const directory = path.join(root, 'idempotent');
    const adapter = createLocalMediaAdapter({ directory });

    const first = await adapter.put(
      { fileName: 'evil.html', contentType: 'text/html', byteLength: JPEG.byteLength },
      JPEG,
    );
    const second = await adapter.put(
      { fileName: 'renamed.jpg', contentType: 'image/jpeg', byteLength: JPEG.byteLength },
      JPEG,
    );

    assert.match(first.storagePath, /\.jpg$/);
    assert.equal(second.storagePath, first.storagePath);
    assert.equal(first.duplicate, false);
    assert.equal(second.duplicate, true);

    const webp = await adapter.put(
      { fileName: 'x.png', contentType: 'image/png', byteLength: WEBP.byteLength },
      WEBP,
    );
    assert.match(webp.storagePath, /\.webp$/);
  });

  it('writes nothing for a non-image or a length mismatch', async () => {
    const directory = path.join(root, 'refusals');
    const adapter = createLocalMediaAdapter({ directory });

    await assert.rejects(
      adapter.put(
        { fileName: 'note.txt', contentType: 'text/plain', byteLength: 4 },
        Uint8Array.from([0x74, 0x65, 0x78, 0x74]),
      ),
      (error: unknown) => error instanceof MediaValidationError && error.status === 415,
    );

    await assert.rejects(
      adapter.put({ fileName: 'a.jpg', contentType: 'image/jpeg', byteLength: 1 }, JPEG),
      MediaStorageError,
    );

    const entries = await readdir(directory).catch(() => [] as string[]);
    assert.deepEqual(entries, []);
  });
});

describe('local media — read edge (§2.1)', () => {
  it('serves a stored image with its verified content type', async () => {
    const directory = path.join(root, 'reader');
    const adapter = createLocalMediaAdapter({ directory });
    const stored = await adapter.put(
      { fileName: 'a.png', contentType: 'image/png', byteLength: PNG.byteLength },
      PNG,
    );

    const segments = stored.storagePath.split('/');
    const file = await readLocalMediaFile(directory, segments);
    assert.ok(file);
    assert.equal(file?.contentType, 'image/png');
    assert.deepEqual(new Uint8Array(file?.bytes ?? []), PNG);
  });

  it('refuses traversal, unknown extensions, missing files and absurd depth', async () => {
    const directory = path.join(root, 'traversal');
    const adapter = createLocalMediaAdapter({ directory });
    const stored = await adapter.put(
      { fileName: 'a.png', contentType: 'image/png', byteLength: PNG.byteLength },
      PNG,
    );
    const inside = await readLocalMediaFile(directory, stored.storagePath.split('/'));
    assert.ok(inside);

    // A secret next to the store must stay unreachable through any spelling.
    const secretName = 'secret.png';
    await writeFile(path.join(root, secretName), PNG);

    for (const segments of [
      ['..', secretName],
      ['products', '..', '..', secretName],
      ['', '..', secretName],
      ['/etc/passwd'],
      ['products', 'sha256', '00', `${'0'.repeat(64)}.html`],
      ['products', 'sha256', '00', 'missing.png'],
      ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
    ]) {
      assert.equal(await readLocalMediaFile(directory, segments), null, segments.join('/'));
    }
    assert.equal(resolveMediaFilePath(directory, ['..', secretName]), null);
    assert.equal(resolveMediaFilePath(directory, stored.storagePath.split('/')), path.join(directory, stored.storagePath));
  });

  it('serves nothing when the provider is not the local filesystem', async () => {
    const directory = path.join(root, 'reader');
    const adapter = createLocalMediaAdapter({ directory });
    const stored = await adapter.put(
      { fileName: 'a.png', contentType: 'image/png', byteLength: PNG.byteLength },
      PNG,
    );

    // The route asks the resolver, not the adapter; with S3 selected it 404s.
    assert.equal(resolveLocalMediaDirectory(env(directory, { MEDIA_PROVIDER: 's3' })), null);
    const segments = stored.storagePath.split('/');
    assert.equal(resolveMediaFilePath(directory, segments) !== null, true);
  });
});

describe('local media — upload edge end to end', () => {
  function uploadRequest(bytes: Uint8Array, name = 'photo.png'): Request {
    const payload = new Uint8Array(bytes.byteLength);
    payload.set(bytes);
    const form = new FormData();
    form.set('file', new File([payload], name, { type: 'application/octet-stream' }));
    return new Request('http://127.0.0.1:3000/api/admin/media', { method: 'POST', body: form });
  }

  it('stores through the handler and reads back the same bytes', async () => {
    const directory = path.join(root, 'e2e');
    const response = await handleMediaUploadRequest(uploadRequest(PNG), {
      env: env(directory),
      adapter: undefined,
    });

    assert.equal(response.status, 200);
    const body = (await response.json()) as { storagePath: string; publicUrl: string; duplicate: boolean };
    assert.equal(body.duplicate, false);
    assert.equal(body.publicUrl, `/media/${body.storagePath}`);

    const served = await readLocalMediaFile(directory, body.storagePath.split('/'));
    assert.ok(served);
    assert.deepEqual(new Uint8Array(served?.bytes ?? []), PNG);
  });

  it('refuses a non-image with 415 and an oversized file with 413, writing neither', async () => {
    const directory = path.join(root, 'e2e-refusals');

    const nonImage = await handleMediaUploadRequest(
      uploadRequest(new TextEncoder().encode('<svg xmlns="http://www.w3.org/2000/svg"/>'), 'x.svg'),
      { env: env(directory), adapter: undefined },
    );
    assert.equal(nonImage.status, 415);

    const oversized = new Uint8Array(MAX_IMAGE_BYTES + 1);
    oversized.set(PNG);
    const tooLarge = await handleMediaUploadRequest(uploadRequest(oversized, 'big.png'), {
      env: env(directory),
      adapter: undefined,
    });
    assert.equal(tooLarge.status, 413);

    const entries = await readdir(directory).catch(() => [] as string[]);
    assert.deepEqual(entries, []);
  });
});
