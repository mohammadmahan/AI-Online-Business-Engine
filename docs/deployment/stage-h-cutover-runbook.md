# Stage H — Live Cutover Runbook & Owner Activation Record (D-153)

**Status: IMPLEMENTED — nothing executed live.** The Stage H
executor exists; a live cutover happens only through this runbook,
under explicit owner authority (D-139, plan §17/§21.6).

## 1. Preconditions (all fail-closed)

| # | Requirement | Verified by |
|---|---|---|
| H-01 | `stage_g_closure_seal.v1` present, `STAGE_G_CLOSED`, digest recomputing, rooted in the D-112 chain | executor |
| H-02 | Stage F owner token fresh, unspent, window covering the activation tick, fingerprint == seal manifest | executor |
| H-03 | Dokploy target state healthy, zero unmapped port exposure | executor + adapter |

Any refusal ⇒ **zero side-effects**: no transition, no state change,
one audited `CUTOVER_ABORTED` record naming the blocker.

Record verdicts: `CUTOVER_EXECUTED` (transition confirmed, critical
window green), `CUTOVER_ABORTED` (refusal BEFORE any side-effect),
`ROLLBACK_ARMED` (transition happened but the critical window is not
green — the atomic rollback payload is emitted for the operator).

## 2. Owner token injection (Step 1)

The owner mints the token OFFLINE with their own signing key
(never shared, never stored by the engine — D-146/D-124):

```python
from owner_approval_gate import TokenDraft, mint_token

draft = TokenDraft(
    manifest_sha256="<seal.manifest_sha256>",   # the D-144 envelope fingerprint
    session_id="cutover-session-01",            # the bound session
    target_env="staging",                       # or the production env
    issued_tick=<now>,                          # injected logical clock
    expires_tick=<now + 500>,                   # 1..10_000 tick window
    nonce="<unique-per-attempt>",               # burned on first GO
)
token = mint_token(signing_key, draft)          # "<token_id>.<sig>"
```

Hand the orchestrator **both** the token and the draft over the
approval channel. The key never enters the executor.

## 3. Cutover triggering (Steps 2–4)

1. **Closure seal** — load the D-152 seal; the executor verifies the
   digest and its D-112 rooting (H-01).
2. **Owner gate** — run `OwnerApprovalGate.evaluate(token, draft,
   session, env, envelope_text)`; only a `GO` verdict (the nonce is
   burned exactly once at GO) proceeds (H-02).
3. **Pre-cutover assertions** — `DokployStateAdapter.target_state()`
   (direct argv, `docker inspect --format '{{json .}}' <svc>`) must
   show every service running + healthy, restarts ≤ 3, and zero
   unmapped ports on backend services (H-03).
4. **Transition** — the injected `transition` provider performs the
   deployment state → ACTIVE change (Dokploy redeploy of the manifest
   whose SHA-256 equals the seal's `manifest_sha256`); the executor
   emits the immutable `stage_h_activation_record.v1` with its
   `activation_digest` (H-04).

## 4. Live traffic routing

After H-04, route traffic only through the edge service
(`app-orchestrator`, sole `edge` attachment per D-149 ACC-01):
backend services are internal-network-only; the edge is the sole
public surface. The H-03 zero-unmapped-exposure assertion is
re-checked by every monitoring cycle.

## 5. Critical window & rollback execution (H-05)

For `CRITICAL_WINDOW_TICKS = 1_000` ticks after activation the
post-activation probes are watched. Any failed probe arms the
**atomic rollback payload** (`stage_h_rollback_payload.v1`, RB-1):

- **Payload is a verdict, not an action** — the engine never mutates
  the live stack on its own authority; the OPERATOR executes it.
- **Ordering invariant:** stop new work first, then compensate/drain,
  then reconcile; durable evidence is preserved, never deleted
  (D-139).
- **Procedure:** edge gateway back to blue; green stack `stop` (keep
  volumes); re-run the Stage E §4 verification against blue.
- **Post-verification:** smoke green on blue; incident logged to the
  D-121 ledger.

Rollback thresholds (RB-1..RB-6) and health-fallback triggers
(`probe_red`, `heartbeat_stale`, `bundle_expired`, `chain_broken`)
are declared in the D-152 closure contract
(`stage-g-closure-and-handoff.md` §5).

## 6. Safety properties

- **Direct argv only** — `DokployStateAdapter` executes fixed token
  lists with strict timeouts; zero `shell=True`; parameters
  allow-list validated; deep redaction before any string escapes.
- **Zero side-effects on refusal** — every H-01/H-02/H-03 failure
  aborts before the transition provider is invoked.
- **Single-use authority** — the nonce burns at GO; a replayed token
  arrives as a non-GO verdict and aborts.
- **Secret-free records** — the signing key and nonce never enter
  any record; only public commitments (manifest hash, closure
  digest, token id) are restored after redaction in the ledger copy.
- **Immutable record** — `activation_digest` binds the activation to
  THIS seal, THIS token id, and THIS tick; any later alteration of
  the record is detectable by recomputation.

## 7. Post-activation monitoring

- `qa.health_report.v1` probes (D-123) with the mandatory
  `stage_g_triple_evidence` probe (D-151) — a triad FAIL keeps the
  deployment verdict halted.
- `infra_health_probe.deploy_verdict()` — DEPLOY_OK requires every
  probe PASS (fail-closed).
- Scheduled GA-1..GA-7 re-probes (D-150 via the D-151 adapters); a
  REJECTED report feeds the Stage E §5 matrix (RB-3) immediately.
- The D-112 chain verifies end-to-end every cycle (RB-4 on breakage).

## 8. Test surface

`local/tests/test_stage_h_cutover_executor.py` — successful
transition with aligned seal+token; refusal of missing/open/altered/
unrooted seals; refusal of stale/invalid/divergently-bound tokens;
rollback payload safety on a simulated anomaly; redaction scrub;
AST audit of argv isolation and zero shell.

**Nothing here executes a real cutover without the owner's explicit,
single-use authority. D-139 remains the sole activation authority.**
