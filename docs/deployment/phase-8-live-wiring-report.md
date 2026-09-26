# Phase 8 Live Wiring Report — Instagram Graph API Verification (D-158)

**Program:** Live Wiring (Phases 5–18), fourth phase. **Governance:**
D-045 / D-124 / D-139 / D-154 / D-157 / §17 / §21.6. **Predecessor:**
`phase7.live_wiring_attestation.v1` (D-157, commit `2167f19`).
**Engine:** `local/scripts/live_wiring_phase8_igniter.py` — IG-01..IG-05,
fail-closed, injected adapter, STRICT probe-only mode (zero public
publishing), D-124 deep redaction.

---

## 1. Verdict

| Item | Value |
| --- | --- |
| Attestation schema | `phase8.live_wiring_attestation.v1` |
| Verdict | `PHASE8_IGNITED` (offline battery) |
| Upstream binding | `phase7_digest` = SHA-256 recomputed from the phase7 record's canonical bytes AND matched against its D-112 rooting row (`phase7_live_wiring_attestation`) |
| Manifest binding | the Stage E fingerprint carried unchanged: D-154 → phase5 → phase6 → phase7 → phase8 |
| Checks | IG-01 ✓ · IG-02 ✓ · IG-03 ✓ · IG-04 ✓ · IG-05 ✓ (8 rows in the pass path) |
| Publish calls during probe | **0** (structurally refused — the engine never calls `publish_container`, and any adapter-invoked publish is a SAFETY VIOLATION refusal) |
| Handover | Phase 9 (Telegram Sales & Ingress wiring) verified per the IG-05 check detail |

Exactly **one** audited attestation per `run()` call — including aborts
(`IGNITION_INCOMPLETE`) — every copy deep-redacted with the public
commitments (`phase7_digest`, `manifest_sha256`) restored after redaction.

## 2. Upstream attestation verification (IG-01)

Same discipline as D-156/D-157, one level up: the phase7 record must carry
schema `phase7.live_wiring_attestation.v1`, verdict `PHASE7_IGNITED`, and a
hex64 manifest binding; its canonical bytes recompute to the SHA-256
commitment rooted in the D-112 ledger (kind `phase7_live_wiring_attestation`)
over an intact chain. **Fail-closed ordering:** any refusal emits the abort
attestation with ZERO adapter calls (proven across four failure classes:
absent, malformed, unrooted, broken chain — the adapter's call log stays
empty).

## 3. Runtime profile verification (IG-02)

- Census must carry `runtime_profile_verified: true` with **Phases 5, 6 AND
  7** present+VERIFIED+WIRED (data/queue/orchestration, Notion OS, and the
  AI runtime the caption comes from).
- Repo-real seams importable and consistent with the D-154 `ENTRY_POINTS`
  registry: `canonical.instagram_adapter` (D-069 workflow + D-071 redaction),
  `canonical.instagram_contracts` (local Class-B validation),
  `canonical.instagram_publisher` (D-070 idempotency vault + outbox),
  `canonical.instagram_live` (D-072 Graph error/usage classification), and
  `publishing.instagram` (ENTRY_POINTS[9] — the registry governs the phase
  numbering; this program's task track calls it Phase 8).

## 4. Permission/scope matrix (IG-03)

| Scope | Purpose | Status in probe |
| --- | --- | --- |
| `instagram_basic` | account/media metadata reads | required, verified present |
| `instagram_content_publish` | container creation (the probe-only workflow) | required, verified present |
| `pages_show_list` | Page↔IG account linkage | required, verified present |

Additional capability gates:

- **Token validity + margin:** `token_valid_until` must exceed the injected
  clock by ≥ `EXPIRY_THRESHOLD_TICKS` (300) — an expired or fresh-expiring
  token refuses (expired / margin refusals tested).
- **Auth errors:** any capability-probe exception classifies as a permission
  failure (401/403 carrier → immediate refusal; no retries).
- **Graph usage envelope:** the documented `X-App-Usage` shape
  (`call_count`/`total_time`/`total_cputime`) feeds the real
  `GraphUsageTracker`; usage at/over the 75% warn level (headroom ≤ 25%)
  refuses. Measured in the pass path: **headroom 95.0%**.
- **Retry invariants:** Class-A transients only (timeouts), ≤ 2 retries;
  contract/auth failures refuse immediately (never retried).

## 5. Synthetic container probe trace (IG-04)

Measured trace (in-process `MockInstagramAdapter`, the real D-069 workflow):

```
START             caption produced by the REAL Phase 7 ModelRouter
                  (generate_caption → caption_proposal.v1 contract
                  validated); caption + media hashes recorded as
                  commitments
AUTH              local Class-B prevention through the REAL
                  validate_publish_payload (aspect_ratio 4:5 ∈
                  {1:1, 4:5, 16:9}, caption length, ≤30 hashtags,
                  media_hash ≥ 8 chars) — an invalid payload can
                  NEVER reach the network
CONTAINER_CREATE  mock container created (status IN_PROGRESS);
                  Class-A create-timeout retries ≤ 2 then refusal
STATUS_POLL       real bounded poll_until_ready: IN_PROGRESS →
                  FINISHED (max 10 polls; ERROR/EXPIRED terminal)
VERIFY            publish-call audit: adapter call log checked —
                  any publish invocation = SAFETY VIOLATION refusal;
                  probe state-collision check (a container id
                  already used by an earlier probe refuses)
CLEANUP           probe container archived via the probe-only seam;
                  the workspace is left exactly as found
```

- Full IG-01..IG-05 cycle: **2.15 ms** in-process; adapter calls observed:
  `['create', 'status', 'archive']` — no `publish`.
- Deterministic summary hash: SHA-256 over the probe plan
  (`9f8501637be9466a…` in the recorded run; digest deterministic across
  identical runs).
- Refusal legs are typed and named: media format non-compliance, container
  create failure (Class-B), timeout with retry overflow, terminal container
  state, probe state collision, publish invocation (SAFETY VIOLATION),
  cleanup failure, missing router.

## 6. Latency & rate-limit benchmarks

| Metric | Value | Note |
| --- | --- | --- |
| Full IG-01..05 cycle (in-process) | 2.15 ms | engine overhead; hashing-dominated |
| Adapter ops per probe | 3 (create, status, archive) | far under any rate envelope |
| Graph usage headroom (probe fixture) | 95.0% | warn level 75% — refusal above |
| Container poll budget | 10 polls max (real `poll_until_ready`) | bounded, no infinite loop |
| Retry budget | 2 Class-A retries | auth/contract failures never retried |

Live Graph API latencies are a deployment-time property measured by the
same engine with the real `GraphApiAdapter` injected (D-045/D-071 owner
gate: `INSTAGRAM_LIVE_ENABLED=true` AND env keys — none exist, none
requested); the engine records per-op evidence only as commitments.

## 7. Security posture

- **Token isolation:** access tokens (`IGQV…`/`EAAG…` markers), client
  secrets and auth headers never enter attestation, audit copies, or
  refusal details — the canonical adapter layer's `redact()` strips token
  material from every escaping string, and D-124 deep redaction runs over
  every emitted record with public commitments restored.
- **Data minimization:** captions appear only as hashes; container ids only
  as hashes; no page ids, media URLs, or raw API responses in any record.
- **Probe-only guarantee (structural):** the engine source never calls
  `publish_container`; the run audits the adapter call log and refuses with
  `SAFETY VIOLATION` if any publish was invoked; the archive seam is the
  only cleanup surface.
- **AST-pinned purity:** no socket/http/urllib/requests/asyncio/os/
  subprocess imports, no shell/spawn calls; the adapter and router arrive
  injected (`ig=`, `router=`) with the transport injected inside them
  (D-045/D-075).

## 8. Battery evidence

- New module `local/tests/test_live_wiring_phase8.py`: **45/45**.
- Full regression: **1776/1776 tests across 74 modules, ×2 consecutive
  runs, 0 bad, 0 skipped**, machine-reconciled census (74 unique modules
  both runs). The chain is fully authentic: phase7 attestation built by
  the REAL D-157 igniter → D-156 → D-155 → D-154 (real Stage F gate, real
  D-152/D-153 producers), the caption through the REAL `ModelRouter`
  (`generate_caption` → `caption_proposal.v1`), and the container workflow
  through the REAL `MockInstagramAdapter` + `poll_until_ready` +
  `validate_publish_payload`.

## 9. Handover to Phase 9 (Telegram Sales & Ingress wiring)

Phase 8 leaves the engine with:

- **A verified Instagram surface** — capability-profiled, scope-checked,
  rate-envelope-guarded, and probe-only by construction; Phase 9's gate
  requires the Phase 8 attestation the same way IG-01 requires Phase 7
  (fail-closed recursion: Phase N refusal ⇒ no Phase N+1 probes).
- **The publish-ready path, deliberately never taken** — container create →
  poll → FINISHED is proven; the D-070 idempotency vault and outbox
  publisher (`canonical.instagram_publisher`) sit behind the owner's
  explicit activation decision. No public feed mutation has ever been
  made by this program.
- **Cross-channel template** — the probe pattern (capability profile →
  local Class-B validation → synthetic resource with bounded polling →
  publish-audit → archive) is the template for Telegram wiring next
  (`canonical.telegram_ingress`, ENTRY_POINTS[10]).
- **Content pipeline closed loop** — Phase 7's AI runtime now feeds
  Phase 8's media workflow (caption_proposal.v1 → validate_publish_payload),
  so content flows AI → contract → channel-probe without ever bypassing a
  contract or an owner gate.

Phase 9 remains owner-gated: no real Telegram credentials, no live
ingress, no publishing without explicit owner decisions (D-045/D-139,
plan §17/§21.6).
