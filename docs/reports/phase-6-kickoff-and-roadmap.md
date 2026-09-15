# Phase 6 Kickoff & Roadmap — Notion Business OS (The Brain)

- Initiated: 2026-09-15
- Authority: MASTER_PLAN §13 — **Phase 6 = Notion Business OS**
  ("Dashboard, SOPs, knowledge base, content calendar, ideas, review
  queues, reports")
- Strategy: **local-first** (D-053). Phase 6 is **design/contract-only
  in this kickoff** — per the project TODO gate: *"Phase 6 — Notion
  Business OS (no Notion workspace automation)"*. No Notion workspace,
  no API integration, no credentials (D-045), no external connections
  in this batch.
- Predecessor: Phase 5 n8n Foundation closed at foundation level
  (M1–M4, gate report `docs/reports/phase-5-n8n-foundation-gate-report.md`).

---

## 0. Naming & placement reconciliation (important)

This kickoff intentionally does **not** create
`docs/MASTER_PLAN-PHASE-6.md` or a `docs/phase-6/` directory:

- MASTER_PLAN §13 already **is** the authoritative Phase 6 definition;
  a second "master plan" file for one phase would fork the plan.
- Repository convention: phase specifications live in
  `docs/phases/`, kickoffs/gate reports in `docs/reports/`
  (see `phase-5-kickoff-and-roadmap.md`,
  `phase-5-n8n-foundation-gate-report.md`). The full Phase 6
  specification belongs at `docs/phases/phase-06-notion-business-os.md`
  when Phase 6 execution begins.

### Source-of-truth correction (material)

The draft kickoff proposed "Establish Notion as the single source of
truth for business state." That contradicts approved architecture:

- **Canonical business data (products, variants, vocabulary, prices,
  identifiers, mapping registry, events): PostgreSQL** — D-055
  Approved; D-048 Option A resolves prices at the canonical layer.
- **Transactional ecommerce execution: WooCommerce** (projection).
- **Notion = the Business-OS / knowledge layer**: authoritative only
  for knowledge artifacts it owns — SOPs, knowledge base, content
  ideas, content calendar, dashboards, review-queue *surfaces*, and
  reports. It never becomes the store of canonical business data.

The error-router incident trail (M3/M4) already materializes HITL
items into the canonical **VerificationQueue** with D-026 provenance;
Phase 6 must *surface* that queue in Notion, not relocate it. Whether
the durable system of record for HITL/incidents stays PostgreSQL (with
Notion as view/mirror) is **D-060 (Proposed)** below.

---

## 1. Phase objective

Make Notion the operating surface where the owner runs the business —
knowledge, planning, content pipeline, and human review — while every
automation reads its *actionable* business facts from the canonical
PostgreSQL layer. n8n bridges the two under the D-050 authority tiers.

## 2. Core entities (PROPOSED schema sketch — owner approves at Phase 6 build)

| Entity | Purpose | Key fields (sketch) | Authoritative layer |
| --- | --- | --- | --- |
| Content Ideas | idea → publication pipeline | title, status, source refs, target channels | Notion (knowledge layer) |
| Content Calendar | scheduled content | date, channel, idea link, asset refs | Notion (knowledge layer) |
| Campaigns | marketing campaigns | dates, goal, tier, ROI tracker | Notion (knowledge layer) |
| SOPs / Knowledge Base | operating procedures | title, body, version, owner | Notion (knowledge layer) |
| Review Queues (HITL) | human decisions | links to canonical queue items, decision, decision date | **canonical PostgreSQL** (D-060 Proposed); Notion = read surface |
| Dashboards / Reports | KPIs, sync health, conflicts | views over canonical + Woo telemetry | Notion (read-only surfaces) |

The draft's Content-Ideas status lifecycle (Backlog, Researching,
Draft, Review, Approved, Published) is preserved as the **proposed**
lifecycle; it becomes a controlled vocabulary only when the owner
approves it as such at Phase 6 build time. **No new controlled
vocabulary is created by this kickoff.**

## 3. Business-logic contracts

### 3.1 Trigger definition

A Notion-side event (e.g., an idea moved to an agreed
"Ready for Automation" status) is a **request**, not an authority:
n8n consumes it, validates it against canonical data and the D-050
tier matrix, and executes only what the tier allows. Publication,
price, and vocabulary effects remain RED/YELLOW per D-050 and the
n8n conventions standard.

### 3.2 Idempotency (D-027 — corrected)

The draft proposed `Notion Page ID + Last Updated Timestamp` as the
idempotency key. **Rejected — same defect class the M1 review fixed**
(see `docs/standards/n8n-idempotency-and-retries.md`): a timestamp
changes on every edit, so the key is different on every retry and
dedupe silently fails.

Phase 6 contract: the M1 key grammar applies verbatim —

```
idempotency_key = SHA256(source_system + event_id + event_type)
                = SHA256('notion' + notion_page_id + event_type)
```

- Deterministic per logical event; **retries reuse the same key**.
- Notion page `last_edited_time` is **delivery/change-detection
  metadata only** — never key material.
- D-027 verdicts (new / `skipped_duplicate` / 409 integrity error on
  conflicting payload / deterministic reconciliation) land in the
  canonical event store, exactly like every other source system.

### 3.3 Notion API specifics

Page-ID formats, property schemas, rate limits, and webhook/polling
behavior are **implementation-time verification** (noted honestly, as
with the Woo API in D-043): no Notion connection exists locally, and
this kickoff does not browse the web or request credentials.

## 4. Sync rules & authority matrix (D-050-aligned; replaces "master/slave")

| Flow | Authoritative source | Direction | Tier | Notes |
| --- | --- | --- | --- | --- |
| Knowledge content (SOPs, ideas, calendar) | Notion | Notion → n8n (read) | GREEN | n8n reads to orchestrate; never writes back uninvited |
| Content idea → canonical product/price facts | PostgreSQL canonical | Notion reads via n8n view data | GREEN | Notion renders; canonical owns facts |
| Review-queue decisions | **Human** (D-050) | Human → canonical queue → Notion mirror | RED (decision) | The decision is made once, in the canonical queue; Notion reflects it |
| Notion property edits by n8n | n/a by default | — | YELLOW per write, case-by-case | Only with an explicit, per-workflow D-050 classification and human-approval marker; **no blanket write-back** |
| Incident/HITL records | canonical queue (D-060 Proposed) | canonical → Notion (mirror) | GREEN (write to Notion only) | Append-only D-026 provenance lives in the canonical layer |

The draft's "Notion is the master, n8n is the slave" framing is
replaced by this matrix: Notion masters **its own knowledge layer**,
the canonical DB masters **business facts**, and every automation
write is tier-classified. No default bidirectional sync (Phase 3
sync-contract rule, carried forward).

## 5. Milestones (design-first, consistent with the TODO gate)

- **M1 — Phase 6 specification**: `docs/phases/phase-06-notion-business-os.md`
  (entity schemas, property dictionaries, status lifecycles for owner
  approval, page/DB layout for the workspace).
- **M2 — Data contracts & idempotency conformance**: Notion-source
  event contract mapped to the D-027 store; contract tests mirroring
  the M2/M3 pattern (static + executed).
- **M3 — Local integration scaffolding**: mock Notion adapter behind
  the provider-neutral boundary (RULES §35 pattern, like mock-Woo);
  no real Notion connection.
- **M4 — Gate report**: data-integrity audit of contracts, idempotency
  conformance proof, and the **explicitly deferred** Notion API
  connectivity audit (requires workspace + credentials = owner-gated;
  the draft's "audit of Notion API connectivity" cannot pass locally
  and is not claimed).

Deferred to later phases per MASTER_PLAN and D-059: content
generation/posting automation (Phase 15 with Phase 9 surfaces),
Instagram, payment, shipping.

## 6. D-060 — HITL/incident system of record & Notion integration boundaries (PROPOSED)

- **Status:** **Proposed** (2026-09-15, recorded from the Phase 6
  kickoff instruction) — requires owner approval.
- **Question A — durable HITL/incident store:**
  - **Option A (recommended):** canonical PostgreSQL remains the
    system of record for HITL/incidents and their D-026 provenance;
    Notion receives a **mirror/view** for human ergonomics. Rationale:
    the M4 chain already materializes dead-letters into
    `VerificationQueue` with provenance; PostgreSQL gives append-only
    enforcement, transactional integrity, and idempotent ingestion —
    none of which a Notion database can guarantee.
  - **Option B:** the Notion database itself is the record; canonical
    tooling syncs decisions back. Rejected as recommendation: weaker
    integrity guarantees, split provenance, sync-conflict surface.
- **Question B — content-idea lifecycle statuses** (Backlog →
  Researching → Draft → Review → Approved → Published): approve as
  proposed, amend, or defer to M1 design.
- **Question C — Notion write-backs by n8n:** none by default;
  any future write-back workflow carries its own D-050 tier
  classification and approval marker.

## 7. Phase 6 gates (corrected)

1. Data-contract review and owner sign-off on entity schemas and
   lifecycles (this kickoff proposes; owner disposes — D-060).
2. Idempotency conformance with the M1/D-027 key grammar (test-proven
   at M2).
3. ~~Audit of Notion API connectivity~~ → **deferred, owner-gated**:
   requires a Notion workspace, integration, and credentials — none
   of which may exist under D-045/D-053 until the owner opens that
   gate.

## 8. Next actionable step

Owner rules on D-060 (A/B per question). Then Phase 6 M1 produces
`docs/phases/phase-06-notion-business-os.md` under the approved
options — still with no workspace automation until the owner opens
the integration gate.
