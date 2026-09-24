# Stage E — Cutover Verification Matrix & Manifest Fingerprint Binding (D-145)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **SPECIFICATION + wired enforcement** in
  `local/scripts/verify_cutover_readiness.py` (V-01..V-09). Cutover
  itself remains **owner-gated** (D-139, plan §17/§21.6) — a green
  matrix is necessary, never sufficient.
- Predecessors: `stage-d-compose-architecture.md` (D-144 generator),
  `stage-e-cutover-runbook.md` (RB matrix, header policy),
  `stage-f-authorization.md` (SF gate), D-138 attestation.

## 1. Purpose

Define the complete pre-cutover verification matrix and make the
Stage D manifest **cryptographically bound** to the cutover decision:
the exact bytes cleared for cutover are pinned by a SHA-256 fingerprint
envelope; any drift re-opens the gate.

## 2. The Cutover Verification Matrix (V-01..V-09)

| Check | Subject | Source of truth | Failure semantics |
|---|---|---|---|
| V-01 | D-138 attestation is GO for the candidate | launch evaluator (commit-bound) | FAIL on missing/stale/dirty — never assumed |
| V-02 | No production secrets in the planning shell | live env scan (D-045) | exit 2, refuses to evaluate at all |
| V-03 | Prod `${VAR:?}` contract documented in `.env.example` | manifest parse | FAIL naming missing keys |
| V-04 | Restart policy + cpu/mem ceilings on all services | manifest parse | FAIL naming deficient services |
| V-05 | `runtime_preflight` refuses incomplete, admits complete | fail-closed proof (synthetic values) | FAIL if either direction breaks |
| V-06 | Rollback matrix RB-1..RB-6 + stop→compensate→reconcile | runbook §5 | FAIL naming missing rows |
| V-07 | Edge header policy (HSTS/nosniff/frame-deny/CSP/HTTPS) | runbook §4 | FAIL naming missing headers |
| **V-08** | **Stage D manifest fingerprint + isolation** | **`stage_d_fingerprint.envelope` vs generated manifest bytes** | FAIL on NO_MANIFEST / NO_ENVELOPE / MISMATCH / MALFORMED, or any isolation violation |
| **V-09** | **Health-probe contract parity** | **container healthchecks vs `infra_health_probe.py` semantics** | FAIL for any declared service whose check is absent or off-contract |

Exit codes: `0` ready · `1` findings (fail closed) · `2` cannot assess.

## 3. V-08 — Manifest immutability by fingerprint

1. **Generation (Stage D):** `stage_d_compose_generator.py` renders
   `docker-compose.dokploy.yaml` deterministically — identical inputs
   yield identical bytes, so the hash is a function of the declared
   configuration, not of the machine.
2. **Binding:** the operator records
   `manifest_sha256: <64-hex>` in `stage_d_fingerprint.envelope` at
   the moment the manifest is reviewed and accepted. The envelope
   carries hashes only — never secret values (D-124).
3. **Verification (V-08):** the harness recomputes the SHA-256 of the
   on-disk manifest and compares. Verdicts: `VERIFY` · `NO_MANIFEST`
   · `NO_ENVELOPE` · `MISMATCH` · `MALFORMED` — everything except
   `VERIFY` blocks cutover.
4. **Invalidation:** editing the manifest (even one byte), changing
   the template or generator, or re-generating with different image
   pins changes the hash ⇒ `MISMATCH` ⇒ the previous clearance is
   void and the manifest must be re-reviewed and re-bound. This is
   the D-138 evidence-validity model applied at the manifest layer.
5. **Isolation half:** the same check re-asserts the D-144 network
   contract on the bound bytes — zero `ports:` on
   postgres/redis/telemetry, backend-only attachment, the
   app-orchestrator the sole `edge` surface, strict `${VAR:?…}`
   references only (no loose `$VAR` forms).

## 4. V-09 — Probe contract parity

The deployment gate can only clear containers it can verify. Each
generated service's healthcheck must map onto an
`infra_health_probe.py` semantic:

| Service | Required healthcheck shape | Probe equivalent |
|---|---|---|
| postgres-ssot | `pg_isready` | `pg_ssot` (SELECT-1 readiness) |
| redis | `ping … PONG` (with AUTH) | `redis_broker` |
| app-orchestrator | `GET /healthz/worker` | `worker_heartbeat` |
| telemetry-circuit | `GET /-/healthy` | `telemetry_circuit` (not latched OPEN) |

A declared service without a healthcheck, or with a check that does
not map onto the contract, is **unverifiable ⇒ fail closed** — the
same rule the probe applies to unwired verifiers.

## 5. Fingerprint as prerequisite for the owner-gated switch

The launch switch (D-139 promotion) consumes this matrix as follows:

1. All of V-01..V-09 green — including the V-08 `VERIFY` verdict on
   the exact manifest bytes — is the *technical* cutover clearance
   (offline mode exit 0).
2. The Stage F authorization gate (`--stage-f`) independently requires
   the seven owner sign-offs; unsigned rows block regardless of the
   technical matrix.
3. At cutover time the operator re-runs offline mode: if the manifest
   changed after binding, V-08 fails and the switch cannot proceed —
   the fingerprint makes "reviewed ≠ deployed" drift structurally
   impossible to miss.
4. The edge probe (`--edge`) and snapshot proof (`--snapshot`) remain
   separate opt-in modes; they add evidence, never bypass V-08/V-09.

## 6. Redaction (D-124)

Findings carry hashes (16-char prefixes), service names, check names,
and masked keys — never secret values, never manifest content. The
envelope file itself contains no secret material by construction.

## 7. Unresolved owner decisions

- When to re-bind after an intentional manifest change (owner reviews
  the diff, then re-binds — procedure, not automation).
- Whether the envelope should additionally record the template hash
  (currently the generator+template are covered transitively by the
  deterministic render).
- Cutover timing and maintenance window — Stage F territory.
