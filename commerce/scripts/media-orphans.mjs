#!/usr/bin/env node
/**
 * D-172 §2.1 / Phase 5 (local media) — READ-ONLY orphan-media dry run.
 *
 * POLICY: unreferenced media is RETAINED by default. Removing a
 * `product_images` association never deletes bytes, because keys are
 * content-addressed and may be shared between products. This script only
 * REPORTS; it has no delete path, no flag to enable one, and no way to "clean".
 * A future destructive cleanup needs its own owner decision and safety review.
 *
 * What it does:
 *  1. validates the environment (local filesystem provider only, an explicit
 *     non-root directory, a loopback PostgreSQL target) and refuses otherwise;
 *  2. reads the COMPLETE set of `commerce.product_images.storage_path` values
 *     with one SELECT — every status, DRAFT and ARCHIVED included, because a
 *     draft product's images are still referenced;
 *  3. walks exactly `<MEDIA_LOCAL_DIR>/products/sha256/<2 hex>/<hash>.<ext>`,
 *     never following a symlink, never descending past that layout;
 *  4. reports the valid content-addressed files no row references, their total
 *     bytes and (optionally) age, and separately counts everything it could NOT
 *     classify so nothing is silently called safe.
 *
 * What it does NOT do: connect to MinIO/S3, touch the database, read or write
 * media bytes, change permissions or timestamps, expose an HTTP surface, or
 * claim that absence of a reference makes deletion safe later. A dry run is a
 * point-in-time observation, not authorization.
 *
 * Usage:
 *   DATABASE_URL=postgresql://…@127.0.0.1:55433/commerce_local \
 *   MEDIA_PROVIDER=local MEDIA_LOCAL_DIR=./.media-data \
 *     npm run media:orphans            # human summary
 *     npm run media:orphans -- --json  # machine-readable
 *
 * Exit codes: 0 report produced (with or without candidates) · 2 configuration
 * refusal · 3 database unavailable/refused · 4 unsafe media tree.
 */
import { createHash } from 'node:crypto';
import { lstat, readdir, realpath } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

/* ------------------------------------------------------------------ policy */

const STORAGE_KEY_RE =
  /^products\/sha256\/([0-9a-f]{2})\/([0-9a-f]{64})\.(jpg|png|webp)$/;
const SHARD_RE = /^[0-9a-f]{2}$/;
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);
const STORE_TREE = ['products', 'sha256'];

export const RETENTION_NOTE =
  'Unreferenced media is RETAINED by default. This report is a point-in-time ' +
  'observation, not authorization to delete; candidates may become referenced ' +
  'again and files may be shared.';

export const CLEANUP_SAFEGUARDS = [
  'a verified backup of both the media root and the database',
  'a quiesced or coordinated writer (no uploads/gallery saves during the sweep)',
  'a fresh reference check immediately before any deletion, not a reused report',
  'explicit owner approval for that specific destructive run (PROJECT_RULES §3)',
];

/** True only for a key this store itself writes. */
export function isStoredMediaKey(key) {
  const match = STORAGE_KEY_RE.exec(key);
  return match !== null && match[2].startsWith(match[1]);
}

/**
 * Environment → scan configuration, or a refusal. Every refusal is explicit:
 * an absent or ambiguous setting is never interpreted as a default.
 */
export function resolveScanConfig(env = process.env) {
  const provider = (env.MEDIA_PROVIDER ?? '').trim().toLowerCase();
  if (provider !== 'local') {
    return {
      ok: false,
      code: 'UNSUPPORTED_PROVIDER',
      message:
        'this dry run audits the LOCAL filesystem provider only; set MEDIA_PROVIDER=local. ' +
        'MinIO/S3 needs its own inventory and is not covered here',
    };
  }

  if ((env.NODE_ENV ?? '').trim().toLowerCase() === 'production') {
    return {
      ok: false,
      code: 'PRODUCTION_BUILD',
      message: 'the local filesystem provider does not resolve in a production build',
    };
  }

  const rawDirectory = (env.MEDIA_LOCAL_DIR ?? '').trim();
  if (rawDirectory === '') {
    return {
      ok: false,
      code: 'MEDIA_ROOT_MISSING',
      message: 'MEDIA_LOCAL_DIR is not set — the media root is never guessed',
    };
  }
  const root = path.resolve(rawDirectory);
  if (root === path.parse(root).root) {
    return {
      ok: false,
      code: 'UNSAFE_MEDIA_ROOT',
      message: 'MEDIA_LOCAL_DIR is the filesystem root; refusing to scan the whole machine',
    };
  }

  const rawUrl = (env.DATABASE_URL ?? '').trim();
  if (rawUrl === '') {
    return {
      ok: false,
      code: 'DATABASE_TARGET_MISSING',
      message: 'DATABASE_URL is not set — no references can be read, so nothing is classified',
    };
  }
  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return {
      ok: false,
      code: 'DATABASE_TARGET_UNSAFE',
      message: 'DATABASE_URL is not a parseable PostgreSQL URL',
    };
  }
  if (url.protocol !== 'postgres:' && url.protocol !== 'postgresql:') {
    return {
      ok: false,
      code: 'DATABASE_TARGET_UNSAFE',
      message: 'DATABASE_URL must be a PostgreSQL URL',
    };
  }
  if (!LOOPBACK_HOSTS.has(url.hostname.toLowerCase())) {
    return {
      ok: false,
      code: 'DATABASE_TARGET_UNSAFE',
      message:
        'DATABASE_URL host is not loopback — this report pairs a LOCAL media root with its ' +
        'own local database and refuses a remote target',
    };
  }

  return {
    ok: true,
    root,
    database: { url: rawUrl, host: url.hostname, port: url.port || '5432' },
  };
}

/* -------------------------------------------------------------------- scan */

function emptyScan() {
  return {
    files: [],
    malformedKeys: [],
    symlinks: [],
    unexpectedEntries: [],
    nonRegularFiles: [],
    storeTreeMissing: false,
  };
}

/**
 * Reads the store without ever following a link. Returns either a refusal or a
 * classified inventory; nothing is inferred from a name that does not match
 * the store's own key format.
 */
export async function scanLocalMediaStore(configuredRoot) {
  const root = path.resolve(configuredRoot);

  let rootStat;
  try {
    rootStat = await lstat(root);
  } catch {
    return {
      ok: false,
      code: 'MEDIA_ROOT_MISSING',
      message: 'the configured media root does not exist',
    };
  }
  if (rootStat.isSymbolicLink()) {
    return {
      ok: false,
      code: 'UNSAFE_MEDIA_ROOT',
      message: 'the configured media root is a symlink; refusing an ambiguous target',
    };
  }
  if (!rootStat.isDirectory()) {
    return {
      ok: false,
      code: 'UNSAFE_MEDIA_ROOT',
      message: 'the configured media root is not a directory',
    };
  }

  const realRoot = await realpath(root);
  // Canonicalise the root (a platform directory such as /var may itself be a
  // link) AFTER the symlink refusal above; only real directories are scanned.

  const scan = emptyScan();
  let current = realRoot;
  for (const segment of STORE_TREE) {
    current = path.join(current, segment);
    let stat;
    try {
      stat = await lstat(current);
    } catch {
      scan.storeTreeMissing = true;
      return { ok: true, root: realRoot, ...scan };
    }
    if (stat.isSymbolicLink() || !stat.isDirectory()) {
      return {
        ok: false,
        code: 'UNSAFE_MEDIA_TREE',
        message: `the store path segment "${segment}" is not a real directory; refusing to continue`,
      };
    }
  }

  const shardEntries = await readdir(current, { withFileTypes: true });
  for (const shard of shardEntries) {
    const shardRelative = `products/sha256/${shard.name}`;
    if (shard.isSymbolicLink()) {
      scan.symlinks.push(shardRelative);
      continue;
    }
    if (!shard.isDirectory() || !SHARD_RE.test(shard.name)) {
      scan.unexpectedEntries.push(shardRelative);
      continue;
    }

    const shardPath = path.join(current, shard.name);
    const entries = await readdir(shardPath, { withFileTypes: true });
    for (const entry of entries) {
      const relativeKey = `${shardRelative}/${entry.name}`;
      if (entry.isSymbolicLink()) {
        // Never stat through it: the link target may be outside the store.
        scan.symlinks.push(relativeKey);
        continue;
      }
      if (!entry.isFile()) {
        if (entry.isDirectory()) {
          scan.unexpectedEntries.push(relativeKey);
        } else {
          scan.nonRegularFiles.push(relativeKey);
        }
        continue;
      }
      if (!isStoredMediaKey(relativeKey)) {
        scan.malformedKeys.push(relativeKey);
        continue;
      }
      const stat = await lstat(path.join(shardPath, entry.name));
      if (!stat.isFile()) {
        scan.nonRegularFiles.push(relativeKey);
        continue;
      }
      scan.files.push({
        key: relativeKey,
        bytes: stat.size,
        modifiedAt: stat.mtime.toISOString(),
      });
    }
  }

  scan.files.sort((left, right) => left.key.localeCompare(right.key));
  scan.malformedKeys.sort();
  scan.symlinks.sort();
  scan.unexpectedEntries.sort();
  scan.nonRegularFiles.sort();
  return { ok: true, root: realRoot, ...scan };
}

/* -------------------------------------------------------------- references */

export const REFERENCE_QUERY =
  'select storage_path from commerce.product_images order by storage_path';

/**
 * The COMPLETE reference set: no status filter, no product filter, no limit.
 * One SELECT, no writes. `pool` is injected so a test can prove the SQL shape
 * without a server.
 */
export async function loadReferences(pool) {
  let rows;
  try {
    const result = await pool.query(REFERENCE_QUERY);
    rows = result.rows;
  } catch {
    return {
      ok: false,
      code: 'DATABASE_UNAVAILABLE',
      message: 'the reference query failed; nothing was classified',
    };
  }
  if (!Array.isArray(rows) || rows.some((row) => typeof row?.storage_path !== 'string')) {
    return {
      ok: false,
      code: 'DATABASE_RESPONSE_UNEXPECTED',
      message: 'the reference query returned an unexpected shape; nothing was classified',
    };
  }
  const keys = new Set();
  let foreign = 0;
  for (const row of rows) {
    if (isStoredMediaKey(row.storage_path)) {
      keys.add(row.storage_path);
    } else {
      foreign += 1;
    }
  }
  return { ok: true, rowCount: rows.length, keys, foreignReferenceRows: foreign };
}

/* ----------------------------------------------------------------- report */

export function buildOrphanReport(scan, references) {
  const scannedKeys = new Set(scan.files.map((file) => file.key));
  const candidates = scan.files.filter((file) => !references.keys.has(file.key));
  const referencedOnDisk = scan.files.filter((file) => references.keys.has(file.key));
  const missingOnDisk = [...references.keys].filter((key) => !scannedKeys.has(key));

  return {
    scannedFiles: scan.files.length,
    scannedBytes: scan.files.reduce((total, file) => total + file.bytes, 0),
    referenceRows: references.rowCount,
    distinctReferencedKeys: references.keys.size,
    foreignReferenceRows: references.foreignReferenceRows,
    referencedFilesOnDisk: referencedOnDisk.length,
    referencedKeysMissingOnDisk: missingOnDisk.length,
    referencedKeysMissingOnDiskSample: missingOnDisk.slice(0, 10),
    candidates: candidates.map((file) => ({
      key: file.key,
      bytes: file.bytes,
      modifiedAt: file.modifiedAt,
      ageDays: Math.floor((Date.now() - Date.parse(file.modifiedAt)) / 86_400_000),
    })),
    candidateCount: candidates.length,
    candidateBytes: candidates.reduce((total, file) => total + file.bytes, 0),
    malformedKeys: scan.malformedKeys,
    symlinks: scan.symlinks,
    unexpectedEntries: scan.unexpectedEntries,
    nonRegularFiles: scan.nonRegularFiles,
    storeTreeMissing: scan.storeTreeMissing,
  };
}

/* -------------------------------------------------------------------- main */

function fingerprint(value) {
  return createHash('sha256').update(value).digest('hex').slice(0, 12);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function refusal(code, message) {
  console.error(`[commerce] media orphan dry run refused — ${code}: ${message}`);
  const exitCode = code.startsWith('DATABASE_') ? 3 : code.startsWith('UNSAFE_MEDIA') ? 4 : 2;
  return exitCode;
}

async function main(argv) {
  const json = argv.includes('--json');
  const unknown = argv.filter((arg) => arg !== '--json');
  if (unknown.length > 0) {
    return refusal('BAD_ARGUMENT', `unknown argument(s): ${unknown.join(', ')}`);
  }

  const config = resolveScanConfig(process.env);
  if (!config.ok) {
    return refusal(config.code, config.message);
  }

  const scan = await scanLocalMediaStore(config.root);
  if (!scan.ok) {
    return refusal(scan.code, scan.message);
  }

  const pg = (await import('pg')).default;
  const pool = new pg.Pool({ connectionString: config.database.url, max: 1 });
  let references;
  try {
    references = await loadReferences(pool);
  } finally {
    await pool.end().catch(() => {});
  }
  if (!references.ok) {
    return refusal(references.code, references.message);
  }

  const report = buildOrphanReport(scan, references);
  const summary = {
    provider: 'local',
    mediaRoot: 'configured (absolute path withheld)',
    mediaRootFingerprint: fingerprint(config.root),
    database: `loopback:${config.database.port}`,
    ...report,
    policy: RETENTION_NOTE,
    cleanupSafeguards: CLEANUP_SAFEGUARDS,
    generatedAt: new Date().toISOString(),
  };

  if (json) {
    console.log(JSON.stringify(summary, null, 2));
    return 0;
  }

  console.log('[commerce] LOCAL media orphan dry run — READ ONLY');
  console.log(`  provider:                  ${summary.provider}`);
  console.log(`  media root:                ${summary.mediaRoot} (fingerprint ${summary.mediaRootFingerprint})`);
  console.log(`  database:                  ${summary.database}`);
  console.log(`  stored files:              ${report.scannedFiles} (${formatBytes(report.scannedBytes)})`);
  console.log(`  reference rows:            ${report.referenceRows} (${report.distinctReferencedKeys} distinct keys)`);
  if (report.foreignReferenceRows > 0) {
    console.log(`  non-store references:      ${report.foreignReferenceRows} row(s) — not part of this scan`);
  }
  console.log(`  referenced files on disk:  ${report.referencedFilesOnDisk}`);
  console.log(`  referenced keys not found: ${report.referencedKeysMissingOnDisk}`);
  console.log(
    `  UNREFERENCED CANDIDATES:   ${report.candidateCount} (${formatBytes(report.candidateBytes)})`,
  );
  for (const candidate of report.candidates) {
    console.log(`    - ${candidate.key}  ${formatBytes(candidate.bytes)}  age ${candidate.ageDays}d`);
  }
  if (report.candidates.length === 0) {
    console.log('    (none)');
  }
  console.log(
    `  not classified:            malformed=${report.malformedKeys.length} ` +
      `symlink=${report.symlinks.length} unexpected=${report.unexpectedEntries.length} ` +
      `non-regular=${report.nonRegularFiles.length}`,
  );
  for (const key of report.malformedKeys) console.log(`    ! malformed key: ${key}`);
  for (const key of report.symlinks) console.log(`    ! symlink (not followed): ${key}`);
  for (const key of report.unexpectedEntries) console.log(`    ! unexpected entry: ${key}`);
  for (const key of report.nonRegularFiles) console.log(`    ! non-regular file: ${key}`);
  if (report.storeTreeMissing) {
    console.log('  note: the store tree does not exist under this root; zero files is not a cleanup signal');
  }
  console.log(`  policy: ${RETENTION_NOTE}`);
  console.log('  This run performed no writes and no deletes.');
  return 0;
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;

if (invokedDirectly) {
  main(process.argv.slice(2))
    .then((code) => process.exit(code))
    .catch(() => {
      console.error('[commerce] media orphan dry run failed — unexpected error; nothing was changed');
      process.exit(1);
    });
}
