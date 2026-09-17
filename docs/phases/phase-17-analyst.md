# Phase 17 — AI Business Analyst & Decision Engine (D-101–D-104)

- Status: **implemented (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  no external AI SDKs, no network calls, no credentials (D-045),
  no wall-clock reads (D-093/D-095/D-100 precedent), event-sourced
  audit with full rebuildability.

## 1. Objective

Turn the durable metrics of Phases 9–15 (publication outcomes,
order velocity, revenue, scheduling density) into deterministic,
provenance-tracked business insight — without ever letting the
analyst execute business-altering logic. The analyst OBSERVES and
PROPOSES; humans (or explicitly safe auto-accept rules for low-impact
insights) decide.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-101 | Canonical `BusinessInsight`/`Recommendation`, lifecycle GENERATED → EVALUATED → DISPATCHED_TO_HITL / AUTO_ACCEPTED / DISMISSED (+ SUPERSEDED), deterministic derivation | `analyst_contracts.py` |
| D-102 | `AnalystEngine`: strict evaluation/application separation, SHA-256 insight dedup, `analytics.business_insight` PG + JSON parity, Class-B pre-validation | `analyst_engine.py` |
| D-103 | `AnomalyScanner`: injected detectors over durable multi-phase metrics; breaches recorded as D-027 audit events only — never direct notifications | `analyst_worker.py` |
| D-104 | HITL boundary: HIGH/CRITICAL severity is structurally non-auto-acceptable; immutable decision ledger, rebuildable from durable events | `analyst_engine.py` / `analyst_worker.py` |

## 3. Architecture flow

```
durable metrics (Phases 9–15, via D-085 rollups / Phase 12 refs)
        │
        ▼
AnomalyScanner (analyst_worker)  ── injected detectors, injected now
        │  threshold breach
        ▼
insight proposal (pure evaluation — D-102 separation)
        │  validate: complete metric_refs, confidence ∈ [0,1]
        ▼
AnalystEngine.propose  ── dedup key = SHA-256(category, correlation_keys, window refs)
        │  unique (insight_key) in analytics.business_insight
        ▼
GENERATED event (D-027) → evaluate() → EVALUATED event
        │
        ├─ severity ∈ {HIGH, CRITICAL} or state-mutating payload
        │       → dispatch_to_hitl() → DISPATCHED_TO_HITL   (D-104)
        ├─ low impact + auto-accept-safe rule → AUTO_ACCEPTED
        └─ dismiss() → DISMISSED
any non-terminal insight ← supersede(later insight) → SUPERSEDED
```

- The HITL dispatch bridge emits a Phase 14 `NotificationEngine`
  contract event ONLY through the injected bridge seam — the analyst
  never imports the notification module (D-103 boundary, AST-verified).

## 4. Security boundaries

- Zero network imports; zero AI SDKs (no openai/anthropic/etc.);
  every "model" is an INJECTED deterministic evaluator function.
- Zero `os.environ` in canonical modules; zero wall-clock reads —
  scan/evaluation instants are injected parameters.
- No imports of notification/publishing/OMS/pricing modules from
  analyst modules (import-level boundary, battery-asserted).
- Class-B validation (missing metric context, confidence outside
  [0,1], empty correlation keys on bounded categories) BEFORE any
  durable write (D-102).
- Every durable string passes the store redaction discipline.

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Contracts: insight schema, lifecycle, confidence rules, derivation keys | done |
| M2 | Engine: vault (PG + JSON parity), dedup, evaluation/application split, schema | done |
| M3 | Worker: anomaly scanner, cross-domain correlator, HITL triage bridge | done |
| M4 | Suite incl. live-PG E2E, AST audit, full regression, docs | done |

## 6. Verification record (M4 closeout, 2026-09-17)

- Suite `local/tests/test_phase17_analyst.py`: **27/27 OK, zero
  skipped** (23 offline across M1–M3 + 4 live-PG E2E: real
  `PgEventStore` + real PG `analytics.business_insight` —
  propose/dedup/evaluate/dispatch, 8-thread identical-proposal
  single-creator race, full lifecycle + ledger parity with restart
  parity, live end-to-end scan with HITL dispatch).
- Full battery **623/623 OK, zero skips**; ladder 46/46 OK;
  containers 5/5 healthy (live layer ran, not skipped).
- AST audit **CLEAN** — 0 network imports, 0 AI SDKs (openai/
  anthropic/etc.), 0 domain-module imports from the analyst modules
  (no notification/publishing/analytics/OMS/scheduling/assets
  imports: the metric frame is plain data and every side effect —
  evaluation, HITL dispatch — is an INJECTED callable, D-103
  boundary import-verified), 0 `os.environ`, 0 `time`/`datetime`
  imports in canonical modules (zero wall-clock, D-101).
  Secret scan CLEAN; `git diff --check` PASS.
- Durable state after the run: 11 insight rows on live PG, 9 in
  DISPATCHED_TO_HITL awaiting the owner (the D-104 queue doing its
  job).

### Defects exposed and fixed in-batch

1. **Worker (D-102 dedup violation, test-exposed):** the anomaly
   window_ref embedded the injected scan instant, so re-scanning the
   same evidence at a different instant produced a NEW insight key
   instead of deduplicating. The key now derives from the detector
   + evidence digest only; the scan instant is payload metadata.
2. **Worker (determinism):** insight ids used builtin `hash()` —
   process-randomized across runs. Replaced with a SHA-256 evidence
   digest (D-101 reproducibility).
3. **Worker (metric semantics):** the cancellation-rate detector
   divided cancelled by (placed + cancelled) instead of cancelled /
   placed — the base is placed orders, not all events.
4. **Worker (Class-B completeness):** `build_frame` accepted rollup
   cells missing `value`; incomplete metric context now rejected
   before any processing (D-102).
5. **Contracts (state-machine gap, diag-exposed):** DISPATCHED_TO_HITL
   was fully terminal, making SUPERSEDED unreachable for insights
   waiting for human review — contradicts D-101 ("SUPERSEDED from
   any non-terminal state"). SUPERSEDED is now legal from
   DISPATCHED_TO_HITL; edge matrix 7 legal / 6 illegal, tested.
6. **Engine (D-027 conflicting duplicates):** the dedup audit ref
   embedded the caller's incidental insight_id, so identical
   evidence re-derived under a different label produced a
   conflicting duplicate IntegrityError. The dedup audit is now a
   function of evidence (the insight_key) only, and DUPLICATE
   results surface the ORIGINAL durable insight_id.
7. **Test premises:** live fixtures were not run-scoped at the
   EVIDENCE level (only insight_id), colliding with prior runs'
   rows on the shared durable table — correlation keys are now
   run-scoped (Phase 13–16 precedent); the supersede test assumed
   confidence/insight_id are key material (they are not, by design)
   and now varies the evidence window; the `_stack_up()` guard
   queried a nonexistent compose service name — mirrored from the
   proven Phase 16 guard.
