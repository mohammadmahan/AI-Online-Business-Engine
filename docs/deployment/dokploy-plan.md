# Dokploy Deployment Integration — Plan (PLANNED / D-141 Proposed)

- Status: **PLANNED — documentation only.** Nothing in this plan has been
  installed, provisioned, connected, tested, or approved. Every claim
  below is either (a) verified repository evidence, or (b) sourced from
  the official Dokploy documentation with the links and review date in
  §18. Distinguish throughout: **PLANNED** ≠ IMPLEMENTED ≠ VERIFIED ≠
  OWNER-APPROVED.
- Decision record: **D-141 (Proposed)** — adoption of Dokploy as an
  *optional, replaceable deployment-management layer*; see
  `DECISIONS.md`. Until approved, no Dokploy work beyond planning may
  start (RULES §4/§22 gate).
- Roadmap placement: post-baseline infrastructure work package
  anchored architecturally to **MASTER_PLAN Phase 4 (Infrastructure) /
  Phase 4 brief gate G1 (hosting)**, which remains open by owner
  deferral (D-058). Phases 0–26 are complete; nothing is reopened or
  rewritten — see §5.
- Date: 2026-09-20. Author: engineering session under explicit owner
  documentation authorization.

---

## 1. Purpose

Define — before any implementation — how an optional deployment-
management layer (Dokploy) could be adopted **without** weakening any
governance invariant the project has already earned: local-first
isolation (D-053), credential gating (D-045), provenance (D-026),
event-store idempotency (D-027), observability/zero-leak logging
(D-121/D-124), budget guardrails (D-127), verified-freeze recovery
(D-125), launch readiness and controlled activation (D-137–D-140),
and lock-in reduction (Phase 24 portability contracts, D-129–D-132).

The intended progression is:

```
Local Development  ->  Verification Gates  ->  Dokploy Staging
     ->  Explicit Release Approval  ->  Dokploy Production
```

Dokploy manages **deployment orchestration and operational access
only**. It must never become the authority for business rules, human
approval decisions, transactional data correctness, decision-ledger
integrity, launch readiness, recovery evidence, or production
authorization (§6).

## 2. Non-goals (this plan and any Stage-A work)

- No Dokploy installation, VPS provisioning, or firewall changes.
- No DNS changes, TLS issuance, or domain cutover.
- No GitHub App / GitHub-account connection, no deploy keys, no
  webhook creation.
- No S3 or backup-credential connection; no backup schedule enabled.
- No database migration; no import of any production or customer data.
- No deployment to Staging or Production; no automatic deployment
  enabled anywhere.
- No change to the local Docker Compose workflow (`local/infra/`)
  that the entire battery, ladder, census, and attestation depend on.
- No new business logic embedded in Dokploy UI-only settings or
  Dokploy-specific scripts (§10).
- No claims of completed installation, deployment, backup, restore,
  rollback, or security validation anywhere in this documentation.

## 3. Current-state assessment (repository evidence)

Verified state at `c6516ca` (2026-09-20):

- **Phases 0–26 complete.** Launch candidate at **technical GO**
  (D-137 readiness matrix, D-138 fail-closed attestation, D-139
  owner-gated activation protocol, D-140 evidence battery). Full
  battery 891/891 ×2 green; census T1=769 · T2=44 · T3=68 · T4=10;
  ladder 46/46; AST/entropy CLEAN; stack 5/5.
- **Deployable services** (from `local/infra/docker-compose.yml` —
  the only deployment manifest in the repository): `wordpress`
  (WooCommerce), `woodb` (MySQL 8), `canonical-db` (PostgreSQL 16),
  `n8n` (automation), `media` (MinIO, the D-056 S3-compatible media
  emulator behind `services/media_store.py`), plus `mock-woo`
  (disabled, `deferred` profile, no image). There is **no** custom
  application image yet: engine code runs in-process/locally today.
  No APIs, dashboards, workers, schedulers, or queues beyond these
  exist and none are invented here.
- **Storage surfaces:** all six volumes are Docker **named volumes**
  (`woo_data`, `woo_data_db`, `canonical_data`, `n8n_data`,
  `media_data`, `mock_state`) — no bind mounts. This matters for
  Dokploy Volume Backups (§12).
- **Data-integrity machinery that deployment tooling must not
  undermine:** D-027 event store + hash-chained Phase 19 decision
  ledger (append-only, no-teardown invariant, verified-freeze only),
  D-125 compaction archives, off-host decision-ledger replication
  via the Phase 24 `MediaStoreContract`, two-leg DR drills
  (`local/scripts/resilience_drill.py`,
  `local/scripts/decision_ledger_drill.py`), unified attestation
  (`local/scripts/launch_attestation.py`, `qa.launch_attestation.v1`).
- **Phase 4 status:** architecture-defined, gates deferred by owner
  decision (D-058; `docs/phases/phase-04-infrastructure-brief.md`).
  The brief's G1 recommendation (Iranian VPS running the same
  Docker Compose model as D-054) is the slot a deployment manager
  would occupy. Hosting itself remains an open owner decision —
  adopting Dokploy does not decide G1's *provider* question.

**Context discrepancy resolved:** historical transfer fragments may
mention "Phase 3 Batch 4"; the current repository, Git history,
decision ledger (D-001–D-141), tests, and reports establish Phases
0–26 complete. The older fragment described an early local
scaffolding batch, not the current state. Current state wins; the
fragment is not used for any status claim here.

## 4. Decision status

| Item | Status |
|---|---|
| D-141 (Dokploy adoption as optional deployment layer) | **Approved** (2026-09-20) — planning + Stages A–B only; stages C–H gated by separate per-stage authorizations |
| This plan document | Complete (planning artifact) + Stage A assessment (§20) + Stage B record (§21) |
| Runbooks (deployment, DR, exit) | Written as PLANNED procedures — none executed |
| Any Dokploy environment | Does not exist |

No evidence identifier in this document refers to a performed
operation. No new EV-* or qa.* identifiers are minted for Dokploy;
future evidence will use the existing evidence conventions at
implementation time.

## 5. Roadmap placement

- **Architectural anchor:** MASTER_PLAN §13 **Phase 4 —
  Infrastructure** ("VPS/hosting, backups, monitoring, DNS, SSL,
  environment separation, deployment and recovery") and the Phase 4
  brief's **G1 hosting gate** — the gate deferred by D-058 stays
  open; Dokploy is a *candidate tool* inside it, not a resolution of
  it.
- **Work package:** because Phases 0–26 are closed and must not be
  silently reopened, Dokploy adoption is tracked as the separate,
  post-baseline work package **“Dokploy Deployment Integration”**
  (this document + D-141 + TODO entry), status **PLANNED/Proposed**
  until its own implementation and acceptance tests exist.
- **Cross-references to existing phases** (all complete; this package
  *reuses* their mechanisms, it does not rewrite them):
  - Security hardening — Phase 20 (AST/entropy gates, D-114 boundary)
  - Testing — Phase 21 (battery, census, ladder, zero-skip)
  - Observability — Phase 22 (D-121 log ledger, D-123 probes,
    health-report attestation)
  - Cost management — Phase 23 / D-127 budgets, D-128 ceilings
  - Portability / lock-in reduction — Phase 24 (D-129–D-132,
    `MediaStoreContract`, provider-neutral contracts)
  - End-to-end validation — Phase 25 (conductor, fault ladder)
  - Launch readiness — Phase 26 (D-137 matrix, D-138 evaluator,
    D-139 activation, D-140 battery)
  - Disaster recovery — Phase 26 DR closeout (§9.4 of the phase doc)

## 6. Architecture and authority boundaries

```
Local Development (compose, 127.0.0.1 only — unchanged)
        │  battery · ladder · census · AST/entropy · attestation
        ▼
Verification Gates (existing D-120/D-138 machinery; candidate commit bound)
        ▼
Dokploy Staging  ── validates the verified artifact
        │  synthetic data only; every production-capable switch off
        ▼
Explicit Release Approval (human, auditable — NOT a Dokploy feature)
        ▼
Dokploy Production ── receives the verified artifact (§10)
```

**Dokploy is operational plumbing only. It must never be the
authority for:**

1. Business rules — remain in canonical contracts and the D-027 store.
2. Human approval decisions — remain in the Phase 19 control-audit
   chain and D-139 approval tokens (burned one-time, ledger-bound).
   Dokploy has **no verified native human-approval gate** in the
   documented edition set; approval stays OUTSIDE Dokploy (§10).
3. Transactional data correctness — PostgreSQL canonical store.
4. Decision-ledger integrity — the append-only hash chain and its
   D-125 verified-freeze treatment (never Dokploy-native compaction
   of that ledger; §12).
5. Launch readiness — D-137/D-138 evaluation machinery.
6. Recovery evidence — drills, attestation, EV-BAC-001 conventions.
7. Production authorization — D-139 one-time owner token protocol.

## 7. Environment separation

Three independent environments — Local (exists), Staging (does not
exist), Production (does not exist) — each with separate credentials,
environment variables, data, databases, object storage, networks,
domains, external-integration permissions, backup destinations, and
deployment permissions:

| Concern | Local (current) | Staging (planned) | Production (planned) |
|---|---|---|---|
| Data | fixtures/deterministic | **synthetic or explicitly owner-approved non-production only** | real, owner-authorized |
| External calls | none (D-045/D-053) | none unless individually owner-approved | owner-approved per provider |
| Payment capture | off | **off (hard config gate)** | off until owner activation |
| Shipping purchase | off | **off (hard config gate)** | off until owner activation |
| Publishing/notifications | mock | **synthetic targets only** | owner-gated |
| Backup destination | n/a | dedicated staging bucket/credentials | dedicated production bucket/credentials |
| DNS/domain | 127.0.0.1 | staging hostnames | production hostnames |
| Deployment permission | n/a | staging-scoped Dokploy roles | production-scoped, approval-gated |

The existing fail-closed configuration gates (`payment_capture_enabled`,
`shipping_purchase_enabled` in the D-137/PAY-001/SHI-001 controls)
must be reused as the environment switches — Dokploy environment
variables feed them; Dokploy never overrides their fail-closed
semantics.

Staging must never: publish real content, send real customer
communications, charge payments, mutate production inventory, call
production social-media APIs, or reach production data stores.

## 8. Service inventory (deployable units)

Derived strictly from the repository manifest — nothing invented:

| Service | Image basis | Stateful? | Volume | Backing-store candidate |
|---|---|---|---|---|
| `wordpress` (Woo) | `wordpress:6.5-php8.3-apache` | yes | `woo_data` | Dokploy-managed (files + volume) |
| `woodb` (MySQL 8) | `mysql:8.0` | yes | `woo_data_db` | pending decision (§9) |
| `canonical-db` (PostgreSQL 16) | `postgres:16-alpine` | yes | `canonical_data` | pending decision (§9) |
| `n8n` | `n8nio/n8n` | yes | `n8n_data` | pending decision (§9) |
| `media` (MinIO) | `minio/minio` | yes | `media_data` | pending decision (§9) |
| engine code | none today | n/a | n/a | future application unit(s) |

Stateful-service management choice — **kept pending** (owner decision
inside D-141, to be resolved with Stage A/B evidence, not assumed):
- (a) externally managed (managed DB / provider object storage per
  Phase 4 brief G3), or
- (b) Dokploy-managed containers + Volume Backups.
Both are viable under current documentation (§12, §18); the decision
changes the backup/restore obligations and will be made with
evidence, not by default.

## 9. Storage and database strategy

- All current volumes are named volumes → eligible for Dokploy Volume
  Backups **as a supplement**, not a replacement, for the project's
  own recovery machinery (§12).
- PostgreSQL canonical store: even if containerized, the
  `pg_dump`-level backup is subordinate to the D-027 store's own
  consistency rules; restore verification uses the existing drills,
  not Dokploy's restore success message.
- Decision ledger: its only permitted catastrophe treatment is the
  full-chain verified-freeze snapshot + atomic reinsert
  (`decision_ledger_drill.py`). Dokploy volume snapshots of
  `canonical_data` are **additional** raw-material backups; they are
  never used for compaction and never substitute the chain-verified
  restore path. Any Dokploy feature that would *compact, prune, or
  modify* that data in place is out of scope forever.
- The D-056 media abstraction keeps object storage swappable; a
  Dokploy-managed MinIO is just another `MediaStoreContract`
  implementation.

## 10. Release-governance design

**A push or merge to GitHub must never automatically authorize a
Production deployment.** Required promotion chain:

1. **CI verifies a specific commit** (existing battery/ladder/census/
   sweeps run against the exact SHA; the repository already binds
   evidence to candidate commits — reuse, don't duplicate).
2. **Immutable artifact where supported:** production promotes a
   versioned image (digest-pinned) or the verified compose artifact —
   **not** an unverified rebuild on the production host. Where
   Dokploy rebuilds from source instead of consuming a digest, that
   gap is recorded and mitigated by CI attestation of the source
   commit + drift check; digest-based promotion is preferred and its
   feasibility is a Stage C exit criterion.
3. **Staging validates that exact artifact** (same digest/definition).
4. **Explicit human approval** for production promotion — recorded
   through the project's existing auditable approval machinery
   (Phase 19 control-audit chain / D-139 burn-token), never through a
   Dokploy click alone. *Dokploy is not documented as providing a
   native human-approval gate; the approval layer therefore lives
   outside Dokploy by design.*
5. **Deployed identity recorded:** commit SHA + image digest (or
   compose definition hash) recorded in the D-121 log ledger at
   deploy time.
6. **Failed gates prevent promotion; missing, stale, malformed, or
   negative evidence fails closed** — the D-138 evaluator remains the
   only verdict authority; Dokploy cannot mark a release GO.
7. **Unauthorized repository events cannot trigger Production:**
   auto-deploy stays disabled for Production; webhooks (if used at
   all) are scoped to Staging; webhook URLs are secrets (D-045) and
   never committed.

Application rollback is defined separately from database rollback
(§12, runbooks); database changes require backward-compatible
migrations or an explicitly validated migrate-and-recover procedure —
and **rollback is not described as safe until rehearsed with the
actual application and database versions** (Stage D).

## 11. Security model

Per current official documentation (§18): role model = Owner/Admin/
Member with granular member permissions; fine-grained custom roles,
audit logs, and 2FA are edition/plan-dependent (2FA/passkeys on paid
plans; audit logs Enterprise). Therefore the plan must not assume
capabilities the selected edition may lack:

- **Admin access:** least-privilege role assignment; verify the
  selected edition's 2FA/passkey support during Stage A; if absent,
  compensate (VPN/firewall-restricted UI, IP allowlisting, short-lived
  credentials) and record the residual risk.
- **Management interface:** Dokploy UI on port 3000 must NOT be
  public; expose only via firewall restriction/VPN/tunnel. Traefik
  owns 80/443 on the Dokploy host.
- **SSH administration:** key-only, dedicated admin key(s), no
  password auth; keys scoped to the deployment host only.
- **Credential storage/rotation:** all Dokploy-side credentials are
  project secrets (D-045); rotation runbook entry; no secret ever in
  Git, logs, or screenshots; logs/reports must use placeholders.
- **GitHub access scope:** read-scoped repo access only; prefer
  fine-grained token or app limited to the exact repositories;
  Staging-only webhook; auto-deploy disabled for Production.
- **Webhook security:** secret-token webhooks; treat trigger URL as
  credential; rotate on any exposure.
- **S3 credential scope:** dedicated per-environment backup
  credentials, minimum necessary permissions (put/get/list on the
  exact bucket/prefix only), separate from application media
  credentials (Phase 24 `MediaStoreContract` continues to hold the
  app-side adapter).
- **Database network exposure:** databases bind the overlay network
  only; no published ports; management via SSH tunnels. (Current
  local compose publishes 127.0.0.1-only — the same posture is
  required remotely.)
- **TLS/domains:** Traefik-managed certificates; domain/SSL is
  environment configuration, not code (Phase 4 brief G5).
- **Auditability:** project-side audit trail remains the D-121 log
  ledger + Phase 19 control-audit chain; Dokploy-native audit logs
  (Enterprise) are a supplement if the edition provides them.
- **Alerting, disk capacity, CPU/memory sizing, host patching, log
  retention:** explicit Stage D/E checklist items (runbook); Dokploy
  monitoring is per-service and supplements — never replaces — the
  project's D-123 probes and `qa.health_report.v1`.
- **Worker/scheduled-job duplication, graceful shutdown, retry and
  idempotency:** engine idempotency (D-027 keys) tolerates duplicate
  delivery; scheduled duplication must respect D-128 resource
  ceilings and slot-lock semantics (Phase 15) — a duplicated worker
  must never double-claim a slot (the durable slot-lock ledger
  already arbitrates this).
- **Single-server failure:** Dokploy host loss is a documented DR
  scenario (§12); the control plane is recoverable from its own
  off-host backup — with the caveat that the project's data never
  depends on Dokploy's survival.
- **Control-plane failure / break-glass:** documented emergency
  access path (direct SSH + compose files in Git) exists precisely
  because Dokploy is optional and removable (§10 of the exit
  runbook).

## 12. Backup and recovery model (supplement, not replacement)

**Dokploy backup facts (official docs, §18):**
- Database backups: dedicated features per DB engine (PostgreSQL,
  MySQL, …) to configured S3 destinations, cron-scheduled.
- Volume Backups: **named volumes only** (not bind mounts), to S3,
  cron-scheduled, with a stop-container option recommended for
  consistency; restore requires the target volume to **not exist**
  and consuming containers **stopped** (compose volumes are named
  `{appName}_{volumeName}`).
- Control-plane backup: `dokploy-postgres` DB + `/etc/dokploy` → S3
  zip; restore clears `/etc/dokploy` and drops the control DB; after
  restore, server IP / DNS / Git-provider settings may need
  reconfiguration.
- Backups require a configured S3 destination.

**Project requirements layered on top:**
1. Off-host backups (S3 destination is off-host by construction) with
   **separate, least-privilege backup credentials** per environment.
2. Defined retention; encryption where supported and required.
3. Backup-failure monitoring — a failed backup is an incident routed
   through the D-124/D-121 pipeline, never a silent dashboard state.
4. **Isolated restoration targets:** restores rehearse into isolated
   namespaces/hosts, never over live state.
5. **Periodic restore drills** with application-level integrity
   checks: transactional consistency via the existing store
   verification, decision-ledger **hash-chain verification** after
   any restore touching `canonical_data` (the existing
   `decision_ledger_drill.py --consistency-only` and
   `verify_chain()` machinery).
6. Restored records must retain **source-system isolation** (the
   D-027 `(source_system, event_id)` keys) — verified post-restore.
7. Recovery evidence with timestamps and artifact identifiers,
   following EV-BAC-001 conventions; **a successful backup upload is
   NOT restoration proof** (D-137: a backup counts only after its
   restore attests; a dashboard status or exit code is not evidence).
8. Proposed RPO/RTO values are **owner-approval items** (proposed in
   the runbook; nothing approved here).
9. Control-plane recovery documentation (runbook) for Dokploy-host
   loss, including the documented post-restore IP/DNS/provider
   reconfiguration steps.
10. Scenario coverage required in the DR runbook: server loss,
    corrupted volume, failed deployment, failed database migration,
    compromised deployment credential — each with procedure, evidence
    requirements, and stop conditions.
11. **Never** test recovery by deleting, truncating, compacting, or
    destructively modifying the live append-only decision ledger;
    its catastrophe semantics are the existing atomic full-chain
    round-trip only.
12. Bind mounts are **not** covered by Dokploy Volume Backups (docs);
    the project currently has none, and introducing one would require
    a separate backup strategy — flagged as a Stage B constraint.

## 13. Observability requirements

- Dokploy per-service monitoring/logs **supplement** the project's
  D-123 probes and `qa.launch_attestation.v1`; they never replace
  them.
- Deployment events (deploy start/finish, identity, actor) are
  mirrored into the D-121 log ledger so the observability surface
  stays unified and leak-free (D-124 redaction applies).
- The launch attestation remains the readiness authority; a
  Dokploy-reported healthy service does not alter any D-137 control.

## 14. Adoption stages (A–H)

Status vocabulary: **PLANNED** (this document), **IMPLEMENTED**
(exists and runs), **VERIFIED** (tested with evidence), **BLOCKED**
(waiting on owner gate). Only Stage A has left PLANNED.

| Stage | Scope | Key exclusions | Owner approval needed | Acceptance criteria (summary) | Status |
|---|---|---|---|---|---|
| **A — Architecture & repository assessment** | Verify service inventory, volume/manifest portability, compose→Dokploy mapping notes, edition capability check (2FA/audit/roles), digest-based promotion feasibility | No installs, no accounts, no credentials | D-141 approval | Assessment notes committed; no environment touched | **VERIFIED** (§20, 2026-09-20) |
| **B — Portable deployment preparation** | Version-controlled, secret-free staging compose overlay; env-var contract (`.env` non-auto-injection documented); named-volume policy; digest/build strategy | No server, no DNS, no secrets committed | Provisioning gate (below) | Overlay validated by local compose lint/parity test | **VERIFIED** (§21, 2026-09-20) |
| **C — Isolated Staging proof of concept** | Provision staging host per approved G1 path; install Dokploy (specific pinned version, reviewed installer); deploy the *staging overlay only*; synthetic data; webhooks off or staging-scoped | No production data import; no auto-deploy to prod; no DNS for production | **VPS + installer + firewall + GitHub connect + DNS (staging)** — each separately authorized | Staging serves the stack from the approved manifest; battery-compatible checks pass against staging; deploy identity recorded | PLANNED |
| **D — Security, failure, rollback, backup, recovery verification** | DR scenarios (§12.10); restore drills incl. decision-ledger chain verification; rollback rehearsal with actual app/DB versions; credential-compromise procedure; webhook-abuse test | No destructive action against any live ledger | Import/migration/backup-credential gates as reached | Every scenario has recorded evidence; rollback proven with real versions | PLANNED |
| **E — Production-readiness evaluation** | Run the D-137 matrix + D-138 evaluator with Dokploy-specific evidence legs; RPO/RTO proposal; exit-drill dry check | No production deployment | — | D-138 verdict GO for the production *candidate* only | PLANNED |
| **F — Explicit owner approval & controlled Production activation** | D-139 protocol: preflight → dry run → canary → observation → promotion, with burn-token approvals | Automatic production deployment stays OFF | **D-139 one-time owner authorization** (separate from D-141) | Activation machine transitions recorded; ledger-bound approvals | PLANNED |
| **G — Post-deployment acceptance & operational handover** | Observability parity checks, alert routing, runbook finalization, retention enforcement | — | — | Attainment recorded via `qa.health_report.v1` | PLANNED |
| **H — Portability & Dokploy exit drill** | Execute the exit runbook: recreate the stack from Git + backups **without Dokploy**; restore control-plane-independence | No data loss tolerance | — | Stack identical (fold-verified) with Dokploy removed | PLANNED |

**Separate explicit owner authorization is required before each of:**
provisioning any VPS/server; running any installer from the internet;
opening firewall ports; connecting a GitHub account or installing any
GitHub App; creating deployment credentials; changing DNS; enabling
automatic deployment; connecting S3/backup credentials; importing any
production data; migrating a database; deploying to Production;
running any destructive recovery procedure. (Stage C/F gate columns
are summaries, not grants.)

**Stop conditions** (any stage): a governance invariant would be
weakened; an acceptance criterion fails with no in-scope fix; evidence
cannot be produced; the owner gate is unmet; D-138 verdict is not GO
at Stage E.

## 15. Risk register (summary; full handling in runbooks)

| # | Risk | Mitigation direction |
|---|---|---|
| R1 | Dokploy UI/API exposed publicly | firewall/VPN-only exposure; edition 2FA verification (Stage A) |
| R2 | Webhook abuse / unauthorized deploy trigger | staging-scoped webhooks, secret tokens, prod auto-deploy OFF |
| R3 | Volume-backup restore collision (volume exists / containers running) | restore runbook enforces documented preconditions; isolated targets |
| R4 | Bind-mount backup gap | policy: named volumes only; bind mounts require separate strategy |
| R5 | Compose rebuild ≠ verified artifact (supply drift) | digest-pinned promotion preferred; CI attestation + drift check |
| R6 | Dokploy control-plane loss | control-plane S3 backup + documented post-restore reconfiguration |
| R7 | Single-server failure takes everything | off-host backups; project data independent of Dokploy survival |
| R8 | Backup success mistaken for recoverability | restore drills mandatory; upload ≠ evidence (D-137) |
| R9 | Decision-ledger integrity damage via tooling | ledger is append-only; verified-freeze only; no Dokploy compaction of it, ever |
| R10 | Staging/production bleed (data, credentials, webhooks) | hard env separation (§7); fail-closed capture/purchase gates |
| R11 | Edition capability mismatch (2FA/audit/roles) | Stage A capability matrix before any commitment |
| R12 | Vendor lock-in via UI-only configuration | §10 exit plan; Git-reproducible config; Stage H mandatory drill |
| R13 | Port conflicts on target host (80/443/3000) | pre-flight host checklist (Stage C) |
| R14 | Scheduling/worker duplication side effects | D-027 idempotency + durable slot locks; D-128 ceilings |

## 16. Rollback and exit strategy (summary)

- **Application rollback:** redeploy the previous verified artifact
  (documented Dokploy rollback/previous-deployment behavior is to be
  confirmed on the selected version in Stage C/D); never a database
  roll-forward/back by accident.
- **Database rollback:** backward-compatible migrations required by
  default; any non-compatible change needs an explicitly validated
  migrate-and-recover procedure rehearsed in Stage D. Untested
  rollback is **not** described as safe anywhere.
- **Full exit:** the exit runbook recreates the entire stack from
  Git + restore-verified backups with Dokploy removed; because
  config is Git-first and data is in named volumes + S3, Dokploy is
  replaceable by construction (Phase 24 portability is preserved).
  Stage H proves it.

## 17. Required owner approvals (cumulative list)

1. D-141 approval (this plan → Stage A may start).
2. Staging provisioning: VPS, installer execution, firewall, GitHub
   connection, staging DNS — each explicit.
3. Backup credentials / S3 destination connection.
4. Any data import or migration.
5. Production-readiness acceptance of proposed RPO/RTO.
6. **Production activation: D-139 one-time, context-bound owner
   token** — separate from all of the above and never implied by
   them. (D-139 exists in the authoritative ledger; nothing here
   invents or bypasses it.)

## 18. Official references (reviewed 2026-09-20)

- Docker Compose integration (Compose vs Stack, env `.env` behavior
  and non-injection, volumes: bind `../files` vs named, webhook
  deploy triggers, deployment history/cancel): https://docs.dokploy.com/docs/core/docker-compose
- Volume Backups (named-volumes-only, S3 destinations, cron,
  stop-container consistency option, restore preconditions — target
  volume must not exist, containers stopped, `{appName}_{volumeName}`
  naming): https://docs.dokploy.com/docs/core/volume-backups
- Backups (control plane: `dokploy-postgres` + `/etc/dokploy` → S3
  zip; restore clears `/etc/dokploy` and drops the control DB;
  post-restore IP/DNS/Git-provider steps): https://docs.dokploy.com/docs/core/backups
- Installation (≥2GB RAM / 30GB disk; ports 80/443/3000 must be free;
  supported distros; pinned-version installer guidance):
  https://docs.dokploy.com/docs/core/installation
- Zero Downtime (default Swarm stop-then-start leads to Bad Gateway;
  ZDD requires Swarm health-check configuration — therefore ZDD is
  NOT promised for ordinary Compose deployments):
  https://docs.dokploy.com/docs/core/applications/zero-downtime
- Permissions (Owner/Admin/Member; granular member permissions;
  custom roles = Enterprise; 2FA/passkeys on paid plans; audit logs
  Enterprise): https://docs.dokploy.com/docs/core/permissions

Documentation observed may change with Dokploy releases; Stage A must
re-verify every capability claim against the version actually
selected, and update this section's review date.

## 19. Unresolved questions (owner decisions pending)

1. D-141 approval itself (adopt Dokploy as the optional deployment
   layer at all).
2. Stateful-service management: externally managed (managed DB /
   provider object storage) vs Dokploy-managed + Volume Backups (§8)
   — decided with Stage A/B evidence.
3. Hosting provider and region (Phase 4 G1 remains open; sanctions/
   payment considerations per the brief).
4. Staging host sizing (≥2GB RAM/30GB disk is the documented floor;
   the 5-service stack plus builds may want more — sized in Stage B).
5. Selected Dokploy edition/version and therefore the 2FA/audit/
   custom-role capability set (§11).
6. RPO/RTO values (proposed in the DR runbook; approved by owner).
7. Digest-based promotion mechanics for the future engine image
   (Feasibility checked in Stage C; today no application image
   exists).
8. Whether any webhook-based auto-deploy is wanted for Staging at
   all, or manual/CLI-triggered deploys only.

## 20. Stage A assessment — architecture & repository (VERIFIED 2026-09-20)

Executed under D-141 **Approved** (2026-09-20). Scope honored:
analytical only — no install, no provisioning, no server setup, no
DNS change, no credential connection, no operational change to any
environment. Every claim below is grounded in the manifest at this
commit (`local/infra/docker-compose.yml`, 140 lines) and
`.env.example` — re-verified at assessment time.

### 20.1 Service inventory — re-verified

Five active services + one disabled entry, exactly as §8 declared:

| Service | Image (registry) | Volumes | Healthcheck | depends_on |
|---|---|---|---|---|
| `wordpress` | `wordpress:6.5-php8.3-apache` | `woo_data` | CMD php | `woodb` (service_healthy) |
| `woodb` | `mysql:8.0` | `woo_data_db` | mysqladmin ping | — |
| `canonical-db` | `postgres:16-alpine` | `canonical_data` | pg_isready | — |
| `n8n` | `n8nio/n8n:latest` | `n8n_data` | /healthz | `canonical-db` (service_healthy) |
| `media` | `minio/minio:latest` | `media_data` | mc ready | — |
| `mock-woo` | `python:3.12-alpine` (placeholder) | `mock_state` | — | — (profile `deferred`) |

Confirmed: **zero `build:` contexts, zero Dockerfiles anywhere in
the repository** (filesystem search at assessment time). All
currently deployable units are registry images. The engine codebase
itself runs in-process locally — no application image exists yet.

### 20.2 Compose → Dokploy mapping notes

- **Compose-type deployment is the correct Dokploy service type**
  for this manifest (Stack/Swarm mode is not required and would
  change semantics — §18).
- `depends_on: condition: service_healthy` (wordpress→woodb,
  n8n→canonical-db) is standard compose semantics; per-service
  healthchecks already exist on all five active services — a good
  fit for Dokploy's health-check display, and a Stage C validation
  point that start-order conditions behave as locally observed.
- **Networks:** the manifest declares no explicit networks (compose
  default per-project bridge). Dokploy composes services with its
  own network naming — mapping is expected to be transparent, but
  inter-service DNS names (`woodb:3306`, `woodb:3306` style
  `WORDPRESS_DB_HOST`, canonical-db service name) must be
  re-verified in Stage C.
- `TZ: Asia/Tehran` on woodb/canonical-db and
  `GENERIC_TIMEZONE=Asia/Tehran` on n8n must carry into the staging
  overlay unchanged (deterministic chronology assumptions).

### 20.3 Environment-variable contract — assessed

`.env.example` declares **23 variables** (APP_ENV; 5 canonical-DB;
4 Woo; 2 n8n; 4 media; 2 AI; 2 logging; 3 mock-woo). The
**credential-REFERENCE pattern** (`WOO_CREDENTIAL_REF`,
`N8N_CREDENTIAL_REF`, `MEDIA_CREDENTIAL_REF`, `AI_CREDENTIAL_REF`)
means no secret value ever needs to exist in Git — exactly what the
per-environment env handling requires. Two structural facts shape
Stage B: (1) Dokploy does **not** auto-inject a `.env` file into
compose services (§18) — the overlay must declare the environment
block explicitly; (2) `APP_ENV` is the promotion-contract switch
(phase-03-3 §19) — the staging overlay pins `APP_ENV=staging` and
the battery's existing environment-awareness is the enforcement
point.

### 20.4 Storage surfaces — assessed

All six volumes are Docker **named volumes**; no bind mounts
anywhere. Every storage surface is therefore eligible for Dokploy
Volume Backups per official documentation (named-volumes-only).
Boundaries that do not move: D-125 verified-freeze archives, the
two-leg DR drills, and EV-BAC-001 remain the integrity/recovery
authority; Dokploy backups are a supplement (§12). Restore
preconditions (destination volume must not exist; consuming
containers stopped; `{appName}_{volumeName}` naming) are recorded
in the DR runbook and become Stage D rehearsal material.

### 20.5 Edition capability check (2FA / audit / roles)

Per official docs (§18, reviewed 2026-09-20): Owner/Admin/Member
roles with granular member permissions are standard; **custom roles
are Enterprise; 2FA/passkeys are paid-plan; audit logs are
Enterprise.** Consequence for a self-hosted/free deployment: the
deployment layer's own audit trail cannot be assumed. Compensating
controls required in Stage B/C: management-interface firewall
restriction, SSH hardening, and the project's authoritative audit
surfaces (D-121 `engine.log.v1`, Phase 19 `admin.control_audit`)
remain the only approval/audit record — D-141 already makes
Dokploy non-authoritative for approvals; Stage A confirms the
free edition forces that boundary rather than merely preferring it.

### 20.6 Digest-based promotion feasibility

Compose files natively support digest pinning
(`image: repo@sha256:…`), so "Staging validates the exact artifact
Production receives" is implementable **without any Dokploy-specific
promotion feature**: Stage B pins all five third-party images to
verified digests; when the future engine image exists, the §10
build-once/promote-digest pattern applies unchanged. No blocker.

### 20.7 Findings

- **F-1 (portable):** the manifest is fully portable to Dokploy —
  no build infrastructure needed; Stage B is overlay + digest
  pinning, not image engineering.
- **F-2 (exposure remodel):** the manifest's `127.0.0.1` port
  bindings are local-only semantics and cannot survive verbatim:
  naively copied they make services unreachable from the gateway;
  naively dropped they publish every service. The staging overlay
  must expose only the intended public surface (initially
  WordPress) via domain/TLS and keep canonical-db, media, n8n
  internal to the Dokploy network.
- **F-3 (restart semantics):** every service sets `restart: "no"`
  — correct locally, wrong for a hosted environment. The overlay
  must set explicit restart policies so containers survive host
  restarts.
- **F-4 (storage):** named-volumes-only means all surfaces are
  backup-eligible; restore preconditions noted; supplement-only
  boundary preserved.
- **F-5 (env contract):** 23-variable contract with credential-REF
  pattern maps cleanly; explicit environment declaration in the
  overlay required (no `.env` auto-injection); `APP_ENV=staging` is
  the hard non-production guard.
- **F-6 (edition gap):** free/self-hosted edition lacks audit logs,
  2FA, custom roles — compensating controls mandatory; project
  audit surfaces stay authoritative.
- **F-7 (zero-downtime):** not promised for ordinary Compose
  deployments (stop-then-start; Swarm health-checks required per
  §18) — staging/production acceptance includes an explicit deploy
  window; ZDD is out of scope for this plan.
- **F-8 (promotion):** digest-pinning promotion is feasible
  vendor-neutrally; no Dokploy-proprietary mechanism is required or
  assumed.

### 20.8 Stage B gates (what Stage B must deliver before Stage C)

1. **G-B1:** version-controlled, secret-free staging compose overlay
   implementing F-2/F-3/F-5 (exposure remodel, restart policies,
   `APP_ENV=staging`, digest pins per F-8) — validated by local
   compose config/lint and a battery-attested parity test; no
   server exists yet.
2. **G-B2:** env-var contract table (all 23 variables → source per
   environment; credential-REFs unchanged; staging values synthetic
   only).
3. **G-B3:** named-volume policy: backup schedule proposal,
   retention, restore preconditions — integrated with (not
   replacing) D-125/drill evidence.
4. **G-B4:** staging data policy: synthetic data only; all
   §7 staging prohibitions encoded as manifest/config facts where
   possible (e.g., AI_ENABLED=false, no production credentials).
5. **G-B5 (hand-off):** Stage C **cannot start** without its
   separate owner authorizations (VPS provisioning, installer
   execution, firewall ports, GitHub connection, staging DNS,
   S3/backup credentials — each individually granted per §14/§17).
   Stage B produces only files and local validation evidence.

> Note on stage numbering: the Isolated Staging proof of concept is
> **Stage C** in this plan; Stage B is the local, secret-free
> preparation that gates it.

**Stage A acceptance criterion met:** assessment notes committed;
no environment touched; no tooling installed.

## 21. Stage B record — staging preparation (VERIFIED 2026-09-20)

Executed under D-141 **Approved** (planning + stages A–B scope).
Documentation/configuration-only: no host, no install, no DNS, no
credentials, no deployment. Artifacts committed at this commit:

- `local/infra/compose.staging.yml` — the staging manifest (§21.1)
- `docs/deployment/staging-volume-backup-policy.md` — volume backup &
  retention template (§21.4, G-B3)
- `local/tests/test_deployment_staging_manifest.py` — battery suite
  machine-checking G-B1..G-B4 (15 tests, green ×2)

### 21.1 The staging manifest (G-B1)

**Standalone, not a merge overlay — deviation from the word
"overlay" is deliberate and technical:** F-2 requires *replacing*
the local manifest's 127.0.0.1-only port bindings, and Compose merge
semantics *append* port lists — a merge overlay cannot express that
replacement. The file is complete and self-contained, deployable
with plain `docker compose -f compose.staging.yml up` (Phase 24
exit-drill requirement).

- **Exposure remodel (F-2):** WordPress is the ONLY published
  service (host port 18080 → container 80, deliberately avoiding the
  deployment gateway's documented 80/443/3000). canonical-db, woodb,
  media, n8n publish nothing. Direct raw exposure of 18080 is a
  Stage C firewall decision (owner-gated); domain/TLS is attached by
  the deployment layer's proxy, never encoded in the manifest.
- **Restart policies (F-3):** every service `restart: unless-stopped`
  (hosted semantics; local's `"no"` replaced).
- **Digest pinning (F-8):** all six images pinned
  `tag@sha256:<index-digest>`; digests verified 2026-09-20 against
  registry `Docker-Content-Digest` headers (multi-arch index digests).
  **Source substitution:** media = `quay.io/minio/minio` —
  docker.io/minio/minio is no longer anonymously resolvable (Hub
  metadata API: object not found; registry API: 401; quay.io
  verified 2026-09-20). One self-review fix during authoring: the
  mock-woo placeholder digest was initially drafted unverified and
  was fetched-and-corrected before validation (recorded for honesty).
- **Health/start-order parity:** healthchecks on all five active
  services; `service_healthy` start conditions preserved; TZ
  Asia/Tehran carried over.
- **Vendor neutrality:** no deployment-layer labels, no UI-only
  settings, no networks block — the layer attaches its proxy network
  at deploy time; inter-service DNS re-verified in Stage C (§20.2).

### 21.2 Environment contract (G-B2)

The 23 `.env.example` variables (§20.3) extend to **23 + 6** for
staging deployment: the manifest requires six **fail-closed deploy
secrets** (`${VAR:?…}` — `docker compose config` REFUSES without
them; refusal behavior battery-tested):

| Variable | Feeds | Local analogue (throwaway) | Staging source |
|---|---|---|---|
| `CANONICAL_DB_PASSWORD` | canonical-db | `engine-local-only` (contract var) | deployment-layer env / secret store — never Git |
| `WORDPRESS_DB_PASSWORD` | wordpress | `wp-local-only` (hardcoded locally) | same |
| `MYSQL_PASSWORD` | woodb | `wp-local-only` | same |
| `MYSQL_ROOT_PASSWORD` | woodb | `root-local-only` | same |
| `N8N_ENCRYPTION_KEY` | n8n | `engine-local-encryption-only` | same |
| `MINIO_ROOT_PASSWORD` | media | `engine-local-media-only` | same |

Non-secret staging defaults are synthetic and inline
(`wordpress_staging`, `wp_staging`, `business_engine_staging`,
`engine_staging`, `staging-media`). Credential-REF pattern unchanged;
**staging grants NO AI credential ref at all** (`AI_ENABLED` unused,
no `AI_CREDENTIAL_REF` in any environment — G-B4). No local
throwaway credential literal appears in the staging file
(battery-asserted).

### 21.3 Synthetic-data policy (G-B4)

Staging runs **synthetic data only**: schema applied by
`scripts/apply_schema.py` (idempotent, as locally); no production
data import (Stage C/D owner gates). Prohibitions encoded as
manifest facts: `WORDPRESS_DEBUG=0`; staging-synthetic DB/user
names; no AI credentials; mock-woo stays profile-gated (never a
real Woo — D-052); no published ports on any data plane. Prohibitions
that live in process, not config: no real publishing, no customer
communications, no payments, no production social actions — enforced
by the §7 environment-separation model and Stage C scope review.

### 21.4 Volume backup & retention template (G-B3)

`docs/deployment/staging-volume-backup-policy.md`: per-volume
schedules/retention (proposals — RPO/RTO owner-approved pending),
off-host + separate-credential requirements, upload ≠ restoration
evidence, restore preconditions (destination volume must not exist;
consuming containers stopped; `{appName}_{volumeName}` naming), and
the explicit supplement-only relationship to D-125 archives, both DR
drills, and EV-BAC-001.

### 21.5 Validation evidence (this commit)

- `docker compose -f local/infra/compose.staging.yml config` —
  schema-valid, resolves cleanly with synthetic env (rc=0); **refuses
  without any of the six secrets (rc=1, variable named in stderr)**.
- Battery suite `local/tests/test_deployment_staging_manifest.py`:
  **15/15 green ×2** — digest pins, exposure model, restart policies,
  fail-closed secrets, no credential literals, guardrails, parity,
  healthchecks, volumes, neutrality.

### 21.6 Stage C gate checklist (hand-off — all required BEFORE Stage C)

1. Separate owner authorizations, each individually granted: VPS
   provisioning; installer execution (pinned version); firewall
   ports (18080 or the approved proxy surface); GitHub connection;
   staging DNS; S3/backup credentials.
2. Owner-approved RPO/RTO values (§21.4 proposals).
3. Owner decision: staging operator access to n8n — SSH tunnel
   default vs staging-scoped authenticated domain (§19 Q8).
4. Owner decision: any webhook-triggered deploy for staging, or
   manual deploys only (§19 Q8).
5. Selected Dokploy edition/version pinned (§19 Q5) — 2FA/audit
   capability set re-verified against the selected version (§18).
6. Staging host sizing (≥2GB/30GB floor; 5-service stack may want
   more — §19 Q4).
7. Stateful-service management choice (§19 Q2) — informed by §21.4.

**Stage B acceptance criterion met:** overlay validated by local
compose lint + battery-attested structural test; no server, no DNS,
no secrets committed.

### 21.7 Stage B amendment — networks, env template, validator (2026-09-20)

Amendment under the same D-141 Stage B scope, adding three artifacts
in response to operator review:

1. **Isolated network topology** (replaces the §21.1
   default-bridge note): the manifest now declares an explicit
   topology — `data` (bridge, `internal: true`, no outbound routing)
   carrying every stateful plane plus its consumers, and `frontend`
   (attachable by the deployment layer's proxy) carrying **WordPress
   only**. A compromised data-plane container cannot egress; nothing
   on `data` is gateway-reachable. Vendor-neutral: plain
   `docker compose up` yields the same topology. Battery-tested
   (resolved view) in `TestStagingNetworkIsolation`.
2. **`.env.staging.example`** — the full staging env contract
   documented (30 variables) with the six deploy secrets as
   `<SET-BY-DEPLOYMENT-LAYER>` placeholders and zero hardcoded
   secret values (battery-asserted). Variables are categorized:
   compose-consumed (9) · app-env contract consumed by the engine
   process/deployment environment (12) · placeholder-only (9).
3. **`local/scripts/validate_staging_compose.py`** — pre-deploy
   operator validation: schema resolution, per-variable fail-closed
   proof (config refuses without each of the six secrets), resolved
   structure (digest pins, exposure model, network isolation,
   restart/healthchecks, volumes), and bidirectional env-contract
   drift detection (manifest ⇄ template). Exit codes: 0 valid ·
   1 validation failure · 2 environment unavailable. Current run:
   **VALID, rc=0** (schema, 6×fail-closed, topology, contract
   complete).

**Directive reconciliation (operator scope note):** the Stage B
execution directive listed "Postgres, Redis, API/Backend, n8n,
Workers" as the core services. Repository evidence (Stage A §20.1,
manifest inventory, full-text search: zero Redis/Worker/API-service
references anywhere in the repo) shows this repository's core set is
WordPress/Woo, MySQL, PostgreSQL (canonical), n8n, MinIO (+ deferred
mock-woo). The manifest wires the ACTUAL core services; no Redis,
API container, or worker processes are invented — the engine runs
in-process today, and the validation script fails any service-set
drift from the base manifest. If/when engine API or worker services
materialize, they are added here by a future amendment.

## 22. Stage C readiness record (2026-09-20) — READY, execution owner-gated

Stage C deliverables are complete and battery-attested; EXECUTION
(host provisioning, installer, firewall, DNS, credentials) remains
gated per §17/§21.6 and has not occurred:

- **Provisioning runbook** —
  `docs/runbooks/dokploy-vps-provisioning.md`: owner-gate table
  (G1–G6, fail-closed), host requirements (OS/≥2GB RAM floor with
  4 GB recommended/≥30GB disk floor with 60 GB recommended per
  official docs), firewall & port plan (22 admin-restricted; 80/443
  public via Traefik; **3000 never public**; 18080 closed by
  default), SSH hardening (key-only, no root, no password), pinned
  installer procedure with human review + hash/version logging,
  initial security configuration (2FA where supported, read-scoped
  GitHub, separate minimum-privilege backup credentials, staging-only
  toggles), post-install acceptance checklist, host-level rollback,
  append-only verification log (currently EMPTY — nothing executed),
  and stop conditions.
- **Read-only VPS readiness probe** —
  `local/scripts/validate_vps_readiness.py`: SSH batch-mode (key
  only, `ConnectTimeout` bounded) checks of connectivity, OS family,
  RAM/disk floors, gateway-port occupancy (idempotent Dokploy/Traefik
  rerun support), SSH hardening state, Docker/compose presence, UFW
  status. **Mutates nothing** — the read-only guarantee is
  battery-pinned (every SSH payload must match an allowlist of
  read-only commands; forbidden operations scanned). Exit 0 ready /
  1 findings / 2 cannot-assess; the exit-2 path is exercised
  (unreachable host).
- **Battery** — `local/tests/test_stage_c_vps_readiness.py`: 14
  offline tests pinning thresholds (runbook ⇄ script agreement on
  the official floors), OS/port classification fixtures, exit
  semantics, and the read-only guarantee. 14/14 ×2 green.

**Boundary restatement:** this record marks Stage C as *READY* — not
*EXECUTED*. No host exists; no VPS has been provisioned; the installer
has not been downloaded or run; no firewall has changed; no DNS record
exists; no GitHub connection or backup credential exists. The runbook's
verification log is the execution evidence surface and is empty.

## 23. Stages D–H readiness record (2026-09-20) — READY, execution owner-gated

The Stage D–H verification frameworks are delivered and
battery-attested; EXECUTION (deploy, backup, restore, drill) remains
owner-gated and has not occurred:

- **Health & E2E validation** —
  `local/scripts/validate_staging_health.py`, two modes: MANIFEST
  (offline; health surface + synthetic probe plan for the five core
  services) and LIVE (read-only SSH drill: container health states,
  in-network synthetic probes via `compose exec`, and the DEPLOYED-side
  isolation invariants — data-plane containers must be gateway-less
  (internal network), frontend may carry WordPress only). Exit
  0/1/2 semantics; the read-only discipline is allowlist-pinned by
  battery.
- **Staging DR & backup drill runbook** —
  `docs/runbooks/staging-disaster-recovery.md`: per-store backup
  procedures (PostgreSQL logical dump + physical copy, MySQL
  single-transaction dump, MinIO mirror, n8n volume archive),
  off-host transfer + failure-alert requirements, the step-by-step
  restoration drill with official restore preconditions, the
  integrity acceptance (decision-ledger consistency + fold equality +
  health exit 0 — never dashboard status), the RPO/RTO verification
  checklist (measures the policy §2 proposals), and uniform evidence
  requirements. Boundaries: supplement-only vs D-125/drills; the
  decision ledger is never destructively touched.
- **Exit drill runbook** — `docs/runbooks/dokploy-exit-drill.md`:
  the zero-lock-in verification with invariants I1–I5 (manifest
  self-sufficiency, independence, data survival, parity, reversibility),
  scoped control-plane removal (never compose-project containers or
  volumes), and an append-only verification log (currently EMPTY).
- **Battery** — `local/tests/test_stage_dh_readiness.py`: 13 offline
  tests covering the health script (both modes, read-only payloads),
  DR runbook coverage (all four stores, integrity gates, boundaries,
  RPO/RTO consistency with the policy), exit-drill invariants, and
  manifest self-sufficiency (no layer-specific fields in non-comment
  lines). 13/13 ×2 green.

**Boundary restatement:** Stages D–H are *READY*, not *EXECUTED*. No
staging host exists, so no live drill, backup, restore, or exit run
has occurred; both new runbooks' verification logs are empty and are
the execution evidence surfaces.

## 24. Production runtime hardening record (2026-09-21) — VALIDATED LOCALLY, deployment owner-gated

Fulfills the owner directive "Phase 12 / Stage B — Dokploy deployment
manifests, container runtime hardening & integrated health probes"
(the repository's Phase 12 record is Order Management, D-081–D-084;
this work belongs to the D-141 Dokploy work package). Delivered and
**empirically executed** on the local Docker daemon with synthetic
credentials in an isolated compose project (`prodcheck`); nothing
provisioned, no host exists, D-139 activation authority untouched:

- **Production runtime manifest** — `local/infra/compose.prod.yml`:
  five services (wordpress, woodb, canonical-db, n8n, media), digest-
  pinned identical to staging, with hardening verified RUNNING, not
  just declared: `no-new-privileges:true` everywhere, **read-only
  rootfs** on canonical-db/woodb/n8n/media with explicit tmpfs+volume
  write seams (postgres PGDATA, mysql socket+datadir, n8n cache
  uid-1000-owned, minio tmp), non-root n8n (`user: "1000:1000"`),
  CPU/memory limits on every service, **ZERO published ports**
  (gateway-only frontend; data network `internal: true` — verified
  link-scope routes, no default gateway, no egress), APP_ENV
  production-fixed, mock-woo structurally absent (production reaches
  the real Woo via the D-043/D-047 live client).
  Runtime-caught fixes during validation: n8n requires a writable
  `/home/node/.cache` (root-owned tmpfs → EACCES crash) and an
  explicit `NODE_OPTIONS=--max-old-space-size` under cgroup limits
  (V8 heap OOM); both fixed in the manifest, not waived.
- **Fail-closed startup pre-flight** —
  `local/canonical/runtime_preflight.py`: `check_environment`
  refuses startup on ANY missing/malformed mandatory key (APP_ENV,
  canonical-DB SSOT five, media three, N8N_URL), any active
  prohibited key (WORDPRESS_DEBUG, AI_LIVE_ENABLED — D-045,
  N8N_DIAGNOSTICS_ENABLED), or short secrets; error messages carry
  key names, never values (D-124). `readiness_probe` composes
  pool + schema + media + n8n verdicts — missing evidence is
  NOT_READY, never a pass.
- **Health & pre-flight harness** —
  `local/scripts/validate_dokploy_runtime.py`, three modes:
  MANIFEST (offline hardening surface: nnp/limits/zero-ports/
  internal-data/frontend-wordpress-only, per-secret fail-closed
  resolution, no default credential literals, healthcheck plan);
  RUNTIME (empirical: isolated up → inspect hardening → seam
  writability → gateway-less egress checks → SSOT migration
  integrity `13/13` schemas → idempotent re-apply → scope-limited
  teardown that refuses any other project); GATE (pre-flight
  rehearsal). Exit 0/1/2 = verified/findings/environment gap.
- **SSOT schema ordering defect fixed** — the production validation
  exposed a latent `local/db/schema.sql` bug invisible locally:
  `hitl.review_tickets` and `admin.operator_actions` were created
  BEFORE their `CREATE SCHEMA` statements (fatal on a fresh database
  where the schemas do not pre-exist). Ordering corrected; guarded by
  `TestSchemaOrdering` (every schema must precede its first CREATE
  TABLE use).
- **Battery** — `local/tests/test_dokploy_runtime.py`: 13 tests
  (preflight contract incl. per-key refusal + value-withholding;
  readiness fail-closed; schema ordering guard; validator manifest/
  gate modes via subprocess; optional empirical RUNTIME mode that
  skips honestly on daemon-unreachable). 13/13 ×2 green; full
  battery 1125/1125 ×2 zero-skip.

**Boundary restatement:** this is a runtime-hardening deliverable,
not a deployment. No production host, domain, credential, or DNS
change exists or was made; the manifest has never run outside the
isolated local `prodcheck` project; D-139 remains the sole
production-activation authority and Stage C+ the owner-gated path.

## 25. Stage C sizing & target-validation record (2026-09-22)

Status: **PLANNED readiness artifacts delivered, executed only against
the local plan — no host exists, nothing provisioned.** Complements
§22 (host probe) with the sizing + target layer:

- **Sizing report** — `docs/deployment/stage-c-readiness.md`: host
  baseline derived STRICTLY from the validated `compose.prod.yml`
  (3328 MiB / 4.0 CPU container ceilings ⇒ 6 GiB RAM floor / 8 GiB
  recommended, 2 vCPU floor / 4 recommended, 40 GB disk floor / 80
  recommended, SSD required, cgroup v2 + Docker ≥ 24 + compose v2
  required); UFW/SSH baselines, zero-public-ports posture, the 9-key
  `${VAR:?}` credential inventory, volume layout, and Stage C exit
  criteria.
- **Target harness** — `local/scripts/validate_vps_target.py`, two
  strictly separated modes (exit 0/1/2): OFFLINE plan verification
  (env-contract documentation, D-045 planning hygiene — REFUSES to run
  when a real mandatory secret is present in the shell, sizing totals
  pinned to the manifest, durable volume plan, subnet guard) and an
  opt-in READ-ONLY SSH target probe (OS/CPU/RAM/disk, docker ≥ 24 +
  compose v2, cgroup v2, UFW, public-3000 guard, live docker-network
  subnet collisions) behind a command allowlist pinned by tests — no
  mutating remote command is possible.
- **Battery** — `local/tests/test_stage_c_readiness.py`: 21 tests
  (sizing pins vs report, real-output parsers, offline subprocess
  green run, fail-closed secret-in-planning-env ⇒ exit 2 with key
  names but never values, probe decision logic on a stub transport,
  per-dimension degraded findings, read-only allowlist guarantee,
  D-124 redaction).

All Stage C *execution* (provisioning, installer, firewall, DNS)
remains behind the §17/§21.6 per-item owner authorizations; the probe
mutates nothing on any host it inspects.

## 26. Stage D execution record (2026-09-22) — VERIFIED ON THE LIVE STAGING STACK

Status: **runbook + harnesses delivered AND executed against a running
staging compose project locally** (synthetic credentials; no host, no
Dokploy installation, no external mutation). Delivered:

- **Runbook** — `docs/deployment/stage-d-staging-runbook.md`: health-
  gated per-tier launch sequence (`up -d --wait`), bootstrap and smoke
  harness contracts, recovery procedures (partial failure, SSOT
  suspicion, failed rollout), abort gates, and Stage D exit criteria.
- **Bootstrap** — `local/scripts/bootstrap_staging.py`: fail-closed
  preflight (prohibited production keys abort BEFORE migration),
  idempotent 13-schema apply + O/I/L-gated seed via the proven
  seed_registry primitives, staging smoke fixture, container-scoped
  permission seam. **Transport guard:** the shared `q()` prefers host
  psql against LOCAL_* defaults — bootstrap pins the container
  transport and refuses any DB target outside `engine-staging-*`,
  eliminating the cross-environment (staging→local SSOT) defect class.
  Verified green ×2 consecutively (idempotency proof: second run
  reports the fixture "already present").
- **Smoke harness** — `local/scripts/run_staging_smoke_tests.py`,
  21/21 verified: 10 SYNTHETIC checks over the real canonical engines
  (env contract + production-leak refusal; happy path generation →
  review gate → Woo staging DRAFT (RED publish refused) → IG/TG
  dispatch with queued→published outbox transitions; D-070 dedup on
  identical key material; D-081 order replay ⇒ skipped_duplicate;
  unreviewed refusal; per-target crash isolation + durable COMPENSATED
  marker; D-124 redaction) + 11 STACK checks over the live project
  (5 healthy services, 13/13 schemas, n8n healthz inside the data
  network, isolation probes, zero published DB ports). Stack mode is
  label-based — verification needs NO secret env (health evidence
  never requires credentials). Redis/Celery reconciled: none exist in
  this stdlib-only repository; the durable outbox IS the queued-work
  plane and is what the harness verifies.
- **Battery** — `local/tests/test_stage_d_smoke.py`: 10 tests, all
  green with the stack up (synthetic subprocess run, stack-down
  degraded-honestly behavior, transport guard, preflight-before-
  migration, --check mutation-free, secret-value hygiene,
  deterministic reruns), zero skips.

Empirical findings folded in during validation: mock-woo is a deferred
profile (absent by design, not a failure); `docker compose ps` port
`null` means declared-but-unmapped (NOT published); staging and local
dev gateway share port 18080 — concurrent projects on one dev machine
must stagger the gateway (documented in the runbook).

Stage D *external* execution (remote host, DNS, real deployment)
remains owner-gated per plan §17.

## 27. Stage E record (2026-09-22) — CUTOVER RUNBOOK + READINESS HARNESS (PLANNED artifacts, execution owner-gated)

Stage E readiness deliverables authored and machine-verified offline;
**no cutover has been performed and no production host exists** —
execution requires the D-139 promotion gate plus the plan §17/§21.6
per-item owner authorizations.

- **Runbook** — `docs/deployment/stage-e-cutover-runbook.md`:
  - §2 sequence: preflight (`verify_cutover_readiness.py` offline
    V-01..V-07 all green) → **D-125 snapshot/backup proof**
    (`--snapshot`: write_snapshot → verify_snapshot → bit-flip →
    verify MUST refuse; live drill via `resilience_drill.py`) →
    controlled container transition (compose `up -d` rolling,
    health-gated per service) → post-cutover smoke
    (`run_staging_smoke_tests.py` harness, prod project) → D-139
    promotion requires the Phase-19 one-time owner approval token.
  - §3 rollback matrix **RB-1..RB-6** with the deterministic ordering
    invariant **stop new work → compensate in-flight work → reconcile
    outbox/locks/reservations** — rollback never deletes forensic
    records; a post-rollback state-verification report is mandatory.
  - §4 edge policy: HSTS ≥ 31536000, `X-Content-Type-Options: nosniff`,
    `X-Frame-Options: DENY`, CSP present, HTTP→HTTPS 301/308 redirect;
    TLS termination at the edge (Traefik/Dokploy); our manifests
    publish zero ports, so the edge is the ONLY public surface.
  - §5 owner sign-off: every live credential handoff itemized under
    D-045 (Dokploy → env secret store only; never in Git, never in
    the planning shell).
- **Harness** — `local/scripts/verify_cutover_readiness.py`
  (exit 0 = ready · 1 = findings · 2 = cannot assess):
  - OFFLINE V-01..V-07: D-138 attestation GO for a CLEAN candidate
    (composed with `launch_attestation.run_attestation` — both DR
    legs + sweeps + matrix; a dirty tree ⇒ DIRTY, fail closed);
    D-045 planning-shell refusal — a real production secret value in
    the environment aborts with exit 2 BEFORE any evaluation; env
    contract (9 `${VAR:?}` keys documented in `.env.example`);
    manifest posture scoped to the `services:` block (restart +
    cpu/mem on all five); preflight fail-closed contract proof;
    RB-1..RB-6 + header policy declared in the runbook.
  - `--snapshot`: synthetic point-in-time D-125 proof (tamper
    evidence verified).
  - `--edge URL`: opt-in live read-only probe of the cutover target
    (headers + HTTPS redirect; unreachable edge ⇒ exit 2, never a
    guess).
- **Battery** — `local/tests/test_stage_e_cutover.py`: 15 tests ×2
  consecutive green (offline CLI structure, DIRTY fail-closed, V-02
  secret refusal with redaction asserted, posture parsers incl. the
  services-block scoping regression, header accept/flag matrices,
  snapshot tamper evidence, attestation composition, runbook
  invariants).
- **Empirical finding folded in:** `manifest_service_posture`
  originally split the whole manifest, so the network names
  `frontend:`/`data:` were misparsed as services — fixed by scoping
  to the `services:` block (test-pinned).

## 28. Stage F authorization gate + Stage G acceptance record (2026-09-22) — PLANNED artifacts, execution owner-gated

- **Stage F** — `docs/deployment/stage-f-authorization.md`: the
  Stage E §6 sign-off matrix synthesized into seven blocking
  authorizations **SF-1..SF-7** (window-scoped SSH, deploy secret
  staging by key NAME only, DNS/TLS, off-host MediaStore creds,
  single-use commit-bound promotion token, break-glass ack, rotation
  plan) with the five-step token rotation procedure (Phase 19
  control-audit issuance → out-of-band delivery → single D-139
  consumption → audit-recorded; abort ⇒ NEW token, never reuse) and
  gate-exit criteria binding V-gates + `--snapshot` + `--stage-f` +
  D-138 GO on the SAME commit. Machine-verified by
  `verify_cutover_readiness.py --stage-f` (F-1 matrix integrity,
  F-2 runbook §6 ↔ SF-1..SF-6 mapping, F-3 unsigned rows reported by
  name — an empty execution log is the honest default, F-4 D-045
  leak refusal exit 2 before any evaluation). Today's honest state:
  F-3 FAILS (nothing signed); the gate converts to pass only when
  the owner completes §2.
- **Stage E edge evidence → D-138** —
  `launch_evidence.monitoring_evidence` now accepts the Stage E
  `--edge` probe report as MON-001 monitoring evidence: edge
  findings or an unassessable edge are NEGATIVE evidence (fail
  closed); green edge keeps the verdict; absent report stays
  backward-compatible. `launch_attestation.run_attestation` threads
  it through to the matrix. The nine-domain owner-approved matrix
  (D-137) is unchanged — no new control, honest folding only.
- **Stage G** — `docs/deployment/stage-g-acceptance.md`: post-cutover
  acceptance specification with automated probe definitions
  GA-1..GA-7 (container surface, SSOT integrity + zero-data-loss
  fold/chain checks, business metric lifecycle sanity, telemetry
  liveness, live edge policy conformance, budget/breaker posture,
  FRESH recovery evidence) and the evaluation protocol: explicit
  ACCEPTED/REJECTED, no partial acceptance, two consecutive green
  cycles with a synthetic business flow between them, any
  FAIL/CANNOT_ASSESS ⇒ REJECTED, rollback interlock via the Stage E
  RB-1..RB-6 ordering, fresh evidence after any rollback. Probe
  executor (`run_stage_g_acceptance.py`) is planned and authored
  only when a cutover is authorized.
- **Battery** — `local/tests/test_stage_f_authorization.py`: 23
  tests (CLI structure + rc=1-on-unsigned + D-045 exit-2 refusal,
  truncated-matrix/malformed-signature fail-closed, D-138 edge
  binding incl. backward compatibility and failing-probe dominance,
  Stage G rule pins, redaction).
- **Runbook amendment** — Stage E §6 checklist split into the six
  entry-window items (SF-1..SF-6) and the post-window rotation
  execution (SF-7) so the gate mapping is exact.

## 29. Stage H vendor-exit & restore harness record (2026-09-22) — PLANNED procedure, OFFLINE-PROVEN harness

- **Status:** the Stage H *procedure* remains owner-gated (no host
  exists); the *harness* is implemented and offline-proven.
- **Delivered:**
  - `docs/deployment/stage-h-vendor-exit.md` — the data-plane exit
    procedure composing `dokploy-exit-plan.md` (what lives where) and
    `dokploy-exit-drill.md` (I1–I5): freeze → export → **prove
    before teardown** (dry-run import parity + drill invariants) →
    teardown → re-hydrate on any vanilla target → attest. No
    forensic record is ever deleted; every destructive step is a
    separate owner-authorized action.
  - `local/scripts/verify_vendor_exit.py` — exit 0/1/2; `check`
    (offline self-proof + D-045 shell hygiene), `export` (read-only
    SSOT dump, 13 declared surfaces incl. the HITL decision ledger
    and Phase-19 control audit, D-124-redacted), `dry-run-import`
    (per-surface fold + row-count parity = 100% schema integrity and
    row parity). Armoring: PBKDF2-HMAC-SHA256 + NIST SP 800-90A
    HMAC_DRBG keystream + HMAC tag (stdlib-only defense-in-depth;
    storage-layer encryption remains the primary control).
- **D-142 memory foundation** (same battery): `local/src/memory/`
  — `vector_store.py` (pgvector DDL as pinned text, HNSW hook,
  injected-executor adapter, deterministic summarization pruning,
  deep zero-leak redaction on write AND read) and
  `memwal_adapter.py` (deterministic hash-chained `memwal.wal.v1`
  portable artifacts, offline-first sync with transparent
  local-SSOT fallback that never raises to the agent, D-125
  snapshot composition). Walrus/relayer NOT connected (D-045):
  remote transport is injected-only; battery fully air-gapped.
- **Battery:** 27 tests (`local/tests/test_stage_h_and_memwal.py`)
  — export/import round trip, tamper detection, armored round trip
  with wrong-passphrase refusal, pgvector DDL pins, KNN SQL shape,
  pruning determinism, WAL determinism/tamper/fallback, D-045
  refusal. Full battery 1221/1221 ×2 green (§30 verification).

## 30. Stage H re-hydration wired into staging smoke + D-142 consumer record (2026-09-22)

- **S-07 (Stage D smoke):** `run_staging_smoke_tests.py` now composes
  `verify_vendor_exit` directly — synthetic export → dry-run import
  with 100% per-surface fold + row-count parity over the compose-only
  surfaces — so every staging smoke run re-proves the Stage H
  data-plane guarantee (11/11 checks).
- **D-142 consumers:** `local/src/ai/memory_interceptor.py` wires the
  memory layer into the Phase 7/8 AI pipelines: `MemoryContextProvider`
  (brand guidelines / similar interactions / session summary into
  `prompt_payload["memory_context"]`), `MemoryWritingInterceptor`
  (completed interactions + evaluation summaries, deep-redacted, WAL
  export + offline-first sync), `MemoryEnabledAiRuntime` (composing
  wrapper; the canonical `ai_runtime` boundary is untouched). Every
  memory hop is guarded: store failures, missing stores, and D-127
  refusals degrade to honest per-op reports and zero-shot generation
  continues. New D-127 resource `memory_ops` (baseline 10,000/run,
  env-overridable `PHASE23_BUDGET_MEMORY_OPS`).
- **Battery:** `test_memory_ai_integration.py` 17 tests — context
  injection, degradation/fallback, budget gating both directions,
  redaction through the full pipeline, S-07 smoke integration.
  Full battery 1238/1238 ×2 green (§29 → +17).

## 31. Publishing pipeline E2E + memory feedback loop record (2026-09-22)

- **`local/src/publishing/`** (D-142 consumer extension): the
  Phase 9–12 multi-channel pipeline composed with the memory layer —
  `orchestrator.py` (schedule → DUE → per-target dispatch through the
  canonical outbox publishers → deterministic retry circuit →
  durable DLQ rows in the SSOT → budget-gated engagement feedback
  into VectorStore + portable WAL export), `telegram.py` /
  `instagram.py` (receipt-normalizing dispatchers over the canonical
  publishers), `receipts.py` (D-124 normalization), `retry_policy.py`
  (deterministic exponential backoff, 2/4/8 logical ticks, DLQ after
  3 retries; crashes and Class-B terminal violations dead-letter
  immediately — D-126 no-jitter).
- **Guarantees proven:** at-most-once per publish key (terminal-post
  skip + canonical vault guard, zero duplicate platform sends);
  canonical engines untouched (injected composition only); every
  degraded path (store failure, budget refusal, missing memory)
  fails open to the pipeline with honest reports.
- **Battery:** `test_publishing_pipeline_e2e.py` 10 tests — full
  lifecycle with feedback memory, schedule idempotency, slot
  conflicts, concurrent duplicate refusal, retry ladder, durable DLQ,
  budget-gated feedback, memory fail-open, redaction sweep over
  receipts/DLQ/memory. Full battery 1248/1248 ×2 green (§30 → +10).

## 32. Commerce & workspace sync record (2026-09-22) — Phase 13–16 facades, hermetic-proven

- **Scope:** Phase 13 (WooCommerce orders/webhooks), Phase 14 (Notion
  workspace sync), Phase 15 (catalog/stock authority), Phase 16
  (customer support AI) composed with the canonical engines and the
  D-142 memory layer. No new infrastructure; no live provider touched
  (D-045 — WooCommerce transport and Notion provider are injected
  only; every default path refuses without them).
- **Delivered:**
  `local/src/commerce/sync_orchestrator.py` — HMAC-SHA256
  fail-closed webhook intake (`verify_webhook` + explicit-verified
  requirement; a payload alone is NEVER trusted) → canonical OMS
  `place_order` lifecycle with order-intent fingerprint dedup
  (replay ⇒ `duplicate`, conflicting payload ⇒ `conflict` verdict,
  D-027 integrity violations surface as deterministic conflicts, not
  exceptions); SSOT-FIRST outbound transition sync (state committed
  before the HTTP attempt; transport failures classified via the
  D-052 taxonomy and reported, never fatal to the SSOT); refunds
  routed through `OmsEngine.transition` (COMPLETED→REFUNDED is the
  only audit-legal terminal exit — no raw HTTP drift).
  `local/src/integrations/notion_adapter.py` — replication facade
  over the shipped `services/notion_adapter.py` boundary (canonical
  `PollingEngine`/`ingest_notion_event` path, D-060 contract shape,
  bounded-queue backpressure that fails closed, deep-redacted payload
  builders).
  `local/src/commerce/support_memory_bridge.py` — Phase 16 support
  resolution: `SupportKnowledgeIndex` embeds FAQ/product/policy
  knowledge into the D-142 vector store (redacted BEFORE embedding,
  D-127 `memory_ops` gated); `SupportMemoryBridge` composes semantic
  KNN retrieval with an injected SSOT order lookup (refs/states/ids
  only — no PII, no payment material) and degrades to deterministic
  template responses on ANY memory/SSOT failure; memory is never
  order-authority (a poisoned knowledge base cannot fabricate order
  state).
- **Battery:** `test_commerce_and_workspace_e2e.py` 24 tests — HMAC
  rejection matrices, idempotent replay, conflicting-payload
  conflict, full OMS lifecycle with failing transport, inventory
  guard, D-045 refusals, canonical-ingest idempotency, backpressure,
  semantic retrieval, order-context flow, vector/lookup failure
  degradation, budget-gated hops,  canary never persisted, router context redaction, memory-not-
  authority. Full battery 1272/1272 ×2 green (§31 → +24 net census;
  24 new tests, zero losses — census machine-reconciled across all
  55 modules, module sets and per-module counts identical across
  both runs).

## 33. Analytics & Strategy Wiring (2026-09-22)

Phase 17/18 facades close the learning loop on the deployment-facing
system: `local/src/analytics/campaign_correlator.py` folds Phase 9–12
engagement and Phase 13–16 order streams through the canonical D-087
correlator into deterministic ROAS / funnel / attribution ratios, and
persists WINNING-campaign summaries through the D-142 memory layer
(deep-redacted before embedding, D-127 `memory_ops` pre-dispatch
gated, `memwal.wal.v1` WAL export for portability) so future Phase 7/8
generation starts from proven winners.
`local/src/analytics/strategy_optimizer.py` provides the deterministic
heuristic floor for schedule/category/theme recommendations and a
fail-closed telemetry circuit: publish-failure, webhook-drop and
cart-abandonment rates are evaluated against declared thresholds —
missing or malformed telemetry emits an alert (never a silent pass),
and any alert-pipeline failure LATCHES the circuit open until an
explicit operator reset.

Canonical engines untouched; all collectors and sinks injected
(D-045); analytics remains read-model only (D-026/D-027 — the SSOT
stays authoritative). Battery: `test_analytics_and_strategy_e2e.py`
25 tests; full regression 1297/1297 ×2 consecutive green across 56
modules (1272 + 25, census machine-reconciled).

## 34. Alert Escalation & Winner-Context Loop (2026-09-22)

Closes both open loops from §33 on the deployment-facing system.
`local/src/analytics/telemetry_notification_bridge.py` maps
`TelemetryCircuit` alerts onto the canonical D-089 notification
boundary AS SHIPPED (strict local validation → policy → D-090 vault
claim → durable QUEUED record): missing or malformed telemetry pages
CRITICAL (the observability surface itself is dead — bypasses quiet
hours), threshold breaches page HIGH; epoch-keyed logical identities
coalesce repeated breaches while the circuit is latched (D-090
duplicate protection does the spam control), and an operator reset
opens a new epoch so re-breaches alert again. All variables pass the
D-124 deep redactor before the event is built; transport or contract
failures surface as structured `BridgeReport`s — an alert is never
silently marked delivered.
`local/src/ai/campaign_winner_context.py` feeds the persisted
`campaign-winners` memory session back into Phase 7/8 prompt
construction: bounded, deterministic (seq-desc) retrieval through
the D-142 store's re-redacting read path, defensive line parsing,
D-127 `memory_ops` pre-dispatch gating, non-mutating payload merge,
and zero-shot degradation on any failure — the generation pipeline
never raises because of memory.

Canonical engines untouched; offline-hermetic battery
`test_notification_and_winner_context_e2e.py` (20 tests); full
regression 1317/1317 ×2 consecutive green across 57 modules
(1297 + 20, census machine-reconciled).

## 35. Infrastructure Stage B–H provisioning artifacts (2026-09-22)

- Status: **IMPLEMENTED as readiness artifacts — nothing provisioned,
  installed, or deployed.** Stage B–H remain owner-gated per §17/§21.6.
- Delivered under `local/infra/dokploy/`:
  - `README.md` — stage map, authority boundaries, and the rule that
    every value is a fail-closed reference injected from the secret
    store at deploy time (D-045/D-124; zero credential values in Git).
  - `postgres-ssot.env.example` — Stage B SSOT provisioning contract:
    non-secret identity + fail-closed `CANONICAL_DB_PASSWORD`, D-125
    drill-required `archive_command`/`archive_timeout` WAL parameters,
    and the Postgres being the only authoritative data service.
  - `redis.env.example` — Stage C broker/cache contract: fail-closed
    AUTH (`REDIS_PASSWORD`), `noeviction` durability policy, AOF
    persistence enabled.
  - `deploy_orchestrator.sh` — Stage H shell orchestration skeleton:
    preflight env validation (fails closed on any missing variable),
    stage-by-stage reachability probes, `--dry-run` mode, Stage H
    transactional spot-check (`SELECT 1`), and Stage D-125 drill
    invocation — exit 0 only on a fully green chain.
- Delivered under `local/src/infra/`:
  - `infra_health_probe.py` — Part B verification bridge: probes the
    five core surfaces (PostgreSQL SSOT, Redis broker, worker
    heartbeat, telemetry circuit state, orchestrator path) with
    INJECTED connector callables, deep-redacts every diagnostic detail
    (D-124), and fails closed with a structured report on any failure —
    internal connection strings never surface.
- Verification: new battery `test_dokploy_infrastructure.py` (24
  tests); full regression **1341/1341 ×2 consecutive green** across
  58 modules (1317 + 24, census machine-reconciled).
