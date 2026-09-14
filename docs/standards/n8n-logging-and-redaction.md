# n8n Logging, Audit Trails, and Redaction Policy

- Authority: Phase 5 M1 / **D-059 Approved (Option A)**
- Traceability: D-026 (provenance), D-045 (secrets), D-048 (price
  integrity), D-027 (event correlation), phase-03-3 §17 (structured
  logging minimums)

---

## 1. Structured log line (JSON, one event per line)

Every workflow execution that reads, mutates, or computes business
data must emit at minimum:

```json
{
  "schema": "engine.log.v1",
  "workflow_id": "GREEN-CATALOG-MANUAL-CANONICAL_DB_SMOKE",
  "execution_id": "<n8n execution id>",
  "timestamp_utc": "2026-09-14T12:00:00Z",
  "trigger_event": {"source_system": "...", "event_id": "...", "type": "..."},
  "idempotency_key": "sha256:...",
  "actor": "SYSTEM | N8N_CRON | USER:<id>",
  "tier_reached": "GREEN | YELLOW | RED",
  "status": "SUCCESS | FAILED | PENDING_REVIEW",
  "error_class": "A|B|C|D|E or null",
  "entity_refs": [{"type": "product", "id": "P90001"}],
  "provenance_ref": "<D-026 provenance id, when a decision/value was recorded>"
}
```

- `timestamp_utc` is the sole timestamp (ISO-8601, UTC); Jalali
  rendering is a display concern, never a log concern.
- Correlation rule: every log line carries the D-027 `idempotency_key`
  (or the workflow-native event identity) so a business event can be
  traced end-to-end across systems.

## 2. Redaction & privacy mandate

### Strictly redacted (never logged, in any field)

- passwords, authorization headers, bearer/API tokens, webhook signing
  secrets, encryption keys;
- customer PII: phone numbers, personal emails, addresses, payment
  tokens, order personal details;
- full connection strings / URLs with embedded credentials.

Redaction failures are Class C-adjacent incidents: if a secret reached
a log, treat it as a leaked credential (rotate + owner review), not a
cosmetic bug.

### Permitted for tracing (non-redacted)

- canonical business identifiers: Product IDs (`P90001`), Variant IDs,
  SKUs (SKU stays *data* in logs, never a lookup key, per D-046);
- approved vocabulary terms (colors, sizes, families, categories);
- resolved price **tier names** and amounts (`variant_sale → 490000`)
  as computed by D-048 — with the invariant that logs never *become*
  a price source;
- execution timings, node names, error codes, deterministic
  idempotency hashes.

## 3. Where logs live

- Local-first (D-053): structured lines to the container's stdout,
  collected by the Docker logging driver; no external log service in
  this phase (G6 deferred by D-058).
- No workflow may send logs to any external endpoint (that would be an
  external connection — forbidden without its own owner decision).
