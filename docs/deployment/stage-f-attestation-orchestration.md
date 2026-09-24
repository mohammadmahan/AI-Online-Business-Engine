# Stage F — Attestation Integration & Cutover Orchestration (D-147)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **IMPLEMENTED (engine + battery) — nothing authorized,
  nothing deployed.** No cutover bundle with verdict
  `READY_FOR_CUTOVER` has been produced against real infrastructure;
  activation remains owner-gated (D-139, plan §17/§21.6).
- Predecessors: Stage C validation gate (D-143), Stage D configuration
  engine (D-144), Stage E fingerprint binding (D-145), Stage F owner
  authorization gate (D-146).
- Machine enforcement: `local/scripts/cutover_orchestrator.py`,
  rule V-10 in `local/scripts/verify_cutover_readiness.py`, and
  `local/tests/test_cutover_orchestrator_stage_f.py`.

## 1. Purpose

D-146 made the owner token machine-verifiable; D-147 closes the loop
by (a) making the Stage F verdict a **first-class cutover check**
(V-10) so technical clearance cannot exist without it, and (b) providing
the deterministic coordinator that executes the pre-cutover pipeline
in one ordered, audited, hash-bound transaction.

## 2. Rule V-10 — Stage F owner authorization verdict

`verify_cutover_readiness.py` extends the matrix to **V-01..V-10**.
V-10 consumes the verdict record produced by the D-146 gate
(`local/volumes/security/stage_f_verdict.json` — a RUNTIME artifact,
never committed; the gate writes one record per evaluation) and
refuses — always fail-closed — when:

| Condition                                    | Refusal                                     |
|----------------------------------------------|---------------------------------------------|
| No record on disk                            | the gate has not authorized THIS cutover     |
| Record unreadable / malformed                | fail closed                                  |
| Record carries `signature`/`sig`/`nonce`/`signing_key`/`token` fields | forbidden material — refuse and re-mint |
| `gate != "GO"`                               | cutover not authorized                       |
| Fingerprint malformed or ≠ bound manifest    | re-mint after re-binding (D-138 validity)    |
| Ticks malformed / TTL window outside bounds  | fail closed                                  |
| `now >= expires`                             | authorization expired — re-mint required     |
| `now < issued`                               | not yet valid                                |

There is no path from a missing, stale, mismatched, or negative Stage F
verdict to `CUTOVER READY`. The check binds the record to the exact
manifest hash from the V-08 binding — the same bytes Stage E cleared.

**Redaction rule (D-124):** verdict records and check details carry
token ids (16-hex commitments), fingerprints (public binding data,
committed in Git), verdict words, and tick numbers — never signature
bits, nonces, or key material. The gate's redactor is configured to
preserve exactly the two public commitments (`token_id`,
`manifest_sha256`); everything else secret-shaped is scrubbed.

## 3. The cutover transaction (orchestrator)

`cutover_orchestrator.py` runs the ordered pipeline with INJECTED
dependencies (no subprocess/sockets/file I/O/wall clock in the core):

```
Step 1  Stage C   host facts & prerequisites (D-143 validator)
Step 2  Stage D/E manifest fingerprint + V-01..V-10
                  (verify_cutover_readiness offline matrix)
Step 3  Stage F   owner authorization evaluation (D-146 gate; V-10)
Step 4  CutoverBundle  immutable attestation artifact
                  (cutover.bundle.v1 + SHA-256 bundle_hash)
```

Ordering guarantees:

- **Abort-before-burn:** the token is evaluated (and its nonce
  consumed — single-use) only AFTER Stages C and D/E are green. A
  technical failure never wastes an owner authorization (battery-proven).
- **Anti-replay:** a replayed token fails at Step 3 (`replay_rejected`)
  and the bundle is `BLOCKED` with `stage_f_not_authorized`. A replayed
  ATTESTATION is equally inert: bundles are not consumed as authority —
  the nonce burn is the only consumption, so re-presenting an old
  bundle changes nothing.
- **Exactly one audited bundle per call** — `READY_FOR_CUTOVER` or
  `BLOCKED` with a named `abort_reason` (`stage_c_not_ready`,
  `stage_de_not_ready`, `stage_f_not_authorized`), emitted to the
  injected audit sink (D-121 log ledger in production) and bound by
  `bundle_hash` (canonical bytes, key-sorted, sha256).
- **Fail-closed default:** any exception from the gate surfaces as a
  `BLOCKED` bundle — never a silent pass, never a crash with side
  effects.

### 3.1 Bundle contract

| Field                        | Meaning                                   |
|------------------------------|-------------------------------------------|
| `schema`                     | `cutover.bundle.v1`                       |
| `verdict`                    | `READY_FOR_CUTOVER` / `BLOCKED`           |
| `candidate_manifest_sha256`  | exact bound manifest fingerprint          |
| `session_id`, `target_env`   | cutover context                           |
| `observed_tick`              | injected logical clock at bundle time     |
| `steps`                      | per-step verdicts (secret-free details)   |
| `stage_f_token_id`           | the consuming token's public commitment   |
| `abort_reason`               | named blocker (empty when ready)          |

## 4. Attestation lifecycle

1. Owner validates technical readiness (`verify_cutover_readiness.py`
   — V-01..V-09 green expected; V-10 pending authorization).
2. Owner mints the token (D-146 §3) for the exact fingerprint,
   session, and environment, with a sane TTL.
3. Orchestrator executes `run_pipeline(token, draft)`; Steps 1–2 gate
   the burn; Step 3 consumes the nonce exactly once; Step 4 emits the
   hash-bound bundle.
4. `READY_FOR_CUTOVER` is **necessary** for Stage G — never sufficient:
   plan §17/§21.6 sign-offs and D-139 remain the activation authority.

## 5. Handoff into Stage G

Stage G (actual container provisioning) begins ONLY on a
`READY_FOR_CUTOVER` bundle whose `bundle_hash` is recorded in the
control-audit chain, AND an explicit owner command for THIS bundle
hash. Boundaries preserved:

- The bundle authorizes provisioning for the exact manifest bytes it
  binds — regeneration invalidates it (V-08 re-binding → new bundle).
- Rollback remains reachable at every point (runbook §6; the D-125
  archive path governs the data plane).
- Every Stage G action appends to the D-112 control-audit chain; the
  bundle hash is the join key between the pre-cutover attestation and
  the provisioning evidence.
