# Phase 20 — Security Hardening & Threat Model (D-113–D-116)

- Status: **implemented (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), zero-skip testing; all controls
  local, deterministic, test-proven; no new external dependencies;
  no wall clock; D-045 re-verified.

## 1. Objective

Make the security posture explicit and test-backed: a threat
taxonomy mapped control-to-test across all prior phases, a uniform
input-hardening gate in front of contract layers, escalated ledger
and replay defenses, and a battery-executed repository sweep.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-113 | `ThreatModel`/`SecurityControl` registry: 6 threat categories mapped to controls + test artifacts — no control without a test | `security_contracts.py` |
| D-114 | `InputHardeningGate`: size/charset/shape/depth/width limits, duplicate-key + homoglyph rejection, NFC canonicalization | `security_engine.py` |
| D-115 | Chain-head attestations (O(1) tamper check) over Phase 18/19 chains; chain-anchored replay burns; deterministic rate limits + lockouts | `security_engine.py` |
| D-116 | Extended AST sweep (eval/exec, subprocess, pickle/marshal, network, random, bare except) + entropy secret scan, battery-executed | `security_worker.py` |

## 3. Threat → control → test mapping

| Threat | Phase surface | Control | Test artifact |
|---|---|---|---|
| Credential leakage | D-045 (all phases) | no-credential discipline + entropy scan | `test_d116_entropy_scan_clean`, battery AST audits |
| Replay attacks | Phase 19 confirmation keys | single-use per-VALUE burns, chain-anchored | `TestM4Live::test_live_*`, `test_replay_*` |
| Ledger tampering | Phases 18/19 chains | hash chains + chain-head attestations | `test_tamper_*`, `test_attestation_*` |
| Race-condition injection | Phases 12/15/17/18/19 | PK-as-lock exactly-once claims | per-phase 8-thread races |
| Oversized/malformed payloads | all contract layers | `InputHardeningGate` limits + canonicalization | `TestM2Gate::test_*` battery |
| Enumeration/probing via errors | error surfaces | uniform error taxonomy, no internals in messages | `test_error_surface_discipline` |

## 4. Architecture flow

```
caller payload ──► InputHardeningGate (D-114)
      size limits · charset/shape · JSON depth/width
      duplicate-key rejection · homoglyph rejection · NFC normalize
        ▼
semantic contract validators (Phases 9–19, unchanged semantics)
        ▼
engines (exactly-once locks, D-027 events)
        ▼
ledgers (18/19) ──► chain-head ATTESTATION (D-115): O(1) verify
rate limiter (D-115): budget counters, lockout after threshold
        ▼
security sweep (D-116): AST detectors + entropy scan — runs IN the battery
```

## 5. Security boundaries

- The gate is pure (no I/O); attestation and rate limiting live in
  the engine; the sweep reads the repository AST — no execution of
  scanned code.
- Deterministic: logical clock stamps only; no randomness in any
  control (the sweep flags `random` in canonical modules).
- D-045 re-verified: zero real credentials; entropy scan over the
  full repository is battery-asserted CLEAN.

## 6. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Threat taxonomy, control registry, hardening policies | done |
| M2 | InputHardeningGate, attestation vault, rate limiter, schema | done |
| M3 | Extended AST sweep, entropy scanner, cross-phase re-audit | done |
| M4 | Hardening battery incl. live-PG, full regression, docs | done |

## 7. Verification record (M4 closeout, 2026-09-17)

- Suite `local/tests/test_phase20_security.py`: **33/33 OK, zero
  skipped** — 28 offline (contract battery, gate, attestation v2,
  rate limiter/lockout, sweeps) + **5 live-PG E2E** (durable
  hardening-audit vault with re-report dedup, attestation tamper
  detection over the LIVE `admin.control_audit` table with
  byte-exact restore, HITL per-ticket ledger attestation ×3
  resolutions, deterministic 8-thread lockout race, 8-thread
  audit-record dedup race → exactly one durable row).
- Full regression battery: **702/702 OK, zero skipped**
  (includes 669 prior + 33 Phase 20); ladder 46/46 OK.
- Extended AST sweep (D-116): **0 findings** in canonical modules
  (0 network/AI-SDK imports, 0 dynamic exec, 0 unsafe
  deserialization, 0 randomness); 20 `subprocess` uses confirmed
  confined to test harnesses (established Node/psql tooling).
- Secret-entropy scan (D-045 re-verification): **0 flags** across
  92 files; bounds re-audit: **11/11 validator modules clean**.
- Live containers 5/5 healthy; `git diff --check` PASS.

### Re-audit gaps fixed in-batch (D-114)

1. **Six unbounded validator surfaces** (oms, analytics,
   scheduling, analyst, hitl, admin) — each now declares and
   enforces explicit bounds (was silent truncation or nothing).
2. **Attestation v1 could not detect interior mutation** — a
   vault edit of an interior row kept its stored `row_hash`, so a
   head-only/hash-only fold missed it. v2 folds the FULL ROW of
   every position (mutation/swap/truncate/append each detected;
   proven offline and on live PG).
3. **`security.hardening_audit` did not exist** — added to
   `local/db/schema.sql` (PK = attempt-unique record key, D-027
   dedup) with `_PgAuditVault` + `_JsonAuditVault` parity.
4. **M2 completion:** `HardeningEngine` facade added — durable,
   idempotent audit records and one-shot attest/verify over
   injected ledger providers (no cross-module imports).
5. **Detector false positives fixed in M3** (`re.compile` vs bare
   `compile`, entropy discrimination of UPPER_SNAKE identifiers,
   synthetic mock-token allowlist) — documented in §6.
6. **Layered-defense scope clarified (test-exposed):** module
   validators guarantee BOUNDS; control/confusable/charset
   rejection is the GATE's role at system entry points — asserted
   in both layers' tests.

### Standing owner gates

All controls are LOCAL and deterministic; no external security
providers, no auth backends, no network (D-045/D-116). Phase 20
passing does NOT prove compatibility with real WAFs, SIEMs, or
secret managers — those remain future owner-gated milestones.
