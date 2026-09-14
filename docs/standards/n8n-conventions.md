# n8n Workflow Conventions & Standards

- Authority: Phase 5 M1 / **D-059 Approved (Option A)**
- Traceability: D-045 (credential references), D-050 (authority tiers),
  D-052 (failure classes), D-053 (local-first isolation), D-017/D-027
  (idempotency), D-026 (provenance)
- Scope: conventions only. No business workflow is valid until it
  satisfies every acceptance criterion here and in the sibling
  standards documents.

---

## 1. Workflow naming convention

Canonical format (all uppercase segments, underscore-separated):

```
[TIER]-[DOMAIN]-[TRIGGER]-[ACTION_DESCRIPTION]
```

- `TIER` ∈ `GREEN | YELLOW | RED` — the D-050 tier this workflow can
  ever reach (a workflow containing any RED node is a RED workflow).
- `DOMAIN` ∈ `CATALOG | MEDIA | PUBLISH | INTEGRATION | OPS` (extensible
  only by owner decision).
- `TRIGGER` ∈ `CRON | WEBHOOK | MANUAL | QUEUE`.

Examples:

- `GREEN-CATALOG-MANUAL-CANONICAL_DB_SMOKE`
- `YELLOW-MEDIA-WEBHOOK-GENERATE_IMAGE_DERIVATIVES`
- `RED-PUBLISH-WEBHOOK-DISPATCH_SOCIAL_POST`

A workflow's name must state its **highest** reachable tier; a GREEN
name on a workflow that can write is a violation, not a formality.

## 2. Directory & storage strategy

- Raw workflow export JSON files: `local/n8n/workflows/` — one file per
  workflow, named exactly as the workflow (`<WORKFLOW_NAME>.json`).
- Reusable sub-workflow templates: `local/n8n/templates/`.
- Every workflow edited in the local n8n UI must be exported to Git in
  the same working session; an un-exported change is an untracked
  production change (RULES §22 discipline applied to automations).

## 3. Credential & environment isolation (D-045 / D-053)

- **No credentials, passwords, tokens, or API keys may ever appear in
  workflow JSON nodes.** Not hard-coded, not in expressions, not in
  query strings, not in "temp" nodes.
- Credentials are referenced through n8n's internal credential store
  (which itself must reference environment variables at setup time) —
  the repository contains only the workflow JSON, never the store.
- Workflows that can produce external side effects must check
  `$env.APP_ENV` and **refuse execution** unless the environment is
  explicitly authorized for that tier (RED workflows hard-refuse in
  anything but an explicitly authorized environment).
- Never put credentials in docs, Excel, AI prompts, or logs (D-045).

## 4. D-050 authority tiers mapped to n8n behavior

- **GREEN — automated, non-destructive:** read-only SELECTs, metric
  aggregation, internal cache/log updates. Requires no human gate but
  must stay read-only *by construction* (no write-capable nodes).
- **YELLOW — automated with guardrails:** image processing, draft
  generation, normalization. Every YELLOW workflow must assert its
  invariants before any write (validation node(s) whose failure routes
  to the failure path, never to a silent write).
- **RED — destructive / public / financial:** social posting, price
  changes, inventory writes, publication. **Strictly forbidden from
  autonomous execution**: the workflow must verify an explicit HITL
  approval marker (approved deterministic flow or human gate) before
  the RED node, and must abort without one. AI-proposed actions enter
  only as proposals; the approval is human (D-050: AI never passes
  the gate).

## 5. Workflow validity checklist (applies to every workflow)

1. Name matches the convention and states the true highest tier.
2. Owner recorded in workflow settings (who answers for it).
3. Trigger class explicit; webhook triggers follow the sibling
   idempotency contract.
4. Retry policy declared per node family (sibling document).
5. No embedded secrets (grep-checked in review).
6. `$env.APP_ENV` guard present where any tier > GREEN node exists.
7. Execution logging per the sibling logging standard.
