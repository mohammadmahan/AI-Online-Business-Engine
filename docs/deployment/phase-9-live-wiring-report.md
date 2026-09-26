# Phase 9 Live Wiring Report — Telegram Sales & Ingress Verification (D-159)

**Program:** Live Wiring (Phases 5–18), fifth phase. **Governance:**
D-045 / D-073 / D-074 / D-124 / D-139 / D-154 / D-158 / §17 / §21.7.
**Predecessor:** `phase8.live_wiring_attestation.v1` (D-158, commit
`8655c10`). **Engine:** `local/scripts/live_wiring_phase9_igniter.py` —
TG-01..TG-05, fail-closed, injected adapter/ingress, STRICT
SANDBOX-INGRESS mode (zero outbound dispatch), D-124 deep redaction.

---

## 1. Verdict

| Item | Value |
| --- | --- |
| Attestation schema | `phase9.live_wiring_attestation.v1` |
| Verdict | `PHASE9_IGNITED` (offline battery) |
| Upstream binding | `phase8_digest` = SHA-256 recomputed from the phase8 record's canonical bytes AND matched against its D-112 rooting row (`phase8_live_wiring_attestation`) |
| Manifest binding | the Stage E fingerprint carried unchanged: D-154 → phase5 → phase6 → phase7 → phase8 → phase9 |
| Checks | TG-01 ✓ · TG-02 ✓ · TG-03 ✓ · TG-04 ✓ · TG-05 ✓ (8 rows in the pass path) |
| Outbound dispatches during probe | **0** (structurally refused — the engine never calls a send method, and any adapter send in the log is a SAFETY VIOLATION refusal) |
| Handover | Phase 10 (Multi-channel Order Orchestration) verified per the TG-05 check detail |

Exactly **one** audited attestation per `run()` call — including aborts
(`IGNITION_INCOMPLETE`) — every copy deep-redacted with the public
commitments (`phase8_digest`, `manifest_sha256`) restored after redaction.

## 2. Upstream attestation verification (TG-01)

Same discipline as D-156/D-157/D-158, one level up: the phase8 record must
carry schema `phase8.live_wiring_attestation.v1`, verdict
`PHASE8_IGNITED`, and a hex64 manifest binding; its canonical bytes
recompute to the SHA-256 commitment rooted in the D-112 ledger (kind
`phase8_live_wiring_attestation`) over an intact chain. **Fail-closed
ordering:** any refusal emits the abort attestation with ZERO adapter calls
(proven across four failure classes: absent, malformed, unrooted, broken
chain — the adapter's call log stays empty).

## 3. Runtime profile verification (TG-02)

- Census must carry `runtime_profile_verified: true` with **Phases 5, 6, 7
  AND 8** present+VERIFIED+WIRED (queues/orchestration, Notion state, AI
  runtime, and the content publisher the sales flow builds on).
- Repo-real seams importable and consistent with the D-154 `ENTRY_POINTS`
  registry: `canonical.telegram_ingress` (ENTRY_POINTS[10] — the registry
  governs the phase numbering; this program's task track calls it Phase 9),
  `canonical.telegram_contracts` (D-073 markup/payload contracts),
  `canonical.telegram_adapter` (D-075 adapter + redaction, D-074 pacer),
  and `canonical.telegram_publisher` (D-076 error classification + outbox).

## 4. Security & webhook signature matrix (TG-03)

| Mechanism | Implementation | Verification |
| --- | --- | --- |
| Bot token format | documented `<bot id>:<hash>` shape (`BOT_TOKEN_RE`) | malformed token refuses |
| `getMe` capability | simulated via the injected adapter's capability profile | probe failure (auth carrier) refuses |
| Webhook shared secret | the REAL `verify_webhook_secret_token` (constant-time compare, charset rules) | the run PROVES both directions: a wrong header is refused AND the correct header is accepted — the run only ignites when both hold |
| Rate envelope | the REAL `RatePacer` (D-074: 30 msgs/s global, 1 msg/s per chat) | a 6-op per-chat burst inside 0.5 s is PACED (positive waits), never dropped |
| Message length cap | 4096 chars (`MAX_TEXT_CHARS`) | oversized replies refuse |
| Retry invariants | Class-A transients only, ≤ 2 retries | auth/contract failures never retried |

## 5. Synthetic ingress & sales flow trace (TG-04)

Measured trace (in-process, all REAL canonical layers):

```
START           synthetic update phase9-tg-probe-0001 serialized;
                body/update hashes recorded as commitments
AUTH            REAL webhook path: shared secret verified
                (constant-time), malformed payloads (not-json, empty
                object) fail closed locally, update parsed through
                the REAL parse_update (metadata-minimizing: profile
                names DROPPED, ids+content only)
INGRESS_PARSE   kind=message, has_media=False, text extracted
INTENT_ROUTE    deterministic intent extraction → order_inquiry
                (unknown intent refuses)
INFER           sales reply through the REAL Phase 7 ModelRouter
                (caption_proposal.v1 contract-validated); the mock
                reply is CONSTRUCTED (method/chat-ref-hash/text-hash)
                — never dispatched; length cap enforced
STATE_UPDATE    session state persisted in the namespaced
                SessionStore (Redis-parity seam); a re-set with a
                DIFFERENT value is a state-collision refusal
VERIFY          adapter call log audited — any send* method in the
                log is a SAFETY VIOLATION refusal; dispatched=False
CLEANUP         session store emptied (residue check); mandatory
                even on abort
```

- Full TG-01..TG-05 cycle: **0.67 ms** in-process; adapter calls observed:
  `[]` — zero network surface touched.
- Deterministic summary hash: SHA-256 over the cycle plan
  (`a4daeb7dbab68ddb…` in the recorded run; identical across runs).
- Refusal legs are typed and named: malformed update accepted (contract
  break), unknown intent, session state collision, outbound dispatch
  (SAFETY VIOLATION), cleanup failure, missing router/reply route.

## 6. Latency & throughput guardrails

| Guardrail | Value | Note |
| --- | --- | --- |
| Full TG-01..05 cycle (in-process) | 0.67 ms | engine overhead; hashing-dominated |
| Global send envelope | 30 msgs/s (D-074) | paced, never dropped |
| Per-chat envelope | 1 msg/s (D-074) | burst proven paced in TG-03 |
| Ingress surface | ≤ 128 KB per update (`MAX_UPDATE_BYTES`) | oversized refuses |
| Text cap | 4096 chars | enforced on the constructed reply |
| Retry budget | 2 Class-A retries | auth/contract failures never retried |

Live Bot API latencies are a deployment-time property measured by the same
engine with the real `LiveTelegramAdapter` injected (D-045/D-075 owner
gate: `TELEGRAM_LIVE_ENABLED=true` AND `TELEGRAM_BOT_TOKEN` — no
credential exists, none requested).

## 7. Security posture

- **Token isolation:** the bot token, webhook secret, signing key and
  canaries never appear in attestation, audit copies, or refusal details;
  the canonical adapter's `redact()` strips `bot<token>` URL forms and
  caller-known secrets from every escaping string.
- **PII minimization:** the REAL `parse_update` drops profile metadata
  (names, username, language) at the boundary; chat/user ids appear in
  emitted records only as hashes; message and reply texts appear only as
  hashes.
- **Sandbox-ingress guarantee (structural):** the engine source contains
  no send-method calls; the run audits the adapter log and refuses with
  `SAFETY VIOLATION` if any outbound dispatch was invoked; the session
  store is namespaced (`phase9-session:`), collision-refusing, and
  mandatory-cleaned even on abort.
- **AST-pinned purity:** no socket/http/urllib/requests/asyncio/os/
  subprocess imports, no shell/spawn calls; the adapter and router arrive
  injected (`tg=`, `router=`) with the transport injected inside them
  (D-045/D-073/D-075).
- **No unsolicited delivery:** no broadcast, no webhook hijacking, no
  customer notification — every fixture is a synthetic sandbox id.

## 8. Battery evidence

- New module `local/tests/test_live_wiring_phase9.py`: **46/46**.
- Full regression: **1822/1822 tests across 75 modules, ×2 consecutive
  runs, 0 bad, 0 skipped**, machine-reconciled census (75 unique modules
  both runs). The chain is fully authentic: phase8 attestation built by
  the REAL D-158 igniter → D-157 → D-156 → D-155 → D-154 (real Stage F
  gate, real D-152/D-153 producers), the ingress through the REAL webhook
  path (`verify_webhook_secret_token` + `parse_update` + `TelegramIngress`),
  and the reply through the REAL `ModelRouter` (`caption_proposal.v1`).

## 9. Handover to Phase 10 (Multi-channel Order Orchestration)

Phase 9 leaves the engine with:

- **A verified conversational ingress surface** — webhook-secret-gated,
  deduplicated (D-027 at-least-once), metadata-minimizing, and
  sandbox-only by construction; Phase 10's gate requires the Phase 9
  attestation the same way TG-01 requires Phase 8 (fail-closed
  recursion: Phase N refusal ⇒ no Phase N+1 probes).
- **A proven sales intent loop** — update → parse → intent → AI reply →
  contract validation → session persistence → cleanup, with a
  deterministic summary hash as the artifact commitment; Phase 10's
  multi-channel order orchestration consumes the same intent/session
  seams across channels (the order-intent event the cycle classifies is
  the OMS entry contract).
- **Rate/pacing discipline shared** — the D-074 pacer and 4096-char caps
  are the throughput envelope every later channel phase inherits.
- **Dispatch-ready path, deliberately never taken** — the outbound
  publisher seam (`canonical.telegram_publisher`, D-076 classification +
  dead-letter) is verified importable and consistent with the registry,
  but no message has ever been dispatched; delivery remains behind the
  owner's explicit activation decision.

Phase 10 remains owner-gated: no real order mutation, no live channel
dispatch, no production webhook registration without explicit owner
decisions (D-045/D-139, plan §17/§21.7).
