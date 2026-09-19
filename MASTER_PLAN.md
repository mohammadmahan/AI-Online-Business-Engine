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
> credentials remain owner-gated (D-045). **Phase 12 closed at
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
