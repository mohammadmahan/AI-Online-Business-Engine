# Runbook: Staging Deployment (Stage D — PLANNED, execution owner-gated)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED readiness artifact.** No staging host exists yet;
  the deliverables here — this runbook, `local/scripts/bootstrap_staging.py`
  and `local/scripts/run_staging_smoke_tests.py` — are executed only
  after the Stage C owner gates (plan §17/§21.6) are granted and a host
  has passed `validate_vps_target.py` + `validate_vps_readiness.py`
  (both exit 0).
- Prerequisites: Stage C complete; the secret-free staging manifest
  `local/infra/compose.staging.yml` (Stage B, G-B1–G-B4 verified);
  synthetic-data policy (plan §21.3); volume backup policy
  (`docs/deployment/staging-volume-backup-policy.md`).

## 0. Authority gates (binding)

- **D-045:** staging runs with ZERO live platform credentials. Every
  live flag (`AI_LIVE_ENABLED`, `WOO_LIVE_ENABLED`,
  `INSTAGRAM_LIVE_ENABLED`, `TELEGRAM_LIVE_ENABLED`,
  `NOTION_LIVE_ENABLED`, `ORCH_LIVE_ENABLED`) is `false`/absent by
  contract; the canonical adapters are construction-gated and refuse
  without keys even if a flag were set. Staging data is synthetic
  (plan §21.3) — no real customer data, no real publishing, no
  payments, no production inventory mutation.
- **D-139:** staging is a rehearsal environment. Nothing executed here
  authorizes Production activation; promotion remains a separately
  owner-approved sequence.
- **D-141:** SSH access to the staging host, DNS/domain for the
  staging UI, and any backup credential are each separate owner
  authorizations recorded per plan §17.

## 1. Environment separation (verified properties, not aspirations)

| Dimension | Staging value | Enforced by |
|---|---|---|
| Database | `business_engine_staging` @ internal `data` net | manifest `${CANONICAL_DB_NAME:-business_engine_staging}` |
| Gateway surface | `18080:80` ONLY (firewalled at Stage C) | manifest F-2 |
| Provider endpoints | mock adapters in-process; `engine-staging-mockwoo` placeholder container | D-052/D-043 |
| `APP_ENV` | `staging` (preflight admits local/staging/production per env_name contract) | `runtime_preflight.check_environment` |
| Secrets | `${VAR:?}` fail-closed; injected at deploy only | manifest G-B5/D-045 |
| Networks | `data` internal; `frontend` gateway-only | Stage B amendment |

## 2. Deployment sequence (per-service, health-gated)

Run from the repository root on the staging host (or via the Dokploy
stack deploy — the compose file is Dokploy-compatible by Stage B G-B1):

```bash
# 2.0 preconditions (fail closed)
python3 local/scripts/validate_staging_compose.py          # rc 0 required
# export the staging secret set per .env.example (never committed)
export N8N_ENCRYPTION_KEY=...        # owner-injected
export CANONICAL_DB_PASSWORD=...     # owner-injected

# 2.1 pull (quiet) then start DBs first; wait for health before dependents
docker compose -f local/infra/compose.staging.yml pull --quiet
docker compose -f local/infra/compose.staging.yml up -d woodb canonical-db
docker compose -f local/infra/compose.staging.yml \
    up -d --wait woodb canonical-db          # exits non-zero unless healthy

# 2.2 SSOT bootstrap: schema (13 schemas, idempotent) + registry seed
#     (O/I/L-gated) + staged permission adjustments — see §3
python3 local/scripts/bootstrap_staging.py

# 2.3 stateful-adjacent services, then the gateway surface last
docker compose -f local/infra/compose.staging.yml up -d --wait media n8n
docker compose -f local/infra/compose.staging.yml up -d --wait wordpress mockwoo

# 2.4 verify the isolated topology + health plan
python3 local/scripts/validate_staging_health.py            # manifest mode
python3 local/scripts/run_staging_smoke_tests.py            # synthetic E2E
```

Zero-downtime notes: `up -d --wait` gates each tier on its healthcheck
(db 5s×30, n8n 10s×12); the gateway (WordPress) starts LAST so a failed
bootstrap never leaves a publicly reachable half-stack; restart policy
is `unless-stopped` (documented Docker Compose behavior — NOT a
zero-downtime guarantee; plan §8 reserves zero-downtime claims).

## 3. Bootstrap: `local/scripts/bootstrap_staging.py`

One idempotent operator command that composes the existing, proven
primitives (no parallel seed logic is invented):

1. **Preflight (fail-closed):** `runtime_preflight.check_environment`
   runs against the exported staging env with `env_name="staging"` —
   missing mandatory keys, malformed values, or an active prohibited
   production key (`WORDPRESS_DEBUG`, `AI_LIVE_ENABLED`,
   `N8N_DIAGNOSTICS_ENABLED`) aborts BEFORE any migration. Error text
   carries key names, never values (D-124).
2. **Schema migration:** applies `local/db/schema.sql` idempotently
   through `seed_registry.q` (host psql → container psql fallback,
   same transport as `apply_schema.py`), then asserts all **13
   schemas** (`seed canonical registry events provenance hitl admin
   assets oms analytics orchestration instagram telegram`) exist.
3. **Seed verification:** reuses `seed_registry.verify()` — registry
   counts pinned against `canonical/vocab.py`, O/I/L gate audited
   in-database, owner-sanctioned codes surfaced separately (D-030/D-057).
4. **Baseline synthetic seed:** inserts a minimal staging-only smoke
   product fixture into the canonical store IF absent (deterministic
   IDs `STG-...`; never touches production namespaces).
5. **Permission adjustments (staged, idempotent):** ensures the
   n8n/WordPress volume seams are writable by their container users —
   `chown`-equivalents are executed ONLY inside project containers on
   project volumes (`docker compose exec`, project-name pinned),
   never on the host filesystem.

Exit 0/1; every step prints an `[OK]/[FAIL]` line and the script is
safe to re-run (all inserts are `ON CONFLICT DO NOTHING`, schema apply
is idempotent).

## 4. Smoke & integration verification: `run_staging_smoke_tests.py`

Two modes (exit 0 verified / 1 findings / 2 environment gap):

- **SYNTHETIC (default, no stack required):** drives the REAL canonical
  engines end-to-end in-process — content generation (Phase 7/8
  `ModelRouter` + `MockAiProvider`) → human review gate (D-050
  `ProposalLifecycle` accept) → WooCommerce staging draft (Phase 4
  `SyncEngine` over `MockWooAdapter` — RED-tier publish refused, draft
  staged) → Instagram/Telegram dispatch via the Phase 11
  `ContentToChannelPipeline` over real outbox publishers. Asserts:
  outbox state transitions (`queued → published`), idempotency
  (`duplicate_publish_blocked` on re-dispatch), unreviewed-proposal
  refusal, per-target crash isolation, **durable append-only
  compensation markers**, DLQ emission on Class-E freeze, D-124
  redaction of every receipt/payload, and OMS idempotency
  (`client_order_id` replay ⇒ `skipped_duplicate`, D-081).
- **STACK (opt-in `--stack`):** adds live-container probes over the
  private network — every service healthcheck green, canonical-DB
  reachable and post-bootstrap (13 schemas + seed counts), n8n
  healthz 200 **from inside the data network**, gateway surface on
  18080 only, WordPress → MySQL round-trip, MinIO S3 round-trip via
  `media_store` seams, and **isolation invariants** (no published DB
  port; internal data network cannot egress). Inter-container checks
  run through `docker compose exec` only — never through the host.

The suite in `local/tests/test_stage_d_smoke.py` executes both scripts
as subprocesses (the SYNTHETIC mode end-to-end) and pins the fail-closed
behaviors, so the harness cannot silently rot.

## 5. Recovery procedures

- **Partial stack failure:** `docker compose ... up -d --wait <svc>`
  re-converges; all durable planes are volumes, all engine state is
  event-sourced — restarts are safe by design.
- **SSOT corruption suspicion:** stop writes, snapshot
  `canonical_data`, re-run bootstrap (schema idempotent), verify via
  `decision_ledger_drill.py --consistency-only` and the D-125 fold
  equality check; restore from the latest verified archive only with
  owner approval (DR runbook `docs/runbooks/staging-disaster-recovery.md`).
- **Failed rollout:** `docker compose ... down` (NO `-v` by default —
  volumes survive; `-v` is a named, owner-approved destructive step),
  re-deploy, re-run §2.4.
- **Abort gates:** any bootstrap FAIL, any smoke exit ≥ 1, or any
  unexpected live-credential presence stops Stage D before Stage E.

## 6. Stage D exit criteria

1. Bootstrap exits 0 twice consecutively (idempotency proof).
2. Smoke harness exits 0 (synthetic mode) on the staging host AND the
   battery (`test_stage_d_smoke.py`) is green in CI-equivalent runs.
3. `validate_staging_health.py` manifest mode exit 0; `--live` drill
   exit 0 against the deployed stack.
4. Zero live-credential materialization events (D-045) — audited by
   the smoke harness's leak assertions.
5. Evidence rows appended to the plan's verification log by the
   operator (never pre-written).
