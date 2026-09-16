# Phase 6 Specification: Notion Business OS (M1 — The Blueprint)

- Status: **M1 blueprint ✓ · M2 contracts ✓ · D-027 ingestion path ✓ · M3 adapter + polling engine ✓ · M4 integrity audit + conformance proof ✓** — 2026-09-15
- Ingestion wiring (M2+): `local/canonical/notion_ingest.py` — contracts →
  D-060 key → D-027 dedupe → lifecycle validation → `events.event_record`
  (live PostgreSQL, D-055) → D-026 provenance; failures persist durable rows
  + HITL items (D-028); 16 live integration tests in
  `local/tests/test_phase6_notion_ingest.py`
- Provider-neutral adapter (M3): `local/services/notion_adapter.py` —
  `NotionProvider` interface (RULES §35, mock-Woo pattern) with
  `MockNotionAdapter` as the local implementation; `PollingEngine`
  drives fetch → boundary validation → ingest with a per-page cursor
  (unchanged pages emit nothing; changed markers = new D-027 events;
  failed ingestions never advance the cursor). Live Notion API adapter
  = drop-in `NotionProvider`; the verified revision field plugs into
  `NOTION_REVISION_MARKER_FIELDS` with zero structural rewrites
- Authority: MASTER_PLAN §13 (Phase 6 = Notion Business OS);
  D-059 Option A sequencing; **D-060 Approved — Option A**.
- Scope discipline: **specification only** — no Notion workspace,
  no API connection, no credentials (D-045/D-053; the standing
  "no Notion workspace automation" gate holds until the owner opens it).
- Companion documents: kickoff & authority matrix at
  `docs/reports/phase-6-kickoff-and-roadmap.md`; n8n operating
  standards in `docs/standards/`.

---

## 1. Domain

Business Operations, Content Pipeline, Knowledge Management.

## 2. Governance (D-050 / D-060 Approved — Option A / D-055)

- **PostgreSQL (canonical layer): single source of truth** for
  business state, events (D-027), the mapping registry (D-046), and
  HITL/incident decisions with their D-026 provenance.
- **Notion: the Business interface** — operational dashboards, SOP
  repository, knowledge base, content ideas/calendar, and review
  *surfaces*. Notion mirrors canonical truth; it never replaces it.
- Every automation write is tier-classified per D-050 and the n8n
  conventions standard (`docs/standards/n8n-conventions.md`).
  No default bidirectional sync (Phase 3 sync-contract rule).

## 3. Data Contracts

- All external Notion events MUST be mapped to canonical internal
  formats before ingestion (mock-adapter boundary, RULES §35 pattern).
- Idempotency follows the M1 grammar exactly
  (`docs/standards/n8n-idempotency-and-retries.md`), refined by
  **D-060 (Approved, amended 2026-09-15)**:

  ```
  idempotency_key = SHA256(source_system + event_id + event_type
                           + revision_marker)
                  = SHA256('notion' + notion_page_id + event_type
                           + revision_marker)
  ```

  - `revision_marker` is the **source-provided revision identifier
    carried in the event payload — NOT wall-clock time**. The plain
    `(page_id, event_type)` key collapsed legitimate repeated
    transitions (Draft → Review → Draft → Review: the second Review
    event would be silently dropped as a duplicate).
  - Retry deduplication stays intact: a retry of the **same
    delivery** yields the same marker (same key →
    `skipped_duplicate`); distinct revisions yield distinct keys
    (distinct logical events).
  - **The marker's concrete source field is UNVERIFIED until the
    Notion API connectivity verification runs** (owner-gated,
    D-045/D-053). Do not implement against a guessed field.
  - Notion `last_edited_time` remains change-detection metadata
    **only**, never key material.
  - Duplicate → `skipped_duplicate`; conflicting payload → 409
    integrity error / human review (D-027 verdicts, canonical event
    store).

## 4. Lifecycle (Content Idea) — approved via D-060 (extended 2026-09-15)

```
Backlog → Researching → Draft → Review → Approved → Scheduled → Published

Terminal states:
  Rejected  — reachable from any pre-Approved state
  Archived  — reachable from Published or Rejected
```

- `Approved` is not time-bound; `Scheduled` exists so a publishing
  queue acts only on scheduled items (owner rationale, D-060).
- Terminal `Rejected` / `Archived` prevent unbounded HITL-queue
  growth (items can no longer accumulate in Review indefinitely).
- Becomes a controlled vocabulary only when implemented against the
  canonical seed/tooling; the sequence above is the approved semantic
  model. Trigger contract: a status move into the automation-ready
  state is a *request* consumed by n8n — never an authority to
  execute RED-tier effects without the D-050 human-approval marker.

## 5. Security & Provenance

- No direct writes from n8n to Notion without an explicit,
  per-workflow D-050 authorization record (approval marker + tier).
- A D-026 provenance identity must accompany all sync events;
  provenance is attached by canonical tooling, never by the n8n
  runtime (same boundary as the M4 dead-letter bridge).
- No Notion credentials in Git, Markdown, Excel, prompts, or logs
  (D-045); credential creation is an owner-gated step.

## 6. M1 acceptance criteria (the Blueprint is done when)

1. Entity schemas + Notion property dictionaries documented for the
   five core entities (Content Ideas, Calendar, Campaigns, SOPs/KB,
   Review-queue surfaces) — sketches in kickoff §2, expanded here.
2. Status lifecycles approved and mapped to canonical event types.
3. Notion-source event contract mapped to the D-027 store.
4. No connection, credentials, or workspace changes anywhere.

## 7. M4 — data-integrity audit, conformance proof, deferred connectivity (2026-09-15)

M4 is an **audit and proof milestone**, not a live integration.

### 7.1 Audit findings (defects found → fixed in the same batch)
1. **Automatic retry loop on Class-B/E failures (D-052 violation):** the
   poller re-emitted a failed page every cycle (cursor intentionally not
   advanced). Fixed with a failed-marker poison list: while a page's
   marker equals the failed marker it is **suppressed** (no automatic
   retry; the HITL item owns the outcome); a corrected source (new
   marker) re-delivers. Cycle results gained a `suppressed` bucket.
2. **Provenance only on success:** D-026 records now attach to FAILED
   deliveries too (contract failures, lifecycle violations, conflicting
   duplicates) — the audit trail must explain rejected data.
3. **Wall-clock in failure identity:** `_pre_key` derived the failure-row
   id from the full payload including `last_edited_time`. Excluded —
   no idempotency identity (not even failure records) may derive from
   change-detection metadata (D-060).
4. **Store-neutral conflict repeat-sighting:** the re-raise check was
   PgEventStore-SQL-only; now uses the D-027 record interface
   (`get_record`, added to BOTH stores for parity), so the JSON store
   satisfies row C identically.
5. **psql trailing-empty-field truncation:** `get_record`'s chr(31)
   concat lost trailing empty columns because chr(31) is Python
   whitespace and `.strip()` ate them; rows now end with an `END`
   sentinel and fail loudly on malformed output.
6. **(2026-09-16, Phase 7 M4 cross-audit) Non-monotonic reconstruction
   ordering:** `rebuild_state` ordered by `received_at` (wall-clock);
   on the local VM the clock stepped backward under rapid successive
   ingests, reordering genuinely sequential events and breaking
   lifecycle reconstruction (reproduced 2/60 rapid-ingest iterations;
   symptom: intermittent `Review -> Review` in the row-D conformance
   test). Fix: monotonic `events.event_record.ingest_seq bigserial`
   (PG) + durable `receive_seq` (JSON store); `succeeded_references`
   orders by the sequence; `received_at` demoted to audit metadata.
   Verified 0/60 post-fix on both stores; regression test
   `test_rapid_ingest_reconstruction_is_monotonic_on_live_store`.

### 7.2 Conformance matrix (frozen, machine-readable)
- Location: `local/tests/fixtures/notion/conformance_matrix.json`
- Executor: `local/tests/test_phase6_notion_m4_conformance.py` — every
  row (A–H) executes against BOTH stores (json_local +
  postgres_canonical) via subTest-style classes; expected outcomes are
  frozen in the fixture; changing one is a contract change requiring a
  decision-record amendment.
- Commands: `python3 -m unittest local.tests.test_phase6_notion_m4_conformance -v`
  · full battery: `python3 -m unittest discover -s local/tests -p "test_*.py"`
  · canonical: `python3 local/canonical/tests.py` · live smoke:
  `python3 local/scripts/smoke_test.py`

### 7.3 Connectivity audit — EXPLICITLY DEFERRED (owner-gated)
- **No real Notion API credential was used in M4.** None exists in this
  repository, and none may be created without owner approval (D-045/D-053).
- The real revision-marker source field remains **UNVERIFIED**;
  `NOTION_REVISION_MARKER_FIELDS` still contains only the mock contract
  field.
- `last_edited_time` remains change-detection metadata only until
  owner-approved verification runs; it is never idempotency-key
  material (D-060).
- Live Notion API connectivity verification is a **separate owner-gated
  milestone** (requires an owner-approved workspace + credential).
- **M4 passing does NOT prove live Notion compatibility.** All M4
  conformance is proven against the mock provider and both local
  canonical stores.

## 8. Traceability

| Rule | Anchor |
| --- | --- |
| Notion role / HITL SSOT | D-060 (Approved — Option A), D-055 |
| Idempotency grammar | D-017, D-027, M1 standard |
| Authority tiers | D-050, `docs/standards/n8n-conventions.md` |
| Provenance boundary | D-026 (bridge pattern, M4) |
| Failure classes | D-052 (incl. D-061: `undefined_table` stays Class E) |
| Credentials gate | D-045; local-first D-053 |
| Sequencing | D-059 Option A; content-posting effects deferred to Phase 15 / Phase 9 surfaces |
