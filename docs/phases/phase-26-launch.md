# Phase 26 — Launch Readiness, Go/No-Go Attestation & Controlled Activation (D-137–D-140)

- Status: **specification (M0) — decisions PROPOSED, pending owner
  approval; implementation gated on approval**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  strictly localhost/air-gapped (D-045); deterministic chronology
  (injected logical clocks only — D-085/D-086/D-093/D-121 precedent);
  immutable-ledger guarantees are NEVER weakened (D-096/D-112/D-115/D-125).
- **Operating principle:** Phase 26 produces launch *readiness* and a
  deterministic verdict — it is NOT permission to launch. No real
  provider activation, public publication, payment capture, shipment
  purchase, DNS change, credential rotation, or any irreversible
  external action occurs in M0 or before explicit one-time owner
  authorization (D-050 red tier).

## 0. Governance reconciliation & grounding (M0 audit)

MASTER_PLAN §13: **"Phase 26 — Launch. Launch only after security,
backups, payment, inventory, shipping, monitoring, escalation,
end-to-end, and recovery checks pass."** Those nine areas are the
authoritative control domains for D-137.

Baseline `f6d0904` (Phase 25 closeout): battery 814/814 ×2 green,
Phase 25 suite 18/18 zero-skip, census T1=706 · T2=44 · T3=54 · T4=10
(32 modules), ladder 46/46, AST CLEAN (68 files), entropy CLEAN
(112 files), stack 5/5, tree clean = origin/main.

**Grounded implementation surfaces (compose, never duplicate):**

| Existing primitive | Phase 26 use |
|---|---|
| Phase 20 `security_worker.py` sweeps (`ast_sweep`, `entropy_scan`, `bounds_re_audit`) + D-114 input hardening | Security-domain evidence: isolation, least-privilege, audit-ledger integrity, config checks |
| D-121 `obs_contracts` `LogLedger` / `TraceContext` (`engine.log.v1`) | Machine readiness + activation telemetry audit destination |
| D-123 `obs_health.py` (`qa.health_report.v1`, `ProbeRegistry`) | Monitoring-domain probes; readiness evaluator consumes probe verdicts |
| D-124 redaction / zero-leak gates | Evidence + report secret redaction |
| D-125 `compaction.py` verified-freeze archives | Backup/restore-domain evidence pattern (attested archives; restore rehearsal) |
| D-127 `budget_engine.BudgetLedger` (+ D-128 envelopes) | Canary resource/cost ceilings, hard refusal, kill-switch input |
| Phase 19 `admin_contracts.py` RBAC (`is_permitted`), one-time `confirmation_key` consumption, `admin.control_audit` hash-chained vault (JSON + PG twins) | Owner-approval tokens, break-glass, human-decision audit destination |
| Phase 24 `portability*.py` contracts | Provider-boundary evidence (payments/shipping/channel swaps behind declared contracts) |
| Phase 25 `e2e_contracts/e2e_conductor/e2e_recovery` + `qa_toolkit.FaultScript` | End-to-end + recovery evidence; dry-run/canary rehearsal harness |
| D-027 event stores (JSON parity + `PgEventStore`) | Durable attestation & activation-state persistence (live leg) |

**No new subsystems are invented** — every control composes an
existing, battery-proven primitive.

## 1. D-137 — Launch Readiness Control Matrix (Proposed)

One canonical, versioned control matrix over the nine MASTER_PLAN
domains. Each control: stable `control_id` (`SEC-*`, `BAK-*`, `PAY-*`,
`INV-*`, `SHP-*`, `MON-*`, `ESC-*`, `E2E-*`), owner **role**
(configuration, never a hard-coded identity), severity
(`critical`/`high`/`medium`), mandatory flag, declared
**evidence kind** (see §4 validity model), evidence reference, and
remediation guidance. States: `PASS`, `FAIL`, `BLOCKED`,
`NOT_APPLICABLE` — **missing/stale/unknown evidence is never PASS**
(it evaluates as `BLOCKED` and fails the verdict closed).

Domain anchors (all machine-checkable in this repository):
security → Phase 20 sweeps + D-114; backup → D-125 verified-freeze +
restore-rehearsal evidence (a backup is valid only after a successful
restore); payments → server-side verify path (Phase 12
`payment_verdict` flow), idempotent callbacks (D-027 keys), negative
verdicts → cancel + inventory restore (Phase 25-proven), capture
DISABLED until owner activation; inventory → D-082/D-084 atomic
reservation + oversell prevention + failure restoration; shipping →
provider-neutral intent boundary (Phase 24 contract), no purchase
pre-approval; monitoring → D-123 probes + D-121 ledger + D-124
redaction; escalation → config-declared roles (Phase 19 RBAC actor
model), severity→role routing, runbook refs, break-glass audited;
end-to-end/recovery → Phase 25 suite + census + ladder tied to the
exact candidate commit.

## 2. D-138 — Deterministic Go/No-Go Attestation (Proposed)

Pure evaluator over the matrix: verdict `GO` (all mandatory `PASS`, no
blockers) / `CONDITIONAL_GO` (only for explicitly declared
limited-scope activation; never silently full production) / `NO_GO`
(any mandatory FAIL/BLOCKED/stale/unevaluable). Properties: fail
closed; stable finding ordering; identical inputs ⇒ byte-identical
output; evidence bound to candidate commit + configuration
fingerprint (secrets excluded, D-124); machine + human reports from
one canonical result; **attestation hash** over (matrix version,
candidate commit, config fingerprint, evidence refs, findings,
verdict, approval state); any source/config change, expiry, or failed
recheck invalidates prior attestation. Technical GO is **necessary
but not sufficient** — owner approval remains mandatory.

## 3. D-139 — Controlled Activation, Canary & Rollback (Proposed)

Activation is a gated, reversible sequence — never one global switch.
State machine: `DRAFT → ASSESSED → (NO_GO | GO_ATTESTED) →
OWNER_APPROVED → DRY_RUN → CANARY → OBSERVING → PROMOTED`, with
`ROLLING_BACK → ROLLED_BACK` reachable from every state that can
produce external side effects, and illegal transitions failing
deterministically.

- **Preflight:** candidate commit identity, clean tree, attestation
  validity, backup/restore evidence, monitoring/escalation availability.
- **Dry run:** config + provider-reachability validation with **zero
  public side effects** (no capture, no publication, no purchase).
- **Limited canary:** smallest owner-approved scope under D-127/D-128
  ceilings, hard refusal enforced, kill-switch available, every
  transition audited.
- **Observation:** error rate, latency, queue depth, retries, budget,
  publication/order outcomes, inventory consistency, alert delivery
  vs declared thresholds.
- **Promotion:** explicit one-time owner approval token (Phase 19
  confirmation-key semantics: replay/expiry/mismatch/consumed all
  rejected); absence of failures never infers approval.
- **Rollback:** deterministic triggers; stop-new-work before
  compensate/drain; forensic evidence preserved (never deleted);
  outbox/lock/reservation/intent reconciliation post-rollback;
  state-verification report.

Audit destinations (proposed): machine readiness/activation telemetry
→ D-121 `engine.log.v1`; human approval, break-glass, promotion →
Phase 19 `admin.control_audit` chain.

## 4. Evidence-validity model (D-137/D-138)

- **Commit-bound** (regenerated on any source change): test battery,
  census, ladder, AST/entropy/diff sweeps, E2E + recovery evidence.
- **Configuration-bound** (regenerated on config-fingerprint change):
  budget envelopes, escalation routing, threshold declarations.
- **Expiring** (logical age, not wall clock): provider reachability
  probes, restore rehearsals, monitoring attestation.
- **Human-attested** (owner role, recorded in the control-audit
  chain): backup-policy sign-off, launch authorization, break-glass.

The evaluator takes validity metadata as injected inputs; it computes
staleness from declared logical horizons — never from wall-clock time.

## 5. Milestone plan (implementation gated on approval)

| M | Content | Proof |
|---|---|---|
| M1 | `canonical/launch_contracts.py` (controls, evidence kinds, validity, fingerprints) + `launch_evaluator.py` (pure verdict + attestation hash) | Offline diag: complete-pass, mandatory-fail, blocked, missing/stale/malformed evidence, config/commit mismatch, byte-identical outputs |
| M2 | Evidence collectors (injected adapters over the grounded surfaces) + `activation state machine` + rollback/reconciliation protocol | Activation + rollback rehearsal offline; approval replay/expiry/mismatch rejection; kill-switch; zero side effects in dry-run; live-PG persistence leg |
| M3 | `tests/test_phase26_launch.py` — matrix evaluation, validity/invalidation, attestation determinism, approval gates, dry-run safety, canary ceilings, monitoring/escalation, backup/restore proof, rollback reconciliation (offline-hermetic + live-PG, zero skips) | Suite green |
| M4 | Battery ×2 + verbose census + ladder + AST/entropy/redaction/diff sweeps + evidence pack + docs closeout | §6 gates all PASS |

## 6. Acceptance gates (D-140)

Phase 26 suite zero-skip · full battery ×2 green, zero warnings/flakes ·
census reconciles exactly · ladder green · AST + entropy + redaction
CLEAN · `git diff --check` PASS · stack healthy · tree clean ·
evidence pack generated from canonical results with attestation hash.

## 7. Owner decision points (awaiting ruling)

1. Approve / amend D-137–D-140 (all Proposed).
2. Confirm M0 + implementation prepare and rehearse launch controls
   but perform NO real production activation.
3. Confirm missing operational evidence always yields `NO_GO` (never
   an assumed pass).
4. Approve the activation sequence: preflight → dry run → limited
   canary → observation → explicit promotion → rollback on breach.
5. Approve audit destinations: D-121 ledger for machine telemetry;
   Phase 19 control-audit chain for human approvals/break-glass.
6. Confirm the final Phase 26 commit establishes a **launch candidate
   only**; live activation requires a separate explicit one-time owner
   authorization.

## 8. Verification record

- Date: 2026-09-19 · Decisions D-137–D-140 **APPROVED** (owner,
  2026-09-19, all six ruling points applied).
- **M1 — contracts & evaluator** (`canonical/launch_contracts.py`,
  `canonical/launch_evaluator.py`): closed control-state tuple
  (`PASS/FAIL/BLOCKED/NOT_APPLICABLE`), mandatory/severity flags,
  evidence-validity model (commit-bound, config-bound, logical
  expiry, human-attested), secret-free config fingerprint
  (D-124 redaction gate on the fingerprint path), fail-closed
  evaluator — missing/malformed/stale/unbound/contradictory evidence
  is NEVER a pass; verdicts `GO` / `CONDITIONAL_GO` (limited-scope
  only) / `NO_GO`; attestation hash over (matrix version, candidate
  commit, config fingerprint, evidence, findings, verdict, approval
  state); byte-identical canonical output for identical inputs.
- **M2 — activation & evidence** (`canonical/launch_activation.py`,
  `canonical/launch_evidence.py`): DRAFT → ASSESSED → (NO_GO |
  GO_ATTESTED) → OWNER_APPROVED → DRY_RUN → CANARY → OBSERVING →
  PROMOTED, illegal transitions deterministic-rejected; one-time
  context-bound approval tokens with owner nonce (replay/expiry/
  mismatch/consumed rejected; durable burn in the D-027 store);
  rollback reachable from CANARY/OBSERVING (every side-effect-capable
  state); kill-switch; dry-run zero-side-effect guard; machine
  telemetry → D-121 `engine.log.v1`, human approvals → Phase 19
  hash-chained `admin.control_audit` via the new public
  `append_external_audit` (D-112 tamper-evident). Nine-domain
  canonical matrix + collectors over existing surfaces (Phase 20
  sweeps, D-123 probes, D-125 compaction/restore rehearsal,
  D-127/D-128 budgets, Phase 25 conductor evidence).
- **M3 — battery** (`local/tests/test_phase26_launch.py`): **46/46
  zero-skip** (43 offline-hermetic + 3 live-PG) — matrix evaluation,
  fail-closed paths, verdict determinism, commit/config binding,
  redaction, approval replay/expiry/mismatch/consumption, dry-run
  safety, canary ceilings, rollback ordering + reconciliation,
  live chain verification + durable burn in real PostgreSQL.
- **M4 — gates**: battery **860/860, two consecutive green runs,
  zero warnings**; ladder 46/46; census reconciles exactly
  (**T1=710 · T2=46 · T3=56 · T4=13 = 860, 33 modules, green=True**);
  AST CLEAN (107 files) / entropy CLEAN (107 files) / channel
  isolation CLEAN (72 files); `git diff --check` PASS; stack 5/5
  healthy.
- **Live-leg defects found & fixed in-batch** (all pinned by tests):
  1. `PgVault.append_audit` relied on the PG sequence default for
     `audit_seq` while `row_hash` embedded the Python-side seq —
     any delete (retention) silently diverged them and broke the
     chain for every later row. Fixed: `audit_seq` inserted
     explicitly, with a `::bigint` cast for the text-transport
     psql boundary.
  2. PG audit rows stored the string `'None'` for NULL command/
     target (psql transport cannot carry SQL NULL) while the JSON
     vault preserved real `None` — a Phase 24-style parity gap.
     Fixed with the `_norm_none`/`_denorm_none` sentinel in BOTH
     vaults (`'None'` is never a legal command).
  3. Rehearsal debris from pre-fix runs (rows 433–454) was pruned
     after verification; Phase 19–23 history (rows 1–432) verified
     intact — `verify_chain() → {'ok': True, 'rows': 432}`.
- **Suite-found engine defects fixed in-batch**: fail-open
  aggregation over missing evidence (empty contract set ⇒ GO),
  DRY_RUN/OBSERVING wrongly token-gated (they are zero-side-effect;
  the side-effect-capable transitions are CANARY/OBSERVING-entry/
  PROMOTED), replay-deadlocked approval context (owner nonce added
  — context-bound yet fresh per attempt), OBSERVING rollback
  reachability.
- **Result: launch candidate established — NOT a launch.** The
  deterministic verdict machinery is shipped and attested; live
  production activation requires a separate, explicit, one-time
  owner authorization (D-139).

---

## 9. Resilience drill — catastrophic recovery (extension, 2026-09-19)

- **Scope:** the BAC-001 backup/recovery control executed FOR REAL
  against the live D-027 store: a run-scoped flow seeded through the
  real `PgEventStore` API (receive → begin → succeed + one
  skipped-duplicate terminal), archived with the D-125
  verified-freeze primitives (`write_snapshot`/`verify_snapshot`),
  PROVEN destroyed (counted `DELETE … RETURNING`), then restored from
  the archive — only after the archive re-verified (the D-125 gate:
  a backup counts only after its attestation holds).
- **Fail-closed gates proven:** a forged archive (single flipped
  byte) and a missing archive both raise the Class-B
  `CompactionError` and restore NOTHING — missing or negative
  evidence can never yield a pass (D-137 anti-fail-open).
- **Verification performed:** canonical fold equality (pre-catastrophe
  state == post-restore state == archive-attested fold), store-level
  equality via `get_record`/`succeeded_references` in deterministic
  order, global store count byte-identical across the disaster (zero
  collateral damage to other namespaces), per-run namespace isolation
  with post-run cleanup.
- **Suite:** `local/tests/test_phase26_resilience_drill.py` — 4 tests
  (2 offline T1 + 2 live-PG T3), two consecutive green runs, zero
  skips; BAC-001 evidence bound to the runtime-resolved candidate
  commit and the configuration fingerprint.
- **Anti-fabrication note:** an externally supplied drill script
  referenced non-existent modules (`RestoreEngine`,
  `EvidenceCollector.generate_census`) and a non-existent archive and
  would have appended an unearned certificate BEFORE any run. It was
  reimplemented on the real primitives; the certificate below
  reflects only the machine-verified runs.

### Census correction (recorded 2026-09-19)

The Phase 26 closeout block above recorded the census as
`T1=710 · T2=46 · T3=56 · T4=13` — those figures came from a manual
module-level tally and do not reproduce under the canonical D-120
toolkit (module tally missed class-based T3/T4 rules). The canonical
recount of that same closeout state is **T1=749 · T2=44 · T3=57 ·
T4=10 = 860**. The current state (with the drill) reconciles as
**T1=751 · T2=44 · T3=59 · T4=10 = 864 (34 modules), green=True**.
Totals were always exact; only the tier split was mis-recorded.

### Recovery certificate

- Date: 2026-09-19
- Drill: catastrophic recovery (destroy → restore → verify)
- Result: **PASSED** — machine-verified (4/4 ×2 consecutive runs,
  zero skips, live PostgreSQL stack 5/5 healthy)
- Evidence: `EV-BAC-001` (commit-bound, config-fingerprint-bound)
- Primitives: D-125 `write_snapshot`/`verify_snapshot` over the live
  `events.event_record` D-027 store (run-scoped namespace only)
- Exclusions: production rows untouched; rehearsal namespaced and
  cleaned; no wall-clock identity material (D-085/D-093).

### Operationalization — operator command & matrix integration (2026-09-19)

**Command:** `local/scripts/resilience_drill.py`
(`--events N`, `--json`; exits 2 when the stack is unhealthy — fail
closed before stage 1). Six-stage lifecycle, each stage
machine-checked with structured status output:

1. Scoped seed & canonical fold capture (real D-027 API;
   run-scoped namespace — live production state is never touched)
2. Snapshot archiving & verification (D-125 verified-freeze gate)
3. Controlled scope purge (counted `DELETE … RETURNING` —
   destruction proven; global store count reconciles)
4. Rehydration from the re-verified snapshot (idempotent inserts,
   original `ingest_seq` preserved)
5. Byte-equal fold & storage verification (records, references,
   ordering, zero collateral rows)
6. Evidence certification (EV-BAC-001, commit + fingerprint bound)

**Fail-closed properties (fault-injection-tested):** a failure at
ANY stage — before or after the archive verifies — yields verdict
`FAILED` and NEGATIVE evidence; the namespace is always cleaned.
The verdict is recomputed from the stage list on every path (a
fail-open regression caught by fault injection was fixed and is
pinned by the battery).

**Matrix integration (D-137/D-138):**
`canonical_matrix(..., drill_result=<structured result>)` derives
BAC-001 from the real rehearsal: write gate = stages 1–2, verify
gate = stages 2+4, overall = drill ok. A FAILED drill blocks
BAC-001 ⇒ NO_GO — disaster-recovery readiness now rests on real,
repeatable rehearsal evidence rather than a caller's boolean.

**Battery:** `test_phase26_resilience_drill.py` 10/10 ×2 green
(5 offline + 5 live-PG: lifecycle, debris-free guarantee, fault
injection, CLI JSON contract, matrix integration). Full battery
**870/870 ×2 green, zero warnings**; census (canonical D-120
toolkit) **T1=754 · T2=44 · T3=62 · T4=10 = 870 (34 modules),
green=True**; AST CLEAN (72 files) / entropy CLEAN (118 files);
`git diff --check` PASS; stack 5/5 healthy.
