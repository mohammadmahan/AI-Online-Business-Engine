/**
 * Deterministic mock provider for the AI Ops & Shared Memory Hub (D-171 §5.5,
 * Phase 27.7 `/ai-engine`).
 *
 * ── Boundaries ──────────────────────────────────────────────────────────────
 * ZERO provider calls, ZERO network, ZERO credentials, ZERO writes. Every
 * instant below is a fixed literal, so the page prerenders byte-identically
 * (no `Date.now()`, no `Math.random()`).
 *
 * ── Canonical grounding ─────────────────────────────────────────────────────
 * - Shared memory: D-142 is PLANNED and its external connectivity is owner-gated
 *   (D-045), so the honest steady state is `NOT_CONNECTED` with NO namespaces
 *   and NO counts. The local parity backend (`local/src/memory/`) is not a
 *   remote connection and is never reported as one.
 * - Routes: the canonical task types (`ai_tasks.py`).
 * - Stages: the `ai.observe.v1` stages (`ai_observability.py`, D-065). The
 *   canonical schema records pipeline stages; it has no tool-calling registry,
 *   so no tool list is invented here.
 * - Budgets: the D-127 resource/window vocabulary and the D-063 soft ratio
 *   (0.8). The window allowance is metered in TOKENS, a quantity the mock
 *   provider genuinely reports, while `costMicroUsd` comes from the canonical
 *   TARIFFS table — which prices ONLY the free deterministic mock provider, so
 *   a non-zero cost would be a fabricated reading and the guard refuses any
 *   (provider, model) pair outside that table.
 * - Proposals: the D-064 lifecycle states and the canonical `aiprop|<pid>`
 *   durable id form.
 *
 * ── Fail-closed invariant guard ─────────────────────────────────────────────
 * `assertAiOpsConsistency()` throws at BUILD time when, among others:
 *   1. the memory layer is not CONNECTED yet reports namespaces or counts, or
 *      its totals disagree with the namespace rows,
 *   2. a route is half-measured (some readings present, some absent), its
 *      success rate does not derive from its counts, or a route with zero
 *      invocations claims a success rate,
 *   3. a consumption ratio or pressure disagrees with its derivation, or a
 *      cost row's price disagrees with the canonical tariff table,
 *   4. a proposal's decision instant disagrees with its terminal state,
 *   5. the summary disagrees with the rows, or a gated control is enabled
 *      without BOTH a provider call path and a credential.
 *
 * ── Scenarios ───────────────────────────────────────────────────────────────
 * `steady` (default), `token-pressure`, `idle` via `CP_AI_OPS_SCENARIO`; an
 * unrecognised value falls back to `all-unknown` (NO_DATA), so a typo can never
 * render as measured.
 */

import type { Provenance } from '@/types/telemetry';
import type {
  AgentRouteObservability,
  AgentStageUsage,
  AiOpsControlSpec,
  AiOpsDataSource,
  AiOpsOverview,
  AiOpsSnapshot,
  AiProposalDraft,
  AiRouteId,
  BudgetPressure,
  MemoryLayerStatus,
  ObserveStageId,
  ProposalMutation,
  ProposalState,
  TokenCostAnalytics,
} from '@/types/ai-ops';

/** Named, deterministic scenarios. Default is `steady`. */
export type AiOpsScenario = 'steady' | 'token-pressure' | 'idle' | 'all-unknown';

/** Fixed literal instant, so the static prerender is byte-stable. */
const MOCK_INSTANT = '2026-10-08T08:00:00.000Z';

const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

/** The three canonical execution routes (task types, `ai_tasks.py`). */
const ROUTE_IDS: AiRouteId[] = [
  'propose_content_idea',
  'generate_caption',
  'enrich_description',
];

/** The canonical `ai.observe.v1` stages (D-065). */
const STAGE_IDS: ObserveStageId[] = [
  'provider_call',
  'validation',
  'divergence',
  'lifecycle',
  'hitl_decision',
  'fallback',
];

/** The canonical D-064 proposal lifecycle states. */
const PROPOSAL_STATES: ProposalState[] = [
  'PROPOSED',
  'IN_REVIEW',
  'ACCEPTED',
  'REJECTED',
  'MODIFIED_BY_HUMAN',
];

/**
 * The canonical soft-budget ratio (D-063-identical, `budget_contracts.py`
 * `_SOFT_RATIO`): at or above 80% of an allowance the reading is a WARNING, and
 * only an over-allowance reading is EXCEEDED.
 */
export const SOFT_BUDGET_RATIO = 0.8;

/** The D-127 window allowance this screen meters, in tokens per logical day. */
export const TOKEN_CEILING_PER_DAY = 40_000;

/**
 * Integer micro-USD budgets of the canonical route targets
 * (`ai_runtime.py` RouteTarget.budget_usd: 0.50 / 0.50 / 1.00 per run).
 */
const RUN_BUDGET_MICRO_USD: Record<AiRouteId, number> = {
  propose_content_idea: 500_000,
  generate_caption: 500_000,
  enrich_description: 1_000_000,
};

/**
 * Independent restatement of the canonical tariff table
 * (`ai_runtime.py` TARIFFS) in integer micro-USD per 1K tokens.
 *
 * The guard deliberately does NOT import the canonical table: it must be able
 * to fail even if the runtime's pricing drifts, so the priced pairs are written
 * out here and any other pair is refused rather than priced arbitrarily.
 */
const TARIFF_MICRO_USD_PER_1K: Record<string, { input: number; output: number }> = {
  'mock/mock-1': { input: 0, output: 0 },
};

/** Persian titles of the canonical routes. */
const ROUTE_TITLES: Record<AiRouteId, string> = {
  propose_content_idea: 'پیشنهاد ایدهٔ محتوا',
  generate_caption: 'ساخت کپشن',
  enrich_description: 'غنی‌سازی توضیح کالا',
};

const PROVIDER = 'mock';
const MODEL = 'mock-1';

/** One route row BEFORE derivation (`successRatePercent` is derived below). */
interface RouteSpec {
  id: AiRouteId;
  invocations: number | null;
  succeeded: number | null;
  failed: number | null;
  p95LatencyMs: number | null;
  lastRunUtc: string | null;
  stages: AgentStageUsage[];
}

/** One cost row BEFORE derivation (totals, ratio and pressure are derived). */
interface CostSpec {
  routeId: AiRouteId;
  promptTokens: number | null;
  completionTokens: number | null;
  tokenCeiling: number;
}

/** One proposal row; `decidedAtUtc` must agree with the terminal state. */
interface ProposalSpec {
  id: string;
  titleFa: string;
  routeId: AiRouteId;
  state: ProposalState;
  submittedAtUtc: string;
  decidedAtUtc: string | null;
  lastMutation: ProposalMutation;
}

/**
 * The steady route catalog: a measured, healthy runtime with one recorded
 * failure per route where the canonical pipeline legitimately diverges.
 */
const BASE_ROUTES: RouteSpec[] = [
  {
    id: 'propose_content_idea',
    invocations: 24,
    succeeded: 23,
    failed: 1,
    p95LatencyMs: 1_240,
    lastRunUtc: '2026-10-08T07:58:10.000Z',
    stages: [
      { stage: 'provider_call', invocations: 24 },
      { stage: 'validation', invocations: 24 },
      { stage: 'lifecycle', invocations: 23 },
      { stage: 'hitl_decision', invocations: 23 },
    ],
  },
  {
    id: 'generate_caption',
    invocations: 41,
    succeeded: 41,
    failed: 0,
    p95LatencyMs: 980,
    lastRunUtc: '2026-10-08T07:59:02.000Z',
    stages: [
      { stage: 'provider_call', invocations: 41 },
      { stage: 'validation', invocations: 41 },
      { stage: 'lifecycle', invocations: 41 },
      { stage: 'hitl_decision', invocations: 40 },
    ],
  },
  {
    id: 'enrich_description',
    invocations: 12,
    succeeded: 11,
    failed: 1,
    p95LatencyMs: 1_875,
    lastRunUtc: '2026-10-08T07:57:20.000Z',
    stages: [
      { stage: 'provider_call', invocations: 12 },
      { stage: 'validation', invocations: 12 },
      { stage: 'divergence', invocations: 1 },
      { stage: 'lifecycle', invocations: 11 },
    ],
  },
];

/** Steady token readings: comfortably below the daily allowance. */
const BASE_COST: CostSpec[] = [
  { routeId: 'propose_content_idea', promptTokens: 18_400, completionTokens: 6_100, tokenCeiling: TOKEN_CEILING_PER_DAY },
  { routeId: 'generate_caption', promptTokens: 22_000, completionTokens: 5_400, tokenCeiling: TOKEN_CEILING_PER_DAY },
  { routeId: 'enrich_description', promptTokens: 16_500, completionTokens: 4_100, tokenCeiling: TOKEN_CEILING_PER_DAY },
];

/** The steady proposal set: every lifecycle state represented exactly once. */
const BASE_PROPOSALS: ProposalSpec[] = [
  {
    id: 'aiprop|8f21c4d90ab3',
    titleFa: 'پیش‌نویس توضیح کالای P90401',
    routeId: 'enrich_description',
    state: 'IN_REVIEW',
    submittedAtUtc: '2026-10-08T06:12:00.000Z',
    decidedAtUtc: null,
    lastMutation: 'AI_GENERATED',
  },
  {
    id: 'aiprop|1ce9a75d2f08',
    titleFa: 'ایدهٔ محتوای کمپین پاییز',
    routeId: 'propose_content_idea',
    state: 'PROPOSED',
    submittedAtUtc: '2026-10-08T07:31:00.000Z',
    decidedAtUtc: null,
    lastMutation: 'AI_GENERATED',
  },
  {
    id: 'aiprop|44b0e6f7c215',
    titleFa: 'کپشن اینستاگرام کالای P90402',
    routeId: 'generate_caption',
    state: 'ACCEPTED',
    submittedAtUtc: '2026-10-07T18:05:00.000Z',
    decidedAtUtc: '2026-10-07T19:22:00.000Z',
    lastMutation: 'HUMAN_ENTERED',
  },
  {
    id: 'aiprop|2f6b90ac41de',
    titleFa: 'ایدهٔ محتوای ماهانهٔ فروشگاه',
    routeId: 'propose_content_idea',
    state: 'MODIFIED_BY_HUMAN',
    submittedAtUtc: '2026-10-07T09:48:00.000Z',
    decidedAtUtc: '2026-10-07T11:03:00.000Z',
    lastMutation: 'HUMAN_ENTERED',
  },
  {
    id: 'aiprop|9a7d3e51b8c0',
    titleFa: 'توضیح کالای P90403',
    routeId: 'enrich_description',
    state: 'REJECTED',
    submittedAtUtc: '2026-10-06T14:20:00.000Z',
    decidedAtUtc: '2026-10-06T15:41:00.000Z',
    lastMutation: 'HUMAN_ENTERED',
  },
];

/** Route overrides per scenario (merged over the steady catalog). */
const ROUTE_OVERRIDES: Partial<
  Record<AiOpsScenario, Partial<Record<AiRouteId, Partial<RouteSpec>>>>
> = {
  'token-pressure': {
    enrich_description: { invocations: 19, succeeded: 17, failed: 2, p95LatencyMs: 2_410 },
  },
};

/** Cost overrides per scenario. */
const COST_OVERRIDES: Partial<Record<AiOpsScenario, Partial<Record<AiRouteId, Partial<CostSpec>>>>> = {
  'token-pressure': {
    // 38_400 / 40_000 = 0.96 and 35_600 / 40_000 = 0.89: both above the
    // canonical soft ratio, both still inside the allowance (no invented spend).
    propose_content_idea: { promptTokens: 29_800, completionTokens: 8_600 },
    enrich_description: { promptTokens: 26_500, completionTokens: 9_100 },
  },
};

/** Proposal counts per scenario (`undefined` = the steady set). */
const PROPOSAL_COUNT: Partial<Record<AiOpsScenario, number>> = {
  idle: 0,
};

/**
 * The three gated controls (D-171 §5.5/§6).
 *
 * Every one is DISABLED: running a route calls a provider, querying the memory
 * layer needs the external connection that D-045 gates, and connecting that
 * layer IS the owner decision — none of the three may originate from this
 * interface. A disabled control always states why.
 */
const RUN_ROUTE_REASON =
  'اجرای مسیر هوش مصنوعی یک فراخوانی ارائه‌دهنده است؛ این رابط هیچ مسیر فراخوانی و هیچ اعتبارنامه‌ای ندارد (D-171 §5.5/§6)';

const QUERY_MEMORY_REASON =
  'خواندن حافظهٔ مشترک نیازمند اتصال بیرونی است و اتصال بیرونی تا عبور از گیت مالک برقرار نمی‌شود (D-045/D-142)';

const CONNECT_MEMORY_REASON =
  'برقراری اتصال لایهٔ حافظه، خودِ تصمیم مالک است و از این رابط انجام نمی‌شود؛ وضعیت تنها نمایش داده می‌شود (D-142/D-045)';

/** The gated controls, exported so any future live source renders the same reality. */
export const AI_OPS_CONTROLS: AiOpsControlSpec[] = [
  {
    id: 'RUN_AGENT_ROUTE',
    titleFa: 'اجرای دستی مسیر هوش مصنوعی',
    descriptionFa:
      'اجرای یک مسیر هوش مصنوعی از روی این صفحه؛ این کنش یک فراخوانی ارائه‌دهنده می‌سازد و از رابط کنترل انجام نمی‌شود (D-171 §5.5)',
    enabled: false,
    blockedReasonFa: RUN_ROUTE_REASON,
  },
  {
    id: 'QUERY_MEMORY',
    titleFa: 'پرس‌وجوی حافظهٔ مشترک',
    descriptionFa:
      'خواندن نام‌فضاها و بردارهای حافظهٔ مشترک؛ نیازمند اتصال بیرونی است که تا گیت مالک برقرار نمی‌شود (D-045)',
    enabled: false,
    blockedReasonFa: QUERY_MEMORY_REASON,
  },
  {
    id: 'CONNECT_MEMORY_LAYER',
    titleFa: 'برقراری اتصال لایهٔ حافظه',
    descriptionFa:
      'وصل‌کردن لایهٔ حافظهٔ مشترک به سرویس بیرونی؛ این تصمیم یک‌بارمصرف و مالک‌محور است (D-139/D-142)',
    enabled: false,
    blockedReasonFa: CONNECT_MEMORY_REASON,
  },
];

/**
 * The memory layer for a scenario.
 *
 * `NOT_CONNECTED` (the mandated steady state, D-171 §5.5) and `UNKNOWN` (no
 * reading was produced at all) both carry NO namespaces and NO counts: an
 * unconnected layer has nothing to enumerate, and reporting zero would read as
 * a measurement.
 */
function memoryFor(scenario: AiOpsScenario, provenance: Provenance): MemoryLayerStatus {
  if (scenario === 'all-unknown') {
    return {
      state: 'UNKNOWN',
      detailFa:
        'هیچ خوانشی از لایهٔ حافظه تولید نشد؛ وضعیت نامشخص است و هیچ نام‌فضا یا شمارشی نمایش داده نمی‌شود.',
      namespaces: [],
      totalVectors: null,
      totalBytes: null,
      lastMeasuredUtc: null,
      provenance,
    };
  }
  return {
    state: 'NOT_CONNECTED',
    detailFa:
      'لایهٔ حافظهٔ مشترک برنامه‌ریزی‌شده است و هنوز وصل نشده؛ تا عبور از گیت مالک هیچ اتصال زنده‌ای برقرار نمی‌شود و هیچ شمارشی جعل نمی‌گردد (D-142/D-045).',
    namespaces: [],
    totalVectors: null,
    totalBytes: null,
    lastMeasuredUtc: null,
    provenance,
  };
}

/** Derived success rate: `null` when nothing was invoked — never 100%. */
export function successRatePercent(succeeded: number | null, invocations: number | null): number | null {
  if (succeeded === null || invocations === null || invocations === 0) return null;
  return Math.round((succeeded / invocations) * 1000) / 10;
}

/** Derived consumption ratio, rounded to four decimals like the guard compares. */
export function consumedRatio(totalTokens: number | null, ceiling: number): number | null {
  if (totalTokens === null || ceiling <= 0) return null;
  return Math.round((totalTokens / ceiling) * 10_000) / 10_000;
}

/** Derived pressure from the ratio via the canonical soft ratio (D-063). */
export function budgetPressure(ratio: number | null): BudgetPressure {
  if (ratio === null) return 'UNKNOWN';
  if (ratio > 1) return 'EXCEEDED';
  if (ratio >= SOFT_BUDGET_RATIO) return 'WARNING';
  return 'OK';
}

/**
 * Integer micro-USD for a priced (provider, model) pair, or `null` for a pair
 * the canonical tariff table does not price — an unpriced pair is never given
 * an invented price (the canonical `estimate_cost` marks it `unknown_tariff`).
 */
export function canonicalCostMicroUsd(
  provider: string,
  model: string,
  promptTokens: number,
  completionTokens: number,
): number | null {
  const tariff = TARIFF_MICRO_USD_PER_1K[`${provider}/${model}`];
  if (tariff === undefined) return null;
  return Math.round((promptTokens / 1000) * tariff.input + (completionTokens / 1000) * tariff.output);
}

function routesFor(scenario: AiOpsScenario): AgentRouteObservability[] {
  const unmeasured = scenario === 'all-unknown';
  const overrides = unmeasured ? {} : (ROUTE_OVERRIDES[scenario] ?? {});
  return BASE_ROUTES.map((spec) => {
    const merged: RouteSpec = { ...spec, ...(overrides[spec.id] ?? {}) };
    if (unmeasured || scenario === 'idle') {
      return {
        id: merged.id,
        titleFa: ROUTE_TITLES[merged.id],
        invocations: scenario === 'idle' ? 0 : null,
        succeeded: scenario === 'idle' ? 0 : null,
        failed: scenario === 'idle' ? 0 : null,
        successRatePercent: null,
        p95LatencyMs: null,
        lastRunUtc: null,
        stages: [],
      };
    }
    return {
      id: merged.id,
      titleFa: ROUTE_TITLES[merged.id],
      invocations: merged.invocations,
      succeeded: merged.succeeded,
      failed: merged.failed,
      successRatePercent: successRatePercent(merged.succeeded, merged.invocations),
      p95LatencyMs: merged.p95LatencyMs,
      lastRunUtc: merged.lastRunUtc,
      stages: merged.stages,
    };
  });
}

function costFor(scenario: AiOpsScenario): TokenCostAnalytics[] {
  const unmeasured = scenario === 'all-unknown';
  const overrides = unmeasured ? {} : (COST_OVERRIDES[scenario] ?? {});
  return BASE_COST.map((spec) => {
    const merged: CostSpec = { ...spec, ...(overrides[spec.routeId] ?? {}) };
    const measured = !unmeasured && scenario !== 'idle';
    const promptTokens = measured ? merged.promptTokens : scenario === 'idle' ? 0 : null;
    const completionTokens = measured ? merged.completionTokens : scenario === 'idle' ? 0 : null;
    const totalTokens =
      promptTokens === null || completionTokens === null ? null : promptTokens + completionTokens;
    const ratio = consumedRatio(totalTokens, merged.tokenCeiling);
    return {
      routeId: merged.routeId,
      provider: PROVIDER,
      model: MODEL,
      promptTokens,
      completionTokens,
      totalTokens,
      resource: 'llm_tokens',
      window: 'per_logical_day',
      tokenCeiling: merged.tokenCeiling,
      consumedRatio: ratio,
      pressure: budgetPressure(ratio),
      costMicroUsd:
        promptTokens === null || completionTokens === null
          ? null
          : canonicalCostMicroUsd(PROVIDER, MODEL, promptTokens, completionTokens),
      runBudgetMicroUsd: RUN_BUDGET_MICRO_USD[merged.routeId],
    };
  });
}

function proposalsFor(scenario: AiOpsScenario): AiProposalDraft[] {
  if (scenario === 'all-unknown') return [];
  const count = PROPOSAL_COUNT[scenario];
  const specs = count === undefined ? BASE_PROPOSALS : BASE_PROPOSALS.slice(0, count);
  return specs.map((spec) => ({ ...spec }));
}

const PRESSURE_SEVERITY: Record<BudgetPressure, number> = {
  OK: 0,
  UNKNOWN: 1,
  WARNING: 2,
  EXCEEDED: 3,
};

/** Count states and resolve the worst budget pressure. The strip DERIVES this. */
export function summarizeAiOps(
  memory: MemoryLayerStatus,
  routes: AgentRouteObservability[],
  cost: TokenCostAnalytics[],
  proposals: AiProposalDraft[],
): AiOpsOverview {
  let worstBudgetPressure: BudgetPressure = 'OK';
  for (const row of cost) {
    if (PRESSURE_SEVERITY[row.pressure] > PRESSURE_SEVERITY[worstBudgetPressure]) {
      worstBudgetPressure = row.pressure;
    }
  }

  const measured = routes.filter((route) => route.invocations !== null).length;
  const awaiting = proposals.filter(
    (proposal) => proposal.state === 'PROPOSED' || proposal.state === 'IN_REVIEW',
  ).length;

  return {
    memoryState: memory.state,
    routesMeasured: measured,
    routesUnmeasured: routes.length - measured,
    worstBudgetPressure,
    proposalsAwaitingDecision: awaiting,
    proposalsDecided: proposals.length - awaiting,
    hasBudgetAlert: cost.some(
      (row) => row.pressure === 'WARNING' || row.pressure === 'EXCEEDED',
    ),
  };
}

/** True when the state means "connected", i.e. may enumerate namespaces. */
function isConnected(state: MemoryLayerStatus['state']): boolean {
  return state === 'CONNECTED' || state === 'DEGRADED';
}

/** True exactly for the D-064 terminal states. */
function isTerminal(state: ProposalState): boolean {
  return state === 'ACCEPTED' || state === 'REJECTED' || state === 'MODIFIED_BY_HUMAN';
}

/**
 * Assert the snapshot cannot display a state the canonical rules forbid.
 *
 * Throwing is the fail-closed behaviour: a contradictory AI-ops snapshot is
 * never rendered with a reassuring badge.
 */
export function assertAiOpsConsistency(snapshot: AiOpsSnapshot): AiOpsSnapshot {
  const problems: string[] = [];

  // ── memory layer (D-142) ──────────────────────────────────────────────────
  const memory = snapshot.memory;
  if (!memory.detailFa.trim()) problems.push('memory: detail must not be empty');
  if (memory.provenance !== snapshot.provenance) {
    problems.push('memory: provenance must match the snapshot provenance');
  }
  if (!isConnected(memory.state)) {
    if (memory.namespaces.length > 0) {
      problems.push(`${memory.state} memory layer must not enumerate namespaces (fail-closed)`);
    }
    if (memory.totalVectors !== null || memory.totalBytes !== null) {
      problems.push(`${memory.state} memory layer must not report counts (fail-closed)`);
    }
    if (memory.state === 'NOT_CONNECTED' && memory.lastMeasuredUtc !== null) {
      problems.push('NOT_CONNECTED memory layer must not carry a measurement instant');
    }
  } else {
    if (memory.namespaces.length === 0) {
      problems.push(`${memory.state} memory layer must enumerate at least one namespace`);
    }
    for (const namespace of memory.namespaces) {
      if (!namespace.name.trim()) problems.push('memory namespace name must not be empty');
      if (!Number.isInteger(namespace.vectors) || namespace.vectors < 0) {
        problems.push(`memory namespace ${namespace.name}: vectors must be a non-negative integer`);
      }
      if (!Number.isInteger(namespace.bytes) || namespace.bytes < 0) {
        problems.push(`memory namespace ${namespace.name}: bytes must be a non-negative integer`);
      }
    }
    const vectors = memory.namespaces.reduce((sum, namespace) => sum + namespace.vectors, 0);
    const bytes = memory.namespaces.reduce((sum, namespace) => sum + namespace.bytes, 0);
    if (memory.totalVectors !== vectors) {
      problems.push(`memory totalVectors ${memory.totalVectors} != derived ${vectors}`);
    }
    if (memory.totalBytes !== bytes) {
      problems.push(`memory totalBytes ${memory.totalBytes} != derived ${bytes}`);
    }
    if (memory.lastMeasuredUtc === null || !ISO_RE.test(memory.lastMeasuredUtc)) {
      problems.push(`${memory.state} memory layer requires an ISO-8601 measurement instant`);
    }
  }
  if (memory.lastMeasuredUtc !== null && !ISO_RE.test(memory.lastMeasuredUtc)) {
    problems.push('memory lastMeasuredUtc is not an ISO-8601 literal');
  }

  // ── agent observability ──────────────────────────────────────────────────
  const routeIds = snapshot.routes.map((route) => route.id);
  for (const id of ROUTE_IDS) {
    if (!routeIds.includes(id)) {
      problems.push(`missing route ${id} (all three canonical routes are required)`);
    }
  }
  if (new Set(routeIds).size !== routeIds.length) problems.push('duplicate route id in snapshot');

  for (const route of snapshot.routes) {
    const label = route.id;
    if (!route.titleFa.trim()) problems.push(`${label}: title must not be empty`);

    const counts = [route.invocations, route.succeeded, route.failed];
    const anyPresent = counts.some((value) => value !== null);
    const allPresent = counts.every((value) => value !== null);
    if (anyPresent && !allPresent) {
      problems.push(`${label}: a route is either measured or unmeasured, never half-measured`);
    }
    for (const [field, value] of [
      ['invocations', route.invocations],
      ['succeeded', route.succeeded],
      ['failed', route.failed],
    ] as Array<[string, number | null]>) {
      if (value !== null && (!Number.isInteger(value) || value < 0)) {
        problems.push(`${label}: ${field} must be a non-negative integer`);
      }
    }

    if (!allPresent) {
      if (route.successRatePercent !== null || route.p95LatencyMs !== null || route.lastRunUtc !== null) {
        problems.push(`${label}: an unmeasured route must not carry readings (fail-closed)`);
      }
      if (route.stages.length > 0) {
        problems.push(`${label}: an unmeasured route must not report stage usage`);
      }
      continue;
    }

    const invocations = route.invocations as number;
    const succeeded = route.succeeded as number;
    const failed = route.failed as number;
    if (succeeded + failed !== invocations) {
      problems.push(
        `${label}: succeeded + failed ${succeeded + failed} != invocations ${invocations}`,
      );
    }
    const expectedRate = successRatePercent(succeeded, invocations);
    if (route.successRatePercent !== expectedRate) {
      problems.push(`${label}: successRatePercent ${route.successRatePercent} != derived ${expectedRate}`);
    }
    if (invocations === 0 && route.successRatePercent !== null) {
      problems.push(`${label}: zero invocations must not claim a success rate (fail-closed)`);
    }
    if (invocations > 0) {
      if (route.p95LatencyMs === null || !Number.isInteger(route.p95LatencyMs) || route.p95LatencyMs < 0) {
        problems.push(`${label}: a measured route requires a non-negative integer p95 latency`);
      }
      if (route.lastRunUtc === null || !ISO_RE.test(route.lastRunUtc)) {
        problems.push(`${label}: a measured route requires an ISO-8601 last-run instant`);
      }
    }

    const stages = route.stages.map((usage) => usage.stage);
    if (new Set(stages).size !== stages.length) problems.push(`${label}: duplicate stage usage row`);
    for (const usage of route.stages) {
      if (!STAGE_IDS.includes(usage.stage)) {
        problems.push(`${label}: unknown observability stage ${usage.stage}`);
      }
      if (!Number.isInteger(usage.invocations) || usage.invocations <= 0) {
        problems.push(`${label}: stage ${usage.stage} usage must be a positive integer`);
      }
    }
  }

  // ── token & cost analytics (D-063/D-127, canonical tariff) ───────────────
  const costIds = snapshot.cost.map((row) => row.routeId);
  for (const id of ROUTE_IDS) {
    if (!costIds.includes(id)) problems.push(`missing cost row for route ${id}`);
  }
  if (new Set(costIds).size !== costIds.length) problems.push('duplicate cost row in snapshot');

  for (const row of snapshot.cost) {
    const label = row.routeId;
    const readings = [row.promptTokens, row.completionTokens];
    const anyPresent = readings.some((value) => value !== null);
    const allPresent = readings.every((value) => value !== null);
    if (anyPresent && !allPresent) {
      problems.push(`${label}: token readings must be all present or all absent`);
    }
    for (const [field, value] of [
      ['promptTokens', row.promptTokens],
      ['completionTokens', row.completionTokens],
    ] as Array<[string, number | null]>) {
      if (value !== null && (!Number.isInteger(value) || value < 0)) {
        problems.push(`${label}: ${field} must be a non-negative integer`);
      }
    }
    if (!Number.isInteger(row.tokenCeiling) || row.tokenCeiling <= 0) {
      problems.push(`${label}: tokenCeiling must be a positive integer`);
    }
    if (!Number.isInteger(row.runBudgetMicroUsd) || row.runBudgetMicroUsd < 0) {
      problems.push(`${label}: runBudgetMicroUsd must be a non-negative integer (micro-USD)`);
    }
    if (!row.provider.trim() || !row.model.trim()) {
      problems.push(`${label}: provider and model must be named`);
    }

    const expectedTotal =
      row.promptTokens === null || row.completionTokens === null
        ? null
        : row.promptTokens + row.completionTokens;
    if (row.totalTokens !== expectedTotal) {
      problems.push(`${label}: totalTokens ${row.totalTokens} != derived ${expectedTotal}`);
    }
    const expectedRatio = consumedRatio(row.totalTokens, row.tokenCeiling);
    if (row.consumedRatio !== expectedRatio) {
      problems.push(`${label}: consumedRatio ${row.consumedRatio} != derived ${expectedRatio}`);
    }
    const expectedPressure = budgetPressure(row.consumedRatio);
    if (row.pressure !== expectedPressure) {
      problems.push(`${label}: pressure ${row.pressure} != derived ${expectedPressure}`);
    }

    if (row.totalTokens === null) {
      if (row.costMicroUsd !== null) {
        problems.push(`${label}: an unmeasured consumption must not carry a cost (fail-closed)`);
      }
    } else {
      const expectedCost = canonicalCostMicroUsd(
        row.provider,
        row.model,
        row.promptTokens as number,
        row.completionTokens as number,
      );
      if (expectedCost === null) {
        problems.push(
          `${label}: (${row.provider}/${row.model}) is outside the canonical tariff table — no price may be invented`,
        );
      } else if (row.costMicroUsd !== expectedCost) {
        problems.push(`${label}: costMicroUsd ${row.costMicroUsd} != canonical tariff ${expectedCost}`);
      }
    }
  }

  // ── proposals (D-060/D-064) ──────────────────────────────────────────────
  const proposalIds = snapshot.proposals.map((proposal) => proposal.id);
  if (new Set(proposalIds).size !== proposalIds.length) {
    problems.push('duplicate proposal id in snapshot');
  }
  for (const proposal of snapshot.proposals) {
    const label = proposal.id;
    if (!proposal.titleFa.trim()) problems.push(`${label}: title must not be empty`);
    if (!ROUTE_IDS.includes(proposal.routeId)) problems.push(`${label}: unknown route ${proposal.routeId}`);
    if (!PROPOSAL_STATES.includes(proposal.state)) problems.push(`${label}: unknown state ${proposal.state}`);
    if (!/^aiprop\|[0-9a-f]{12}$/.test(proposal.id)) {
      problems.push(`${label}: id must be the canonical aiprop|<pid> durable form`);
    }
    if (!ISO_RE.test(proposal.submittedAtUtc)) {
      problems.push(`${label}: submittedAtUtc is not an ISO-8601 literal`);
    }
    if (isTerminal(proposal.state)) {
      if (proposal.decidedAtUtc === null || !ISO_RE.test(proposal.decidedAtUtc)) {
        problems.push(`${label}: a terminal state requires the human decision instant`);
      } else if (proposal.decidedAtUtc < proposal.submittedAtUtc) {
        problems.push(`${label}: decision instant precedes the submission`);
      }
      if (proposal.lastMutation !== 'HUMAN_ENTERED') {
        problems.push(`${label}: a terminal state must carry HUMAN_ENTERED provenance (D-026)`);
      }
    } else {
      if (proposal.decidedAtUtc !== null) {
        problems.push(`${label}: a non-terminal state must not carry a decision instant`);
      }
      if (proposal.lastMutation !== 'AI_GENERATED') {
        problems.push(`${label}: a pending draft must carry AI_GENERATED provenance (D-026)`);
      }
    }
  }

  // ── the seam that produced the snapshot is stated, not inferred ──────────
  if (snapshot.sourceMode === 'MOCK' && snapshot.provenance === 'live') {
    problems.push('a MOCK snapshot must not claim live provenance');
  }
  if (snapshot.sourceMode === 'LIVE' && snapshot.provenance === 'mock') {
    problems.push('a LIVE snapshot must not claim mock provenance');
  }

  // ── summary is derived, never retyped ────────────────────────────────────
  const expected = summarizeAiOps(snapshot.memory, snapshot.routes, snapshot.cost, snapshot.proposals);
  for (const key of Object.keys(expected) as Array<keyof AiOpsOverview>) {
    if (snapshot.summary[key] !== expected[key]) {
      problems.push(`summary.${key} ${snapshot.summary[key]} != ${expected[key]}`);
    }
  }

  // ── gated controls (D-171 §5.5 constraints / §6) ─────────────────────────
  for (const control of snapshot.controls) {
    if (!control.titleFa.trim() || !control.descriptionFa.trim()) {
      problems.push(`${control.id}: title and description must not be empty`);
    }
    if (
      control.enabled &&
      (!snapshot.providerGate.providerCallPathConnected || !snapshot.providerGate.credentialPresent)
    ) {
      problems.push(
        `${control.id}: control enabled without a provider call path and a credential (D-171 §5.5/§6)`,
      );
    }
    if (control.enabled && control.blockedReasonFa.length > 0) {
      problems.push(`${control.id}: enabled control must not carry a blocked reason`);
    }
    if (!control.enabled && !control.blockedReasonFa.trim()) {
      problems.push(`${control.id}: disabled control must state why it is unavailable`);
    }
  }

  if (problems.length > 0) {
    throw new Error(`fail-closed violation in AI ops snapshot: ${problems.join('; ')}`);
  }
  return snapshot;
}

/** Build the full snapshot for a scenario, guarded for fail-closed consistency. */
export function mockAiOps(scenario: AiOpsScenario = 'steady'): AiOpsSnapshot {
  const unavailable = scenario === 'all-unknown';
  const provenance: Provenance = unavailable ? 'unavailable' : 'mock';
  const memory = memoryFor(scenario, provenance);
  const routes = routesFor(scenario);
  const cost = costFor(scenario);
  const proposals = proposalsFor(scenario);
  const snapshot: AiOpsSnapshot = {
    generatedAt: MOCK_INSTANT,
    scenario,
    provenance,
    sourceMode: 'MOCK',
    memory,
    routes,
    cost,
    proposals,
    controls: AI_OPS_CONTROLS,
    // No provider call path and no credential exist in this phase, so every
    // control must be disabled — the guard enforces that pairing.
    providerGate: { providerCallPathConnected: false, credentialPresent: false },
    summary: summarizeAiOps(memory, routes, cost, proposals),
  };
  return assertAiOpsConsistency(snapshot);
}

/**
 * Read the active scenario from the environment.
 *
 * Defaults to `steady`; an unrecognised value falls back to `all-unknown`, so a
 * typo can never render as measured usage (fail-closed).
 */
export function activeAiOpsScenario(): AiOpsScenario {
  const raw = process.env.CP_AI_OPS_SCENARIO;
  if (raw === undefined || raw === '' || raw === 'steady') return 'steady';
  if (raw === 'token-pressure') return 'token-pressure';
  if (raw === 'idle') return 'idle';
  return 'all-unknown';
}

/** The mock implementation of the swap seam. */
export function createMockAiOpsSource(scenario: AiOpsScenario = 'steady'): AiOpsDataSource {
  return {
    async load(): Promise<AiOpsSnapshot> {
      return mockAiOps(scenario);
    },
  };
}

/**
 * The single seam for `/ai-engine`.
 *
 * Only the deterministic mock exists: no canonical read-only HTTP surface for
 * agent observability, token analytics or proposals has been wired, and the
 * shared-memory layer itself is PLANNED behind the D-045 owner gate (D-142).
 * The page therefore never claims a live reading, and this function has no
 * LIVE branch to drift.
 */
export async function getAiOpsSource(): Promise<AiOpsDataSource> {
  return createMockAiOpsSource(activeAiOpsScenario());
}
