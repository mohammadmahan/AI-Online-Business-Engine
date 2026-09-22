# Stage G — Post-Cutover Acceptance Specification (D-141; PLANNED)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED specification.** No cutover has occurred; the
  probes below are defined so the post-launch verification phase is
  completely specified BEFORE any live deployment begins. Execution
  is owner-gated (D-139) and uses production data only after the
  Stage F gate passes.
- Predecessors: Stage E runbook §4 (post-cutover smoke), Stage F
  authorization gate, `run_staging_smoke_tests.py` (the proven smoke
  harness pattern), D-123 health probes, D-121 log ledger, D-137
  control matrix.

## 1. Purpose and exit verdict

Stage G answers one question with evidence: **did the cutover
actually succeed?** It runs immediately after the Stage E transition
and must reach an explicit verdict:

- `ACCEPTED` — all probes pass for two consecutive evaluation
  cycles; the platform hands over to steady-state operations.
- `REJECTED` — any mandatory probe fails, is missing, or cannot be
  assessed; Stage E §5 rollback matrix governs immediately.

There is no partial acceptance: unknown is failure (D-137
fail-closed precedent).

## 2. Acceptance probe definitions

Every probe is read-only, deterministic, and emits a structured
verdict (`PASS`/`FAIL`/`CANNOT_ASSESS`) with a detail string that
never contains secret material (D-124). Definitions here are the
contract; the executor script is authored at implementation time
(`local/scripts/run_stage_g_acceptance.py`, planned) and must
implement exactly these checks:

### GA-1 — Container surface
All five production services (`wordpress`, `woodb`, `canonical-db`,
`n8n`, `media`) report healthy under the deployed project labels;
the edge is the only published surface (zero direct DB/app ports).
Pattern: Stage D stack checks (label-based, no secret env needed).

### GA-2 — SSOT integrity (zero-data-loss validation)
Canonical PostgreSQL schema census equals the bootstrap census
(13/13 schemas; provenance tables present); the decision-ledger hash
chain verifies end-to-end (D-112 chain walk) and the transactional
fold (D-125) over a post-cutover snapshot equals the fold recorded
at the Stage E backup step — proving the cutover window lost no
durable row.

### GA-3 — Business metric sanity
The D-085 rollup frame over post-cutover publication/order outcomes
is internally consistent: every dispatched item has a terminal
outbox state; every order has a lifecycle-consistent state
(PLACED/VALIDATED/FULFILLING/COMPLETED or a terminal CANCELLED/
REFUNDED); no phantom rows (Phase 25 reconciliation invariants,
D-135).

### GA-4 — Telemetry verification
`qa.health_report.v1` generates with all probes PASS; the D-121 log
ledger accepts an append and verifies its chain; the D-123 probe
registry runs green. A silent telemetry plane is a REJECTED
cutover, not a warning.

### GA-5 — Edge policy conformance
The live edge (the only public surface) returns the Stage E §4
header policy: HSTS ≥ 31536000, `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, CSP present, HTTP→HTTPS 301/308. This is
the Stage E `--edge` probe executed against production and folded
into MON-001 (launch_evidence.monitoring_evidence).

### GA-6 — Budget & breaker posture
D-127 budget ledgers are within envelope at cutover completion; no
breaker is left OPEN from cutover-time faults (D-066/D-126
hygiene); the D-128 ceilings match the deployed manifest limits.

### GA-7 — Recovery readiness (post-change, not stale)
The transactional restore drill and the decision-ledger consistency
pass re-run green **against the deployed state** — evidence older
than the cutover commit does not satisfy GA-7 (D-138 evidence
validity model: code change invalidates commit-bound evidence).

## 3. Evaluation protocol

1. Quiesce window: operators stop injecting change; the platform
   runs its normal deterministic workers only.
2. Run all probes GA-1..GA-7; record each verdict with a logical
   sequence stamp (no wall clock — D-085/D-093/D-121 precedent).
3. **Two consecutive green cycles** are required for ACCEPTED;
   between cycles, the platform executes at least one full
   synthetic business flow (the Phase 25 conductor path, staged
   shapes) to prove liveness, not just stillness.
4. Any FAIL or CANNOT_ASSESS in cycle 1 ⇒ REJECTED immediately
   (fail closed). A FAIL in cycle 2 after a green cycle 1 is also
   REJECTED — flakiness is not acceptance.
5. The acceptance report (probe verdicts, commit, config
   fingerprint, fold values, chain lengths) is appended to the
   runbook's execution log and referenced from the D-140 evidence
   pack as the Stage G attachment.

## 4. Rollback interlock

Stage G does not decide rollback by itself; it declares REJECTED
and Stage E §5 governs. The RB-1..RB-6 ordering (stop → compensate
→ reconcile) applies unchanged. After any rollback, Stage G restarts
from probe GA-1 only after a NEW successful cutover (fresh evidence;
no carry-over of green probes across transitions).

## 5. Explicit non-goals

- No performance/load certification: Stage G verifies correctness
  and integrity surfaces, not throughput SLAs.
- No marketing/analytics attribution: business metric sanity (GA-3)
  is lifecycle consistency, not commercial effectiveness.
- No production data seeding: synthetic flows only until the owner
  explicitly authorizes real-data operation (D-045/D-139).

## 6. References

- `docs/deployment/stage-e-cutover-runbook.md` §2/§4/§5
- `docs/deployment/stage-f-authorization.md` (the gate that must
  pass before any Stage G execution exists)
- `DECISIONS.md` D-112, D-121, D-123, D-124, D-125, D-127, D-128,
  D-135, D-137–D-141
