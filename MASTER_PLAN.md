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
> routing, HITL dead-letters — activation steps pending) with the
> core-side live wiring shipped 2026-09-20 (webhook contracts, HMAC
> auth, deterministic dispatcher, live verification script — report
> §8); Phase 10 Telegram live wiring shipped 2026-09-21 (ingress
> contracts on the D-075 seam: webhook secret-token verification
> fail-closed under D-045, strict update parsing, long-poll
> offset/dedup contracts; egress completion on the D-074/D-075/D-076
> seam; validation drill with opt-in live probe); Phase 6 Notion
> live wiring shipped 2026-09-21 (outbound client contracts on the
> D-060 seam: D-045-gated `LiveNotionClient` with injected
> transport, byte-equal block/page mapping, deterministic 3 req/sec
> pacer + jitter-free backoff plans, D-052 error classification,
> token/id redaction; validation drill with opt-in read-only live
> probe); Phase 3/4 Woo live REST client + Phase 9 classified Graph
> API layer shipped 2026-09-21 (D-043/D-047 real adapter with D-050
> RED-tier payload gates + approved-registry taxonomy validation;
> D-069..D-072 graph error taxonomy on the publisher's carriers,
> usage tracking, pinned v26.0; read-only live probes both behind
> D-045 gates); Phase 7/8 multi-provider AI routing shipped
> 2026-09-21 (DeepSeek + local-Ollama drop-in adapters on the
> D-062/D-066 seam, deterministic ProviderChain with terminal mock
> fallback, call-count circuit breaker, five-category wire error
> taxonomy incl. ContextLength→D, D-063 budget ceilings, read-only
> live probes behind D-045); Phase 6
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
> credentials remain owner-gated (D-045). **Phase 10 closed at
> foundation level (Telegram Platform Integration, D-073–D-076 all
> owner-approved):** Bot API content contract with strict local
> MarkdownV2/HTML parsing and payload constraints (caption ≤ 1024,
> text ≤ 4096, album ≤ 10, file ≤ 50 MB), SHA-256 idempotency vault on
> `telegram.publish_lock` with absolute double-post protection
> (incl. durable terminal guard), token-bucket rate pacer (30/s
> global, 1/s per chat), owner-gated live adapter behind
> `TELEGRAM_LIVE_ENABLED` with `bot<token>` redaction everywhere, and
> the transactional outbox with D-052-aligned classifier
> (A backoff / B terminal DLQ / C retry_after cooldown / E freeze +
> HITL alert) — end-to-end proven on the live store incl. 10-thread
> concurrency and restart safety. Live Telegram credentials remain
> owner-gated (D-045). **Phase 11 closed at foundation level
> (Cross-Platform Orchestration & Publication Fan-Out, D-077–D-080
> all owner-approved):** universal fan-out payload with a
> destination-matrix transform pipeline into the real platform
> contracts, the FanOutLifecycle state machine with deterministic
> partial-success aggregation from durable per-target outcomes,
> coordinated release windows (base + per-target stagger), a PG
> PK-as-lock anti-race lock (`orchestration.fanout_lock`) proven
> single-winner under 10 threads, retry coordination that never
> re-triggers served targets, HITL cancellation that never reverts
> published platforms, and a reconciliation worker that rebuilds
> job state from durable event-store data alone. Live platform
> credentials remain owner-gated (D-045). **Phase 11 live pipeline
> hardening (2026-09-21):** content-to-channel pipeline
> (`canonical/content_pipeline.py`) composes AI generation → HUMAN
> review gate (D-050) → product staging (SyncEngine, RED-tier
> proposal-gated) → fan-out (D-077/D-078) → real D-070/D-074 outbox
> publishers with duplicate-content blocking, per-target crash
> isolation, and append-only compensation markers; operator drill
> `validate_orchestration_live.py` (offline 15/15 + read-only
> ORCH_LIVE_ENABLED live probe). **Dokploy production runtime
> hardening (2026-09-21, D-141 plan §24):** hardened prod manifest
> `compose.prod.yml` (no-new-privileges, read-only rootfs + tmpfs
> seams, non-root n8n, resource limits, zero published ports,
> internal data network — empirically verified running in the
> isolated prodcheck project), fail-closed startup pre-flight
> (`runtime_preflight.py`), three-mode runtime validator, and a
> fresh-database schema-ordering fix in `db/schema.sql` (hitl/admin
> before use); deployment itself remains owner-gated (Stage C+,
> D-139). **Stage C sizing & target validation (2026-09-22, D-141
> plan §25):** `stage-c-readiness.md` sizing report derived from the
> validated manifest (6 GiB RAM / 2 vCPU / 40 GB floors, cgroup v2 +
> Docker ≥ 24 required) plus `validate_vps_target.py` — offline plan
> verification with D-045 fail-closed secret-in-planning-env refusal,
> and an opt-in READ-ONLY SSH target probe behind a test-pinned
> command allowlist; no host exists, provisioning owner-gated.
> **Stage D staging verification (2026-09-22, D-141 plan §26):**
> staging runbook + bootstrap (`bootstrap_staging.py`, transport-
> guarded against cross-environment SSOT targets) + smoke harness
> (`run_staging_smoke_tests.py`, 21/21 incl. live stack checks) +
> `test_stage_d_smoke.py` 10/10 — executed against a running local
> staging project with synthetic credentials; external deployment
> remains owner-gated. **Stage E cutover readiness (2026-09-22,
> D-141 plan §27):** cutover runbook (preflight → D-125 snapshot
> proof → health-gated transition → post-cutover smoke; RB-1..RB-6
> rollback matrix with stop→compensate→reconcile ordering; edge
> header policy; D-045 sign-off; D-139 promotion gate) +
> `verify_cutover_readiness.py` (offline V-01..V-07 fail-closed,
> `--snapshot` tamper evidence, opt-in `--edge` probe) +
> `test_stage_e_cutover.py` 15/15 ×2 — PLANNED artifacts; execution
> owner-gated under D-139. **Stage F/G (2026-09-22, D-141 plan
> §28):** Stage F authorization gate (`stage-f-authorization.md`,
> SF-1..SF-7 + token rotation; `--stage-f` machine verification,
> unsigned ⇒ fail closed) and Stage G acceptance spec
> (`stage-g-acceptance.md`, GA-1..GA-7, two-cycle protocol);
> Stage E edge evidence folded into D-138 MON-001; 23-test battery —
> all PLANNED; execution owner-gated under D-139. **Stage H + D-142
> foundation (2026-09-22, D-141 plan §29):** vendor-exit harness
> (`stage-h-vendor-exit.md` + `verify_vendor_exit.py` — SSOT export
> to tamper-evident/armored archive, dry-run import with 100%
> row-parity proof; procedure owner-gated) and the portable agent
> memory foundation (`local/src/memory/` pgvector store +
> MemWal-pattern WAL adapter, offline-first, Walrus NOT connected
> per D-045); 27-test battery. **Memory consumers wired
> (2026-09-22):** Phase 7/8 pipelines read memory context and write
> completed interactions/summaries through
> `local/src/ai/memory_interceptor.py` (zero-blockage degradation,
> D-127 `memory_ops` metering, canonical boundary untouched);
> Stage D smoke embeds the Stage H re-hydration parity proof (S-07);
> 17-test battery. **Publishing feedback loop (2026-09-22):**
> `local/src/publishing/` orchestrator composes the Phase 10/11
> engines with deterministic retry/DLQ hardening and D-142 engagement
> feedback into memory (10-test battery); canonical engines
> untouched, at-most-once delivery preserved end-to-end. **Commerce
> & workspace sync (2026-09-22):** Phase 13–16 facades compose the
> canonical engines with the D-142 memory layer — `local/src/
> commerce/sync_orchestrator.py` (HMAC fail-closed WooCommerce
> webhook intake into the D-081 lifecycle with fingerprint-deduped
> at-most-once semantics; SSOT-first outbound transition sync with
> D-052 classification; refunds via the canonical lifecycle),
> `local/src/integrations/notion_adapter.py` (injected-provider
> replication through the canonical Notion ingest path with
> backpressure and redaction), and `local/src/commerce/>  support_memory_bridge.py` (support agent semantic retrieval over
>  redacted knowledge vectors + injected SSOT order context,
>  deterministic template fallback, memory never order-authority);
>  24-test battery. **Analytics & strategy (2026-09-22):** Phase 17/18
>  facades compose the canonical D-087/D-088 read model with the
>  D-142 memory layer — `local/src/analytics/campaign_correlator.py`
>  (deterministic ROAS/funnel/attribution ratios over the canonical
>  correlator; winning-campaign summaries deep-redacted and persisted
>  through the budget-gated memory write path + portable WAL) and
>  `local/src/analytics/strategy_optimizer.py` (heuristic floor for
>  schedule/category/theme recommendations; fail-closed telemetry
>  circuit latching open on alert-pipeline failure; missing or
>  malformed telemetry is never reported healthy); 25-test battery.
>  **Alerting & learning loop closed (2026-09-22):** the Phase 18
>  telemetry circuit's alerts map onto the canonical D-089 boundary
>  (`telemetry_notification_bridge.py` — severity-tiered
>  missing/malformed=CRITICAL, breaches=HIGH; epoch-keyed D-090
>  dedup coalesces repeats while latched; transport failures surface
>  as structured reports, never silent delivery), and the persisted
>  `campaign-winners` memory session enters Phase 7/8 prompt
>  construction (`campaign_winner_context.py` — bounded, seq-desc
>  deterministic retrieval; D-127 gated; zero-blockage degradation);
>  20-test battery. **Dokploy infrastructure Stage B–H provisioning
>  artifacts (2026-09-22, plan §35 — readiness only, deployment owner-
>  gated under D-141/D-139):** `local/infra/dokploy/` stage contracts
>  (SSOT Postgres env template with D-125 WAL archiving parameters,
>  Redis AUTH/noeviction/AOF template, `deploy_orchestrator.sh`
>  fail-closed stage-by-stage shell skeleton with `--dry-run`) plus
>  `local/src/infra/infra_health_probe.py` (injected-connector health
>  probe over SSOT/broker/heartbeat/telemetry; deep-redacted
>  diagnostics; halts the deployment chain on any failure); 24-test
>  battery. **Phase 12 closed at
> foundation level (Order Management System, D-081–D-084 all
> owner-approved):** canonical order contract with line items bound
> to Product ID / Variant ID / SKU (D-017 discipline), lifecycle
> `PLACED → VALIDATED → FULFILLING → COMPLETED` with CANCELLED/
> REFUNDED terminals and `client_order_id` SHA-256 idempotency
> (D-081), provider-neutral inventory with atomic PostgreSQL
> row-lock reservation — oversell impossible by construction
> (D-082), payment-neutral boundary with fulfillment notifications
> riding the Phase 11 fan-out (D-083), and an immutable transition
> audit with TTL auto-cancel reconciliation for orphaned FULFILLING
> orders (D-084). Payment gateway and live store credentials remain
> owner-gated (D-045). Details and exact closure gates: `TODO.md`.
>
> **Phase 13 — Analytics, Reporting & Metrics Engine — CLOSED at
> foundation level (2026-09-17), D-085–D-088 all owner-approved.**
> CQRS read model over the D-027 store (projection writes ONLY to the
> `analytics` schema; transactional domains untouched, D-085),
> incremental `ingest_seq` cursor with exactly-once consumption and
> deterministic hourly/daily/monthly windows from each event's own
> `occurred_at` — no wall-clock anywhere (D-086), campaign attribution
> join between publication and OMS streams without any hard
> cross-domain dependency (D-087), and idempotent window-hash report
> generation with a PK-as-hash audit vault (D-088). Suite 28/28
> zero-skip (incl. live-PG E2E), battery 526/526, ladder 46/46; the
> live layer exposed and fixed a real snapshot-shape defect plus a
> CQRS write-orphan. Live store credentials remain owner-gated
> (D-045). Details and exact closure gates: `TODO.md`.
>
> **Phase 14 — Notification System & User Alerts — CLOSED at
> foundation level (2026-09-17), D-089–D-092 all owner-approved.**
> Universal NotificationEvent contract with strict local Class-B
> validation before queueing (D-089), exactly-once-per-channel
> delivery vault (SHA-256 dedup keys, PG PK-as-lock) with pure-
> function quiet-hours/frequency guards and independent per-channel
> fan-out (D-090), transactional outbox worker with deterministic
> exponential backoff and a HITL-materializing DLQ (D-091), and a
> fully durable delivery audit with terminal-sticky status tracking
> (D-092). Suite 26/26 zero-skip incl. live-PG E2E, battery 552/552,
> ladder 46/46; the suite exposed and fixed a DLQ read-shape defect,
> a retry-ladder stall, and a terminal-stickiness hole. No provider
> endpoints or credentials exist or are requested (D-045). Details
> and exact closure gates: `TODO.md`.
>
> **Phase 15 — Content Calendar & Scheduling Engine — CLOSED at
> foundation level (2026-09-17), D-093–D-096 all owner-approved.**
> Canonical ScheduledPost lifecycle SCHEDULED → DUE → DISPATCHED
> (+ CANCELLED / RESCHEDULED with full provenance) driven by the
> injectable clock — zero wall-clock reads (D-093); per-platform
> PK-as-lock slot reservations with a configurable gap where
> conflicting plans are recorded slot_conflict Class-B rejections
> and reschedule claims-new-before-supersede (D-094); a durable,
> ingest_seq-ordered due scanner bridging to the Phase 11
> FanOutEngine — the scheduler never publishes (D-095); and
> pre-DISPATCHED-only mutability with an append-only slot ledger and
> a calendar view rebuilt from durable events alone (D-096). Suite
> 24/24 zero-skip incl. live-PG E2E, battery 576/576, ladder 46/46.
> Details and exact closure gates: `TODO.md`.
>
> **Phase 16 — Content Versioning & Media Asset Management — CLOSED
> at foundation level (2026-09-17), D-097–D-100 all owner-approved.**
> Pure content-addressable assets (SHA-256 computed from bytes, one
> checksum = one asset, dedup by construction) with immutable
> append-only ContentVersion chains and durable version numbers
> (D-097); an AssetVault over PG unique constraints + JSON parity
> where corrupt/oversized/mime-mismatched registrations are Class-B
> rejections BEFORE any byte reaches storage (D-098); deterministic
> pure derivation keys with an idempotent PENDING_DERIVATION →
> PROCESSING → READY/FAILED variant state machine and no external
> transcoder call (D-099); and quarantine-with-cooldown lifecycle
> plus historical reconstruction from durable events alone (D-100).
> Suite 20/20 zero-skip incl. live-PG E2E (8-thread single-creator
> race), battery 596/596, ladder 46/46.
> Details and exact closure gates: `TODO.md`.
>
> **Phase 17 — AI Business Analyst & Decision Engine — CLOSED at
> foundation level (2026-09-17), D-101–D-104 all owner-approved.**
> Canonical BusinessInsight with deterministic SHA-256 evidence
> identity and the GENERATED → EVALUATED → DISPATCHED_TO_HITL /
> AUTO_ACCEPTED / DISMISSED (+ SUPERSEDED from any non-terminal
> state) lifecycle (D-101); an AnalystEngine with strict
> evaluation/application separation, evidence-only dedup audits and
> the analytics.business_insight PK as the atomic dedup (D-102);
> injected deterministic detectors over plain durable metric frames
> whose threshold breaches are recorded STRICTLY as D-027 insight
> events — no direct notifications, dispatch delegated through an
> injected seam to the Phase 14 contracts (D-103); and a
> structurally enforced HITL boundary where HIGH/CRITICAL severity
> or state-mutating payloads can never auto-accept, with the full
> decision ledger rebuildable from durable events alone (D-104).
> Suite 27/27 zero-skip incl. live-PG E2E, battery 623/623, ladder
> 46/46.
> Details and exact closure gates: `TODO.md`.
>
> **Phase 18 — HITL Approval Engine & Decision Ledger — CLOSED at
> foundation level (2026-09-17), D-105–D-108 all owner-approved.**
> Canonical HitlReviewTicket across four queues (INSIGHT_REVIEW /
> PUBLISH_GATE / ORDER_OVERRIDE / ASSET_FLAG) with the lifecycle
> PENDING_REVIEW → CLAIMED → APPROVED / REJECTED / MODIFIED /
> ESCALATED / EXPIRED — escalation a re-queuing loop with elevated
> roles, expiry decided ONLY by a deterministic sweep on an injected
> logical clock (D-105); PK-as-lock atomic claims where an 8-thread
> race yields exactly one winner, an append-only SHA-256 hash-chained
> decision ledger with tamper verification, and idempotent ingestion
> of Phase 17 DISPATCHED_TO_HITL insights (D-106/D-108); and
> idempotent resolution application through injected queue-type
> command dispatchers — a repeated approval signal produces zero
> duplicate side-effects, with zero cross-module imports (D-107).
> Suite 22/22 zero-skip incl. live-PG E2E, battery 645/645, ladder
> 46/46.
> Details and exact closure gates: `TODO.md`.
>
> **Phase 19 — Internal Tools, Operator Console & Admin Control
> Plane — CLOSED at foundation level (2026-09-17), D-109–D-112 all
> owner-approved.** A closed six-command operator grammar
> (PAUSE/RESUME_QUEUE, RETRY_DLQ_ITEM, FORCE_SUPERSEDE_INSIGHT,
> MANUAL_SLOT_OVERRIDE, REPLAY_EVENTS) with deterministic local-
> token RBAC (D-109); a ControlPlaneEngine over
> `admin.operator_actions` (PK-as-lock, exactly-once application,
> 8-thread race proven) and a global hash-chained
> `admin.control_audit` with verify_chain tamper detection (D-112);
> REPLAY strictly dry-run unless a single-use per-VALUE
> confirmation key burns before dispatch (D-110); a multi-domain
> state facade over injected reads (DLQ / HITL / insights / assets)
> with reader-error isolation; and durable queue control + DLQ
> retries with attempt budgets + circuit breakers (manual and
> threshold trips, deterministic logical-clock cool-downs,
> HALF_OPEN probes) emitting only D-027 events (D-111). Suite
> 24/24 zero-skip incl. live-PG E2E, battery 669/669, ladder
> 46/46.
> Details and exact closure gates: `TODO.md`.

> **Phase 20 — Security Hardening & Threat Model — CLOSED (2026-09-17),
> D-113–D-116 all owner-approved.** A canonical threat taxonomy and
> battery-backed control registry (every control names its test
> artifact, D-113); a system-wide `InputHardeningGate` (size/
> charset/control-char/confusable/NFC-canonicalization/JSON
> depth-width/duplicate-key, D-114) with ALL prior-phase validators
> re-audited — six unbounded surfaces hardened; chain-head
> attestation **v2** (position-weighted FULL-ROW fold over the
> Phase 18/19 hash chains — interior mutation, swap, truncation and
> append each detected; live-PG tamper proven with byte-exact
> restore) plus a durable `security.hardening_audit` vault and
> deterministic rate-limit/lockout counters on the logical clock
> (D-115); extended AST sweep + secret-entropy scan + bounds
> re-audit all CLEAN (D-116). Suite 33/33 zero-skip incl. 5 live-PG
> E2E, battery 702/702, ladder 46/46. Next: **Phase 21**.
> Details: `docs/phases/phase-20-security-hardening.md` §7, `TODO.md`.

> **Phase 21 — Testing & Quality Engineering — CLOSED (2026-09-18),
> D-117–D-120 all owner-approved.** Deterministic QA toolkit
> (tier taxonomy D-120, state-machine audit D-117, fault injectors
> D-118, seeded fuzzer D-119) in `local/canonical/qa_toolkit.py`;
> invariant battery over ALL five phase-17–20 edge matrices (closed
> by construction); chaos battery (handler/dispatcher exceptions,
> transient dispatch, mid-transaction PG aborts with clean-rollback
> + audit-truth + ledger-integrity invariants, 8-thread ledger and
> live slot-lock contention — exactly-one-winner each); 585-case
> deterministic fuzz over every D-114 entry point with frozen
> verdict fixtures. The regression net caught and fixed 3 shipped
> defects (DueScanner work-starvation on the accumulating durable
> store; a test race-key prefix collision against the never-deleted
> `slot_lock` ledger; D-114 entry-point lint pollution) — each
> pinned deterministically and mutation-checked. Tier census
> reconciles exactly: T1=629 · T2=46 · T3=42 live-PG · T4=7 →
> **battery 724/724 zero-skip, TWO consecutive green runs**;
> ladder 46/46; AST/entropy/bounds sweeps CLEAN. Next: **Phase 22**.
> Details: `docs/phases/phase-21-testing-quality.md` §6, `TODO.md`.

> **Phase 22 — Observability & Health Telemetry — CLOSED
> (2026-09-18), D-121–D-124 all owner-approved.** Canonical
> operational log ledger (`engine.log.v1`: deterministic
> trace/causal ids over causal inputs, JSONL + D-027-backed durable
> vault, D-114/D-124 zero-leak boundary — credential redaction, PII
> keys, marked truncation, Class-B taxonomy); deterministic metrics
> registry (monotone counters, fixed-bucket histograms, declared
> bounded cardinality, byte-identical exposition) with a
> loopback-only Prometheus text exporter in `local/services/`
> (bind hardcoded 127.0.0.1); composable health probes rendering
> the machine-readable `qa.health_report.v1` attestation with an
> operator CLI (live: pg PASS, ledger fold PASS, breakers honestly
> DEGRADED on durable residue). Suite 26/26 zero-skip incl. 5
> live-PG E2E; battery **750/750 zero-skip, two consecutive green
> runs**; ladder 46/46; AST (88 files) / entropy (98 files) /
> bounds (11/11) sweeps CLEAN. Next: **Phase 23**.
> Details: `docs/phases/phase-22-observability.md` §6, `TODO.md`.

> **Phase 23 — Resilience & Cost Optimization — CLOSED (2026-09-18),
> D-125–D-128 all owner-approved same-day.** Deterministic retention
> & compaction (D-125: state-based eligibility, verified-freeze
> JSONL archives with attestation folds, fail-closed teardown,
> hardening_audit manifest rows, `COMPACT_RETIREABLE` admin command,
> declared idempotent indexes + keyset reads — tamper evidence
> never weakened, chain attestation verified unchanged after
> compaction); shared resilience envelope (D-126: D-052-bound
> RetryPolicy with jitter-free logical backoff, BudgetedExecutor,
> psql transport concurrency ceiling with deterministic Class-A
> fast-fail, breaker hygiene); platform resource-budget envelopes
> (D-127: 5 resources × green/yellow, env-configurable,
> D-063-identical ≥80% warn / 100% pre-dispatch refusal, one
> consumption ledger with AI write-through); chaos × compaction ×
> quota battery (D-128: forgery detection, fail-closed compaction,
> pool saturation, quota exhaustion). Suite 20/20 zero-skip incl.
> 3 live-PG E2E; battery **770/770 zero-skip, two consecutive
> green runs**; ladder 46/46; AST (93 files) / entropy (103 files)
> sweeps CLEAN. In-batch catch: slot-lock boolean-parse defect
> (fixed, re-proven, pinned). Next: **Phase 24**.
> Details: `docs/phases/phase-23-resilience-cost.md` §6, `TODO.md`.

> **Phase 24 — Vendor Lock-in & Neutral Portability — CLOSED
> (2026-09-18), D-129–D-132 all owner-approved same-day.**
> Portability is now a tested property, not an assertion:
> ProviderContract conformance over the shipped provider set with
> D-127 token write-through proven to exact metering and 100% hard
> refusal (D-129); BackendPair parity harness — all four declared
> pairs (event store, slot locks, notification locks, media)
> mode=both with ZERO divergences incl. live PG, envelope
> divergence in JSON slot-lock `claim` caught and conformed
> (D-130); channel-adapter registry with deterministic hot-swap
> verdicts audited through the shipped D-121 LogLedger emitter and
> the D-131 channel-confinement AST rule joined to the D-116
> extended sweep (D-131); `test_phase24_portability.py` 26/26
> zero-skip incl. live-PG E2E (D-132). Battery **796/796 zero-skip,
> two consecutive green runs + census run, zero warnings**; ladder
> 46/46; census reconciles exactly (T1=694 · T2=44 · T3=51 · T4=7,
> 31 modules); entropy CLEAN (122 files); canonical AST gate green;
> stack 5/5 healthy. Next: **Phase 25**.
> Details: `docs/phases/phase-24-vendor-lockin.md` §6, `TODO.md`.

> **Phase 25 — Full System Test & E2E Failure/Recovery — CLOSED
> (2026-09-18), D-133–D-136 all owner-approved same-day.**
> The MASTER_PLAN headline flow (Instagram lead → conversation →
> product discovery → cart/order → payment → verification →
> inventory → shipping → notification → analytics) is now ONE
> deterministic execution unit: a pure ten-stage conductor with
> declared stage envelopes, zero schema mutation, and one unbroken
> D-121 trace (D-133); a fault ladder over the real engines —
> Class-A outage recovers by REPLAY, D-127 budget exhaustion
> refuses pre-dispatch, media faults fail closed, lock contention
> yields byte-untouched claims, payment failure CANCELS the order,
> RESTORES inventory, and queues the failure notice (D-134);
> stranded-lock sweeps, durable-only rebuilds, and exactly-once
> outbox replay on JSON AND live PG (D-135); the full-spectrum
> battery with offline-hermetic T4 + live-PG T3 classes (D-136).
> Suite 18/18 zero-skip incl. 3 live-PG E2E. Battery **814/814,
> two consecutive green runs + census run, zero warnings**; ladder
> 46/46; census reconciles exactly (T1=706 · T2=44 · T3=54 · T4=10,
> 32 modules); AST CLEAN (68 files) / entropy CLEAN (112 files);
> stack 5/5 healthy. Next: **Phase 26**.
> Details: `docs/phases/phase-25-full-system-test.md` §7, `TODO.md`.

> **Phase 26 — Launch (CLOSED 2026-09-19).** Nine-domain readiness
> control matrix, fail-closed deterministic Go/No-Go evaluator with
> commit+config-bound attestation, controlled activation state
> machine (preflight → dry-run → canary → observation → promotion;
> rollback reachable from every side-effect-capable state),
> one-time owner approval tokens, launch evidence pack (D-137–D-140).
> Suite 46/46 zero-skip (43 offline + 3 live-PG) ×3 green; battery
> **860/860 ×2 green, zero warnings**; ladder 46/46; census
> T1=710 · T2=46 · T3=56 · T4=13 = 860 (33 modules); sweeps CLEAN;
> stack 5/5 healthy. Result: **launch candidate established —
> NOT a launch**; live activation requires separate explicit
> one-time owner authorization. Next: **Phase 27**.
> Details: `docs/phases/phase-26-launch.md` §8, `TODO.md`.
>
> **Phase 26 extension — resilience drill operationalized
> (2026-09-19).** BAC-001 is now a first-class operator command
> (`local/scripts/resilience_drill.py`): six-stage lifecycle —
> scoped seed+fold → D-125 archive+verify → counted purge →
> rehydration → byte-equal verification → EV-BAC-001 certification —
> with CLI/JSON status output, run-scoped isolation, and fail-closed
> behavior on every fault path (drill failure ⇒ NEGATIVE evidence ⇒
> BAC-001 blocks ⇒ NO_GO). Drill evidence feeds the D-137 matrix via
> `canonical_matrix(drill_result=…)` → the D-138 bundle. Battery
> **870/870 ×2 green, zero warnings**; census (canonical D-120
> toolkit) T1=754 · T2=44 · T3=62 · T4=10 = 870 (34 modules);
> AST/entropy CLEAN; stack 5/5. Details: §9 of the phase doc.
>
> **Phase 26 extension — decision-ledger resilience (2026-09-19).**
> The disaster-proof boundary now includes the Phase 19 hash-chained
> human decision ledger: `compact()` refuses it for teardown (D-125
> governance — row removal breaks the chain permanently); the
> `decision_ledger_drill.py` operator command archives the FULL
> chain (verified-freeze), catastrophically destroys + reinserts it
> atomically, re-verifies tamper evidence (same head hash), and
> reconciles decided-vs-happened against the D-027 store. Suite-
> found defect fixed: `PgEventStore.get_record` dropped its explicit
> source (read-path twin of the Phase 9 finding). Battery
> **877/877 ×2 green, zero warnings**; census T1=758 · T2=44 ·
> T3=65 · T4=10 = 877 (35 modules). The Brain (human + AI decisions)
> is now disaster-proof alongside the transactional data.
>
> **Phase 26 DR closeout (2026-09-19) — the recovery loop is
> closed.** The decision-ledger archive now replicates OFF-HOST
> through the Phase 24 `MediaStoreContract` (re-downloaded and
> re-attested — host-level loss can no longer take chain and backup
> together; drill = 7 stages). D-138 makes a production GO require
> BOTH a fresh green transactional restore drill AND a fresh green
> decision-ledger consistency pass — every missing/failed path is
> fail-closed NO_GO, pinned by a five-path battery. The unified
> attestation command (`launch_attestation.py`) emits
> `qa.health_report.v1` + `qa.launch_attestation.v1` with a
> deterministic hash: live run **GO** — both DR legs RECOVERED,
> 533 decisions reconciled, sweeps CLEAN. Battery **891/891 ×2
> green, zero warnings**; census (D-120 toolkit) T1=769 · T2=44 ·
> T3=68 · T4=10 = 891 (36 modules); ladder 46/46; AST/entropy
> CLEAN. Launch candidate GO — live activation still owner-gated
> (D-139).
>
> **Post-baseline work package — “Dokploy Deployment Integration”
> (2026-09-20, ACTIVE; D-141 Approved — planning + Stages A–B only).**
> Optional, replaceable deployment-management layer for
> Staging/Production, anchored to the open Phase 4 G1 hosting gate
> (the D-058 deferral stands; nothing is reopened).
> `docs/deployment/dokploy-plan.md` + deployment/DR/exit runbooks —
> staged adoption A–H, per-stage owner authorizations, release
> governance (GitHub push ≠ production authorization; approvals
> stay in the Phase 19 chain + D-139 burn tokens; the append-only
> decision ledger keeps D-125 verified-freeze semantics — never
> tool-managed compaction), backups supplement D-125/drills
> (never replace), mandatory Stage-H exit drill preserves the
> Phase 24 lock-in-reduction goals. Facts sourced from official
> Dokploy documentation (reviewed 2026-09-20). **Stage A VERIFIED**
> — architecture & repository assessment committed (plan §20).
> **Stage B VERIFIED** — secret-free staging manifest
> (`local/infra/compose.staging.yml`: digest-pinned images incl. a
> documented quay.io source substitution for the media image,
> exposure remodel with WordPress as the only published surface,
> hosted restart policies, fail-closed `${VAR:?}` secret
> requirements battery-tested), environment contract 23+6,
> synthetic-data policy, volume backup/retention template
> (`docs/deployment/staging-volume-backup-policy.md`); structural
> suite 15/15 ×2 green, later extended to 25 ×2 with the Stage B
> amendment: explicit isolated network topology (data
> internal:true + frontend, wordpress-only), `.env.staging.example`
> env contract (30 variables, secrets placeholder-only), and the
> pre-deploy validator `local/scripts/validate_staging_compose.py`
> (VALID rc=0). **Stage C READY (2026-09-20, not executed):**
> provisioning runbook + read-only VPS readiness probe delivered and
> battery-attested (plan §22); **Stages D–H READY (plan §23):**
> health/E2E validation script, staging DR/backup drill runbook, and
> exit-drill runbook delivered and battery-attested. Execution
> remains gated by the §21.6/§17 per-item owner authorizations.
> **Nothing installed, provisioned, connected, or deployed.**
>
> **Post-baseline work item — “Portable multi-agent shared-memory
> layer (MemWal)” (2026-09-20, D-142 Approved, PLANNED).** Adopt
> `MystenLabs/MemWal` (Walrus Memory) as the external, encrypted,
> portable shared-memory layer for AI agents at live-AI-integration
> time — composing with the Phase 7–10 surfaces (`AiProvider`
> boundary, proposal lifecycle, observability) and the owner-stated
> future optimization workstreams — gated behind Dokploy
> infrastructure stabilization (D-141 stages C+). Boundaries:
> D-045 external-connectivity/credential gating, provider-neutral
> seam with a local deterministic parity backend (D-129/D-131,
> Phase 24 replaceability), memory writes never authority
> (D-026/D-027), zero-leak redaction (D-114/D-124). **Nothing
> installed, connected, or integrated.**
> **Post-baseline work package — "Launch hardening & cutover" (2026-09-24..25,
> D-143..D-153).** Security hardening of the publishing surface
> (D-141 plan §24), Stage C sizing & target validation, Stage D
> staging verification, cutover runbook, Stage F/G readiness (all
> D-141), Stage H + D-142 exit foundation, then the launch chain:
> Stage G acceptance closure with the immutable seal (D-152) and
> **Stage H executed — D-153**
> (commit `36066b6`): the fail-closed H-01..H-05 executor bound the
> seal, the fresh Stage F owner token, and the pre-cutover
> environment assertions into one activation with an immutable
> record. Stage H is EXECUTED; the activation is a TECHNICAL GO,
> not a production launch (D-139).
>
> **Post-baseline work package — "Dokploy Deployment Completion &
> Live Wiring" (2026-09-25..26, ACTIVE; D-154, commit `eba88a1`).**
> `dokploy.completion_attestation.v1` synthesized the full Stages
> B–H track (1606/1606 ×2 across 70 modules) and transitioned the
> program to Live Wiring. Six phases are now VERIFIED under the
> fail-closed attestation recursion (each phase gates on the
> previous attestation, canonical-bytes digest recompute matched
> against its D-112 rooting row):
> **Phase 5 — D-155** (`f2b6963`): PostgreSQL SSOT, Redis (PING
> 28.6 ms, noeviction, isolated namespace), n8n dispatcher with the
> D-027 idempotency drill — `phase5.live_wiring_attestation.v1`.
> **Phase 6 — D-156** (`50e5855`): live Notion contract layer, the
> four canonical databases schema-verified, non-destructive
> create/replay/read/archive probe — `phase6.live_wiring_attestation.v1`.
> **Phase 7 — D-157** (`2167f19`): verified runtime profile,
> deterministic `ModelRouter` routing under hard caps, the
> synthetic PM cycle over the real AI contracts ($0.00 mock
> tariff) — `phase7.live_wiring_attestation.v1`.
> **Phase 8 — D-158** (`8655c10`): Instagram Graph capability
> profile (scopes, token margin, GraphUsageTracker envelope), the
> container probe create→status→archive with NO publish ever —
> `phase8.live_wiring_attestation.v1`.
> **Phase 9 — D-159** (`f424595`): Telegram ingress sandbox (webhook
> shared-secret proven both directions, D-074 RatePacer, reply
> constructed never dispatched, zero outbound dispatch ever) —
> `phase9.live_wiring_attestation.v1`.
> **Phase 10 — D-160** (`d88325d`): Multi-channel Order
> Orchestration in STRICT SANDBOX/DRY-RUN — the synthetic order
> lifecycle through the real OMS stack (D-081 idempotency keys,
> D-082 reservations released, PLACED→VALIDATED→CANCELLED), the
> REAL D-083 fan-out boundary driven with durable receipts under
> publisher-less binds and an ephemeral D-079 lock, zero payment
> boundaries crossed — `phase10.live_wiring_attestation.v1`.
> Battery 1870/1870 ×2 consecutive green across 76 modules.
> **Phase 11 — D-161** (`d284dd9`): Payment Gateway & Settlement
> Verification in STRICT FAIL-CLOSED DRY-RUN — the sandbox gateway
> capability-capped to sandbox/dry_run/status_query (live_charge
> structurally unreachable in probe mode), deterministic
> settlement keys, D-027 settlement idempotency proven both
> directions, the OMS lifecycle through COMPLETED with the D-084
> receipt inside the COMPLETED transition ref (receipt-once
> proven), the settlement event through the REAL fan-out boundary
> under an ephemeral D-079 lock, zero real money movement —
> `phase11.payment_wiring_attestation.v1`.
> Battery 1912/1912 ×2 consecutive green across 77 modules.
> **Phase 12 — D-162** (`2218702`): Shipping & Orchestration Engine
> in STRICT FAIL-CLOSED DRY-RUN — the sandbox carrier capability-
> capped to sandbox/dry_run/tracking_query (live_ship structurally
> unreachable in probe mode, provider unselected per open decision
> 11), the D-154 slot-13 cross-walk pin (orchestration_engine =
> "Shipping"), address-free deterministic shipment keys,
> D-027 shipment idempotency proven both directions, the OMS
> lifecycle through COMPLETED with the D-084 receipt carrying the
> shipment id inside the COMPLETED transition ref (receipt-once
> proven), the tracking event through the REAL fan-out boundary
> under an ephemeral D-079 lock, zero carrier bookings —
> `phase12.shipping_wiring_attestation.v1`.
> Battery 1955/1955 ×2 consecutive green across 78 modules.
> **Phase 14 — D-164** (`f46d8b6`): Scheduling Engine (registry slot
> 15 "Marketing Automation") in STRICT DRY-RUN after the D-163
> slot-14 CRM-not-needed disposition — the REAL D-093/D-094/D-096
> calendar engine driven on the REAL D-027 store with clock-free
> contracts, deterministic idempotency keys, pure 15-minute slot
> buckets, durable SLOT_CONFLICT rejections, new-slots-first
> reschedule with superseded ledger rows, SCHEDULED→DUE→CANCELLED
> with terminal immutability, a drift-free calendar view rebuilt
> from durable events alone, the due-notification through the REAL
> fan-out boundary with publisher-less binds, and EPHEMERAL slot
> locks (zero durable claims) — the probe plans, it never dispatches
> — `phase14.scheduling_wiring_attestation.v1`.
> Battery 1999/1999 ×2 consecutive green across 79 modules.
> **Phase 15 — D-165** (`90e2eb1`): Analytics Engine (registry slot
> 16) in STRICT EPHEMERAL DRY-RUN — the REAL D-085/D-086 CQRS
> projection engine driven read-only over an injected synthetic
> stream with windowing from the recorded event instant (no wall
> clock), the D-087 classifier proven pure, count/revenue rollup
> math deterministic, incremental == full replay (zero drift), a
> malformed payload quarantined with the cursor held, the D-088
> window_hash report identity, and an EPHEMERAL cursor store behind
> a fail-closed entry gate — no warehouse, no external analytics
> platform, zero durable footprint —
> `phase15.analytics_wiring_attestation.v1`.
> Battery 2043/2043 ×2 consecutive green across 80 modules.
> **Phase 16 — D-166** (`2144df5`): Analyst Service (registry slot
> 17 "AI Business Analyst") in STRICT DRY-RUN — the REAL
> D-101/D-102/D-104 insight lifecycle driven over the REAL D-027
> store with an INJECTED PURE evaluator (no LLM SDK, no data lake,
> mock D-142-shaped fixtures), evidence-keyed dedup, the D-104 HITL
> boundary proven structural both ways, supersede with terminals
> exitless, the durable rationale rebuilt from D-027 events alone,
> invalid requests refused with zero durable rows, and an EPHEMERAL
> vault refused by class if non-ephemeral —
> `phase16.analyst_wiring_attestation.v1`.
> Battery 2087/2087 ×2 consecutive green across 81 modules.
> **Phase 17 — D-167** (`ccba01f`): Notification Engine
> (D-089–D-092; no dedicated registry slot — slot 18 stays HITL per
> the D-154 cross-walk, asserted not reassigned) in STRICT DRY-RUN —
> the REAL D-089/D-090/D-092 enqueue path driven over the REAL D-027
> store with the EPHEMERAL in-process claim backend and NO dispatch
> transport bound (zero email/SMS/push/webhook egress), the
> contact-metadata gate fail-closed (subject/phone_ref/endpoint_ref
> present-or-refuse), the D-090 dedup identity deterministic,
> quiet-hours/CRITICAL-bypass/frequency-cap policy pure, dispatch
> idempotency (a same-alert retry durably DUPLICATE_BLOCKED),
> late-transient terminal stickiness, the durable status view
> drift-free, the DLQ trigger proven at contract level, and an
> ephemeral lock backend refused by class if durable —
> `phase17.notification_wiring_attestation.v1`.
> Battery 2131/2131 ×2 consecutive green across 82 modules.
> **Phase 18 — D-168** (`1c5234b`): HITL Service (registry slot 18
> `canonical.ai_hitl_service` — THE FINAL REGISTRY IGNITION) in
> STRICT DRY-RUN — the REAL D-105/D-106/D-108 ledger engine driven
> over the REAL D-027 store with the EPHEMERAL in-process vault and
> NO reviewer-notification channel bound (zero human-surface
> egress), the analyst boundary edge (DISPATCHED_TO_HITL insights
> ingest INSIGHT_REVIEW idempotently), atomic claim discipline,
> human-only resolutions with durable payload overrides, the
> escalation loop with deterministic role elevation, the expiration
> sweep from an injected logical clock (EXPIRED sweep-only), 5
> malformed payloads refused with zero durable rows, and the D-108
> tamper-evident chains verified per ticket —
> `phase18.hitl_wiring_attestation.v1`.
> Battery 2175/2175 ×2 consecutive green across 83 modules. Registry
> slots 5–18 ALL dispositioned (slot 14 closed CRM-not-needed,
> D-163).
> **Program-level completion reconciliation — D-169** (`3cf630a`): the WHOLE
> Live Wiring track re-verified in one place — the REAL phase 5–18
> battery chain-builders re-ran the authentic chain D-154 → … →
> D-168 (14 digests recomputed byte-exactly, rooted in the D-112
> ledger, linkage unbroken, byte-stable with the governance
> record), the FULL-SUITE slot census reconciled against the LIVE
> D-154 cross-walk (12 census rows VERIFIED/WIRED, slot 14 SEALED
> per D-163, slot 18 LOCKED to `canonical.ai_hitl_service`), and
> the fail-closed invariants held end to end —
> `live_wiring.completion_reconciliation.v1`, verdict
> `PROGRAM_RECONCILED`, digest `c30d3047d28d6c69…`. Battery
> test_live_wiring_completion.py 50/50 ×2; full regression 2225/2225
> ×2 consecutive green across 84 modules. Post-closeout sync
> (`eaefa3b`): stage-e dirty-tree tests made deterministic on a
> committed tree; full regression re-run ×2 green at 2226/2226
> across 84 modules. THE LIVE WIRING PROGRAM
> (PHASES 5–18) IS COMPLETE — terminal for the track.
> **Every channel is verified, not opened**: production activation,
> live external credentials, and Iranian payment/shipping provider
> selection (open decisions 10/11) remain owner-gated
> (D-045/D-139, plan §17/§21).
>

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

> Status: **closed (launch candidate `f6d0904`+; verdict machinery
> shipped, no activation performed)** — see the blockquote above and
> `docs/phases/phase-26-launch.md` §8. Recovery rehearsal
> operationalized as the `resilience_drill.py` operator command
> (phase doc §9); drill evidence feeds the launch matrix (D-137/D-138).

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

Current phase: **Live Wiring program-level completion reconciliation
(registry closeout, D-169) --- COMPLETE --- THE LIVE WIRING PROGRAM
(PHASES 5–18) IS COMPLETE --- the engine is a verified Launch
Candidate with Stages A–H VERIFIED and Live Wiring registry slots
5--18 ALL dispositioned (5–13 and 15–18 VERIFIED/WIRED, 14 closed
CRM-not-needed, 18 TAKEN by the HITL ignition); production
activation remains owner-gated (D-139) --- owner sign-off on the
closeout record RECORDED (D-170, 2026-09-29); the track is
OFFICIALLY CLOSED and the verified Launch Candidate hands off to
Infrastructure Deployment & Staging orchestration (Dokploy Stage C
rollout — every step still owner-gated)**

Completed (Phases 0--26 plus the post-baseline hardening, Dokploy
and Live Wiring programs; per-phase detail in §13 and the
`docs/phases/` specifications):

-   Business concept, architecture foundation, and planning documents
    (Phases 0--1)
-   Canonical governance: decision ledger D-001--D-169, authority
    tiers (D-050), local-first isolation (D-053), error taxonomy
    (D-052), provenance (D-026), idempotent event store (D-027)
-   Local stack: PostgreSQL canonical store, n8n foundation, mock
    Notion/Woo providers, offline dashboard (Phases 2--6)
-   AI runtime: provider-neutral router, strict output contracts,
    HITL proposal lifecycle, budget guardrails (Phases 7--8; D-062--D-068)
-   Channels: Instagram, Telegram, cross-platform fan-out (Phases 9--11)
-   Operations: order management, analytics, notifications, scheduling,
    versioning/media (Phases 12--16)
-   Intelligence & control: AI analyst, HITL approval engine, operator
    console, security hardening, QA engineering, observability,
    resilience/cost (Phases 17--23)
-   Portability: vendor-neutral provider/storage/channel contracts
    (Phase 24; D-129--D-132)
-   Full-system E2E ladder with fault injection and self-healing
    (Phase 25; D-133--D-136)
-   Launch readiness: D-137 control matrix, D-138 fail-closed Go/No-Go
    attestation, D-139 controlled activation protocol (owner-gated),
    D-140 evidence battery (Phase 26)
-   Launch hardening & cutover: D-143..D-153, ending with Stage G
    acceptance closure (D-152, immutable seal) and the EXECUTED
    Stage H cutover (D-153, commit `36066b6`) --- a technical GO
    activation record, not a production launch
-   Dokploy Deployment Integration: Stages A--H **VERIFIED and
    COMPLETED** (D-141 program; completion attestation
    `dokploy.completion_attestation.v1` under D-154, commit
    `eba88a1`)
-   Live Wiring registry slots 5--18 **ALL DISPOSITIONED** under the
    fail-closed attestation recursion: Phase 5 data/queue/
    orchestration wiring (D-155), Phase 6 Notion Business OS
    (D-156), Phase 7 AI Runtime + Product Manager (D-157), Phase 8
    Instagram Graph probe-only (D-158), Phase 9 Telegram ingress
    sandbox (D-159), Phase 10 Multi-channel Order Orchestration
    dry-run (D-160, commit `d88325d`), Phase 11 Payment Gateway &
    Settlement dry-run with the capability-capped sandbox gateway
    (D-161, commit `d284dd9`),    Phase 12 Shipping & Orchestration
    dry-run with the capability-capped sandbox carrier and the
    slot-13 cross-walk pin
    (D-162, commit `2218702`), registry slot
    14 dispositioned CRM-not-needed (D-163 — no CRM built or
    ignited; the existing `commerce.sync_orchestrator` facade
    stands), Phase 14 Scheduling Engine dry-run with ephemeral slot
    locks and the slot-15 cross-walk pin (D-164, commit `f46d8b6`),
    Phase    15 Analytics Engine ephemeral read-side dry-run with the
    slot-16 cross-walk pin (D-165, commit `90e2eb1`), Phase 16
    Analyst Service dry-run with the injected pure evaluator and the
    slot-17 cross-walk pin (D-166, commit `2144df5`), Phase 17
    Notification Engine dry-run with NO dispatch transport bound,
    the slot-18 registry fact asserted (NOT reassigned — the D-154
    binding to `canonical.ai_hitl_service` stands; D-167, commit
    `ccba01f`), Phase 18 HITL Service ignition TAKING slot 18
    exactly as the D-154 cross-walk binds it — the final registry
    ignition, ephemeral vault, no reviewer-notification channel,
    escalation loop and D-108 tamper-evident ledger proven (D-168,
    commit `1c5234b`); the program-level completion reconciliation
    re-verified the whole track (D-169, commit `3cf630a` — chain
    unbroken, census reconciled, invariants green); decision
    ledger current through D-169
-   Disaster recovery closeout: D-125 verified-freeze compaction,
    transactional + decision-ledger drills (EV-BAC-001), off-host
    archive replication via Phase 24 `MediaStoreContract`, two-leg
    D-138 launch-gate binding, unified `qa.launch_attestation.v1`

Verified state at the D-169 reconciliation boundary:
full battery **2225/2225 ×2 consecutive green across 84 modules**,
zero skipped; post-closeout sync (`eaefa3b`): full regression re-run
×2 green at **2226/2226 across 84 modules** on the committed tree;
the D-169 reconciliation re-ran the authentic upstream
attestation chain (D-154 → … → D-168) — every digest recomputed
byte-exactly, matched its D-112 rooting, linkage unbroken and
byte-stable with the governance record; engine-local stack 5/5
healthy; attestation chain unrevoked (`dokploy.completion_attestation.v1`
→ `phase5` … → `phase12.shipping_wiring_attestation.v1` →
`phase14.scheduling_wiring_attestation.v1` →
`phase15.analytics_wiring_attestation.v1` →
`phase16.analyst_wiring_attestation.v1` →
`phase17.notification_wiring_attestation.v1` →
`phase18.hitl_wiring_attestation.v1` →
`live_wiring.completion_reconciliation.v1`). Every channel is
verified, NOT opened: zero public publishing, zero outbound Telegram
dispatch, zero real money movement ever (the settlement gateway
holds no live-charge capability), zero carrier bookings ever (the
shipping carrier holds no live-ship capability and the provider is
unselected), zero scheduled-post dispatches ever (the scheduling
probe plans and never dispatches), zero analytics egress ever (the
projection loop is read-only, in-process and ephemeral),zero LLM/AI-provider contact in the analyst probe (the evaluator is
injected and pure; insights stop at DISPATCHED_TO_HITL, ingested by
the D-168 HITL service — ignited, not opened), zero email/SMS/push/webhook egress ever in the
notification probe (no channel adapter is bound; alerts stop at
durable QUEUED/receipted states), zero human-notification or
reviewer-signal egress ever in the HITL probe (no dashboard or
notification emitter is bound; decisions stop at durable tickets and
the tamper-evident ledger).

Next milestone: **owner-authorized controlled activation**
(D-139 preflight → dry run → canary → observation → promotion) ---
a separate, explicit, one-time owner decision; a technical GO is
necessary but NOT sufficient. The Live Wiring program itself is
CLOSED (D-169 reconciliation: the chain unbroken, the all-slot
census reconciled, the fail-closed invariants green — no further
wiring phases exist). Provider selection for Iranian payment (open
decision 10) and shipping (open decision 11) remains open and is
required before payment-capture and shipping-purchase go-live;
owner review of the Phase 14–18 completion records (D-164–D-168)
closes those phases. The owner has SIGNED OFF on the D-169 closeout
record (D-170, 2026-09-29) — the Live Wiring track is OFFICIALLY
CLOSED; the Launch Candidate hands off to Infrastructure Deployment
& Staging orchestration (Dokploy Stage C rollout and beyond — every
step still owner-gated;
`docs/deployment/launch-candidate-handoff.md`).

Standing invariants (reaffirmed): fail-closed posture on every
ignition path; local-first sandbox isolation (D-053); all
production switches owner-gated (D-139/D-045); payment and shipping
live providers UNSELECTED; release governance holds --- GitHub push
is never production authorization.
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
