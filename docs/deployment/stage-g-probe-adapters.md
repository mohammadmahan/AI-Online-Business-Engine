# Stage G — Production Probe Adapters & the Triple-Evidence Launch Gate (D-151)

**Status: IMPLEMENTED — nothing provisioned, nothing probed live.**
D-150 delivered the live probe *engine* (pure core, injected
executors). D-151 delivers the missing halves: the concrete
**production executor adapters** that run against the real Docker
host, and the **triple-evidence gate** that binds the three Stage G
digests into the launch attestation.

## 1. Why adapters are a separate layer

`verify_stage_g_live_probes.py` (D-150) performs zero I/O by design
(RULES §35): every capability arrives as an injected executor. The
battery pins the engine with fakes. Production execution needs the
opposite discipline — code that *does* touch the host, and therefore
must be the most constrained code in the repository:

- **Direct argv only.** Every child process is spawned from a fixed
  token list. Zero `shell=True`, zero string-concatenated command
  lines, zero unescaped interpolation. The only tokens that vary are
  allow-list validated first (service names against the D-149
  service set shape, ports as bounded digit strings, paths as
  absolute, `..`-free, bounded-length strings).
- **Strict timeouts.** Every `subprocess.run` carries a hard
  `timeout` (default `EXEC_TIMEOUT_S = 15` seconds). A hung child is
  killed by the subprocess machinery and surfaces as a fail-closed
  `AdapterError("timeout")` — a probe that hangs is a FAIL, never a
  wait (D-150 fail-closed precedent).
- **Fail-closed exit codes.** Nonzero exit, empty payload, malformed
  JSON, unknown service, malformed restart count — all failures.
  Nothing is guessed; nothing is skipped.
- **Deep redaction before return.** Every string leaving an adapter —
  including error text — passes `deep_redact` (D-124) first.
- **Sanitized errors.** Raised exceptions carry a failure KIND and
  bounded, redacted detail only. Raw stderr, connection strings,
  hosts, and credentials never ride along.

## 2. `local/scripts/stage_g_probe_adapters.py`

Three executors, satisfying the D-150 runner interface exactly
(`StageGLiveProbeRunner(clock, audit_sink, **build_executors())`):

### `DockerInspectExecutor` — GA-1 / GA-6

`docker inspect --format '{{json .}}' <service>` per service
(structured JSON argv; the service name is the only interpolated
slot and is allow-list validated):

- `container_status(services)` → `{svc: {healthy, restarts}}` —
  `healthy` = `State.Running` AND `Health.Status == "healthy"`
  (services without a healthcheck fall back to `Running`; the
  D-149 ACC-01 probe-parity contract requires core services to
  carry healthchecks); `restarts` = `RestartCount` (GA-1 judges
  the crash-loop ceiling ≤ 3).
- `published_ports(services)` → `{svc: [host_ip:host_port:container_port]}`
  — any host-side binding is reported raw; the GA-6 judge decides
  (zero published ports on all services).

### `ContainerExecExecutor` — GA-2..GA-5

Every command is `docker exec -i <service> <fixed argv…>` — the
child process is `docker` itself with tokenized arguments; no shell
on either side of the boundary.

| Probe | Inner command (fixed argv) | Result |
|---|---|---|
| GA-2 `pg_roundtrip` | `psql -v ON_ERROR_STOP=1 -X -q -A -t -U <user> -d <db> -c "<one roundtrip statement>"` | `True` iff the roundtrip row returns `1` |
| GA-3 `redis_ping` | `redis-cli -p <port> PING` and `redis-cli -p <port> CONFIG GET maxmemory-policy` | `{pong, auth_required, ttl_ok, exposed}` |
| GA-4 `app_loopback` | `wget -q -O - -T 10 http://127.0.0.1:<port>/healthz/worker` | `True` iff exit 0 and non-empty body |
| GA-5 `worker_heartbeat` | same wget, payload parsed as JSON | `{registered, age}` with age ∈ ℕ |

Broker semantics, stated exactly:

- `pong` — PING answered PONG inside the container.
- `auth_required` — the `requirepass` policy the owner declares at
  construction (a fixed constant sourced from the D-149-validated
  manifest). The adapter deliberately does NOT probe AUTH by issuing
  unauthenticated commands and reading the refusal — an
  unauthenticated command stream is exactly the traffic a hardened
  broker must refuse, and probing refusal semantics is not this
  adapter's job. D-150's judge treats `auth_required=False` as a
  GA-3 failure.
- `ttl_ok` — the runtime `maxmemory-policy` equals the declared
  policy (default `noeviction`): runtime and provisioning contract
  must agree.
- `exposed` — delegated to the inspect executor's port bindings; an
  externally bound broker is a hard refusal (D-150).

The GA-2 roundtrip is ONE statement (`DROP TABLE IF EXISTS … ;
CREATE … ; INSERT … ; SELECT … ; DROP …`) — atomic to the probe,
leaves nothing behind. PG identifiers (user, database) are
constructor-injected bounded identifiers, never free text.

### `LogStreamScrubberExecutor` — GA-7

`docker logs --tail <N> --stdout|--stderr <service>` per service
(fixed argv), sliced to `max_bytes` (default `LOG_SLICE_BYTES =
65_536`, hard ceiling 1 MiB), **deep-redacted before return**, with
the leak-detection discipline inherited from D-150: secret-shaped
RAW material is detected before redaction masks it, and a leak is a
GA-7 failure (the judge flips the probe and the run).

`build_executors()` wires all three into the D-150 runner kwargs in
one call.

## 3. `local/src/security/launch_attestation_verifier.py` — the triple-evidence gate

Stage G now produces three cryptographically bound digests:

| Artifact | Digest field | Producer |
|---|---|---|
| `cutover.bundle.v1` | `bundle_hash` | D-147 orchestrator |
| `stage_g_acceptance_report.v1` | `acceptance_fingerprint` | D-149 runner |
| `stage_g_live_probe_report.v1` | `probe_digest` | D-150 runner |

`TripleEvidenceGate.evaluate()` enforces **TRIAD-01..04**, all
fail-closed, every refusal naming its blocker:

- **TRIAD-01 hash integrity** — each digest recomputed from its
  artifact's canonical bytes (the exact `json.dumps(sort_keys=True,
  separators=(",", ":"))` SHA-256 formula every Stage G engine
  uses) matches the recorded value. A mismatch is TAMPER, never a
  warning.
- **TRIAD-02 correlation** — one deployment fingerprint across all
  three artifacts (bundle `candidate_manifest_sha256` == acceptance
  `manifest_sha256` == probe `manifest_sha256`), and the probe's
  `acceptance_fingerprint` equals the acceptance report's own
  fingerprint (the probes observed the deployment THIS acceptance
  cleared).
- **TRIAD-03 D-112 rooting** — each digest appears in the operator
  control-audit chain (row kind in `stage_g_preflight` /
  `cutover_bundle_recorded` / `stage_g_acceptance` /
  `stage_g_live_probe`, or the digest embedded in a row's detail),
  AND the chain verifies end-to-end via the injected
  `chain_verifier` (the `ControlPlaneEngine.verify_chain` shape).
  A broken chain attests nothing.
- **TRIAD-04 verdicts** — `READY_FOR_CUTOVER` → `ACCEPTED` →
  `PROBES_ACCEPTED`. A cleared-but-rejected history never
  justifies launch.

All providers are injected (`bundle`, `acceptance`, `probe`,
`audit_rows`, `chain_verifier`); the gate performs zero I/O and is
AST-pinned in the battery. Every check runs even after earlier
failures — one verdict names EVERY blocker.

### Integration into the launch attestation

- `triad_probe(gate)` wraps the gate as a `qa.health_report.v1`
  probe (`stage_g_triple_evidence`): `LAUNCH_READY` → PASS,
  `LAUNCH_BLOCKED` → **FAIL** (launch evidence is binary, never
  degraded — tamper-evidence precedent, D-123 `ledger_integrity`).
  Provider/evaluation errors are FAILs too.
- `wire_into_registry(registry, gate)` registers the probe on a
  `canonical.obs_health.ProbeRegistry`. Because the probe is
  mandatory, a registry wired through it cannot render a passing
  health report while the triad is incomplete — `overall` follows
  the FAIL, and the D-138 attestation hash binds the verdict to the
  exact evidence set.
- Production wiring: `bundle`/`acceptance`/`probe` load the three
  Stage G artifacts; `audit_rows` bridges to
  `default_vault().audit_rows()`; `chain_verifier` is
  `ControlPlaneEngine.verify_chain`. A chain the vault cannot read
  is an unreadable chain — FAIL.
- `launch_attestation.py` keeps its D-137/D-138 matrix composition
  (its `edge_report` parameter remains available for Stage E
  monitoring evidence); the triad gate rides inside the rendered
  `qa.health_report.v1` as a mandatory probe. Production activation
  itself remains exclusively owner-gated (D-139, plan §17/§21.6).

## 4. Safety boundaries & timeout parameters

| Boundary | Value / rule |
|---|---|
| Exec timeout | `EXEC_TIMEOUT_S = 15.0` s per child process |
| Log slice | `LOG_SLICE_BYTES = 65_536` bytes per stream (≤ 1 MiB) |
| Log tail | `tail_lines ≤ 10_000` |
| Service names | `^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$` + D-149 service set |
| Ports | digits only, `0 < port < 65536` |
| Heartbeat path | absolute, `..`-free, ≤ 200 chars |
| Shell | zero `shell=True`; inner container commands are fixed argv token lists |
| stdin | explicit `input_text` only; credentials never ride in argv or env |
| Error surface | exception TYPE + bounded, redacted detail (≤ 200 chars) |

## 5. Test surface (`test_stage_g_adapters_and_launch_attestation.py`)

- **ADAPTER** — mock docker-inspect JSON parsed without any shell;
  healthy stack produces the exact D-150 payload shapes.
- **FAILCLOSE** — nonzero exit, malformed JSON, invalid service
  names, timeout, and spawn failure all fail closed with sanitized
  `AdapterError` types; payload text never leaks.
- **TRIAD** — the gate passes when bundle, acceptance, and probe
  digests are valid, correlated, D-112-rooted, and verdict-chained;
  fails closed when any digest is absent, tampered, uncorrelated,
  unrooted, or the chain is broken.
- **REDACT** — canaries never escape any adapter surface.
- **AST** — zero `shell=True`, zero `os.system`/`popen`/`Popen`, one
  spawning seam, `timeout=` on every `subprocess.run` call, and
  zero I/O in the verifier's import surface.

Nothing here provisions, deploys, or activates anything: the
adapters read and probe; the gate judges. **D-139 remains the sole
activation authority.**
