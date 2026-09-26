# Phase 6 Live Wiring Report — Notion Workspace Sync Verification (D-156)

**Program:** Live Wiring (Phases 5–18), second phase. **Governance:**
D-139 / D-154 / D-155 / §17 / §21.6. **Predecessor:**
`phase5.live_wiring_attestation.v1` (D-155, commit `f2b6963`).
**Engine:** `local/scripts/live_wiring_phase6_igniter.py` — NOT-01..NOT-05,
fail-closed, injected client transport, zero raw shell, D-124 deep redaction.

---

## 1. Verdict

| Item | Value |
| --- | --- |
| Attestation schema | `phase6.live_wiring_attestation.v1` |
| Verdict | `PHASE6_IGNITED` (offline battery) |
| Upstream binding | `phase5_digest` = the D-155 attestation's SHA-256, recomputed from the record's canonical bytes AND matched against its D-112 rooting row (`phase5_live_wiring_attestation`) |
| Manifest binding | the Stage E fingerprint carried unchanged: D-154 certificate → phase5 attestation → phase6 attestation |
| Checks | NOT-01 ✓ · NOT-02 ✓ · NOT-03 ✓ · NOT-04 ✓ · NOT-05 ✓ (13 rows in the pass path) |
| Handover | Phase 7 (AI Runtime & Product Manager wiring) verified per the NOT-05 check detail |

Exactly **one** audited attestation is emitted per `run()` call — including
aborts (`IGNITION_INCOMPLETE`) — every copy deep-redacted with the public
commitments (`phase5_digest`, `manifest_sha256`) restored after redaction
(D-146/D-153/D-154/D-155 precedent).

## 2. NOT rule results

### NOT-01 — Phase 5 attestation gate (fail-closed ordering)
- Schema `phase5.live_wiring_attestation.v1`, verdict `PHASE5_IGNITED`.
- **Digest verification:** the attestation record's canonical bytes recompute
  to the SHA-256 commitment rooted in the D-112 ledger — a mismatch (drifted
  or altered upstream attestation) refuses by name before any Notion call.
- Manifest fingerprint binding verified (hex64); D-112 chain integrity
  verified (zero breaks). A refusal here emits the abort attestation with
  **zero** transport requests executed.

### NOT-02 — live Notion authentication & rate-limit guardrails
- Authentication exercises the **real canonical client layer**
  (`canonical/notion_live.py`): a `GET /users/me` through the injected
  transport; non-200 responses classify through the real
  `classify_notion_error` (401/403 → Class-E `NotionAuthError` → immediate
  refusal; 5xx → Class-A transient; timeouts → typed failure). The
  integration token never leaves the client; every escaping error string
  passes `redact_notion`.
- **Token-bucket compliance:** a 12-request burst inside ~1.1 s (well over
  the 3/s `NOTION_RATE_LIMIT_PER_SEC` bucket) is PACED, never dropped —
  measured waits `[0, 0, 0, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.1, 0.1]`
  seconds through the real `NotionPacer` (deterministic synthetic ticks).

### NOT-03 — canonical database schema conformance
The four canonical workspace databases, verified for property names +
types + select options + relation integrity:

| Database key | Notion title | Mandatory properties |
| --- | --- | --- |
| `marketing_campaigns` | Marketing Campaigns | Name(title), Channel(select: instagram/telegram/email/organic), Budget(number), Status(select) |
| `order_pipeline` | Order Pipeline | Name(title), OrderRef(rich_text), Amount(number), Stage(select: new/paid/shipped/refunded), Product(**relation**) |
| `product_catalog` | Product Catalog | Name(title), SKU(rich_text), Price(number), Status(select: draft/active/retired) |
| `tasks_sops` | Tasks/SOPs | Name(title), Kind(select: task/sop/checklist), Owner(people), DueDate(date), Campaign(**relation**) |

- A missing mandatory property, a corrupted property type (e.g.
  `Price:rich_text != number`), a missing select option, or an unbound
  relation each refuse with the offending database and property named.
- Relation integrity: every declared relation must carry a target workspace
  object id (`relations_resolved` counted in the attestation).

### NOT-04 — non-destructive synthetic probe (write → read → cleanup)
- The probe payload is **fixed** (`Name=phase6-sync-probe`,
  `SKU=phase6-probe-0001`, `Status=draft`), so its D-027-style idempotency
  key (SHA-256 over the payload's canonical bytes) is deterministic across
  runs and replays.
- Cycle: **create** probe page in `product_catalog` → **replay** create with
  the same idempotency key (MUST return the SAME page — a distinct page is
  an idempotency collision and fails the run) → **read back** (SKU match) →
  **archive** (workspace left clean). Per-step telemetry names the failing
  leg (WRITE/REPLAY/READ/CLEANUP) in refusal details.
- This is the engine's ONLY write path, and it is provably non-destructive:
  the probe page is archived inside the same run.

### NOT-05 — canonical emission
- `Phase6Attestation` is a frozen dataclass; `attestation_digest` = SHA-256
  over canonical JSON (the shared project formula). Deterministic for
  identical inputs; exactly one record per run.

## 3. Verification topology

```
igniter (pure core: clock + audit_sink + providers only)
 ├─ NOT-01  phase5 attestation → digest recompute ↔ D-112 rooting row
 │          (kind phase5_live_wiring_attestation) + chain integrity
 ├─ NOT-02  injected Notion client (LiveNotionClient-compatible)
 │            └─ transport(request{method,url,headers,json})
 │               → response{status_code,body,retry_after}
 │            └─ real NotionPacer token bucket (3/s, paced not dropped)
 │            └─ real classify_notion_error (D-052 classes)
 ├─ NOT-03  4× GET /databases/{id} → schema conformance (types, options,
 │          relations) against the declared WorkspaceSchema
 └─ NOT-04  POST /pages (idempotency-keyed) → GET /blocks/{id}/children
            → PATCH /pages/{id} (archive) — write→read→cleanup
audit_sink → exactly one deep-redacted D-112 record per run
```

Purity envelope (AST-audited in the battery): the igniter core has no
network imports, no `os`/`subprocess`, no shell/spawn calls, and never
constructs a transport itself — the client arrives injected (`notion=`),
with the live HTTPS transport injected *inside* it (D-045/D-075). The
canonical `notion_live` layer is itself wall-clock-free (synthetic pacer
ticks in tests).

## 4. Sync latency metrics

| Metric | Measured | Note |
| --- | --- | --- |
| Full NOT-01..NOT-05 cycle (in-process transport, 8 API ops incl. paced burst) | **0.56 ms** | engine overhead only; dominated by canonical JSON hashing |
| Paced burst schedule (12 ops @ 3/s bucket) | first 3 immediate, then 0.7→0.1 s waits | pacing, never dropping — the D-074/D-126 discipline |
| Probe idempotency | replay returns the SAME page id | D-027 key adherence proven, collision refused |

Live-API latencies (network round-trips to `api.notion.com`) are a
deployment-time property measured by the same engine with the real
transport injected; the engine records per-op evidence only as
commitments (counts, keys, verdicts), never payloads.

## 5. Security posture

- **Token isolation:** the Notion integration token lives inside the
  injected client only; the engine never sees it (the battery proves the
  attestation, audit copies, AND the transport request log are
  token-free — the client redacts `Authorization` material from every
  escaping string via `redact_notion`).
- **D-124 deep redaction** over every emitted record, with public
  commitments (`phase5_digest`, `manifest_sha256`) restored for chain
  correlation; refusal details carry only exception TYPE names (never
  raw server bodies).
- **Database IDs** are workspace references, not secrets, but they are
  never logged by the engine — only the four canonical keys appear.
- **Fail-closed:** missing/tampered phase5 attestation, transport timeout,
  401/403, schema mismatch, probe failure, idempotency collision — each
  aborts the run with zero side-effects and one abort record.

## 6. Battery evidence

- New module `local/tests/test_live_wiring_phase6.py`: **42/42**.
- Full regression: **1686/1686 tests across 72 modules, ×2 consecutive
  runs, 0 bad, 0 skipped**, machine-reconciled census (72 unique modules
  both runs). The battery builds the phase5 attestation through the REAL
  D-155 igniter over the authentic Stage C→H chain (real D-152 closure,
  real Stage F gate, real D-153 executor, real D-154 synthesizer) and
  drives the REAL canonical Notion contract layer over an in-process
  transport.

## 7. Handover to Phase 7 (AI Runtime & Product Manager wiring)

Phase 6 leaves the engine with:

- **Workspace OS verified** — four conformant databases with typed
  properties, select vocabularies, and resolved relations; downstream
  phases write/read through the SAME `WorkspaceSchema` contract, so a
  schema drift anywhere is caught by the phase's NOT-03 gate before
  wiring proceeds.
- **Idempotent sync writes** — the probe's idempotency-key pattern
  (SHA-256 over canonical payload bytes, same-key⇒same-page) is the
  template for every later phase's external write (AI dispatch records,
  channel publishing, order mirrors).
- **Paced API access** — the 3/s token bucket plus deterministic backoff
  plans (`backoff_plan`) are the shared rate discipline for all Notion
  consumers (Phase 7 PM writes, Phase 15 campaign logs).
- **Governance chain extended** — D-156's attestation roots in the D-155
  attestation and the D-112 ledger; Phase 7's gate requires the Phase 6
  attestation the same way NOT-01 requires Phase 5 (fail-closed
  recursion: Phase N refusal ⇒ no Phase N+1 probes).

Ignition order for Phases 7–18 is unchanged from the completion report's
transition guide; each phase adds one igniter module, one battery module,
and one governance row, exactly as Phases 5 and 6 did.
