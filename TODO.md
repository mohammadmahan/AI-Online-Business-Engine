# TODO

Living task list for the AI-First Online Business Engine.

- Conventions: `[ ]` open, `[x]` done. Completed items stay until the
  phase closes.
- Required reading before work: `MASTER_PLAN.md`, `PROJECT_RULES.md`,
  relevant docs, then this file (`PROJECT_RULES.md` §2).

---

## Phase 1 — Project Architecture (closed)

Status: **Complete** (foundation committed in `e6d85ca`); scope in
`docs/phases/phase-01-project-architecture.md`

- [x] Validate planning documents (`MASTER_PLAN.md`, `PROJECT_RULES.md`)
- [x] Create `README.md`
- [x] Create `ARCHITECTURE.md`
- [x] Create `DATA_MODEL.md`
- [x] Create `SECURITY.md`
- [x] Create `DECISIONS.md`
- [x] Create `TODO.md`
- [x] Create `docs/` structure (`docs/README.md`, `docs/glossary.md`,
      `docs/phases/phase-01-project-architecture.md`)
- [x] SKU strategy review → recorded as **D-014 (Approved)** in
      `DECISIONS.md`; final convention approved by the human owner
      (see D-014 / D-015)
- [x] Self-review pass: valid Markdown, no secrets, cross-references
      valid, Definition of Done checked per file
- [x] Commit the foundation (explicit human approval; commit `e6d85ca`)

## Phase 2 — Product Data System (current)

Scope from MASTER_PLAN §13: product/variant model, SKU, taxonomy,
media, validation, import/export, Excel import preparation. Decisions
D-014 (SKU convention), D-015 (identifier separation), D-017
(identifier policy), D-018 (variant-defining attributes), D-019
(vocabulary governance), D-020 (size-system architecture), D-021
(required-field policy), D-022 (product status state machine),
D-023 (publication status state machine), D-024 (price model), D-025
(discount model), D-026 (provenance mechanism), D-027 (event-level
idempotency), D-028 (Excel import contract), D-029 (registry v1
structure), and D-030 (size-code governance) are **Approved**; the
remaining Phase 2 open items include registry v1 concrete values
(D-016.C), concrete size-code mappings (D-020/D-030), and SEO slug
language (D-016.M).

Ordered tasks (tasks 1–10 resolved via D-017–D-021, D-022/D-023,
D-024–D-027, and D-028–D-030 — do not treat
other items as done until verified):

- [x] ~~SKU strategy~~ — resolved: D-014 **Approved** (2026-09-11)
- [x] 1. Finalize Product/Variant identifier policy — **D-017
       Approved** (2026-09-11): Product ID = product code (`P00001`…),
       Variant ID = opaque UUIDv4, AI never issues identifiers;
       event-level idempotency still open (D-016.K)
- [x] 2. Finalize variant-defining attributes — **D-018 Approved**
       (2026-09-11): exactly {Color, Size}, per-axis applicability,
       SKU suffix = active axes (Color, then Size)
- [x] 3. Finalize minimum required product fields — **D-021 Approved**
       (2026-09-11): minimal creation minimums, publication minimum,
       verified-data-only inventory, bounded AI enrichment
- [x] 4. Design controlled-vocabulary registry v1 — governance
       **D-019 Approved**; v1 structure **D-029 Approved** (required:
       color, size, category); concrete registry v1 values remain OPEN
       and owner-supplied
- [x] 5. Resolve size system — architecture **D-020 Approved**
       (multi-family); size-code governance **D-030 Approved**
       (O/I/L-safe); concrete size-code mappings remain an explicit
       OPEN owner sub-decision
- [x] 6. Define product/publication status state machines —
       **D-022 / D-023 Approved** (2026-09-12): product lifecycle
       `draft`/`active`/`archived`; publication `unpublished`/
       `in_review`/`published`/`withdrawn`; publication transitions are
       Red-tier (human approval); AI may suggest, never execute
- [x] 7. Define price/discount model — **D-024 / D-025 Approved**
       (2026-09-12): three-field minimal price model (list price,
       variant override, optional sale price with explicit validity);
       sale-price-only discounts, no discount engine; AI suggests
       only, Red tier applies to production changes
- [x] 8. Define provenance mechanism — **D-026 Approved**
       (2026-09-12): per-value provenance tuple (source, actor,
       timestamp, review state, optional source ref + raw value),
       immutable/append-only; five source types; provenance ≠ audit log
- [x] 9. Define import idempotency policy — **D-027 Approved**
       (2026-09-12): event-level idempotency via (source system, event
       ID) unique key with terminal processing states; safe retries;
       distinct from identifier-based idempotency (D-017)
- [x] 10. Decide Excel import scope — **D-028 Approved**
       (2026-09-12): input-only contract over semantic fields (the
       physical sheet/column mapping is confirmed at the specification
       task); dry-run first; human-approved exceptions; Excel never
       issues IDs/SKUs and never writes inventory
- [x] 11. Consolidate the logical data model — **done (2026-09-12)**:
       `DATA_MODEL.md` §13 consolidates D-014–D-030 into one
       implementation-ready logical model (entity catalog,
       relationships, identity, missing-value semantics, import/
       idempotency, provenance, authority matrix, deferred boundary);
       no new business rules
- [x] 12. Produce Excel import specification — **done (2026-09-12)**:
       semantic import contract + validation pipeline + error classes
       + dry-run/partial-failure/re-import rules in the phase-02
       document; physical sheet/column mapping remains an **open
       dependency** pending the owner's workbook (not in the repo —
       not invented)
- [x] 13. Perform Phase 2 final review — **done (2026-09-12)**: full
       D-014–D-030 audit passed; no contradictions; open gates
       preserved (see the phase-02 review section)
- [ ] 14. Commit Phase 2 foundation only after human approval

Standing constraints (always apply):

- No API keys or credentials in the repository, ever.
- No production infrastructure.
- SKU convention is approved (D-014); SKU issuance remains human/approved
  tooling only — AI never assigns or invents a SKU.
- No major architectural decisions outside `DECISIONS.md` (STOP →
  EXPLAIN → APPROVAL).

## Phase 2.5 — Business Data Configuration (current)

Owner-approved configuration on top of the closed Phase 2 decision
set (specification/configuration only — no implementation). Scope and
values in `docs/phases/phase-02-5-business-data-configuration.md`.

- [x] Batch 1 — Register approved store structure **(2026-09-12,
      owner-approved; recorded in the Phase 2.5 document)**:
      category structure (2 primaries + 12 women's + 8 men's
      subcategories; category NOT variant-defining); Registry v1 =
      exactly {color, size, category}; 25 owner-approved color terms
      (Persian display values; no aliases invented; no SKU codes
      assigned); approved size families Alpha/8 · Numeric/11 ·
      Pants Waist/9 (shoe excluded; no code mappings; no equivalence
      links); approved product-attribute list (8 general + 5
      garment-specific; Color/Size remain the only variant-defining
      axes); seller-enters-readable-values principle; AI authority
      unchanged. Recorded as owner-approved configuration, not
      AI-generated defaults.
- [x] Batch 2 — Color & size code governance **(2026-09-12,
      owner-approved; recorded as decision D-032 + the Phase 2.5
      document)**: 25 owner-approved color codes (BK, WHT, GRY, …,
      CAM — the owner corrected the initial BLK/BLU/YLW to the
      O/I/L-safe BK/BU/YW; D-014 rule 7 and D-030 remain fully
      intact, no exception); size codes family-scoped — Alpha
      XS→XS · S→S · M→M · L→LG · XL→XG · XXL→XXG · 3XL→3XG ·
      4XL→4XG (separate O/I/L-safe codes; display labels remain
      L/XL per D-020 rule 4), Numeric 34→34 … 54→54 and Pants Waist
      28→28 … 44→44 (canonical value = code); no aliases created,
      no equivalence links, no runtime SKU generation; AI may
      validate but never assign codes. *(Historical note: the Alpha-L
      code `LG` later conflicted with D-030; resolved 2026-09-13 by
      owner decision **D-057** — the canonical code is now `LRG`,
      no D-030 exception created.)*
- [x] Batch 3 — Physical Excel contract **(2026-09-12,
      owner-approved; recorded as decision D-033 + the new
      `docs/phases/phase-02-5-excel-master-template.md`)**:
      `product-master.xlsx` with 4 sheets (محصولات، تنوع‌ها، راهنما،
      گزینه‌ها); exact columns/types/required-optional, canonical
      Persian↔canonical status/vocabulary mappings, D-032 codes,
      D-024/D-025 price fields, blank=NOT_PROVIDED / نامشخص=UNKNOWN /
      invalid=rejected, active-axis encoding, dropdown validation,
      D-026/D-027/D-028/D-017 import semantics unchanged; closes the
      D-028 physical-mapping gate. Template file itself is built at
      the implementation task — no code/implementation in this batch.
- [ ] Size equivalence mappings, if ever needed (owner-curated only,
      D-020 rule 7)
- [ ] Color/size aliases (owner-supplied when needed; none invented)
- [ ] Data-entry language for general product data (register item 4;
      not resolved by Batch 1)
- [ ] SEO slug language (D-016.M)
- [ ] Inventory design constraints (D-016.I)
- [ ] Registry promotion decisions for brand/material/pattern/style/
      season/usage/collar/sleeve/length/closure/fit (separate owner
      decisions; D-019/D-029 governance)
- [ ] Phase 3+ integration decisions (blocked until their phase)

## Phase 3 — WooCommerce Foundation (current)

Scope from MASTER_PLAN §13: WooCommerce foundation. The owner opened
Phase 3 (2026-09-12); Batch 1 is the complete **design/specification
batch** (decisions D-034–D-045; normative design in
`docs/phases/phase-03-1-woocommerce-foundation.md`). No production
integration, no connection to a real instance, no credentials, no
n8n workflows, no implementation code.

Batch 1 — completed design (do not treat implementation as done):

- [x] WooCommerce foundation architecture design (architectural
      role, two-layer canonical/projection contract) — **D-034–D-045
      Approved** (2026-09-12)
- [x] Product/Variant identity mapping design — **D-034 Approved**
      (five distinct identifiers; mapping-registry model; Woo numeric
      IDs are technical, never our identity)
- [x] Simple vs variable product-type mapping design — **D-035
      Approved** (deterministic from D-018 active axes; no third type)
- [x] Category mapping design — **D-036 Approved** (two-level
      hierarchy; duplicate leaf names stay distinguishable)
- [x] Attribute/size-family mapping design — **D-037 Approved**
      (pa_color; one size attribute per family; Size Family is
      internal context; non-registry attributes not created)
- [x] Price mapping design — **D-038 Approved** (D-024/D-025 →
      regular/sale price fields; price-divergence resolution sub-gate
      OPEN)
- [x] Lifecycle/publication mapping design — **D-039 Approved**
      (canonical D-022/D-023 states; Woo projection; never deleted)
- [x] Media mapping design — **D-040 Approved** (featured + gallery
      order; storage sub-decision OPEN)
- [x] Inventory boundary design — **D-041 Approved** (D-016.I stays
      open; no stock fields/sync in this batch)
- [x] API boundary design — **D-043 Approved** (conceptual resource
      contract; implementation-time verification points)
- [x] n8n boundary design — **D-042 Approved** (explicit per-field
      sync directions; no default bidirectional field sync)
- [x] Security/credentials boundary design — **D-045 Approved** (no
      secrets exist or requested; least privilege; per-environment)

Batch 2 — sync architecture (2026-09-12; design/specification only;
normative design in `docs/phases/phase-03-2-woocommerce-sync-architecture.md`):

- [x] D-038 sub-gate analysis + price-sync architecture proposal —
      **D-048 Approved** (2026-09-13, owner — Option A: canonical-
      layer projection; options A/B/C compared; consequences
      recorded)
- [x] Mapping-registry complete conceptual design — **D-046
      Approved** (entry types, authoritative side, uniqueness both
      directions, immutable/write-once/mutable classes, creation/
      update/lookup rules, missing/stale/conflicting/orphaned
      states, recovery, review conditions, provenance,
      D-017/D-027 relationship)
- [x] Field-level sync contract — **D-047 Approved** (every field
      group: canonical owner, Woo projection, direction, write
      actor, Woo-manual-edit/divergence behavior, UNKNOWN/
      NOT_PROVIDED behavior, AI propose / tooling execute,
      approval tier; no default bidirectional sync)
- [x] Product/variation CRUD contract — **D-047 Approved**
      (create/update/read product + variation, hide/withdraw/
      archive, no destructive delete by default; preconditions,
      validation, registry lookup, idempotency key, read-back
      verification, failure handling, compensation concept,
      provenance)
- [x] Idempotency + duplicate prevention operational model — within
      **D-044/D-046** (D-017 identifier level + D-027 event level;
      ambiguous-response read-back reconciliation; SKU never the
      identity)
- [x] Conflict-detection classes — within **D-044** (11 deterministic
      classes with severity, automatic action, review requirement,
      recovery path; AI never silently resolves)
- [x] Woo-side divergence handling — within **D-047** (detection,
      canonical preservation, review queue, optional controlled
      re-projection, no silent overwrite)
- [x] Green/Yellow/Red authority matrix for Woo operations — **D-050
      Approved**
- [x] Media storage direction — **D-049 Approved** (external/object
      storage + Woo references; provider decision deferred to
      Phase 4)
- [x] Non-registry attribute representation — **D-051 Approved**
      (canonical free-text fields + Woo product meta; no automatic
      vocabularies; Color/Size untouched)
- [x] Test/sandbox strategy — **D-052 Approved** (unit validation,
      mocks, isolated staging, failure/duplicate/conflict/price-
      divergence simulations, compensation tests, production-
      readiness gate; execution in Batch 3+)
- [x] Credential/secret structure (conceptual) — within **D-045**
      (environment separation, Woo base URL handling, reference-
      based credentials for Woo/n8n/AI-provider, rotation concept,
      least privilege, log redaction, Git exclusion, Freebuff
      prompt exclusion)

Batch 3 — local development environment (2026-09-13; design only;
normative design in `docs/phases/phase-03-3-local-development-
environment.md`; owner directive: **LOCAL-FIRST**):

- [x] Local-first architecture + Local → Staging → Production
      promotion contract — **D-053 Approved** (owner directive;
      change-configuration-not-business-logic model; local stack =
      development tooling, Phase 4 stays blocked)
- [x] Local component architecture (WordPress+Woo, Woo DB, canonical
      DB, registry, event store, n8n, mock adapter, local media,
      logging) — designed in phase-03-3 §2
- [x] Local runtime technology evaluation — **D-054 Approved**
      (2026-09-13, owner; Docker Compose recommended; native macOS
      and remote-VPS rejected)
- [x] Environment configuration strategy (.env.example committed;
      real env files gitignored; reference-based credentials) —
      extends D-045
- [x] Local WordPress + WooCommerce design (permalinks/REST/webhooks/
      cron/timezone/Toman/RTL; D-035/D-036/D-037 seeds only; local
      Woo never canonical)
- [x] Local database responsibility split + canonical storage
      analysis — **D-055 Approved** (2026-09-13, owner; relational
      app DB — PostgreSQL; files rejected; Woo-as-canonical
      forbidden)
- [x] Mapping-registry local implementation plan — D-046 realized
      (schema, bidirectional uniqueness, lifecycle, orphan/conflict,
      SKU-as-data)
- [x] Event/idempotency store design — D-027 realized (composite key,
      payload-hash conflict detection, terminal states, test reset)
- [x] Mock WooCommerce adapter architecture — same interface as the
      real adapter (D-043/D-047); all D-044 failure classes; no real
      connection
- [x] Price-projection test environment — **D-048 Option A verified
      as approved** (11-case matrix incl. the divergence case;
      canonical inputs never modified)
- [x] Local media design — **D-056 Approved** (2026-09-13, owner;
      S3-compatible emulator behind the D-049 adapter boundary; real
      provider stays Phase 4)
- [x] n8n local boundaries — conceptual workflows only; deterministic
      /AI-proposal/human-approval/Woo-execution stages separated; AI
      never executes Red operations
- [x] AI runtime boundary (local stubbing; unchanged authority) —
      D-050/RULES §32 preserved
- [x] Excel import local test matrix (approved sheets/values only;
      D-028/D-033 semantics)
- [x] Testing strategy (10 layers per D-052) + reset strategy
- [x] Deterministic fictional test dataset (P90001–P90010; approved
      vocabulary only)
- [x] Observability design (structured logs; D-027/D-044 fields; no
      secrets logged)
- [x] Local security baseline (.gitignore plan, localhost-only,
      least privilege, throwaway credentials)

Batch 4 — local environment scaffolding (2026-09-13; D-054/D-055/
D-056 owner-approved; implementation per phase-03-3 §22 boundary B):

- [x] Local project structure (local/{infra,db,canonical,services,
      scripts,fixtures}; guide in `local/README.md`)
- [x] Docker Compose stack (D-054: wordpress+woo, mysql, postgres
      canonical, n8n, minio media, deferred mock service; named
      volumes; 127.0.0.1-only ports; healthchecks)
- [x] Canonical PostgreSQL schema (D-055: seed/canonical/registry/
      events/provenance schemas; identifier separation; sale rules;
      active-combo uniqueness; D-046 bidirectional 1:1; D-027 key;
      D-026 append-only trigger)
- [x] Owner-approved vocabulary seed script + verification (D-031/
      D-032; idempotent; O/I/L audit; **D-030 gate clear since
      D-057**: the historic LG conflict was resolved — 28/28 size
      terms seed)
- [x] Canonical logic layer + 31 unit tests (vocab, identifiers,
      D-046 second guard, D-027 repeats, D-024/D-025/D-048 11-case
      matrix, provenance)
- [x] Mock Woo adapter (D-043/D-047 interface; D-044 failure
      injection: 401/403/429/5xx/timeout/ambiguous-timeout/
      malformed/duplicate/partial; inventory read-only per D-041)
- [x] Media abstraction + local object store (D-056; content-hash
      dedupe; metadata/alt text; provider swap = env-only change)
- [x] D-033 Excel fixture generator — 12/12 deterministic error-code
      profile (products P90001–P90010 + variants; approved values
      only); .xlsx rendering deferred (openpyxl not installed)
- [x] Reset tooling (`local_env.py reset-volumes`; explicit
      RESET-LOCAL confirmation; volumes enumerated; local-only by
      construction)
- [x] .env.example (committed, dummy local values) + .gitignore
      (env secrets, volumes, noise)
- [x] Smoke test (§17): **9 passed / 3 skipped / 0 failed** — the 3
      skipped checks need the running containers (Docker not
      installed on this machine yet)

Batch 4b — local executable architecture (2026-09-13; D-042/D-044/
D-046/D-047/D-048/D-050/D-026/D-027 as approved; runs offline today,
against the real canonical DB once Docker exists):

- [x] Sync engine (D-042/D-047): canonical → mapping → projection →
      mock Woo; D-048 Option A price materialization at sync; D-039
      projection table (draft = no Woo record; publish = RED-gated);
      D-014 SKU derivation (Color then Size, approved D-032 codes);
      D-051 attribute meta; SEO slug NOT projected (D-016.M open);
      post-write read-back verification
- [x] D-027 event store (executable): (source_system, event_id) key;
      identical repeat → skipped_duplicate; conflicting payload →
      integrity error (human review); terminal states never re-entered;
      non-terminal retry under the same ID; sync and re-projection
      kept in separate event namespaces (drift must be re-writable)
- [x] D-026 provenance engine (executable): five source types;
      append-only records; review_state only advances; per-field
      value linkages supersede with full history retained
- [x] D-046 mapping registry (executable): bidirectional 1:1 active
      uniqueness; deterministic second guard; Woo IDs write-once;
      stale/superseded entries archived (never deleted); replacement
      only via reviewed relink; SKU stored as data, never a key
- [x] D-050 Green/Yellow/Red operational gate (executable):
      require_authority() enforces RED = explicit human authorization
      (publish/withdraw/price-write/conflict-resolution); AI never
      passes the gate
- [x] Taxonomy seed into Woo (D-031/D-032/D-036/D-037): 2 primaries +
      20 leaves, pa_color (25 terms), 3 family-scoped size attributes;
      idempotent; alpha/L blocked at the D-030 gate (24/28 size terms
      seeded)
- [x] Divergence detection (GREEN) + controlled re-projection (RED
      when price-affecting or published; own D-027 namespace) — Woo
      hand-edits never silently adopted or overwritten
- [x] D-044 failure classes (executable): 6 injected classes fail
      cleanly (event = failed, nothing adopted); ambiguous timeout
      recovered deterministically via the _pm_pid marker lookup with
      provenance (never blind re-create, never fuzzy name matching)
- [x] Compensation: hide-and-flag; no destructive delete (RULES §22)
- [x] Full test ladder (local/tests/test_ladder.py): **46 tests —
      43 passed / 3 skipped (need Docker) / 0 failed**; originals:
      31/31 unit + smoke 9/3/0
- [x] Same engine against the REAL canonical PostgreSQL (live, D-055):
      **DONE 2026-09-14** — colima stack up (5 services healthy,
      127.0.0.1-only), schema applied + re-apply verified idempotent
      (DO-block guard for `product_publication_minimum`), full
      vocabulary seeded 28/28 sizes incl. D-057 `LRG` (seed-script
      per-row ON CONFLICT bug fixed; `size_term_code_check` aligned
      with the approved sanction), ladder **0 skipped — 105/105 pass**
      with live schema+seed layers, smoke **12/12** (live-DB checks;
      self-cleaning + code-not-display-value fixes). Mock-Woo runs
      in-process; its container service wrapper stays deferred
      (phase-03-3 §22)

Phase 4 (owner-sequenced 2026-09-13: "Data Entry & Verification
Engine" runs locally first; official Phase 4 "Infrastructure" gates
run in parallel and stay owner-gated):

- [x] Import runner CLI (`local/scripts/import_runner.py`): dry-run →
      report (exit 2 on invalid rows); promotion ONLY with explicit
      `--authorize` (D-028 human boundary); D-027 event per run
      (identical workbook → skipped_duplicate); D-017 identifier
      idempotency (same ID + changed values → CONFLICTING_UPDATE
      review item, canonical preserved); D-026 IMPORTED provenance +
      linkages; SKU-as-data uniqueness; optional mock-Woo sync verb
      (hidden records only; publish stays RED)
- [x] Pipeline verified on the D-033 fixture: dry-run 16-error
      profile across all 12 error codes; promote → 5 products +
      3 variants (price-invalid rows are now EXCLUDED from promotion —
      validator gap closed, see edge-case suite below); re-promote →
      skipped_duplicate; sync → 5 created_hidden (P90002 ×2 variations
      incl. the D-048 divergence case, P90006 ×1 variant-sale case);
      re-sync → all skipped_duplicate
- [x] Phase 4 edge-case suite (`local/tests/test_phase4_edge_cases.py`,
      16 tests): D-027 zero-write identical re-import + conflicting-
      payload integrity error; D-024/D-025/D-048 full precedence
      matrix incl. expiry boundaries; D-030/D-031/D-032/D-057 registry
      + sanction-ledger invariants; D-019/D-020 no-auto-vocabulary and
      family scoping through the validator; D-026 append-only
      provenance + advancing review state; executable refusal ledger
      (`NO_INVENTED_RULES` in import_runner.py) documenting that
      1,000-Toman rounding, negative-margin checks and provenance
      rewriting on re-import were REFUSED as unapproved rules
- [x] Validator gap closed (`local/canonical/excel.py`):
      INVALID_PRICE rows were previously reported AND retained in the
      valid set (promotable with a recorded error); they are now
      rejected per D-028 — invalid = rejected
- [x] Persistence fixes surfaced by the run (in `sync_engine.py`):
      registry keys JSON-serializable (`type\x1fkey`) + one-time
      tuple-key migration; `_as_date` guard for JSON-round-tripped
      dates (D-024/D-025 sale-validity comparisons)
- [x] Phase 4 Infrastructure decision brief (design-only):
      `docs/phases/phase-04-infrastructure-brief.md` — G1 hosting,
      G2 instance model, G3 media provider (D-049 gate), G4 backups,
      G5 domain/SSL, G6 observability, G7 promotion gates — ALL OPEN
- [x] Owner: ~~decide G1–G7~~ — **DEFERRED via D-058 (2026-09-14,
      owner)**: all seven gates deferred until product operational
      validation concludes; local-first strategy continues; closure
      evidence in `docs/reports/phase-4-infrastructure-gates-status.md`.
      Reopening any gate requires its own owner decision record
- [x] Owner: ~~resolve register row 24 (alpha/L LG code)~~ —
      **RESOLVED 2026-09-13 via D-057 (`LRG`)**; full vocabulary
      seed and alpha-size sync unblocked
- [x] Verification-queue tooling (`local/canonical/`
      `verification_tool.py` + `local/tests/`
      `test_verification_queue.py`, 11 tests): append-only HITL review
      (D-026) — decisions stamped in place with reviewer identity +
      provenance, never popped; deduplicated enqueue of runner review
      items; D-050: decisions are human-only (`--reviewer` required;
      no auto-resolve path exists); queue state lives under gitignored
      `local/volumes/verification/`; 16 fixture error rows materialize
      end-to-end (report → queue → decision)
      (human review workflow — the queue currently reports; it does
      not yet provide an interactive review UI)

Batch 4 — findings and open items:

- [x] ~~**Owner decision (BLOCKER for full vocabulary seed):**
      D-032's owner-approved size code **LG** (for size L) contains
      the letter L, which D-030 rule 1 forbids~~ — **RESOLVED
      2026-09-13, owner decision D-057**: the canonical Alpha-L code
      is now **`LRG`** (O/I/L-safe, no D-030 exception created;
      deprecate+replace per D-030 rule 5 — `LG` was never referenced
      by real data). Conflict ledger (`CODE_CONFLICTS`) is empty;
      the seed gate stays armed; **28/28 size codes seed**
- [x] ~~BLOCKED (2026-09-14): host disk full~~ — **RESOLVED same
      day**: owner freed disk space (34 Gi available); colima restart
      with registry mirrors → full stack up, schema+seed live, all
      skips converted to passes (see live-DB record above)
- [ ] Install openpyxl to render the .xlsx fixture
      (`pip install openpyxl`, then re-run `make_fixtures.py`)
- [ ] WooCommerce plugin activation + store configuration inside the
      local instance (implementation-time verification points per
      phase-03-3 §5)

Batch 3+ — remaining Phase 3 work (OPEN, in order):

- [x] ~~Owner decision: D-048 price-sync architecture proposal~~ —
      **Resolved 2026-09-13: Option A (canonical-layer projection)
      owner-approved** (alternatives B/C not chosen)
- [x] ~~Owner decisions: D-054 (Docker Compose local stack), D-055
      (relational canonical database), D-056 (local media emulator)~~ —
      **Resolved 2026-09-13: all three owner-approved**
- [x] ~~Local scaffolding after approval~~ — **done in Batch 4**
      (Compose stack, .gitignore, .env.example, canonical schema +
      registry/vocabulary seeding, mock Woo adapter, media emulator,
      price-projection harness, Excel fixtures, reset tooling — see the
      Batch 4 section above)
- [ ] WooCommerce environment selection/setup (hosting/VPS —
      register row 6; environment separation per RULES §18;
      production/staging only — the local stack is separate)
- [ ] Media storage provider selection (D-049 direction approved;
      provider deferred to Phase 4)
- [ ] API credential configuration (after environment exists;
      secrets never in this repository — D-045/RULES §16)
- [ ] Mapping registry implementation (D-034/D-046 — required before
      any sync implementation)
- [ ] Controlled-vocabulary seed into Woo (categories D-036;
      pa_color + family size attributes D-037 — one-time,
      owner-approved data)
- [ ] Product/variation synchronization implementation (D-048 now
      approved; prerequisites: environment, credentials, registry
      seed)
- [ ] Automated tests for the sync flows per the D-052 strategy
      (unit + mock + staging; RULES §23 failure cases)
- [ ] Sandbox/test environment verification
- [ ] Inventory implementation (blocked — D-016.I open)
- [ ] Media implementation (blocked — D-040 sub-decision open)
- [ ] n8n sync workflows — foundation **closed** (Phase 5 M1–M4,
      gate report `docs/reports/phase-5-n8n-foundation-gate-report.md`):
      standards, sandbox, error router with D-052 dead-letter → HITL
      bridge (D-026 provenance); production sync workflows still await
      the real WooCommerce connection

## Blocked / do-not-start

Forbidden until their phase begins (MASTER_PLAN §16). Do not start
these even if they seem helpful:

- [x] ~~Phase 3 — WooCommerce foundation~~ — **unblocked (2026-09-12,
      owner opened Phase 3)**; Batch 1 design recorded via
      D-034–D-045 (see below)
- [ ] Phase 4 — Infrastructure (no hosting, DNS, backups setup)
- [x] ~~Phase 5 — n8n foundation~~ — **unblocked and CLOSED at
      foundation level (2026-09-14, D-059 Option A; M1–M4 shipped,
      gate report passed)** — local-only (D-053); owner activation
      steps (credential + error-workflow designation) pending per the
      gate report §5; production n8n and real credentials remain
      forbidden (D-045)
- [x] ~~Phase 6 — Notion Business OS~~ — **CLOSED at foundation level
      (2026-09-15, M1–M4 shipped; final commit `9ab29e5`; gate:
      conformance matrix A–H green against both D-027 stores)** —
      kickoff recorded 2026-09-15 (`docs/reports/
      phase-6-kickoff-and-roadmap.md`): design/contract-first roadmap
      (M1–M4), D-027-corrected Notion idempotency, D-050 authority
      matrix; **D-060 Approved — Option A, amended 2026-09-15**
      (canonical PostgreSQL = HITL/incident SSOT, Notion mirrors;
      lifecycle extended with Scheduled/Rejected/Archived;
      idempotency key refined with revision_marker — marker source
      owner-gated pending Notion API verification) — M1 blueprint
      scaffolded at
      `docs/phases/phase-06-notion-business-os.md`; **D-061 Accepted**
      (undefined_table stays Class E, no logic change); **M2 contracts
      + D-027 ingestion path implemented** (`local/canonical/
      notion_contracts.py`, `local/canonical/notion_ingest.py`: 9-state
      machine, revision-marker key, live-PostgreSQL event store with
      dedupe/conflict/HITL semantics, D-026 provenance; 16 live
      integration tests, 0 skips); **M3 adapter + polling engine
      implemented** (`local/services/notion_adapter.py`:
      NotionProvider boundary, MockNotionAdapter, PollingEngine with
      per-page cursor — unchanged pages emit nothing, changed markers
      yield new D-027 events; error boundary captures malformed
      adapter output without crashing; 17 adapter/engine tests,
      live + offline); **M4 integrity audit + conformance proof
      complete** (frozen matrix `local/tests/fixtures/notion/
      conformance_matrix.json` rows A–H executed against BOTH stores;
      fixes: failed-marker suppression stops D-052 auto-retry loops,
      provenance on failed deliveries, wall-clock excluded from
      pre-key identity, store-neutral conflict re-raise, psql
      trailing-field sentinel; **Notion connectivity explicitly
      deferred, owner-gated — no credentials used or created**).
      Standing owner gate: no Notion workspace automation; live
      connectivity verification = separate owner-gated milestone.
- [x] Phase 12 — Order Management System — **CLOSED at foundation
      level (2026-09-16), D-081–D-084 all owner-approved**:
      D-081 order contract (`local/canonical/oms_contracts.py`:
      canonical Order with line items bound to Product ID / Variant
      ID / SKU — identities never derived from each other; money as
      strict integer minor units with float rejection; lifecycle
      `PLACED → VALIDATED → FULFILLING → COMPLETED` + CANCELLED from
      any pre-COMPLETED state + REFUNDED from COMPLETED only;
      CANCELLED/REFUNDED absolute terminals; `client_order_id`
      SHA-256 idempotency — replay = skipped_duplicate, conflicting
      payload = integrity error); D-082 inventory
      (`oms_engine.py` + `oms.inventory`/`oms.reservation` schema:
      provider-neutral InventoryStore; live PgInventory guarded
      conditional UPDATE — the row lock — no read-modify-write
      anywhere; deterministic insufficient_stock; in-call rollback on
      multi-line partial failure; JSON parity store; reservation
      ledger drives release on CANCELLED/REFUNDED/TTL-expiry);
      D-083 payment-neutral boundary (markers pending/unpaid only,
      no gateway module, no credentials) + fulfillment notifications
      through the Phase 11 FanOutEngine with caller-configured
      targets (the OMS never invents destinations; notification
      failure never blocks the order — D-077 isolation proven);
      D-084 audit + reconciliation (every transition a D-027 event
      with D-026 provenance; OmsReconciliationWorker auto-cancels
      orphaned FULFILLING orders past configurable TTL with reason
      `fulfillment_ttl_expired`, returns reserved stock, never
      touches COMPLETED, dry-audit mode).
      Phase 12 suite 37/37 (incl. live-PG E2E: full lifecycle, real
      row-lock oversell — single winner of 10 concurrent buyers —,
      TTL reconciliation with stock return, restart-safety,
      notification isolation); battery 498/498 zero-skip; ladder
      46/46; AST audit clean (zero network imports, zero platform/
      price/publication refs, zero payment-gateway paths, zero
      os.environ access); secret scan clean; diff-check PASS.
      Suite-found defects fixed in-batch: silent float truncation of
      money (strict integer coercion), dead notification bridge
      (targets now caller-configured), partial-reservation rollback
      hole (in-call tracking), PG integer cast at boundary,
      provenance-surface mismatch. Standing owner gate: payment
      gateway and live store credentials (D-045) — none exist, none
      requested.
- [ ] Phase 26 — Launch Readiness, Go/No-Go Attestation & Controlled
      Activation — **IN PROGRESS (M0 spec registered 2026-09-19;
      D-137–D-140 PROPOSED, implementation owner-gated)**:
      canonical launch-readiness control matrix over the nine
      MASTER_PLAN domains (D-137), deterministic fail-closed Go/No-Go
      evaluator with commit+config-bound attestation (D-138),
      controlled activation state machine with one-time owner
      approval, canary ceilings, kill-switch and reconciliation-
      preserving rollback (D-139), launch verification battery +
      canonical evidence pack (D-140). Grounded surfaces: Phase 20
      sweeps/D-114, D-121 ledger, D-123 probes, D-124 redaction,
      D-125 compaction, D-127/D-128 budgets, Phase 19 RBAC +
      confirmation-key + control-audit chain, Phase 24 portability,
      Phase 25 conductor/fault-ladder/recovery. **Completion
      produces a launch CANDIDATE + verdict — NOT a launch; live
      activation requires a separate explicit one-time owner
      authorization.** Spec: `docs/phases/phase-26-launch.md`.
- [x] Phase 25 — Full System Test & E2E Failure/Recovery Ladder — **CLOSED
      (2026-09-18), D-133–D-136 all owner-approved same-day**:
      D-133 conductor (`canonical/e2e_contracts.py` +
      `e2e_conductor.py`: pure ten-stage flow — lead → conversation →
      discovery → cart/order → payment intent → verification →
      inventory → shipping → notification → analytics — over declared
      stage envelopes, zero schema mutation, ONE unbroken D-121 root
      trace with per-stage causal ids; D-052 class classified AT the
      stage boundary — the audited class is what recovery routes on);
      D-134 fault ladder over the REAL engines (Class-A outage
      recovers by replay with jitter-free backoff and a byte-equal
      end state; D-127 exhaustion refuses pre-dispatch with zero
      provider invocation and NO auto-retry; media fault fails
      closed; lock contention yields a byte-untouched claim;
      payment failure → CANCELLED, inventory RESTORED 8→10, failure
      notice via the real D-089 registry); D-135 reconciliation
      (idempotent stranded-lock sweep with zero phantoms and no
      resurrection; durable-only rebuild; exactly-once outbox replay
      on JSON AND live PG; conflicting duplicate → IntegrityError);
      D-136 battery (`test_phase25_full_system.py`: 15 offline +
      3 live-PG E2E — the full flow persisted through the real
      PgEventStore). FULL battery **814/814 zero-skip, two
      consecutive green runs + census run, zero warnings**; ladder
      46/46; census reconciles exactly (T1=706 · T2=44 · T3=54 ·
      T4=10 = 814, 32 modules); AST CLEAN (68 files) / entropy CLEAN
      (112 files); `git diff --check` PASS; stack 5/5 healthy.
      Details: `docs/phases/phase-25-full-system-test.md` §7.
- [x] Phase 24 — Vendor Lock-in & Neutral Portability Layer — **CLOSED
      (2026-09-18), D-129–D-132 all owner-approved same-day**:
      D-129 neutrality (`canonical/portability.py` `ProviderContract`;
      conformance proven for Mock + live-compatible adapters +
      FallbackProvider under the declared composite-members rule;
      mock usage-envelope conformance gap found & fixed; D-127 token
      write-through proven to exact metering + 100% hard refusal);
      D-130 storage abstraction (`BackendPair` +
      `assert_backend_parity` — all four declared pairs (event store,
      slot locks, notification locks, media) mode=both ZERO
      divergences incl. live PG; JSON slot-lock `claim` envelope
      divergence caught & conformed (consumers read `post_id` only);
      `LocalObjectStore` gained `list()`; media conformance PASS);
      D-131 channel adapters (`ChannelAdapterContract`; hot-swap
      registry with deterministic verdict rows through the SHIPPED
      D-121 `LogLedger` emitter + D-124 redaction gate;
      channel-confinement AST rule joined to the D-116 extended
      sweep as a declared-homes allowlist; planted violations
      caught; analytics literals relocated to single contracts home,
      Phase 13 battery re-verified 28/28); D-132 battery
      (`test_phase24_portability.py` 26/26 zero-skip incl. live-PG
      E2E: parity mode=both, lockout ⇒ D-066 fallback with exact
      ledger metering, hot-swap audit rows). FULL battery
      **796/796 zero-skip, two consecutive green runs + census run,
      zero warnings**; ladder 46/46; census reconciles exactly
      (T1=694 · T2=44 · T3=51 · T4=7 = 796, 31 modules); entropy
      CLEAN (122 files); canonical AST gate green; stack 5/5
      healthy; `git diff --check` PASS.
      Details: `docs/phases/phase-24-vendor-lockin.md` §6.
- [x] Phase 23 — Resilience & Cost Optimization — **CLOSED
      (2026-09-18), D-125–D-128 all owner-approved same-day**:
      D-125 compaction (`local/canonical/compaction.py`: state-based
      eligibility, verified-freeze JSONL archives + attestation
      folds, fail-closed teardown with count checks, manifest rows
      in `security.hardening_audit` (`compaction_manifest` kind
      added), `COMPACT_RETIREABLE` admin command (admin-only,
      Phase 19 control plane), declared idempotent indexes
      (pending-status partial, slot-lock platform+active, breaker
      state+horizon) + keyset `keyset_scan_events`);
      D-126 resilience (`local/canonical/resilience.py`:
      D-052-bound RetryPolicy — jitter-free logical backoff,
      A retry / B,C,E terminal / D quarantine; BudgetedExecutor;
      psql transport ceiling with bounded queue + deterministic
      `TransportSaturation` Class-A fast-fail);
      D-127 budgets (`budget_contracts.py` + `budget_engine.py`:
      5 resources × green/yellow, env-configurable via
      `PHASE23_BUDGET_*`, ≥80% warn / 100% pre-dispatch refusal,
      exact-boundary allowed, D-063 write-through, batch
      stop-at-refusal); D-128 battery (forgery detection,
      fail-closed compaction, saturation chaos, quota exhaustion).
      Suite 20/20 zero-skip incl. 3 live-PG E2E (active lock
      survives, chain attestation unchanged after compaction).
      Battery **770/770 zero-skip, two consecutive green runs**;
      ladder 46/46; census reconciles 770/770 across 30 modules
      (T1=666 · T2=46 · T3=51 · T4=7); AST (93) / entropy (103)
      CLEAN. In-batch catch: slot-lock boolean-parse defect
      (archive preserved evidence; parser fixed, re-proven, pinned).
      Standing gate: bounds are local/env-config; production sizing
      stays owner-gated. Next: Phase 24 per MASTER_PLAN.
- [x] Phase 23 — Resilience & Cost Optimization — **M0 SPEC
      REGISTERED (2026-09-18), awaiting owner approval of
      D-125–D-128**:
      Spec: `docs/phases/phase-23-resilience-cost.md` (governance
      reconciliation vs MASTER_PLAN §13 "Cost Control", live
      growth evidence: event_record 20,561 rows, breaker residue
      82/82 non-CLOSED). PROPOSED decisions: **D-125**
      deterministic retention/compaction via verified-freeze
      archives (state-based eligibility, attestation-verified
      snapshots, fail-closed teardown, hardening_audit manifests,
      declared indexes + keyset reads — tamper-evidence NEVER
      weakened); **D-126** resilience envelope (D-052-bound
      RetryPolicy with logical backoff, BudgetedExecutor, psql
      transport concurrency ceiling with deterministic fast-fail,
      breaker-hygiene compaction); **D-127** platform
      resource-budget envelopes (D-063-identical ≥80% warn / 100%
      pre-dispatch refusal, per_run/per_logical_day windows,
      green/yellow scopes, single consumption ledger with AI
      write-through); **D-128** chaos × compaction × quota battery.
      Owner items: approve/amend D-125..D-128; compaction cadence
      (per-run automatic vs control-plane `COMPACT_RETIREABLE`
      command); default budget numbers. Implementation M1–M4
      starts ONLY after approval.
- [x] Phase 22 — Observability & Health Telemetry — **CLOSED
      (2026-09-18), D-121–D-124 all owner-approved**:
      D-121 log ledger (`local/canonical/obs_contracts.py`:
      engine.log.v1 — 8 required fields, 7 domains, deterministic
      SHA-256 trace/causal ids over causal inputs via
      TraceContext root/child, JSONL append-only sink + PgLogVault
      over the D-027 transport with `log|<trace>|<causal>` keys —
      re-emission dedupes, trace-scoped counts exact);
      D-122 metrics (`local/canonical/obs_metrics.py`: monotone
      counters (positive-int only), gauges, fixed-bucket
      histograms, declared bounded cardinality (≤8 labels, ≤64
      sets), byte-identical Prometheus text exposition;
      `local/services/metrics_exporter.py`: stdlib HTTP bound
      HARDCODED to 127.0.0.1, serves exactly the exposition, 404
      off-path); D-123 health (`local/canonical/obs_health.py`:
      PASS/DEGRADED/FAIL probes — degraded explicit, threshold
      ordering guarded — rendering qa.health_report.v1 with an
      operator CLI; shipped probes: pg schema presence, D-115
      ledger fold over the Phase 19 chain, queue depth, breaker
      states); D-124 zero-leak telemetry (credential markers →
      `[REDACTED]` in details/payloads/LABELS, PII denylist,
      marked `…[TRUNC]` oversize, control chars Class-B, no engine
      imports from observability). Suite 26/26 zero-skip incl. 5
      live-PG E2E (vault dedupe + trace counts, live probes, CLI
      attestation over the real chain). Battery **750/750
      zero-skip, two consecutive green runs**; ladder 46/46;
      census reconciles 750/750 across 29 modules (T1=649 · T2=46
      · T3=48 · T4=7); AST (88) / entropy (98) / bounds (11/11)
      CLEAN. In-batch fixes: sanitize ordering (truncate before
      gate), vault key trace-embedding, exporter moved canonical →
      services (Phase 20 sweep caught `http.server` in canonical),
      run-scoped live-test ids. Standing owner gate: loopback
      only — no external collector/APM (D-045); Phase 22 passing
      does NOT prove compatibility with real observability
      infrastructure. Next: Phase 23 per MASTER_PLAN.
- [x] Phase 21 — Testing & Quality Engineering — **CLOSED
      (2026-09-18), D-117–D-120 all owner-approved**:
      D-120 tier taxonomy + toolkit (`local/canonical/qa_toolkit.py`:
      Unit → Subsystem Ladder → Local PG Integration → Full E2E,
      census derived from real discovery output and reconciled
      exactly 724/724); D-117 state-machine invariant battery over
      all five phase-17–20 edge matrices (each proven CLOSED by
      construction — undeclared transitions refused at the
      validator, not by exception); D-118 deterministic chaos
      (handler/dispatcher exception isolation, flaky-dispatch
      redelivery dedupe, mid-transaction PG aborts with
      clean-rollback + audit-truth + ledger-integrity invariants,
      8-thread ledger and live slot-lock contention — exactly-one
      winner each, zero wall-clock reads); D-119 seeded fuzz (585
      cases) over every D-114 entry point with frozen verdict
      fixtures. Net-found shipped defects, fixed + pinned +
      mutation-checked: DueScanner work-starvation on the
      accumulating durable store (D-095/D-096); Phase 15 race-key
      prefix collision vs the never-deleted `slot_lock` ledger
      (intermittent `0 != 1`); 5 unclosed test file handles
      polluting D-114 entry-point output. Battery **724/724
      zero-skip, two consecutive green runs**; ladder 46/46;
      AST sweep (84 files) + entropy scan (94 files) + bounds
      re-audit (11/11) all CLEAN; stack 5/5 healthy. Observation
      logged for a future batch: `time.time_ns()` row-ID components
      in Phases 9–11 publishers (IDs, not D-027 keys). Next:
      Phase 22 (Observability) per MASTER_PLAN.
- [x] Phase 20 — Security Hardening & Threat Model — **CLOSED
      (2026-09-17), D-113–D-116 all owner-approved**:
      D-113 contracts (`local/canonical/security_contracts.py`:
      six-category threat taxonomy mapped to phase surfaces —
      credential leakage, replay attacks, ledger tampering, race
      injection, oversized/malformed payloads, error-surface
      enumeration; battery-backed control registry where every
      control NAMES its test artifact (no untested claims);
      HardeningPolicy numeric bounds + HardeningAuditRecord
      validation); D-114 hardening (`security_engine.py`:
      system-wide InputHardeningGate — payload/string size caps,
      identifier charset, control-character, confusable-unicode and
      invisible-codepoint rejection, NFC canonicalization, JSON
      depth/width caps, duplicate-key rejection, uniform
      reason-code-only error surfaces; ALL prior-phase validators
      re-audited, six unbounded surfaces hardened with declared +
      enforced bounds); D-115 ledger/replay defense (chain-head
      attestation **v2** — position-weighted FULL-ROW SHA-256 fold
      over the Phase 18/19 chains: interior mutation, swap,
      truncation and append each detected, verified live-PG with
      byte-exact restore; durable `security.hardening_audit` PK-dedup
      vault + HardeningEngine facade; deterministic logical-clock
      rate limiter with lockout arming/expiry and chain-anchored
      replay-key burns); D-116 sweep worker (`security_worker.py`:
      extended AST detectors — dynamic exec, process escape, unsafe
      deserialization, network sockets, randomness, bare excepts —
      subprocess confined to test tooling; secret-entropy scanner
      with identifier discrimination + synthetic mock-token
      allowlist; 11/11 bounds re-audit clean).
      Phase 20 suite 33/33 zero-skip (28 offline + 5 live-PG E2E:
      durable hardening-audit with re-report dedup, live
      admin.control_audit attestation tamper detection + restore,
      HITL ledger attestation, deterministic 8-thread lockout race,
      8-thread audit-record dedup race → exactly one row); battery
      702/702 zero-skip; ladder 46/46; extended AST sweep clean
      (0 findings); entropy scan clean (0 flags / 92 files);
      diff-check PASS; containers 5/5 healthy.
      In-batch defects fixed: attestation v1 blind to interior-row
      payload mutation (hash-only fold → full-row fold v2);
      security.hardening_audit missing from schema (added + live);
      missing vault import (`_json`) crashing PG audit writes;
      `re.compile` flagged as dynamic compile; entropy scanner
      flagging UPPER_SNAKE constants; layered-defense scope
      clarified (validators = bounds, gate = charset/controls).
      Standing owner gate: all controls local + deterministic; no
      external security providers, auth backends, WAF/SIEM, or
      network (D-045/D-116) — Phase 20 passing does NOT prove
      compatibility with real security infrastructure.
- [x] Phase 19 — Internal Tools, Operator Console & Admin Control
      Plane — **CLOSED at foundation level (2026-09-17), D-109–D-112
      all owner-approved**:
      D-109 contracts (`local/canonical/admin_contracts.py`: closed
      six-command grammar — PAUSE_QUEUE, RESUME_QUEUE,
      RETRY_DLQ_ITEM, FORCE_SUPERSEDE_INSIGHT, MANUAL_SLOT_OVERRIDE,
      REPLAY_EVENTS; deterministic local-token RBAC
      (`actor:operator:*` queue ops, `actor:admin:*` all,
      `actor:system:*` engine-internal) with strict
      `actor:<role>:<non-empty id>` token parsing; OperatorAction /
      QueueControlCommand / SystemDiagnosticReport /
      AuditQueryFilter validators; circuit-breaker CLOSED → OPEN →
      HALF_OPEN state machine; replay DRY_RUN/APPLY decision);
      D-110 engine (`admin_engine.py` + `admin.operator_actions` /
      `admin.control_audit` / `admin.circuit_breakers` schema:
      action_id PK as the exactly-once application guard;
      REPLAY_EVENTS dry-run by default, APPLY only with a
      single-use per-KEY-VALUE confirmation key burned BEFORE
      dispatch and its burn recorded in the tamper-evident chain;
      handler envelopes carry the computed mode; multi-domain
      diagnostic report via injected read callables with reader-
      error isolation — queues/HITL/insights/assets, zero
      cross-module imports; filtered action queries); D-111 worker
      (`admin_worker.py`: durable queue control states (PAUSED/
      OPEN) with idempotent transitions; DLQ item retries through
      an injected dispatcher with attempt budgets (≥5 refused) and
      refusals audited; circuit breakers tripping manually or via
      injected threshold detectors with deterministic logical-clock
      cool-downs and HALF_OPEN probe close/re-open — every
      intervention an immutable D-027 event); D-112 audit (global
      SHA-256 hash-chained operator ledger, verify_chain tamper
      detection — Phase 18 standard; zero UI/frontend coupling —
      a callable facade only).
      Phase 19 suite 24/24 zero-skip (20 offline + 4 live-PG E2E:
      real PgEventStore + PG admin tables, 8-thread identical-action
      race with exactly one APPLIED, live replay-key burn,
      queue-control/breaker restart parity); battery 669/669
      zero-skip; ladder 46/46; AST audit clean (0 network imports,
      0 AI SDKs, 0 UI framework couplings, 0 cross-domain imports,
      0 time/datetime, 0 os.environ); secret scan clean;
      diff-check PASS.
      Suite-found defects fixed in-batch: failed report readers
      leaking None into the validated domain map; RBAC token
      parser accepting id-less actors; ambiguous REPLAY reason
      condition; replay handler envelopes missing the computed
      mode; per-action-id key burn allowing the same key to apply
      twice under a new action id (now per-KEY-VALUE via audited
      burns); an undefined-name crash on verify_chain's success
      path; and two live tests missing registered handlers.
      Standing owner gate: no auth providers, no real identities,
      no UI framework, no network (D-045) — operators are local
      token refs; Phase 19 passing does NOT prove live SSO/UI
      compatibility.
- [x] Phase 18 — HITL Approval Engine & Decision Ledger — **CLOSED at
      foundation level (2026-09-17), D-105–D-108 all owner-approved**:
      D-105 contracts (`local/canonical/hitl_contracts.py`: canonical
      HitlReviewTicket — ticket_id, queue_type INSIGHT_REVIEW /
      PUBLISH_GATE / ORDER_OVERRIDE / ASSET_FLAG, payload_ref,
      required_role, logical clock stamps (never wall clock); role
      discipline via mock local actor refs (role:*/agent:* — D-045);
      lifecycle PENDING_REVIEW → CLAIMED → APPROVED / REJECTED /
      MODIFIED / ESCALATED / EXPIRED with EXPIRED sweep-only (never
      a reviewer action), MODIFIED requiring payload_override,
      escalation a re-queuing LOOP with deterministic role elevation;
      strict ReviewAction/Resolution validation); D-106 engine
      (`hitl_engine.py` + `hitl.review_tickets` / `hitl.review_ledger`
      schema: ticket_id PK as the atomic claim lock — guarded UPDATE,
      exactly one CLAIMED winner under 8-thread races; append-only
      ledger hash-chained per ticket with verify_chain tamper
      detection; idempotent ingestion of Phase 17
      DISPATCHED_TO_HITL insights via unique ingest_key with
      SHA-256-digest deterministic ticket ids; JSON parity vault;
      deterministic expire_sweep on an injected logical-clock
      evaluator — zero wall-clock); D-107 dispatcher
      (`hitl_dispatcher.py`: HitlIngestionBridge over an injected
      insight source (filters non-HITL rows, re-ingest idempotent);
      resolution → downstream command through injected queue-type
      dispatchers (apply recommendation / unblock slot / OMS
      compensation / asset flag) with zero cross-module imports;
      exactly-once application gate — a duplicate approval/rejection
      signal produces zero duplicate side-effects; dispatcher
      failures recorded, never silent; command_for() pure downstream
      contract shape carrying the MODIFIED override); D-108 audit
      (full ledger parity: original proposal → claim → resolution →
      applied action, all D-027 events, ledger rows hash-chained —
      mutation of decision history is detectable).
      Phase 18 suite 22/22 zero-skip (18 offline + 4 live-PG E2E:
      real PgEventStore + PG vault/ledger, 8-thread multi-reviewer
      claim race with exactly one winner, claim→resolve→apply chain
      with on-PG chain verification, ingestion idempotency, expiry
      sweep + restart parity); battery 645/645 zero-skip; ladder
      46/46; AST audit clean (0 network imports, 0 AI SDKs, 0
      cross-domain imports, 0 time/datetime, 0 os.environ); secret
      scan clean; diff-check PASS.
      Suite-found defects fixed in-batch: psql transport rendering
      Python None as the invalid jsonb token (every live insert
      failed — optional jsonb now emits a literal SQL NULL keyword
      via control flow), builtin hash() in ingest ticket ids
      (process-randomized — SHA-256 digest, Phase 17 precedent),
      and a missing _JsonVault.max_ledger_seq parity method.
      Standing owner gate: no auth backends, no real identities, no
      network (D-045) — actors are mock local role references;
      Phase 18 passing does NOT prove live identity-provider
      compatibility.
- [x] Phase 17 — AI Business Analyst & Decision Engine — **CLOSED at
      foundation level (2026-09-17), D-101–D-104 all owner-approved**:
      D-101 contracts (`local/canonical/analyst_contracts.py`:
      canonical BusinessInsight/Recommendation — insight identity =
      SHA-256 over (category, sorted correlation keys, sorted metric
      refs), identical evidence ⇒ identical insight; lifecycle
      GENERATED → EVALUATED → DISPATCHED_TO_HITL / AUTO_ACCEPTED /
      DISMISSED with SUPERSEDED reachable from any non-terminal
      state incl. HITL-waiting; confidence_score ∈ [0,1]; Class-B
      validation of incomplete metric contexts before any durable
      write; D-104 boundary helpers requires_hitl/can_auto_accept);
      D-102 engine (`analyst_engine.py` + `analytics.business_insight`
      schema: strict evaluation/application separation — the injected
      evaluator sees the durable row and mutates nothing; evidence-
      only dedup audits (caller labels never create conflicting D-027
      duplicates); PG PK dedup + JSON parity vault; every transition
      an attempt-unique D-027 event; ledger() rebuilds the complete
      decision rationale from durable events alone); D-103 worker
      (`analyst_worker.py`: plain-data metric frame from D-085 rollup
      cells + Phase 15 scheduling observations — zero domain-module
      imports (AST-verified); four injected deterministic built-in
      detectors (publication failure, order cancellation, order
      drought, scheduling hotspot) with configurable thresholds;
      breaches proposed as insights via the engine = immutable D-027
      audit events only; HitlTriageBridge emits a Phase 14
      contract-shaped hitl.review_required.v1 event through an
      injected callable — never a direct notification call; re-scan
      idempotent via evidence dedup); D-104 enforcement (auto_accept
      structurally refuses HIGH/CRITICAL severity or state-mutating
      payloads — battery-asserted unreachable).
      Phase 17 suite 27/27 zero-skip (23 offline + 4 live-PG E2E:
      real PgEventStore + PG vault, propose/dedup/evaluate/dispatch,
      8-thread identical-proposal single-creator race, lifecycle +
      ledger + restart parity, live scan E2E); battery 623/623
      zero-skip; ladder 46/46; AST audit clean (0 network imports,
      0 AI SDKs, 0 domain-module imports from analyst modules, 0
      os.environ, 0 time/datetime imports in canonical modules);
      secret scan clean; diff-check PASS.
      Suite-found defects fixed in-batch: scan instant leaking into
      the insight key (re-scan created new insights — now evidence-
      only keys, instant is metadata), builtin hash() ids
      (process-randomized — SHA-256 evidence digest), cancellation
      ratio computed over the wrong denominator, build_frame
      accepting incomplete cells, DISPATCHED_TO_HITL fully terminal
      (SUPERSEDED unreachable from HITL — contradicted D-101), dedup
      audit embedding caller insight_id (conflicting D-027
      duplicates on identical evidence), and live fixtures not
      run-scoped at the evidence level (shared durable table —
      Phase 13–16 precedent).
      Standing owner gate: no external AI APIs, no credentials
      (D-045) — evaluators are injected deterministic functions;
      Phase 17 passing does NOT prove live AI-provider or
      notification compatibility.
- [x] Phase 16 — Content Versioning & Media Asset Management —
      **CLOSED at foundation level (2026-09-17), D-097–D-100 all
      owner-approved**:
      D-097 contracts (`local/canonical/asset_contracts.py`:
      canonical MediaAsset — checksum COMPUTED from the actual bytes
      via SHA-256, size cross-checked, mime allow-list + signature
      contradiction check, byte cap; ContentVersion — v1-root rule,
      parent links, monotonic numbers; single-chain graph validator;
      pure deterministic derivation keys over (checksum, kind, spec);
      durable reference vocabulary + ACTIVE/QUARANTINED/GC_ELIGIBLE
      and PENDING_DERIVATION/PROCESSING/READY/FAILED vocabularies);
      D-098 vault (`asset_engine.py` + `assets.media_asset` /
      `assets.content_version` schema: PG unique constraints as the
      atomicity — checksum PK + (content_id, version_number) unique —
      with a JSON parity backend; Class-B validation BEFORE any byte
      reaches storage; dedup by construction returns DEDUPLICATED
      with the existing asset_id; append-only chains with stale-head
      protection and durable version-number derivation — never a
      caller counter; binaries behind the injected Phase 3 MediaStore
      seam — references only, never deletes); D-099 variant bridge
      (`asset_worker.py`: idempotent derivation — same parent+spec
      yields the same derivation key and reference, reprocessing
      safe; unknown parent fails deterministically; cooldown-aware
      processing semantics); D-100 lifecycle + audit (quarantine
      scanner — referenced assets kept, orphans quarantined at the
      injected instant, configurable cooldown → GC-eligible,
      resurrection on reference; every upload/dedup/version/
      lifecycle/variant action a D-027 event; historical version
      reconstruction from durable rows alone — fresh-engine parity
      tested).
      Phase 16 suite 20/20 zero-skip (17 offline + live-PG E2E:
      real PgEventStore + PG vault, register→dedup→version chain,
      8-thread same-checksum single-creator race, quarantine scan on
      shared durable state, restart parity); battery 596/596
      zero-skip; ladder 46/46; AST audit clean (zero network
      imports, zero cloud SDKs, zero platform/pricing/notification
      imports in asset modules, zero os.environ; the two scan hits
      are the D-027 services.sync_engine EventStore dependency —
      the established Phase 13–15 precedent); secret scan clean;
      diff-check PASS.
      Suite-found defects fixed in-batch: concurrent same-checksum
      dedup losers colliding on ONE event id (terminal guard
      IntegrityError from worker threads) — _record now treats a
      lost exactly-once race as a clean loser; register_asset
      silently DROPPING a contradicting declared checksum instead
      of Class-B-rejecting (corrupt registration now rejected
      before storage); test-harness EPERM cascade (_JsonVault
      mkdir vs os.remove teardown) masking all M2/M3 results; and
      an invalid test premise (validate_variant_kind returns the
      SPEC dict, not a kind set).
      Standing owner gate: no storage endpoints or credentials
      (D-045) — none exist, none requested; binaries stay local
      behind the MediaStore seam; Phase 16 passing does NOT prove
      live cloud-storage compatibility.
- [x] Phase 15 — Content Calendar & Scheduling Engine — **CLOSED at
      foundation level (2026-09-17), D-093–D-096 all owner-approved**:
      D-093 contract (`local/canonical/scheduling_contracts.py`:
      canonical ScheduledPost — post_id, content_ref, targets =
      Phase 11 destination matrix, scheduled_for as the producer's
      own ISO instant, SHA-256 idempotency over (content_ref, sorted
      targets, scheduled_for); lifecycle SCHEDULED → DUE →
      DISPATCHED + CANCELLED (SCHEDULED/DUE) + RESCHEDULED as a
      SCHEDULED-only revision marker keeping the prior time; strict
      local Class-B validation; pure slot arithmetic flooring instants
      to configurable gap buckets that must divide 1440; due =
      scheduled_for <= injected now — the wall clock never enters any
      key or comparison); D-094 slot guard (`scheduling_engine.py` +
      `scheduling.slot_lock` schema: per-platform PK-as-lock claims,
      `active` flag keeps superseded rows as ledger history and makes
      freed slots re-claimable, conflicting plans record slot_conflict
      Class-B rejections that leave existing slots untouched, JSON
      parity backend); D-095 due scanner + bridge
      (`scheduling_worker.py`: durable-data-only reads in ingest_seq
      order, injected now_iso at exactly one boundary, bridge to
      FanOutEngine.route()+dispatch() via the provider-neutral
      FanOutBridge — the scheduler NEVER imports or re-implements
      publishing (AST-verified), receipts consumed and recorded,
      bridge failures recorded with the post left DUE for recovery,
      independent-post discipline, reconciliation from durable data
      only); D-096 mutability + audit (only pre-DISPATCHED posts
      mutable — dispatched/terminal mutations are recorded rejections;
      reschedule claims NEW slots first so a conflicting reschedule
      changes nothing and supersedes old slots into history on
      success; attempt-unique transition event ids from a durable
      count — conflicting duplicates surface as D-027 IntegrityError,
      never swallowed; calendar view rebuilt from durable events
      alone — fresh-engine parity tested).
      Phase 15 suite 24/24 zero-skip (21 offline + 3 live-PG E2E:
      real PgEventStore + PG slot_lock, schedule→conflict→
      reschedule→reclaim chain, 8-thread single-winner slot claim,
      due-scan → DISPATCHED with fresh-engine restart parity);
      battery 576/576 zero-skip; ladder 46/46; AST audit clean
      (zero network imports, zero publishing-module imports in
      scheduling modules — the D-095 boundary import-verified, zero
      decision verbs, zero os.environ); secret scan clean;
      diff-check PASS.
      Suite-found defects fixed in-batch: unreachable
      SCHEDULED→RESCHEDULED edge (key-guard ordering), superseded
      slots blocking re-claim + reschedule recording despite slot
      conflict (active-flag redesign + claims-new-first),
      reschedule event-id collision on retries (attempt-unique ids
      + IntegrityError never swallowed), and two invalid test
      premises (bucket flooring 09:20→09:15; fixed platforms on the
      shared live ledger — run-scoped platforms + delta assertions).
      Standing owner gate: no platform endpoints or credentials
      (D-045) — none exist, none requested; Phase 15 passing does
      NOT prove live platform compatibility.
- [x] Phase 14 — Notification System & User Alerts — **CLOSED at
      foundation level (2026-09-17), D-089–D-092 all owner-approved**:
      D-089 contract (`local/canonical/notification_contracts.py`:
      universal NotificationEvent — recipient, channel
      IN_APP/EMAIL/SMS/WEBHOOK, priority LOW..CRITICAL, versioned
      template registry with declared required variables + per-channel
      requirements, SHA-256 dedup over (recipient, channel, template,
      logical event_key) so reformatted retries collapse while
      distinct alerts differ; strict LOCAL Class-B validation before
      anything is queued — 15 rejection classes tested; quiet-hours
      and frequency caps as pure functions of the event's own
      timestamp + the durable ledger, CRITICAL bypass, no wall clock);
      D-090 vault + engine (`notification_engine.py` +
      `notifications.delivery_lock` schema: PK-as-lock exactly-once-
      per-channel claims — losers record duplicate_blocked and never
      dispatch; PG + JSON-parity backends; independent per-channel
      fan-out; durable status view rebuilt from store data only);
      D-091 outbox worker (`notification_worker.py` +
      `notifications.dead_letter` schema: drain from the durable
      queue view, exponential backoff = f(attempt_no) — 2/4/8/16/32/60
      cap, deterministic, no clock; transient retries return to
      QUEUED with every outcome advancing the lock row's attempt_no
      (restart-safe ladder); attempts-exhausted and Class-B go to the
      DLQ; rate-limit waits honored without consuming retry budget;
      no-adapter-bound and adapter-exception carriers recorded, never
      silent; reconciliation from durable data only);
      D-092 audit (every attempt/receipt/failure a D-027 event with
      redacted strings; status lifecycle PENDING → QUEUED →
      DISPATCHED → DELIVERED | FAILED | POLICY_DEFERRED |
      DUPLICATE_BLOCKED with terminal stickiness — late transient
      receipts never demote DELIVERED/FAILED).
      Phase 14 suite 26/26 zero-skip (22 offline + 4 live-PG E2E:
      real PgEventStore + PG delivery_lock + PG dead_letter,
      independent fan-out + delivery, same-key duplicate-block,
      retry ladder → DLQ → restart parity, Class-B DLQ row = HITL
      review material); battery 552/552 zero-skip; ladder 46/46;
      AST audit clean (zero network imports in canonical modules,
      zero decision verbs, zero os.environ — only the test-only
      stack guard and a docstring hit); secret scan clean;
      diff-check PASS.
      Suite-found defects fixed in-batch: PG DLQ read-shape bug
      (items() demanded 7 segments for 6-field rows — DLQ reads came
      back empty while admits accumulated), retry-ladder stall
      (transient outcomes parked at DISPATCHED, attempt counter
      never advanced), terminal-stickiness hole (late transient
      receipt demoted DELIVERED/FAILED), missing SMS-capable
      template (added order.shipped.v1), register row 30 repair
      (initial str_replace overwrote row 29's prefix — restored
      byte-identical from git, then inserted properly).
      Standing owner gate: no EMAIL/SMS/WEBHOOK endpoints or
      provider credentials (D-045) — none exist, none requested;
      nothing ever leaves the local stack; Phase 14 passing does
      NOT prove live provider compatibility.
- [x] Phase 13 — Analytics, Reporting & Metrics Engine — **CLOSED at
      foundation level (2026-09-17), D-085–D-088 all owner-approved**:
      D-085 canonical analytics model (`local/canonical/analytics_contracts.py`:
      metric vocabulary `publication_published` / `publication_failed` /
      `order_placed` / `order_completed` / `order_cancelled` /
      `revenue_minor`, deterministic hourly/daily/monthly windowing
      from each event's own `occurred_at` — no wall-clock; rollup math
      count-vs-sum per kind; merge = raw accumulator, finalize = the
      single serialization edge); D-086 projection engine
      (`analytics_engine.py` + `analytics` schema: ingest_seq cursor
      with exactly-once consumption, atomic advance of cursor +
      per-grain snapshots + metric_rollup cells in ONE statement,
      JSON parity store, deterministic rebuild);
      D-087 CampaignCorrelator (`analytics_worker.py`: publication ⟕
      order join on source campaign id within an hours-after-
      publication window, unattributed orders preserved — read-model
      join, zero hard cross-domain dependency); D-088 exporter +
      audit vault (JSON/CSV projections, SHA-256 window_hash
      idempotent generation — same inputs ⇒ same hash ⇒
      idempotent_hit, PgReportVault PK-as-hash on
      `analytics.report_audit` + JSON parity, audit trail of every
      request).
      Phase 13 suite 28/28 zero-skip (24 offline + 4 live-PG E2E:
      real PgEventStore → _PgCursorStore → PgReportVault, cursor
      advance + exactly-once, revenue delta attribution, rebuild
      byte-determinism over the full live history, fresh-engine
      cursor parity); battery 526/526 zero-skip; ladder 46/46;
      AST audit clean (zero network imports, zero platform/price/
      publication module refs — `publication_*` is the D-085 metric
      vocabulary, zero decision verbs, zero os.environ in canonical
      modules); secret scan clean; diff-check PASS.
      Suite-found defects fixed in-batch: PG snapshot shape bug
      (whole 3-grain dict written into every per-grain row ⇒ live
      incremental passes silently wiped rollups — live-only, JSON
      store unaffected; now per-grain rows + stale rows cleared +
      full live rebuild verified), CQRS write-orphan
      (`analytics.metric_rollup` written by nobody — now upserted
      inside the atomic advance), merge_rollups double-finalize +
      lost last_seq, PgReportVault missing `import sys`, and two
      live tests with invalid shared-store premises (rewritten to
      rebuild↔rebuild determinism and per-run revenue delta).
      Standing owner gate: live store credentials (D-045) — none
      exist, none requested; analytics never leaves the local stack.
- [x] Phase 11 — Cross-Platform Orchestration & Publication Fan-Out —
      **CLOSED at foundation level (2026-09-16), D-077–D-080 all
      owner-approved**:
      D-077 fan-out contract (`local/canonical/orchestration_contracts.py`:
      universal dispatch payload + strict local validation — job_id
      regex, sha-256 media hash, aspect-ratio whitelist — Class-B
      before any dispatch; destination matrix `KNOWN_TARGETS →
      transform_for_{instagram,telegram}` delegating final authority
      to the D-069/D-073 validators; deterministic truncation with
      recorded warnings; independent fan-out — no cross-target
      rollback anywhere); D-078 lifecycle + partial success
      (`orchestration_engine.py`: ROUTED → DISPATCHING →
      SUCCESS | PARTIAL_SUCCESS | FAILED, deterministic aggregation
      from DURABLE per-target outcomes — duplicate_publish_blocked
      counts as served, cancelled counts terminal; per-target receipt
      events + sequenced aggregate events on the D-027 store);
      D-079 coordinated schedule + anti-race (release_plan base +
      per-target stagger arithmetic, no wall-clock reads;
      `orchestration.fanout_lock` PG PK-as-lock — live-migrated + in
      schema.sql — proven single-winner under 10 threads, losers get
      already_claimed); D-080 resiliency (`orchestration_worker.py`:
      reconciliation scan from durable data only — repairs missing
      aggregates, re-dispatches ONLY failing targets, published
      targets never re-triggered; HITL cancel never reverts published
      platforms, rejected/unstarted targets abortable).
      Phase 11 suite 50/50 (incl. live-PG E2E through the REAL
      Phase 9/10 publishers + vaults, thread anti-race proof,
      restart-safety reconstruction); battery 461/461 zero-skip;
      ladder 46/46; AST audit clean (zero network imports, zero
      Woo/price/publication refs, zero decision verbs, zero
      os.environ access); secret scan clean; diff-check PASS.
      Suite-found defects fixed in-batch: lowercase-stage vs
      uppercase-vocabulary reconstruction bug (restart state wrongly
      DISPATCHING/None), aggregate event id collision vs D-027
      conflicting-duplicate (now sequenced per job, restart-safe),
      lost no-publisher-bound receipt (continue before persist),
      cancel semantics (terminal_reject targets are abortable).
      Standing owner gate: live platform credentials (D-045) — none
      exist, none requested.
- [x] Phase 10 — Telegram Platform Integration — **CLOSED at
      foundation level (2026-09-16), D-073–D-076 all owner-approved**:
      D-073 contracts (`local/canonical/telegram_contracts.py`:
      Text/Photo/Video/Document/MediaGroup schemas, strict local
      MarkdownV2/HTML parsing — escape_markdownv2/escape_html +
      validators, constraints: caption ≤ 1024, text ≤ 4096, album
      2..10 photo|video, file ≤ 50 MB, chat_id int|@channel,
      parse_mode ∈ {"", MarkdownV2, HTML}); D-074 vault + pacer
      (`telegram_publisher.py` + `telegram_adapter.py`:
      SHA-256 key over (chat_id, content_id, media_hash, text_hash,
      scheduled_slot), `telegram.publish_lock` PK-as-lock on live
      PostgreSQL, durable terminal guard, token-bucket pacer 30/s
      global + 1/s per-chat, reservations never drop); D-075 adapter
      (`telegram_adapter.py`: MockTelegramAdapter deterministic
      controls — 429+retry_after, blocked 403, chat-not-found 400,
      migrate-to-supergroup, timeout, 5xx — plus LiveTelegramAdapter
      with injectable transport behind TELEGRAM_LIVE_ENABLED + token
      gate; redact() strips bot<token> URL patterns and bare tokens
      from every error/DLQ/provenance string); D-076 outbox + DLQ
      (transactional outbox on the D-027 store, D-052-aligned
      classifier: A backoff / B terminal reject→DLQ / C
      retry_after-honoring cooldown / E queue freeze + HITL alert,
      D-026 provenance on every outcome).
      Phase 10 suite 51/51 (incl. 10-thread single-winner concurrency,
      live-PG E2E with restart safety, durable audit reconstruction);
      battery 411/411 zero-skip; ladder 46/46; AST audit clean (no
      Woo/price/publication path; env access only in the D-075 gate);
      secret scan clean; diff-check PASS. Suite-found defects fixed
      in-batch: unique blocked-dispatch event ids (concurrent loser
      collision), durable terminal guard before dispatch, pacer
      reservation only after vault claim. Standing owner gate: live
      Telegram Bot API credentials (D-045) — none exist, none
      requested.
- [x] Phase 9 — Instagram Integration — **CLOSED at foundation level
      (2026-09-16), D-069–D-072 all owner-approved**:
      D-069 contracts (`local/canonical/instagram_contracts.py`:
      PENDING → MEDIA_CREATE → CONTAINER_STATUS → MEDIA_PUBLISH →
      PUBLISHED state machine, FAILED terminal; local Class-B
      pre-dispatch validators — aspect ratio 1:1/4:5/16:9, caption
      ≤ 2,200 chars, ≤ 30 hashtags — invalid payloads rejected with
      ZERO network calls); D-070 idempotency vault
      (`instagram_publisher.py`: deterministic SHA-256 key over
      (content_id, media_hash, caption_hash, scheduled_slot),
      exclusive `instagram.publish_lock` PK lock on live PostgreSQL,
      absolute double-publish protection across restarts and
      concurrent dispatchers — 10-thread proof); D-071 adapter
      (`instagram_adapter.py`: MockInstagramAdapter zero-network +
      LiveInstagramAdapter with injectable transport,
      INSTAGRAM_LIVE_ENABLED + token construction gate, bounded
      container-status poller, redact() strips access tokens from
      every error/log/observability record); D-072 outbox + DLQ
      (transactional outbox on the D-027 store, classifier aligned
      with D-052: Class-A backoff retry / Class-B terminal reject /
      Class-C cooldown / Class-E queue freeze + HITL alert,
      dead-letter entries redacted + D-026 provenance-linked).
      Phase 9 suite 24/24 (incl. live-PG E2E, concurrency, restart
      safety); battery zero-skip; AST audit clean (no Woo/price/
      publication path; env access only in the D-071 gate).
      **M4 cross-batch fix:** PgEventStore pinned its constructor
      `source_system` and silently re-keyed every operation, ignoring
      the method-level argument — per-source isolation broke (rows
      landed under `notion`, `succeeded_references("instagram")`
      empty, event ids collided across sources). Fixed by threading
      the method-level `source_system` through all store operations
      (constructor value demoted to fallback); Phase 6/7 suites
      re-verified green (122 tests). Standing owner gate: live
      Instagram Graph API credentials (D-045) — none exist, none
      requested.
- [x] Phase 8 — AI Product Manager & Operational Observability
      — **COMPLETE (2026-09-16), D-065–D-068 all owner-approved**:
      D-065 unified observability (`local/canonical/`
      `ai_observability.py`, schema `ai.observe.v1`, correlation_id
      end-to-end, cost report by task/provider/day, D-045 redaction
      guard); D-066 live OpenAI/Anthropic adapters
      (`ai_providers_live.py`, injectable transport = zero network in
      tests, AI_LIVE_ENABLED + API-key construction gate, graceful
      fallback to MockAiProvider with observable D-065 record,
      BUDGET_EXCEEDED_HALT pre-dispatch quarantine); D-067 template
      registry (`ai_templates.py` + `local/templates/*/v1.0.0.json`,
      strict contract validation, monotonic semver, hash-pinned,
      drift fails loudly); D-068 HITL review inbox
      (`ai_hitl_service.py`: deterministic inbox, single + bulk
      approve/reject/edit, per-item independence, idempotent
      re-decisions, contract-validated human edits, D-065
      hitl_decision records). Phase 8 suite 42/42; battery 336/336
      zero-skip; AST audit clean (no Woo/price/publication path);
      E2E proven on live PostgreSQL. Standing owner gate: live AI
      credentials (D-045, register row 9) — none exist, none
      requested.
- [x] Phase 7 — AI Runtime (model routing, structured outputs,
      validation, cost control, provenance, logging, approval gates)
      — **CLOSED at foundation level (2026-09-16), M1–M4 complete**
      — **M1 done (2026-09-15)**: blueprint
      `docs/phases/phase-07-ai-runtime.md`; strict v1 output contracts
      + validator (`local/canonical/ai_contracts.py`, fixture-pinned);
      provider-neutral router + MockAiProvider + budget/rate
      guardrails + usage ledger (`local/canonical/ai_runtime.py`);
      D-050 boundary test-enforced (import-graph no-Red-path);
      **D-062/D-063/D-064 APPROVED (2026-09-15)**; no credentials
      exist or requested (D-045).
      **M2 done (2026-09-15)**: proposal lifecycle & HITL round-trip
      (`local/canonical/ai_proposal_lifecycle.py`) — PROPOSED →
      IN_REVIEW → ACCEPTED/REJECTED/MODIFIED_BY_HUMAN, every
      transition a D-027 event on the live PostgreSQL store,
      D-026 provenance per human decision + AI record advanced once
      at terminal decision, terminal decisions immutable (identical
      re-decision idempotent, changed re-decision refused),
      submit() refuses non-AiProposal envelopes, `|applied`
      bookkeeping excluded from lifecycle history, no-auto-advance
      API-shape tests.
      **M3 done (2026-09-15)**: concrete task implementations + batch
      execution (`local/canonical/ai_tasks.py`) — ContentIdeaTask /
      CaptionTask / DescriptionTask on the M1 contracts via the
      provider-neutral router (MockAiProvider, D-053); deterministic
      divergence detection vs approved vocabulary (D-029/D-031/D-032
      near-miss hashtags = Class B) and canonical records (unknown
      product_id, scope widening); dry-run mode (zero pipeline
      persistence; router metering stays ON so dry-runs cannot evade
      D-063); batch processing with hard-budget stop before dispatch;
      persist mode lands PROPOSED only via the M2 lifecycle (idempotent
      by deterministic tag; divergent output persists nothing).
      **M4 done (2026-09-16) — Phase 7 CLOSED at foundation level**:
      gate report `docs/reports/PHASE_7_GATE_REPORT.md`; M4 audit
      suite `local/tests/test_phase7_ai_runtime_m4.py` (23 tests:
      static AST path audit, dynamic conformance incl. conflicting
      re-delivery refused offline+live, cost-ledger audit, D-045
      provider-boundary audit, live-PG restart durability);
      hardening: AiProposal frozen (tamper-evident envelope); M4 audit
      also found + fixed a cross-cutting store defect (wall-clock
      received_at not a safe ordering key on VMs — monotonic
      ingest_seq/receive_seq ordering now, Phase 6 doc §7.1.6).
      Phase 7 total 100/100, battery 294/294 zero-skip.
      Standing owner gate: real AI provider selection + credentials
      (register row 9, D-045) — none exist, none requested; live
      provider compatibility NOT proven by Phase 7.
- [ ] Phase 7+ — Instagram, payment, shipping integrations
