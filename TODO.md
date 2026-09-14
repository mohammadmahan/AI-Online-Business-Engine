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
- [ ] n8n workflows (blocked — Phase 5)

## Blocked / do-not-start

Forbidden until their phase begins (MASTER_PLAN §16). Do not start
these even if they seem helpful:

- [x] ~~Phase 3 — WooCommerce foundation~~ — **unblocked (2026-09-12,
      owner opened Phase 3)**; Batch 1 design recorded via
      D-034–D-045 (see below)
- [ ] Phase 4 — Infrastructure (no hosting, DNS, backups setup)
- [ ] Phase 5 — n8n foundation (no workflows, no credentials)
- [ ] Phase 6 — Notion Business OS (no Notion workspace automation)
- [ ] Phase 7+ — AI Runtime, Instagram, payment, shipping integrations
