# MASTER PLAN

# AI-First Online Business Engine

## 1. Project Vision

Build a reusable, AI-first Online Business Engine for operating online
businesses with emphasis on correctness, security, simplicity, low
operating cost, modularity, portability, observability, and automation.

The first implementation is an Iranian online clothing business selling
women's and men's clothing. The architecture must later be reusable for
other online businesses with minimal change.

### Initial business assumptions

-   Market: Iran
-   Language: Persian / Farsi
-   UI: RTL-first
-   Products: women's and men's clothing
-   Product count: variable and scalable
-   Currency: Iranian Toman
-   Initial acquisition and communication: Instagram
-   Ecommerce core: WooCommerce
-   Automation/orchestration: n8n
-   Business management/knowledge: Notion
-   Runtime AI: API-based AI services
-   Development/custom tooling: Freebuff
-   Engineering/architecture assistance: Claude or another capable
    engineering model
-   Iranian payment and shipping providers: to be researched and
    selected later

## 2. Core Philosophy

Do not rebuild mature systems without a strong reason.

Prefer existing systems and open standards. Build custom software only
when a required capability is missing, integration requires it, or a
reusable internal tool provides clear value.

Priority:

1.  Correctness
2.  Security
3.  Simplicity
4.  Maintainability
5.  Cost efficiency
6.  Scalability
7.  Documentation

## 3. Target Architecture

``` text
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

### System roles

**WooCommerce** is the ecommerce Source of Truth for products, variants,
SKUs, prices, inventory, orders, customers, coupons, and transactional
store state.

**n8n** is the automation/orchestration layer for webhooks, scheduled
jobs, APIs, transformations, AI orchestration, retries, idempotency,
errors, and notifications.

**Notion** is the Business Operating System for dashboards, SOPs,
documentation, knowledge, content planning, ideas, review queues, and
reports. It is not the source of truth for inventory, payment, or order
state.

**AI Runtime** handles classification, extraction, content drafts,
customer assistance, sales assistance, analysis, recommendations, and
low-risk decisions. AI must never invent facts.

**Instagram** is the initial customer acquisition and communication
channel. Prefer official Meta APIs and supported integrations.

**Freebuff** is the development/custom application layer for internal
tools, dashboards, utilities, adapters, tests, refactoring, and custom
interfaces. It does not replace WooCommerce or n8n by default.

## 4. Data Architecture

The conceptual normalized model contains:

-   Products
-   Variants
-   Media
-   Options / Taxonomy

### Product

Possible fields:

-   Product ID
-   Name
-   Brand
-   Main category
-   Subcategory
-   Product status
-   Price
-   Previous price
-   Discount
-   Material/fabric
-   Color
-   Size
-   Pattern
-   Model/form
-   Style
-   Season
-   Usage
-   Collar
-   Sleeve
-   Length
-   Closure
-   Stretch
-   Fabric thickness
-   Suitable-for
-   Description
-   Short description
-   SEO title
-   SEO description
-   Keywords
-   Main image
-   Additional media
-   Product URL
-   Publication status
-   Created/updated dates
-   Internal notes

Most attributes are optional.

### Variant

A variant is a real independently sellable combination, for example:

``` text
Product P0001
Color Black
Size L
SKU P0001-BLK-L
```

Possible variant fields:

-   Variant ID
-   Product ID
-   SKU
-   Color
-   Size
-   Price
-   Sale price
-   Stock quantity
-   Stock status
-   Barcode
-   Weight
-   Status

Do not create artificial variants for products that do not need
variants.

### SKU

SKU means Stock Keeping Unit.

Rules:

-   Unique
-   Stable
-   Deterministic
-   Never silently reused
-   Production changes require human approval

A provisional pattern is:

``` text
P0001-BLK-M
```

The final production convention must be explicitly approved before
inventory automation.

### Media

Possible fields:

-   Media ID
-   Product ID
-   Media type
-   URL
-   Alt text
-   Display order
-   Source
-   Created date
-   Status

### Options / Taxonomy

May include:

-   Categories
-   Colors
-   Sizes
-   Fabrics
-   Styles
-   Seasons
-   Uses
-   Collar types
-   Sleeve types
-   Length types
-   Closure types

Use controlled vocabulary where consistency matters, while preserving
unknown/unprovided values.

## 5. Data Integrity

Incomplete product information is allowed.

AI must never invent:

-   Material
-   Color
-   Size
-   Measurements
-   Price
-   Stock
-   Discount
-   Shipping time
-   Payment status
-   Order status
-   Customer information

Use explicit states such as:

``` text
UNKNOWN
NOT_PROVIDED
AI_GENERATED
HUMAN_REVIEWED
HUMAN_VERIFIED
```

AI inference must never be presented as verified fact.

## 6. Pricing

Store Toman prices as numbers, for example:

``` text
590000
```

Do not use formatted strings such as `590,000 تومان` as the primary
stored value.

Production prices must not be changed automatically without explicit
authorization. AI may recommend a price change, but execution requires
authorization and auditability.

## 7. Inventory

WooCommerce is the transactional inventory Source of Truth.

Inventory operations must:

-   Use verified data
-   Be idempotent
-   Prevent duplicate decrements
-   Be auditable
-   Have retry/recovery behavior
-   Never use AI to estimate actual stock

## 8. Customer and Order Data

Transactional customer and order state belongs to WooCommerce or the
verified transactional provider.

Notion may contain operational references but is not the transactional
source of truth.

Payment status must be verified server-side. Shipping status must come
from a verified integration.

## 9. Human-in-the-Loop

### Green --- autonomous

-   Formatting
-   Classification
-   Drafts
-   Internal summaries
-   Low-risk transformations

### Yellow --- monitored

-   Customer response drafts
-   Product-content generation
-   Lead classification
-   Marketing drafts
-   Recommendations

### Red --- human approval

-   Refunds
-   Financial actions
-   Production price changes
-   Credential changes
-   Security changes
-   Destructive operations
-   Permanent deletion
-   High-impact disputes
-   High-risk production deployment

## 10. Security

Required baseline:

-   HTTPS/SSL
-   Secret management
-   API-key protection
-   Webhook authentication
-   Least privilege
-   2FA where available
-   Backups
-   Audit logging
-   Error monitoring
-   Development/production separation
-   Credential rotation
-   Recovery procedures

Never put secrets in source code, Git, documentation, screenshots, logs,
or public repositories.

## 11. Development and Git

Prefer:

``` text
Development -> Testing/Staging -> Production
```

Use Git for project history.

Never commit passwords, tokens, API keys, private credentials, or
unnecessary sensitive customer data.

## 12. Project Documentation

The project should contain:

``` text
MASTER_PLAN.md
PROJECT_RULES.md
README.md
ARCHITECTURE.md
DATA_MODEL.md
SECURITY.md
DECISIONS.md
TODO.md
docs/
```

## 13. Project Phases

> **Progress (2026-09-16):** Phases 0–2 closed; Phase 3 closed at
> foundation level (local-first architecture + executable local stack,
> D-053–D-056); Phase 4 infrastructure gates deferred by owner decision
> (D-058); Phase 5 closed at foundation level (n8n standards, error
> routing, HITL dead-letters — activation steps pending); Phase 6
> closed at foundation level (Notion Business OS contracts, ingestion,
> adapter/poller, conformance proof — live Notion connectivity
> owner-gated/deferred); **Phase 7 closed at foundation level** (AI
> runtime M1–M4: contracts, proposal lifecycle, HITL round-trip,
> tasks/batch, gate report — `docs/reports/PHASE_7_GATE_REPORT.md`);
> **Phase 8 complete (AI Product Manager & Operational Observability,
> D-065–D-068 all owner-approved):** unified observability collector
> (`ai.observe.v1`), owner-gated live OpenAI/Anthropic adapters with
> graceful mock fallback + BUDGET_EXCEEDED_HALT quarantine, versioned
> prompt-template registry (`local/templates/`, hash-pinned), and the
> HITL review inbox with idempotent bulk actions — end-to-end proven
> on the live PostgreSQL store. Live AI credentials remain owner-gated
> (D-045, register row 9). **Phase 9 closed at foundation level
> (Instagram Integration, D-069–D-072 all owner-approved):** Graph API
> two-step container workflow as a strict state machine with local
> Class-B pre-dispatch validation, SHA-256 publish idempotency vault
> with exclusive PostgreSQL locking (absolute double-publish
> protection), owner-gated live adapter behind `INSTAGRAM_LIVE_ENABLED`
> with token redaction, and the transactional outbox with
> D-052-aligned classifier (A backoff / B terminal / C cooldown /
> E freeze+alert) and DLQ — end-to-end proven on the live store,
> including restart-safety and concurrency. A cross-batch store defect
> was found and fixed in M4 (see `TODO.md` Phase 9). Live Instagram
> credentials remain owner-gated (D-045). Next: **Phase 10**. Details
> and exact closure gates: `TODO.md`.

### Phase 0 --- Foundation

Business definition, technology choices, planning documents, Git
repository.

### Phase 1 --- Project Architecture

Create and validate README, architecture, data model, security,
decisions, TODO, and docs structure. Approve the initial SKU strategy.

### Phase 2 --- Product Data System

Product/variant model, SKU, taxonomy, media, validation, import/export,
Excel import preparation.

### Phase 3 --- WooCommerce Foundation

Hosting, WordPress, WooCommerce, Persian/RTL, domain, SSL, product
mapping, inventory, orders, customers.

### Phase 4 --- Infrastructure

VPS/hosting, backups, monitoring, DNS, SSL, environment separation,
deployment and recovery.

### Phase 5 --- n8n Foundation

Credentials, webhooks, workflow conventions, errors, retries,
idempotency, logging, environments.

### Phase 6 --- Notion Business OS

Dashboard, SOPs, knowledge base, content calendar, ideas, review queues,
reports.

### Phase 7 --- AI Runtime

Model routing, structured outputs, validation, cost control, provenance,
logging, approval gates.

### Phase 8 --- AI Product Manager

Extraction, descriptions, SEO drafts, categorization, attribute
suggestions, data-quality checks.

### Phase 9 --- Instagram

Official Meta integration where supported, lead capture, comments, DMs,
product retrieval, handoff, logging.

### Phase 10 --- AI Sales Agent

FAQ, product discovery, availability, variants, order lookup, sales
assistance, human escalation.

### Phase 11 --- Order Management

Order notifications, status synchronization, internal tasks, customer
notifications, exception handling.

### Phase 12 --- Payment

Research Iranian provider, implement initiation, callback, server-side
verification, idempotency, failed-payment handling, logging, human
approval.

### Phase 13 --- Shipping

Research Iranian provider, shipping calculation where supported,
shipment creation, tracking, status synchronization, notifications.

### Phase 14 --- CRM

Introduce a separate CRM only if WooCommerce + Notion + n8n are
insufficient.

### Phase 15 --- Marketing Automation

Content planning, content generation, campaigns, follow-up,
segmentation, re-engagement.

### Phase 16 --- Analytics

Revenue, orders, average order value, conversion, product performance,
inventory, marketing, customers, automation, AI cost.

### Phase 17 --- AI Business Analyst

Sales trends, product performance, inventory risk, customer patterns,
marketing effectiveness, bottlenecks, cost optimization.

### Phase 18 --- Human-in-the-Loop System

Approval queues, risk levels, escalation, audit trail, manual overrides,
recovery.

### Phase 19 --- Custom Internal Tools

Build only high-value custom tools such as product bulk editors,
data-quality dashboards, workflow monitors, AI review consoles, and
business command centers.

### Phase 20 --- Security Hardening

Credential audit, permission audit, webhook audit, dependency audit,
backup/recovery verification, access review, logging review.

### Phase 21 --- Testing

Normal, empty, missing, invalid, duplicate, API failure, timeout,
authentication failure, rate limit, partial failure, malformed AI
output, rejection, retry, and recovery cases.

### Phase 22 --- Observability

Structured logs, alerts, workflow monitoring, integration health checks,
AI usage monitoring, cost monitoring, audit events.

### Phase 23 --- Cost Control

Before adding a paid service, evaluate existing capabilities, open
source, self-hosting, n8n, Freebuff, total cost, maintenance, and
lock-in.

### Phase 24 --- Vendor Lock-in

Keep provider integrations replaceable where practical, using clear
provider boundaries.

### Phase 25 --- Full System Test

Test the end-to-end flow:

``` text
Instagram lead
-> conversation
-> product discovery
-> cart/order
-> payment
-> payment verification
-> inventory
-> shipping
-> notification
-> analytics
```

Test failures and recovery at every important step.

### Phase 26 --- Launch

Launch only after security, backups, payment, inventory, shipping,
monitoring, escalation, end-to-end, and recovery checks pass.

### Phase 27 --- Optimization

Continuously improve conversion, automation, AI quality, cost,
performance, reliability, and customer experience.

### Phase 28 --- Reusable Business Engine

Extract reusable product, customer, order, workflow, AI, analytics,
notification, admin, and provider-adapter components.

## 14. Definition of Done

A phase is complete only when:

-   Implementation exists
-   Relevant tests/checks pass
-   Failure cases are considered
-   Security is reviewed
-   Documentation is updated
-   Git history is understandable
-   Required human approval exists
-   No known critical issue is hidden
-   The next phase has a clear entry condition

## 15. Freebuff Work Protocol

For every meaningful task:

1.  Read `MASTER_PLAN.md`.
2.  Read `PROJECT_RULES.md`.
3.  Read relevant documentation.
4.  Identify current phase.
5.  Identify the smallest safe change.
6.  Explain the plan before major architectural changes.
7.  Implement only approved scope.
8.  Run tests/checks.
9.  Review changes.
10. Update documentation when behavior or architecture changes.
11. Update `TODO.md` when it exists.
12. Report changes, checks, issues, risks, and next step.

For database, ecommerce, authentication, payment, security,
infrastructure, data ownership, API strategy, vendor dependency, or
production changes: stop and request human approval before high-risk
implementation.

## 16. Current Status

Current phase: **Phase 0 --- Foundation**

Completed/decided:

-   Business concept
-   Reusable engine direction
-   Product scope
-   Product Master Excel structure
-   WooCommerce
-   n8n
-   Notion
-   AI runtime direction
-   Freebuff development layer
-   Git repository
-   Planning documents

Next milestone: **Phase 1 --- Project Architecture**

First tasks:

1.  Validate planning documents.
2.  Create README.md.
3.  Create ARCHITECTURE.md.
4.  Create DATA_MODEL.md.
5.  Create SECURITY.md.
6.  Create DECISIONS.md.
7.  Create TODO.md.
8.  Create docs/.
9.  Review SKU strategy.
10. Commit the foundation.

Do not build production WooCommerce, n8n, payment, shipping, or
Instagram integrations before the architecture foundation is approved.

## 17. Final Principle

The engine must be simple, modular, automated, secure, affordable,
observable, recoverable, AI-first, API-first, scalable, portable,
maintainable, testable, and replaceable.

When two approaches are valid, prefer the simpler, safer, cheaper, more
portable, more testable, more recoverable, and less vendor-dependent
approach.
