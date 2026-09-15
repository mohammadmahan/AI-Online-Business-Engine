# Phase 6 Specification: Notion Business OS (M1 — The Blueprint)

- Status: **M1 blueprint ✓ · M2 contracts ✓ · D-027 ingestion path ✓** — 2026-09-15
- Ingestion wiring (M2+): `local/canonical/notion_ingest.py` — contracts →
  D-060 key → D-027 dedupe → lifecycle validation → `events.event_record`
  (live PostgreSQL, D-055) → D-026 provenance; failures persist durable rows
  + HITL items (D-028); 16 live integration tests in
  `local/tests/test_phase6_notion_ingest.py`
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

## 7. Traceability

| Rule | Anchor |
| --- | --- |
| Notion role / HITL SSOT | D-060 (Approved — Option A), D-055 |
| Idempotency grammar | D-017, D-027, M1 standard |
| Authority tiers | D-050, `docs/standards/n8n-conventions.md` |
| Provenance boundary | D-026 (bridge pattern, M4) |
| Failure classes | D-052 (incl. D-061: `undefined_table` stays Class E) |
| Credentials gate | D-045; local-first D-053 |
| Sequencing | D-059 Option A; content-posting effects deferred to Phase 15 / Phase 9 surfaces |
