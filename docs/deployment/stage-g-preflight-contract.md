# Stage G — Provisioning Pre-Flight Contract (D-148)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **IMPLEMENTED (engine + battery) — nothing provisioned.**
  No Stage G provisioning command has been executed; every artifact
  here is a gate that must be passed, not evidence that anything has
  run. Execution remains owner-gated (D-139, plan §17/§21.6).
- Predecessors: Stage F owner authorization gate (D-146), cutover
  orchestration wire (D-147), D-112 control-audit chain, D-055
  PostgreSQL SSOT, D-138 evidence-validity model.
- Machine enforcement: `local/src/security/pg_replay_store.py`,
  `local/scripts/stage_g_preflight_validator.py`, and
  `local/tests/test_stage_g_preflight_and_pg_replay.py`.

## 1. Purpose

Stage G provisioning may not rest on memory-ephemeral state: a host
restart must not resurrect a spent authorization, and the actual
provisioning command must be bound — cryptographically — to the exact
attestation it executes. D-148 closes both gaps: a durable,
crash-resilient nonce burn on the SSOT, and a four-rule pre-flight
that joins the cutover bundle, the owner command, and the D-112 audit
chain before any container is created.

## 2. Durable replay store (`security.consumed_owner_nonces`)

### 2.1 Schema (idempotent DDL, applied on first use)

```sql
CREATE SCHEMA IF NOT EXISTS security;
CREATE TABLE IF NOT EXISTS security.consumed_owner_nonces (
    nonce_hash    text NOT NULL,   -- SHA-256 burn key (never the raw nonce)
    scope         text NOT NULL,   -- burn namespace, default stage-f-cutover
    token_id      text NOT NULL,   -- public commitment of the token
    session_id    text NOT NULL,
    target_env    text NOT NULL,
    logical_at    text NOT NULL,   -- injected logical tick
    burned_at_utc text NOT NULL,   -- injected UTC stamp (audit metadata)
    PRIMARY KEY (nonce_hash, scope)
);
```

### 2.2 Atomic consume

One statement adjudicates the race — no read-modify-write window:

```sql
INSERT INTO security.consumed_owner_nonces (...)
VALUES (...)
ON CONFLICT (nonce_hash, scope) DO NOTHING
RETURNING nonce_hash;
```

A returned row = first use (`consumed=True`); zero rows = replay
(`consumed=False`). Live-probe evidence: under a 6-thread same-key
race, exactly 1 winner and 5 losers. `consume()` raises
`ReplayStoreError` on any transport failure — **a lost DB is never an
approval** (fail-closed); the gate's caller surfaces it as a BLOCKED
verdict.

### 2.3 Wiring & redaction

- The engine performs no I/O: the transport is an injected
  `exec(sql) -> str` (production: `seed_registry.q` host-psql/
  container-psql with the D-126 concurrency ceiling; tests:
  in-process fake).
- `utc_stamp` is injected — the core reads no wall clock.
- Only the SHA-256 burn key and public commitments (token id,
  session, env) are stored; raw nonces, tokens, signatures, and keys
  never reach the table or any report (D-124).

## 3. Pre-flight rules (G-01..G-04)

| Rule | Check | Refusal when |
|------|-------|--------------|
| G-01 | Bundle is `cutover.bundle.v1` and `bundle_hash` equals the SHA-256 recomputed over its canonical bytes | missing/malformed hash, schema mismatch, any byte of the bundle tampered |
| G-02 | Verdict is strictly `READY_FOR_CUTOVER` and the bundle is unexpired (`now − observed_tick < MAX_BUNDLE_AGE_TICKS = 5000`) | BLOCKED bundle, malformed/future tick, expired attestation |
| G-03 | The owner deployment command carries the IDENTICAL `bundle_hash` as its explicit authorization token | command without a hash, malformed hash, hash of a DIFFERENT bundle |
| G-04 | The cutover decision is recorded in the D-112 control-audit chain (an audit row of kind `stage_g_preflight`/`cutover_bundle_recorded`, or any row whose detail embeds the bundle hash) | chain unreadable, no matching row — the decision is not durably attested |

Verdicts: `PREFLIGHT_CLEARED` only when all four pass; otherwise
`PREFLIGHT_BLOCKED` with the named failing rule ids. Reports carry
hashes, ids, rule ids, and tick numbers only (D-124).

## 4. Failure modes and their meaning

- **Bundle tampered (G-01):** someone edited the attestation after it
  was emitted. Refuse; re-run the D-147 pipeline to produce a fresh
  bundle.
- **Bundle expired (G-02):** the attestation is stale relative to the
  live state. Refuse; re-attest (D-138 evidence-validity model).
- **Command/bundle mismatch (G-03):** the owner approved a different
  cutover than the one being provisioned. Refuse — this is the exact
  confusion the hash binding exists to prevent.
- **No audit record (G-04):** the decision was never durably attested
  (or the chain is broken/unavailable). Refuse; record the decision
  through the D-112 engine first.
- **Replay store unavailable:** the Stage F gate itself must fail
  closed (D-146); provisioning cannot proceed on an unevaluatable
  authorization layer.

## 5. Operational runbook (owner-executed)

1. Complete the D-147 pipeline → obtain the READY bundle + `bundle_hash`.
2. Record the decision: append a D-112 control-audit row whose detail
   embeds the bundle hash (G-04's join key).
3. Compose the deployment command carrying the SAME hash, e.g.
   `dokploy deploy --bundle-hash <bundle_hash> …` — the hash IS the
   authorization token.
4. Run the pre-flight validator with the bundle artifact and the
   command hash; require `PREFLIGHT_CLEARED`.
5. Only then execute provisioning (Stage G acceptance per
   `docs/deployment/stage-g-acceptance.md` governs afterwards).
6. Any refusal: stop, remediate the named rule, re-run. A BLOCKED
   pre-flight never degrades to a warning.

## 6. Boundaries

The validator is composition-only (injected bundle/audit/clock
providers; AST-pinned no sockets/subprocess) and performs no
provisioning itself. Nothing in D-148 authorizes a real deployment;
D-139 remains the sole activation authority.
