/**
 * D-171 §5.5 — native `node:test` coverage for the AI Ops & Shared Memory Hub.
 *
 * Proves the fail-closed rules of `/ai-engine` rather than asserting them:
 *   - the guard REJECTS a memory layer that reports namespaces or counts while
 *     it is not connected, a half-measured route, a half-measured token row, a
 *     success rate that does not derive from its counts, a consumption ratio or
 *     pressure that disagrees with its derivation, a price invented outside the
 *     canonical tariff table, a proposal whose decision instant disagrees with
 *     its lifecycle state, and an enabled control without a provider call path;
 *   - the derivations are pure and boundary-exact (the canonical 0.8 soft ratio,
 *     zero invocations never a 100% success rate);
 *   - every scenario renders honestly (steady measured, token-pressure warning,
 *     idle zero-but-measured, all-unknown unavailable with no counts);
 *   - the `/ai-engine` Business card keeps the mandated `NOT_CONNECTED` status
 *     code, can never be green on sample data, and reports «بدون داده» when the
 *     source is unavailable.
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { aiEngineBusinessCard, assertBusinessCard } from '@/lib/business-summary';
import {
  assertAiOpsConsistency,
  budgetPressure,
  canonicalCostMicroUsd,
  consumedRatio,
  mockAiOps,
  SOFT_BUDGET_RATIO,
  successRatePercent,
  summarizeAiOps,
} from '@/lib/mock/ai-ops-data';
import type { AiOpsSnapshot } from '@/types/ai-ops';

/** Deep copy a snapshot so each case mutates its own instance. */
function clone(snapshot: AiOpsSnapshot): AiOpsSnapshot {
  return JSON.parse(JSON.stringify(snapshot)) as AiOpsSnapshot;
}

/**
 * Index access with an explicit failure: `noUncheckedIndexedAccess` is on, and a
 * missing fixture row must fail the case rather than mutate `undefined`.
 */
function at<T>(items: T[], index: number): T {
  const value = items[index];
  if (value === undefined) throw new Error(`fixture row ${index} is missing`);
  return value;
}

const steady = mockAiOps('steady');

describe('derivations', () => {
  it('never turns zero invocations into a success rate', () => {
    assert.equal(successRatePercent(0, 0), null);
    assert.equal(successRatePercent(null, 10), null);
    assert.equal(successRatePercent(10, null), null);
    assert.equal(successRatePercent(1, 2), 50);
  });

  it('derives the consumption ratio at four decimals and null when unmeasured', () => {
    assert.equal(consumedRatio(null, 100), null);
    assert.equal(consumedRatio(10, 0), null);
    assert.equal(consumedRatio(61, 100), 0.61);
    assert.equal(consumedRatio(1, 3), 0.3333);
  });

  it('applies the canonical 0.8 soft ratio at its exact boundary', () => {
    assert.equal(SOFT_BUDGET_RATIO, 0.8);
    assert.equal(budgetPressure(null), 'UNKNOWN');
    assert.equal(budgetPressure(0.7999), 'OK');
    assert.equal(budgetPressure(0.8), 'WARNING');
    assert.equal(budgetPressure(1), 'WARNING');
    assert.equal(budgetPressure(1.0001), 'EXCEEDED');
  });

  it('prices only the pairs the canonical tariff table carries', () => {
    assert.equal(canonicalCostMicroUsd('mock', 'mock-1', 10_000, 2_000), 0);
    assert.equal(canonicalCostMicroUsd('openai', 'gpt-x', 10_000, 2_000), null);
  });
});

describe('mock scenarios', () => {
  it('renders steady measured, with the memory layer not connected and no counts', () => {
    assert.equal(steady.provenance, 'mock');
    assert.equal(steady.memory.state, 'NOT_CONNECTED');
    assert.deepEqual(steady.memory.namespaces, []);
    assert.equal(steady.memory.totalVectors, null);
    assert.equal(steady.memory.totalBytes, null);
    assert.equal(steady.summary.routesMeasured, 3);
    assert.equal(steady.summary.routesUnmeasured, 0);
    assert.equal(steady.summary.worstBudgetPressure, 'OK');
    assert.equal(steady.summary.hasBudgetAlert, false);
  });

  it('is deterministic: repeated builds are byte-identical', () => {
    assert.deepEqual(mockAiOps('steady'), steady);
    assert.deepEqual(mockAiOps('token-pressure'), mockAiOps('token-pressure'));
  });

  it('raises the budget warning honestly in the token-pressure scenario', () => {
    const pressure = mockAiOps('token-pressure');
    assert.equal(pressure.summary.worstBudgetPressure, 'WARNING');
    assert.equal(pressure.summary.hasBudgetAlert, true);
    const worst = pressure.cost.find((row) => row.routeId === 'propose_content_idea');
    assert.ok(worst !== undefined);
    assert.equal(worst.pressure, 'WARNING');
    assert.ok((worst.consumedRatio ?? 0) >= SOFT_BUDGET_RATIO);
    // The canonical free mock provider still costs nothing: no invented spend.
    assert.equal(worst.costMicroUsd, 0);
  });

  it('renders idle as measured-but-zero, never as a success rate', () => {
    const idle = mockAiOps('idle');
    for (const route of idle.routes) {
      assert.equal(route.invocations, 0);
      assert.equal(route.successRatePercent, null);
      assert.equal(route.p95LatencyMs, null);
      assert.deepEqual(route.stages, []);
    }
    assert.equal(idle.summary.routesMeasured, 3);
    assert.equal(idle.summary.proposalsAwaitingDecision, 0);
    assert.equal(idle.proposals.length, 0);
  });

  it('renders all-unknown as unavailable with no reading anywhere', () => {
    const unknown = mockAiOps('all-unknown');
    assert.equal(unknown.provenance, 'unavailable');
    assert.equal(unknown.memory.state, 'UNKNOWN');
    assert.deepEqual(unknown.memory.namespaces, []);
    assert.equal(unknown.memory.totalVectors, null);
    assert.equal(unknown.summary.routesUnmeasured, 3);
    for (const route of unknown.routes) {
      assert.equal(route.invocations, null);
      assert.equal(route.successRatePercent, null);
    }
    for (const row of unknown.cost) {
      assert.equal(row.totalTokens, null);
      assert.equal(row.costMicroUsd, null);
      assert.equal(row.pressure, 'UNKNOWN');
    }
    assert.equal(unknown.proposals.length, 0);
  });
});

describe('fail-closed guard', () => {
  it('accepts every scenario it builds', () => {
    for (const scenario of ['steady', 'token-pressure', 'idle', 'all-unknown'] as const) {
      assert.doesNotThrow(() => assertAiOpsConsistency(mockAiOps(scenario)));
    }
  });

  it('refuses a memory layer that reports namespaces while not connected', () => {
    const bad = clone(steady);
    bad.memory.namespaces = [{ name: 'agent-context', vectors: 12, bytes: 4_096 }];
    assert.throws(
      () => assertAiOpsConsistency(bad),
      /NOT_CONNECTED memory layer must not enumerate namespaces/,
    );
  });

  it('refuses a zero count masquerading as a measurement', () => {
    const bad = clone(steady);
    bad.memory.totalVectors = 0;
    assert.throws(() => assertAiOpsConsistency(bad), /must not report counts/);
  });

  it('refuses a half-measured route', () => {
    const bad = clone(steady);
    at(bad.routes, 0).succeeded = null;
    assert.throws(() => assertAiOpsConsistency(bad), /never half-measured/);
  });

  it('refuses a success rate that does not derive from its counts', () => {
    const bad = clone(steady);
    at(bad.routes, 0).successRatePercent = 99;
    assert.throws(() => assertAiOpsConsistency(bad), /successRatePercent 99 != derived/);
  });

  it('refuses counts that do not add up', () => {
    const bad = clone(steady);
    at(bad.routes, 1).failed = 5;
    assert.throws(() => assertAiOpsConsistency(bad), /succeeded \+ failed/);
  });

  it('refuses a measured route with no latency', () => {
    const bad = clone(steady);
    at(bad.routes, 2).p95LatencyMs = null;
    assert.throws(() => assertAiOpsConsistency(bad), /requires a non-negative integer p95 latency/);
  });

  it('refuses a half-measured token row', () => {
    const bad = clone(steady);
    at(bad.cost, 0).completionTokens = null;
    assert.throws(() => assertAiOpsConsistency(bad), /token readings must be all present or all absent/);
  });

  it('refuses a pressure that disagrees with its ratio', () => {
    const bad = clone(steady);
    at(bad.cost, 2).pressure = 'WARNING';
    assert.throws(() => assertAiOpsConsistency(bad), /pressure WARNING != derived OK/);
  });

  it('refuses a cost invented for an unpriced provider', () => {
    const bad = clone(steady);
    at(bad.cost, 0).provider = 'openai';
    at(bad.cost, 0).model = 'gpt-x';
    at(bad.cost, 0).costMicroUsd = 1_234;
    assert.throws(() => assertAiOpsConsistency(bad), /outside the canonical tariff table/);
  });

  it('refuses a terminal proposal without its decision instant', () => {
    const bad = clone(steady);
    const accepted = bad.proposals.find((proposal) => proposal.state === 'ACCEPTED');
    assert.ok(accepted !== undefined);
    accepted.decidedAtUtc = null;
    assert.throws(() => assertAiOpsConsistency(bad), /terminal state requires the human decision instant/);
  });

  it('refuses a pending proposal carrying human provenance', () => {
    const bad = clone(steady);
    const proposed = bad.proposals.find((proposal) => proposal.state === 'PROPOSED');
    assert.ok(proposed !== undefined);
    proposed.lastMutation = 'HUMAN_ENTERED';
    assert.throws(() => assertAiOpsConsistency(bad), /pending draft must carry AI_GENERATED/);
  });

  it('refuses a proposal id outside the canonical durable form', () => {
    const bad = clone(steady);
    at(bad.proposals, 0).id = 'proposal-1';
    assert.throws(() => assertAiOpsConsistency(bad), /canonical aiprop\|<pid> durable form/);
  });

  it('refuses an enabled control without a provider call path', () => {
    const bad = clone(steady);
    at(bad.controls, 0).enabled = true;
    at(bad.controls, 0).blockedReasonFa = '';
    assert.throws(
      () => assertAiOpsConsistency(bad),
      /control enabled without a provider call path and a credential/,
    );
  });

  it('refuses a summary that disagrees with the rows', () => {
    const bad = clone(steady);
    bad.summary.proposalsAwaitingDecision = 99;
    assert.throws(() => assertAiOpsConsistency(bad), /summary\.proposalsAwaitingDecision 99/);
  });

  it('refuses a mock snapshot claiming live provenance', () => {
    const bad = clone(steady);
    bad.provenance = 'live';
    assert.throws(() => assertAiOpsConsistency(bad), /MOCK snapshot must not claim live provenance/);
  });

  it('derives the summary from the rows, never from the snapshot', () => {
    const derived = summarizeAiOps(steady.memory, steady.routes, steady.cost, steady.proposals);
    assert.deepEqual(derived, steady.summary);
  });
});

describe('/ai-engine Business card', () => {
  it('keeps the mandated NOT_CONNECTED state and never goes green on sample data', () => {
    const card = aiEngineBusinessCard(steady);
    assert.equal(card.status.code, 'UNKNOWN');
    assert.notEqual(card.status.tone, 'success');
    assert.equal(card.provenance.code, 'MOCK');
    const memoryMetric = card.metrics.find((metric) => metric.label.includes('حافظه'));
    assert.ok(memoryMetric !== undefined);
    assert.ok(memoryMetric.value.includes('NOT_CONNECTED'));
    assert.doesNotThrow(() => assertBusinessCard(card));
  });

  it('reports a budget warning when the consumption nears its ceiling', () => {
    const card = aiEngineBusinessCard(mockAiOps('token-pressure'));
    assert.equal(card.status.code, 'REVIEW');
    assert.notEqual(card.status.tone, 'success');
  });

  it('reports «بدون داده» when nothing could be read', () => {
    const card = aiEngineBusinessCard(mockAiOps('all-unknown'));
    assert.equal(card.status.code, 'NO_DATA');
    assert.equal(card.provenance.code, 'NO_DATA');
    assert.doesNotThrow(() => assertBusinessCard(card));
  });

  it('is deterministic for the same snapshot', () => {
    assert.deepEqual(aiEngineBusinessCard(steady), aiEngineBusinessCard(mockAiOps('steady')));
  });
});
