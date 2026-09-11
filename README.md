# AI-First Online Business Engine

A reusable, AI-first engine for operating online businesses, built on
mature systems and automation. The first implementation is an Iranian
online clothing business (women's and men's clothing) — market: Iran,
language: Persian/Farsi, UI: RTL-first, currency: Iranian Toman,
initial acquisition channel: Instagram.

The architecture must later be reusable for other online businesses
with minimal change. The guiding principle: **build on existing
technology; do not rebuild mature systems without a strong reason.**

**Status:** Phase 1 — Project Architecture (documentation foundation).
No systems are built, connected, or configured yet.

---

## System stack

| System | Role |
| --- | --- |
| **WooCommerce** | Ecommerce Source of Truth — products, variants, SKUs, prices, inventory, orders, customers, coupons |
| **n8n** | Automation / orchestration — webhooks, workflows, AI orchestration, retries, idempotency |
| **Notion** | Business Operating System — dashboards, SOPs, knowledge, content calendar (never transactional truth) |
| **AI Runtime** | API-based AI services — classification, extraction, drafts, assistance, analysis (never invents facts) |
| **Instagram** | Initial customer acquisition and communication channel (official APIs preferred) |
| **Freebuff** | Development / custom-tool layer — internal tools, adapters, tests (does not replace WooCommerce or n8n) |

## Documentation

| Document | Purpose |
| --- | --- |
| [MASTER_PLAN.md](MASTER_PLAN.md) | Vision, architecture, data architecture, 29-phase roadmap, current status |
| [PROJECT_RULES.md](PROJECT_RULES.md) | Operational constitution: principles, safety, data integrity, protocols |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Target architecture, system roles, source-of-truth matrix, open decisions |
| [DATA_MODEL.md](DATA_MODEL.md) | Conceptual data model: Product / Variant / Media / Taxonomy, integrity rules |
| [SECURITY.md](SECURITY.md) | Security baseline, secrets policy, AI safety rules, incident handling |
| [DECISIONS.md](DECISIONS.md) | Decision log — approved decisions and open decisions (nothing silent) |
| [TODO.md](TODO.md) | Current phase checklist, blocked items, next phase preview |
| [docs/](docs/README.md) | Supporting docs: glossary, per-phase scope documents |

**Start here:** read `MASTER_PLAN.md` and `PROJECT_RULES.md` before any
meaningful work (`PROJECT_RULES.md` §2).

## How to work in this repository

1. Read `MASTER_PLAN.md`, `PROJECT_RULES.md`, relevant docs, and
   `TODO.md`.
2. Identify the current phase and make the smallest safe change.
3. Never invent data — use `UNKNOWN` / `NOT_PROVIDED`; keep AI output
   marked `AI_GENERATED` until human-reviewed.
4. High-risk areas (architecture, payment, security, credentials,
   production, destructive operations) require **STOP → EXPLAIN →
   APPROVAL** by the human owner.
5. Never commit secrets. Report partial failures honestly.
6. Update documentation when reality changes.

## Constraints

- Priorities: Correctness → Security → Simplicity → Maintainability →
  Cost efficiency → Scalability → Documentation.
- No production WooCommerce, n8n, payment, shipping, or Instagram work
  before the architecture foundation is approved (MASTER_PLAN §16).
- Payment and shipping providers (Iranian market) are **not yet
  selected** — see the open decision register in `DECISIONS.md`.
