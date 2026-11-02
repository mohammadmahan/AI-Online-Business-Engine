#!/usr/bin/env node
/**
 * D-172 §2.1 / G-5 — LOCAL media bucket bootstrap.
 *
 * Creates the storefront's bucket in the EXISTING local MinIO service and sets a
 * read-only anonymous policy so the storefront's plain `<img>` URLs work. This
 * is a development convenience, not a migration and not a deployment step.
 *
 * FAIL-CLOSED GUARD: the target must be loopback on the local MinIO port
 * (19000). It cannot be aimed at a cloud endpoint or a shared host, there is no
 * flag that overrides it, and no credential is printed.
 *
 * Credentials come from the environment (the compose file's disposable local
 * literals). Nothing is hard-coded here and nothing is written to Git.
 *
 * Usage:
 *   composer() { ... }            # see commerce/README.md for the exact exports
 *   npm run media:bucket
 */
import {
  CreateBucketCommand,
  HeadBucketCommand,
  PutBucketPolicyCommand,
  S3Client,
} from '@aws-sdk/client-s3';

const LOCAL_MEDIA_PORT = '19000';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);
const BUCKET_RE = /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/;

function fail(message) {
  console.error(`media:bucket refused — ${message}`);
  process.exit(1);
}

function parseEndpoint(raw) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    fail('MEDIA_S3_ENDPOINT is not a parseable URL.');
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    fail('MEDIA_S3_ENDPOINT must be http(s).');
  }
  if (!LOOPBACK_HOSTS.has(url.hostname.toLowerCase()) || url.port !== LOCAL_MEDIA_PORT) {
    fail(
      `refusing a non-local target (host=${url.hostname} port=${url.port || 'default'}); ` +
        `only loopback:${LOCAL_MEDIA_PORT} is allowed.`,
    );
  }
  if (url.username !== '' || url.password !== '') {
    fail('MEDIA_S3_ENDPOINT must not carry credentials in the URL.');
  }
  if (url.pathname !== '/' && url.pathname !== '') {
    fail('MEDIA_S3_ENDPOINT must be the service origin, with no path.');
  }
  return url;
}

const rawEndpoint = process.env.MEDIA_S3_ENDPOINT?.trim();
if (!rawEndpoint) {
  fail('MEDIA_S3_ENDPOINT is not set. This script never guesses a target.');
}
const endpoint = parseEndpoint(rawEndpoint);

const bucket = process.env.MEDIA_S3_BUCKET?.trim();
if (!bucket || !BUCKET_RE.test(bucket) || bucket.includes('..')) {
  fail('MEDIA_S3_BUCKET is missing or not a valid local bucket name.');
}

const accessKeyId = process.env.MEDIA_S3_ACCESS_KEY?.trim();
const secretAccessKey = process.env.MEDIA_S3_SECRET_KEY?.trim();
if (!accessKeyId || !secretAccessKey) {
  fail('MEDIA_S3_ACCESS_KEY and MEDIA_S3_SECRET_KEY are required.');
}

const client = new S3Client({
  endpoint: endpoint.origin,
  region: process.env.MEDIA_S3_REGION?.trim() || 'us-east-1',
  forcePathStyle: true,
  credentials: { accessKeyId, secretAccessKey },
});

const status = (error) => (typeof error === 'object' && error !== null && '$metadata' in error
  ? error.$metadata?.httpStatusCode
  : undefined);
const name = (error) => (error instanceof Error ? error.name : 'UnknownError');

console.log(`media:bucket target = ${endpoint.hostname}:${endpoint.port} bucket=${bucket}`);

let created = false;
try {
  await client.send(new HeadBucketCommand({ Bucket: bucket }));
} catch (error) {
  if (status(error) === 404 || name(error) === 'NotFound') {
    try {
      await client.send(new CreateBucketCommand({ Bucket: bucket }));
      created = true;
    } catch (createError) {
      console.error(`media:bucket failed — bucket was not created (${name(createError)}).`);
      process.exit(1);
    }
  } else {
    console.error(
      `media:bucket failed — MinIO is not reachable or refused the request (${name(error)}).`,
    );
    process.exit(1);
  }
}

const policy = {
  Version: '2012-10-17',
  Statement: [
    {
      Sid: 'LocalCatalogPublicRead',
      Effect: 'Allow',
      Principal: '*',
      Action: ['s3:GetObject'],
      Resource: [`arn:aws:s3:::${bucket}/*`],
    },
  ],
};

try {
  await client.send(
    new PutBucketPolicyCommand({
      Bucket: bucket,
      Policy: JSON.stringify(policy),
    }),
  );
} catch (error) {
  console.error(`media:bucket failed — the public read policy was not applied (${name(error)}).`);
  process.exit(1);
}

console.log(`media:bucket bucket = ${created ? 'created' : 'already present'}`);
console.log('media:bucket policy = anonymous read-only on the bucket (loopback only)');
