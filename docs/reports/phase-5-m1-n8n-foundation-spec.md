# Phase 5 — M1 Execution Spec: n8n Foundation

- Generated: 2026-09-14
- Status: **Ready for execution**
- Authority: MASTER_PLAN §13 Phase 5 + **D-059 Approved (Option A)**
- Scope discipline: design/conventions only — no business workflows,
  no credentials, no external connections (D-053 local-first).

---

## 1. Objective

Establish the foundational operating rules and baseline implementation
standards for n8n workflows **before any production-oriented
automation is introduced**, so that every later workflow (product
validation, Woo projection orchestration, Workstream B content
pipeline) inherits the same deterministic, auditable skeleton.

## 2. M1 deliverables

1. Environment and credential-boundary conventions (D-045 references,
   never embedded secrets; `.env.example` extension)
2. Workflow naming and foldering conventions
3. Webhook idempotency contract aligned with D-027
4. Failure classes and retry policy aligned with D-052
5. Logging, redaction, and audit-event minimums (D-045/D-026,
   phase-03-3 §17)
6. GREEN/YELLOW/RED execution tiers mapped from D-050 into n8n
   workflow behavior

## 3. Required repository artifacts

- `docs/standards/n8n-conventions.md`
- `docs/standards/n8n-idempotency-and-retries.md`
- `docs/standards/n8n-logging-and-redaction.md`
- `local/n8n/README.md`

## 4. Acceptance criteria

- No workflow may be considered valid without a naming convention,
  owner, trigger class, and retry policy.
- No webhook workflow may be accepted without an idempotency strategy.
- No credential may be embedded in workflow definitions.
- Logging examples must distinguish redactable vs non-redactable
  fields.
- A trivial local sandbox workflow must be specified for later
  implementation (M2).

## 5. Deferred explicitly (not part of M1)

- social caption generation (Workstream B / Phase 15)
- media publishing adapters (Phase 15 / Phase 9)
- Instagram-specific automation (Phase 9)
- marketing automation orchestration (Phase 15)
- live external platform posting (later phases; gated integrations)

## 6. Decision anchors the standards must cite

| Topic | Anchor |
|---|---|
| Local-first + promotion model | D-053 (change configuration, not business logic) |
| Local stack ports/health | D-054 compose (`engine-local-n8n`, 127.0.0.1:15678) |
| Canonical data access | D-055 PostgreSQL (127.0.0.1:55432) |
| Secrets/credential references | D-045 + Batch 2 extension (register item 8 Open) |
| Identifier vs event idempotency | D-017 / D-027 |
| Failure classes → retry policy | D-052 table |
| Authority tiers | D-050 Green/Yellow/Red (AI never passes the gate) |
| Provenance of automation actions | D-026 |
| Price reads in workflows | D-048 Option A (resolve, never mutate) |
| Media reads | D-049/D-056 (MinIO local, provider-neutral) |
