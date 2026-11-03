import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { after, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import { ORDER_CONFIRMED_KIND, SMS_CHANNEL } from '@/lib/notification-rules';
import { handleNotificationDispatchRequest } from '@/server/notifications/dispatch-endpoint';
import { MockSmsChannel } from '@/server/notifications/sms';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository } from '@/server/repository';
import { MERCHANT_TRANSITION, transitionOrder } from '@/server/services/orders';

/**
 * D-172 §6.2 / Phase 6 B5 — the LOCAL dispatch scheduler runner.
 *
 * These cases drive the real `scripts/dispatch-scheduler.mjs` as a child process
 * against a real HTTP server that wraps the REAL operator endpoint
 * (`handleNotificationDispatchRequest`) over the REAL queue behaviour
 * (`dispatchNotifications` + the repository contract). Nothing is stubbed at the
 * seam the scheduler uses, so what passes here is the whole trigger path:
 * argv/env → HTTP → bearer auth → claim → send → settle.
 *
 * The properties asserted are the ones an unattended timer must have:
 *
 *  - it authenticates (the endpoint's constant-time bearer check passes);
 *  - one pass drains and settles the row, and a second pass sends nothing;
 *  - an empty queue is a normal `claimed=0`, not an error;
 *  - no token → exit 2 and NO request reaches the server;
 *  - a non-loopback target → exit 2 before any socket is opened;
 *  - a wrong token → exit 3 with exactly one request (never a retry storm);
 *  - a transient 503 → retried with backoff, then succeeds;
 *  - the token never appears in the runner's output.
 */

const execFileAsync = promisify(execFile);
const SCRIPT = fileURLToPath(new URL('../../../scripts/dispatch-scheduler.mjs', import.meta.url));
const TOKEN = 'scheduler-token-0123456789abcdef';
const ORDER_ID = 'order-dispatch-scheduler';

interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
}

async function runScheduler(argv: string[], env: NodeJS.ProcessEnv): Promise<RunResult> {
  try {
    const { stdout, stderr } = await execFileAsync(process.execPath, [SCRIPT, ...argv], {
      env,
      timeout: 30_000,
      maxBuffer: 1_000_000,
    });
    return { code: 0, stdout, stderr };
  } catch (error) {
    const failure = error as { code?: number | string; stdout?: string; stderr?: string };
    return {
      code: typeof failure.code === 'number' ? failure.code : -1,
      stdout: failure.stdout ?? '',
      stderr: failure.stderr ?? '',
    };
  }
}

/** A PAID order with exactly one queued confirmation, through the real service. */
async function paidOrderWithQueue(): Promise<CommerceRepository> {
  const repository = createMemoryRepository({
    orders: [
      {
        id: ORDER_ID,
        customerName: 'زهرا محمدی',
        customerPhone: '09123456789',
        postalCode: '1999999999',
        status: 'PENDING',
        totalAmount: 1_450_000,
        discountAmount: 0,
        shippingAmount: 0,
        trackingCode: null,
        shippingAddress: 'تهران، خیابان ولیعصر، پلاک ۱۲',
        paymentRefId: null,
        createdAt: new Date('2026-06-01T00:00:00.000Z'),
        items: [
          {
            sku: 'scheduler-S',
            productTitle: 'مانتو کتان',
            size: 'S',
            colorName: 'مشکی',
            quantity: 1,
            unitPrice: 1_450_000,
          },
        ],
      },
    ],
  });

  const moved = await transitionOrder(repository, ORDER_ID, 'PAID', MERCHANT_TRANSITION, [
    { kind: ORDER_CONFIRMED_KIND, channel: SMS_CHANNEL },
  ]);
  assert.deepEqual(moved, { ok: true }, 'the fixture order must reach PAID with a queued SMS');
  return repository;
}

interface EndpointHarness {
  server: Server;
  url: string;
  authorizations: Array<string | null>;
  channel: MockSmsChannel;
  close: () => Promise<void>;
}

/**
 * A loopback HTTP server that forwards to the REAL endpoint handler. `failures`
 * makes the first N calls answer 503, which is how the retry/backoff path is
 * exercised without waiting on a real outage.
 */
async function startEndpoint(repository: CommerceRepository, failures = 0): Promise<EndpointHarness> {
  const channel = new MockSmsChannel();
  const authorizations: Array<string | null> = [];
  let remainingFailures = failures;

  const server = createServer((request, response) => {
    authorizations.push(request.headers.authorization ?? null);

    if (remainingFailures > 0) {
      remainingFailures -= 1;
      response.writeHead(503, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: false, code: 'UNAVAILABLE' }));
      return;
    }

    const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    void handleNotificationDispatchRequest(
      new Request(`${origin}${request.url ?? '/'}`, {
        method: 'POST',
        headers: { authorization: request.headers.authorization ?? '' },
      }),
      {
        token: TOKEN,
        getRepository: () => repository,
        channel: { ok: true, channel, mode: 'MOCK' },
      },
    )
      .then(async (result) => {
        response.writeHead(result.status, { 'content-type': 'application/json' });
        response.end(await result.text());
      })
      .catch(() => {
        response.writeHead(500, { 'content-type': 'application/json' });
        response.end(JSON.stringify({ ok: false, code: 'UNEXPECTED' }));
      });
  });

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', resolve);
  });

  const { port } = server.address() as AddressInfo;
  return {
    server,
    url: `http://127.0.0.1:${port}/api/internal/notifications/dispatch`,
    authorizations,
    channel,
    close: () => new Promise<void>((resolve) => server.close(() => resolve())),
  };
}

/** The runner's environment with the token removed, for the refusal cases. */
function envFor(url: string, overrides: Record<string, string> = {}): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env, NOTIFICATIONS_DISPATCH_URL: url };
  delete env.NOTIFICATIONS_DISPATCH_TOKEN;
  delete env.NOTIFICATIONS_DISPATCH_INTERVAL_MS;
  return { ...env, ...overrides };
}

describe('§6.2 / B5 — local dispatch scheduler runner', () => {
  const harnesses: EndpointHarness[] = [];

  after(async () => {
    await Promise.all(harnesses.map((harness) => harness.close()));
  });

  it('sends the bearer token, drains one batch and settles the row; a second pass sends nothing', async () => {
    const repository = await paidOrderWithQueue();
    const harness = await startEndpoint(repository);
    harnesses.push(harness);

    const first = await runScheduler(['--once'], envFor(harness.url, { NOTIFICATIONS_DISPATCH_TOKEN: TOKEN }));
    assert.equal(first.code, 0, `the runner must succeed: ${first.stderr}`);
    assert.match(first.stdout, /claimed=1/);
    assert.match(first.stdout, /sent=1/);
    assert.match(first.stdout, /--once complete/);
    assert.equal(harness.authorizations.length, 1);
    assert.equal(harness.authorizations[0], `Bearer ${TOKEN}`, 'the endpoint sees a real bearer token');
    assert.equal(harness.channel.calls.length, 1, 'exactly one SMS was recorded');

    const second = await runScheduler(['--once'], envFor(harness.url, { NOTIFICATIONS_DISPATCH_TOKEN: TOKEN }));
    assert.equal(second.code, 0, 'an empty queue is a normal run, not a failure');
    assert.match(second.stdout, /claimed=0/);
    assert.equal(harness.channel.calls.length, 1, 'the settled row is never sent twice');
    assert.equal(harness.authorizations.length, 2);
  });

  it('refuses without a token and never calls the endpoint', async () => {
    const repository = await paidOrderWithQueue();
    const harness = await startEndpoint(repository);
    harnesses.push(harness);

    const result = await runScheduler(['--once'], envFor(harness.url));
    assert.equal(result.code, 2, 'an absent token is a configuration refusal');
    assert.match(result.stderr, /NOTIFICATIONS_DISPATCH_TOKEN/);
    assert.equal(harness.authorizations.length, 0, 'no request may be made without a token');
    assert.equal(harness.channel.calls.length, 0);
  });

  it('refuses a non-loopback endpoint before opening a socket', async () => {
    const result = await runScheduler(
      ['--once'],
      envFor('https://commerce.example.com/api/internal/notifications/dispatch', {
        NOTIFICATIONS_DISPATCH_TOKEN: TOKEN,
      }),
    );
    assert.equal(result.code, 2);
    assert.match(result.stderr, /not loopback/);
  });

  it('stops on a bearer refusal with one request instead of retrying', async () => {
    const repository = await paidOrderWithQueue();
    const harness = await startEndpoint(repository);
    harnesses.push(harness);

    const result = await runScheduler(
      ['--once'],
      envFor(harness.url, { NOTIFICATIONS_DISPATCH_TOKEN: 'wrong-token-000000' }),
    );
    assert.equal(result.code, 3, 'authentication refusal is fatal, not transient');
    assert.match(result.stderr, /refused the bearer token/);
    assert.equal(harness.authorizations.length, 1, 'a wrong token is never retried');
    assert.equal(harness.channel.calls.length, 0);
  });

  it('retries a transient 503 with backoff and then succeeds', async () => {
    const repository = await paidOrderWithQueue();
    const harness = await startEndpoint(repository, 1);
    harnesses.push(harness);

    const result = await runScheduler(['--once'], envFor(harness.url, { NOTIFICATIONS_DISPATCH_TOKEN: TOKEN }));
    assert.equal(result.code, 0, `the retry must recover: ${result.stderr}`);
    assert.match(result.stderr, /attempt 1\/5/);
    assert.match(result.stdout, /sent=1/);
    assert.equal(harness.authorizations.length, 2, 'one refusal, then one successful attempt');
    assert.equal(harness.channel.calls.length, 1);
  });

  it('never prints the token', async () => {
    const repository = await paidOrderWithQueue();
    const harness = await startEndpoint(repository);
    harnesses.push(harness);

    const result = await runScheduler(['--once'], envFor(harness.url, { NOTIFICATIONS_DISPATCH_TOKEN: TOKEN }));
    assert.equal(result.code, 0);
    assert.ok(!result.stdout.includes(TOKEN), 'stdout must not carry the bearer token');
    assert.ok(!result.stderr.includes(TOKEN), 'stderr must not carry the bearer token');
  });
});
