# Local n8n Operations Guide

- Authority: Phase 5 M1 / **D-059 Approved (Option A)**
- Scope: local operations only (D-053). No production n8n, no external
  connections, no credentials in this repository.

## Runtime facts (verified 2026-09-14)

| Item | Value |
|---|---|
| Container | `engine-local-n8n` (compose service `n8n`) |
| Endpoint | `http://127.0.0.1:15678` (localhost-only, D-054) |
| Health | `GET /healthz` → HTTP 200 |
| Network | compose network `infra_default` |
| Persistence | Docker named volume `infra_n8n_data` → `/home/node/.n8n` |
| Timezone | `Asia/Tehran` (`GENERIC_TIMEZONE`) |
| Telemetry | diagnostics/personalization disabled |

Start/stop/reset are handled by the stack tooling
(`docker compose -f local/infra/docker-compose.yml …`).

## Directory layout

- `workflows/` — exported workflow JSON, one file per workflow, named
  exactly as the workflow (`<WORKFLOW_NAME>.json`).
- `templates/` — reusable sub-workflow templates.

## Engineer guidelines

1. **Never edit a workflow in the n8n UI without exporting it to Git
   in the same working session** — an un-exported change is an
   untracked production change.
2. Name workflows strictly per
   `docs/standards/n8n-conventions.md` (`[TIER]-[DOMAIN]-[TRIGGER]-[ACTION]`,
   stating the true highest tier).
3. Validate every workflow against all three standards documents
   before considering it valid:
   - `docs/standards/n8n-conventions.md` (naming, isolation, tiers,
     validity checklist),
   - `docs/standards/n8n-idempotency-and-retries.md` (D-027 webhook
     contract, D-052 retry matrix, dead-letter route),
   - `docs/standards/n8n-logging-and-redaction.md` (log schema,
     redaction mandate).
4. Credentials: reference n8n's credential store only; the store
   itself must be configured from environment variables at setup time
   and is never exported or committed (D-045).
5. Workflows shipped so far (both imported into the local instance,
   both inactive by default):
   - `GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE` — M2 sandbox smoke
     (manual trigger → read-only D-055 query → `engine.log.v1` line).
   - `GREEN-OPS-ERROR-GLOBAL_FAILURE_ROUTER` — M3 global error router
     (Error Trigger → D-052 classification + D-045 redaction →
     `engine.log.v1` failure line). Designate it in **Settings →
     Error workflows** so every failed execution routes through it;
     Class A is retryable, B/C/E dead-letter to the HITL queue,
     D quarantines.
   The taxonomy logic both workflows may rely on lives in the canonical
   module `local/canonical/n8n_failure_taxonomy.js` (CI-executed;
   embedded byte-identically in the router's Code node — the M3 test
   suite enforces the parity).
