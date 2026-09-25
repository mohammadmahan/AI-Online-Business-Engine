# Stage G — Formal Closure & Stage H Handoff Seal (D-152)

**Status: IMPLEMENTED — nothing provisioned, nothing activated.**
D-152 concludes Stage G: a single master orchestrator verifies the
complete C→G artifact chain and emits the singular, unforgeable
`stage_g_closure_seal.v1` whose `closure_digest` is the cryptographic
root for Stage H (live activation) entry.

## 1. The closure seal

`stage_g_closure_seal.v1` (emitted by
`local/scripts/stage_g_closure_and_handoff.py`):

| Field | Meaning |
|---|---|
| `verdict` | `STAGE_G_CLOSED` / `STAGE_G_OPEN` |
| `manifest_sha256` | the Stage D envelope fingerprint |
| `bundle_hash` | the D-147 attestation root |
| `acceptance_fingerprint` | the D-149 clearance root |
| `probe_digest` | the D-150 live observation root |
| `checks` | CLS-01..CLS-05 verdict rows, deep-redacted (D-124) |
| `closure_digest` | SHA-256 over the seal's canonical bytes — the Stage H root |

Every digest field is verified against recomputation before it is
sealed; the seal is emitted and audited exactly once per run
(including aborts) to the injected D-112/D-121 sink. **Exactly one
seal per closure attempt** — a re-closure after remediation produces
a new, distinct seal; the old one stays in the chain as history.

## 2. The closure checks (CLS-01..CLS-05)

- **CLS-01 — chain presence & integrity.** Every link must be
  present, schema-correct, and intact:
  - Stage C host readiness: verdict `READY` with every check green;
  - Stage D: manifest SHA-256 matches its fingerprint envelope,
    bound for `stage-e-cutover`;
  - Stage E: the rollback contract present (parsed deeply in
    CLS-04);
  - Stage F: `cutover.bundle.v1` with `bundle_hash` recomputing,
    carrying its `stage_f_token_id`;
  - Stage G: acceptance `ACCEPTED`, live probes `PROBES_ACCEPTED`.
- **CLS-02 — zero drift.** ONE manifest fingerprint across the
  envelope, the raw manifest bytes, the bundle
  (`candidate_manifest_sha256`), the acceptance report
  (`manifest_sha256`) and the probe report (`manifest_sha256`); the
  probe's `acceptance_fingerprint` equals the acceptance report's
  own fingerprint.
- **CLS-03 — the triad gate with zero bypasses.** The D-151
  `TripleEvidenceGate` verdict must be `LAUNCH_EVIDENCE_COMPLETE`
  with **every** TRIAD-01..04 rule present in `checks` and passing —
  a skipped rule or a blocked rule is a refusal (zero warnings, zero
  bypassed rules).
- **CLS-04 — atomic rollback + health fallbacks.** The Stage E §5
  matrix must parse as RB-1..RB-6 table rows each carrying
  trigger / procedure / post-verification, the ordering invariant
  (`stop new work first, then compensate/drain, then reconcile`) must
  be declared, and every health-fallback trigger must be well-formed
  (name, positive `threshold_ticks`, action).
- **CLS-05 — the seal.** All previous checks green ⇒ the seal is
  emitted as `STAGE_G_CLOSED` with the root digest; any refusal ⇒
  `STAGE_G_OPEN` with the named blockers (the seal is still emitted —
  an OPEN seal is itself audited evidence).

## 3. What the seal does NOT authorize

The seal authorizes a **handoff candidate** only. It is necessary but
NOT sufficient for activation: production activation remains
exclusively owner-gated (D-139, plan §17/§21.6). The seal carries no
credentials, no signatures, no nonces — only public commitments
(hashes, ids, verdict phrases).

## 4. Owner runbook — invoking Stage H with the seal

1. **Re-run closure immediately before handoff.** The seal is
   evidence-bound, not perpetual: re-run the orchestrator against the
   current artifacts; a stale seal (older than the newest artifact in
   the chain) is not a handoff basis.
2. **Verify the seal in the D-112 chain.** Locate the closure row
   (kind `stage_g_closure`) and confirm `closure_digest` recomputes
   from the seal dict.
3. **Invoke Dokploy provisioning** with the Stage D manifest whose
   SHA-256 equals `manifest_sha256` inside the seal — Dokploy
   consumes the compose file; the seal's digest is the recorded
   authorization root.
4. **After provisioning:** run the D-150 live probes (via the D-151
   adapters) and require `PROBES_ACCEPTED` binding THIS manifest and
   THIS acceptance fingerprint.
5. **Record the activation row** in the D-112 chain (kind
   `stage_h_activation`) referencing the seal's `closure_digest`.
6. **Owner confirmation.** The one-time owner approval (D-139) is the
   final authority — the technical chain being green never
   substitutes for it.

## 5. Rollback thresholds (CLS-04 triggers + Stage E §5 matrix)

The Stage E §5 matrix (RB-1..RB-6) governs every rollback; the
ordering invariant (stop → compensate/drain → reconcile; evidence
preserved, never deleted) is verified, not assumed. Health-fallback
triggers declared at closure (and re-validated at handoff):

| Trigger | Threshold | Action |
|---|---|---|
| `probe_red` | 1 red probe (threshold_ticks = 1) | Stage E §5 row governs (RB-3) |
| `heartbeat_stale` | 120 ticks without a fresh heartbeat | RB-3 (drain + edge to blue) |
| `bundle_expired` | bundle age ≥ 5000 ticks at closure | re-attest (no rollback; closure refused) |
| `chain_broken` | 1 chain-verify failure | RB-4 (freeze dispatch, reconcile) |

Any threshold change after closure ⇒ the seal is void; re-close.

## 6. Post-activation health monitoring

- `qa.health_report.v1` probes (D-123) with the mandatory
  `stage_g_triple_evidence` probe (D-151) — a triad FAIL keeps the
  deployment verdict halted.
- `infra_health_probe.deploy_verdict()` — DEPLOY_OK requires every
  probe PASS; any red probe is a halt (fail-closed).
- The D-150 GA-1..GA-7 probes re-run on schedule via the D-151
  adapters; a REJECTED report feeds Stage E §5 (RB-3) immediately.
- The D-112 chain verifies end-to-end on every monitoring cycle; a
  broken chain is an RB-4 trigger.

## 7. Test surface

`local/tests/test_stage_g_closure_and_handoff.py` — full passing
closure over real Stage D material, refusal of every tamper path
(each chain link, drift, triad, rollback/fallback malformation),
redaction scrub, AST audit of the pure core.

Nothing here provisions, deploys, or activates anything. **D-139
remains the sole activation authority.**
