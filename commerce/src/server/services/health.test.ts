import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';

import { probeCanonicalDatabase } from '@/server/db-context';
import {
  HEALTH_CACHE_CONTROL,
  HEALTH_PATH,
  evaluateHealth,
  handleHealthRequest,
  healthResponse,
} from '@/server/services/health';

/**
 * §6.3 G-2 — the readiness verdict, offline.
 *
 * The point of these tests is the REFUSAL side, not the happy path: an
 * orchestrator believes whatever this endpoint says, so the failure that matters
 * is "it said healthy while nothing could be served" (D-171 §2.2). The probe is
 * injected, so the whole matrix runs with no database, no container and no
 * network.
 */
describe('health — fail-closed readiness verdict', () => {
  const original = process.env.DATABASE_URL;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.DATABASE_URL;
    } else {
      process.env.DATABASE_URL = original;
    }
  });

  it('answers 503 db_unconfigured and never probes when no connection is configured', async () => {
    let probed = false;

    const verdict = await evaluateHealth({
      configured: () => false,
      probe: async () => {
        probed = true;
      },
    });

    assert.equal(probed, false, 'an unconfigured surface must not open a connection');
    assert.deepEqual(verdict, {
      status: 'unavailable',
      httpStatus: 503,
      reason: 'db_unconfigured',
    });
  });

  it('answers 200 only when the probe actually resolves', async () => {
    const verdict = await evaluateHealth({
      configured: () => true,
      probe: async () => {},
    });

    assert.deepEqual(verdict, { status: 'ok', httpStatus: 200 });
  });

  it('answers 503 db_unreachable when the probe throws, and swallows the driver text', async () => {
    const verdict = await evaluateHealth({
      configured: () => true,
      probe: async () => {
        throw new Error('password authentication failed for user "leaky-value"');
      },
    });

    assert.deepEqual(verdict, {
      status: 'unavailable',
      httpStatus: 503,
      reason: 'db_unreachable',
    });
    assert.ok(!JSON.stringify(verdict).includes('leaky-value'));

    const text = await healthResponse(verdict).text();
    assert.ok(!text.includes('leaky-value'));
    assert.ok(!text.includes('password'));
  });

  it('treats a timeout like any other unreachable failure', async () => {
    const verdict = await evaluateHealth({
      configured: () => true,
      probe: () => Promise.reject(new Error('DB_PROBE_TIMEOUT')),
    });

    assert.equal(verdict.httpStatus, 503);
    assert.equal(verdict.reason, 'db_unreachable');
  });

  it('emits the no-store, non-disclosing response contract', async () => {
    const healthy = healthResponse({ status: 'ok', httpStatus: 200 });
    assert.equal(healthy.status, 200);
    assert.equal(healthy.headers.get('cache-control'), HEALTH_CACHE_CONTROL);
    assert.match(healthy.headers.get('content-type') ?? '', /application\/json/);
    assert.deepEqual(await healthy.json(), { status: 'ok' });

    const unhealthy = healthResponse({
      status: 'unavailable',
      httpStatus: 503,
      reason: 'db_unconfigured',
    });
    assert.equal(unhealthy.status, 503);
    assert.equal(unhealthy.headers.get('cache-control'), HEALTH_CACHE_CONTROL);
    assert.deepEqual(await unhealthy.json(), {
      status: 'unavailable',
      reason: 'db_unconfigured',
    });
  });

  it('exposes exactly one path', () => {
    assert.equal(HEALTH_PATH, '/healthz');
    assert.equal(HEALTH_CACHE_CONTROL, 'no-store');
  });

  it('refuses at the probe itself when DATABASE_URL is absent or blank', async () => {
    delete process.env.DATABASE_URL;
    await assert.rejects(probeCanonicalDatabase(), /DB_NOT_CONFIGURED/);

    process.env.DATABASE_URL = '   ';
    await assert.rejects(probeCanonicalDatabase(), /DB_NOT_CONFIGURED/);
  });

  it('wires the route to the live environment: no DATABASE_URL means 503, not a pass', async () => {
    delete process.env.DATABASE_URL;

    const response = await handleHealthRequest();

    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), {
      status: 'unavailable',
      reason: 'db_unconfigured',
    });
  });
});
