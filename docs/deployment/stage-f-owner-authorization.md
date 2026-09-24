# Stage F — Owner Authorization & Context-Bound Approval Tokens (D-146)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **IMPLEMENTED (engine + battery) — nothing authorized,
  nothing deployed.** No production cutover token has been minted or
  consumed; real activation remains owner-gated (D-139, plan
  §17/§21.6).
- Predecessors: Stage D configuration engine (D-144), Stage E cutover
  verification matrix V-01..V-09 (D-145), canonical approval-token
  lineage (`canonical/launch_activation.py` D-139 semantics, Phase 19
  one-time burn pattern).
- Machine enforcement: `local/src/security/owner_approval_gate.py` +
  `local/tests/test_owner_approval_gate.py`.

## 1. Purpose

Stage E proves the deployment is *technically* ready. Stage F is the
human half of the gate: the final cutover switch may be armed only
when the OWNER has explicitly authorized THIS cutover — for THIS
manifest fingerprint, THIS session, THIS target environment — with a
single-use, time-bounded, cryptographically verifiable token. Absence
of a token, an unreadable token, or an unevaluatable gate is always
NO_GO. Never a pass.

## 2. Token model

### 2.1 Binding payload

Every token commits (HMAC-SHA256, canonical JSON, sorted keys) to:

| Field              | Meaning                                        | Bound to                                    |
|--------------------|------------------------------------------------|---------------------------------------------|
| `manifest_sha256`  | exact Stage D manifest fingerprint             | `stage_d_fingerprint.envelope` (D-144/145)  |
| `session_id`       | cutover session identifier                     | orchestrator-issued run context             |
| `target_env`       | deployment target (`staging`, `production`, …) | environment separation (plan §6)            |
| `issued_tick`      | logical issuance tick                          | injected logical clock (no wall clock)      |
| `expires_tick`     | hard expiry tick                               | TTL window [1, 10000] ticks                 |
| `nonce`            | owner-chosen one-time value                    | replay burn key                             |

### 2.2 Wire format

```
<token_id>.<hex hmac-sha256 signature>
token_id = sha256(canonical binding)[:16]   # commitment, not secret
```

The token id is a **commitment**: the verifier recomputes it from the
presented draft/context and compares in constant time before touching
the signature. A token cannot be transplanted between sessions,
environments, or manifests without failing `unknown_binding` or
`fingerprint_mismatch`.

### 2.3 Key handling (D-124)

The signing key is owner-held secret material:

- It is injected into the gate constructor from the secret store
  (production) or memory (tests). It is **never** embedded in tokens,
  reports, errors, logs, or artifacts.
- Reports carry the token **id** (a hash commitment), verdict words,
  and hashes — never the key, never the signature.
- All report text and detail fields pass `deep_redact` before leaving
  the engine, and the serialized report itself is re-redacted as a
  belt-and-braces measure.

## 3. Lifecycle

```
 OWNER (offline)                     ORCHESTRATOR (deployment side)
 ─────────────────                   ──────────────────────────────
 1. read envelope → fingerprint
 2. compose TokenDraft
    (fingerprint, session, env,
     issued, expires, nonce)
 3. mint_token(key, draft)
    → "<id>.<sig>"
 4. hand <token> + <draft> to the
    orchestrator over the APPROVED
    approval channel (never a
    public channel, never Git)
                                     5. OwnerApprovalGate.evaluate(
                                          token, draft, session,
                                          env, envelope_text)
                                     6. outcome GO → arm cutover
                                        (still logged + reversible
                                        per D-139); NO_GO → blocked,
                                        findings audited
                                     7. nonce burned exactly once
                                        (replay store; durable)
```

Rules:

- The draft rides WITH the token; the gate refuses when the draft
  does not describe the current session/target, when the draft's
  fingerprint differs from the current envelope, or when the token id
  does not commit to the presented material.
- Expiry is judged against the **injected logical clock** only.
- Consumption is single-use: the burn key
  `sha256({burn, token_id, nonce})` goes through the injected replay
  store (`consume(key) -> bool`); `False` ⇒ `replay_rejected`.
- Every evaluation — GO or NO_GO — emits one redacted report to the
  injected audit sink (D-121 `engine.log.v1` in production). A sink
  failure raises; the gate never evaluates quietly.

## 4. Rejection taxonomy (fail-closed, stable order)

| Reason                 | Trigger                                                     |
|------------------------|-------------------------------------------------------------|
| `malformed_token`      | not `<id>.<sig>` shape / empty components                    |
| `malformed_context`    | session/env shape invalid                                    |
| `malformed_draft`      | draft missing or wrong type                                  |
| `context_mismatch`     | draft describes a different session/target                   |
| `envelope_invalid`     | envelope missing/malformed/not bound for stage-e-cutover     |
| `fingerprint_drift`    | envelope fingerprint ≠ gate-bound fingerprint                |
| `fingerprint_mismatch` | draft minted for a different manifest                        |
| `unknown_binding`      | token id does not commit to presented material               |
| `signature_invalid`    | HMAC mismatch (constant-time compare)                        |
| `ttl_malformed`        | non-integer ticks                                            |
| `ttl_window_invalid`   | window outside [1, 10000] ticks                              |
| `token_expired`        | now ≥ expires (injected clock)                               |
| `token_not_yet_valid`  | now < issued                                                 |
| `nonce_malformed`      | nonce shape invalid                                          |
| `replay_rejected`      | burn key already consumed                                    |

Any unlisted failure mode also refuses (the default is NO_GO).

## 5. Emergency halt & revocation

- **Revocation by supersession:** the gate binds to the envelope
  fingerprint. Regenerating the Stage D manifest (any byte) invalidates
  every outstanding token — they must be re-minted for the new
  fingerprint after re-review.
- **Revocation by session:** tokens are session-bound; declaring a new
  session id invalidates outstanding tokens for the old one.
- **Break-glass / kill-switch:** the canonical D-139 kill switch
  (`ActivationMachine`, `KillSwitch`) remains the runtime halt path and
  is unaffected; Stage F tokens authorize ARMING the switch, not
  overriding a trip.
- **Auditability:** all outcomes (including refusals and replays) are
  auditable events; replay attempts are themselves security-relevant
  findings.

## 6. Evidence validity

A Stage F GO is valid for exactly ONE consumption within its TTL
window against the exact fingerprint/session/env it commits to. Any
of the following voids it: manifest regeneration, session change,
environment change, expiry, prior consumption, or gate re-binding to a
different fingerprint. Evidence references for the launch pack record
the token id and verdict — never key or signature material.

## 7. Boundaries

The engine performs no network I/O, no subprocess calls, no direct
file access, and reads no wall clock — all world effects arrive via
injected collaborators (RULES §35). The battery pins these boundaries
with an AST audit. Owner authorization via this gate remains **one
necessary input** to activation; D-139 approval semantics and plan
§17/§21.6 owner sign-offs continue to govern the actual cutover.
