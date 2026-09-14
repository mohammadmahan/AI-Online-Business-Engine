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
5. M2 sandbox workflow (`GREEN-OPS-MANUAL-CANONICAL_DB_SMOKE`) is the
   first and only workflow until M2's spec is executed.
