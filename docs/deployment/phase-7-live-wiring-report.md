# Phase 7 Live Wiring Report — AI Runtime & Product Manager Verification (D-157)

**Program:** Live Wiring (Phases 5–18), third phase. **Governance:**
D-139 / D-154 / D-155 / D-156 / §17 / §21.6. **Predecessor:**
`phase6.live_wiring_attestation.v1` (D-156, commit `50e5855`).
**Engine:** `local/scripts/live_wiring_phase7_igniter.py` — AIR-01..AIR-05,
fail-closed, injected router/Notion/census providers, zero raw shell,
D-124 deep redaction, strict data minimization.

---

## 1. Verdict

| Item | Value |
| --- | --- |
| Attestation schema | `phase7.live_wiring_attestation.v1` |
| Verdict | `PHASE7_IGNITED` (offline battery) |
| Upstream binding | `phase6_digest` = SHA-256 recomputed from the phase6 record's canonical bytes AND matched against its D-112 rooting row (`phase6_live_wiring_attestation`) |
| Manifest binding | the Stage E fingerprint carried unchanged: D-154 → phase5 → phase6 → phase7 |
| Checks | AIR-01 ✓ · AIR-02 ✓ · AIR-03 ✓ · AIR-04 ✓ · AIR-05 ✓ (7 rows in the pass path) |
| Handover | Phase 8 (Instagram wiring) verified per the AIR-05 check detail |

Exactly **one** audited attestation per `run()` call — including aborts
(`IGNITION_INCOMPLETE`) — every copy deep-redacted with the public
commitments (`phase6_digest`, `manifest_sha256`) restored after redaction.

## 2. Upstream attestation verification method (AIR-01)

Identical discipline to D-156's NOT-01, applied one level up the chain:

1. the phase6 record must carry schema `phase6.live_wiring_attestation.v1`,
   verdict `PHASE6_IGNITED`, and a hex64 `manifest_sha256` binding;
2. the record's **canonical bytes** (`sort_keys`, `,`/`:` separators) are
   hashed with the shared project formula;
3. the digest must equal the commitment in the D-112 ledger row of kind
   `phase6_live_wiring_attestation` — a mismatch refuses as
   **DRIFTED/altered upstream attestation**;
4. the D-112 chain verifier must report zero breaks.

**Fail-closed ordering:** `run()` evaluates AIR-01 first; any refusal emits
the abort attestation and returns — the router and the Notion probe client
are never touched (proven by `test_17_refusal_makes_zero_provider_calls`
across four failure classes: absent, malformed, unrooted, broken chain —
zero `MockAiProvider` calls, zero probe requests).

## 3. Runtime profile verification (AIR-02)

- The injected census must carry `runtime_profile_verified: true` (the
  D-154 certificate's verified profile is the only wiring baseline) and
  Phase 5 + Phase 6 rows marked present+**VERIFIED**+**WIRED**; any missing
  or unwired prerequisite refuses.
- **Repo-real seams** (not MASTER_PLAN-only names) must be importable and
  consistent with the D-154 `ENTRY_POINTS` registry:
  `canonical.ai_runtime` (ENTRY_POINTS[7]), `canonical.ai_contracts`,
  `canonical.vocab` (owner-approved vocabulary), and
  `canonical.ai_proposal_lifecycle` (ENTRY_POINTS[8], the Phase 8 PM
  lifecycle). A registry-vs-repo mismatch refuses as **registry drift**.

## 4. Provider routing constraints (AIR-03)

| Constraint | Enforcement |
| --- | --- |
| Determinism | the task's route target is resolved twice; diverging provider/model ⇒ refusal (same inputs ⇒ same route) |
| Provider/model allowlist | `{mock: (mock-1,)}` by default; unknown provider or model ⇒ refusal (a `deepseek`-routed policy refuses) |
| Token cap | route `max_tokens` ≤ 2048 |
| Budget cap | route `budget_usd` ≤ $1.00 per cycle; the real `ModelRouter` additionally enforces per-task `BudgetExceeded` at dispatch |
| Tool calls | ≤ 4 per cycle through the counted `_dispatch_tool` seam |
| Retries | ≤ 2, **Class-A transients only**; auth/contract failures refuse immediately (no retry) |
| Timeout | 15 s per provider operation (D-151) |

## 5. Synthetic PM cycle trace (AIR-04)

Fixed fixture (`phase7-pm-brief-0001`): product کت و جلیقه, color مشکی,
market context پاییز. The measured trace (in-process transport):

```
START    brief normalized → brief_hash 8f4b…-class commitment
VOCAB    category leaf verified against CATEGORY_PAIRS;
         color مشکی → owner-approved SKU code BK (D-032, O/I/L-safe)
ROUTE    ModelRouter: propose_content_idea → mock/mock-1 (attempt 1)
INFER    45 tokens in / 49 tokens out, cost $0.00, latency 1 ms
VALIDATE real ai_contracts contract content_idea_proposal.v1 → valid
         (target_lifecycle_state constrained to "Backlog" — AI may
         only PROPOSE at the lifecycle root, D-060)
PACK     content plan skeleton → summary_hash c4cd60975127e8d9…;
         artifact stored at phase7-scratch:plan-0001 ONLY
CLEANUP  scratch deleted; residue check empty
NOTION   strictly probe-only: create (idempotency-keyed) → replay
         (SAME page) → read-back → archive — 3 requests, all minimal
```

- Full AIR-01..AIR-05 cycle: **3.51 ms** in-process (engine overhead
  dominated by canonical JSON hashing — the deterministic summary hash is
  `SHA-256` over the packaged plan).
- The ONLY write surfaces: the namespace-scoped `ScratchStore` (keys
  outside `phase7-scratch:` refuse) and the optional probe-only Notion
  client (create/replay/read/archive, page always archived inside the run).
- Failure legs are typed and named: unsafe tool request, scratch scope
  violation, provider dispatch failure with retry overflow, budget
  guardrail refusal, invalid output schema, probe collision, missing
  cleanup — every abort still cleans the scratch store (fail-closed
  hygiene) and emits one abort record.

## 6. Latency & cost guardrails

| Guardrail | Value | Evidence |
| --- | --- | --- |
| Cycle cost | **$0.00** (mock tariff; real providers are owner-gated additions per D-129) | INFER telemetry |
| Cycle tokens | 94 total (45 in / 49 out), far under the 2048 cap | INFER telemetry |
| Tool calls | 4 of 4 (write/read/delete + notion probe) | counted seam |
| Cycle wall time | 3.51 ms in-process | measured |
| Per-task budget | $0.50 route cap under the $1.00 cycle cap | `ModelRouter.budgets` |

The D-127 budget envelope stays authoritative: the router's spend tracking
is always active (not ledger-gated), so repeated ignition runs cannot
accumulate hidden spend.

## 7. Security posture

- **Prompt/response isolation:** prompts, tool inputs and provider
  fragments never enter any emitted record — only hashes, counts, route
  names and step verdicts (proven: the market-context fixture and cycle id
  appear nowhere in attestation or audit copies).
- **Token isolation:** provider tokens, Notion tokens, the signing key and
  canaries never appear in attestation, audit copies, or refusal details;
  the Notion probe requests carry op-names only (create/read/archive).
- **D-124 deep redaction** over every emitted record with public
  commitments restored.
- **AST-pinned purity:** no socket/http/urllib/requests/asyncio/os/
  subprocess imports, no shell/spawn calls; router and Notion arrive
  injected (`router=`, `notion=`); the scratch store is the only general
  write surface and enforces its namespace.
- **Owner-gated escalation:** real AI providers (D-045 credential gate),
  real workspace writes, and any lifecycle promotion remain owner
  decisions — the cycle PROPOSES to `Backlog`, nothing else.

## 8. Battery evidence

- New module `local/tests/test_live_wiring_phase7.py`: **45/45**.
- Full regression: **1731/1731 tests across 73 modules, ×2 consecutive
  runs, 0 bad, 0 skipped**, machine-reconciled census (73 unique modules
  both runs). The chain is fully authentic: phase6 attestation built by
  the REAL D-156 igniter → over the REAL D-155 igniter → over the REAL
  D-154 synthesizer (real Stage F gate, real D-152/D-153 producers), and
  the AI leg runs the REAL `ModelRouter` + `MockAiProvider` +
  `ai_contracts` validation.

## 9. Handover to Phase 8 (Instagram wiring)

Phase 7 leaves the engine with:

- **A verified AI runtime surface** — deterministic, allowlisted, capped
  routing with contract-validated outputs; Phase 8's Instagram content
  generation consumes the same `ModelRouter` seam (caption tasks already
  have a registered route: `generate_caption` → `caption_proposal.v1`).
- **A proven PM core loop** — normalize → align → propose → validate →
  package → cleanup, with a deterministic summary hash as the artifact
  commitment; Phase 8 reuses the identical cycle shape over its own
  fixtures.
- **Idempotent external-write discipline** — the probe-only Notion write
  pattern (fixed payload, payload-hash idempotency key, mandatory cleanup)
  is the template for Instagram publishing probes in Phase 8.
- **Governance chain extended** — D-157's attestation roots in the D-156
  attestation and the D-112 ledger; Phase 8's gate will require the Phase
  7 attestation the same way AIR-01 requires Phase 6 (fail-closed
  recursion: Phase N refusal ⇒ no Phase N+1 probes).

Phase 8 remains owner-gated: no real Instagram credentials, no real
publishing, no lifecycle promotion without explicit owner decisions
(D-045/D-139, plan §17/§21.6).
