#!/usr/bin/env node
/**
 * D-171 §2.3 / §10 — Phase 27.13 technical-asset census & view-isolation gate.
 *
 * Renders every route of the running control plane and proves, from the actual
 * HTML, BOTH directions of the view-isolation invariant:
 *
 *   1. BUSINESS VIEW — the text a non-technical shop owner can read contains
 *      ZERO technical assets: no container/service identity, no probe latency or
 *      measurement units, no machine status codes beyond the mandated UI state
 *      vocabulary, no trace/digest values, no payload references, no debug
 *      controls, no Latin machine keys.
 *   2. TECHNICAL VIEW — every declared technical asset is STILL RENDERED, in
 *      full: the census counts each gated surface and asserts its content
 *      markers are present in the console. Nothing was deleted or mocked out to
 *      make the Business view clean.
 *   3. CENSUS FIDELITY — the set of gated surfaces on each route equals the
 *      manifest below, so a new surface cannot appear ungated and a declared
 *      asset cannot silently disappear.
 *
 * Isolation is decided by the SAME mechanism the app uses — the Tailwind gate
 * variants on the pre-paint `data-view-mode` attribute — so this script walks the
 * markup exactly as the browser hides it:
 *   `[[data-view-mode=business]_&]:hidden`  → technical-only subtree
 *   `[[data-view-mode=technical]_&]:hidden` → business-only subtree
 * `sr-only` text and accessible names (`aria-label`, `title`, …) are audited
 * too, because a screen-reader user must not hear an id that the sighted user
 * cannot see.
 *
 * Requires the dev server (default http://localhost:3000). No dependencies:
 * exit 0 = every case passed, 1 = a violation. Run:
 *   node scripts/check-view-isolation.mjs [--base-url http://localhost:3000]
 *                                        [--dump] [--report <file>]
 */

import { writeFileSync } from 'node:fs';

// ── the census manifest ─────────────────────────────────────────────────────
// Every gated surface that must exist on a route, by its `data-surface` id.
const SHELL = ['shell-environment', 'shell-dependencies', 'shell-kill-switch', 'page-route-code'];

const SURFACES = {
  '/dashboard': [
    ...SHELL,
    'dashboard-page-meta',
    'dashboard-mock-notice',
    'dashboard-health',
    'dashboard-kpi-codes',
    'dashboard-approvals-identifiers',
    'dashboard-ledger-events',
    'dashboard-emergency-actions',
  ],
  '/automations': [
    ...SHELL,
    'automations-page-meta',
    'automations-notice',
    'automations-telemetry-strip',
    'automations-containers',
    'automations-gates',
    'automations-queues',
    'automations-override',
  ],
  '/hitl-queue': [
    ...SHELL,
    'hitl-page-meta',
    'hitl-notice',
    'hitl-table-identifiers',
    'hitl-action-panel',
  ],
  '/orders': [
    ...SHELL,
    'orders-page-meta',
    'orders-notice',
    'orders-revenue-footnote',
    'orders-table-identifiers',
    'orders-write-gate',
  ],
  '/inventory': [
    ...SHELL,
    'inventory-page-meta',
    'inventory-notice',
    'inventory-metrics-codes',
    'inventory-table-identifiers',
    'inventory-variant-key',
    'inventory-write-gate',
  ],
  // Phase 27.7 (AI Ops & Shared Memory Hub): the memory layer, the agent
  // observability table, the token/cost table, the proposal drafts and the
  // gated controls are console surfaces — the Business view reads the
  // aggregated card and the plain-Persian header/summary only.
  '/ai-engine': [
    ...SHELL,
    'ai-engine-page-meta',
    'ai-engine-notice',
    'ai-engine-memory',
    'ai-engine-routes',
    'ai-engine-cost',
    'ai-engine-proposals',
    'ai-engine-controls',
    'page-phase-ref',
  ],
  '/settings': [...SHELL, 'page-phase-ref'],
};

// Surfaces that only exist after an interaction (a drawer or an expanded row).
// They carry the same gate in the markup but cannot be counted from an initial
// render; Phase 27.13 verifies them in the browser (computed styles) instead.
const ON_DEMAND = [
  'orders-drawer-identifiers',
  'orders-drawer-payment-audit',
  'hitl-drawer-identifiers',
  'hitl-drawer-payload-diff',
  'hitl-drawer-reasoning-log',
  'inventory-row-identifiers',
  'inventory-provenance',
  'inventory-sync-history',
];

// Technical content that must still be visible in the console (≥ min matches).
const ASSET_PROOF = {
  '/dashboard': [
    { id: 'service-codes', re: /\b(?:postgres|redis|n8n|walrus|dokploy)\b/gi, min: 1 },
    { id: 'service-states', re: /\b(?:HEALTHY|DEGRADED|UNAVAILABLE|UNKNOWN|OK)\b/g, min: 1 },
    { id: 'ledger-traces', re: /\btrace-[0-9a-f]{6,}\b/gi, min: 1 },
    { id: 'measurement-times', re: /\b\d{2}:\d{2}\b/g, min: 1 },
  ],
  '/automations': [
    { id: 'container-refs', re: /\b(?:engine-local-[a-z0-9-]+|redis|dokploy)\b/gi, min: 1 },
    { id: 'gate-ids', re: /\bV-0\d\b/g, min: 9 },
    { id: 'container-statuses', re: /\b(?:HEALTHY|DEGRADED|DOWN|UNKNOWN)\b/g, min: 1 },
    { id: 'probe-latency-label', re: /(?:latencyMs|PROBE_LATENCY|ms\b|بدون پاسخ)/gi, min: 1 },
    { id: 'gate-statuses', re: /\b(?:PASS|BLOCKED|EVALUATING|BYPASS_PREVENTED)\b/g, min: 1 },
  ],
  '/hitl-queue': [
    { id: 'taxonomy-codes', re: /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, min: 1 },
    { id: 'engine-sources', re: /\b[a-z]+:[a-z_]+\b/g, min: 1 },
  ],
  '/orders': [
    { id: 'woo-record-ids', re: /\b\d{4,}\b/g, min: 1 },
  ],
  '/inventory': [
    { id: 'product-ids', re: /\bP\d{5}\b/g, min: 1 },
    { id: 'variant-keys', re: /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/g, min: 1 },
    { id: 'opaque-key-short-form', re: /\b[0-9a-f]{6,}[\u2026.]+[0-9a-f]{4}\b/g, min: 1 },
  ],
  '/ai-engine': [
    { id: 'roadmap-phase-ref', re: /Phase\s*27\.\d/g, min: 1 },
    { id: 'memory-layer-state', re: /\bNOT_CONNECTED\b/g, min: 1 },
    { id: 'route-task-types', re: /\b(?:propose_content_idea|generate_caption|enrich_description)\b/g, min: 3 },
    { id: 'observability-stages', re: /\b(?:provider_call|validation|divergence|lifecycle|hitl_decision|fallback)\b/g, min: 1 },
    { id: 'budget-resource', re: /\bllm_tokens\b/g, min: 1 },
    { id: 'proposal-ids', re: /\baiprop\|[0-9a-f]{12}\b/g, min: 1 },
    { id: 'proposal-states', re: /\b(?:PROPOSED|IN_REVIEW|ACCEPTED|REJECTED|MODIFIED_BY_HUMAN)\b/g, min: 1 },
    { id: 'latency-measurement', re: /\b\d[\d,]* ms\b/g, min: 1 },
  ],
  '/settings': [{ id: 'roadmap-phase-ref', re: /Phase\s*27\.\d/g, min: 1 }],
};

// Technical assets that must NOT appear in the Business view's readable text.
// Decision-doc cross references (D-121, D-146, D-171) and the mandated UI state
// vocabulary are traceability, not assets: they are allowed on both views
// (D-171 §3.1 "icon + Persian label + English status code").
const LEAK = [
  { name: 'infrastructure-service-name', re: /\b(?:postgres|postgresql|redis|n8n|walrus|dokploy|sidecar)\b/gi },
  { name: 'latin-machine-key', re: /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g },
  { name: 'machine-code', re: /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g },
  { name: 'gateway-or-gate-ref', re: /\b(?:GW|WOO)-\*?\d+\b/gi },
  { name: 'payload-digest', re: /\bsha256:[0-9a-f]+/gi },
  { name: 'trace-value', re: /\btrace-[0-9a-f]{6,}\b/gi },
  { name: 'raw-uuid', re: /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi },
  { name: 'latency-measurement', re: /\b\d+(?:\.\d+)?\s*ms\b/gi },
  { name: 'measurement-unit-or-protocol', re: /\b(?:CPU|RAM|MB|GB|METRICS|HTTP|JSON|SLA)\b/g },
  { name: 'machine-status-word', re: /\b(?:HEALTHY|DEGRADED|UNAVAILABLE|BLOCKED|EVALUATING|BYPASS_PREVENTED|STALE|FRESH|PASS|DOWN)\b/g },
  { name: 'container-ref', re: /\bengine-local-[a-z0-9-]+\b/gi },
  { name: 'integration-source-ref', re: /\b[a-z]+:[a-z_]+\b/g },
  { name: 'woo-prefix', re: /\bWoo:/g },
  { name: 'console-vocabulary-fa', re: /(کانتینر|تلمتری|سایدکار|پروب|کاوش زنده|لجر|ماتریس گیت|صف خام|کد وضعیت|کاننیکال|کنونیکال)/g },
  { name: 'gate-id', re: /\bV-\d{2}\b/g },
  // Deployed-artefact vocabulary a shop owner has no context for. Domain nouns
  // the spec itself puts in the Business view (SKU, the canonical Product ID and
  // record references such as ORD-####/HITL-####, the store platform's own
  // name) are allowed — the full boundary rule is recorded in DECISIONS.md
  // row 72 under Phase 27.13, and every shared value is a STRUCTURED reference
  // rather than an opaque machine key.
  { name: 'engineering-vocabulary-en', re: /\b(?:canonical|payload|endpoint|webhook|namespace|sidecar|latency|sweep|phases?)\b/gi },
  // Internal project vocabulary (roadmap phase labels) and finance acronyms a
  // shop owner has no context for: console-only assets (DECISIONS.md row 72).
  { name: 'roadmap-phase-ref', re: /\bPhase\s*\d+(?:\.\d+)?/gi },
  { name: 'finance-acronym', re: /\b(?:GMV|AOV|ROAS|CPC|QPS|WMS)\b/g },
  // The SHORTENED form of an opaque key (`a1f2c3d4…4c5d`) is the same asset as
  // the full UUID below it: gating only the full value would leave the asset
  // readable, so the census asserts the shortened rendering too.
  { name: 'opaque-key-fragment', re: /\b[0-9a-f]{6,}[\u2026.]+[0-9a-f]{4}\b/g },
  { name: 'endpoint', re: /\b(?:https?:\/\/|127\.0\.0\.1|localhost)\S*/gi },
];

// Business domain terms the OWNER has ruled are approved canonical commerce
// vocabulary, NOT IT jargon: a shop owner reads `SKU` (شناسه کالا / Stock
// Keeping Unit), `PRODUCT`, `ID` and `UTC` as their own words for their own
// goods, so they are explicitly permitted in Business cards AND table contents
// on every route (owner ruling 2026-10-07; DECISIONS.md row 72 / D-171).
// Keep this list owner-controlled: adding a term here widens what the census
// accepts as readable in the Business view.
const BUSINESS_TERMS = new Set([
  'SKU', 'PRODUCT', 'ID', 'UTC', 'DRY', 'RUN',
]);

// Mandated UI state vocabulary: every one of these codes is rendered as a
// badge next to a Persian label (D-171 §3.1/§3.5, "icon + Persian label +
// English status code"), so it is traceability, not a technical asset. The
// machine keys / taxonomy codes / measurement codes are deliberately NOT here —
// those are census assets and must not reach the Business view.
const ALLOWED_CODES = new Set([
  // Business card + provenance states. `NOT_CONNECTED` is the mandated memory
  // layer state of D-171 §5.5 (D-142 is PLANNED until the D-045 owner gate), so
  // it is a status code the Business view states explicitly rather than a
  // machine key it must hide.
  'OK', 'MOCK', 'LIVE', 'NO_DATA', 'UNKNOWN', 'REVIEW', 'ACTION', 'PROCESSING', 'NOT_CONNECTED',
  // HITL severity / status / decision
  'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'PENDING', 'PENDING_REVIEW', 'CLAIMED', 'EXPIRED',
  'APPROVED', 'REJECTED', 'MODIFIED', 'ESCALATED',
  // Commerce channel / payment / fulfillment / risk
  'WEB_STORE', 'INSTAGRAM_DM', 'TELEGRAM', 'PLACED', 'PAID', 'FAILED', 'PENDING_PAYMENT',
  'REFUNDED', 'CANCELLED', 'UNFULFILLED', 'FULFILLING', 'SHIPPED', 'DELIVERED', 'COMPLETED',
  'VALIDATED', 'NOT_APPLICABLE', 'SETTLED',
  // Inventory stock / sync / lock
  'IN_STOCK', 'LOW_STOCK', 'OUT_OF_STOCK', 'DRIFT', 'DRIFT_DETECTED', 'IN_SYNC', 'PENDING_SYNC',
  'SYNC_ERROR',
  'EXTERNAL_SYNC', 'IMPORTED', 'HUMAN_ENTERED', 'HUMAN_REVIEWED', 'HUMAN_VERIFIED',
  'AI_GENERATED', 'SYSTEM_GENERATED', 'NONE', 'PULL', 'PUSH', 'RECONCILE', 'STOCK_OVERRIDE',
  'PRICE_FREEZE',
  // Business nouns / traceability words (owner-ruled permitted terms)
  ...BUSINESS_TERMS,
]);

// ── argv ────────────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
function argValue(flag, fallback) {
  const index = argv.indexOf(flag);
  return index >= 0 && argv[index + 1] !== undefined ? argv[index + 1] : fallback;
}
const BASE_URL = argValue('--base-url', process.env.CP_BASE_URL ?? 'http://localhost:3000').replace(/\/$/, '');
const DUMP = argv.includes('--dump');
const EXPLAIN = argValue('--explain', null);
const REPORT = argValue('--report', null);

// ── markup → per-view readable text ─────────────────────────────────────────
const VOID_TAGS = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
const SKIP_TAGS = new Set(['head', 'script', 'style', 'template']);
const ATTR_TEXT = ['aria-label', 'aria-description', 'aria-valuetext', 'title', 'placeholder', 'alt'];

function decodeEntities(value) {
  return value
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&nbsp;/g, ' ');
}

const TAG_RE = /<(\/?)([a-zA-Z][a-zA-Z0-9:-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>/g;

/** Split the document into the text each view can actually read. */
function extract(html, needle) {
  /** First text node containing `needle`: the state it was judged with. */
  let witness = null;
  const business = [];
  const technical = [];
  const audible = { business: [], technical: [] };
  const surfaces = {};
  const stack = [];
  let cursor = 0;
  let match;

  TAG_RE.lastIndex = 0;
  while ((match = TAG_RE.exec(html)) !== null) {
    const text = decodeEntities(html.slice(cursor, match.index)).replace(/\s+/g, ' ').trim();
    cursor = TAG_RE.lastIndex;
    const parent = stack[stack.length - 1] ?? { businessOnly: false, technicalOnly: false };
    if (text) {
      if (!parent.technicalOnly) business.push(text);
      if (!parent.businessOnly) technical.push(text);
      if (needle !== null && witness === null && text.includes(needle)) {
        witness = {
          hiddenInBusiness: parent.technicalOnly,
          hiddenInTechnical: parent.businessOnly,
          chain: stack.map(
            (s) =>
              `${s.tag}${s.businessOnly ? '⟨business-only⟩' : ''}${s.technicalOnly ? '⟨technical-only⟩' : ''}[${(s.cls ?? '').slice(0, 55)}]`,
          ),
        };
      }
    }

    const [, closing, rawTag, attrs, selfClosing] = match;
    const tag = rawTag.toLowerCase();

    if (closing) {
      for (let index = stack.length - 1; index >= 0; index -= 1) {
        if (stack[index].tag === tag) {
          stack.length = index;
          break;
        }
      }
      continue;
    }

    const classValue = decodeEntities((attrs.match(/\bclass="([^"]*)"/) ?? [, ''])[1]);
    const own = gateOf(classValue);
    const businessOnly = own.businessOnly || parent.businessOnly;
    const technicalOnly = own.technicalOnly || parent.technicalOnly;
    const surface = (attrs.match(/\bdata-surface="([^"]*)"/) ?? [, null])[1];
    const gate = (attrs.match(/\bdata-view-gate="([^"]*)"/) ?? [, null])[1];
    if (surface !== null && gate !== null) surfaces[surface] = (surfaces[surface] ?? 0) + 1;

    const attributeText = ATTR_TEXT.map(
      (name) => (attrs.match(new RegExp(`\\b${name}="([^"]*)"`)) ?? [, null])[1],
    )
      .filter((value) => value !== null)
      .map((value) => decodeEntities(value).replace(/\s+/g, ' ').trim())
      .join(' ')
      .trim();
    if (attributeText) {
      if (!technicalOnly) audible.business.push(attributeText);
      if (!businessOnly) audible.technical.push(attributeText);
    }

    if (SKIP_TAGS.has(tag)) {
      const close = new RegExp(`</${tag}\\s*>`, 'i').exec(html.slice(cursor));
      if (close) {
        cursor += close.index + close[0].length;
        TAG_RE.lastIndex = cursor;
      }
      continue;
    }
    if (!VOID_TAGS.has(tag) && !selfClosing) {
      stack.push({ tag, businessOnly, technicalOnly, cls: classValue });
    }
  }

  const tail = decodeEntities(html.slice(cursor)).replace(/\s+/g, ' ').trim();
  const parent = stack[stack.length - 1] ?? { businessOnly: false, technicalOnly: false };
  if (tail && !parent.technicalOnly) business.push(tail);
  if (tail && !parent.businessOnly) technical.push(tail);

  return {
    business: `${business.join(' | ')} | ${audible.business.join(' | ')}`,
    technical: `${technical.join(' | ')} | ${audible.technical.join(' | ')}`,
    surfaces,
    witness,
  };
}

/**
 * Read the view gates a class attribute carries.
 *
 * The mechanism is the approved Tailwind arbitrary variant on the pre-paint
 * attribute, and the UTILITY after the variant decides the direction:
 *   `[[data-view-mode=technical]_&]:hidden` → business-only (hidden in console)
 *   `[[data-view-mode=technical]_&]:flex`   → technical-only (revealed in console)
 *   `[[data-view-mode=business]_&]:hidden`  → technical-only
 *   `[[data-view-mode=business]_&]:flex`    → business-only
 */
const VARIANT_RE = /\[\[data-view-mode=(business|technical)\]_&\]:([^\s"']+)/g;
function gateOf(classValue) {
  // `hidden` as a BASE utility is what makes a non-hiding variant a gate: the
  // element is hidden by default and only a view variant reveals it.
  const baseHidden = /(?:^|\s)hidden(?:\s|$)/.test(classValue);
  let businessOnly = false;
  let technicalOnly = false;
  for (const [, mode, chain] of classValue.matchAll(VARIANT_RE)) {
    // A stacked variant (`lg:grid-cols-1`) still names its LAST utility.
    const hides = chain.split(':').pop() === 'hidden';
    if (hides) {
      // `<view>:hidden` → the element belongs to the OTHER view.
      if (mode === 'technical') businessOnly = true;
      else technicalOnly = true;
    } else if (baseHidden) {
      // `hidden … <view>:<utility>` → revealed only in that view.
      if (mode === 'technical') technicalOnly = true;
      else businessOnly = true;
    }
    // Otherwise it is a layout variant inside a view (e.g. a single-column
    // grid in the Business view), not a gate.
  }
  return { businessOnly, technicalOnly };
}

/** Every non-allowlisted leak match in a text, with a readable excerpt. */
function leaks(text) {
  const found = [];
  for (const { name, re } of LEAK) {
    const pattern = new RegExp(re.source, re.flags.includes('g') ? re.flags : `${re.flags}g`);
    let hit;
    while ((hit = pattern.exec(text)) !== null) {
      const value = hit[0].trim();
      if (ALLOWED_CODES.has(value.toUpperCase())) continue;
      found.push({ name, value, excerpt: text.slice(Math.max(0, hit.index - 45), hit.index + 45) });
      if (found.length > 60) return found;
    }
  }
  return found;
}

function count(text, re) {
  const pattern = new RegExp(re.source, re.flags.includes('g') ? re.flags : `${re.flags}g`);
  return (text.match(pattern) ?? []).length;
}

// ── run ─────────────────────────────────────────────────────────────────────
const failures = [];
const rows = [];
const reportLines = [
  '# Phase 27.13 — technical asset census & view-isolation result',
  '',
  `Generated by \`node scripts/check-view-isolation.mjs --report …\` against \`${BASE_URL}\`.`,
  '',
  '| Route | gated technical surfaces | console asset proofs | Business-view leaks |',
  '|---|---|---|---|',
];

for (const [route, expected] of Object.entries(SURFACES)) {
  let html;
  try {
    const response = await fetch(`${BASE_URL}${route}`, { headers: { accept: 'text/html' } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    html = await response.text();
  } catch (error) {
    failures.push(`${route}: could not render (${error.message}) — is the dev server running?`);
    continue;
  }

  const { business, technical, surfaces, witness } = extract(html, EXPLAIN);
  const businessLeaks = leaks(business);

  const missing = expected.filter((id) => (surfaces[id] ?? 0) === 0);
  if (missing.length > 0) failures.push(`${route}: gated surface(s) missing from the markup: ${missing.join(', ')}`);
  if (businessLeaks.length > 0) {
    for (const leak of businessLeaks.slice(0, 12)) {
      failures.push(`${route}: [${leak.name}] "${leak.value}" in Business view — …${leak.excerpt}…`);
    }
  }

  const proofs = ASSET_PROOF[route] ?? [];
  const failedProofs = proofs.filter(({ re, min }) => count(technical, re) < min);
  for (const proof of failedProofs) {
    failures.push(`${route}: console asset "${proof.id}" missing or reduced in the technical view`);
  }

  rows.push({
    route,
    surfaces: Object.keys(surfaces).length,
    proofs: `${proofs.length - failedProofs.length}/${proofs.length}`,
    leaks: businessLeaks.length,
  });
  reportLines.push(
    `| \`${route}\` | ${Object.keys(surfaces).length} | ${proofs.length - failedProofs.length}/${proofs.length} | ${businessLeaks.length} |`,
  );

  if (EXPLAIN) {
    console.log(`\n===== ${route} — "${EXPLAIN}" =====`);
    console.log(
      `  hidden from Business view: ${witness ? witness.hiddenInBusiness : 'n/a'} | hidden from console: ${witness ? witness.hiddenInTechnical : 'n/a'}`,
    );
    console.log(`  ancestors at that text node: ${witness ? witness.chain.join(' > ') : 'n/a'}`);
  }

  if (DUMP) {
    console.log(`\n===== ${route} — BUSINESS =====\n${business.slice(0, 2600)}`);
    console.log(`\n===== ${route} — TECHNICAL =====\n${technical.slice(0, 2600)}`);
  }
}

console.log('\nroute'.padEnd(16), 'gated'.padStart(6), 'proofs'.padStart(7), 'leaks'.padStart(6));
for (const row of rows) {
  console.log(row.route.padEnd(16), String(row.surfaces).padStart(6), row.proofs.padStart(7), String(row.leaks).padStart(6));
}

console.log(`\non-demand surfaces (interaction-revealed; verified in the browser):\n  ${ON_DEMAND.join(', ')}`);

if (REPORT) {
  reportLines.push('', '## On-demand surfaces', '', `Interaction-revealed (verified in the browser, not from an initial render): ${ON_DEMAND.join(', ')}.`, '');
  writeFileSync(REPORT, `${reportLines.join('\n')}\n`, 'utf8');
  console.log(`\ncensus report written to ${REPORT}`);
}

if (failures.length > 0) {
  console.error(`\n✗ view isolation: ${failures.length} violation(s)\n`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}

console.log('\n✓ view isolation: every Business surface is clean and every console asset is intact');
