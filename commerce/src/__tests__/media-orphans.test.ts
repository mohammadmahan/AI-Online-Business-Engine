import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, rm, stat, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, describe, it } from 'node:test';

/**
 * D-172 §2.1 / Phase 5 — the LOCAL orphan-media dry run.
 *
 * The runner is READ-ONLY by construction: it has no delete path and no write
 * call. These tests drive its real functions against throwaway directories and
 * an injected pool stub, so they can prove the properties that matter without a
 * database or a live store:
 *
 *  - a referenced key is never a candidate, whichever product owns it and even
 *    when several rows share it;
 *  - an unreferenced key is a candidate with its exact bytes;
 *  - malformed keys, symlinks and unexpected entries are reported as
 *    NOT classifiable, never as safe candidates;
 *  - the environment gate refuses an unsupported provider, a missing/unsafe
 *    root, a production build and a missing or non-loopback database;
 *  - the scanner follows no link and mutates nothing (names, sizes, mtimes and
 *    content are compared before and after);
 *  - the reference read is one plain SELECT with no status filter, so DRAFT and
 *    ARCHIVED products' images count as references.
 */

interface OrphanModule {
  RETENTION_NOTE: string;
  CLEANUP_SAFEGUARDS: string[];
  REFERENCE_QUERY: string;
  isStoredMediaKey(key: string): boolean;
  resolveScanConfig(env: Record<string, string | undefined>):
    | { ok: true; root: string; database: { url: string; host: string; port: string } }
    | { ok: false; code: string; message: string };
  scanLocalMediaStore(root: string): Promise<Scan>;
  loadReferences(pool: {
    query(sql: string): Promise<{ rows: unknown[] }>;
  }): Promise<References>;
  buildOrphanReport(scan: ScanOk, references: ReferencesOk): Report;
}

interface ScanFile {
  key: string;
  bytes: number;
  modifiedAt: string;
}

interface ScanOk {
  ok: true;
  root: string;
  files: ScanFile[];
  malformedKeys: string[];
  symlinks: string[];
  unexpectedEntries: string[];
  nonRegularFiles: string[];
  storeTreeMissing: boolean;
}

type Scan = ScanOk | { ok: false; code: string; message: string };

interface ReferencesOk {
  ok: true;
  rowCount: number;
  keys: Set<string>;
  foreignReferenceRows: number;
}

type References = ReferencesOk | { ok: false; code: string; message: string };

interface Report {
  scannedFiles: number;
  scannedBytes: number;
  referenceRows: number;
  distinctReferencedKeys: number;
  foreignReferenceRows: number;
  referencedFilesOnDisk: number;
  referencedKeysMissingOnDisk: number;
  candidateCount: number;
  candidateBytes: number;
  candidates: Array<{ key: string; bytes: number; ageDays: number }>;
  malformedKeys: string[];
  symlinks: string[];
  unexpectedEntries: string[];
  nonRegularFiles: string[];
  storeTreeMissing: boolean;
}

const orphans = (await import(
  new URL('../../scripts/media-orphans.mjs', import.meta.url).href
)) as unknown as OrphanModule;

const roots: string[] = [];

after(async () => {
  await Promise.all(roots.map((root) => rm(root, { recursive: true, force: true })));
});

async function tempRoot(): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), 'commerce-orphans-'));
  roots.push(root);
  return root;
}

/** A valid content-addressed key; the bytes are irrelevant to the scanner. */
function keyFor(seed: string, extension = 'jpg'): string {
  const hash = createHash('sha256').update(seed).digest('hex');
  return `products/sha256/${hash.slice(0, 2)}/${hash}.${extension}`;
}

async function putFile(root: string, key: string, bytes = 'image-bytes'): Promise<void> {
  const absolute = path.join(root, key);
  await mkdir(path.dirname(absolute), { recursive: true });
  await writeFile(absolute, bytes);
}

function references(keys: string[], rowCount = keys.length): ReferencesOk {
  return { ok: true, rowCount, keys: new Set(keys), foreignReferenceRows: 0 };
}

async function scanOk(root: string): Promise<ScanOk> {
  const scan = await orphans.scanLocalMediaStore(root);
  assert.equal(scan.ok, true, JSON.stringify(scan));
  return scan as ScanOk;
}

const ENV = {
  MEDIA_PROVIDER: 'local',
  MEDIA_LOCAL_DIR: '/tmp/media-root',
  DATABASE_URL: 'postgresql://user:secret@127.0.0.1:55433/commerce_local',
  NODE_ENV: 'development',
};

/** Every mutation-relevant fact about a tree, for the no-write assertion. */
async function treeSnapshot(root: string): Promise<string[]> {
  const rows: string[] = [];
  async function walk(directory: string): Promise<void> {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const absolute = path.join(directory, entry.name);
      const info = await stat(absolute);
      const digest = entry.isFile() ? createHash('sha256').update(await readFile(absolute)).digest('hex') : '-';
      rows.push(
        `${path.relative(root, absolute)}|${entry.isFile() ? 'file' : 'dir'}|${info.size}|${info.mtimeMs}|${digest}`,
      );
      if (entry.isDirectory()) {
        await walk(absolute);
      }
    }
  }
  await walk(root);
  return rows.sort();
}

describe('§2.1 local media orphan dry run — classification', () => {
  it('never counts a referenced file, and counts an unreferenced one with its bytes', async () => {
    const root = await tempRoot();
    const referenced = keyFor('referenced');
    const orphan = keyFor('orphan');
    await putFile(root, referenced, 'twelve bytes');
    await putFile(root, orphan, 'orphan-bytes');

    const report = orphans.buildOrphanReport(await scanOk(root), references([referenced]));

    assert.equal(report.scannedFiles, 2);
    assert.equal(report.referencedFilesOnDisk, 1);
    assert.equal(report.candidateCount, 1);
    assert.equal(report.candidates[0]?.key, orphan);
    assert.equal(report.candidateBytes, Buffer.byteLength('orphan-bytes'));
    assert.deepEqual(report.malformedKeys, []);
  });

  it('treats a key shared by several rows as referenced once, under any owner', async () => {
    const root = await tempRoot();
    const shared = keyFor('shared');
    await putFile(root, shared);

    // Two products, two rows, one storage_path — still referenced.
    const report = orphans.buildOrphanReport(await scanOk(root), references([shared, shared]));

    assert.equal(report.referenceRows, 2);
    assert.equal(report.distinctReferencedKeys, 1);
    assert.equal(report.candidateCount, 0);
    assert.equal(report.referencedFilesOnDisk, 1);
  });

  it('lists every file when the gallery set is empty', async () => {
    const root = await tempRoot();
    await putFile(root, keyFor('empty-a'), 'aaaa');
    await putFile(root, keyFor('empty-b'), 'bbbbbb');

    const report = orphans.buildOrphanReport(await scanOk(root), references([]));

    assert.equal(report.candidateCount, 2);
    assert.equal(report.candidateBytes, 10);
    assert.equal(report.referenceRows, 0);
  });

  it('reports referenced keys that are no longer on disk without calling them candidates', async () => {
    const root = await tempRoot();
    const missing = keyFor('missing');
    await putFile(root, keyFor('present'));

    const report = orphans.buildOrphanReport(await scanOk(root), references([missing]));

    assert.equal(report.referencedKeysMissingOnDisk, 1);
    assert.equal(report.candidateCount, 1);
  });

  it('never classifies a malformed key as a safe candidate', async () => {
    const root = await tempRoot();
    const valid = keyFor('valid');
    const wrongShard = keyFor('wrong-shard').replace(
      /^products\/sha256\/(..)\//,
      'products/sha256/zz/',
    );
    const wrongExtension = keyFor('gif', 'gif');
    const shortHash = 'products/sha256/ab/abc.jpg';
    const traversal = 'products/sha256/ab/../../../../etc/passwd';
    for (const key of [valid, wrongShard, wrongExtension, shortHash]) {
      await putFile(root, key);
    }

    const scan = await scanOk(root);
    const report = orphans.buildOrphanReport(scan, references([]));

    assert.equal(report.candidateCount, 1);
    assert.equal(report.candidates[0]?.key, valid);
    assert.ok(report.malformedKeys.includes(wrongExtension));
    assert.ok(report.malformedKeys.includes(shortHash));
    assert.equal(orphans.isStoredMediaKey(traversal), false);
    assert.equal(orphans.isStoredMediaKey('/etc/passwd'), false);
    assert.equal(orphans.isStoredMediaKey(wrongShard), false);
  });

  it('reports a symlinked FILE without following it', async () => {
    const root = await tempRoot();
    const outside = await tempRoot();
    const outsideFile = path.join(outside, 'outside.jpg');
    await writeFile(outsideFile, 'outside-bytes');
    const linkKey = keyFor('symlink-file');
    await mkdir(path.join(root, path.dirname(linkKey)), { recursive: true });
    await symlink(outsideFile, path.join(root, linkKey));

    const scan = await scanOk(root);
    const report = orphans.buildOrphanReport(scan, references([]));

    assert.equal(report.candidateCount, 0, 'a link is never a deletion candidate');
    assert.ok(report.symlinks.includes(linkKey));
  });

  it('reports a symlinked shard DIRECTORY and never walks through it', async () => {
    const root = await tempRoot();
    const outside = await tempRoot();
    const outsideKey = keyFor('symlink-dir-target');
    await putFile(outside, outsideKey);
    await mkdir(path.join(root, 'products/sha256'), { recursive: true });
    const shard = outsideKey.split('/')[2] as string;
    await symlink(path.join(outside, 'products/sha256', shard), path.join(root, 'products/sha256/aa'));

    const scan = await scanOk(root);
    const report = orphans.buildOrphanReport(scan, references([]));

    assert.equal(report.candidateCount, 0);
    assert.ok(report.symlinks.some((entry) => entry.startsWith('products/sha256/')));
  });

  it('refuses a symlinked media root and an unexpected depth', async () => {
    const real = await tempRoot();
    await putFile(real, keyFor('root-target'));
    const linkParent = await tempRoot();
    const linkedRoot = path.join(linkParent, 'linked');
    await symlink(real, linkedRoot);

    const refused = await orphans.scanLocalMediaStore(linkedRoot);
    assert.equal(refused.ok, false);
    assert.equal((refused as { code: string }).code, 'UNSAFE_MEDIA_ROOT');

    const root = await tempRoot();
    const nested = keyFor('nested');
    await putFile(root, nested);
    await mkdir(path.join(root, 'products/sha256/aa/nested-dir'), { recursive: true });
    const scan = await scanOk(root);
    const report = orphans.buildOrphanReport(scan, references([]));
    assert.ok(report.unexpectedEntries.some((entry) => entry.endsWith('nested-dir')));
    assert.equal(report.candidateCount, 1, 'only the valid file is a candidate');
  });

  it('reports a missing store tree as zero files, not as an error or a cleanup signal', async () => {
    const root = await tempRoot();

    const scan = await scanOk(root);
    const report = orphans.buildOrphanReport(scan, references([]));

    assert.equal(report.scannedFiles, 0);
    assert.equal(report.candidateCount, 0);
    assert.equal(report.storeTreeMissing, true);
  });

  it('refuses a missing media root', async () => {
    const scan = await orphans.scanLocalMediaStore(path.join(tmpdir(), 'commerce-orphans-does-not-exist'));
    assert.equal(scan.ok, false);
    assert.equal((scan as { code: string }).code, 'MEDIA_ROOT_MISSING');
  });

  it('makes no writes and no deletes', async () => {
    const root = await tempRoot();
    await putFile(root, keyFor('stable-a'), 'a');
    await putFile(root, keyFor('stable-b'), 'bb');
    const before = await treeSnapshot(root);

    const scan = await scanOk(root);
    orphans.buildOrphanReport(scan, references([]));

    assert.deepEqual(await treeSnapshot(root), before);
  });
});

describe('§2.1 local media orphan dry run — environment gate', () => {
  const cases: Array<[string, Record<string, string | undefined>, string]> = [
    ['an unsupported provider (s3)', { ...ENV, MEDIA_PROVIDER: 's3' }, 'UNSUPPORTED_PROVIDER'],
    ['an unknown provider', { ...ENV, MEDIA_PROVIDER: 'files' }, 'UNSUPPORTED_PROVIDER'],
    ['an unset provider', { ...ENV, MEDIA_PROVIDER: undefined }, 'UNSUPPORTED_PROVIDER'],
    ['a production build', { ...ENV, NODE_ENV: 'production' }, 'PRODUCTION_BUILD'],
    ['a missing media root', { ...ENV, MEDIA_LOCAL_DIR: '  ' }, 'MEDIA_ROOT_MISSING'],
    ['the filesystem root', { ...ENV, MEDIA_LOCAL_DIR: '/' }, 'UNSAFE_MEDIA_ROOT'],
    ['no database target', { ...ENV, DATABASE_URL: undefined }, 'DATABASE_TARGET_MISSING'],
    ['a malformed database URL', { ...ENV, DATABASE_URL: 'not a url' }, 'DATABASE_TARGET_UNSAFE'],
    ['a non-PostgreSQL URL', { ...ENV, DATABASE_URL: 'mysql://127.0.0.1/db' }, 'DATABASE_TARGET_UNSAFE'],
    [
      'a remote database',
      { ...ENV, DATABASE_URL: 'postgresql://user:secret@db.example.com:5432/commerce' },
      'DATABASE_TARGET_UNSAFE',
    ],
  ];

  for (const [name, env, code] of cases) {
    it(`refuses ${name}`, () => {
      const config = orphans.resolveScanConfig(env);
      assert.equal(config.ok, false);
      assert.equal((config as { code: string }).code, code);
    });
  }

  it('accepts the local provider with a loopback database and exposes only its target', () => {
    const config = orphans.resolveScanConfig(ENV);
    assert.equal(config.ok, true);
    if (!config.ok) return;
    assert.equal(config.root, '/tmp/media-root');
    assert.equal(config.database.host, '127.0.0.1');
    assert.equal(config.database.port, '55433');
  });
});

describe('§2.1 local media orphan dry run — reference read', () => {
  it('reads EVERY product_image row in one plain SELECT (DRAFT and ARCHIVED included)', async () => {
    const queries: string[] = [];
    const result = await orphans.loadReferences({
      async query(sql: string) {
        queries.push(sql);
        return { rows: [{ storage_path: keyFor('draft') }, { storage_path: keyFor('archived') }] };
      },
    });

    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.equal(result.rowCount, 2);
    assert.equal(result.keys.size, 2);
    assert.equal(queries.length, 1);
    assert.match(queries[0] as string, /^\s*select/i);
    assert.match(queries[0] as string, /commerce\.product_images/);
    assert.doesNotMatch(queries[0] as string, /status|limit|insert|update|delete/i);
  });

  it('counts a legacy non-store reference without classifying it', async () => {
    const result = await orphans.loadReferences({
      async query() {
        return {
          rows: [
            { storage_path: keyFor('store') },
            { storage_path: 'https://cdn.example/legacy.jpg' },
          ],
        };
      },
    });

    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.equal(result.foreignReferenceRows, 1);
    assert.equal(result.keys.size, 1);
  });

  it('refuses when the database answers with an unexpected shape', async () => {
    const result = await orphans.loadReferences({
      async query() {
        return { rows: [{ nope: 1 }] };
      },
    });
    assert.equal(result.ok, false);
    assert.equal((result as { code: string }).code, 'DATABASE_RESPONSE_UNEXPECTED');
  });

  it('refuses when the database is unavailable', async () => {
    const result = await orphans.loadReferences({
      async query() {
        throw new Error('connect ECONNREFUSED');
      },
    });
    assert.equal(result.ok, false);
    assert.equal((result as { code: string }).code, 'DATABASE_UNAVAILABLE');
  });
});
