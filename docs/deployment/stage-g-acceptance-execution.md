# Stage G — Acceptance Execution Specification (D-149)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **IMPLEMENTED (executor + battery) — nothing provisioned,
  nothing deployed.** The executor evaluates configuration readiness;
  the live GA-1..GA-7 deployment probes
  (`docs/deployment/stage-g-acceptance.md`) run against a real stack
  only after owner-gated provisioning.
- Predecessors: Stage G pre-flight contract (D-148), cutover
  orchestration wire (D-147), Stage F owner authorization (D-146),
  Stage D configuration engine (D-144), runtime preflight contract
  (`canonical/runtime_preflight.py`).
- Machine enforcement: `local/scripts/run_stage_g_acceptance.py` +
  `local/tests/test_stage_g_acceptance.py`.

## 1. Purpose and position in the chain

Stage G acceptance is the last configuration-readiness gate before
provisioning and the first artifact the owner's final activation
decision consumes. The chain is strict and ordered:

```
D-146 owner token → D-147 cutover bundle (READY)
  → D-148 pre-flight (PREFLIGHT_CLEARED, G-01..G-04)
    → D-149 acceptance (ACC-01..ACC-04, this executor)
      → owner-gated provisioning → live GA-1..GA-7 probes
```

Nothing downstream of a stage may run without that stage's positive,
unexpired, hash-bound verdict.

## 2. Entry gate (fail-closed)

The executor requires a `PREFLIGHT_CLEARED` verdict from the D-148
validator (injected provider). A `PREFLIGHT_BLOCKED`, malformed, or
absent verdict aborts the run immediately: a REJECTED report naming
the gate is emitted and audited, and **no ACC check is evaluated**.
The gate also binds the bundle: when the pre-flight cleared a specific
bundle hash and a bundle is supplied, the executor verifies the
pre-flight cleared THIS bundle — a mismatch is an immediate rejection.

## 3. Acceptance checks

### ACC-01 — Manifest conformance (structure + isolation + parity)

- Required service set present (`postgres-ssot`, `redis`,
  `app-orchestrator`, `telemetry-circuit`).
- Backend services declare zero `ports:` and never attach to `edge`;
  `app-orchestrator` is the sole edge attachment; `backend` network
  internal.
- Every service's healthcheck maps onto the D-145 probe-parity
  contract (`pg_isready` / PING-PONG / `/healthz/worker` /
  `/-/healthy`).
- Dependency graph: app depends only on backend services; no service
  depends on the edge service (edge-leaf, acyclic).
- No service drift from the bound template (every template service
  present in the manifest).

### ACC-02 — Environment schema (strict contract, D-124)

- Every `${VAR:?…}` reference maps onto the declared contract
  (`canonical.runtime_preflight.MANDATORY_KEYS` + the known Stage D
  image/secret names); an unknown variable is a schema violation.
- Strict interpolation only — loose forms (`$VAR`, `${VAR}`, `$(VAR)`)
  refused (comments exempt: documentation may cite the shapes).
- **No secret-shaped literal anywhere in the manifest** — values
  never enter Git, reports, or artifacts (D-124).

### ACC-03 — Hardening baseline (template parity)

- Every service: `mem_limit` + `cpus` ceilings, `restart:
  unless-stopped`, `no-new-privileges`.
- Read-only rootfs + tmpfs write seams pinned at template parity: the
  services whose shipped Stage D template block declares
  `read_only: true` (SSOT, broker) must retain it; app/telemetry
  images needing writable state paths are baseline-checked by
  parity, not blanket read-only.
- Volume mounts restricted to declared named volumes — host bind
  mounts refused.

### ACC-04 — Canonical report artifact

Emits `stage_g_acceptance_report.v1`:

| Field                 | Meaning                                        |
|-----------------------|------------------------------------------------|
| `schema`              | `stage_g_acceptance_report.v1`                 |
| `verdict`             | `ACCEPTED` / `REJECTED`                        |
| `manifest_sha256`     | exact manifest bytes evaluated                 |
| `template_sha256`     | bound template bytes                           |
| `bundle_sha256`       | the cleared cutover bundle ('' when none)      |
| `checks`              | per-ACC verdicts with secret-free details      |
| `observed_tick`       | injected logical clock                         |

plus the computed **SHA-256 acceptance fingerprint** over the
canonical report bytes — the join key the owner's final activation
decision references. Exactly one report is emitted and audited per
run (including aborts), to the injected D-121 audit sink.

## 4. Failure remediation matrix

| Finding                          | Remediation                                        |
|----------------------------------|----------------------------------------------------|
| PREFLIGHT gate not cleared       | complete D-148 G-01..G-04; never bypass            |
| Bundle mismatch at the gate      | re-run the D-147 pipeline; re-clear the new bundle |
| Backend service with `ports:`    | regenerate via the D-144 generator                 |
| Loose variable form              | regenerate; strict `${VAR:?…}` only                |
| Unknown env reference            | declare it in the contract or remove the reference |
| Secret-shaped literal            | replace with a strict ref; regenerate              |
| Missing ceilings/policy          | restore the template hardening block               |
| Non-declared volume mount        | use a named volume declared in the manifest        |
| Template drift (missing service) | regenerate the manifest from the bound template    |

After ANY remediation the manifest changes bytes → its fingerprint
changes → Stage E re-binding and a fresh pre-flight are required
before re-running acceptance (D-138 evidence-validity model).

## 5. Handoff to final owner activation

An `ACCEPTED` report is **necessary, never sufficient**:

1. The acceptance fingerprint is recorded in the D-112 control-audit
   chain next to the bundle hash (G-04 join).
2. Provisioning proceeds under the D-148 pre-flight authority; the
   live stack is then verified by GA-1..GA-7
   (`stage-g-acceptance.md`), requiring two consecutive green cycles.
3. Production activation itself remains exclusively owner-gated
   (D-139, plan §17/§21.6): the executor produces evidence — it never
   authorizes, provisions, or deploys.

## 6. Boundaries

Pure core: injected clock/audit/providers, zero sockets/subprocess/
direct file I/O (AST-pinned in the battery), deep-redacted details
(D-124). The executor performs no deployment side effects — it is a
verdict machine.
