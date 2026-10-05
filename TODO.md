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

## Phase 2 — Product Data System (closed)

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

## Phase 2.5 — Business Data Configuration (closed)

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

## Phase 3 — WooCommerce Foundation (closed)

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
- [x] **Live Woo REST client shipped 2026-09-21** (`local/canonical/`
      `woo_live.py`): the real adapter implementing the SAME interface
      as `services/mock_woo.py` (that module's stated design intent).
      HTTP Basic auth over HTTPS (Woo REST v3 documented pattern) with
      credentials resolved from `WOO_LIVE_ENABLED` + `WOO_STORE_URL`
      + `WOO_CONSUMER_KEY`/`WOO_CONSUMER_SECRET` env references only
      (fail-closed, D-045); **D-050 enforced at the PAYLOAD level** —
      publish/private status, `catalog_visibility=visible`, and price
      writes on published products are RED-tier and refuse BEFORE any
      request is built unless `authorized=True` (hidden/draft
      projections and taxonomy seeding stay YELLOW, matching the
      SyncEngine tier table); taxonomy validated against the approved
      registries (D-031/D-033 pairs, D-032 codes, D-030 O/I/L gate
      with the D-057 LRG sanction) locally; product/post publishing
      contracts + media-reference seam (D-040/D-049 — Woo holds
      references only); deterministic D-052-aligned error carriers
      (401/403→E, 429→C Retry-After, 5xx→A, 400→B) and ck_/cs_
      redaction (D-124). Health/contract drill
      `local/scripts/validate_wordpress_live.py`: offline synthetic
      drill + opt-in READ-ONLY `/wc/v3/system_status` probe behind
      the full gate (exit 2 without — none exist). Standing owner
      gate: no Woo store credentials exist, none requested (D-045);
      live store connection = owner-gated Phase 4 G1/G2 territory.
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
      the real WooCommerce connection. **Live wiring core side shipped
      (2026-09-20, report §8):** webhook contracts + HMAC auth +
      deterministic dispatcher (`canonical/n8n_webhook_contracts.py`)
      and `local/scripts/validate_n8n_live.py` (offline + live modes;
      API round-trip behind the N8N_API_PROBE/N8N_API_KEY owner gate);
      battery 18/18 ×2 green.

## Active Phase — Infrastructure Deployment & Staging Orchestration
(Dokploy Stage C rollout and beyond) — handoff ACTIVE; every stage
owner-gated, nothing provisioned, connected, or deployed

Previous phase record — Live Wiring Program-Level Completion
Reconciliation (registry closeout, D-169) — COMPLETE — **THE LIVE
WIRING PROGRAM (PHASES 5–18) IS COMPLETE — OFFICIALLY CLOSED
(D-170 owner sign-off, 2026-09-29)**

Registry note: D-168 took slot 18 = `canonical.ai_hitl_service` per
the D-154 cross-walk — the final ignition. The D-169 reconciliation
re-verified the whole track in one place: the REAL phase 5–18
chain-builders re-ran the authentic chain D-154 → … → D-168 (14
digests byte-exact, rooted, linkage unbroken, byte-stable with the
governance record), the full-suite slot census reconciled against
the LIVE D-154 registry (12 census rows VERIFIED/WIRED, slot 14
SEALED per D-163, slot 18 LOCKED), and the fail-closed invariants
held end to end. Verdict `PROGRAM_RECONCILED`, attestation digest
`c30d3047d28d6c69…`, 17/17 rule checks PASS. NO further Live Wiring
phases exist — the track is CLOSED; production activation stays
owner-gated (D-139).

- [x] D-169 engine — `live_wiring_completion_reconciliation.py`
      (REC-01..REC-05, fail-closed, injected chain/census
      providers, exactly-once emission guard, deep redaction D-124,
      AST-pure — no os/socket/subprocess imports)
- [x] REC-01 — the REAL phase 5–18 chain re-run: 14 digests
      recompute byte-exactly, rooted in the D-112 ledger (anchored
      by the D-154 certificate row), linkage unbroken, byte-stable
      with the governance record (D-167 `048952dc…` full-match,
      D-168 `0026f4c9…` full-match); chain digest `97d88f42…`
- [x] REC-02 — the full-suite census against the LIVE D-154
      `ENTRY_POINTS`: 12 rows (5–12, 15–18) present+VERIFIED+WIRED,
      byte-exact seam matches, slot 14 SEALED (D-163), slot 18
      LOCKED to `canonical.ai_hitl_service`
- [x] REC-03 — the fail-closed invariants: zero durable footprint,
      the REAL D-027 store carrying ONLY `hitl::` rows (15), ZERO
      human-surface egress, egress-marker sweep clean, AST purity
- [x] Battery `test_live_wiring_completion.py` 50/50 ×2 (PASS over
      the REAL chain re-run; every refusal class; redaction; AST)
- [x] Full regression 2225/2225 ×2 consecutive green across 84
      modules (2175 + 50; the 83 untouched modules still carrying
      exactly 2175)
- [x] Report `docs/deployment/phase-19-reconciliation-report.md`
      (re-run digest table, all-slot census cross-walk, invariant
      matrix, program completion boundary)
- [x] Owner review of the D-169 program closeout record
      (attestation digest `c30d3047…`) — **SIGNED OFF (2026-09-29;
      D-170)** — closes the Live Wiring program

Post-closeout verification sync (2026-09-28, commit `eaefa3b`): the
stage-e dirty-tree battery tests were made deterministic on a
committed tree (probe-file setUp/tearDown; a clean tree now asserts
GO — the old tests assumed the battery runs dirty by design, which
no longer held once D-169 landed); full regression re-run ×2 on the
committed tree — **2226/2226 green across 84 modules** (2175 + 50
+ 1 clean-tree GO counter-pin), zero fails, no skips.

Reality check (2026-09-27, this reconciliation): the D-163
disposition and the D-164 engine, battery, report and governance
were **landed in commit `f46d8b6`**
(`phase14.scheduling_wiring_attestation.v1`, battery 44/44 ×2, full
regression 1999/1999 ×2 across 79 modules); governance hashes and
the status timeline were synced in the follow-up docs commit. The
items below are the phase's standing execution checklist — CLOSED:
the owner review completed 2026-09-29 (D-170). Phases 10 (D-160,
`d88325d`), 11 (D-161, `d284dd9`), 12 (D-162, `2218702`),14 (`f46d8b6`), 15 (`90e2eb1`), 16 (`2144df5`), 17 (`ccba01f`), 18
(`4c224cd`) and the D-169 reconciliation (this phase) are CLOSED at
owner-reviewed (D-170, 2026-09-29).

- [x] D-163 — the CRM-not-needed conditional formally resolved
      NEGATIVE with the pillar-sufficiency evidence (WooCommerce
      facade hermetic-proven, Notion D-156, n8n D-155); registry
      slot 14 stays bound to the existing
      `commerce.sync_orchestrator` facade; no CRM built or ignited;
      the D-154 certificate unaffected
- [x] Upstream attestation verification — SCH-01 recomputes the
      `phase12.shipping_wiring_attestation.v1` canonical bytes and
      matches the D-112 rooting row
      `phase12_shipping_wiring_attestation` BEFORE any calendar
      call (refusals never construct the engine or the store)
- [x] Seams asserted against the repo and the D-154 registry —
      `canonical.scheduling_engine` (ENTRY_POINTS[15] "Marketing
      Automation" per the D-154 cross-walk, re-asserted
      defense-in-depth), `canonical.scheduling_contracts`,
      `canonical.scheduling_worker`, `canonical.orchestration_engine`
      (ENTRY_POINTS[13]), `services.sync_engine`; census Phases
      5–12 VERIFIED/WIRED (slot 14 deliberately not required)
- [x] Scheduling contracts through the REAL validator — 7
      post-rejection classes with named reasons; deterministic
      SHA-256 idempotency keys over (content_ref, sorted targets,
      scheduled_for); pure 15-minute slot-bucket arithmetic
      (same-bucket keys collide cross-post, never cross-platform);
      pure due semantics; clock-free throughout (D-093)
- [x] Dry-run scheduling cycle over the REAL SchedulingEngine —
      identical re-schedule → `retried` (same key); conflicting
      payload under the same post_id → `IntegrityError`; a
      same-(platform,bucket) post is a durable SLOT_CONFLICT
      rejection (the post is NOT scheduled); reschedule claims NEW
      slots FIRST, supersedes old (the ledger keeps the row) and
      the freed slot is re-claimable; SCHEDULED→DUE→CANCELLED with
      terminal immutability (cancel AND reschedule on CANCELLED
      refuse); the due-notification event through the REAL
      FanOutEngine with publisher-less binds under an EPHEMERAL
      D-079 lock; the calendar view rebuilt from DURABLE events
      alone matching the driven lifecycle exactly (zero drift);
      the publish-marker sweep over the LIVE store records plus a
      refusal of any non-ephemeral slot backend; zero-residue
      cleanup
- [x] Lock hygiene — `_EphemeralSlotLocks` injected (claim/supersede/
      history parity with `_JsonSlotLocks`, ZERO durable footprint);
      no `scheduling.slot_lock` PG rows and no shared-file writes
      (the D-079 discipline applied to the calendar)
- [x] Attestation emission — canonical `phase14.scheduling_wiring_attestation.v1`
      with SHA-256 `attestation_digest`, exactly once per run
      (aborts included)
- [x] Test battery — `local/tests/test_live_wiring_phase14.py`
      44/44 ×2 over the authentic D-162→…→D-154 chain; full
      regression 1999/1999 ×2 across 79 modules (the 78 untouched
      modules still carrying exactly 1955)
- [ ] Owner review of the D-163 + D-164 completion record
      (attestation digest `29b3c5df…`, commit `f46d8b6`) — closes
      the phase
- [ ] Probe-safe locking in the canonical layer (fold the ephemeral
      D-079 fan-out lock AND an ephemeral slot-lock mode into
      `FanOutEngine` / `SchedulingEngine` as probe modes) — prevents
      future probe authors repeating the default-lock-claims-PG
      incident (carried over from Phases 10/11/12)

## Phase 27 — Admin Dashboard Scaffolding & Control Plane (D-171)

Unified Web Control Plane — **D-171 Approved (2026-10-03,
owner-directed)**. Plan anchor: `MASTER_PLAN.md` §13 Phase 19 (Custom
Internal Tools — "business command centers"). NOTE: this is the
admin-dashboard track, **not** MASTER_PLAN §13 Phase 27
(Optimization), which is distinct and unaffected. Spec:
`docs/decisions/D-171-unified-web-control-plane.md`.

Standing gates (unchanged): nothing installed, connected, provisioned,
or activated; no live credentials exist or are requested (D-045);
production activation remains the sole owner-gated act (D-139); the
plane is never an authority (D-026/D-027/D-146 preserved). The
existing static `dashboard/` snapshot stays untouched.

Design standards are MANDATED (not advisory) by
`.claude/skills/ui-ux-pro-max` v2.13.0: RTL + Vazirmatn; WCAG 2.2 AA
contrast (text ≥ 4.5:1, large text ≥ 3:1, non-text/icons/borders ≥
3:1, measured independently in BOTH themes); touch targets web ≥
24×24 CSS px (or documented exception), mobile ≥ 44×44 pt / ≥ 48×48
dp, ≥ 8px gap; non-color-dependent semantics (icon + Persian label +
English status code); no raw hex in components; SVG icons only.

**Numbering note (2026-10-03):** the owner's execution directives split
this roadmap into 27.1 tooling, 27.2 app shell, and 27.3 executive
overview, shifting the D-171 §4 phases to 27.4–27.8. D-171 §4 content
is unchanged; only these TODO labels follow the directives.

**Numbering note (2026-10-04):** the owner's Inventory & Canonical SKU
Control directive places Inventory at **27.5**, ahead of Telemetry &
Gates; those two labels swap below (D-171 §4 content unchanged).

### Phase 27.1 — Foundation & Tooling Setup

Owner directive 2026-10-03 (Foundation & Tooling Setup).

- [x] Next.js (App Router) + Tailwind CSS scaffold committed to the
      repo (no package installed into the engine's Python tree)
- [x] Strict RTL layout (`dir="rtl"`, `lang="fa"`), Vazirmatn
      typographic hierarchy self-hosted via `next/font` with
      `system-ui` fallback and `font-display: swap`
- [x] Semantic color-token layer (`#1E40AF` primary, `#F8FAFC` /
      `#0F172A` canvases, `#FFFFFF` / `#1E293B` cards, `#D97706` /
      `#B45309` accent/warning, `#15803D` / `#4ADE80` success,
      `#DC2626` / `#F87171` destructive)
- [x] Contrast audit in both themes, enforced fail-closed
      (`npm run check:contrast`): 52 pairings, 0 violations; non-text
      ≥ 3:1; white text forbidden on `#D97706`
- [x] Token discipline enforced: the gate scans every file under
      `src/` and fails on any 6-digit hex literal outside the three
      token-definition files
- [x] Radix UI / Shadcn baseline primitives (Slot, Dialog) with 8px
      radius, 44×44 px minimum targets, and ARIA attributes
- [ ] Auth layer with fail-closed sessions; no token persisted in
      browser storage (outside the owner's 27.1 scope — pending)
- [ ] Direct canonical PostgreSQL (D-055) connection — READ-ONLY
      role, bounded pool, parameterized allow-listed queries only
      (deferred to live wiring; 27.3 renders a labeled mock)

### Phase 27.2 — App Shell & Navigation Structure

Owner directive 2026-10-03 (App Shell & Navigation Structure).

- [x] Global shell: responsive RTL sidebar + header + main content
      container, with a skip-link to main content
- [x] Master Layout: sidebar navigation, header, light/dark theme
      toggle with a no-flash pre-paint bootstrap, and a connection
      status indicator (mock hook; live probe deferred)
- [x] Header extras: environment badge, system status banner, and an
      emergency kill-switch placeholder that is inert and says so
- [x] Seven canonical routes scaffolded (`/dashboard`, `/hitl-queue`,
      `/inventory`, `/automations`, `/ai-engine`, `/orders`,
      `/settings`) with Persian titles, breadcrumbs, and card
      containers
- [x] Accessibility: `aria-current` on the active route, visible
      focus rings, reduced-motion respect, SVG icons only, and
      24 px web / 44 px coarse-pointer target floors

### Phase 27.3 — Executive Overview Dashboard

Owner directive 2026-10-03 (Executive Overview). `/dashboard` is
upgraded from its stub to the executive surface.

- [x] System health grid: PostgreSQL / Dokploy / n8n / Walrus with
      explicit UNKNOWN or UNAVAILABLE (danger) states — absent
      evidence is never green
- [x] Executive KPI grid (4 columns, responsive) with trend
      indicators and non-color-only direction cues
- [x] Pending-approvals quick list (top 3, linking to
      `/hitl-queue`) and recent system events (last 5, D-121 trace
      ids)
- [x] Emergency action trigger cards (soft-pause, system-wide flush
      preview) — preview-only, disabled with an explicit Persian
      reason
- [x] Typed contracts in `src/types/telemetry.ts` +
      `src/types/dashboard.ts` and a deterministic mock provider in
      `src/lib/mock/dashboard-data.ts` behind a single
      `DashboardDataSource` swap seam
- [x] Zero external network calls in the mock layer; deterministic
      values (fixed seed, fixed instants) so the page prerenders
      statically
- [x] Fail-closed consistency guard: a snapshot claiming `ok` while
      any of its own metrics read NOT_PROBED/UNKNOWN/NOT_CONNECTED
      throws at build time instead of rendering a green badge
- [ ] Live data from the canonical SSOT (live-wiring phase) — this
      phase is mock-only by design

### Phase 27.4 — HITL Approval Center

Owner directive 2026-10-04 (HITL Review Queue). The canonical
vocabulary is mirrored from `local/canonical/hitl_contracts.py`
(D-105/D-106) — queue types, lifecycle states, roles and the D-101
severity/category taxonomy are the engine's own values, not UI
inventions.

- [x] Card-table over AI decisions: severity, category, source,
      age, status (severity-first ordering; `sortBySeverityFirst`)
- [x] Diff drawer for payload and `payload_override` — native
      `<dialog>` (focus trap and Escape for free), per-field
      current-vs-proposed table
- [x] Reasoning log rebuilt from D-027 events — never raw model
      chain-of-thought; each step carries its D-121 trace id
- [x] Filters (severity / status / free text) as client state only:
      filtering never mutates a ticket, and the hidden count is
      stated as text
- [x] No-token ⇒ action disabled; single-winner claim semantics
      preserved; irreversible acts require a second confirmation
      (`ESCALATED` carries `CONFIRM_2X`)
- [x] Fail-closed consistency guard: a snapshot claiming a state the
      engine cannot produce throws at BUILD time instead of
      rendering — verified live against two injected violations
      (enabled action without token; `PENDING_REVIEW` carrying a
      reviewer), each of which failed the build
- [x] Zero external network calls in the mock layer; fixed literal
      instants so the queue prerenders statically in both themes
- [ ] One-click actions routed through the REAL HITL engine
      (D-068 / D-168) — the four actions are rendered and DISABLED
      with their own stated reason; the UI neither mints nor holds a
      single-use owner token and has no signing key (D-146). Gated on
      live wiring.
- [ ] Every action produces one D-121 traceable ledger record — no
      action can execute in this phase, so no such record exists yet.
      Gated on the same live wiring as the item above.

### Phase 27.6 — Telemetry & Gates

Owner directive 2026-10-05 (Telemetry, Container Health & Pipeline
Gates). `/automations` is upgraded from its stub to a mock-backed,
read-only telemetry plane; the D-171 §5.4 bullets the directive did not
scope stay unchecked below.

- [x] Typed contracts in `src/types/telemetry.ts`: container health for
      the five named surfaces (postgres, n8n, redis, dokploy, walrus)
      with `HEALTHY`/`DEGRADED`/`DOWN`/`UNKNOWN`, CPU/memory/uptime,
      port mapping and last-probe instant; pipeline gates `V-01`..`V-10`
      with `PASS`/`BLOCKED`/`EVALUATING`/`BYPASS_PREVENTED`, evidence
      staleness and the D-121 audit record; queue telemetry (Redis
      depth/throughput, n8n active/waiting/failed); and gated action
      specs whose `blockedReasonFa` is non-optional
- [x] Deterministic mock provider in `src/lib/mock/telemetry-data.ts`
      with Persian metrics for all containers and V-01..V-10 — zero
      external network calls, fixed literal instants, so the page
      prerenders statically byte-identically
- [x] Fail-closed build-time invariant guard
      (`assertTelemetryConsistency`): a snapshot throws at BUILD time
      when a container marked `DOWN` carries live metrics, or when a
      gate whose status is not `PASS` claims to pass — plus absent/stale
      evidence on a PASS gate, missing audit reasons on
      BLOCKED/BYPASS_PREVENTED gates and actions enabled without token +
      signed path; verified live against two injected violations, each
      of which failed the build with the exact guard message, source
      restored byte-identical (sha256)
- [x] Scenario harness behind `CP_TELEMETRY_SCENARIO`: `steady`
      (default), `degraded-pipeline`, `gate-blocked`; an unrecognised
      value falls back to `all-unknown`, which renders NO_DATA with
      UNKNOWN containers, EVALUATING gates and unread queues
- [x] Container health grid — CPU/memory meters drawn from real
      readings only; a `DOWN` or `UNKNOWN` surface renders no bar and
      states `METRICS: UNAVAILABLE`; incident notes, probe instants and
      the concrete `containerRef` (non-null only where a manifest names
      a service; Walrus is PLANNED, D-142)
- [x] Gates matrix V-01..V-10 — the canonical Cutover Verification
      Matrix semantics (D-145) plus the Stage-F single-use owner
      authorization (`V-10`, D-146/D-147): verifier FAIL → `BLOCKED`,
      exit 2 → `EVALUATING`, V-10 refusal → `BYPASS_PREVENTED`; evidence
      reference per gate with `FRESH`/`STALE` labeled, absent evidence
      never green
- [x] Queue & throughput monitor — Redis depth + throughput and n8n
      active/waiting/failed with derived pressure against fixed
      thresholds; an unread broker is `UNKNOWN`, never a zero-depth
      queue
- [x] Emergency gate override panel rendered DISABLED with per-action
      stated reasons (force-gate / restart / flush-queue): no
      single-use owner token exists here (D-146) and no signed write
      path is connected (D-171 §6)
- [x] Audit rationale drawer for blocked / bypass-prevented gates as a
      native `<dialog>` — keyboard-accessible with platform focus trap
      and Escape-to-close, read-only by construction
- [x] Full RTL + Vazirmatn layout verified in a production build in
      both themes, with zero console errors
- [ ] Live probes for the real containers (`engine-local-*` /
      `engine-staging-*`) — this phase reads the deterministic mock
      only; a live probe requires credentials the UI must never hold
      (D-171 §6)
- [ ] Failure tracking with D-121 trace context and ledger links — the
      audit reasons and trace ids are rendered; ledger links need the
      live ledger read path
- [ ] DLQ depth and listing — the queue monitor covers depth,
      throughput and recent failures; a DLQ panel needs the live queue
      API

### Phase 27.5 — Inventory & Canonical SKU Viewer

Owner directive 2026-10-04 (Inventory & Canonical SKU Control).
`/inventory` is upgraded from its stub to a mock-backed, read-only
inventory control plane; the D-171 §5.3 bullets that the directive did
not scope stay unchecked below.

- [x] Typed contracts in `src/types/inventory.ts` mirroring the
      canonical product/inventory schema: Product ID `P#####`, Variant
      ID (canonical UUIDv4) and SKU `P#####[-CC][-SS]` with approved
      D-032 axis codes (D-014/D-015/D-017), Persian product name,
      integer Toman price (D-010), stock quantity + safe threshold,
      sync status (`IN_SYNC`, `PENDING_SYNC`, `SYNC_ERROR`,
      `DRIFT_DETECTED`), WooCommerce mapping ids (D-046 / `woo_live.py`)
      and lock state (Price Freeze / Out-of-Stock Override)
- [x] Deterministic mock provider in `src/lib/mock/inventory-data.ts`
      with Persian catalog samples across tech, digital and physical
      accessories — zero external network calls, fixed literals, so the
      page prerenders statically byte-identically
- [x] Fail-closed build-time invariant guard
      (`assertInventoryConsistency`): a snapshot throws at BUILD time
      when (a) a row with `stock_qty <= safe_threshold` carries no
      low-stock alert, or (b) a `DRIFT_DETECTED` row is marked
      clean/synced — verified live against both injected violations,
      each of which failed the build, source restored byte-identical
- [x] Scenario harness behind `CP_INVENTORY_SCENARIO`: `steady` (default),
      `low-stock-surge`, `sync-drift`; an unrecognised value falls back
      to `all-unknown`, which renders NO_DATA without any counts
- [x] Metrics banner — Total SKUs, Low Stock Warnings, Out of Stock and
      active WooCommerce Drift count — derived from the rendered rows and
      guarded against disagreement
- [x] Search & filter controls: SKU/title search, sync status, stock
      category and price range; an invalid range is explicit and yields
      no rows rather than silently ignoring the filter
- [x] Dense RTL SKU table: integer-Toman price formatting, stock against
      threshold, non-color-only status badges, and an expandable row
      carrying the WooCommerce sync history (D-121 trace per step),
      mapping ids, lock reason and D-026 provenance
- [x] Manual sync / override gate rendered DISABLED with its own stated
      reasons — no owner token (D-146) and no canonical/webhook write
      path — preserving the fail-closed rule that no control looks live
      while doing nothing (D-171 §6)
- [x] Product ID / Variant ID / SKU displayed separately, never derived
      from each other (D-015)
- [ ] Data-dense table with keyset server-side pagination (stable
      under concurrent data change) — the 14-row mock needs none; gated
      on the live read path
- [ ] Inline edit (price, stock, status) with pre-submit validation
      and rollback on error — deliberately absent while there is no
      write path (same gate as the action panel)
- [ ] Sync status with WooCommerce (D-003, D-034–D-045) and Notion
      (D-060, D-156); conflicts explicit and fail-closed — the
      WooCommerce status/drift half is delivered and guarded; Notion
      remains pending
- [ ] D-011 provenance and missing-data states surfaced per value —
      the row carries D-026 source/review state; per-value provenance
      needs the D-026 store
- [ ] CSV export with rate limiting and a mandatory ledger record

### Phase 27.7 — AI Ops & Shared Memory Hub

- [ ] Memory-layer status (Walrus / D-142) — `NOT_CONNECTED` shown
      explicitly until the D-045 owner gate is passed; never
      fabricated data
- [ ] Agent observability: execution routes, tools invoked, success
      rate, latency
- [ ] Token and cost analytics per route/model under the D-063 /
      D-127 ceilings
- [ ] AI proposal drafts and their D-060 lifecycle states
- [ ] No provider call originates from the UI; no credential is ever
      rendered

### Phase 27.8 — Commerce & Analytics

- [ ] Orders table with channel tags (telegram / instagram_dm /
      web_store) along the D-081 lifecycle
- [ ] Order detail: items with SKU, status history, D-084 receipts
- [ ] Payment gateway log fully masked — zero PAN, auth code, or
      gateway secret (D-114 / D-124)
- [ ] Shipping status with provider UNSELECTED (open decision 11)
- [ ] Invoice issuance in integer Toman, no decimals (D-010)
- [ ] Transactional analytics (revenue, conversion, basket, returns)
      rebuilt from SSOT events
- [ ] **DRY-RUN ONLY** until the owner selects the payment provider
      (open decision 10) and shipping provider (open decision 11) —
      no real payment path exists in the UI

### Phase 27 standing gates

- [ ] Owner review of each phase completion record before the next
      phase starts (PROJECT_RULES §3, D-139)
- [ ] No production activation, provisioning, or live credential use
      is authorized by D-171

## Forward previews

- [x] Live Wiring program-level completion reconciliation — **DONE
      (D-169)**: every registry slot is dispositioned (slots 5–13
      and 15–17 VERIFIED/WIRED, slot 14 closed CRM-not-needed per
      D-163, slot 18 TAKEN by the HITL ignition per D-168); the
      full attestation chain D-154 → … → D-168 re-verified against
      the D-154 certificate (14 digests byte-exact, rooted in the
      D-112 ledger, linkage unbroken), the all-slot census
      reconciled against the LIVE registry, the fail-closed
      invariants green (zero human-surface egress, zero durable
      footprint, AST purity); verdict `PROGRAM_RECONCILED`, digest
      `c30d3047d28d6c69…`; battery 50/50 ×2; full regression
      2225/2225 ×2 across 84 modules. The Live Wiring program is
      COMPLETE — the standing owner gates remain: owner-authorized
      controlled activation (D-139 preflight → dry run → canary →
      observation → promotion; Iranian payment provider (open
      decision 10) and shipping provider (open decision 11) must be
      selected before payment-capture and shipping-purchase
      go-live), and owner review of the Phase 14–18 completion
      records (D-164–D-168)
- [ ] Owner-authorized controlled activation (D-139 preflight →
      dry run → canary → observation → promotion) — a separate,
      explicit, one-time owner decision; Iranian payment provider
      (open decision 10) and shipping provider (open decision 11)
      must be selected before payment-capture and shipping-purchase
      go-live

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
      **Live wiring shipped 2026-09-21 (outbound client contracts on
      the D-060 seam):** `local/canonical/notion_live.py` —
      `LiveNotionClient` (construction-gated under D-045:
      `NOTION_LIVE_ENABLED=true` + `NOTION_API_KEY` both required,
      injected transport mandatory — direct HTTP forbidden; token
      redacted from every escaping error), safe block/page mapping
      (`to_notion_blocks`/`from_notion_page`: content model ⇄ Notion
      children byte-equal, local Class-B rejections BEFORE any
      request build, unknown block types skipped forward-safely),
      deterministic `NotionPacer` at Notion's documented 3 req/sec
      average (1-second sliding window; waits returned as verdicts,
      caller owns sleeping), jitter-free exponential backoff PLANS
      with Retry-After floor (deterministic, D-126 precedent; no
      sleeps in the pure module), D-052-aligned classification
      (429→C carrying retry_after, 401/403→E human-gated,
      5xx→A transient, 400 validation→B terminal), and
      `redact_notion` stripping token material AND object ids
      (D-124 zero-leak). Health/contract drill
      `local/scripts/validate_notion_live.py`: offline synthetic
      round-trip (gate matrix, mapping, limiter, taxonomy,
      redaction) + opt-in read-only `/v1/users/me` live probe behind
      the same gate (exit 2 without — none exist). Suite 31/31 ×2;
      battery 1013/1013 ×2, zero skips. Standing owner gate: no
      Notion credentials exist, none requested (D-045) — live
      workspace automation remains the owner-gated milestone.
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
- [ ] Work item — **Portable multi-agent shared-memory layer (MemWal)**
      — **FOUNDATION IMPLEMENTED (2026-09-22; D-142 Approved)**:
      local-first memory layer shipped behind the injected,
      provider-neutral seam — `local/src/memory/vector_store.py`
      (pgvector-compatible SSOT store: pinned DDL, HNSW hook,
      deterministic summarization pruning, deep zero-leak redaction
      on write AND read) and `local/src/memory/memwal_adapter.py`
      (portable hash-chained `memwal.wal.v1` artifacts, offline-first
      sync with transparent local-SSOT fallback, D-125      snapshot composition). Remaining: Walrus/relayer connectivity at
      live-AI-integration time — external connectivity and
      credentials remain owner-gated (D-045); **nothing installed,
      connected, or integrated** on the external side; memory writes
      stay non-authoritative (D-026/D-027); zero-leak redaction
      enforced (D-114/D-124). **Consumers wired (2026-09-22):**
      `local/src/ai/memory_interceptor.py` — Phase 7/8 pipelines get
      memory context via `prompt_payload["memory_context"]`
      (guidelines / similar interactions / session summary) and
      completed interactions + evaluation summaries are written back
      behind a new D-127 `memory_ops` budget resource; EVERY memory
      hop degrades gracefully (store failure, budget refusal, missing
      store ⇒ zero-shot continuation, honest per-op reports) and the
      canonical AI boundary is untouched. Stage D smoke gains S-07
      (Stage H export→dry-run-import parity proof inside every smoke
      run; 11/11). `test_memory_ai_integration.py` 17/17 ×2.
      **Publishing feedback loop (2026-09-22):**
      `local/src/publishing/` — context-aware orchestrator over the
      canonical Phase 10 calendar + Phase 11 outbox publishers
      (schedule → DUE → per-target dispatch → deterministic retry
      ladder → durable DLQ rows in the SSOT → budget-gated engagement
      feedback into VectorStore + WAL export). At-most-once preserved
      end-to-end (terminal-post skip + canonical vault guard);
      receipts/deep-redacted everywhere; `memory_interceptor` reused
      for budget gating. `test_publishing_pipeline_e2e.py` 10/10 ×2.
      **Commerce & workspace sync (2026-09-22, Phase 13–16 facades):**
      `local/src/commerce/sync_orchestrator.py` — bidirectional
      WooCommerce ⇄ SSOT: HMAC-SHA256 fail-closed webhook intake →
      canonical OMS lifecycle (fingerprint-addressed at-most-once;
      replay ⇒ duplicate, conflicting payload ⇒ conflict verdict),
      SSOT-first outbound transitions with D-052-classified sync
      results, refunds routed through the canonical lifecycle;
      `local/src/integrations/notion_adapter.py` — replication facade
      over the shipped Notion boundary (injected provider D-045,
      canonical ingest idempotency, backpressure fails closed,
      D-124-redacted payload builders); `local/src/commerce/
      support_memory_bridge.py` — Phase 16 support agent reads the
      D-142 vector store (FAQ/product/policy knowledge, budget-gated,
      redacted before embedding) plus an injected SSOT order lookup
      (PII-safe refs only), zero-blockage template fallback on any
      failure, memory never order-authority.
      `test_commerce_and_workspace_e2e.py` 24/24 ×2.
      **Analytics & strategy (2026-09-22, Phase 17/18 facades):**
      `local/src/analytics/campaign_correlator.py` — deterministic
      ROAS / funnel / engagement-to-revenue attribution over the
      canonical D-087 correlator (48h window, latest-publication
      join, unattributed orders preserved); winning-campaign
      summaries deep-redacted BEFORE embedding and persisted through
      the D-142 memory write path (D-127 `memory_ops` gated) plus
      portable `memwal.wal.v1` WAL export; `local/src/analytics/
      strategy_optimizer.py` — deterministic heuristic floor for
      posting-bucket / product-category / content-theme
      recommendations, and a fail-closed telemetry circuit
      (publish-failure / webhook-drop / cart-abandonment thresholds;
      missing or malformed telemetry alerts rather than passing;
      sink failure latches the      circuit OPEN until operator reset).
      `test_analytics_and_strategy_e2e.py` 25/25 ×2.
      **Alerting & learning loop closed (2026-09-22):**
      `local/src/analytics/telemetry_notification_bridge.py` —
      `TelemetryCircuit` sink mapping onto the canonical D-089
      boundary (validate → policy → D-090 vault → durable QUEUED):
      missing/malformed telemetry pages CRITICAL (bypasses quiet
      hours), breaches page HIGH; epoch-keyed `event_key` coalesces
      repeated breaches while the circuit is latched (D-090
      DUPLICATE_BLOCKED), operator `reset()` + `on_circuit_reset()`
      opens a new epoch; deep-redacted variables only; transport
      failure ⇒ structured `BridgeReport` (rejected/transport_error)
      — never silently marked delivered.
      `local/src/ai/campaign_winner_context.py` — Phase 7/8 prompt
      adapter over the persisted `campaign-winners` session:
      bounded retrieval (`max_winners`, `max_chars`), seq-desc
      deterministic total order, defensive parser (redacted themes
      dropped), D-127 `memory_ops` pre-dispatch gate, non-mutating
      payload merge under `memory_context.winners_block`, zero-shot
      degradation on any store/budget failure.
      `test_notification_and_winner_context_e2e.py` 20/20 ×2.
- [ ] Work package — **Dokploy Deployment Integration** — **ACTIVE
      (2026-09-20; D-141 Approved — planning + Stages A–B only)**:
      optional, replaceable deployment-management layer for
      Staging/Production, anchored architecturally to the open
      Phase 4 G1 hosting gate (D-058 deferral stands). Plan +
      runbooks written (`docs/deployment/dokploy-plan.md`,
      `docs/runbooks/dokploy-{deployment,disaster-recovery,exit-plan}.md`):
      stages A–H, per-stage owner authorizations, release governance
      (GitHub push ≠ production authorization; approval stays in the
      Phase 19 chain + D-139 burn tokens), backups as supplement to
      D-125/drills (never replacement), mandatory exit drill
      (Phase 24 lock-in goals preserved). **Stage A VERIFIED** —
      architecture & repository assessment committed (plan §20).
      **Stage B VERIFIED** — secret-free staging manifest
      (`local/infra/compose.staging.yml`: digest-pinned images,
      exposure remodel, hosted restart policies, fail-closed secret
      variables), env contract 23+6 (battery-tested), synthetic-data
      policy, volume backup/retention template
      (`docs/deployment/staging-volume-backup-policy.md`); suite
      15/15 ×2 green. **Stage B amendment (same day):** explicit
      isolated network topology (data internal + frontend,
      wordpress-only), `.env.staging.example` (30-var contract,
      secrets placeholder-only), pre-deploy validator
      `local/scripts/validate_staging_compose.py` (VALID rc=0);
      battery extended to 25 tests ×2 green; directive
      reconciliation recorded (plan §21.7 — no Redis/API/Workers
      invented). **Stage C READY (2026-09-20, not executed):**
      provisioning runbook `docs/runbooks/dokploy-vps-provisioning.md`
      (G1–G6 owner gates, requirements per official floors, UFW/SSH
      hardening, pinned installer, initial security config, rollback,
      empty verification log) + read-only VPS readiness probe
      `local/scripts/validate_vps_readiness.py` (battery-pinned
      read-only guarantee; exit 0/1/2); suite 14/14 ×2 green.
      **Nothing installed, provisioned, connected, or deployed.**
      Next: execution requires the per-item owner authorizations in
      plan §21.6 (VPS, installer, firewall, GitHub connect, staging
      DNS, backup credentials, RPO/RTO approval, operator-access and
      webhook decisions, edition pinning) — run the grant gate, then
      the probe, then the runbook, under those grants. The signable
      checklist `docs/deployment/stage-c-owner-grants.md`
      (SC-1..SC-12; SC-7/8/9/11/12 pre-filled ratification-ready,
      2026-09-29) is machine-verified by
      `local/scripts/verify_stage_c_grants.py` (fail-closed exit
      0/1/2; battery `test_stage_c_grants.py` 17/17 ×2). The gate is
      chained into the deployment pipeline: `launch_attestation.py
      --check-stage-c` folds an unsigned checklist into the verdict as
      an explicit SC-GRANTS blocker, both VPS probes refuse under
      `--require-grants` before any probe work (exit 2), and
      `docs/deployment/stage-c-runbook.md` orchestrates the stage end
      to end under the authoritative G1–G6 taxonomy (battery
      `test_stage_c_gate_integration.py` 15/15 ×2). The Stage C dry-run
      harness `local/scripts/stage_c_dry_run.py` simulates G1–G6 over
      the grants checklist, `compose.staging.yml`, and the fill-in
      `.env.staging.template` (30-var contract, strict D-045
      placeholders, grant annotations; parse-only, zero mutation;
      battery `test_stage_c_dry_run.py` 18/18 ×2). The acceptance
      suite `local/scripts/stage_c_acceptance.py` probes all five
      planes on the engine-local rehearsal stack (synthetic data only,
      stack-identity guarded; MediaStoreContract round-trip zero
      residue; tunnel-only n8n; ledger consistency-only —
      `stage_c.acceptance_run.v1`, live run 10/10 ACCEPTED; battery
      `test_stage_c_acceptance.py` 31/31 ×2). The gate runner
      `local/scripts/stage_c_runbook.py` orchestrates G1–G6
      sequentially (env lint → preflight clearance → network boundary
      → stack ping → acceptance → attestation token
      `docs/deployment/stage-c-attestation.json` on unanimous pass
      only; `stage_c.runbook_attestation.v1`; battery
      `test_stage_c_runbook.py` 19/19 ×2). **Stage C Layer 2 —
      attestation ingestion & backup-policy clearance (2026-09-30,
      plan §23/§24 — tooling VALIDATED LOCALLY, execution still
      owner-gated):** `local/scripts/stage_c_token.py` (fail-closed
      verification of the emitted token — schema, digest integrity
      re-proving the G6 emission algorithm, SHA-256 artifact
      bindings, CURRENT/ANCESTOR commit provenance via
      `git merge-base --is-ancestor`, G1–G5 gate ledger, acceptance
      payload integrity: 10-probe census, stack 5/5, media
      zero-residue marker, event ledger non-zero; missing/corrupted/
      schema-invalid/integrity-failing refuse with exit 2;
      `stage_c.token_verification.v1`, live run VERIFIED against the
      committed bc39efb token) wired as the second leg of
      `launch_attestation.py --check-stage-c` (a findings-bearing
      token appends the SC-RUNBOOK blocker under the same
      never-upgrade-a-NO_GO rule as SC-GRANTS; unreadable or
      corrupted token refuses exit 2 before the report prints;
      SC_TOKEN/SC_TOKEN_ENV/SC_TOKEN_MANIFEST/SC_TOKEN_GRANTS
      override the artifact paths);
      `local/scripts/stage_c_backup_checks.py`
      (`stage_c.backup_clearance.v1`, parse-only V1–V7 per
      `staging-volume-backup-policy.md` §2: six-volume census,
      schedule coverage + RPO floors canonical 6 h / media 24 h,
      retention 30/8/6 + 14 d, off-host S3-compatible mandate,
      separate minimum-permission backup credentials with the
      commented BACKUP_* placeholder block (D-045), restore
      preconditions, supplement-only / upload ≠ restoration evidence
      (D-137); live      CLEAR 14/14). Battery
      `test_stage_c_attestation_ingest.py` 48/48 ×2; full regression
      2374/2374 ×2 green (2326 + 48, expected honest skip).
      **Stage C milestone closure & grants readiness (2026-09-30,
      plan §24/§25 closeout — documentation + audit only, nothing
      provisioned):** `local/scripts/stage_c_grants_audit.py`
      (`stage_c.grants_readiness_audit.v1`): all 12 SC-1..SC-12
      slots audited structurally READY for sign-off (A1 anchors,
      A2 census in both tables, A3 matrix completeness, A4 §3 rows
      5-cell and EMPTY — nothing pre-signed, A5 the 5 pre-filled
      decisions SC-7/8/9/11/12 match their RATIFICATION-PENDING
      notes, A6 the REAL verifier's standing verdict is the required
      fail-closed one: NOT_AUTHORIZED 0/12); `--simulate-sign`
      proves the AUTHORIZED side offline over a synthetic fully-
      signed copy (12/12, zero mutation of the real artifact).
      Fail-closed re-probe: grants verifier rc 1, dry-run rc 1, both
      VPS probes rc 2 under `--require-grants` (refusal BEFORE any
      probe/SSH work), composite `--check-stage-c` rc 1 with the
      SC-GRANTS blocker. Plan §54 appended (the Layer 1 + Layer 2
      milestone record with `--check-stage-c` operational guidance
      and the token-regeneration remediation path); stage-c-runbook
      §2 gained the composite gate as pre-execution step 6 plus the
      remediation paragraph. The committed token was REGENERATED via
      `stage_c_runbook.py` (live G1–G6 READY, live run 10/10
      ACCEPTED): now bound to candidate `743c9c6`, digest
      `54e2b93a…`, live ledger 76183, bindings unchanged — the
      documented remediation path, re-verified by `stage_c_token.py`
      VERIFIED. **Stage D preparation entry (2026-09-30, plan §26/§37
      — SCAFFOLD ONLY, nothing deployed, remote execution still
      owner-gated with SC-1..SC-12 at 0/12):**
      `docs/deployment/stage-d-runbook.md` (the Stage D deployment
      flow as ONE fail-closed sequence: template integrity → D-144
      generation → manifest contract verification → local lineage
      rehearsal via `bootstrap_staging.py --check` +
      `run_staging_smoke_tests.py` 21/21 — the staging lineage is the
      rehearsal surface, the rendered Dokploy manifest has no local
      stack behind it until an owner-gated deployment → the standing
      Stage C composite gate; topology, secret-envelope boundaries,
      recovery/rollback, and the Stage E handoff package pinned);
      `local/scripts/stage_d_preflight.py` (`stage_d.verdict.v1`,
      parse-only AST-pure, exit 0/1/2): two modes over the D-144
      contract — template mode (canonical template HOLDS 7/7: four
      services, backend internal, zero published ports on the three
      data services, V-09 probe parity, strict ${VAR:?} refs, named
      volumes) and manifest mode (the same checks against any
      candidate manifest — drift refuses with named findings before
      a deployment layer ever sees it); battery
      `test_stage_d_preflight.py` 20/20 ×2 (every refusal class,
      multi-violation accumulation, cannot-assess, JSON contract,
      zero-leak, AST purity); plan §55 appended; full regression
      2409/2409 ×2 green (2389 + 20, expected honest skip); D-045
      scan clean. **Stage D codified rehearsal entry (2026-09-30,
      plan §56 — offline evidence machinery only, deployment still
      owner-gated with SC-1..SC-12 at 0/12):**
      `local/scripts/stage_d_rehearsal.py` (`stage_d.rehearsal.v1`,
      exit 0/2): runbook §3 steps 2–3 as ONE fail-closed command —
      D-144 render over four synthetic digest-pinned slots + the
      committed names-only envelope, byte-identical re-render proof,
      `stage_d_preflight.py --mode manifest` HOLDS 7/7 — temp-only
      artifacts, AST-pure, masked key names on every refusal;
      `local/infra/dokploy/stage_d_mock.env.example` (`__MOCK__`
      placeholders, never real credentials); battery
      `test_stage_d_rehearsal.py` 19/19 (determinism, every refusal
      class, zero-leak redaction, D-045 clean, purity, zero repo
      artifacts); plan §56 appended;      full regression green ×2. **Stage D steps 4–5 executed entry
      (2026-09-30, plan §57 — verification COMPLETE pending final
      owner sign-off, SC-1..SC-12 NOT_AUTHORIZED 0/12, nothing
      deployed):** generator hardened to strict immutable digest pins
      (floating tags / short / uppercase digests REFUSED exit 2;
      battery 18→21); digest propagation proven across simulated
      staging→production transitions (identical pins ⇒ byte-identical
      manifests, envelope scoping isolated to env_fingerprint, 4/4
      pin census; daemon leg re-resolves postgres/mysql digests
      identically); step 4 live: `bootstrap_staging.py --check` exit 0
      (preflight 9/9 keys resolved values-withheld — in-process from
      the running containers, since corrected to the documented
      operator-export workflow (`local/infra/.env.staging`, gitignored;
      runbook §3 Step 4); 13/13 schemas) +
      `run_staging_smoke_tests.py --stack` 22/22; step 5 composite:
      grants READY 6/6 + verifier NOT_AUTHORIZED 0/12 + rehearsal
      REHEARSAL_PASS + `--check-stage-c` NO_GO sole blocker SC-GRANTS
      — readiness does not breach the Stage C fail-closed
      authorization state; plan §57 appended; full regression green
      ×2; D-045 clean.
      **Stage D Step 4 governance tightening (2026-10-01, doc-only):**
      runbook §3 Step 4 now documents the operator export explicitly
      (gitignored `local/infra/.env.staging` sourced with
      `set -a; . …; set +a` before `bootstrap_staging.py --check`);
      §57/TODO wording corrected — the 2026-09-30 run resolved the 9
      keys in-process from the running containers (values never
      printed; no committed code reads secrets from containers), and
      the operator-export path is the required documented workflow
      going forward; no code change, battery untouched; D-045 clean.
      **Stage D Step 4 evidence re-run via operator export
      (2026-10-01, doc-only):** `bootstrap_staging.py --check`
      executed through exactly the runbook workflow (`set -a; .
      local/infra/.env.staging; set +a`; gitignored operator file,
      mode 600, values never printed): exit 0, preflight 9/9 keys
      resolved from the operator-exported env, 13/13 schemas, no
      container reads, running stack untouched; §57 evidence updated.
      Incidental findings flagged for follow-up (not fixed here):
      committed HEAD carries a 6-char throwaway literal where D-141
      had committed a strict `${CANONICAL_DB_PASSWORD:?}` ref
      (compose.staging.yml postgres+minio) and the committed
      `.env.staging.example`/`.template` envelopes are not directly
      source-able; D-045 clean.
      **Stage D integrity: stack-consistent credential + finding
      retraction (2026-10-02, battery +1):** the 2026-10-01 claim of
      a committed 6-char literal replacing the D-141 strict
      `${CANONICAL_DB_PASSWORD:?}` ref was RETRACTED — probe parsing
      artifact (awk third field captured the word `secret` from the
      ref error message; `git log -L` numbers reflect the older file
      layout); `git log -S` proves the strict refs were added once
      (ffd8663) and never removed — the compose contract was never
      relaxed. The staging DB role credential was rotated to a
generated ≥8 value stored only in the gitignored operator file
      (socket-side ALTER over stdin, value never displayed, D-124);
      real-TCP auth proof on the staging data network: exported
      credential authenticates (positive control), wrong password
      rejected (negative control) — the exported env authenticates
      the RUNNING database, no trust-only bypass remains, no
      container env reads; fresh `bootstrap_staging.py --check` via
      the documented export: exit 0, preflight 9/9, 13/13 schemas,
      stack untouched; new per-line strict-ref test pins BOTH
      staging `${VAR:?}` credential refs against literal drift
      (test_deployment_staging_manifest 25→26); full battery ×2;
      stage-e 16/16 clean-tree pin; D-045 clean.
      **Stage E baseline verification + Stage F owner review package
      (2026-10-02, doc-only):** Stage E entry points mapped
      (MASTER_PLAN L488/L1323; dokploy-plan §27/§38; cutover runbook
      §0–§7; Stage F gate) and the minimal G0–G6 go/no-go ladder
      accepted with zero new machinery; machine-verified baseline:
      offline readiness V-01..V-09 ALL PASS (attestation GO
      d95f2d96…, D-144 binding 7ca49705… holds) with SOLE blocker
      V-10 Stage F authorization absent — required fail-closed
      answer (offline exit 1); `--stage-f` exit 1 with F-2 map PASS
      and F-3 honest unsigned default SF-1..SF-7; §58 appended;
      Stage F sign-off template + commit-bound token workflow added
      to stage-f-authorization.md §7 for owner review — no signature
      minted, no host touched; D-045 clean; stage-e 16/16 clean-tree
      pin.
      **Phase 5 igniter live rehearsal (2026-10-02, dry-run only):**
      battery-pattern harness with live transports — ephemeral
      redis:7-alpine drill container (noeviction, maxmemory 256mb,
      removed at teardown) on the local engine network + real
      ArgvPsqlTransport against engine-local-postgres + the
      documented in-process D-053 webhook precedent; IGN-01..IGN-05
      ALL GREEN (14/14 checks): D-154 certificate
      INFRASTRUCTURE_COMPLETE rooted in the D-112 chain (7 rows, zero
      breaks); PG pooling headroom (max_connections 100 over 3+12),
      read roundtrip, SSOT schema ready (seed.size_term, 28 rows);
      Redis PING 37.2 ms < 50 ms, noeviction, drill-namespace
      set/get/delete roundtrip; D-053 parse_event + HMAC verified
      over raw bytes + redelivery skipped (handler once, D-027 store
      roundtrip); single emission of
      phase5.live_wiring_attestation.v1 (digest cca91ed9…, cert
      27d6c43e…, manifest 7ca49705…); canonical battery module 38/38;
      zero repo artifacts, zero dangling containers, stack 10/10
      healthy after teardown; stage-e 16/16 clean-tree re-run;
      Phase 6 handoff verified; next gates unchanged (owner-side
      SC-1..SC-12 + SF-1..SF-7, then cutover).
      **Stages
      D–H READY (2026-09-20, not executed, plan §23):** health/E2E validation script
      (`local/scripts/validate_staging_health.py`: manifest +
      read-only live modes, deployed-side isolation invariants),
      staging DR/backup drill runbook
      (`docs/runbooks/staging-disaster-recovery.md`: per-store
      backup/restore, integrity acceptance, RPO/RTO checklist),
      exit-drill runbook (`docs/runbooks/dokploy-exit-drill.md`:
      I1–I5 zero-lock-in invariants, empty verification log);
      battery suite 13/13 ×2 green. Execution follows the Stage C
      gates. **Production runtime hardening (2026-09-21, plan §24,
      VALIDATED LOCALLY — deployment still owner-gated):**
      `local/infra/compose.prod.yml` (hardened runtime manifest:
      no-new-privileges everywhere, read-only rootfs + tmpfs seams on
      the four data services, non-root n8n uid 1000, CPU/mem limits,
      ZERO published ports, internal data network — all verified
      RUNNING in the isolated prodcheck project, not just declared);
      fail-closed startup pre-flight
      (`local/canonical/runtime_preflight.py`: mandatory-key matrix,
      prohibited production keys, secret values never echoed);
      `local/scripts/validate_dokploy_runtime.py` (MANIFEST/RUNTIME/
      GATE modes, exit 0/1/2); SSOT `schema.sql` ordering defect fixed
      (hitl/admin tables preceded their CREATE SCHEMA — fatal on a
      fresh database, guarded by battery);
      `test_dokploy_runtime.py` 13/13 ×2, full battery 1125/1125 ×2
      zero-skip. **Stage C sizing & target validation (2026-09-22,
      plan §25 — PLANNED artifacts, execution owner-gated):**
      `docs/deployment/stage-c-readiness.md` (host baseline derived
      from the validated manifest: 3328 MiB / 4.0 CPU ceilings ⇒ 6 GiB
      RAM floor, 2 vCPU floor, 40 GB disk floor, cgroup v2 + Docker
      ≥ 24 required; UFW/SSH baselines; 9-key credential inventory;
      exit criteria) + `local/scripts/validate_vps_target.py` (offline
      plan verification incl. D-045 fail-closed secret-in-planning-env
      refusal + opt-in READ-ONLY SSH target probe behind a pinned
      command allowlist) + `test_stage_c_readiness.py` 21/21 ×2.
      **Stage D staging verification (2026-09-22, plan §26 — runbook
      + harnesses EXECUTED on a live local staging project, external
      deployment owner-gated):** `stage-d-staging-runbook.md`
      (health-gated per-tier launch, recovery procedures, abort
      gates); `bootstrap_staging.py` (fail-closed preflight, idempotent
      13-schema apply + O/I/L seed, transport guard refusing any DB
      target outside engine-staging-* — kills the staging→local SSOT
      cross-environment defect class); `run_staging_smoke_tests.py`
      21/21 (10 synthetic canonical-engine checks + 11 stack checks,
      label-based so verification needs no secret env);
      `test_stage_d_smoke.py` 10/10 zero-skip. **Stage E cutover
      readiness (2026-09-22, plan §27 — runbook + harness PLANNED,
      execution owner-gated under D-139):**
      `stage-e-cutover-runbook.md` (preflight → backup → transition →
      post-cutover smoke; RB-1..RB-6 rollback matrix with the
      stop→compensate→reconcile ordering; edge header policy; D-045
      credential-handoff sign-off; D-139 promotion gate);
      `verify_cutover_readiness.py` (OFFLINE V-01..V-07 fail-closed
      incl. D-045 planning-shell secret refusal and D-138 attestation
      composition — DIRTY tree fails closed; `--snapshot` D-125
      tamper-evidence proof; opt-in `--edge` live header/redirect
      probe, unreachable ⇒ exit 2); `test_stage_e_cutover.py` 15/15
      ×2 zero-skip. **Stage F authorization gate + Stage G
      acceptance spec (2026-09-22, plan §28 — PLANNED artifacts,
      execution owner-gated under D-139):**
      `stage-f-authorization.md` (SF-1..SF-7 blocking authorizations,
      single-use commit-bound token rotation procedure, gate-exit
      criteria) machine-verified by `verify_cutover_readiness.py
      --stage-f` (F-1..F-4 fail-closed; honest default = unsigned ⇒
      rc 1); Stage E `--edge` probe folded into D-138 MON-001 as
      monitoring evidence (findings/unassessable ⇒ negative,
      backward-compatible); `stage-g-acceptance.md` (GA-1..GA-7
      probes, two-cycle ACCEPTED/REJECTED protocol, rollback
      interlock); `test_stage_f_authorization.py` 23/23 ×2
      zero-skip. **Stage H vendor-exit harness + D-142 memory
      foundation (2026-09-22, plan §29 — procedure PLANNED,
      harness OFFLINE-PROVEN):** `stage-h-vendor-exit.md`
      (data-plane exit procedure; prove-before-teardown);
      `verify_vendor_exit.py` (check/export/dry-run-import, exit
      0/1/2, D-045 hygiene, D-124 redaction, fold parity, tamper
      detection, PBKDF2+HMAC_DRBG armoring);
      `local/src/memory/` pgvector-compatible store + MemWal-pattern
      portable WAL adapter with offline-first fallback (Walrus NOT
      connected, D-045); `test_stage_h_and_memwal.py` 27/27 ×2
      zero-skip. **Infrastructure Stage B–H provisioning artifacts
      (2026-09-22, plan §35 — readiness only, execution owner-gated):**
      `local/infra/dokploy/` (README stage map + authority boundaries,
      `postgres-ssot.env.example` Stage B SSOT contract with D-125
      WAL-archiving parameters, `redis.env.example` Stage C
      AUTH/noeviction/AOF contract, `deploy_orchestrator.sh` Stage H
      fail-closed shell skeleton with `--dry-run` and per-stage health
      gates) + `local/src/infra/infra_health_probe.py` (Part B
      verification bridge: injected-connector probes over SSOT,
      broker, worker heartbeat, telemetry circuit; deep-redacted
      diagnostics per D-124; fail-closed halt on any core failure);
      `test_dokploy_infrastructure.py` 24/24 ×2, full battery
      1341/1341 ×2 zero-skip. **Stage C validation gate (2026-09-24,
      plan §36 — D-143 Approved, hermetic validator only):**
      `local/infra/dokploy/stage_c_runbook_validator.py` (VC-01..VC-14
      over an injected host-adapter/facts-file interface: OS/kernel/
      Docker/cgroup floors, 80/443 gateway-collision + 3000/5432/6379
      public-binding refusals, UFW profile contract, planning-env
      NAMES with sha256 fingerprint binding (values never read out),
      pinned installer ref, domain shape, G1–G5 owner attestations;
      READY/NOT_READY/CANNOT_ASSESS fail-closed) + host-prerequisites
      spec `docs/deployment/stage-c-host-prerequisites.md` (sizing,
      UFW boundaries, installer isolation, TLS termination, sign-off
      procedure, evidence validity); SSH probe stays in
      `validate_vps_target.py` (single probing surface, battery-
      asserted);      `test_dokploy_stage_c_validator.py` 18/18 ×2, full
      battery 1359/1359 ×2 zero-skip. **Nothing provisioned — Stage C
      execution still requires the §17/§21.6 owner authorizations
      (VPS, installer, firewall, DNS, credentials).** **Stage D
      configuration engine (2026-09-24, plan §37 — D-144 Approved,
      hermetic generator only):**
      `local/infra/dokploy/dokploy_compose_template.yaml` (canonical
      template: postgres-ssot/redis/app-orchestrator/telemetry-circuit,
      internal backend network, probe-parity healthchecks, resource
      ceilings) + `local/infra/dokploy/stage_d_compose_generator.py`
      (deterministic byte-identical render; strict `${VAR:?}` secret
      contract with masked-key fail-closed and sha256 fingerprint
      binding; zero ports on backend services; app sole edge surface;
      digest-pin enforcement; AST-pinned no-socket/no-subprocess/
      no-environ) + `docs/deployment/stage-d-compose-architecture.md`
      (topology, isolation matrix, injection sequence, rollback);
      `test_dokploy_stage_d_generator.py` 18/18 ×2, full battery
      1377/1377 ×2 zero-skip. **Generation is a local configuration
      act — real deployment remains owner-gated (D-139).**
- [x] Dokploy Stage E — cutover readiness wire & manifest fingerprint
      binding — **COMPLETE (2026-09-24; D-145 Approved, owner-directed)**:
      `verify_cutover_readiness.py` extended with V-08 (Stage D manifest
      SHA-256 fingerprint + envelope binding — VERIFY / NO_MANIFEST /
      NO_ENVELOPE / MISMATCH / MALFORMED, everything but VERIFY blocks,
      network isolation re-asserted on the bound bytes) and V-09
      (health-probe contract parity — every generated container
      healthcheck must map onto an `infra_health_probe.py` semantic,
      fail-closed otherwise); `docs/deployment/stage-e-cutover-fingerprint-binding.md`
      (V-01..V-09 cutover verification matrix, evidence-validity model,
      Stage F handoff); `test_dokploy_stage_e_cutover_wire.py` 15/15 ×2,
      full battery 1392/1392 ×2 zero-skip. **V-01..V-09 is technical
      clearance only — cutover/activation authority stays with the
      Stage F owner sign-offs and D-139.**
- [x] Dokploy Stage F — context-bound owner authorization engine —
      **COMPLETE (2026-09-24; D-146 Approved, owner-directed)**:
      `local/src/security/owner_approval_gate.py` (HMAC-SHA256 token
      binding manifest fingerprint + session + target env + logical
      TTL window + owner nonce; `<token_id>.<sig>` wire format with
      recomputed commitment; fail-closed rejection taxonomy incl.
      replay burn through an injected durable store; injected logical
      clock — no wall clock; every GO/NO_GO audited to an injected
      sink with deep redaction, key/sig never surfaced; AST-pinned
      zero-I/O core) + `docs/deployment/stage-f-owner-authorization.md`
      (token lifecycle, owner↔orchestrator handoff, rejection
      taxonomy, revocation model, evidence validity) +
      `test_owner_approval_gate.py` 19/19 ×2, full battery
      1411/1411 ×2 zero-skip. **Nothing authorized or deployed — the
      gate is a necessary input to activation; D-139 remains the sole
      cutover authority.**
- [x] Dokploy Stage F attestation integration & cutover orchestration
      wire — **COMPLETE (2026-09-24; D-147 Approved, owner-directed)**:
      cutover matrix extended to V-01..V-10 (the Stage F verdict
      record is a fail-closed prerequisite bound to the V-08 manifest
      fingerprint; forbidden-material/expiry/mismatch all refuse);
      `local/scripts/cutover_orchestrator.py` (ordered transaction
      Stage C → D/E → Stage F → immutable `cutover.bundle.v1` with
      SHA-256 bundle_hash; abort-before-burn on technical failure;
      replay refusal; one audited bundle per call; AST-pinned zero
      I/O) + `docs/deployment/stage-f-attestation-orchestration.md`
      (V-10 spec, lifecycle, Stage G handoff via D-112 bundle-hash
      recording) + `test_cutover_orchestrator_stage_f.py` 20/20 ×2,
      full battery 1431/1431 ×2 zero-skip. **Nothing authorized or
      deployed — Stage G requires a READY bundle plus an explicit
      owner command; D-139 remains the sole activation authority.**
- [x] Stage F/G durable replay store & provisioning pre-flight —
      **COMPLETE (2026-09-24; D-148 Approved, owner-directed)**:
      `local/src/security/pg_replay_store.py` (crash-resilient nonce
      burn on the D-055 SSOT — `security.consumed_owner_nonces` with
      idempotent DDL and atomic `ON CONFLICT DO NOTHING RETURNING`
      adjudication, live-proven 1 winner/5 losers under a 6-thread
      race; injected transport + UTC stamp; transport failure ⇒
      `ReplayStoreError`, a lost DB is never an approval; burns
      survive restarts and gate re-instantiation) +
      `local/scripts/stage_g_preflight_validator.py` (G-01..G-04:
      bundle schema+hash integrity, strictly-READY unexpired,
      owner-command hash identity, D-112 audit-chain join — all
      fail-closed to `PREFLIGHT_CLEARED`/`PREFLIGHT_BLOCKED`) +
      `docs/deployment/stage-g-preflight-contract.md` (schema,
      failure modes, owner runbook) +
      `test_stage_g_preflight_and_pg_replay.py` 20/20 ×2 (offline +
      live-PG tier), full battery 1451/1451 ×2 zero-skip. **Nothing
      provisioned or deployed; D-139 remains the sole activation
      authority.**
- [x] Stage G acceptance executor & cutover readiness verification —
      **COMPLETE (2026-09-24; D-149 Approved, owner-directed)**:
      `local/scripts/run_stage_g_acceptance.py` (fail-closed
      PREFLIGHT_CLEARED entry gate incl. tampered-bundle refusal;
      ACC-01 manifest conformance vs the bound Stage D template,
      ACC-02 strict env-contract + secret-literal refusal, ACC-03
      hardening baseline at template parity, ACC-04 canonical
      `stage_g_acceptance_report.v1` with deterministic SHA-256
      acceptance fingerprint binding manifest+template+bundle; one
      audited report per run; AST-pinned zero-I/O pure core) +
      `docs/deployment/stage-g-acceptance-execution.md` (lifecycle,
      remediation matrix, D-112 fingerprint handoff, D-139 owner
      activation) + `test_stage_g_acceptance.py` 20/20 ×2, full
      battery 1471/1471 ×2 zero-skip. **Nothing provisioned or
      deployed — the fingerprint is evidence for the owner's final
      activation decision; D-139 remains the sole activation
      authority.**
- [x] Stage G post-provisioning live probe engine — **COMPLETE
      (2026-09-24; D-150 Approved, owner-directed)**:
      `local/scripts/verify_stage_g_live_probes.py` (fail-closed
      entry gate on a valid ACCEPTED untampered D-149 report with
      matching manifest fingerprint; GA-1..GA-7 — container lifecycle,
      SSOT read/write roundtrip, broker PONG+auth+TTL with exposure
      refusal, app loopback, worker heartbeat freshness, zero
      published ports, zero secret material in output streams —
      through INJECTED executors, absent executor ⇒ FAIL, transport
      exceptions type-only; leak detection on raw text before
      redaction, any leak flips the run; canonical
      `stage_g_live_probe_report.v1` with SHA-256 probe digest; one
      audited report per run; AST-pinned zero-I/O core) +
      `docs/deployment/stage-g-live-probes.md` (probe mechanics,
      executor interface, timeout discipline, D-112 handoff) +
      `test_stage_g_live_probes.py` 20/20 ×2, full battery
      1491/1491 ×2 zero-skip. **Nothing provisioned or probed live;
      D-139 remains the sole activation authority.**
- [x] Stage G production probe adapters & launch attestation triad
      binding — **COMPLETE (2026-09-25; D-151 Approved,
      owner-directed)**: `local/scripts/stage_g_probe_adapters.py`
      (concrete D-150 executors — DockerInspectExecutor GA-1/GA-6,
      ContainerExecExecutor GA-2..GA-5 inside container namespaces,
      LogStreamScrubberExecutor GA-7 — direct argv only, zero
      `shell=True`, single AST-pinned spawning seam, allow-list
      validated parameters, 15s hard timeouts, fail-closed exit
      codes, deep redaction before return, secret-shaped raw
      payloads never echoed) +
      `local/src/security/launch_attestation_verifier.py`
      (`TripleEvidenceGate` TRIAD-01..04 — hash integrity,
      correlation, D-112 rooting with end-to-end chain verify,
      verdict chain; `wire_into_registry` installs the mandatory
      `stage_g_triple_evidence` probe in every `qa.health_report.v1`,
      a blocked triad is probe FAIL) +
      `docs/deployment/stage-g-probe-adapters.md` (adapter
      interfaces, safety boundaries, timeout parameters, integration
      flow) + `test_stage_g_adapters_and_launch_attestation.py`
      29/29 ×2, full battery 1520/1520 ×2 zero-skip. **Nothing
      provisioned or probed live; D-139 remains the sole activation
      authority.**
- [x] Stage G formal closure & Stage H handoff seal — **COMPLETE
      (2026-09-25; D-152 Approved, owner-directed)**:
      `local/scripts/stage_g_closure_and_handoff.py`
      (CLS-01..CLS-05 over the complete C→G artifact chain — host
      readiness, Stage D manifest⇔envelope binding, Stage E
      contract, Stage F bundle+token, Stage G acceptance+probes;
      zero-drift fingerprint assertion; D-151 triad with zero
      bypasses; RB-1..RB-6 rollback matrix + ordering invariant +
      health-fallback trigger parsing; canonical
      `stage_g_closure_seal.v1` with the SHA-256 `closure_digest` as
      the Stage H entry root; one audited seal per run; AST-pinned
      pure core) + `docs/deployment/stage-g-closure-and-handoff.md`
      (closure report + Stage H owner runbook: handoff steps, D-112
      seal-row verification, manifest-bound provisioning, rollback
      thresholds, post-activation monitoring) +
      `test_stage_g_closure_and_handoff.py` 23/23 ×2, full battery
      1543/1543 ×2 zero-skip. **The seal authorizes a handoff
      candidate only — nothing provisioned, nothing activated; D-139
      remains the sole activation authority.**
- [x] Stage H live cutover orchestration & owner activation record —
      **COMPLETE (2026-09-25; D-153 Approved, owner-directed)**:
      `local/scripts/stage_h_cutover_executor.py` (H-01..H-05 —
      D-152 seal verification + D-112 rooting, fresh unspent Stage F
      owner token with activation-tick window binding and divergent-
      fingerprint refusal, Dokploy target-state assertions via the
      direct-argv adapter, ACTIVE transition + immutable
      `stage_h_activation_record.v1` with `activation_digest`,
      critical-window watch arming the RB-1 rollback payload; ANY
      refusal aborts with ZERO side-effects) +
      `docs/deployment/stage-h-cutover-runbook.md` (owner token
      minting/injection, cutover steps, edge-only traffic routing,
      rollback execution, post-activation monitoring) +
      `test_stage_h_cutover_executor.py` 25/25 ×2 through the real
      D-152 closure runner and real Stage F gate, full battery
      1568/1568 ×2 zero-skip. **Nothing provisioned, nothing
      activated — the engine never mutates the live stack on its own
      authority; D-139 remains the sole activation authority.**
- [x] Stage H — Dokploy Final Deployment Completion Attestation &
      Transition to Live Wiring — **COMPLETE (2026-09-25; D-154
      Approved, owner-directed)**:
      `local/scripts/dokploy_completion_attestation.py`
      (DEP-01..DEP-05 — the entire Stages B–H lifecycle re-verified
      as ONE unbroken cryptographic continuum: every link re-checked
      against its own engine's rules, ONE manifest SHA-256 with the
      configuration-digest chain recomputed byte-exactly, ALL FIVE
      stage commitments anchored in the D-112 ledger with zero chain
      breaks, every Phase 5–18 Live-Wiring entry point
      present+verified+wired against the verified runtime profile,
      and the canonical `dokploy.completion_attestation.v1` emitted
      with the SHA-256 `attestation_digest` declaring
      INFRASTRUCTURE_COMPLETE ready for service ignition; refusals
      name their stage and still emit the certificate as
      INFRASTRUCTURE_INCOMPLETE) +
      `docs/deployment/dokploy-final-completion-report.md` (B→H
      closure report + the architectural transition guide into Live
      Wiring Phases 5–18) + `test_dokploy_completion_attestation.py`
      38/38 ×2 over the authentic Stage C→H chain (real Stage F
      gate, real D-149/D-150/D-151/D-152/D-153 producers), full
      battery 1606/1606 ×2 zero-skip across 70 modules. **The
      certificate is evidence, not authority — ignition and external
      connectivity remain owner-gated (D-045/D-139, plan §17/§21.6);
      nothing provisioned, nothing activated, nothing ignited.**
- [x] Phase 5 (Live Wiring) — Ignition & Service Connectivity
      Verification — **COMPLETE (2026-09-26; D-155 Approved,
      owner-directed)**:
      `local/scripts/live_wiring_phase5_igniter.py`
      (IGN-01..IGN-05 fail-closed — the D-154
      `dokploy.completion_attestation.v1` verified and D-112-rooted
      BEFORE any probe runs; PostgreSQL SSOT authenticated
      connectivity + schema readiness + pooling invariants through
      the argv-only `ArgvPsqlTransport`; Redis PING < 50 ms,
      noeviction, isolated namespace drill; n8n dispatcher
      readiness through the REAL D-053 contracts with HMAC sha256=
      and the D-027 idempotency drill — the engine's only write;
      canonical `phase5.live_wiring_attestation.v1` emitted exactly
      once per run INCLUDING aborts) +
      `docs/deployment/phase-5-live-wiring-report.md` (topology,
      latency benchmarks, live-evidence provenance, Phase 6
      handover) + `test_live_wiring_phase5.py` 38/38 ×2 over the
      authentic Stage C→H chain, full battery 1644/1644 ×2
      zero-skip across 71 modules. Live run PHASE5_IGNITED against
      the engine-local stack (Redis PING 28.6 ms; 33-table SSOT
      schema; pool headroom proven). **Ignition evidence is not
      authority — Phases 6–18 and external connectivity remain
      owner-gated (D-045/D-139, plan §17/§21.6); no secrets created
      or transmitted; the drill wrote exactly one audited event.**
- [x] Phase 6 (Live Wiring) — Ignition & Notion Workspace Sync
      Verification — **COMPLETE (2026-09-26; D-156 Approved,
      owner-directed)**:
      `local/scripts/live_wiring_phase6_igniter.py`
      (NOT-01..NOT-05 fail-closed — the phase5 attestation
      digest-recomputed AND matched against its D-112 rooting row
      BEFORE any Notion call; authentication + 3/s token-bucket
      pacing through the REAL canonical contract layer; the four
      canonical databases schema-verified (properties, types,
      select options, relations); the non-destructive
      create/replay/read/archive probe with deterministic D-027
      idempotency keys and collision refusal; canonical
      `phase6.live_wiring_attestation.v1` emitted exactly once per
      run INCLUDING aborts) +
      `docs/deployment/phase-6-live-wiring-report.md` (schema map,
      topology, latency metrics, Phase 7 handover) +
      `test_live_wiring_phase6.py` 42/42 ×2 with the phase5
      attestation built by the REAL D-155 igniter over the
      authentic chain, full battery 1686/1686 ×2 zero-skip across
      72 modules. **The workspace is verified, not migrated — live
      credentials and Phases 7–18 remain owner-gated (D-045/D-139,
      plan §17/§21.6); the only write is the archived synthetic
      probe.**
- [x] Phase 7 (Live Wiring) — Ignition & AI Runtime + Product
      Manager Verification — **COMPLETE (2026-09-26; D-157
      Approved, owner-directed)**:
      `local/scripts/live_wiring_phase7_igniter.py`
      (AIR-01..AIR-05 fail-closed — the phase6 attestation
      digest-recomputed AND matched against its D-112 rooting row
      BEFORE any provider call (zero-provider-call proof across
      four failure classes); verified runtime profile + repo-real
      seams consistent with the D-154 ENTRY_POINTS registry;
      deterministic allowlisted bounded routing (token/budget/tool/
      retry/timeout caps); the non-destructive synthetic PM cycle
      through the REAL ModelRouter + ai_contracts with owner-
      approved vocabulary alignment, namespace-scoped scratch-only
      persistence, per-step telemetry, deterministic summary hash,
      optional strictly probe-only Notion write and mandatory
      cleanup; canonical `phase7.live_wiring_attestation.v1`
      emitted exactly once per run INCLUDING aborts) +
      `docs/deployment/phase-7-live-wiring-report.md` (constraints
      table, measured cycle trace, guardrails, Phase 8 handover) +
      `test_live_wiring_phase7.py` 45/45 ×2 with the phase6
      attestation built by the REAL D-156 → D-155 → D-154 chain,
      full battery 1731/1731 ×2 zero-skip across 73 modules.
      **The runtime is proven, not deployed — real AI provider
      credentials (D-045 owner gate), publishing and lifecycle
      promotion remain owner-gated (D-045/D-139, plan §17/§21.6);
      cycle cost $0.00, the only writes are the deleted scratch
      artifact and the archived probe.**
- [x] Phase 8 (Live Wiring) — Ignition & Instagram Graph API
      Verification — **COMPLETE (2026-09-26; D-158 Approved,
      owner-directed)**:
      `local/scripts/live_wiring_phase8_igniter.py`
      (IG-01..IG-05 fail-closed, STRICT PROBE-ONLY — the phase7
      attestation digest-recomputed AND matched against its D-112
      rooting row BEFORE any adapter call (zero-adapter-call
      proof); census Phases 5+6+7 VERIFIED/WIRED + the five
      repo-real Instagram seams consistent with the D-154
      ENTRY_POINTS registry; capability profile with required
      scopes, token expiry margin, and the REAL GraphUsageTracker
      rate envelope; the non-destructive media workflow: caption
      from the REAL Phase 7 ModelRouter → local Class-B
      validate_publish_payload → synthetic container
      IN_PROGRESS→FINISHED via the REAL bounded poll_until_ready →
      publish-call audit (ANY publish = SAFETY VIOLATION refusal)
      → probe archive; canonical
      `phase8.live_wiring_attestation.v1` emitted exactly once per
      run INCLUDING aborts) +
      `docs/deployment/phase-8-live-wiring-report.md` (scope
      matrix, probe trace, rate benchmarks, Phase 9 handover) +
      `test_live_wiring_phase8.py` 45/45 ×2 with the phase7
      attestation built by the REAL D-157→D-156→D-155→D-154 chain,
      full battery 1776/1776 ×2 zero-skip across 74 modules.      **The channel is verified, not opened — zero public
      publishing ever (structurally refused), no live Instagram
      credentials exist or are requested (D-045/D-071 owner gate);
      the only mutation is the archived synthetic probe
      container.**
- [x] Phase 9 (Live Wiring) — Ignition & Telegram Sales/Ingress
      Verification — **COMPLETE (2026-09-26; D-159 Approved,
      owner-directed)**:
      `local/scripts/live_wiring_phase9_igniter.py`
      (TG-01..TG-05 fail-closed, STRICT SANDBOX-INGRESS — the
      phase8 attestation digest-recomputed AND matched against its
      D-112 rooting row BEFORE any adapter call (zero-adapter-call
      proof); census Phases 5+6+7+8 VERIFIED/WIRED + the four
      repo-real Telegram seams consistent with the D-154
      ENTRY_POINTS registry; security profile with bot-token
      format validation, the webhook shared-secret mechanism
      PROVEN both directions through the REAL constant-time
      verifier, and the REAL D-074 RatePacer pacing a per-chat
      burst; the sandbox conversational sales cycle through the
      REAL webhook path (parse_update dropping profile metadata,
      TelegramIngress D-027 dedup) with deterministic intent
      extraction, the reply from the REAL Phase 7 ModelRouter
      CONSTRUCTED but NEVER dispatched, namespaced
      collision-refusing session persistence, adapter-log audit
      (ANY send = SAFETY VIOLATION refusal) and mandatory cleanup;
      canonical `phase9.live_wiring_attestation.v1` emitted
      exactly once per run INCLUDING aborts) +
      `docs/deployment/phase-9-live-wiring-report.md` (security
      matrix, sales-flow trace, guardrails, Phase 10 handover) +
      `test_live_wiring_phase9.py` 46/46 ×2 with the phase8
      attestation built by the REAL D-158→D-157→D-156→D-155→D-154
      chain, full battery 1822/1822 ×2 zero-skip across 75
      modules. **The conversational channel is verified, not
      opened — zero outbound dispatch ever (structurally refused),
      no live Telegram credentials exist or are requested
      (D-045/D-075 owner gate); the only state change is the
      session store entry (deleted before return).**
- [x] Phase 10 (Live Wiring) — Ignition & Multi-channel Order
      Orchestration Verification — **COMPLETE (2026-09-26; D-160
      Approved, owner-directed)**:
      `local/scripts/live_wiring_phase10_igniter.py`
      (ORD-01..ORD-05 fail-closed, STRICT SANDBOX/DRY-RUN — the
      phase9 attestation digest-recomputed AND matched against its
      D-112 rooting row BEFORE any order processing (zero-OMS-call
      proof); census Phases 5+6+7+8+9 VERIFIED/WIRED + the four
      repo-real order seams consistent with the D-154 ENTRY_POINTS
      registry; contracts proven through the REAL validator:
      channel origin tagging, deterministic D-081 idempotency keys,
      IRR/IRT whitelist, strict-integer money with D-114 ceiling,
      allowlist-gated discounts, Class-A-only retries ≤ 2, the
      state machine refusing out-of-order edges; the synthetic
      multi-item lifecycle through the REAL offline OMS stack
      (place → replay-dedup → validate → reserve →
      PLACED→VALIDATED→CANCELLED with full reservation release)
      and the REAL D-083 fan-out boundary driven with durable
      receipts (publisher-less binds — structurally incapable of
      egress) under an EPHEMERAL process-local D-079 lock (the
      default lock claims keys permanently in live PG / the shared
      JSON file — 2 recon-claimed rows purged before commit);
      payment-boundary audit over the LIVE D-027 records (any
      gateway marker = refusal); cleanup deletes the data-minimized
      scratch artifact (zero residue); canonical
      `phase10.live_wiring_attestation.v1` emitted exactly once per
      run INCLUDING aborts) +
      `docs/deployment/phase-10-live-wiring-report.md` (locking
      matrix, lifecycle trace, guardrails, Phase 11 handover) +
      `test_live_wiring_phase10.py` 48/48 ×2 with the phase9
      attestation built by the REAL D-159→D-158→D-157→D-156→D-155→
      D-154 chain, full battery 1870/1870 ×2 zero-skip across 76
      modules. **The order pipeline is verified, not opened — zero
      payment boundaries crossed (markers-only payment_status, no
      gateway field anywhere), no production inventory touched
      (scratch reservations released before return), no live
      credentials exist or are requested (D-045/D-139 owner gate);
      the only state change is the scratch artifact (deleted
      before return).**
- [x] Live Wiring Phase 11 — Ignition & Payment Gateway/Settlement
      Verification — **COMPLETE (2026-09-27; D-161 Approved,
      owner-directed)**:
      `local/scripts/live_wiring_phase11_igniter.py`
      (SET-01..SET-05 fail-closed, STRICT DRY-RUN — the phase10
      attestation digest-recomputed AND matched against its D-112
      rooting row BEFORE any gateway call (zero-gateway-call proof);
      census Phases 5–10 VERIFIED/WIRED + the four repo-real seams
      (`canonical.oms_engine` = ENTRY_POINTS[11],
      `canonical.oms_contracts` = ENTRY_POINTS[12],
      `canonical.orchestration_engine` = ENTRY_POINTS[13],
      `services.sync_engine`) consistent with the D-154 registry;
      gateway capability cap `("sandbox","dry_run","status_query")` —
      live_charge/unknown caps refused, the charge path structurally
      unreachable in probe mode; deterministic SHA-256
      `settlement_key(client_order_id, gateway, amount)`;
      strict-integer money ≥ 1 under the D-114 ceiling; injected
      timeout/partition/decline faults fail CLOSED; the dry-run
      settlement cycle through the REAL OMS stack — sandbox charge
      exactly once, D-027 settlement idempotency both directions,
      PLACED→VALIDATED→FULFILLING→COMPLETED with the D-084
      fulfillment receipt INSIDE the COMPLETED transition ref
      (receipt-once proven over the succeeded refs; a second
      COMPLETED is refused), the settlement event through the REAL
      FanOutEngine with publisher-less binds under an EPHEMERAL
      D-079 lock, the money-marker sweep over the LIVE store records
      plus charge_calls == 1, zero-residue cleanup; canonical
      `phase11.payment_wiring_attestation.v1` emitted exactly once
      per run INCLUDING aborts; suite-found fix: the upstream kwarg
      renamed `phase10_provider` → `upstream_provider` to stay clear
      of the phase-20 entropy sweep) +
      `docs/deployment/phase-11-live-wiring-report.md` (capability/
      money matrix, settlement trace, guardrails, Phase 12 handover) +
      `test_live_wiring_phase11.py` 42/42 ×2 with the phase10
      attestation built by the REAL D-160→…→D-154 chain, full
      battery 1912/1912 ×2 zero-skip across 77 modules. **The
      settlement surface is verified, not opened — zero real money
      movement, no payment provider selected or contacted (owner
      decisions 10/11 open), no live credentials exist or are
      requested (D-045/D-139 owner gate); the only state change is
      the scratch artifact (deleted before return).**
- [x] Live Wiring Phase 12 — Ignition & Shipping/Orchestration
      Verification — **COMPLETE (2026-09-27; D-162 Approved,
      owner-directed)**:
      `local/scripts/live_wiring_phase12_igniter.py`
      (SHP-01..SHP-05 fail-closed, STRICT DRY-RUN — the phase11
      attestation digest-recomputed AND matched against its D-112
      rooting row BEFORE any carrier call (zero-carrier-call proof);
      census Phases 5–11 VERIFIED/WIRED + the four repo-real seams
      (`canonical.orchestration_engine` = ENTRY_POINTS[13]
      "Shipping" per the D-154 cross-walk,
      `canonical.oms_engine` = ENTRY_POINTS[11],
      `canonical.oms_contracts` = ENTRY_POINTS[12],
      `services.sync_engine`) consistent with the D-154 registry
      (slot-13 cross-walk binding re-asserted defense-in-depth);
      carrier capability cap `("sandbox","dry_run","tracking_query")`
      — live_ship/unknown caps refused, the booking path structurally
      unreachable in probe mode, the provider UNSELECTED per open
      decision 11; deterministic SHA-256
      `shipment_key(client_order_id, carrier_id, parcel_hash)` with
      `parcel_hash` over weight/dimensions/declared value ONLY —
      addresses never part of parcel identity; strict-integer parcel
      invariants under the D-114 ceiling; injected
      timeout/partition/refuse/live_ship faults fail CLOSED; the
      dry-run shipping cycle through the REAL OMS stack — sandbox
      label created exactly once with a deterministic derived
      tracking number, D-027 shipment idempotency both directions,
      PLACED→VALIDATED→FULFILLING→COMPLETED with the D-084
      fulfillment receipt carrying the shipment id INSIDE the
      COMPLETED transition ref (receipt-once proven over the
      succeeded refs; a second COMPLETED is refused), the tracking
      event through the REAL FanOutEngine with publisher-less binds
      under an EPHEMERAL D-079 lock, the shipping-marker sweep over
      the LIVE store records plus create_calls == 1, zero-residue
      cleanup; canonical `phase12.shipping_wiring_attestation.v1`
      emitted exactly once per run INCLUDING aborts) +
      `docs/deployment/phase-12-live-wiring-report.md` (capability/
      parcel matrix, shipping trace, guardrails, Phase 13 handover) +
      `test_live_wiring_phase12.py` 43/43 ×2 with the phase11
      attestation built by the REAL D-161→…→D-154 chain, full
      battery 1955/1955 ×2 zero-skip across 78 modules. **The
      shipping surface is verified, not opened — zero carrier
      bookings, no shipping provider selected or contacted (owner
      decision 11 open),      no addresses anywhere in the probe surface,
      no live credentials exist or are requested (D-045/D-139 owner
      gate); the only state change is the scratch artifact (deleted
      before return).**
- [x] Governance D-163 — CRM-not-needed confirmed; registry slot 14
      disposition — **RESOLVED (2026-09-27; D-163 Approved,
      owner-directed)**: the MASTER_PLAN §13 conditional ("a separate
      CRM only if WooCommerce + Notion + n8n are insufficient")
      formally resolved NEGATIVE — the three pillars are shipped AND
      live-wiring verified (WooCommerce D-034–D-045 + the HMAC
      fail-closed `commerce.sync_orchestrator` facade per dokploy-plan
      §32, Notion D-156, n8n D-155) and no governance document records
      any CRM capability gap; registry slot 14 resolves to the
      EXISTING facade, no separate CRM is built or ignited, no
      further build phase for slot 14; the D-154 certificate is
      unaffected (DEP-04 census already reported slot 14 structurally
      ready); the program proceeds directly to slot 15 (D-045/D-139
      preserved — no credentials, no vendor selection, no new
      infrastructure)
- [x] Live Wiring Phase 14 — Ignition & Scheduling Engine
      Verification (registry slot 15) — **COMPLETE (2026-09-27;
      D-164 Approved, owner-directed)**:
      `local/scripts/live_wiring_phase14_igniter.py`
      (SCH-01..SCH-05 fail-closed, STRICT DRY-RUN — the phase12
      attestation digest-recomputed AND matched against its D-112
      rooting row BEFORE any calendar call (zero-engine-call proof);
      census Phases 5–12 VERIFIED/WIRED (slot 14 NOT required —
      D-163) + the five repo-real seams
      (`canonical.scheduling_engine` = ENTRY_POINTS[15] "Marketing
      Automation" per the D-154 cross-walk, `scheduling_contracts`,
      `scheduling_worker`, `canonical.orchestration_engine` =
      ENTRY_POINTS[13], `services.sync_engine`) consistent with the
      D-154 registry (slot-15 cross-walk binding re-asserted
      defense-in-depth); the scheduling contracts enforced through
      the REAL validator (7 post-rejection classes with named
      reasons, deterministic SHA-256 idempotency keys over
      (content_ref, sorted targets, scheduled_for), pure 15-minute
      slot-bucket arithmetic — same-bucket keys collide cross-post
      never cross-platform — and pure due semantics, clock-free);
      the dry-run scheduling cycle over the REAL SchedulingEngine on
      the REAL D-027 parity store — identical re-schedule →
      `retried`, conflicting payload under the same post_id →
      `IntegrityError`, a same-(platform,bucket) post is a durable
      SLOT_CONFLICT rejection, reschedule claims NEW slots first +
      supersedes old with the ledger keeping the row + the freed
      slot re-claimable, SCHEDULED→DUE→CANCELLED with terminal
      immutability (cancel AND reschedule on CANCELLED refuse), the
      due-notification event through the REAL FanOutEngine with
      publisher-less binds under an EPHEMERAL D-079 lock, the
      calendar view rebuilt from DURABLE events alone matching the
      driven lifecycle exactly (zero drift), the publish-marker
      sweep over the LIVE store records plus a refusal of any
      non-ephemeral slot backend, zero-residue cleanup;
      `_EphemeralSlotLocks` = claim/supersede/history parity with
      `_JsonSlotLocks` at ZERO durable footprint (no
      `scheduling.slot_lock` PG rows, no shared-file writes);
      canonical `phase14.scheduling_wiring_attestation.v1` emitted
      exactly once per run INCLUDING aborts) +
      `docs/deployment/phase-14-live-wiring-report.md` (contracts/
      slot matrix, scheduling trace, guardrails, Phase 15 handover) +
      `test_live_wiring_phase14.py` 44/44 ×2 with the phase12
      attestation built by the REAL D-162→…→D-154 chain (plus direct
      contract probes: due boundary, terminal edges, standalone
      engine lifecycle, key determinism), full battery 1999/1999 ×2
      zero-skip across 79 modules. **The scheduling surface is
      verified, not opened — the probe envelope is
      plan/slot_query/calendar_view with NO dispatch capability,
      zero dispatches, zero durable lock claims, no channel egress,
      no wall-clock reads, no live credentials exist or are
      requested (D-045/D-139 owner gate); the only state change is
      the scratch artifact (deleted before return).**
- [x] Live Wiring Phase 15 — Ignition & Analytics Engine
      Verification (registry slot 16) — **COMPLETE (2026-09-27;
      D-165 Approved, owner-directed)**:
      `local/scripts/live_wiring_phase15_igniter.py`
      (ANA-01..ANA-05 fail-closed, STRICT EPHEMERAL DRY-RUN — the
      phase14 attestation digest-recomputed AND matched against its
      D-112 rooting row BEFORE any engine call (zero-engine-call
      proof: the event stream is never read on refusal); census
      Phases 5–12 + 14 VERIFIED/WIRED (slot 14/CRM not a census row
      — D-163) + six repo-real seams (`canonical.analytics_engine` =
      ENTRY_POINTS[16] "Analytics" per the D-154 cross-walk,
      `analytics_contracts`, `analytics_worker`, `scheduling_engine`
      = ENTRY_POINTS[15], `orchestration_engine` = ENTRY_POINTS[13],
      `services.sync_engine`) consistent with the D-154 registry
      (slot-16 cross-walk binding re-asserted defense-in-depth); the
      analytics contracts enforced through the REAL contracts module
      (windowing from the EVENT's own instant — never the clock,
      D-085; the 64-char D-114 bound; classifier purity over the
      durable ref payload only — D-087, with dual-metric COMPLETED
      transitions and in-flight outcomes classifying to None; rollup
      math with counts accumulating and revenue summing; the D-088
      `window_hash` report identity); the synthetic six-event cycle
      over the REAL ProjectionEngine — incremental fold with cursor
      0→16, exactly-once re-consume, a malformed metric payload
      QUARANTINED with the cursor HELD (D-085 flag-never-guess),
      rebuild-from-zero byte-matching the incremental rollups
      (incremental == full replay, zero drift, D-086), the D-088
      idempotent report hash, the egress-marker sweep, zero-residue
      cleanup; `_EphemeralCursorStore` injected with a FAIL-CLOSED
      ENTRY GATE refusing any non-ephemeral cursor backend before
      any engine work (zero files, zero PG rows); canonical
      `phase15.analytics_wiring_attestation.v1` emitted exactly once
      per run INCLUDING aborts) +
      `docs/deployment/phase-15-live-wiring-report.md` (contracts/
      aggregate matrix, analytics trace, guardrails, Phase 16
      handover) + `test_live_wiring_phase15.py` 44/44 ×2 with the
      phase14 attestation built by the REAL D-164→…→D-154 chain,
      full battery 2043/2043 ×2 zero-skip across 80 modules. **The
      analytics read-side is verified, not opened — read-only,
      in-process, ephemeral: no warehouse, no external analytics
      platform, no vendor imports, no wall clock, no durable
      footprint (D-045/D-085/D-087/D-139 owner gates); the only
      state change is the scratch artifact (deleted before
      return).**
- [x] Live Wiring Phase 17 — Notification Engine Verification
      (registry slot 18 NOT taken — D-160 precedent) — **COMPLETE
      (2026-09-27; D-167)**:
      `local/scripts/live_wiring_phase17_igniter.py`
      (NTF-01..NTF-05 fail-closed, STRICT DRY-RUN — the phase16
      attestation digest-recomputed AND matched against its D-112
      rooting row BEFORE any engine call (zero-engine-call proof);
      census Phases 5–12 + 14 + 15 + 16 VERIFIED/WIRED (slot 14/CRM
      not a census row — D-163) + four repo-real seams
      (`canonical.notification_engine`, `canonical.notification_contracts`,
      `canonical.notification_worker`, `services.sync_engine`)
      importable and consistent with the D-154 registry; the slot-18
      registry FACT asserted (`canonical.ai_hitl_service` — no slot
      reassignment; a drifted/absent/reassigned slot 18 refuses);
      the notification contracts enforced through the REAL validator
      (contact-metadata gate fail-closed — EMAIL w/o `subject`, SMS
      w/o `phone_ref`, WEBHOOK w/o `endpoint_ref` refuse Class-B
      before any queueing; 7 templates × 4 channels; deterministic
      SHA-256 dedup identity over (recipient, channel, template,
      logical event_key); pure priority policy — quiet hours defer,
      CRITICAL bypass, frequency caps from the durable ledger; D-092
      outcome vocabulary stable); the synthetic six-notification
      cycle over the REAL NotificationEngine on the REAL D-027 store
      with the EPHEMERAL in-process claim backend and NO dispatch
      transport bound — enqueue → durable QUEUED (exactly-once vault
      claim) → dispatch idempotency (same-alert retry durably
      DUPLICATE_BLOCKED; the loser never dispatches) → priority
      queuing (NORMAL in the quiet window durably POLICY_DEFERRED;
      CRITICAL `hitl.review_required.v1` bypasses quiet hours) →
      intercepted receipts (delivered; late-transient terminal
      stickiness holds DELIVERED) → durable status view rebuilt from
      store data alone (zero drift) → 6 invalid notifications refused
      with ZERO durable rows → the DLQ trigger at contract level
      (permanent_failure → FAILED; `dlq.item_admitted.v1` itself
      enqueued through the same gates) → egress-marker sweep clean;
      zero-residue cleanup; `_EphemeralNotificationLocks` injected
      (the D-079 hazard — the default backend claims keys in live PG
      or the shared `delivery_locks.json` — bypassed) with a
      by-class FAIL-CLOSED refusal of any durable backend at VERIFY
      (battery-proven with a fully functional file-backed backend);
      canonical `phase17.notification_wiring_attestation.v1` emitted
      exactly once per run INCLUDING aborts; digest
      `048952dc580d9add…` byte-stable, phase16 digest `a74345de…`
      bound) + `docs/deployment/phase-17-live-wiring-report.md`
      (contracts/policy matrix, cycle trace, registry-deviation
      record, Phase 18 handover) + `test_live_wiring_phase17.py`
      44/44 ×2 with the phase16 attestation built by the REAL
      D-166→…→D-154 chain, full battery 2131/2131 ×2 zero-skip
      across 82 modules. **The notification surface is verified, not
      opened — alerts are enqueued, policy-gated, dedup-protected and
      receipted in dry-run; no channel adapter is bound and none may
      be until a wiring phase explicitly injects one behind the
      D-091 provider-neutral boundary; zero email/SMS/push/webhook
      egress, zero durable footprint (D-045/D-079/D-089–D-092 owner
      gates); the only state change is the scratch artifact (deleted
      before return).**
- [x] Live Wiring Phase 18 — HITL Service Ignition (registry
      slot 18 TAKEN — the final ignition) — **COMPLETE (2026-09-27;
      D-168)**:
      `local/scripts/live_wiring_phase18_igniter.py`
      (HIT-01..HIT-05 fail-closed, STRICT DRY-RUN — the phase17
      attestation digest-recomputed AND matched against its D-112
      rooting row BEFORE any engine call (zero-engine-call proof);
      census Phases 5–12 + 14 + 15 + 16 + 17 VERIFIED/WIRED (slot
      14/CRM not a census row — D-163) + four repo-real seams with
      THE LOAD-BEARING SLOT-18 PIN
      (`canonical.ai_hitl_service` = ENTRY_POINTS[18] per the D-154
      cross-walk — the binding Phase 17 asserted, now taken; drift,
      absence or reassignment refuses); the HITL contracts enforced
      through the REAL validators (D-105/D-108: ticket-shape gate
      fail-closed — missing fields, illegal queue/role vocabularies,
      CLAIMED-without-reviewer, PENDING-with-reviewer, D-114 bounds;
      ReviewAction gate fail-closed — EXPIRED is NEVER a reviewer
      action (sweep-only), MODIFIED requires a payload_override
      dict, payload_override invalid otherwise, role:/agent: mock
      actor refs only, D-114 feedback bounds; the lifecycle edge
      matrix closed with terminals exitless; the deterministic
      escalation ladder any→ops→owner→escalation); the synthetic
      five-ticket review cycle over the REAL HitlEngine
      (D-105/D-106/D-108) on the REAL D-027 store with the EPHEMERAL
      in-process vault and NO reviewer-notification channel bound —
      analyst-boundary ingestion (the D-166/D-167 handover edge:
      DISPATCHED_TO_HITL insights → INSIGHT_REVIEW, idempotent via
      `analyst:{insight_key}`) → atomic claim discipline (wrong role
      refused, exactly one claimant wins, second claimant loses) →
      human-only resolutions (APPROVED; MODIFIED with durable
      payload_override; a re-resolve refuses; an EXPIRED reviewer
      action is Class-B) → the escalation LOOP (ESCALATED with the
      deterministic role elevation, a fresh elevated PENDING child
      re-queued idempotently, resolved under the elevated role) →
      the deterministic expiration sweep (EXPIRED reachable ONLY
      from the injected logical-clock sweep) → 5 malformed payloads
      refused Class-B with ZERO durable rows and the open-ticket
      registry unchanged → the D-108 tamper-evident chains verified
      per ticket (4 resolutions + 1 expiry) → egress-marker sweep
      clean, the store carrying ONLY `hitl::` rows; zero-residue
      cleanup; `_EphemeralHitlVault` injected (the D-079 hazard —
      the default vault claims rows in live PG or the shared
      `local/volumes/hitl` — bypassed) with a by-class FAIL-CLOSED
      refusal of any durable vault at VERIFY (battery-proven with a
      fully functional file-backed vault); canonical
      `phase18.hitl_wiring_attestation.v1` emitted exactly once per
      run INCLUDING aborts; digest `0026f4c94a11872a…` byte-stable,
      phase17 digest `048952dc…` bound) +
      `docs/deployment/phase-18-live-wiring-report.md` (contracts/
      policy matrix, review trace, program-completion boundary) +
      `test_live_wiring_phase18.py` 44/44 ×2 with the phase17
      attestation built by the REAL D-167→…→D-154 chain, full
      battery 2175/2175 ×2 zero-skip across 83 modules. **The HITL
      surface is ignited, not opened — tickets, claims, decisions
      and the tamper-evident ledger are durable in dry-run; no
      human-notification or dashboard emitter exists and none may be
      bound until an owner-gated phase explicitly injects one; zero
      reviewer signals, zero durable footprint (D-045/D-079/
      D-105–D-108 owner gates); the only state change is the scratch
      artifact (deleted before return).**
- [x] Live Wiring Phase 16 — Ignition & Analyst Service
      Verification (registry slot 17) — **COMPLETE (2026-09-27;
      D-166 Approved, owner-directed)**:
      `local/scripts/live_wiring_phase16_igniter.py`
      (ANL-01..ANL-05 fail-closed, STRICT DRY-RUN — the phase15
      attestation digest-recomputed AND matched against its D-112
      rooting row BEFORE any engine call (zero-engine-call proof);
      census Phases 5–12 + 14 + 15 VERIFIED/WIRED (slot 14/CRM not a
      census row — D-163) + five repo-real seams
      (`canonical.analyst_engine` = ENTRY_POINTS[17] "AI Business
      Analyst" per the D-154 cross-walk, `analyst_contracts`,
      `analyst_worker`, `analytics_engine` = ENTRY_POINTS[16],
      `services.sync_engine`) consistent with the D-154 registry
      (slot-17 cross-walk binding re-asserted defense-in-depth); the
      analyst contracts enforced through the REAL validator (10
      invalid-request classes with named reasons — D-102/D-114;
      deterministic SHA-256 insight identity over (category, sorted
      correlation_keys, sorted metric_refs); the lifecycle edge
      matrix closed with terminals exitless; the D-104 HITL boundary
      structural — HIGH/CRITICAL severity or a state-mutating
      payload is non-auto-acceptable BY CONSTRUCTION); the synthetic
      four-insight cycle over the REAL AnalystEngine on the REAL
      D-027 store with an INJECTED PURE evaluator (no LLM SDK, no
      data lake, mock D-142-shaped fixtures) — evidence-keyed dedup
      (identical evidence ⇒ durable DUPLICATE with a dedup audit row
      regardless of the incidental insight_id), pure evaluation
      applied durably (double evaluation refuses), the D-104
      boundary driven both ways (HIGH auto-accept structurally
      refused → HITL dispatch; LOW auto-accepted; state-mutating LOW
      refused), supersede from the HITL queue with terminal
      exitless, the durable rationale rebuilt from D-027 events
      alone (generated → evaluated → dispatched → superseded), 4
      invalid requests refused with ZERO durable rows added,
      sandbox-marker sweep, zero-residue cleanup; `_EphemeralVault`
      injected with a by-class refusal of any non-ephemeral vault at
      VERIFY; canonical `phase16.analyst_wiring_attestation.v1`
      emitted exactly once per run INCLUDING aborts) +
      `docs/deployment/phase-16-live-wiring-report.md` (contracts/
      boundary matrix, analyst trace, guardrails, Phase 17 handover)
      + `test_live_wiring_phase16.py` 44/44 ×2 with the phase15
      attestation built by the REAL D-165→…→D-154 chain, full
      battery 2087/2087 ×2 zero-skip across 81 modules. **The
      analyst surface is verified, not opened — insights reach
      DISPATCHED_TO_HITL but no HITL service is wired yet (Phase 17
      ignites exactly that edge); zero LLM/lake contact, zero
      durable footprint (D-045/D-101–D-104/D-139 owner gates); the
      only state change is the scratch artifact (deleted before
      return).**
- [x] Live Wiring Program-Level Completion Reconciliation (registry
      closeout) — **COMPLETE (2026-09-28; D-169)**:
      `local/scripts/live_wiring_completion_reconciliation.py`
      (REC-01..REC-05 fail-closed — the program-level boundary after
      D-168 took the final slot): REC-01 re-ran the REAL phase 5–18
      battery chain-builders IN ORDER over the REAL Stage C→H chain
      — the UNBROKEN chain D-154 → … → D-168 re-verified (14
      attestation digests recomputed byte-exactly, MATCHED their
      D-112 rooting commitments anchored by the D-154 certificate
      row `dokploy_completion_attestation`, each attestation binding
      its predecessor's digest — no fork, no gap, no reassignment;
      byte-stable with the governance record: D-165 `4f807900…`,
      D-166 `a74345de…`, D-167 `048952dc580d9add…`, D-168
      `0026f4c94a11872a…`; chain digest `97d88f42…`; verifier zero
      breaks over 20 ledger rows); REC-02 reconciled the FULL-SUITE
      slot census against the LIVE D-154 `ENTRY_POINTS` registry
      (slots 5–18, 14 seams, re-read at run time — 12 census rows
      5–12+15–18 present+VERIFIED+WIRED with byte-exact seam
      matches; slot 14 SEALED CRM-not-needed per D-163 —
      registry-visible as seal evidence, ABSENT from the census
      rows, a rebuilt CRM row refuses; slot 18 LOCKED to
      `canonical.ai_hitl_service` — drift/absence/reassignment
      refuses); REC-03 held the fail-closed invariants END TO END
      (zero durable footprint; the REAL D-027 parity store carrying
      ONLY `hitl::` rows — zero cross-surface leakage; ZERO
      human-surface egress — zero reviewer signals, ephemeral vault,
      no notification channel bound; egress-marker sweep clean; AST
      purity — no sockets/network transports anywhere, no
      process/spawn in the D-168-standard engines); REC-04/REC-05
      emitted exactly ONE canonical
      `live_wiring.completion_reconciliation.v1` (aborts included,
      deep-redacted D-124) — verdict `PROGRAM_RECONCILED`,
      attestation digest `c30d3047d28d6c69…` (byte-stable), 17/17
      rule checks PASS + `docs/deployment/phase-19-reconciliation-report.md`
      (the re-run digest table, the all-slot census cross-walk, the
      invariant matrix, the program completion boundary) +
      `test_live_wiring_completion.py` 50/50 ×2 (PASS over the REAL
      chain re-run; every refusal class; redaction audits; AST
      purity audits), full battery 2225/2225 ×2 zero-skip across 84
      modules. **The reconciliation is a VERIFICATION-ONLY closeout
      — nothing ignited, nothing opened, zero durable footprint; the
      Live Wiring program (Phases 5–18) is COMPLETE and the track is
      CLOSED; the engine remains a VERIFIED Launch Candidate;
      production activation stays owner-gated (D-139); the only
      state change is the scratch artifact (deleted before
      return).**
- [x] Phase 26 — Launch Readiness, Go/No-Go Attestation & Controlled
      Activation — **COMPLETE (2026-09-19; D-137–D-140 APPROVED,
      M1–M4 shipped)**:
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
      Phase 25 conductor/fault-ladder/recovery. **Shipped: suite 46/46
      zero-skip (43 offline + 3 live-PG) ×3 consecutive green;
      battery 860/860 ×2 green, zero warnings; ladder 46/46; census
      reconciles exactly (T1=710 · T2=46 · T3=56 · T4=13, 33 modules);
      AST/entropy/channel sweeps CLEAN; stack 5/5 healthy. Live-leg
      defects fixed in-batch: explicit-audit_seq insert (hash/row
      divergence after retention deletes) + bigint cast + None
      sentinel parity (PG vs JSON vault). Suite-found defects fixed:
      fail-open missing-evidence aggregation, DRY_RUN/OBSERVING token
      scope, replay-deadlocked approval context, OBSERVING rollback
      reachability. Completion produces a launch CANDIDATE + verdict
      — NOT a launch; live activation requires a separate explicit
      one-time owner authorization.** Spec:
      `docs/phases/phase-26-launch.md`. **Extension (2026-09-19):**
      resilience drill — catastrophic recovery (destroy → restore →
      verify over the live D-027 store via the D-125 verified-freeze
      primitives; forged/missing archives fail closed) — shipped and
      PASSED, then OPERATIONALIZED as the `resilience_drill.py`
      operator command (six-stage lifecycle, CLI/JSON dashboard,
      run-scoped, fail-closed on every fault path) with drill
      evidence wired into the launch matrix (`canonical_matrix(
      drill_result=…)` → BAC-001 → D-138 bundle). Suite 10/10 ×2;
      battery 870/870 ×2 green; census T1=754 · T2=44 · T3=62 ·
      T4=10 = 870 (34 modules); sweeps CLEAN; stack 5/5.
      **Extension 2 (2026-09-19):** decision-ledger resilience — the
      Phase 19 hash-chained human decision chain is now disaster-
      proof: `compact()` refuses it for teardown (D-125 governance);
      `decision_ledger_drill.py` operator command (full-chain
      verified-freeze archive → atomic catastrophe → tamper-evident
      rehydration → decided-vs-happened consistency vs the D-027
      store). Suite-found defect fixed:
      `PgEventStore.get_record` dropped its explicit source (read-
      path twin of the Phase 9 finding). Suite 7/7 ×2; battery
      877/877 ×2 green; census T1=758 · T2=44 · T3=65 · T4=10 =
      877 (35 modules); sweeps CLEAN; stack 5/5.
      **Extension 3 (2026-09-19) — DR closeout:** the decision-
      ledger archive now replicates OFF-HOST via the Phase 24
      `MediaStoreContract` (re-downloaded + re-attested; forged/
      missing copies fail attestation — drill = 7 stages); D-138
      binding fail-closed on BOTH legs (production GO requires a
      fresh green transactional drill AND a fresh green ledger
      consistency pass; five negative paths pinned NO_GO/BLOCKED);
      unified `launch_attestation.py` emits `qa.health_report.v1` +
      `qa.launch_attestation.v1` with deterministic hash — live run
      **GO** (both DR legs RECOVERED, 533 decisions reconciled).
      Suite 14/14 ×2; battery **891/891 ×2 green, zero warnings**;
      census (D-120 toolkit) T1=769 · T2=44 · T3=68 · T4=10 = 891
      (36 modules); ladder 46/46; AST/entropy CLEAN; stack 5/5.
      Launch candidate GO — live activation remains owner-gated
      (D-139).
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
      **Live pipeline hardening (2026-09-21)**: content-to-channel
      pipeline (`local/canonical/content_pipeline.py`) composes the
      shipped engines — AI generation (Phase 7/8 router) → HUMAN
      review gate (D-050: PROPOSED/IN_REVIEW/REJECTED proposals
      refused before any dispatch; missing lifecycle fails closed) →
      product staging (Phase 4 SyncEngine, RED-tier proposal-gated,
      defense in depth) → channel fan-out (D-077/D-078) → REAL D-070/
      D-074 outbox publishers (duplicate content across jobs blocked
      by terminal guards — no double posts; Class-C cooldown vs
      Class-E freeze+DLQ boundaries verified end-to-end); crash
      isolation per target; compensation = durable APPEND-ONLY
      COMPENSATED marker + deterministic per-target verdicts
      (COMPLETED / RETRY_SCHEDULED / REFUNDED) — no ledger mutation;
      drill `local/scripts/validate_orchestration_live.py`
      (offline 15/15 + opt-in read-only ORCH_LIVE_ENABLED probe,
      exit 2 gated); battery `test_phase11_orchestration_e2e.py`
      28/28 (incl. drill fail-closed regression proof).
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
      **Live wiring shipped 2026-09-21 (ingress contracts on the
      D-075 seam + egress completion):** `local/canonical/telegram_ingress.py` —
      webhook secret-token verification (constant-time compare over
      the exact raw header, fail-closed: unset `TELEGRAM_WEBHOOK_SECRET`
      ⇒ refuse; Telegram-documented charset/length validated on the
      effective secret regardless of source), strict update parsing
      (UTF-8 JSON, bounded, exact keys, Class-B on violation), and
      long-poll ingress contracts (monotonic `update_id` offset,
      dedup via the durable seen-set — same discipline as the D-070
      idempotency vault). Egress dispatcher wiring reuses the shipped
      D-074 vault/pacer + D-076 retry taxonomy — no new retry logic.
      Health/contract drill `local/scripts/validate_telegram_live.py`:
      offline synthetic round-trip (ingress verify/tamper/refuse,
      egress publish→duplicate-block→invalid-payload, redaction
      active) + opt-in live Bot API probe behind
      `TELEGRAM_LIVE_ENABLED=true` + token (exit 2 without — none
      exist). Suite 21/21 ×2; battery 982/982 ×2, zero skips.
      Standing owner gate: live Telegram Bot API credentials (D-045)
      — none exist, none requested.
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
      **Live wiring shipped 2026-09-21 (classified graph layer on the
      D-071 adapter):** `local/canonical/instagram_live.py` —
      `classify_graph_error` maps documented Graph error bodies
      (rate codes 4/17/32/613 and `is_transient` → Class-C cooldown
      carrier; permission/OAuth codes 10/190/200/2500 → Class-E
      freeze carrier; unknown codes → Class-B terminal) onto the
      D-070 PUBLISHER's existing exception carriers, so live failures
      flow through the shipped cooldown/freeze/backoff/DLQ machinery
      with ZERO publisher changes (fail-closed: malformed bodies are
      Class-B, never silently retried); `GraphUsageTracker` records
      documented X-App-Usage / X-Business-Use-Case-Usage percentages
      with a deterministic ≥75% warn signal (no wall clock);
      `ClassifiedGraphAdapter` (D-071 subclass, same D-045 gate and
      redaction) pins GRAPH_API_VERSION v26.0 per the official
      changelog (reviewed 2026-09-21) and tracks usage on every
      dispatch. Health/contract drill
      `local/scripts/validate_instagram_live.py`: offline synthetic
      publishing-graph drill (gate matrix, local Class-B validators,
      mock two-step workflow, taxonomy matrix, usage tracker,
      redaction) + opt-in READ-ONLY business-fields probe behind the
      full gate (exit 2 without — none exist). Suite 42/42 ×2 (joint
      Woo+Instagram battery); battery 1055/1055 ×2, zero skips.
- [x] Phase 8 — AI Product Manager & Operational Observability
      — **COMPLETE (2026-09-16), D-065–D-068 all owner-approved**:
      **Multi-provider live wiring shipped 2026-09-21**
      (`local/canonical/ai_providers_multi.py`, on the D-062/D-066
      seam — nothing shipped was touched): `DeepSeekProvider`
      (OpenAI-schema-compatible HTTPS adapter, official docs reviewed
      2026-09-21) and `OllamaProvider` (LOCAL loopback daemon,
      air-gapped by construction; the model name is the enablement
      gate — no key exists, none requested, D-045) join OpenAI/
      Anthropic as drop-in `AiProvider` adapters;
      `ProviderChain` generalizes the D-066 fallback to N providers
      with a deterministic terminal mock (Class-A/C advance
      provider-by-provider, Class-B/D surface and are NEVER masked,
      every step emits a D-065 `stage=fallback` record);
      `ProviderCircuitBreaker` (call-count based, no wall clock)
      opens after K consecutive retry-class failures, skips the
      provider for a cooldown window, and closes on success;
      `classify_provider_error` maps wire responses onto the D-052
      taxonomy with the five named categories (Auth→C, RateLimit→A,
      ContextLength→D, ProviderOutage→A, SchemaViolation→B — D never
      falls back because shrinking the prompt is the fix);
      `redact_ai` strips `sk-…`/Bearer key shapes (D-124).
      Validation drill `local/scripts/validate_ai_engine_live.py`:
      offline synthetic drill (gate matrix, taxonomy matrix, chain
      fallthrough, breaker, D-063 hard refusal, redaction) + opt-in
      READ-ONLY probes (`models` listing / local `/api/tags`) behind
      the D-045 gates (exit 2 without — none exist). Suite 29/29 ×2;
      battery 1084/1084 ×2, zero skips; Phase 20 AST sweep clean.
      Standing owner gate: AI provider selection + credentials
      (register row 9, D-045) — none exist, none requested.
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
