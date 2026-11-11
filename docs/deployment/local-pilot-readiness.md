# Local-pilot readiness record — fashion commerce (v1.0)

**Date:** 2026-11-09 · **Version:** 1.0 · **Commit tested:** `5c82312`

> **Historical evidence note (2026-11-11 remediation).** Every count in §2 is a
> measurement of `5c82312` (and the later §10 rerun), not of current `main`.
> Current remediation-baseline evidence at `73b27de` is **540 tests / 129
> suites** offline and **86 tests / 26 suites** live-PostgreSQL; the older
> 497/117 and 77/24 numbers are retained only as history.
> The commerce harness default is now **55431** (configurable through
> `COMMERCE_DB_PORT`); references to 55432 below describe the historical run and
> the Python canonical stack's port.
(`feat(commerce): read-only orphan-media dry run for the local provider`), identical
to `origin/main` at the time of testing (`git rev-list --left-right --count` = `0 0`,
clean tree apart from the untracked `.cloud-attachments/`). This record is an
assessment of **that commit only**; later commits need their own run — §10 is the
independent re-verification run at `015ea4a` (verdicts unchanged).

**What this is.** A bounded, developer-operated, loopback-only pilot of the
`commerce/` track with synthetic data and the mock payment/SMS paths. It consolidates
the four-step local-pilot review (catalog/gallery integrity, local media and the
read-only orphan report, mock payment → `PAID`, outbox + scheduler, admin access,
storefront visibility) into one decision.

**What this is not.** It is not a claim that the project or roadmap is complete, not
authorization for real customers, real money, live SMS, a reachable network, a
deployment or production activation. It does not close, open or reinterpret any
owner gate. A later record **claims** G0 acceptance on 2026-11-03, but no
owner-signed acceptance artifact is present and the authoritative status files
still record G0 OPEN. The **CURRENT G0 gate is therefore UNVERIFIED /
owner-gated pending explicit owner confirmation**; production activation remains
blocked behind D-139, and B1–B6 remain as recorded below. The 2026-10-24 “no
scheduler exists” statement is historical, not current status.

---

## 1. Verdicts (deliberately separate)

| # | Scope | Verdict |
| --- | --- | --- |
| 1 | Developer-operated, loopback-only, synthetic data, mock payment/SMS | **GO — with the recorded limitations and stop conditions** |
| 2 | Any pilot with real customers, a reachable network, live money or live SMS | **NO-GO** |
| 3 | Production activation | **NO-GO** |

A GO for (1) implies nothing about (2) or (3). It rests on the boundary that only the
operator uses the panel, all data is disposable, and no provider credential exists.

**Minimum next action before (2) could be reconsidered:** fix the soft-404 status
(§5.1), remove or validate external image URLs on product creation (§5.2), obtain
HTTPS/ingress and rate-limit review, provide backup + restore evidence, and clear the
owner gates in §6 — none of which this record authorizes.

---

## 2. Evidence reproduced on this commit (2026-11-09)

Every result below was produced on the tree at `5c82312` in this review; commands are
the actual ones run.

| Check | Command | Result |
| --- | --- | --- |
| Unit/integration + lint + typecheck + schema check | `npm run verify` | **rc=0 · 497 tests / 117 suites, 0 fail, 0 skipped**, `db:check` “Everything's fine” |
| Production build | `npm run build` | **rc=0**, `✓ Compiled successfully`; `/products/[slug]` and admin/API routes `ƒ` |
| Live PostgreSQL suite (disposable harness) | `COMMERCE_DATABASE_URL=…@127.0.0.1:55432/commerce_smoke npm run smoke:db` | **rc=0 · 77 tests / 24 suites, 0 fail** |
| Harness positively identified before use | `docker inspect commerce-db-harness-postgres` | project `commerce-db-harness`, image `postgres:16-alpine`, `127.0.0.1:55432->5432`, healthy; `commerce_smoke / commerce_smoke` |
| Readiness probe | `GET :13002/healthz` on a standalone `next start` bound to loopback | **200** `{"status":"ok"}`; connection refused after stop |
| Local media serving (isolated directory) | `GET /media/products/sha256/aa/<64 hex>.png`; missing key | **200 `image/png`**; missing key **404** |
| Admin access control | anonymous `POST /api/admin/media`; `GET /admin/products` | **401**; **307** → `/admin/login?next=%2Fadmin%2Fproducts` |
| Dispatch endpoint auth | anonymous `POST`; `GET` | **401**; **405** |
| Storefront visibility | published / DRAFT / unknown slug | published renders its own title; DRAFT and unknown render the not-found content and leak no product text — but all three return **HTTP 200** (§5.1) |
| Webhook signature boundary | unsigned `POST /api/webhooks/payment` | **401** `SIGNATURE_MISSING` |
| Mock payment → `PAID` | signed `PAID` callback, then replay | **200** `duplicate:false`; replay **200** `duplicate:true`; order `PAID`, reference recorded, history `PENDING->PAID(PAYMENT_CALLBACK)`, exactly one outbox row `PENDING` |
| Outbox + scheduler drain | `npm run scheduler:notifications -- --once` (loopback URL, local token) | **rc=0** `run ok (MOCK) claimed=1 sent=1 retried=0 failed=0`; row `SENT`, attempts 1, `MOCK-SMS-1`; second pass `claimed=0` |
| Process-interruption recovery | stop server, restart with the same environment | **200** healthz, storefront and `PAID`/`SENT` state persisted — no replay, no duplicate send |
| Orphan dry run, development store | `npm run media:orphans` (read-only) | 4 files / 91,493 B, 3 reference rows (3 distinct), 3 referenced files, **1 candidate 13,650 B** `products/sha256/54/548b7c4e…f66.jpg`, 0 unclassified; “performed no writes and no deletes” |
| Orphan dry run, isolated pilot store | `node scripts/media-orphans.mjs` against the disposable DB | 1 file / 70 B, 0 references, **1 candidate**, 0 unclassified |
| Development state untouched | row counts, outbox row, media file count, `:13001/healthz` | 5 products / 3 image rows / 1 order / 1 outbox row; outbox `PENDING attempts=0` dated 2026-11-07 14:45:58Z; 4 media files; healthz **200** |

The disposable harness was stopped with `npm run db:down` (volume retained, no `-v`);
the pilot server and its loopback port were stopped; the isolated media directory was
deleted. No development media file, order, outbox row or database row was written.

---

## 3. Reported in earlier steps but not re-executed here

- **STEP 1 browser walkthrough** of the storefront and admin gallery editor, including
  the end-to-end upload → product-creation flow and the exactly-one-primary invariant
  in the browser. Its code-level invariant is re-covered by `npm run verify`; the
  browser interaction was not repeated in STEP 4.
- **STEP 2 full scheduler operating matrix** (interval mode, SIGINT/SIGTERM clean stop,
  no-token refusal with zero requests, non-loopback refusal, wrong-token stop, 503
  backoff). STEP 4 exercised only `--once` drain and the empty second pass against the
  real endpoint; the remaining cases remain covered by
  `src/server/notifications/dispatch-scheduler.test.ts`.
- **STEP 3's focused orphan-tool test file** (26 tests) is included in the 497-test
  `verify` run, but was not run in isolation in STEP 4.
- **Live JPEG/WebP uploads, the browser uploader, and MinIO** — historically verified
  only partially (PNG live, JPEG/WebP hermetic; MinIO path not re-checked here).

---

## 4. Operating procedure for the loopback synthetic pilot

All commands are run from `commerce/`; every service is bound to `127.0.0.1`.

```bash
# 1. Disposable database (never the development instance on 55433)
export DOCKER_CONTEXT=colima
npm run db:up
export DATABASE_URL=postgresql://commerce_smoke:commerce_smoke_local_only@127.0.0.1:55432/commerce_smoke
npm run db:reset && npm run db:seed      # add synthetic catalog/order fixtures as needed

# 2. Isolated, disposable media directory (never .media-data)
mkdir -p /tmp/aobe-pilot-media

# 3. Application (build first: npm run build)
DATABASE_URL=… \
COMMERCE_PAYMENT_WEBHOOK_SECRET=<loopback test secret> \
NOTIFICATIONS_DISPATCH_TOKEN=<loopback test token> \
MEDIA_PROVIDER=local MEDIA_LOCAL_DIR=/tmp/aobe-pilot-media MEDIA_LOCAL_UPLOAD_ENABLED=true \
  npx next start -p 13002

# 4. Health and scheduler supervision (separate process / cron)
curl -fsS http://127.0.0.1:13002/healthz
NOTIFICATIONS_DISPATCH_URL=http://127.0.0.1:13002/api/internal/notifications/dispatch \
NOTIFICATIONS_DISPATCH_TOKEN=<same token> \
  npm run scheduler:notifications -- --once      # cron form; omit --once for the interval loop

# 5. Read-only media audit
DATABASE_URL=… MEDIA_PROVIDER=local MEDIA_LOCAL_DIR=/tmp/aobe-pilot-media \
  npm run media:orphans

# 6. Shutdown (data stays disposable; keep the development stack out of it)
npm run db:down                                  # never `down -v` on the development stack
```

**Rules that make the boundary real.** `DATABASE_URL` must point at the disposable
`55432` harness; the web tier, scheduler and audit tool each refuse a non-loopback
target. Use only synthetic customers/orders and mock providers (`SMS_LIVE_ENABLED`
unset, no ZarinPal/Kavenegar keys present). Test secrets are loopback literals and
must never be reused or committed. Logs contain counts, status codes and mode only —
no tokens, no URLs with userinfo. The scheduler's tick is the only thing that drains
the queue; not running it is safe and leaves rows `PENDING`.

**Recovery.** The database is a durable container volume and the outbox is the source
of truth: after a web/scheduler kill, restart the process and re-run the scheduler —
a settled row is not resent and a claimed-but-killed batch is retried by the normal
claim window. A corrupt or unwanted pilot state is recovered by `db:reset` (or
removing the harness volume) and reseeding, because the data is disposable. There is
**no backup/restore rehearsal** for this pilot and none is claimed; development data
must not be treated as recoverable by these steps.

---

## 5. Known observations, classified

### 5.1 Soft-404 HTTP status on DRAFT and unknown PDPs — **documented limitation for (1); blocker for (2)/(3)**

`GET /products/<draft-or-unknown>` renders the correct not-found page and leaks no
product content, but answers **HTTP 200**; the identical page at an unknown
top-level route answers 404. Most likely cause: `src/app/(storefront)/loading.tsx`
creates a streaming boundary, so the response can be committed before `notFound()` in
the page runs (not proven by removing the boundary). Not repaired here (outside
STEP 4's scope; the content rule is correct).
It matters to crawlers, caches and uptime monitoring, so it must be fixed before any
reachable/real-customer pilot. For the loopback synthetic pilot it has no effect.

### 5.2 Create-form external media URLs vs gallery-editor restriction — **documented limitation for (1); blocker for (2)/(3)**

The create payload accepts any non-empty `storagePath`/`publicUrl` pair, so an
operator could hotlink a third-party image, while the gallery editor only offers
uploaded objects. In a developer-only, synthetic pilot this is an operator footgun,
not a data-integrity defect; for a merchant-facing pilot it would permit tracking
pixels and broken external sources. Not repaired.

### 5.3 Retained orphan media — **deferred non-pilot item (policy, working as intended)**

The unreferenced object (`54/548b…`, 13,650 B in development; 70 B in the isolated
pilot store) remains untouched. Retention is the documented policy (§`commerce/README.md`
“Orphan media”); no deletion path exists. Not a pilot blocker; any future cleanup
needs the recorded backup, quiesced-writer, fresh-reference-check and owner-approval
safeguards.

### 5.4 Untouched PENDING development outbox row — **deferred non-pilot item**

The development row dated 2026-11-07 14:45:58Z is still `PENDING attempts=0`. It is a
development artifact and evidence that STEP 2/3/4 did not drain the development
queue; the pilot never uses that database. No action.

---

## 6. Owner-gated and unproven (not pilot blockers, but production blockers)

| Requirement | Current status (authoritative docs) | Why it blocks (2)/(3) |
| --- | --- | --- |
| **D-045** live credentials (ZarinPal merchant id + callback URL, Kavenegar key/sender, dispatch token, webhook secret) | Open; none exists, none was requested | Real money/SMS cannot be exercised; only the mock path is proven |
| **D-168** sealed-template re-attestation | Open; affects the canonical worker/OTP only, not the app path | Canonical notification templates cannot enter the sealed registry |
| **D-139** activation + C-1/C-2 manifest/probe wiring | Open | No staging/production authorization or deployed probe |
| **G-5 production media provider / C-8 digest pinning** | Production provider OPEN and unselected; local flag closed; image digest not pinned | No approved production media backend or immutable image |
| **B5 deployed scheduler** | Local runner exists and is verified; deployed scheduling is part of B3 | A deployed queue would wait indefinitely without an owner-chosen supervisor |
| **MON-001** observability, alerting, rollback drill | Open | No log shipping, no alert on failed dispatches or healthz 503 |
| HTTPS/ingress, rate limiting, real-customer privacy review | Not demonstrated | A reachable pilot changes the threat model |
| Backup/restore of pilot or production data | Not demonstrated (disposable data only) | No evidence a real loss is recoverable |
| Live ZarinPal round-trip, live Kavenegar round-trip | Never run without credentials | Provider behavior, template registration and sender lines unverified |

Shipping (decision 11), the AI provider (row 9) and G-6 remain outside this scope and
unchanged.

---

## 7. PASS / BLOCKED / FAIL checklist

| Item | Verdict |
| --- | --- |
| Catalog + gallery integrity (one primary, ordering, no partial writes) | **PASS** (497-test verify; browser recap not rerun — §3) |
| Local media write/read/refuse paths | **PASS** (isolated serve 200/missing 404; upload route guarded) |
| Read-only orphan report, fail-closed, no writes | **PASS** (dev + isolated runs; 26 focused tests inside verify) |
| Mock payment signature → `PAID`, idempotent replay, audit row, outbox in same flow | **PASS** |
| Outbox claim/settle, mock send, exactly-once second pass | **PASS** |
| Scheduler `--once` drain against the real endpoint | **PASS** (interval/SIGTERM matrix not rerun — §3) |
| Admin access control and dispatch auth | **PASS** (401/307/405) |
| Storefront publication rule | **PASS for content** / **BLOCKED for HTTP semantics** (§5.1) |
| Process-interruption recovery | **PASS** (restart preserves state; no duplicate send) |
| Backup/restore evidence | **BLOCKED** (not attempted; disposable data) |
| Live money / live SMS / real-customer traffic | **BLOCKED** (D-045) |
| Deployment, HTTPS, observability, rollback drill | **BLOCKED** (D-139, MON-001) |
| Any check that failed | **None** |

---

## 8. Rollback / stop conditions

Stop the pilot and do not widen its scope if any of the following occurs:

- any service is reachable beyond `127.0.0.1`, or a target other than the disposable
  harness is configured;
- any real customer data, real phone number, real payment or live SMS credential
  appears in the environment;
- a dispatch is sent twice, an outbox row is stuck `PENDING` past the pilot's review,
  or `/healthz` reports non-200 while data is being entered;
- a DRAFT/ARCHIVED product's content becomes visible on the storefront;
- the media store or database is mutated by the audit tool, or the orphan policy is
  bypassed by a manual delete;
- any secret appears in a log, a commit or the browser.

Rollback for the local pilot is `db:reset`/volume removal and redeploying the previous
build; there is no production state to roll back because nothing is deployed.

---

## 9. References

`PROJECT_RULES.md` §2.1/§3 · `docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md` Phase 5/G0
record and §6.3 B5 record · `docs/decisions/D-172-fashion-ecommerce-roadmap.md` ·
`docs/deployment/phase-6-cutover-checklist.md` · `commerce/README.md` (live harness,
local media, orphan policy) · `TODO.md` G0/B1–B6 · `DECISIONS.md` D-045/D-139/MON-001.

---

## 10. Re-verification run — 2026-11-09 at `015ea4a` (append-only; §1–§7 unchanged)

**Why.** §1–§7 are an assessment of `5c82312` only. This section records a second,
independent bounded smoke pass of the same procedure (§4) on the current head.

**Repo state at start.** `main` = `origin/main` = `015ea4a`
(`docs(deployment): record local-pilot readiness verdicts for 5c82312`);
`git rev-list --left-right --count` = `0 0`; working tree clean apart from the untracked
`.cloud-attachments/`. No code differs from the tree §1–§7 assessed.

**Development stack observed, never written.** `commerce-dev-web` (`next dev`, source
mounted, `127.0.0.1:13001`) and `commerce-dev-postgres` (`127.0.0.1:55433`) both
healthy; `GET /healthz` → **200** `{"status":"ok"}` before **and** after the run.
Baseline read before: **5** products, **3** `product_images` rows, **1** order, **1**
`notification_outbox` row `PENDING attempts=0` dated `2026-11-07 14:45:58.816601+00`;
media store **4** files (3 referenced + the retained `54/548b…` candidate). Read after
the run: **identical** on all five counts, outbox row still `PENDING attempts=0` at the
same timestamp, media tree byte-identical (see “no writes” below).

**One deliberate deviation from §4, stated rather than hidden.** The pilot ran from
`git archive HEAD commerce` unpacked under `/tmp` (with a hard-linked `node_modules`),
not in place: the development stack mounts `commerce/` and serves from the same
`.next`, so an in-place `next build` would have destroyed the running dev server's
output. The tree is byte-identical to `015ea4a`, so the behaviour exercised is the
commit's behaviour.

| # | Check | Command / target | Result |
| --- | --- | --- | --- |
| 1 | Disposable harness | `npm run db:up` → `127.0.0.1:55432` `postgres:16-alpine` (16.15) | healthy; `db:reset` + `db:seed` → 3 categories / 3 products / 15 variants / 0 images |
| 2 | Pilot build | `next build` on the `git archive` tree | **rc=0**; `/checkout`, `/api/*`, `/healthz` all dynamic `ƒ` |
| 3 | Pilot readiness probe | `GET 127.0.0.1:13002/healthz` | **200** `{"status":"ok"}` |
| 4 | End-to-end checkout (synthetic customer) | `POST /checkout` → server action `placeOrderAction`; synthetic name, `09120000000`, synthetic address, `1111111111`; one line `DMN-PLS-BLK-M` ×1; `POST_PISHTAZ` | **order `501d521a-b370-4622-b1b1-622f05e4e9cf`**, `PENDING`, totals `890,000 + 45,000 = 935,000`, payment `UNAVAILABLE` / `ZARINPAL_NOT_CONFIGURED`, no payment ref written, history `→ PENDING (STOREFRONT)` |
| 5 | Signed mock payment callback | `POST /api/webhooks/payment`, HMAC-SHA256 over the raw body in `x-commerce-signature: sha256=…` | **200** `PAID`, `duplicate:false`; order `PAID`, `payment_ref_id` recorded, history `PENDING→PAID (PAYMENT_CALLBACK)` |
| 6 | Callback replay (idempotency) | identical signed body delivered again | **200** `PAID`, `duplicate:true` — nothing written |
| 7 | Outbox after `PAID` | `commerce.notification_outbox` | exactly **1** row `order.confirmed / SMS / PENDING attempts=0` |
| 8 | Single dispatch pass | `NOTIFICATIONS_DISPATCH_URL=…:13002… npm run scheduler:notifications -- --once` | **rc=0** `run ok (MOCK) claimed=1 sent=1 retried=0 failed=0 skipped=0`; row `SENT`, attempts 1, `MOCK-SMS-1` |
| 9 | Exactly-once second pass | same `--once` again | `claimed=0 sent=0 retried=0 failed=0` |
| 10 | Dispatch auth boundary | `POST` with a wrong bearer token | **401** `UNAUTHORIZED` |
| 11 | Webhook signature boundary | same body, no signature header | **401** `SIGNATURE_MISSING` |
| 12 | Orphan dry run, development store | `DATABASE_URL=…:55433/commerce_local MEDIA_LOCAL_DIR=./.media-data npm run media:orphans` | 4 files / 89.3 KiB, 3 reference rows (3 distinct), 3 referenced on disk, 0 missing, **1 candidate 13.3 KiB** `54/548b7c4e…f66.jpg`, 0 unclassified; “performed no writes and no deletes” |
| 13 | No writes to the dev media store | `stat` + `shasum -a 256` over `.media-data` before/after | **diff empty** — bytes, mtime and digests identical |
| 14 | Orphan dry run, pilot store | `DATABASE_URL=…:55432/commerce_smoke MEDIA_LOCAL_DIR=/tmp/aobe-pilot-media` | 0 files / 0 references / 0 candidates / 0 unclassified; the tool itself notes an empty tree “is not a cleanup signal” |
| 15 | Teardown | kill pilot; `npm run db:down` (no `-v`); delete the isolated media dir | `13002` refused, `55432` refused, harness volume retained, no `db:reset` against `55433` |

**No production flag, live SMS or live payment credential was used.** The pilot's
environment was seven exports and nothing else: `DATABASE_URL` → the disposable `55432`
harness; `COMMERCE_PAYMENT_WEBHOOK_SECRET` and `NOTIFICATIONS_DISPATCH_TOKEN` → loopback
test literals minted for this run (never committed, deleted with the temporary tree);
`MEDIA_PROVIDER=local`; `MEDIA_LOCAL_DIR=/tmp/aobe-pilot-media`;
`MEDIA_LOCAL_UPLOAD_ENABLED=true`; `SMS_LIVE_ENABLED=false`. No `ZARINPAL_*`, no
`KAVENEGAR_*` and no `PAYMENT_MODE` was present (count = 0 in that source), and no
secret, token or URL with userinfo appeared in either log (grep count = 0). Behaviour
corroborates the environment: the checkout's gateway answer was
`ZARINPAL_NOT_CONFIGURED` and the dispatch report's mode was `MOCK`. `next start` sets
`NODE_ENV=production`, which also disables the mock gateway adapter by construction
(`gateway-runtime.ts`), so “mock” in this pass is the **mock webhook + mock SMS path**,
exactly as §4 implies — the order was never given a faked payment status.

**Non-failure note.** `next start` printed its standing warning that it “does not work
with `output: 'standalone'`”. The server started, probed and served every check above;
the warning concerns the container entrypoint contract (`.next/standalone/server.js`),
not this pilot. Recorded so it is not later discovered as a surprise.

**Verdicts.** Unchanged from §1: developer-operated, loopback-only, synthetic, mock
payment/SMS → **GO with the recorded limitations and stop conditions**; real customers /
reachable network / live money / live SMS → **NO-GO**; production activation → **NO-GO**
(D-139). No owner gate was closed, opened or reinterpreted, and **no check in this pass
failed**; the development baseline was neither altered nor read-modified.
