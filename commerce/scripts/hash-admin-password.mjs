#!/usr/bin/env node
/**
 * D-172 Phase 4 — produce ADMIN_PASSWORD_HASH for the single merchant identity.
 *
 *   npm run admin:hash -- 'the password'
 *   npm run admin:hash                # reads one line from stdin (not echoed)
 *
 * The output is `scrypt:N:r:p:saltHex:keyHex` (colon-delimited so neither Docker
 * Compose nor Next.js expands part of it as `$variable`), exactly the format
 * `verifyAdminPassword` in `src/server/auth/admin-auth.ts` accepts; a test asserts
 * the two agree, so this script cannot drift from the verifier silently.
 *
 * The password is NEVER written to disk or to the repository by this script: it
 * prints the hash for you to paste into `commerce/.env` (gitignored). The local
 * `.env` is the only place it belongs (D-045/D-124 govern real credentials; this
 * is a loopback-only operator password, and it is still never committed).
 *
 * Passing the password as an argument leaves it in your shell history. For a
 * value you care about, use the stdin form.
 */
import { randomBytes, scryptSync } from 'node:crypto';
import { createInterface } from 'node:readline';

// Kept in sync with admin-auth.ts (asserted by src/server/auth/admin-auth.test.ts).
const N = 16_384;
const R = 8;
const P = 1;
const KEY_LENGTH = 32;

function hash(password) {
  const salt = randomBytes(16);
  const key = scryptSync(password, salt, KEY_LENGTH, { N, r: R, p: P });
  return ['scrypt', N, R, P, salt.toString('hex'), key.toString('hex')].join(':');
}

async function readStdinLine() {
  if (process.stdin.isTTY) {
    process.stderr.write('ADMIN password (input is shown): ');
  }
  const rl = createInterface({ input: process.stdin, output: process.stderr });
  const line = await new Promise((resolve) => rl.once('line', resolve));
  rl.close();
  return line;
}

const argument = process.argv[2];
const password = argument !== undefined ? argument : await readStdinLine();

if (typeof password !== 'string' || password.length === 0) {
  process.stderr.write('A non-empty password is required.\n');
  process.exit(1);
}

process.stdout.write(`${hash(password)}\n`);
