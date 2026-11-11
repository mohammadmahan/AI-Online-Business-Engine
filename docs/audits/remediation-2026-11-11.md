# Remediation report — 2026-11-11 audit

Scope: every finding `AUD-01`–`AUD-14` plus the audit's documented coverage
gaps. This is a remediation record, **not** a launch approval. G0 remains
**UNVERIFIED / owner-gated**; no staging or production deployment, real payment,
SMS, social post, AI call, customer-data transfer or destructive migration was
performed.

Baseline commit: `73b27de` (audit checkpoint). Remediation commits: `08cdc88`,
`49e6a5e`, `e6b2c7d`. All pushed fast-forward to `origin/main`.

## Finding status

| ID | Initial finding | Change and evidence | Regression result | State |
|---|---|---|---|---|
| AUD-01 | G0 release status contradicted itself. | Reconciled `MASTER_PLAN.md`, `TODO.md`, `docs/README.md`, `docs/deployment/local-pilot-readiness.md`. A past acceptance **claim** is retained as history; no owner-signed artifact exists, so the current gate is explicitly unverified/owner-gated. | Documentation review; no contradictory current G0 claim remains. | **FIXED** |
| AUD-02 | Dashboard presented stale data as current. | `dashboard/` is marked `HISTORICAL_STATIC` with source, environment, commit, observation time and warning. `dashboard/check-snapshot.mjs` enforces the metadata. | `node dashboard/check-snapshot.mjs` → PASSED. | **FIXED** |
| AUD-03 | Unknown product slug returned HTTP 200. | `generateMetadata` calls `notFound()`; streaming `loading.tsx` boundaries removed from the storefront product route. Added `commerce/scripts/check-storefront-status.mjs`. | Known published product → **200**; unknown slug → **404** via `npm run check:http-status`. | **FIXED** |
| AUD-04 | Commerce harness and Python stack collided on 55432. | Commerce harness defaults to configurable `COMMERCE_DB_PORT=55431`; docs/scripts/compose agree. Stage-D identity is explicitly isolated; `test_ladder` and health-sidecar tests consume configured PostgreSQL values. | Compose config confirms `127.0.0.1:55431`; override `55435` accepted. Full Python suite ran on disposable `55434`. | **FIXED** |
| AUD-05 | Forwarded `127.0.0.1` origin did not hydrate. | `allowedDevOrigins: ['127.0.0.1']` (narrow, no arbitrary origins). Dev server restarted. | Browser at `http://127.0.0.1:13001/checkout` rendered the form, cart no longer stuck loading, no blocked HMR/font console errors. | **FIXED** |
| AUD-06 | Payment/notification activation incomplete. | Fail-closed paths preserved. Added `docs/deployment/payment-notification-activation.md` with preconditions, required secret **names**, sandbox checks, stop conditions. No provider enabled, no fake credentials. | Unsigned/invalid requests still refuse; no live provider round-trip attempted. | **BLOCKED** — owner credentials and explicit activation authorization (D-045/D-139) |
| AUD-07 | Control plane has no auth boundary. | Local `dev`/`start` bind `127.0.0.1`; container exposure remains restricted/documented. Actual listener verified. No authentication was invented. | `lsof` showed only `127.0.0.1:13003`; `/api/health` 200. | **BLOCKED** — non-local access still needs an owner-approved auth/authz design; local exposure is mitigated |
| AUD-08 | No browser security header policy. | Commerce sends CSP (`default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, and restrictive `Permissions-Policy`. Dev-only `unsafe-eval`; production excludes it. HSTS documented at the TLS terminator. | `curl -D` on `/admin/login` returned all headers; login page 200. | **FIXED** |
| AUD-09 | Control-plane LIVE coverage was easy to misread. | README states only `automations` honors `CP_TELEMETRY_MODE`; four pages are explicit MOCK. `check:provenance` guards the route contract and source-mode exposure. | `npm run check:provenance` → PASSED (4 mock, 1 live-capable). | **FIXED** (semantics; no fabricated adapters) |
| AUD-10 | Current test counts in docs were stale. | Current measured counts recorded; historical counts labelled historical. | 540/129 offline, 87/26 live, 119/21 control-plane, 2,877 Python. | **FIXED** |
| AUD-11 | Control plane had no component README. | Added `control-plane/README.md`: start, verification, provenance, loopback-only exposure, container caveat. | Commands executed successfully. | **FIXED** |
| AUD-12 | No concurrent same-key/different-payload test. | Added live race using `IDEM-D`: same key, quantity 1 vs 2. Asserts exactly one durable order, one stock movement, mismatch refusal. Corrected a separate notification assertion that assumed an `ok` count, which contradicts the documented same-status no-op contract; durable one-trail/one-outbox assertions remain. | Live suite **87/87 twice** (26 suites); offline **540/540** (129 suites); build exit 0. | **FIXED** |
| AUD-13 | External integrations unverified. | No live provider was activated. Existing simulated/sandbox tests ran; n8n JSON assets validated structurally, no credential literals/dangling connections. | n8n asset tests 3/3. ZarinPal/SMS/AI/Instagram/Telegram/Notion/shipping remain unverified. | **BLOCKED** — owner credentials, sandbox access and explicit side-effect authorization |
| AUD-14 | Dokploy runtime check blocked by pinned image pulls. | Rechecked with the exact production digests. All five were already cached locally, so the isolated `prodcheck` runtime was retried. The pull failure no longer reproduced; no digest was changed. | Runtime **VERIFIED**: 5/5 containers healthy, hardening and read-only checks passed, SSOT migration applied (13/13 schemas), re-apply idempotent, teardown `rc=0`. | **VERIFIED** |

## Coverage gap outside AUD numbering

| Gap | Result | State |
|---|---|---|
| Authenticated admin CRUD, media upload, order transition in an isolated browser setup | Exercised against a disposable PostgreSQL/media/app copy on `127.0.0.1:13002` with generated credentials. See the second-pass evidence below. | **VERIFIED** |
| Control-plane LIVE adapters beyond `automations` | Not added; current plan does not require them and no telemetry contract exists to fabricate. | **VERIFIED-NOT-A-DEFECT** |
| n8n assets | Both committed workflows parse, have unique nodes, valid connection targets and no obvious credential literals. Not executed against n8n. | **FIXED (contract only)** |

## Final verification evidence

Commands and totals (HEAD `e6b2c7d`):

- Python: `LOCAL_PGHOST=127.0.0.1 LOCAL_PGPORT=55434 LOCAL_PGDATABASE=business_engine_local LOCAL_PGUSER=engine_local LOCAL_PGPASSWORD=engine-local-only PYTHONPATH=. python3 -m unittest discover -s local/tests -t .`
  → **2,877 tests, 1 failure, 103 skipped**; only failure is the Dokploy MinIO pull above.
- Commerce offline: `npm test` → **540 tests, 129 suites, 0 failures**.
- Commerce live: `COMMERCE_DATABASE_URL=…55432/commerce_smoke npm run smoke:db` → **87 tests, 26 suites, 0 failures**, run twice.
- Commerce build: `npm run build` → **exit 0**.
- Typecheck/lint: `npm run typecheck`, `npm run lint` → **exit 0** (commerce and control-plane).
- Control plane: `npm test` → **119 tests, 21 suites, 0 failures**; contrast **52/52**; live verdicts **30/30**; build **exit 0**; provenance check PASSED.
- HTTP status: published product **200**, unknown product **404**.
- Browser: `http://127.0.0.1:13001/checkout` hydrated with the form; no blocked dev resources.
- Loopback: control-plane `npm start` on 13003 listened only on `127.0.0.1:13003`.
- Dashboard snapshot: PASSED (`HISTORICAL_STATIC`, observed `2026-09-16T21:30:00Z`).
- n8n assets: 3/3 tests PASSED.

Standing stack after remediation:

- `http://localhost:13001/healthz` → **200**.
- Products **5**, variants **17**, images **3**, categories **4**, orders **1**, paid **1**, pending outbox **1**, media files **4** — unchanged from baseline.
- `commerce-dev-web`, `commerce-dev-postgres`, `commerce-db-harness-postgres` and five staging containers running/healthy.
- Disposable `aobe-remediation-pg` removed; no `aobe-remediation-*` container remains.
- Git clean except preserved untracked `.cloud-attachments/`; `origin/main...main` = `0 0`.

## New defects or corrections

- The notification race test asserted that exactly one concurrent `transitionOrder`
  returns `ok`. The storage layer intentionally returns success for a same-status
  no-op, so that count is scheduling-dependent. The test now asserts at least one
  accepted writer and the durable invariants: exactly one order, one history row,
  one outbox row. This is a test-contract correction, not a relaxed product
  invariant.
- No new product runtime defect was found in the surviving failures.

## Owner decisions still required

1. Sign (or reject) the G0 gate with a durable owner artifact. Do not infer
   approval from this report.
2. Approve an authentication/authorization design before any non-loopback
   control-plane exposure.
3. Supply and authorize payment, SMS and other provider credentials in the
   target secret store, then run the activation checklist in sandbox mode.
4. ~~Provide registry access or an approved preloaded image set for Dokploy
   runtime verification.~~ **Resolved:** exact digests were already cached and
   the isolated runtime passed.
5. ~~Authorize a separate isolated admin-browser rehearsal.~~ **Completed:** the
   synthetic browser rehearsal ran without touching the standing stack.

## Second verification pass — 2026-11-11

This pass used only disposable resources. The standing app on `13001`, its
database on `55433`, the harness on `55432`, and the five staging containers
were left running and untouched.

### Disposable commerce browser environment

- Separate PostgreSQL container `aobe-browser-pg` on `127.0.0.1:55434`.
- Separate app copy at `commerce/.browser-rehearsal/app` with independent
  `.next`, media root `commerce/.browser-rehearsal/media`, origin
  `127.0.0.1:13002`, generated `rehearsal` credentials and synthetic seed data.
- Final rehearsal counts: categories **4**, products **4**, variants **17**,
  images **0**, orders **1** (`PAID`), retained media objects **1**.
- Standing counts before and after this pass: categories **4**, products **5**,
  variants **17**, images **3**, orders **1**, paid **1**, pending outbox **1**,
  media files **4**; `13001/healthz` **200**.

### Browser-flow result: VERIFIED

- Unauthenticated `/admin` → **307** to login; unauthenticated
  `POST /api/admin/media` → **401** with `ADMIN_UNAUTHORIZED`.
- Real browser sign-in with generated credentials → `/admin`.
- Category creation succeeded; product creation succeeded with two variants
  after a deliberate missing-field rejection.
- Inventory stock/price edits persisted exactly: stock **7**, override
  **700000**, second variant unchanged.
- Product edit/archive persisted: status became **ARCHIVED**.
- Image upload succeeded after the CSP fix; public `/media/...` served **200**,
  `image/jpeg`, 96×96. Removing the association persisted `images=0` while the
  content-addressed file remained (**1** file), matching the documented
  retention policy.
- Order display and transition succeeded: `PENDING → PAID`, exactly one
  `order_status_history` row.
- Product deletion is not implemented; archive is the supported lifecycle
  operation. Category creation only is implemented by design.

### Responsive/RTL result: FAILED (new UI defect)

- `dir` and computed direction are **rtl**; navigation renders at 390px.
- At viewport **390px**, `documentElement.scrollWidth` is **667** and page-level
  overflow remains **true**. The table itself scrolls (`clientWidth 324`,
  `scrollWidth 768`), but it does not contain the page overflow.
- An attempted `overflow-x-clip` on the admin `<main>` did not fix it and was
  reverted. This remains **OPEN**; no claim of a passing mobile layout is made.

### n8n result: PARTIAL / VERIFIED

- Disposable `n8nio/n8n@sha256:b73045…` with a separate SQLite volume and
  disposable PostgreSQL, no published ports.
- Both committed workflows imported; credential import succeeded.
- `n8n execute --id=3f2c9b74-6a11-4d8e-9c2f-5b7a1e9d4a01 --rawOutput` against a
  synthetic `seed.size_family` row returned `status: success`, `finished: true`,
  and observed `size_families: 1`.
- The error-router workflow imported but was not manually executed: its only
  trigger is n8n's Error Trigger, which requires a failed parent execution. Its
  runtime remains **NOT VERIFIED**; the canonical classifier code is covered by
  its existing unit tests.

### Dokploy result: VERIFIED

- Exact pinned images present in the local cache: WordPress, MySQL,
  PostgreSQL, n8n and `quay.io/minio/minio`.
- `DOCKER_CONTEXT=colima python3 local/scripts/validate_dokploy_runtime.py --runtime`
  → isolated stack up, **5/5 healthy**, no-new-privileges/memory/read-only
  checks passed, SSOT schema 13/13 applied, idempotent re-apply passed, teardown
  `rc=0`. No digest was replaced.

### Control-plane boundary result: VERIFIED locally / non-local still BLOCKED

- Host: `npm start` on `13003` listened only on `127.0.0.1:13003`; `/api/health`
  returned 200.
- Container: `docker run -p 127.0.0.1:13003:3000 control-plane:verify` served
  `/api/health` 200; `docker port` reported `3000/tcp -> 127.0.0.1:13003`.
- Inside the container the server binds `0.0.0.0:3000` (`/proc/net/tcp`), so
  isolation depends on the loopback publication. No committed compose file
  enforces that publication and no authentication exists. Non-local exposure
  remains **BLOCKED / owner-gated**; no public auth design was assumed.

### New defects / fixes

- **CSP upload failure — FIXED.** Image upload failed because the picker fetches
  its compressed `data:` preview while CSP `connect-src` omitted `data:`. Added
  `data:` and extended `check:http-status` to assert it. The same check now
  passes against the isolated server.
- **Mobile page overflow — OPEN.** Recorded above; not hidden or marked as a
  pass.

## Third verification pass — mobile overflow and fresh suites (2026-11-11)

**Mobile admin overflow: FIXED and VERIFIED.** Reproduced on the populated inventory table at 390px: `html.clientWidth=390`, `html.scrollWidth=635`; table wrapper `clientWidth=324`, `scrollWidth=871`; table left `-514`. The cause was RTL negative overflow from the wide table escaping its `overflow-x:auto` wrapper (not a lack of table scrolling). Added `contain: paint` to the shared table scroll wrapper; the table remains intentionally scrollable. Measured after: 320px document `320` (wrapper `254/871`), 390px document `390` (wrapper `324/871`), 1440px document `1440` (wrapper `1054/1054`); RTL retained at all widths. Added `npm run check:admin-mobile` (Playwright-core + system Chrome) which authenticates, checks inventory at 320/390/1440, and fails on page-level overflow.

**Fresh suites:** Python against disposable PostgreSQL, exact cached digest, `DOCKER_CONTEXT=colima`: **2,877 run, 0 failed, 102 skipped, OK**. Commerce typecheck **PASS**, lint **PASS**, offline **540/540**, live DB smoke **87/87**, production build **PASS**, HTTP/CSP **PASS**. Control-plane/shared code was not changed; no control-plane suite rerun was required.

**n8n error-router runtime: NOT VERIFIED.** Imported the committed router and a synthetic parent workflow with a thrown Code-node error and no external endpoints. `n8n execute` did not reach execution because the container reported `n8n Task Broker's port 5679 is already in use`; no Error Trigger evidence was produced. Import or classifier unit tests are not runtime evidence.

Standing health/data were checked before start and after cleanup. Disposable DB/app/n8n resources were removed; the standing baseline remains 4 categories, 5 products, 17 variants, 3 images, 1 order (1 paid), 1 pending outbox, 4 media files, health 200.
## Third verification pass — mobile overflow and fresh suites (2026-11-11)

**Mobile admin overflow: FIXED and VERIFIED.** Reproduced on the populated inventory table at 390px: `html.clientWidth=390`, `html.scrollWidth=635`; table wrapper `clientWidth=324`, `scrollWidth=871`; table left `-514`. The cause was RTL negative overflow escaping the table's `overflow-x:auto` wrapper. Added `contain: paint` to the shared wrapper; the table remains intentionally scrollable. After: 320px document `320` (wrapper `254/871`), 390px document `390` (wrapper `324/871`), 1440px document `1440` (wrapper `1054/1054`), RTL retained. Added `npm run check:admin-mobile`, which authenticates and fails on page-level overflow.

**Fresh suites:** Python against disposable PostgreSQL with the exact cached digest, `DOCKER_CONTEXT=colima`: **2,877 run, 0 failed, 102 skipped, OK**. Commerce typecheck PASS, lint PASS, offline 540/540, live DB smoke 87/87, production build PASS, HTTP/CSP PASS. Control-plane/shared code was not changed.

**n8n error-router runtime: NOT VERIFIED.** Imported the committed router and a synthetic parent workflow with a thrown Code-node error and no external endpoints. `n8n execute` did not reach execution because the container reported `n8n Task Broker port 5679 is already in use`; no Error Trigger evidence was produced.

Disposable resources were removed. Standing baseline remains 4 categories, 5 products, 17 variants, 3 images, 1 order (1 paid), 1 pending outbox, 4 media files, health 200.
