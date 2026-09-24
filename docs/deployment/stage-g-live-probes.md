# Stage G — Live Probe Verification Engine (D-150)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **IMPLEMENTED (engine + battery) — nothing provisioned,
  nothing deployed.** The engine is a verdict machine over injected
  executors; no real container has ever been probed with it.
- Predecessors: Stage G acceptance executor (D-149), pre-flight
  contract (D-148), `stage-g-acceptance.md` (the full GA-1..GA-7
  deployment-probe definitions), `infra_health_probe.py` (the probe
  semantics and fail-closed precedent).
- Machine enforcement: `local/scripts/verify_stage_g_live_probes.py` +
  `local/tests/test_stage_g_live_probes.py`.

## 1. Position in the chain

```
D-149 acceptance (ACCEPTED, fingerprint)
  → D-150 live probes (this engine, GA-1..GA-7)
    → probe digest joins the D-112 audit chain
      → final owner activation (D-139, plan §17/§21.6)
```

The engine verifies the RUNTIME surface after provisioning; it grants
nothing by itself and never touches the activation decision.

## 2. Entry gate (fail-closed)

A valid `stage_g_acceptance_report.v1` (D-149) is mandatory:

| Condition                                              | Outcome                          |
|--------------------------------------------------------|----------------------------------|
| Report missing / not an object                          | abort, no probe executes         |
| `schema` != `stage_g_acceptance_report.v1`              | abort                            |
| `verdict` != `ACCEPTED`                                 | abort (provisioning never cleared) |
| `manifest_sha256` malformed or ≠ the deployment probed  | abort (wrong deployment)         |
| `acceptance_fingerprint` ≠ recomputed canonical hash    | abort (TAMPERED acceptance)      |

Every abort emits an audited REJECTED report naming the gate — an
aborted run is never silent.

## 3. Injected executor interface (RULES §35)

The core performs zero I/O. Each probe binds one injected executor to
one pure judge; an ABSENT executor is a probe FAIL (never skipped —
the `infra_health_probe` fail-closed precedent):

| Executor            | Signature                | Judges                      |
|---------------------|--------------------------|-----------------------------|
| `container_status`  | `() -> {svc: {healthy: bool, restarts: int}}` | GA-1 |
| `pg_roundtrip`      | `() -> bool`             | GA-2                        |
| `redis_ping`        | `() -> {pong, auth_required, ttl_ok, exposed}` | GA-3 |
| `app_loopback`      | `() -> bool`             | GA-4                        |
| `worker_heartbeat`  | `() -> {registered, age}`| GA-5                        |
| `published_ports`   | `() -> {svc: [ports]}`   | GA-6                        |
| `output_streams`    | `() -> {stdout, stderr}` | GA-7                        |

In production the executors wrap `docker inspect`/`psql`/`redis-cli`
in the deployment layer; in the battery they are in-process fakes.
Transport exceptions surface as FAIL with the exception TYPE only
(payloads never survive the boundary — D-124).

## 4. Probe mechanics

- **GA-1 container lifecycle:** every core service reports
  `healthy: true` with restarts ≤ 3 (a higher count is a crash loop).
- **GA-2 SSOT integrity:** a read/write transaction roundtrip answers
  `True` on the internal network; connectivity alone is not enough.
- **GA-3 broker integrity:** `PONG` with auth enforced, TTL/eviction
  policy confirmed, and NOT externally exposed — an exposed broker is
  a hard refusal.
- **GA-4 application IPC:** the core loopback endpoint answers.
- **GA-5 worker liveness:** registered with a heartbeat fresher than
  120 ticks (older = stale, fail-closed).
- **GA-6 network boundary:** zero published ports on ALL services
  (the edge terminates at the gateway; a published port on any
  service breaches the isolation contract).
- **GA-7 redaction/log leakage:** no tokens, credentials, or keys in
  the captured stdout/stderr streams; every probe detail is also
  passed through `deep_redact` — secret-shaped material in ANY detail
  flips that probe (and the run) to FAIL.

## 5. Timeouts, retries, and determinism

- Executors are the timeout boundary: the core judges outcomes, never
  waits. A production wrapper applies the plan's probe timeouts
  (healthcheck interval/timeout/retries mirror the manifest) and
  returns a transport error on expiry — the core renders it as FAIL
  (`transport failure: <type>`), never as a retry loop.
- No retry inside the engine: a flaky pass is not acceptance (the
  stage-g-acceptance two-cycle discipline applies to the caller).
- The injected logical clock stamps the report; no wall clock exists
  in the core.

## 6. The canonical artifact

`stage_g_live_probe_report.v1`:

| Field                     | Meaning                                    |
|---------------------------|--------------------------------------------|
| `schema`                  | `stage_g_live_probe_report.v1`             |
| `verdict`                 | `PROBES_ACCEPTED` / `PROBES_REJECTED`      |
| `manifest_sha256`         | the deployment fingerprint probed          |
| `acceptance_fingerprint`  | the D-149 clearance binding                |
| `probes`                  | GA-1..GA-7 verdicts with redacted details  |
| `observed_tick`           | injected logical clock                     |
| `probe_digest` (property) | SHA-256 over the canonical report bytes    |

Exactly one report is emitted and audited per run (including aborts).
`PROBES_ACCEPTED` requires every probe to pass — unknown is failure
(D-137 fail-closed precedent).

## 7. Audit handoff

The probe digest is recorded in the D-112 control-audit chain next to
the acceptance fingerprint and bundle hash (the three-way join key:
what was cleared → what was accepted → what was observed live).
REJECTED reports feed the Stage E §5 rollback matrix. Production
activation remains exclusively owner-gated (D-139, plan §17/§21.6);
this engine produces evidence, never authorization.
