#!/usr/bin/env node
/**
 * Live probe verdict seam — fail-closed verification suite.
 *
 * Phase 27.7 corrective (post-closeout): the seam must render the canonical
 * sidecar verdict EXACTLY — a `503` carrying a validated `UNKNOWN` verdict is
 * `UNKNOWN`, not `DOWN` — while never letting a measurement cross for a
 * `DOWN` / `UNKNOWN` surface and never trusting a malformed or partial body.
 *
 * The suite compiles the pure seam core (`src/lib/probes/verdict.ts`) and the
 * shared build-time guard (`src/lib/mock/telemetry-data.ts`) with the project's
 * own TypeScript, then asserts:
 *
 *   1. verdict fidelity: 503+DOWN → DOWN, 503+UNKNOWN → UNKNOWN, 200+UNKNOWN is
 *      never promoted, malformed/partial bodies are rejected;
 *   2. reading gating: no phantom metrics or queue readings for DOWN/UNKNOWN;
 *   3. label safety: endpoint labels are host + pathname only, never a token;
 *   4. the build-time guard catches injected contradictions (negative cases).
 *
 * No network, no server: exit code 0 = every case passed, 1 = a violation.
 */

import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

// ── compile the pure modules with the project's TypeScript ───────────────────
const work = mkdtempSync(join(tmpdir(), 'cp-live-verdicts-'));
const outDir = join(work, 'out');
const tsconfigPath = join(work, 'tsconfig.json');
writeFileSync(
  tsconfigPath,
  JSON.stringify(
    {
      compilerOptions: {
        target: 'ES2022',
        module: 'commonjs',
        moduleResolution: 'node',
        baseUrl: ROOT,
        paths: { '@/*': ['src/*'] },
        types: ['node'],
        typeRoots: [join(ROOT, 'node_modules/@types')],
        skipLibCheck: true,
        strict: true,
        noEmitOnError: true,
        rootDir: join(ROOT, 'src'),
        outDir,
      },
      files: [
        join(ROOT, 'src/lib/probes/verdict.ts'),
        join(ROOT, 'src/lib/mock/telemetry-data.ts'),
      ],
    },
    null,
    2,
  ),
);

let compileError = null;
try {
  execFileSync(join(ROOT, 'node_modules', '.bin', 'tsc'), ['-p', tsconfigPath], {
    stdio: 'pipe',
    encoding: 'utf8',
  });
} catch (error) {
  compileError = error;
}
if (compileError !== null) {
  console.error('✗ the seam core failed to compile:');
  console.error(compileError.stdout || '');
  console.error(compileError.stderr || '');
  process.exit(1);
}

const require = createRequire(import.meta.url);
const verdict = require(join(outDir, 'lib/probes/verdict.js'));
const telemetry = require(join(outDir, 'lib/mock/telemetry-data.js'));

// ── tiny assertion harness ───────────────────────────────────────────────────
let checks = 0;
let failures = 0;

function check(name, fn) {
  checks += 1;
  try {
    fn();
    console.log(`  ✓ ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`  ✗ ${name}\n      ${error.message}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function equal(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// ── fixtures ─────────────────────────────────────────────────────────────────
const ISO = '2026-10-05T09:00:00.000Z';
const DOWN_REASON = 'فیکسچر: سطح از کار افتاده است.';
const UNKNOWN_REASON = 'فیکسچر: سطح قابل کاوش نیست.';
/** Metric/reading fields a hostile or buggy payload might smuggle through. */
const PHANTOM_FIELDS = {
  cpuPercent: 99,
  memoryUsedMb: 777,
  memoryLimitMb: 1024,
  uptimeSeconds: 4242,
  depth: 7,
  throughputPerMin: 11,
  active: 3,
  waiting: 4,
  failedLast24h: 5,
};

function sidecarBody(containerId, status, reasonFa, extra = {}) {
  return JSON.stringify({
    containerId,
    status,
    reasonFa,
    latencyMs: 12,
    probedAtUtc: ISO,
    ...extra,
  });
}

function noReadings(readings, label) {
  assert(readings.metrics === null, `${label}: metrics must be null`);
  assert(readings.redis === null, `${label}: redis readings must be null`);
  assert(readings.n8n === null, `${label}: n8n readings must be null`);
}

console.log('▸ verdict fidelity — sidecar non-2xx verdicts are honored exactly');

check('503 + canonical DOWN renders DOWN, with the canonical reason', () => {
  const body = sidecarBody('postgres', 'DOWN', DOWN_REASON, PHANTOM_FIELDS);
  const decision = verdict.resolveResponseVerdict(503, body, 'postgres', 1000, 20);
  equal(decision.status, 'DOWN', 'status');
  equal(decision.verdictSource, 'sidecar', 'verdictSource');
  equal(decision.reasonFa, DOWN_REASON, 'reason');
  noReadings(verdict.extractReadings(false, decision.status, body), '503 DOWN');
});

check('503 + canonical UNKNOWN renders UNKNOWN — the regression this fix closes', () => {
  const body = sidecarBody('walrus', 'UNKNOWN', UNKNOWN_REASON, PHANTOM_FIELDS);
  const decision = verdict.resolveResponseVerdict(503, body, 'walrus', 1000, 20);
  equal(decision.status, 'UNKNOWN', 'status');
  equal(decision.verdictSource, 'sidecar', 'verdictSource');
  equal(decision.reasonFa, UNKNOWN_REASON, 'reason');
  noReadings(verdict.extractReadings(false, decision.status, body), '503 UNKNOWN');
});

check('404 + canonical DOWN renders DOWN (every non-2xx class is honored)', () => {
  const body = sidecarBody('n8n', 'DOWN', DOWN_REASON);
  const decision = verdict.resolveResponseVerdict(404, body, 'n8n', 1000, 20);
  equal(decision.status, 'DOWN', 'status');
  equal(decision.verdictSource, 'sidecar', 'verdictSource');
});

check('503 + malformed body degrades to UNKNOWN (never fabricated DOWN)', () => {
  const decision = verdict.resolveResponseVerdict(503, '<html>502 Bad Gateway</html>', 'redis', 1000, 20);
  equal(decision.status, 'UNKNOWN', 'status');
  equal(decision.verdictSource, 'transport', 'verdictSource');
});

check('503 + JSON without a canonical verdict degrades to UNKNOWN', () => {
  const decision = verdict.resolveResponseVerdict(503, '{"error":"boom"}', 'redis', 1000, 20);
  equal(decision.status, 'UNKNOWN', 'status');
  equal(decision.verdictSource, 'transport', 'verdictSource');
});

check('503 + canonical HEALTHY is refused (contradiction → DOWN, no readings)', () => {
  const body = sidecarBody('postgres', 'HEALTHY', '', PHANTOM_FIELDS);
  const decision = verdict.resolveResponseVerdict(503, body, 'postgres', 1000, 20);
  equal(decision.status, 'DOWN', 'status');
  equal(decision.verdictSource, 'transport', 'verdictSource');
  noReadings(verdict.extractReadings(false, decision.status, body), 'contradiction');
});

console.log('▸ 2xx verdicts — never promoted above what the payload declares');

check('200 + canonical UNKNOWN stays UNKNOWN and carries no readings', () => {
  const body = sidecarBody('dokploy', 'UNKNOWN', UNKNOWN_REASON, PHANTOM_FIELDS);
  const decision = verdict.resolveResponseVerdict(200, body, 'dokploy', 1000, 20);
  equal(decision.status, 'UNKNOWN', 'status');
  equal(decision.verdictSource, 'sidecar', 'verdictSource');
  noReadings(verdict.extractReadings(true, decision.status, body), '200 UNKNOWN');
});

check('200 + canonical DOWN stays DOWN and carries no readings', () => {
  const body = sidecarBody('redis', 'DOWN', DOWN_REASON, PHANTOM_FIELDS);
  const decision = verdict.resolveResponseVerdict(200, body, 'redis', 1000, 20);
  equal(decision.status, 'DOWN', 'status');
  noReadings(verdict.extractReadings(true, decision.status, body), '200 DOWN');
});

check('200 + canonical HEALTHY renders HEALTHY with its measured metrics', () => {
  const body = sidecarBody('postgres', 'HEALTHY', '', PHANTOM_FIELDS);
  const decision = verdict.resolveResponseVerdict(200, body, 'postgres', 1000, 20);
  equal(decision.status, 'HEALTHY', 'status');
  equal(decision.verdictSource, 'sidecar', 'verdictSource');
  const readings = verdict.extractReadings(true, decision.status, body);
  equal(readings.metrics.cpuPercent, 99, 'metrics.cpuPercent');
});

check('200 + canonical HEALTHY, slow round trip escalates to DEGRADED', () => {
  const body = sidecarBody('postgres', 'HEALTHY', '');
  const decision = verdict.resolveResponseVerdict(200, body, 'postgres', 100, 250);
  equal(decision.status, 'DEGRADED', 'status');
  assert(decision.reasonFa.includes('250 ms'), 'slow reason must state the measured latency');
});

check('200 + canonical DEGRADED keeps its verdict and its metrics', () => {
  const body = sidecarBody('n8n', 'DEGRADED', 'فیکسچر: تنزل‌یافته.', PHANTOM_FIELDS);
  const decision = verdict.resolveResponseVerdict(200, body, 'n8n', 1000, 20);
  equal(decision.status, 'DEGRADED', 'status');
  equal(decision.verdictSource, 'sidecar', 'verdictSource');
  const readings = verdict.extractReadings(true, decision.status, body);
  assert(readings.metrics !== null, 'DEGRADED is a measured status');
});

check('200 + plain JSON without a verdict keeps the transport contract', () => {
  const body = JSON.stringify({ cpuPercent: 12, memoryUsedMb: 300, memoryLimitMb: 2048, uptimeSeconds: 60 });
  const decision = verdict.resolveResponseVerdict(200, body, 'postgres', 1000, 20);
  equal(decision.status, 'HEALTHY', 'status');
  equal(decision.verdictSource, 'transport', 'verdictSource');
  const readings = verdict.extractReadings(true, decision.status, body);
  equal(readings.metrics.cpuPercent, 12, 'metrics.cpuPercent');
});

check('3xx redirect is DEGRADED: the target was never assessed', () => {
  const decision = verdict.resolveResponseVerdict(302, '', 'redis', 1000, 20);
  equal(decision.status, 'DEGRADED', 'status');
  equal(decision.verdictSource, 'transport', 'verdictSource');
});

check('readings cross only for a measured status on a 2xx response', () => {
  const body = sidecarBody('postgres', 'DOWN', DOWN_REASON, PHANTOM_FIELDS);
  noReadings(verdict.extractReadings(true, 'UNKNOWN', body), 'UNKNOWN');
  noReadings(verdict.extractReadings(true, 'DOWN', body), 'DOWN');
  noReadings(verdict.extractReadings(false, 'HEALTHY', body), 'non-2xx HEALTHY');
  const measured = verdict.extractReadings(true, 'HEALTHY', body);
  assert(measured.metrics !== null, 'HEALTHY must keep readable metrics');
});

console.log('▸ malformed and partial verdict bodies are rejected, never coerced');

const MALFORMED = [
  ['missing the reason field', JSON.stringify({ containerId: 'postgres', status: 'DOWN', latencyMs: 1, probedAtUtc: ISO })],
  ['empty reason on DOWN', sidecarBody('postgres', 'DOWN', '')],
  ['a reason on HEALTHY', sidecarBody('postgres', 'HEALTHY', 'boom')],
  ['a verdict for a different container', sidecarBody('n8n', 'DOWN', DOWN_REASON)],
  ['a control character inside the reason', sidecarBody('postgres', 'DOWN', `a\u0007b`)],
  ['a reason beyond the bound', sidecarBody('postgres', 'DOWN', 'x'.repeat(601))],
  ['a non-numeric latencyMs', sidecarBody('postgres', 'DOWN', DOWN_REASON, { latencyMs: 'fast' })],
  ['a non-ISO probedAtUtc', sidecarBody('postgres', 'DOWN', DOWN_REASON, { probedAtUtc: 'yesterday' })],
  ['a non-canonical status value', sidecarBody('postgres', 'MAYBE', DOWN_REASON)],
  ['a non-object body', '[1,2,3]'],
  ['an empty body', ''],
];

check('every malformed/partial body parses as NOT a verdict', () => {
  for (const [label, raw] of MALFORMED) {
    assert(verdict.parseSidecarVerdict(raw, 'postgres') === null, `${label}: must be rejected`);
  }
});

check('rejected bodies fail closed on both 503 and 200', () => {
  for (const [label, raw] of MALFORMED) {
    equal(verdict.resolveResponseVerdict(503, raw, 'postgres', 1000, 20).status, 'UNKNOWN', `${label} on 503`);
    equal(verdict.resolveResponseVerdict(200, raw, 'postgres', 1000, 20).status, 'HEALTHY', `${label} on 200`);
  }
});

check('an accepted verdict carries no control characters and stays within the bound', () => {
  const parsed = verdict.parseSidecarVerdict(sidecarBody('postgres', 'DOWN', DOWN_REASON), 'postgres');
  assert(parsed !== null, 'the canonical fixture must parse');
  assert(!verdict.SIDECAR_VERDICT_STATUSES.includes('MAYBE'), 'the vocabulary is closed');
  assert(parsed.reasonFa.length <= 600, 'the reason is bounded');
});

console.log('▸ configuration — labels are host + pathname only');

check('an endpoint label never echoes a query-string token', () => {
  const config = verdict.readProbeConfig({
    CP_PROBE_ENDPOINTS: JSON.stringify({
      postgres: 'http://127.0.0.1:8088/health/postgres?token=SEKRIT-TOKEN',
    }),
    CP_PROBE_TOKENS: JSON.stringify({ postgres: 'SEKRIT-TOKEN' }),
  });
  equal(config.endpoints.postgres.label, '127.0.0.1:8088/health/postgres', 'label');
  assert(!config.endpoints.postgres.label.includes('SEKRIT'), 'label must not echo the token');
  assert(!config.endpoints.postgres.label.includes('?'), 'label must not carry a query string');
  equal(config.tokens.postgres, 'SEKRIT-TOKEN', 'the token is kept only for the outbound header');
});

check('invalid endpoints are refused per surface; a malformed document refuses every probe', () => {
  const config = verdict.readProbeConfig({
    CP_PROBE_ENDPOINTS: JSON.stringify({
      postgres: 'not-a-url',
      n8n: 'ftp://example.com/health',
      redis: 42,
    }),
  });
  assert('invalidReasonFa' in config.endpoints.postgres, 'unparsable URL must be invalid');
  assert('invalidReasonFa' in config.endpoints.n8n, 'non-http protocol must be invalid');
  assert('invalidReasonFa' in config.endpoints.redis, 'non-string endpoint must be invalid');
  equal(config.configErrorFa, null, 'a per-surface error is not a config error');

  const broken = verdict.readProbeConfig({ CP_PROBE_ENDPOINTS: '{oops' });
  assert(broken.configErrorFa !== null, 'a malformed document must raise a config error');
  equal(Object.keys(broken.endpoints).length, 0, 'no endpoint may survive a config error');
});

check('timeout and slow-threshold values are clamped to their bounds', () => {
  const config = verdict.readProbeConfig({ CP_PROBE_TIMEOUT_MS: '999999', CP_PROBE_SLOW_MS: 'abc' });
  equal(config.timeoutMs, verdict.MAX_PROBE_TIMEOUT_MS, 'timeout clamp');
  equal(config.slowMs, verdict.DEFAULT_PROBE_SLOW_MS, 'invalid slow falls back');
});

console.log('▸ the shared build-time guard rejects injected contradictions');

function liveSnapshot(scenario) {
  const snapshot = telemetry.mockTelemetry(scenario);
  snapshot.provenance = 'live';
  snapshot.sourceMode = 'LIVE';
  snapshot.containers = snapshot.containers.map((container) => ({ ...container, provenance: 'live' }));
  return snapshot;
}

function probeRecord(overrides = {}) {
  return {
    containerId: 'postgres',
    status: 'HEALTHY',
    latencyMs: 5,
    payloadDigest: 'a'.repeat(64),
    probedAtUtc: ISO,
    reasonFa: '',
    endpointLabel: '127.0.0.1:8088/health/postgres',
    verdictSource: 'sidecar',
    ...overrides,
  };
}

function expectViolation(name, mutate, fragment, scenario = 'degraded-pipeline') {
  check(name, () => {
    const snapshot = liveSnapshot(scenario);
    mutate(snapshot);
    let message = null;
    try {
      telemetry.assertTelemetryConsistency(snapshot);
    } catch (error) {
      message = error.message;
    }
    assert(message !== null, 'the guard must reject this snapshot');
    assert(
      message.includes(fragment),
      `expected the guard message to include ${JSON.stringify(fragment)}, got: ${message}`,
    );
  });
}

check('every canonical scenario passes the guard untouched', () => {
  for (const scenario of ['steady', 'degraded-pipeline', 'gate-blocked', 'all-unknown']) {
    telemetry.mockTelemetry(scenario);
  }
});

expectViolation(
  'an UNKNOWN container carrying metrics is rejected',
  (snapshot) => {
    const walrus = snapshot.containers.find((container) => container.id === 'walrus');
    walrus.metrics = { cpuPercent: 10, memoryUsedMb: 100, memoryLimitMb: 512, uptimeSeconds: 60 };
    walrus.metricsState = 'LIVE';
  },
  'walrus: UNKNOWN container must not carry metrics',
);

expectViolation(
  'a DOWN container carrying metrics is rejected',
  (snapshot) => {
    const redis = snapshot.containers.find((container) => container.id === 'redis');
    redis.metrics = { cpuPercent: 10, memoryUsedMb: 100, memoryLimitMb: 512, uptimeSeconds: 60 };
    redis.metricsState = 'LIVE';
  },
  'redis: DOWN container must not carry live metrics (fail-closed)',
);

expectViolation(
  'a sidecar UNKNOWN verdict rendered as a DOWN badge is rejected',
  (snapshot) => {
    const redis = snapshot.containers.find((container) => container.id === 'redis');
    redis.probe = probeRecord({ containerId: 'redis', status: 'UNKNOWN', reasonFa: UNKNOWN_REASON });
  },
  '!= rendered container status',
);

expectViolation(
  'redis readings under a DOWN verdict are rejected',
  (snapshot) => {
    snapshot.queues.probe.redis = probeRecord({
      containerId: 'redis',
      status: 'DOWN',
      reasonFa: DOWN_REASON,
    });
  },
  'redis readings must be absent unless the broker probe assessed HEALTHY/DEGRADED',
  // `steady` carries live redis readings; `degraded-pipeline` already nulls them.
  'steady',
);

expectViolation(
  'n8n readings under an UNKNOWN verdict are rejected',
  (snapshot) => {
    snapshot.queues.probe.n8n = probeRecord({
      containerId: 'n8n',
      status: 'UNKNOWN',
      reasonFa: UNKNOWN_REASON,
    });
  },
  'n8n readings must be absent unless the probe assessed HEALTHY/DEGRADED',
);

expectViolation(
  'a sidecar verdict without a parsed payload digest is rejected',
  (snapshot) => {
    const postgres = snapshot.containers.find((container) => container.id === 'postgres');
    postgres.probe = probeRecord({ containerId: 'postgres', payloadDigest: null });
  },
  'a sidecar verdict requires the parsed payload digest',
);

expectViolation(
  'an unknown verdictSource is rejected',
  (snapshot) => {
    const postgres = snapshot.containers.find((container) => container.id === 'postgres');
    postgres.probe = probeRecord({ containerId: 'postgres', verdictSource: 'guess' });
  },
  "probe verdictSource must be 'sidecar' or 'transport'",
);

expectViolation(
  'a reason beyond the bound is rejected',
  (snapshot) => {
    const postgres = snapshot.containers.find((container) => container.id === 'postgres');
    postgres.probe = probeRecord({
      containerId: 'postgres',
      status: 'DOWN',
      reasonFa: 'x'.repeat(601),
    });
  },
  'must stay within 600 characters',
);

expectViolation(
  'a reason carrying control characters is rejected',
  (snapshot) => {
    const postgres = snapshot.containers.find((container) => container.id === 'postgres');
    postgres.probe = probeRecord({
      containerId: 'postgres',
      status: 'DOWN',
      reasonFa: 'bad\u0007reason',
    });
  },
  'must not carry control characters',
);

// ── summary ──────────────────────────────────────────────────────────────────
console.log('');
if (failures > 0) {
  console.error(`✗ live verdict seam: ${failures}/${checks} case(s) failed`);
  process.exit(1);
}
console.log(`✓ live verdict seam: ${checks}/${checks} cases passed`);
