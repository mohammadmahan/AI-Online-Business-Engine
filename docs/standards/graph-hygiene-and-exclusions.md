# Graph Hygiene & Exclusion Rules

- Authority: Phase 1–5 Graph Remediation Track (FreeBuf governance closeout)
- Traceability: Phase 1 (baseline drift), Phase 2 (test runtime leakage),
  Phase 3 (duplicate-named modules), Phase 4 (God-node coupling audit),
  D-027 (JSON event store), D-055 (PostgreSQL SSOT)
- Scope: graph-tooling exclusions and hub allowlisting **only**. This
  document changes no runtime logic, no test logic, and no canonical
  contract. It governs what the graph tool is allowed to index.

---

## 1. Tooling baseline (verified)

| Item | Value |
|---|---|
| Tool | `graphify` (`/Library/Frameworks/Python.framework/Versions/3.13/bin/graphify`) |
| Output dir | `graphify-out/` (`graph.json`, `GRAPH_REPORT.md`, `manifest.json`, `cache/`, `graph.html`) |
| Ignore file | `.graphifyignore` (repo root, gitignore syntax) |
| Secondary | `.gitignore` is also honoured (`--no-gitignore` exists to suppress it and prioritise `.graphifyignore`) |
| Semantics | patterns can only ever exclude MORE, never re-include |

Baseline observed **before** these rules: `manifest.json` indexed
`.claude/skills/ui-ux-pro-max/**`, producing **12,411** `ui-ux-pro-max`
occurrences inside `graph.json` and 25 vendored-file hits in
`GRAPH_REPORT.md`.

---

## 2. Exclusion rules

### R-1 — Vendored skill bundles: EXCLUDE
Pattern: `.claude/skills/**`

Justification (Phase 3, evidence-backed): `.claude/skills/` contains exactly
one tree, `ui-ux-pro-max`, which is an immutable vendored third-party pack
whose own doc (`docs/三个 data-scripts-templates 的区别.md`) states that
`src/ui-ux-pro-max/` is the *only* source of truth while `.claude/skills/`
and `cli/assets/` are **synced file copies** that must not be deleted and
must not be converted to symlinks. Every duplicate-name finding
(`core.py` ×7, `design_system.py` ×3, `validate_data.py` ×3) originates here.
No project module under `local/`, `canonical/`, `services/`, or `tests/`
imports any of them (verified: zero matches).

### R-2 — Generated graph output: EXCLUDE
Pattern: `graphify-out/`

Justification: regenerated artifacts, not a source of truth. Also added to
`.gitignore` (section *Local tooling state*) so the working tree reports
clean between runs — it was the sole `??` entry in Phases 1–4.

### R-3 — Local runtime volumes and logs: EXCLUDE
Patterns: `local/volumes/`, `local/local/`, `*.log`, `logs/`

Justification: mirrors the existing `.gitignore` intent — throwaway drill
and runtime state, never architectural evidence.

### R-4 — Dependency and build artifacts: EXCLUDE
Patterns: `node_modules/`, `__pycache__/`, `*.py[cod]`, `*.egg-info/`,
`.venv/`, `venv/`

Justification: third-party/compiled payloads that inflate fan-in counts and
cannot be acted upon.

### R-5 — OS / editor noise: EXCLUDE
Patterns: `.DS_Store`, `._*`, `.idea/`, `.vscode/`

---

## 3. Allowlist: legitimate fan-in backbone hubs

These are **not** violations. They MUST stay indexed and MUST NOT be
suppressed as "God Objects".

| Hub | Definition | Graph weight | Verdict |
|---|---|---|---|
| `EventStore` | `local/services/sync_engine.py:143` (134 L, 8 public methods) | 162 edges | Legitimate event-hub seam |
| `PgEventStore` | `local/canonical/notion_ingest.py:151` (517 L, 9 public methods) | 106 edges | Legitimate event-hub seam |

Phase 4 evidence for allowlisting:

1. **Dependency direction is one-way.** `notion_ingest` → `sync_engine`
   (single edge: `from services.sync_engine import IntegrityError`, line 72).
   `sync_engine` imports only `canonical.identifiers`, `canonical.prices`,
   `canonical.vocab` (leaf SSOT modules) and **never** `notion_ingest`.
2. **Zero circular dependencies**, re-verified at depth: `identifiers.py`,
   `prices.py`, `vocab.py` contain 0 references to `sync_engine`.
3. **Strict encapsulation.** No consumer outside `sync_engine.py` touches
   `.records` / `._store` / `._seq` (repo-wide grep = 0 hits).
4. **Dependency injection, not fabrication.** All engines receive the store
   (`oms_engine.py:255`, `admin_engine.py:407`, `analyst_engine.py:202`,
   `asset_engine.py:231`, `hitl_engine.py:469`, `notification_engine.py:182`,
   `orchestration_engine.py:141`, `scheduling_engine.py:179`) and
   `rebuild_state(store, page_id)` reconstructs from persisted events only.
5. **Contract is narrow** — an 8-method interface, so fan-in is a bounded
   seam rather than a blob. Public method parity between `EventStore` and
   `PgEventStore` is exact (verified by diff).

---

## 4. False-positive rules: docstring mentions and `[INFERRED]` edges

### R-6 — Docstring/comment mentions are NOT dependencies
A symbol appearing inside a docstring or comment must never be promoted to a
dependency edge. Known instance: `local/services/sync_engine.py:177` mentions
`canonical.notion_ingest.rebuild_state` in prose, which made
`git grep -l notion_ingest` list `services/sync_engine.py` and created a
phantom `sync_engine → notion_ingest` back-edge. Confirmed false: the only
non-stdlib imports in that file are `canonical.identifiers`,
`canonical.prices`, `canonical.vocab` (lines 35–51).

**Confirmation rule:** before any finding drives a code change, it must be
reproduced by an import/AST-level CLI check, not by an `[INFERRED]` edge
alone. Example of an INFERRED edge observed in `GRAPH_REPORT.md`:
`_count_succeeded() --uses--> EventStore  [INFERRED]`.

### R-7 — INFERRED edge classes already adjudicated as false positives
| Finding | Verdict | Proof |
|---|---|---|
| Test runtime leakage / cross-coupling among `test_phase20_security.py`, `test_stage_h_and_memwal.py`, `test_phase6_notion_m4_conformance.py` | INFERRED false positive | 73 tests, `OK (skipped=7)`, byte-identical in forward and reverse order; per-file isolated runs reconcile 5+0+2=7; `_m4*` fixture residue 0 before/after |
| `sync_engine ↔ notion_ingest` cycle | INFERRED false positive | docstring-only mention; one-way import only |
| Duplicate `core.py` / `design_system.py` / `validate_data.py` | INFERRED false positive (vendored) | byte-identical triplicates inside `.claude/skills/ui-ux-pro-max/`; documented upstream mirror layout; zero project importers |

---

## 5. Verification procedure (run before acting on any graph finding)

```bash
# 1. Is the node inside a vendored/generated tree? -> ignore it
graphify explain "<Symbol>"            # confirm neighbours + community
graphify path "<A>" "<B>" --directed   # prove/disprove a claimed coupling

# 2. Confirm the edge at source level (never trust [INFERRED] alone)
git grep -n "<symbol>" -- '*.py'       # check indentation: import vs docstring
git grep -ln "<module>" -- '*.py'      # true importer set

# 3. Regression gate (must stay green before/after any change)
python3 -m unittest local/tests/test_phase20_security.py \
  local/tests/test_stage_h_and_memwal.py \
  local/tests/test_phase6_notion_m4_conformance.py
# expected: Ran 73 tests — OK (skipped=7); the 7 skips are docker/Postgres env guards
```

Note: `pytest` is not installed on this machine; the sanctioned runner is
`python3 -m unittest` (all target modules are `unittest.TestCase` based).

---

## 6. Phase 1–5 evidence trail

| Phase | Finding | Verdict | Artifact / command |
|---|---|---|---|
| 1 | Baseline drift vs `913531ae` | Zero drift; HEAD identical; tree clean apart from untracked `graphify-out/` | `git rev-parse HEAD 913531ae`, `git status --porcelain`, `git log --oneline 913531ae..HEAD` |
| 2 | Test leakage / cross-coupling | INFERRED false positive; files untouched | bidirectional `python3 -m unittest` (73 OK, skipped=7) |
| 3 | Duplicate-named modules | Independent / vendored; untouched | `find`+`md5` (13 hits), `diff -q` silent, upstream bundle doc |
| 4 | God nodes `EventStore` / `PgEventStore` | Healthy one-way Event Sourcing hubs; zero cycles | method-parity diff, import-graph grep, encapsulation grep |
| 5 | Graph hygiene rules | R-1…R-7 established; exclusions + allowlist codified | `.graphifyignore`, `.gitignore`, this document |

---

## 7. Non-goals and fail-closed guarantees

- **Phases 1--4 remediation performed no commit and no push**: the drift,
  leakage, duplicate-module and God-node findings were all adjudicated
  without modifying a single tracked byte. The **Phase 5 closeout
  artifacts** (this document, `.graphifyignore`, and the `graphify-out/`
  exclusion in `.gitignore`) are delivered by the owner-authorized
  closeout commit `chore(graph): close 5-phase graph remediation and
  codify hygiene rules` — a **repository-hygiene commit only**. It is NOT
  a deploy and NOT a production authorization: D-139/D-045 stand unchanged
  (per `MASTER_PLAN.md` §11, a GitHub push is never production
  authorization).
- No core runtime logic, canonical contract, or test assertion was modified.
- No live database was touched (all Postgres classes remained skip-guarded).
- The vendored tree stays untouched: no deletion, no symlinks, no
  consolidation. Future propagation happens **only** via
  `npm run sync:assets` from `src/ui-ux-pro-max/` (single source of truth).
- Deferred (proposed, not executed) items, to be re-opened only if a real
  defect is proven: promote the 8-method store contract to a structural
  `typing.Protocol`; add a parity architecture test; internal decomposition
  of `PgEventStore` (517 L) / `SyncEngine` (531 L) preserving public API.
