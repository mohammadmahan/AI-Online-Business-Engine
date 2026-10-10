import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';

import {
  DB_NOT_CONFIGURED_MESSAGE,
  getRepository,
  isDatabaseConfigured,
  withRepository,
} from '@/server/db-context';

/**
 * D-172 §2 — the fail-closed connection gate (D-171 §2.2).
 *
 * The panel has no credential of its own (D-045), so "no DATABASE_URL" must be a
 * REFUSAL, not a silent fallback to a guessed instance, sample data or zeros.
 */
describe('database context — fail-closed gate', () => {
  const original = process.env.DATABASE_URL;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = original;
    }
  });

  it('reports no configuration and refuses work when DATABASE_URL is absent', async () => {
    delete process.env.DATABASE_URL;

    assert.equal(isDatabaseConfigured(), false);
    assert.equal(getRepository(), null);

    // The callback must never run: nothing may read or write without a target.
    let reached = false;
    const result = await withRepository(async () => {
      reached = true;
      return { ok: true as const, data: 'never' };
    });

    assert.equal(reached, false);
    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'DB_NOT_CONFIGURED');
    assert.ok(!result.ok && result.message === DB_NOT_CONFIGURED_MESSAGE);
  });

  it('treats a blank value as unconfigured rather than as a target', async () => {
    process.env.DATABASE_URL = '   ';

    assert.equal(isDatabaseConfigured(), false);
    assert.equal(getRepository(), null);
    const result = await withRepository(async () => ({ ok: true as const, data: 'never' }));
    assert.equal(result.ok, false);
  });

  it('resolves a cached repository once a connection string exists — without connecting', () => {
    process.env.DATABASE_URL = 'postgres://user:pass@127.0.0.1:5432/commerce_test';

    assert.equal(isDatabaseConfigured(), true);
    const first = getRepository();
    assert.notEqual(first, null);
    assert.equal(first, getRepository());
  });

  it('never echoes the driver message when the repository throws', async () => {
    process.env.DATABASE_URL = 'postgres://user:pass@127.0.0.1:5432/commerce_test';

    const result = await withRepository(async () => {
      throw new Error('password authentication failed for user "secret-value"');
    });

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'UNEXPECTED');
    assert.ok(!result.ok && !result.message.includes('secret-value'));
  });
});
