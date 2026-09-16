# Phase 8 — AI Product Manager & Operational Observability

- Date: 2026-09-16
- Authority: MASTER_PLAN §13 (Phase 7 extension) + **D-065 / D-066 / D-067 / D-068 (all Approved, 2026-09-16)**
- Discipline: local-first (D-053), zero-skip tests, AI authority boundary (D-050/D-062/D-064) unchanged and re-asserted.
- Milestone plan: **M1–M4 executed in ONE coherent batch** per the owner instruction.

---

## 1. Objective

Close the operational gap around the Phase 7 AI runtime: unified
observability (D-065), the safe path to real providers (D-066),
versioned prompts (D-067), and a review inbox for proposal volume
(D-068) — with the Red-path boundary intact and battery-proven.

## 2. Components

| Component | Module | Decision |
|---|---|---|
| Observability collector + cost report | `local/canonical/ai_observability.py` | D-065 |
| Live provider adapters (OpenAI/Anthropic) | `local/canonical/ai_providers_live.py` | D-066 |
| Template versioning registry + engine | `local/canonical/ai_templates.py`, `local/templates/` | D-067 |
| HITL review inbox + bulk orchestrator | `local/canonical/ai_hitl_service.py` | D-068 |

## 3. D-065 — Unified AI observability (`ai.observe.v1`)

- Record fields: `schema_version`, `correlation_id`, `occurred_at`,
  `stage` (`provider_call` | `validation` | `divergence` |
  `lifecycle` | `hitl_decision` | `fallback`), `task_type`,
  `provider`, `model`, `template_id`, `template_hash`,
  `prompt_tokens`, `completion_tokens`, `latency_ms`,
  `estimated_cost_usd`, `divergence_rate`, `hitl_decision`
  (`approve` | `reject` | `edit` | `none`), `status`,
  `error_class` (D-052 class when failed), `notes`.
- Storage: append-only JSONL (`AI_OBSERVABILITY_PATH`, default
  `local/volumes/observability/ai_observability.jsonl`); strict
  validation of every record before write (a malformed record is a
  Class-B programming error, never silently written).
- Correlation: the `AiProposal.correlation_id` is the key end-to-end;
  lifecycle/queue events reference the same id. The model never
  invents ids (RULES §3).
- Cost report: aggregate per `task_type` / `provider` / UTC day;
  reads only from the collector — no direct AI access to reporting.
- Authority: the collector is called by the deterministic pipeline
  (tasks, lifecycle, HITL service); the provider boundary remains
  free of any observability write path (AST battery-asserted).

## 4. D-066 — Live adapters & budget quarantine (`ai_providers_live.py`)

- `OpenAiProvider` / `AnthropicProvider` implement the D-062
  `AiProvider` interface over an **injectable transport callable**
  (`transport(request_dict) -> response_dict`). Tests inject fake
  transports — **zero network in the battery** (D-053).
- Construction gate: `AI_LIVE_ENABLED=true` **and** a non-empty API
  key in the environment, else the adapter raises a deterministic
  configuration error (Class B) — it never half-constructs.
- Failure mapping (D-052): transport timeout / connection error →
  Class A; 401/403 → Class C; 429 → Class A (rate limit);
  malformed JSON → Class B `OutputValidationError` via the router.
- **Graceful fallback:** the router-level helper
  `with_live_fallback()` runs the primary (live) provider and, on a
  missing key or 401/429, re-dispatches through `MockAiProvider`;
  the fallback emits a D-065 `stage=fallback` record so isolation is
  observable, and tests never stop.
- **Budget quarantine:** D-063's pre-dispatch hard refusal is the
  named production behavior `BUDGET_EXCEEDED_HALT` — at the daily cap
  the router halts before any dispatch (zero marginal provider calls).
  Optional `provider_name()`-based per-provider daily budgets come
  from routing policy, not from the model.
- Credentials: read from the environment ONLY at construction;
  never logged, never stored in the ledger or observability records
  (D-045 redaction applies).

## 5. D-067 — Template registry (`ai_templates.py`, `local/templates/`)

- Layout: `local/templates/<task_type>/vX.Y.Z.json` — semver-tagged,
  immutable once shipped (a change = a NEW version).
- Template JSON: `{"template_id", "version", "schema_id",
  "prompt_text", "response_contract": <strict D-062 subset>,
  "description"}`; `template_hash = sha256(canonical JSON)`.
- Registry invariants (battery-asserted): monotonic semver per task
  (no overwriting or removing a shipped version); strict schema
  validation at load; unknown template id → Class-B refusal by the
  router; hash mismatch between a template and its recorded hash
  fails loudly.
- Engine: `TemplateEngine.render(task_type, version, context)`
  fills `{placeholders}` deterministically and returns
  `(prompt_text, template_id, template_hash)`; tasks embed the ids in
  every `AiRequest` so `AiProposal`/D-065 records carry full
  reproducibility data.

## 6. D-068 — HITL review inbox & bulk orchestrator (`ai_hitl_service.py`)

- `HitlReviewService` composes the existing `ProposalLifecycle` +
  `VerificationQueue` — **no new authority surface** (D-064's verbs
  remain the only decision verbs; the service calls `decide()` with
  an explicit reviewer, always).
- Inbox: deterministic listing of `PROPOSED`/`IN_REVIEW` proposals
  (id, task, template, created stage, current state) from durable
  store data only.
- Single actions: `approve` / `reject` / `edit_approve(modified)`
  — thin, auditable wrappers over the M2 lifecycle semantics.
- Bulk: `bulk_decide(decisions)` processes an explicit list of
  `(proposal_id, action, …)` items; **per-item independence** — each
  item either completes or fails deterministically with its error
  recorded; a failure NEVER aborts the remaining items and NEVER
  leaves a half-applied item; identical re-decisions inside a bulk
  call are `skipped_duplicate` (M2 idempotency, unchanged); a
  conflicting re-decision is refused per item.
- Human edits: `edit_approve` re-validates the modified payload
  through the D-062 contract + divergence guardrails (D-032
  vocabulary / canonical anchoring) BEFORE acceptance; an invalid
  edit is a Class-B refusal with provenance — never silently applied.
- Every decision writes a D-065 `hitl_decision` record and D-026
  provenance with the acting reviewer.

## 7. Milestones (executed in this batch)

- **M1 — Observability & cost ledger (D-065):** collector, strict
  record validation, correlation ride-through, cost report; tests:
  record shape, append-only, aggregation, no-AI-write-path assertion.
- **M2 — Live adapters & sandboxing (D-066):** OpenAI/Anthropic
  adapters with injectable transport, enablement gate, D-052 failure
  mapping, graceful fallback, BUDGET_EXCEEDED_HALT; tests: gate
  closed by default, zero-network-leak (fake transports), fallback
  observability, halt-before-dispatch.
- **M3 — Template engine & prompt ops (D-067):** shipped v1.0.0
  templates for the three Phase 7 task types; registry invariants;
  render determinism; hash pinning; tests: semver monotonicity,
  hash stability, unknown-id refusal, round-trip reproducibility.
- **M4 — HITL workflow & end-to-end integration (D-068):** review
  inbox service, single + bulk decisions, edit divergence guardrail;
  E2E: task → router → proposal (template ids) → observability →
  inbox → human decision → provenance → apply on the live
  PostgreSQL store; tests cover the full ladder including live-DB.

## 8. Security & authority (re-asserted, battery-enforced)

- AI modules remain stdlib + canonical/services only; no
  requests/urllib/http/socket/subprocess; no `os.environ` except in
  the D-066 construction gate (read-only, never logged).
- No decision verb on any new surface except `HitlReviewService`
  (which delegates to the human-only `decide()`).
- No Woo/Notion/media/price import or string reference in any new
  AI module (AST battery-asserted).
- No credentials exist; the adapters cannot phone home without an
  owner-supplied key AND `AI_LIVE_ENABLED=true` (D-045/D-066).
