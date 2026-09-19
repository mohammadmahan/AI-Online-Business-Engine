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
| D-141 (Dokploy adoption as optional deployment layer) | **Proposed** — requires owner approval before Stage A |
| This plan document | Complete (planning artifact) |
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
(waiting on owner gate). Nothing has left PLANNED.

| Stage | Scope | Key exclusions | Owner approval needed | Acceptance criteria (summary) | Status |
|---|---|---|---|---|---|
| **A — Architecture & repository assessment** | Verify service inventory, volume/manifest portability, compose→Dokploy mapping notes, edition capability check (2FA/audit/roles), digest-based promotion feasibility | No installs, no accounts, no credentials | D-141 approval | Assessment notes committed; no environment touched | PLANNED |
| **B — Portable deployment preparation** | Version-controlled, secret-free staging compose overlay; env-var contract (`.env` non-auto-injection documented); named-volume policy; digest/build strategy | No server, no DNS, no secrets committed | Provisioning gate (below) | Overlay validated by local compose lint/parity test | PLANNED |
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
