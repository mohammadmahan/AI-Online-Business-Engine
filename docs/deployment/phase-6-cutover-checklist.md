# Phase 6 cutover checklist — payment, SMS notification, container readiness

**Track:** fashion e-commerce (D-172), roadmap §6.1–§6.3.
**Status:** the **build/artifact half is GO** — every clause tagged `[AUTO]` below
was executed and passed on 2026-10-24. The **activation half is NO-GO**, blocked
only on owner acts (credentials D-045, deployment D-139, sealed-template ruling
D-168, image pinning G-5/C-8). Nothing in this document authorizes a deployment,
a credential, a registry push, a database migration outside the disposable
loopback harness, or an owner decision.

**Why this file exists.** Roadmap §6.3 ends with “production cutover checklist”
and `TODO.md` G4 carries it as open work. The earlier draft of this checklist
lived *outside* the working tree (`/tmp/aobe_phase6_step5_cutover_checklist.md`)
and was lost when the host restarted; it was **reconstructed from repository
evidence** — each clause below cites the artifact or command that proves it —
rather than from memory. Promoting it into `docs/deployment/` was previously
described as “reserved for the owner”; it is recorded here as a tracked edit
made on direct owner instruction for Phase 6 Step 5, and it changes no gate.

---

## 1. Deliverable inventory

| § | Deliverable | Artifact(s) | State |
| --- | --- | --- | --- |
| §6.1 | ZarinPal adapter behind the existing `PaymentGateway` seam | `commerce/src/server/payments/zarinpal.ts`, `authority-store.ts`, `gateway-runtime.ts` | built, offline + real-PG verified |
| §6.1 | Durable authorization (`authority → amount`) on the order row | `commerce/drizzle/0003_sturdy_machine_man.sql` (`payment_provider`, `payment_authority`, `payment_amount` + 3 constraints) | built, real-PG verified |
| §6.1 | Browser return with server-side verification | `commerce/src/app/api/payments/zarinpal/callback/route.ts` → `src/server/services/payment-callback.ts` | built, verified (doubles + real PG) |
| §6.1 | Idempotent order updating, one pipeline for webhook + browser return | `applyPaymentCallback` (shared), `order_status_history` UNIQUE `(order_id, to_status)` | built, concurrency-proven |
| §6.2 | Order-confirmation outbox written in the `PAID` transaction | `commerce/drizzle/0004_order_notification_outbox.sql`, `src/server/repository.ts` (`enqueueNotification`, `claimNotificationBatch`) | built, real-PG verified |
| §6.2 | Dispatcher (claim → render → send → settle), bounded retries | `src/server/notifications/dispatcher.ts` | built, unit + real-PG verified |
| §6.2 | SMS port + mock/live adapters (Kavenegar) | `src/server/notifications/sms.ts` | built; live path exercised only through an injected transport |
| §6.2 | Operator trigger endpoint | `src/app/api/internal/notifications/dispatch/route.ts` → `dispatch-endpoint.ts` | built, auth matrix + in-container verified |
| §6.3 | Hardened container image | `commerce/Dockerfile`, `commerce/.dockerignore` | built, digest-pinned base, verified |
| §6.3 | Local run posture + env contract | `commerce/docker-compose.local.yml`, `commerce/.env.example` | verified (`compose config`, `up --wait`) |
| §6.3 | Readiness probe | `commerce/src/app/healthz/route.ts` → `src/server/services/health.ts` → `probeCanonicalDatabase()` | verified host-side **and** in-image |

**Not in Phase 6 scope, unchanged:** shipping provider (decision 11, still
mock-only), media storage (G-5), AI provider (row 9), and every engine-track
gate (D-139 activation is its own decision).

---

## 2. Environment contract at cutover

Every variable is read at **call time**, so an unset value is a refusal and not a
startup crash — the container starts, reports unhealthy or refuses the specific
request, and never guesses.

| Variable | Consumer | Unset / empty behaviour | Supplied by |
| --- | --- | --- | --- |
| `DATABASE_URL` | `db-context.ts` (all data paths, `/healthz`) | `/healthz` → `503 db_unconfigured`; data paths → `DB_NOT_CONFIGURED`, order untouched | owner (deployment secret) |
| `COMMERCE_PAYMENT_WEBHOOK_SECRET` | `/api/webhooks/payment` | `503 WEBHOOK_NOT_CONFIGURED`, body unread | owner |
| `ZARINPAL_MERCHANT_ID` | `zarinpal.ts` (request step) | every payment `UNAVAILABLE`, order stays `PENDING` | owner — **missing (D-045)** |
| `ZARINPAL_CALLBACK_URL` | `zarinpal.ts` (request step) | same as above | owner — **missing (D-045)** |
| `ZARINPAL_SANDBOX` | `zarinpal.ts` | defaults to sandbox (`true`); only the literal `false` reaches production | owner |
| `SMS_LIVE_ENABLED` | `notifications/sms.ts` | anything but `true` ⇒ `MockSmsChannel` (records, sends nothing) | owner |
| `KAVENEGAR_API_KEY` | `notifications/sms.ts` | live requested without it ⇒ `503 SMS_LIVE_MODE_MISSING_CREDENTIAL`, **no claim** | owner — **missing (D-045)** |
| `KAVENEGAR_SENDER` | `notifications/sms.ts` | as above | owner — **missing (D-045)** |
| `NOTIFICATIONS_DISPATCH_TOKEN` | `dispatch-endpoint.ts` | `503 DISPATCH_NOT_CONFIGURED`, nothing claimed | owner — **must be minted at cutover** |

`commerce/docker-compose.local.yml` maps **all** of the above with `${VAR:-}`
defaults so an unexported variable reaches the container as an empty string
(`docker compose config` shows `""` for each). The staging/production envelopes
(`local/infra/.env.staging`, `compose.staging.yml`, `compose.prod.yml`, Dokploy
`REQUIRED_SECRETS`) still carry **none** of the payment/SMS keys — wiring them is
an owner act, not part of this checklist's execution.

---

## 3. Cutover clauses

Tags: **`[AUTO]`** executed and passed in this assessment (command in the
evidence column) · **`[OWNER]`** requires an owner act and was **not** performed ·
**`[BLOCKED]`** cannot run until an owner gate opens.

### A. Artifact

| # | Clause | Tag | Evidence |
| --- | --- | --- | --- |
| P6-C1 | The image builds from a **digest-pinned** base, not a floating tag | `[AUTO]` | `docker build -f commerce/Dockerfile -t commerce:local commerce` rc=0; build log resolves `node:20-alpine@sha256:fb4cd12c85ee…` |
| P6-C2 | The runner stage carries only `.next`, `node_modules`, `package.json`, `server.js`, and runs as uid 1000 | `[AUTO]` | runner stage in `Dockerfile`; in-container `id` → `uid=1000(node)` |
| P6-C3 | All Phase 6 routes are **compiled into the artifact** (not only dev/`next start`) | `[AUTO]` | build route table: `ƒ /healthz`, `ƒ /api/webhooks/payment`, `ƒ /api/payments/zarinpal/callback`, `ƒ /api/internal/notifications/dispatch` |
| P6-C4 | The **stale-tag hazard** is closed: never `up` an existing tag and assume it is current | `[AUTO]` | first `compose up` reused a pre-§6.2 `aobe-commerce-local:verify` and the dispatch route answered **404**; after `compose build` the same URL answers **503 DISPATCH_NOT_CONFIGURED** |
| P6-C5 | No environment file, build log or credential reaches any layer | `[AUTO]` | `.dockerignore` excludes `.env*` (keeping `.env.example`) + runner payload inspection |
| P6-C6 | The deployed reference is pinned to the built digest in the deployment manifest | `[BLOCKED]` | Dokploy/Stage-D manifests still carry `@sha256:aaaa…` placeholders (G-5, C-8) — **owner** |

### B. Database

| # | Clause | Tag | Evidence |
| --- | --- | --- | --- |
| P6-C7 | The committed migrations apply cleanly and completely (0000–0004) | `[AUTO]` | `npm run smoke:db` resets + migrates on the disposable harness → **68 tests, 0 fail**; `npm run db:check` → “Everything's fine” (journal: 5 rows) |
| P6-C8 | `notification_outbox` and its guarantees exist in the migrated database | `[AUTO]` | live suite: columns/enums/indexes/CHECKs/FK present; duplicate enqueue → `23505`; CHECK refusals → `23514` |
| P6-C9 | A migration is **additive** and has no down-script; rollback is a restore, not a revert | `[AUTO]` (recorded) | `drizzle/*.sql` contain no `down` statements — cutover rollback = restore the pre-cutover snapshot (see `docs/deployment/staging-volume-backup-policy.md`) |
| P6-C10 | Migrating the staging/production database | `[BLOCKED]` | D-139 — owner act; nothing outside the disposable loopback harness was migrated |


### C. Payment (§6.1)

| # | Clause | Tag | Evidence |
| --- | --- | --- | --- |
| P6-C11 | Unconfigured credentials refuse instead of approximating a payment | `[AUTO]` | `zarinpal.test.ts` / `payment-callback.test.ts`; empty merchant id ⇒ `UNAVAILABLE`, order stays `PENDING` |
| P6-C12 | The browser return verifies server-side and refuses in a fixed order | `[AUTO]` | no `Authority` → 400; `Status≠OK` → 200 `PAYMENT_NOT_COMPLETED` (no verify, no write); unknown authority → 404; declined → 402; unreadable adapter/store → 503; illegal `PAID` → 409 (no audit row) |
| P6-C13 | The amount comes from the **persisted** row (Toman→Rial once), never the query string | `[AUTO]` | `payment-callback.test.ts`; real-PG case verifies from `orders.payment_amount` |
| P6-C14 | Concurrent/replayed deliveries converge to exactly one `PAID` + one audit row | `[AUTO]` | real-PG: four concurrent signed deliveries → one `PAID`, one reference, one trail row; browser-return replay → `duplicate` |
| P6-C15 | Every payment answer is `no-store` | `[AUTO]` | asserted on all callback paths |
| P6-C16 | A real sandbox round-trip (request page → provider → return → `PAID`) | `[BLOCKED]` | no merchant id / callback URL exist (D-045); nothing was sent to ZarinPal |
| P6-C17 | `ZARINPAL_SANDBOX=false` (production host) only after C16 passes | `[BLOCKED]` | owner ruling, after C16 |

### D. Notification (§6.2)

| # | Clause | Tag | Evidence |
| --- | --- | --- | --- |
| P6-C18 | The announcement is enqueued in the **same transaction** that writes `PAID`; `CANCELLED` announces nothing | `[AUTO]` | real-PG: two concurrent `PAID` writes ⇒ one outbox row + one trail row |
| P6-C19 | Exactly-once is structural: UNIQUE `(order_id, kind, channel)` + `ON CONFLICT DO NOTHING` + `PENDING→SENDING` claim under `FOR UPDATE SKIP LOCKED` | `[AUTO]` | live suite: duplicate enqueue `23505`; racing claimants take **disjoint** batches; a `SENT` row is never reclaimed |
| P6-C20 | A crashed claimant's stale lease is reclaimable; a fresh lease is respected | `[AUTO]` | live suite (fresh vs stale lease) |
| P6-C21 | The queue holds **no PII and no body** (recipient + Persian body resolved at dispatch) | `[AUTO]` | live suite asserts no phone number and no body in the row |
| P6-C22 | Retries are bounded; exhaustion is terminal with a provider code | `[AUTO]` | live suite: transient × 3 → `FAILED` + `provider_unavailable`; no further claim |
| P6-C23 | The trigger endpoint refuses safely: unset token ⇒ 503 **claiming nothing**; missing/wrong bearer ⇒ 401; `GET` ⇒ 405; body reports counts only | `[AUTO]` | unit auth matrix + **in-image** probes (§6 below) |
| P6-C24 | Live mode without credentials is a **hard refusal**, never a silent mock, and claims nothing | `[AUTO]` | in-image: `SMS_LIVE_ENABLED=true`, no key ⇒ `503 SMS_LIVE_MODE_MISSING_CREDENTIAL`; the queued row stayed `PENDING` / attempts 0 |
| P6-C25 | The mock path really drains and never double-sends | `[AUTO]` | in-image: first call `claimed 1 / sent 1`, row `SENT` with a provider message id; second call `claimed 0` |
| P6-C26 | Something **calls** the endpoint (cron/scheduler/operator) | `[BLOCKED]` | no scheduler exists by design; until one exists queued rows simply wait — safe, but no buyer SMS is delivered |
| P6-C27 | Credentialed Kavenegar round-trip (registered template + sender line) | `[BLOCKED]` | D-045: no key, no sender, no registration; the live adapter has only ever run over an injected transport |
| P6-C28 | Canonical-worker template admission (`checkout.otp.v1`, `order.confirmed.v1`, `order.tracking.v1`) | `[BLOCKED]` | D-168 seal — **does not affect the app path**, which renders its own bodies; it blocks the canonical worker and the unbuilt OTP step |

### E. Readiness & security posture

| # | Clause | Tag | Evidence |
| --- | --- | --- | --- |
| P6-C29 | `/healthz` is fail-closed and truthful | `[AUTO]` | in-image: configured + reachable → **200** `{"status":"ok"}`; no `DATABASE_URL` → **503** `db_unconfigured`; closed port → **503** `db_unreachable`; every answer `cache-control: no-store` |
| P6-C30 | The container survives its hardened posture | `[AUTO]` | `read_only`, `cap_drop:[ALL]`, `no-new-privileges`, tmpfs only for `/tmp` + `/app/.next/cache`, 512 MiB / 1.0 CPU, `USER node`, not privileged; in-container rootfs write → “Read-only file system” |
| P6-C31 | No credential text is ever logged | `[AUTO]` | container log holds only the Next.js banner + `✓ Ready`; driver messages are swallowed by `health.ts` |
| P6-C32 | The platform's own probe points at `/healthz` for this service | `[BLOCKED]` | no staging/production/Dokploy manifest declares a commerce service at all (C-1/C-2) — **owner** |
| P6-C33 | Log aggregation, alerting and a rollback drill for this service | `[BLOCKED]` | MON-001 stays open; no commerce-specific alerting exists |


---

## 4. Readiness assessment

**Verdict — two answers, deliberately not merged:**

1. **BUILD / ARTIFACT: GO.** Every `[AUTO]` clause passed on 2026-10-24 against a
   clean committed tree: **24 `[AUTO]` clauses, 0 failures**. The image builds
   from the pinned digest, carries every Phase 6 route, applies and passes the
   full migration set, refuses every unconfigured path, drains the queue exactly
   once, and reports readiness truthfully both on the host and inside the
   container.
2. **PRODUCTION ACTIVATION: NO-GO.** Nine clauses are `[BLOCKED]`, and none of
   them is a code gap — each is an owner act this work neither performed nor
   implied (D-045 / D-139 / D-168 / G-5-C-8 / C-1-C-2 / MON-001).

**Remaining owner-gated production blockers, in the order they must be cleared:**

| # | Blocker | Owner act required | Blocks |
| --- | --- | --- | --- |
| B1 | **D-045 credentials** — ZarinPal merchant id + public callback URL; Kavenegar API key + sender line; a generated `NOTIFICATIONS_DISPATCH_TOKEN`; `COMMERCE_PAYMENT_WEBHOOK_SECRET` if the signed webhook is kept | issue + place in the secret store (never in git) | P6-C16, C17, C23, C27 |
| B2 | **D-168 sealed-template re-attestation** (phase-17/18 chain digest successor) | owner ruling per the package recorded in `TODO.md` G3-O | P6-C28 (canonical worker + OTP only) |
| B3 | **Deployment authorization (D-139) + manifest wiring (C-1/C-2)** — declare the commerce service in staging/production, point its probe at `/healthz`, map the §2 env contract | owner + deploy | P6-C10, C32 |
| B4 | **Image pinning (G-5 / C-8)** — replace the `@sha256:aaaa…` placeholders with the built digest | owner/registry grant | P6-C6 |
| B5 | **A scheduler** for `POST /api/internal/notifications/dispatch` (cron, external monitor, or an operator rota) | operational choice | P6-C26 |
| B6 | **Observability** — log shipping, alerting on `failed` dispatches and on `/healthz` 503, rollback drill | MON-001 | P6-C33 |

**Explicit non-goals (recorded so absence is not mistaken for a gap):** OTP at
checkout (§3.4 storefront step is unbuilt), shipping-carrier integration
(decision 11 unselected), media storage (G-5), AI provider (row 9). None is a
Phase 6 cutover clause.

---

## 5. Operator cutover sequence (to be executed only after B1–B4 clear)

Each step is the same command this assessment ran, in the order a real cutover
needs it. Nothing below was executed against staging or production.

```bash
# 1. build from the pinned base (never reuse an existing tag — P6-C4)
docker build -f commerce/Dockerfile -t commerce:<git-sha> commerce

# 2. record + pin the digest into the deployment manifest (P6-C6 / G-5)
docker image inspect commerce:<git-sha> --format '{{index .RepoDigests 0}}'

# 3. migrate the target database through the project's own toolchain (P6-C7/C10)
DATABASE_URL=… npm run db:migrate          # 0000–0004, additive only

# 4. export the §2 contract into the service environment (never into the image)
#    DATABASE_URL, COMMERCE_PAYMENT_WEBHOOK_SECRET, ZARINPAL_MERCHANT_ID,
#    ZARINPAL_CALLBACK_URL, ZARINPAL_SANDBOX=false, SMS_LIVE_ENABLED=true,
#    KAVENEGAR_API_KEY, KAVENEGAR_SENDER, NOTIFICATIONS_DISPATCH_TOKEN

# 5. start and wait for health (the probe is the gate, not the exit code)
docker compose -f commerce/docker-compose.local.yml up -d --wait --wait-timeout 180

# 6. verify readiness and the refusal matrix (P6-C29)
curl -sS -w '%{http_code}\n' https://<host>/healthz          # expect 200 {"status":"ok"}

# 7. verify the operator trigger refuses an anonymous caller (P6-C23)
curl -sS -w '%{http_code}\n' -X POST https://<host>/api/internal/notifications/dispatch   # expect 401

# 8. drain the queue with the bearer token and read the counts only (P6-C25)
curl -sS -H "Authorization: Bearer $NOTIFICATIONS_DISPATCH_TOKEN" \
     -X POST https://<host>/api/internal/notifications/dispatch

# rollback: restore the pre-cutover snapshot (P6-C9 — migrations have no down),
# redeploy the previous pinned digest, and leave queued rows untouched (they wait).
```

### Post-cutover checks (first hour)

- `/healthz` 200 from **two** independent vantage points (host + platform probe).
- One real payment in `ZARINPAL_SANDBOX=true`, then the production host only
  after the round-trip is signed off (P6-C17).
- One real order: `PAID` ⇒ exactly one `commerce.notification_outbox` row ⇒
  exactly one provider message id; a second dispatch call reports `claimed 0`.
- A deliberately wrong bearer token answers `401` and moves no row.


---

## 6. Evidence of this assessment (2026-10-24)

Tree under test: `3111677` plus the two Step-5 edits (this document, and the
`docker-compose.local.yml` SMS/dispatch env mapping). All commands were run on
that tree; nothing was pushed to a registry and nothing was sent to any provider.

| Check | Command | Result |
| --- | --- | --- |
| Unit + integration suites | `npm run verify` (typecheck → lint → test → db:check) | rc=0 · **298 tests / 74 suites, 0 fail** · lint 0 problems · typecheck exit 0 · db.check “Everything's fine” |
| Live database (disposable loopback harness) | `npm run smoke:db` | **68 tests / 0 fail** (schema reset + migrations 0000–0004) |
| Image build (direct) | `docker build -f commerce/Dockerfile -t commerce:local commerce` | rc=0 · `commerce:local` 292 MB · `sha256:71cecbc07197…` |
| Image build (compose path) | `docker compose -f commerce/docker-compose.local.yml build` | rc=0 · `aobe-commerce-local:verify` 292 MB · `sha256:920a115e8acd…` |
| Env contract renders fail-closed | `docker compose -f docker-compose.local.yml config` | every payment/SMS key renders `""` (only `ZARINPAL_SANDBOX` defaults to `"true"`) |
| Stack up under the hardened posture | `… up -d --wait --wait-timeout 180` | `aobe-commerce-local Healthy`, `127.0.0.1:13000->3000/tcp` |
| Structural constraints | `docker inspect` | `ReadonlyRootfs=true`, `CapDrop=[ALL]`, `no-new-privileges:true`, tmpfs `/tmp` + `/app/.next/cache`, 512 MiB, 1.0 CPU, `User=node`, `Privileged=false` |
| Readiness (host) | `GET :13000/healthz` | **200** `{"status":"ok"}`, `cache-control: no-store` |
| Readiness (in-image, negative ×2) | one-off containers | no `DATABASE_URL` → **503** `db_unconfigured`; closed port → **503** `db_unreachable` |
| Dispatch, token unset | `POST :13000/api/internal/notifications/dispatch` | **503** `DISPATCH_NOT_CONFIGURED` |
| Dispatch, `GET` | `GET` on the same path | **405** |
| Dispatch, token set | no bearer → **401**; wrong bearer → **401**; correct bearer → **200** `{"ok":true,"mode":"MOCK",…}` |
| Live SMS without credentials | `SMS_LIVE_ENABLED=true`, no key, correct bearer | **503** `SMS_LIVE_MODE_MISSING_CREDENTIAL`; the queued row stayed `PENDING`, attempts `0`, `sent_at` null |
| Real drain, exactly once | correct bearer, mock channel | first call `{"claimed":1,"sent":1}`; row `SENT`, attempts `1`, provider message id set; second call `{"claimed":0}` |
| Stale-image detection | `compose up` before `compose build` | dispatch route answered **404** (image predated §6.2) — recorded as P6-C4, not hidden |

**Environment caveat measured while producing this table (not a defect).**
`npm test` compiles the live suites into `.test-build/` and runs them whenever
`COMMERCE_DATABASE_URL` is exported in the calling shell. With the harness
**up**, they execute; with the variable set but the harness **down**, the run
fails loudly (`ECONNREFUSED 127.0.0.1:55432`, 68 cancelled) — which is the
correct fail-closed behaviour for a configured but unreachable target. The
canonical offline gate is therefore `env -u COMMERCE_DATABASE_URL npm run
verify` → **298 tests / 74 suites, 0 fail**, with the four live suites reporting
`# SKIP <named reason>` rather than silently passing.

**Housekeeping:** both one-off probe containers were removed, `compose down`
removed the container and its network, and the harness database was stopped with
`npm run db:down` (the pre-existing harness container is not left running).

## 7. Change control

- This document is **append-only** in the repository's sense: a later assessment
  adds a dated section rather than rewriting the clauses above.
- It authorizes **nothing**. Building an image locally, probing `/healthz` and
  draining a disposable harness queue are verification acts; deploying,
  provisioning, migrating a shared database, minting or placing a credential,
  pushing an image, and admitting a sealed template each remain owner decisions
  (D-045 / D-139 / D-168 / G-5 / C-8).
- Related records: roadmap §6.1, §6.2 (build records) and §6.3 (this step),
  `TODO.md` G2/G3/G4, `commerce/README.md` (Phase 6 section),
  `docs/deployment/control-plane-container-spec.md` (the ratified container
  pattern this image follows), `docs/deployment/staging-volume-backup-policy.md`
  (the rollback input for P6-C9).

