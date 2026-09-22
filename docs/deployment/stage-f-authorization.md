# Stage F — Owner Authorization Gate (D-141; PLANNED — not yet executable)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED readiness artifact.** Nothing has been signed,
  no token has been issued, and no production cutover command has
  run. This document converts the Stage E §6 sign-off matrix into a
  deterministic, machine-verifiable pre-cutover gate.
- Predecessor: `docs/deployment/stage-e-cutover-runbook.md` (§1
  preflight, §5 rollback matrix, §6 signoff checklist, §7 stop
  conditions). The runbook's authority gates (§0) remain binding:
  D-139 promotion requires explicit owner approval; no missing or
  stale evidence can ever read as a pass.
- Verification tooling: `local/scripts/verify_cutover_readiness.py
  --stage-f` (fail-closed checklist integrity check; see §4).

## 1. Why a separate authorization gate

Stage E proves the *plan* is technically sound. Stage F proves the
*people and credentials* are authorized before the plan may execute.
A technically green cutover without signed, single-use,
context-bound owner authorization is a NO-GO by definition (D-139:
technical GO is necessary but not sufficient). This gate is therefore
checked **again** immediately before the first cutover command, not
only during planning.

## 2. Sign-off matrix (synthesized from Stage E §6)

Every row is a blocking item: unsigned ⇒ gate fails closed.

| # | Authorization item | Owner role | Evidence form | Binding | Expiry |
|---|--------------------|-----------|---------------|---------|--------|
| SF-1 | Host SSH + sudo granted to operator role, window-scoped | owner | signed entry in the runbook's execution log (name, date, window) | window-bound | start of cutover window |
| SF-2 | Production secret set staged in the deploy secret store (9 `${VAR:?}` keys) | owner | secret-store receipt listing key NAMES only (never values) | config-bound | config-fingerprint change |
| SF-3 | DNS/TLS authorization for the production domain | owner | registrar/DNS-provider change authorization record | domain-bound | 30 days |
| SF-4 | Off-host backup destination credentials (Phase 24 MediaStore) | owner | MediaStore binding attestation (EV-BAC-001 decision leg reference) | config-bound | credential rotation |
| SF-5 | Promotion approval token issued (single-use, commit-bound) | owner | Phase 19 control-audit chain row (token ID, commit, issue time) | commit-bound | single use |
| SF-6 | Break-glass contacts acknowledged by all named roles | owner + sre | acknowledgment entries in the escalation runbook | role-bound | role change |
| SF-7 | Post-window credential rotation plan accepted | owner | signed rotation plan naming every credential that transits the operator shell | plan-bound | cutover completion |

Rules:

- SF-1..SF-6 must be **signed before** the Stage E §1 preflight is
  run against production. SF-7 is signed at gate exit (after
  rollback-or-promotion completes) but its **plan** must exist at
  gate entry.
- Each item records WHO signed, WHEN (date), and the evidence
  reference. A checklist row with no name/date/reference is unsigned.
- The promotion token (SF-5) is issued by the owner through the
  Phase 19 control plane (one-time confirmation mechanics), recorded
  in the Phase 19 control-audit chain, and consumed by the D-139
  activation state machine. It binds to the exact candidate commit;
  a new commit invalidates it.

## 3. Single-use token rotation procedure (SF-5)

1. Owner verifies the launch candidate: attestation GO on a clean
   tree at the exact commit (`verify_cutover_readiness.py` offline,
   all V-gates green).
2. Owner issues the token via the Phase 19 control plane with the
   commit hash and scope `production-promotion` — the control-audit
   chain records issuance (never the token value itself).
3. The token is delivered out-of-band to the operator performing the
   cutover.
4. The D-139 activation machine consumes the token exactly once at
   the PROMOTE transition; replay, expiry, commit mismatch, or
   reuse are rejected deterministically (Phase 26 battery proves
   these properties).
5. Consumption is recorded in the control-audit chain. If the
   cutover aborts after consumption, a NEW token is required — the
   consumed token is never re-used.

## 4. Machine verification (`--stage-f`)

`verify_cutover_readiness.py --stage-f` reads
`docs/deployment/stage-f-authorization.md` and the runbook's
execution log and verifies checklist integrity, failing closed:

- **F-1** every SF-1..SF-7 row is present with owner role, evidence
  form, and binding declared (structural integrity of THIS file).
- **F-2** the runbook §6 checklist rows map 1:1 onto SF-1..SF-7
  (no authorization item may silently disappear between documents).
- **F-3** unsigned rows are reported by name — an empty execution
  log is the honest default (nothing has been signed) and yields
  findings, never a pass.
- **F-4** the planning shell contains no production secret material
  (same D-045 hygiene as the offline mode; a leak aborts with exit 2
  before any checklist evaluation).

Exit codes: 0 = gate satisfied (all rows signed and bound) ·
1 = findings (unsigned/missing rows — the expected state until the
owner signs) · 2 = cannot assess (D-045 leak or unreadable input).

**The gate is expected to report findings today**: no signature
exists because no cutover is authorized. Findings are the honest
state of an unexecuted gate; they convert to a pass only when the
owner completes §2.

## 5. Gate exit criteria

Stage F is complete when, at the moment of cutover:

1. `verify_cutover_readiness.py` (offline) reports zero findings on
   the candidate commit.
2. `--snapshot` mode passes (backup proof, D-125).
3. `--stage-f` reports zero findings (all seven rows signed and
   bound to the candidate).
4. The D-138 attestation (with the Stage E edge evidence folded into
   MON-001) is GO for the same commit.
5. The D-139 activation state machine accepts the preflight→
   dry-run→canary sequence — and PROMOTION still requires the
   owner's in-window approval (D-139: approval is never inferred
   from the absence of failures).

Any failure at any point ⇒ Stage E §5 rollback matrix governs; the
gate is re-entered from step 1 with fresh evidence.

## 6. References

- `docs/deployment/stage-e-cutover-runbook.md` §0/§1/§5/§6/§7
- `DECISIONS.md` D-137–D-140, D-139 (activation authority), D-141
  (adoption stages), D-045 (credential discipline)
- `docs/deployment/stage-g-acceptance.md` (post-cutover acceptance)
