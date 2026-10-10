import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

/**
 * D-172 Phase 2 hardening — the client/server boundary, as an executable guard.
 *
 * The merchant panel's separation is structural: `@/db` and `@/server/**` own
 * PostgreSQL (they import `pg`/`drizzle-orm`), and nothing the browser receives
 * may pull them in. The ONLY value import a `'use client'` module may take from
 * `@/server` is the server-action edge (`@/server/actions/*`), which is what
 * `'use server'` exists for. Everything else — services, repository, db-context,
 * media — must be TYPE-ONLY, because a type import is erased and ships no code.
 *
 * This is asserted statically because the failure mode is silent: a stray value
 * import succeeds in dev (Next can bundle it), then ships a database client to
 * the browser or breaks the build in a way that is easy to paper over. A gate
 * makes the boundary a fact rather than a convention.
 *
 * The scan counts what it inspected and fails if that count collapses, so the
 * guard cannot pass vacuously when the tree moves or the directive changes.
 */

const SRC = fileURLToPath(new URL('../../src/', import.meta.url));
const IMPORT_RE = /^\s*import\b([\s\S]*?)from\s+['"]([^'"]+)['"]/gm;
const CLIENT_DIRECTIVE = /^\s*(['"])use client\1\s*;?/m;

interface Violation {
  file: string;
  specifier: string;
  clause: string;
}

async function sourceFiles(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  const found: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...(await sourceFiles(full)));
    } else if (/\.tsx?$/.test(entry.name)) {
      found.push(full);
    }
  }
  return found;
}

describe('D-172 — client bundles never import the server/database layer', () => {
  it('allows only the server-action edge and type-only imports in "use client" modules', async () => {
    const files = await sourceFiles(SRC);
    const clientFiles: string[] = [];
    const violations: Violation[] = [];

    for (const file of files) {
      const source = await readFile(file, 'utf8');
      if (!CLIENT_DIRECTIVE.test(source)) {
        continue;
      }
      clientFiles.push(path.relative(SRC, file));

      for (const match of source.matchAll(IMPORT_RE)) {
        const clause = match[1] ?? '';
        const specifier = match[2] ?? '';
        const fromServerLayer = specifier.startsWith('@/db') || specifier.startsWith('@/server');
        if (!fromServerLayer) {
          continue;
        }
        if (specifier.startsWith('@/server/actions/')) {
          continue; // the 'use server' edge is the one sanctioned crossing
        }
        if (/^\s*type\b/.test(clause)) {
          continue; // erased at compile time — no code, no credential, no driver
        }
        violations.push({
          file: path.relative(SRC, file),
          specifier,
          clause: clause.replace(/\s+/g, ' ').trim(),
        });
      }
    }

    assert.deepEqual(violations, [], 'a client component value-imports the server/database layer');

    // Non-vacuous: the scan must actually have seen the client surface.
    assert.ok(files.length >= 40, `expected to scan the whole src tree, saw ${files.length} files`);
    assert.ok(
      clientFiles.length >= 8,
      `expected to find the client components, saw ${clientFiles.length}: ${clientFiles.join(', ')}`,
    );
  });

  it('keeps the database driver out of every file the browser can reach', async () => {
    const files = await sourceFiles(SRC);
    const clientFiles: string[] = [];
    for (const file of files) {
      const source = await readFile(file, 'utf8');
      if (CLIENT_DIRECTIVE.test(source)) {
        clientFiles.push(file);
      }
    }

    const offenders: string[] = [];
    for (const file of clientFiles) {
      const source = await readFile(file, 'utf8');
      if (/from\s+['"](pg|drizzle-orm|@\/db)['"]/.test(source)) {
        offenders.push(path.relative(SRC, file));
      }
    }

    assert.deepEqual(offenders, [], 'a client component imports the database driver/module directly');
    assert.equal(clientFiles.length >= 8, true);
  });
});
