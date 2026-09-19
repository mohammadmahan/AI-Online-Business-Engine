# ARCHITECTURE

Target architecture for the AI-First Online Business Engine.

**Status:** Approved direction as documented in `MASTER_PLAN.md` §3–§9
and `PROJECT_RULES.md` §5, §13–§18, §29–§35. This document records those
decisions; it introduces none.

---

## 1. Guiding principles

1. **Do not rebuild mature systems without a strong reason.** Prefer
   existing systems, mature integrations, and open standards. Custom
   software only when a required capability is missing, an integration
   requires it, or a reusable internal tool provides clear value.
2. Priority order for every trade-off: **Correctness → Security →
   Simplicity → Maintainability → Cost efficiency → Scalability →
   Documentation.**
3. Integration preference ladder (PROJECT_RULES §15): official API →
   mature supported integration → reliable open-source adapter → custom
   adapter → browser automation (only when justified and reviewed).

## 2. Target architecture

```text
Instagram
    |
    v
  n8n <-------> Notion Business OS
    |
    +------> AI Runtime
    |
    v
WooCommerce
    |
    +------> Payment Provider
    |
    +------> Shipping Provider

Freebuff = development/custom-tool layer
```

- Instagram is the initial customer acquisition and communication
  channel; it feeds n8n via official Meta APIs where supported.
- n8n is the central orchestration hub and the only component that
  touches multiple systems at once.
- WooCommerce is the transactional core; payment and shipping providers
  attach to it.
- Notion and AI Runtime sit beside n8n, not on the transactional path.
- Freebuff is the development layer for custom tools; it is not part of
  the runtime data path by default.

## 3. System roles

| System | Role | Responsibilities | Explicit non-responsibilities |
| --- | --- | --- | --- |
| **WooCommerce** | Ecommerce Source of Truth | Products, variants, SKUs, prices, inventory, orders, customers, coupons, transactional store state | Not a documentation system; not replaced by Notion or Excel |
| **n8n** | Automation / orchestration | Webhooks, scheduled jobs, API integration, transformations, AI orchestration, retries, idempotency, error handling, notifications | Not a data store; not a source of truth |
| **Notion** | Business Operating System | Dashboards, SOPs, documentation, knowledge, content calendar, ideas, review queues, reports | Not transactional truth for inventory, payment, or order state |
| **AI Runtime** | Intelligence layer | Classification, extraction, content drafts, customer assistance, sales assistance, analysis, recommendations, low-risk decisions | Never invents facts; never autonomous on Red-tier actions |
| **Instagram** | Acquisition / communication channel | Marketing, lead capture, comments, DMs, customer interaction | Not a data store; official APIs preferred over unofficial automation |
| **Freebuff** | Development / custom-tool layer | Internal tools, dashboards, utilities, adapters, tests, refactoring, custom interfaces | Does not replace WooCommerce or n8n by default |

## 4. Source-of-truth matrix

| Data category | Source of Truth | Supporting systems | Never the source of truth |
| --- | --- | --- | --- |
| Products, variants, SKUs | WooCommerce | Notion (references), Excel (import/cleanup) | Notion, Excel |
| Prices | WooCommerce | AI recommendations (Yellow tier) | AI output |
| Inventory | WooCommerce | — | Notion, Excel, AI estimates |
| Orders, customers | WooCommerce | Notion (operational references) | Notion |
| Payment status | Verified provider / WooCommerce (server-side verification) | — | AI inference |
| Shipping status | Verified provider integration | — | AI inference |
| SOPs, documentation, plans, reports | Notion | docs/ in this repository | — |
| Business knowledge, dashboards | Notion | docs/ | — |

Payment status must be verified server-side. Shipping status must come
from a verified integration. (MASTER_PLAN §8, PROJECT_RULES §30–§31)

## 5. Provider boundaries (anti-vendor-lock-in)

Every external provider sits behind a clear boundary so it can be
replaced with minimal damage (PROJECT_RULES §35):

- `AIProvider`
- `PaymentProvider`
- `ShippingProvider`
- `InstagramProvider`

Provider selections are Open decisions (see `DECISIONS.md`). Iranian
payment and shipping providers will be researched and selected in their
phases (Phase 12 / Phase 13); hosting and n8n deployment model in
Phases 3–5.

## 6. Environments

Direction (MASTER_PLAN §11, PROJECT_RULES §18, §43):

```text
Development -> Testing/Staging -> Production
```

- No experimental code against production payment, inventory, or
  customer systems.
- High-risk changes follow Development → Test → Review → Approval →
  Production. A direct Development → Production path is forbidden for
  high-risk changes.
- Concrete hosting, staging topology, and deployment tooling are Open
  decisions (Phases 3–4).
- **Deployment-management layer candidate (D-141, Proposed — PLANNED
  only):** Dokploy is documented as an *optional, replaceable*
  deployment-orchestration layer for Staging/Production
  (`docs/deployment/dokploy-plan.md`). It manages operational
  deployment/access only — never business rules, human approvals,
  data correctness, decision-ledger integrity, launch readiness, or
  production authorization. The local-first compose workflow is
  unchanged; a mandatory exit drill keeps the layer swappable.

## 7. AI autonomy in the architecture

AI Runtime executes only within the Green / Yellow / Red tiers
(MASTER_PLAN §9, PROJECT_RULES §32 — see `docs/glossary.md`):

- **Green (autonomous):** classification, formatting, drafts, internal
  summaries, low-risk transformations.
- **Yellow (monitored):** customer reply drafts, product descriptions,
  lead classification, marketing drafts, recommendations.
- **Red (human approval):** refunds, financial actions, production
  price changes, credential changes, security changes, destructive
  operations, permanent deletion, high-impact disputes, high-risk
  production deployment.

AI output that affects business systems (price, inventory, payment,
refunds, customer identity, order status, destructive operations) must
pass schema validation and deterministic checks before execution
(PROJECT_RULES §33).

## 8. Data flow: initial customer journey (target state)

```text
Instagram lead
  -> conversation (AI-assisted, Yellow tier)
  -> product discovery (verified WooCommerce data only)
  -> cart / order (WooCommerce)
  -> payment (PaymentProvider, server-side verification)
  -> inventory decrement (WooCommerce, idempotent)
  -> shipping (ShippingProvider, verified integration)
  -> notifications (n8n)
  -> analytics / reporting (Notion, later phases)
```

Failure and recovery paths exist at every important step; webhook,
retry, and scheduled events must be idempotent (PROJECT_RULES §25).

## 9. Open architectural decisions

Tracked in `DECISIONS.md`; listed here for visibility. None may be
resolved silently.

| # | Decision | Deferred to |
| --- | --- | --- |
| 1 | ~~Final SKU convention~~ — resolved: **Approved (D-014)**: product code `P00001` + attribute suffix, e.g. `P00001-BLK-M`; see `DECISIONS.md` | Phase 2 (done) |
| 2 | WooCommerce hosting / VPS | Phase 3–4 |
| 3 | n8n deployment model (cloud vs self-hosted) | Phase 5 |
| 4 | AI runtime provider(s) | Phase 7 |
| 5 | Iranian payment provider | Phase 12 |
| 6 | Iranian shipping provider | Phase 13 |
| 7 | Data-entry language for product data (Persian / English / bilingual) | Phase 2 |
