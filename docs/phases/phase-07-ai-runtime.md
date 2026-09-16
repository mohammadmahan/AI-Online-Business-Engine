# Phase 7 Specification: AI Runtime (M1 — Architecture, Structured Output Contracts, Model Routing)

- Status: **M1 in progress (design + safe local scaffolding)** — 2026-09-15
- Authority: MASTER_PLAN §13 Phase 7 ("Model routing, structured
  outputs, validation, cost control, provenance, logging, approval
  gates"); local-first D-053; governance D-026 (provenance),
  D-050 (authority tiers), D-052 (failure taxonomy), D-045
  (credentials), PROJECT_RULES §7 (AI provenance) and §3 ("AI may
  recommend but must not silently make high-risk decisions").
- Scope discipline: **no external AI API connection, no credentials,
  no keys** (owner-gated per D-045/D-053). All local development runs
  against **Mock AI Providers** behind a provider-neutral boundary.

## 1. Objective

Establish the AI runtime *before* any model integration: a
provider-neutral model-router boundary, strict JSON Schema contracts
for every AI output that can enter canonical flows, deterministic
validation, token/cost accounting with budget guardrails, and the
D-050 authority pipeline (AI proposes → system validates → human
reviews/approves). The runtime must be fully testable offline with
mock providers and become production-capable by adding a real provider
implementation — zero structural rewrites.

## 2. Governance baseline (inherited, not redefined)

| Source | Constraint adopted by Phase 7 |
| --- | --- |
| D-026 | Every AI-produced value carries provenance `AI_GENERATED` with actor, timestamp, review state; AI output is never presented as verified fact (RULES §7). |
| D-050 | Tier classification applies to *actions taken on* AI output. AI proposing text is Yellow-class work (queued for review); nothing AI-authored executes a Red operation without explicit human authorization. |
| D-052 | Provider failures classify through the same five-class taxonomy (A transient/retryable, B data-invariant, C authentication, D authority, E unknown→deterministic reconciliation). |
| D-060/D-027 | AI-generated artifacts that enter event flows ride the same D-027 idempotency and HITL materialization as any other source. |
| RULES §3/§8 | AI never invents Product/Variant IDs, SKUs, prices, stock, or controlled vocabulary; never fills missing optional fields with guesses. |

## 3. Architecture blueprint

```
task (enrich_description | propose_content_idea | generate_caption)
  → ModelRouter.route(task, policy)
      → provider selection (routing policy: task → provider, params)
  → AiProvider.generate(request)            ← provider-neutral boundary
      MockAiProvider (local, D-053)  … real adapters owner-gated
  → response normalization (text + usage + finish reason)
  → cost accounting (tokens × tariff table; budget guardrails)
  → StructuredOutputValidator (JSON Schema, deterministic)
      pass → AiProposal envelope (AI_GENERATED provenance, D-026)
      fail → Class-B validation failure (never silently repaired)
  → authority gate (D-050): proposal → queue/HITL (never auto-execute)
```

### 3.1 Model router abstraction (provider-neutral, RULES §35 pattern)

`AiProvider` interface — the ONLY thing the runtime knows about model
vendors (mirrors the `NotionProvider` / `MockWooAdapter` pattern):

```
generate(request: AiRequest) -> AiResponse
```

- `AiRequest`: task type, prompt payload (structured), schema id,
  temperature/max-tokens policy, idempotency tag, cost-center tag.
- `AiResponse`: raw text, parsed JSON (when schema-bound), usage
  {prompt_tokens, completion_tokens}, provider name, model id,
  finish reason, latency.
- Implementations: `MockAiProvider` (local, deterministic, scripted
  responses + configurable failure injection); real OpenAI/Anthropic/
  local-model adapters are **drop-in implementations, owner-gated**.
- Routing policy: pure data (`task_type → {provider, model, params,
  schema_id, budget}`); deterministic, testable, no hidden logic.

### 3.2 Structured output contracts (JSON Schema, strict)

Every AI output that may enter a canonical flow has a versioned JSON
Schema (draft 2020-12). Strict mode: `additionalProperties: false`
everywhere, all fields explicitly typed, enums for controlled
vocabulary references (codes only, never free text for Color/Size/
Category). Initial M1 contracts:

- **`content_idea_proposal.v1`** — title (Persian-safe string),
  working notes, target_lifecycle_state ∈ {Backlog} (AI may only
  propose new ideas at the root), rationale.
- **`caption_proposal.v1`** — caption text (Persian), hashtags
  (array of strings, size-capped), alt_text, media_ref (opaque
  reference string; AI never invents media).
- **`product_description_enrichment.v1`** — product_id (canonical
  Product ID pattern), variant_ids (array, may be empty),
  description_fa, seo_title_fa, seo_keywords (array), rationale.
  The validator cross-checks product_id shape only; existence checks
  belong to the calling flow (never to the model).

Schema evolution rule: additive optional fields only within a
version; breaking changes require a new version id and a decision
amendment (same discipline as the D-060 key serialization).

### 3.3 Cost accounting, rate limiting, budget guardrails

- **Usage ledger:** every call appends
  `{task, provider, model, tokens_in, tokens_out, cost_estimate,
  latency, occurred_at, correlation_id}` — local JSON ledger now
  (gitignored runtime state), later mirrored into PostgreSQL.
- **Tariff table:** static per-(provider, model) token prices in a
  config file; unknown model ⇒ cost 0 + explicit `unknown_tariff`
  flag (never a silent guess).
- **Budget guardrails:** per-task-type and global monetary budgets
  with deterministic enforcement: at ≥ soft limit (default 80%) the
  response is flagged `budget_warning`; at hard limit (100%) the call
  is **refused before dispatch** (Class-B guardrail refusal — cheaper
  than the request, enforced locally, never a silent overrun).
- **Rate limiting:** local token-bucket per provider (default
  conservative); refusals classify Class A (transient, retryable) —
  consistent with D-052's 429/rate-limit mapping.

### 3.4 Authority pipeline (D-050) and HITL integration

- AI output is **always a proposal**: `AiProposal` envelope =
  {schema id + version, validated payload, provider/model, usage,
  cost, provenance record id (AI_GENERATED), review state}.
- Proposals enter the existing VerificationQueue (D-028/D-060) —
  the same HITL surface Notion ingestion already uses; approval is a
  human decision (D-026 review-state advance), never automatic.
- No Phase 7 component may call Woo projection, price, publication,
  or vocabulary-mutation paths. Those remain Red/D-050 regardless of
  how good the proposal looks.

## 4. Failure mapping (D-052 alignment)

| Runtime event | Class | Retry |
| --- | --- | --- |
| Timeout / connection / 429 / rate limit | A | backoff (≤3) |
| Schema validation failure (model output) | B | never (log + re-prompt only as a NEW deterministic attempt with explicitly reduced scope, human-visible) |
| Credential missing/invalid (future real providers) | C | never |
| Attempt to auto-execute a Red action from AI output | D | abort |
| Unknown/ambiguous response shape | E | deterministic reconciliation, human review |

## 5. Milestone plan (M1–M4)

- **M1 — Architecture, contracts, routing — DONE (2026-09-15, commit
  `6916e04`):** blueprint (this document), JSON Schema contract module
  + validator, mock AI provider, model router, usage ledger + budget
  guardrails, D-062+ decision drafts, offline test suite. Zero network.
- **M2 — Proposal pipeline integration — DONE (2026-09-15):**
  `local/canonical/ai_proposal_lifecycle.py`: PROPOSED → IN_REVIEW →
  ACCEPTED / REJECTED / MODIFIED_BY_HUMAN, every transition a durable
  D-027 event (JSON store offline, live PostgreSQL store in
  integration tests), D-026 provenance per human decision, the
  AI_GENERATED record advanced exactly once at the terminal decision
  (provenance id carried inside the durable submit ref —
  restart-safe), terminal decisions immutable (identical re-decision
  = idempotent skip; changed re-decision refused), submit() accepts
  only router-validated AiProposal envelopes, `|applied` execution
  bookkeeping kept out of lifecycle history, applier runs on both
  accept and modify_accept. Authority boundary test-enforced:
  reviewer is keyword-only required, provider surface carries no
  decision verbs, module strings contain no Woo/Notion/publication
  integration. Suite: `local/tests/test_phase7_ai_runtime_m2.py`
  (25 tests: 14 offline state machine, 4 authority boundary, 7 live
  PostgreSQL round-trips incl. restart reconstruction, retry
  idempotency, and Class-B refusal of contract-violating payloads).
- **M3 — Task implementations on the contracts — DONE (2026-09-15):**
  `local/canonical/ai_tasks.py`: ContentIdeaTask (propose_content_idea,
  lifecycle-root Backlog re-checked deterministically in addition to
  the schema enum), CaptionTask (hashtags checked against approved
  D-029/D-031/D-032 vocabulary — a near-miss of an approved color/size
  term is Class B divergence, never silently repaired), DescriptionTask
  (product_id must exist in the canonical store; variant scope never
  widens). All dispatch exclusively through the ModelRouter →
  AiProvider boundary (MockAiProvider locally). Dry-run mode:
  generate + validate + divergence-check with ZERO pipeline
  persistence (no D-027 event, no provenance, no queue item) —
  router-level usage metering deliberately stays ON so dry-runs
  cannot evade D-063 budget accounting. Batch execution: per-entity
  reports, hard-budget refusal stops the batch BEFORE dispatch
  (provider called 0 times past the cap). Persist mode: valid output
  lands as a PROPOSED record via the M2 ProposalLifecycle (durable
  D-027 event + D-026 AI_GENERATED provenance + HITL queue item),
  idempotent by deterministic task tag; divergent output persists
  nothing and surfaces to HITL. Authority boundary: AST-scanned no
  Woo/Notion/publication/price edges, no decision verbs on the task
  surface. Suite: `local/tests/test_phase7_ai_runtime_m3.py`
  (20 tests: 6 offline task semantics, 5 divergence, 3 batch/budget,
  3 authority boundary, 3 live PostgreSQL round-trips).
- **M4 — Gate report + readiness review (remaining):** integrity audit
  of the full AI path (task → router → provider → contract →
  divergence → lifecycle → HITL), cost-ledger audit, authority-gate
  conformance proof, and the **explicitly deferred live-provider
  connectivity audit** (owner-gated; requires approved provider
  selection + credentials per D-045). M4 passing does not prove live
  provider compatibility.

## 6. Security & credentials (unchanged posture)

- No API keys exist; none are requested; none may be created without
  owner approval (D-045/D-053). MockAiProvider requires no secrets.
- `.env.example` gains placeholder **names only** for future provider
  credentials; real values live only in gitignored env files at
  implementation time. Keys never enter prompts, logs, ledger, Git,
  or docs (D-045 redaction rules apply to AI runtime logs).
- Prompt-injection posture (design note): AI output is data, never
  instructions; it can only produce a proposal envelope that humans
  review — the blast radius of a malicious/compromised model response
  is one rejected HITL item.

## 7. M1 acceptance criteria (done when)

1. Contract module with the three v1 JSON Schemas + deterministic
   validator (strict mode) and pinned positive/negative vectors.
2. MockAiProvider with scripted responses, failure injection (each
   D-052 class), and deterministic usage numbers.
3. ModelRouter with pure-data routing policy + budget guardrails
   (soft warning / hard refusal) + token-bucket limiter, offline-tested.
4. Usage ledger writes every call with cost estimates and
   unknown-tariff flagging.
5. D-062+ drafted (Proposed) and open-register rows updated.
6. Full battery green, zero skips, live layers running.

## 8. Traceability

| Concern | Anchor |
| --- | --- |
| AI provenance | D-026, RULES §7 (`AI_GENERATED` → human review states) |
| Authority tiers | D-050 (§3.4 pipeline; Red stays human-only) |
| Failure classification | D-052 (§4 mapping; classifier reuse) |
| Idempotency for AI event flows | D-027, D-060 key grammar |
| Credentials | D-045 (none exist; owner-gated) |
| Local-first | D-053 (mock providers until owner opens connectivity) |
| Canonical storage | D-055 (ledger mirrors into PostgreSQL later) |
| Open register rows | D-062 (router + contracts), D-063 (cost guardrails), D-064 (proposal pipeline) — **Approved 2026-09-15** |
