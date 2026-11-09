import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  expectedPublicUrl,
  storedImagePathProblem,
  validateStoredImageReference,
} from '@/server/media/reference';

/**
 * D-172 §2.1 — what a submitted image reference may be.
 *
 * This is the gate that keeps `product_images.public_url` pointing at the store
 * itself. Every case below is a forgery or a mistake that must be refused; the
 * positive cases are built from the EXACT key shape the two writers produce
 * (`media/local.ts`, `media/s3.ts`).
 */

const HASH = '9dc0e2ca386b75b5933c116b2b3c452932c0c76f32b0b218f1b14f71b883750c';
const PATH = `products/sha256/9d/${HASH}.jpg`;
const LOCAL_URL = `/media/${PATH}`;

const LOCAL_ENV = {
  NODE_ENV: 'development',
  MEDIA_PROVIDER: 'local',
  MEDIA_LOCAL_DIR: '/tmp/commerce-media-reference-test',
};

const S3_ENV = {
  NODE_ENV: 'development',
  MEDIA_S3_ENDPOINT: 'http://127.0.0.1:19000',
  MEDIA_S3_BUCKET: 'media',
  MEDIA_S3_ACCESS_KEY: 'local-only',
  MEDIA_S3_SECRET_KEY: 'local-only',
  MEDIA_PUBLIC_BASE_URL: 'http://127.0.0.1:19000/media',
};

describe('storedImagePathProblem', () => {
  it('accepts the content-addressed shape both writers produce', () => {
    assert.equal(storedImagePathProblem(PATH), null);
    assert.equal(storedImagePathProblem(`products/sha256/aa/${'a'.repeat(64)}.webp`), null);
  });

  it('refuses a prefix that disagrees with the hash', () => {
    assert.notEqual(storedImagePathProblem(`products/sha256/aa/${HASH}.jpg`), null);
  });

  it('refuses traversal, absolute paths, extra segments and non-image extensions', () => {
    for (const candidate of [
      `../${PATH}`,
      `/${PATH}`,
      `products/sha256/9d/${HASH}.svg`,
      `products/sha256/9d/${HASH}.jpg/extra`,
      `products/other/9d/${HASH}.jpg`,
      `products/sha256/9d/${HASH.toUpperCase()}.jpg`,
      `products/sha256/9d/${HASH}.jpg?x=1`,
    ]) {
      assert.notEqual(storedImagePathProblem(candidate), null, candidate);
    }
  });
});

describe('validateStoredImageReference — provider agreement', () => {
  it('accepts the local store’s own site-relative url', () => {
    assert.deepEqual(validateStoredImageReference(PATH, LOCAL_URL, LOCAL_ENV), { ok: true });
    assert.equal(expectedPublicUrl(PATH, LOCAL_ENV), LOCAL_URL);
  });

  it('accepts the S3/MinIO public base and refuses the local form there', () => {
    const s3Url = `http://127.0.0.1:19000/media/${PATH}`;
    assert.deepEqual(validateStoredImageReference(PATH, s3Url, S3_ENV), { ok: true });
    assert.equal(validateStoredImageReference(PATH, LOCAL_URL, S3_ENV).ok, false);
  });

  it('refuses a foreign origin, a query string and a different object under the right prefix', () => {
    for (const url of [
      `https://evil.example/${PATH}`,
      `${LOCAL_URL}?v=2`,
      `${LOCAL_URL}#frag`,
      LOCAL_URL.replace(HASH, 'a'.repeat(64)),
      `/media/products/sha256/aa/${HASH}.jpg`,
    ]) {
      assert.equal(validateStoredImageReference(PATH, url, LOCAL_ENV).ok, false, url);
    }
  });

  it('refuses everything when no provider is configured (or in production)', () => {
    assert.equal(validateStoredImageReference(PATH, LOCAL_URL, {}).ok, false);
    assert.equal(
      validateStoredImageReference(PATH, LOCAL_URL, { ...LOCAL_ENV, NODE_ENV: 'production' }).ok,
      false,
    );
    assert.equal(expectedPublicUrl(PATH, {}), null);
  });
});
