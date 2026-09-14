# Phase 5 Kickoff & Roadmap

- Initiated: 2026-09-14
- Lead architecture: Freebuff agent & Owner (Mohammad)
- Strategy: **local-first** (D-053) — everything below runs on the
  local stack (D-054), no external connections, no credentials.
- Governance: this roadmap **proposes**; only the owner's explicit
  instruction approves (PROJECT_RULES §4). Each milestone's decision
  record gets its own D-number at approval time.

---

## 0. Naming reconciliation (important)

MASTER_PLAN §13 is authoritative: **Phase 5 = n8n Foundation**
("Credentials, webhooks, workflow conventions, errors, retries,
idempotency, logging, environments").

The kickoff instruction titled Phase 5 "Content Creation & Posting
Automation Platform". That workstream is real but is **not** the plan's
Phase 5: it spans Phase 15 (Marketing Automation: content planning,
content generation, campaigns) and Phase 9 surfaces (Instagram), and it
**depends on the n8n foundation existing first**. It is recorded here as
**Workstream B (PROPOSED)** — the owner's naming/sequencing decision is
requested via **D-059 (Proposed)** in DECISIONS.md.

## 1. Phase objective (per MASTER_PLAN §13, Phase 5)

Establish the n8n foundation **without building business workflows
yet**: environment conventions, credential-reference structure
(no real secrets), webhook conventions, error/retry/idempotency
standards, logging standards, and the local↔future-staging promotion
story for automations.

Local readiness verified at kickoff: `engine-local-n8n` healthy,
`/healthz` → HTTP 200 (127.0.0.1:15678); canonical PostgreSQL healthy
(127.0.0.1:55432); MinIO healthy (19000). The runtime pieces Phase 5
orchestrates already exist locally.

## 2. Core pillars

1. **Environment & credential conventions (no secrets):** the local n8n
   instance's data flow uses D-045/D-051-style credential *references*;
   `.env.example` extended with n8n vars; secrets never in Git, docs,
   prompts, or workflows. Concrete secret tooling stays Open (register
   item 8).
2. **Workflow conventions:** naming, folders/projects, versioning,
   single-responsibility workflows, deterministic re-runs; **the
   D-050 Green/Yellow/Red authority matrix maps onto n8n execution**
   (a workflow node may never execute a Red operation without the
   approved human gate).
3. **Webhook & trigger conventions:** deterministic event identity
   (D-027 keys carried in headers/payloads), dedupe at the boundary,
   idempotent handlers; local-only webhook exposure (127.0.0.1).
4. **Error, retry & idempotency standards:** the D-052 failure-class
   table becomes n8n retry policy; dead-letter flow; human-review
   escalation into the existing HITL verification queue (D-026).
5. **Logging & observability standards:** structured JSON events with
   correlation/event IDs (phase-03-3 §17), redaction rules (D-045).

## 3. Milestones (design-first, per project discipline)

- [ ] **M1 — n8n operating conventions doc** (`docs/phases/
      phase-05-n8n-foundation.md`): pillars 1–5 above as concrete,
      testable conventions. Design only; owner reviews.
- [ ] **M2 — Local n8n smoke:** create one trivial sandbox workflow
      (manual trigger → read-only SELECT against canonical DB → log),
      proving credential-reference usage, D-027 event IDs in execution
      metadata, and logging conventions. GREEN-tier (read-only).
- [ ] **M3 — Failure-injection conventions:** simulated timeout/duplicate
      delivery/dead-letter against the sandbox workflow; verify the
      retry/idempotency standards hold in practice.
- [ ] **M4 — Foundation gate review:** owner reviews conventions +
      smoke evidence; Phase 5 formally closed; business workflows
      (first: product-validation and Woo-projection orchestration)
      unblocked for the next phase.

Explicitly **out of scope for Phase 5**: real credentials, real webhooks
beyond localhost, production n8n deployment, Instagram/payment/shipping
integrations, AI runtime.

## 4. Workstream B (PROPOSED — D-059): content creation & posting automation

The instruction's "Phase 5" content platform, correctly placed in the
plan's sequence: **after** Phase 5 (n8n foundation) and logically
aligned with Phase 15 (Marketing Automation) + Phase 9 (Instagram).

Proposed pillars (as instructed, recorded verbatim in intent):
1. **Canonical Content Engine (CCE):** template-driven generator for
   titles, captions, pricing badges, hashtags — consuming canonical
   PostgreSQL data only (prices via D-048 resolution; never AI-invented).
2. **Media Asset Pipeline (MAP):** processing MinIO assets for social
   formats (aspect ratios, compression, watermarking) behind the
   D-049/D-056 abstraction.
3. **Orchestration (n8n):** triggers, scheduled queueing, retries —
   built on the Phase 5 conventions.
4. **Publishing adapters:** Telegram Bot API, Instagram Graph API /
   webhook bridges, WordPress REST API — each a Phase 9/15 gated
   integration (credentials + approval flows; nothing autonomous).
5. **Audit & analytics feedback:** published-post IDs, status, errors —
   D-026 provenance + D-027 event idempotency from day one.

Proposed milestones: M1 content schema/DTOs in the canonical package ·
M2 template engine (human-approved templates) · M3 n8n integration with
local Postgres/MinIO · M4 end-to-end local dry-run publishing.

**AI authority carries over unchanged:** AI may draft/enrich/propose
content; it may never publish autonomously, invent prices/stock,
or execute Red-tier operations without the approved human gate.

## 5. Sequencing decision requested (D-059, Proposed)

- **Option A (recommended):** execute the plan's Phase 5 (n8n
  foundation, M1–M4 above) first; Workstream B starts immediately
  after, as Phase 15's opening batch. Respects dependencies; no
  MASTER_PLAN rewrite needed.
- **Option B:** run Workstream B content-engine work (M1–M2 only:
  schema + templates, no orchestration) in parallel with Phase 5,
  deferring its n8n/adapter parts to Phase 15.
- **Option C:** renumber the plan around the content platform —
  requires a formal MASTER_PLAN §13 amendment decision; not recommended.
