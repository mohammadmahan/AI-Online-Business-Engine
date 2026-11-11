# Full-System Audit — 2026-11-11

**Status:** audit complete, remediation not started
**Repository:** `AI-Online-Business-Engine`
**Baseline commit:** `1b2d0f9`
**Audit scope:** `commerce/`, `control-plane/`, Python `local/`, static `dashboard/`, documentation, local deployment tooling, and the end-to-end seams between them.
**Safety:** no production or staging deployment, no real payment or SMS traffic, no destructive migration, no credential disclosure, and no application-logic changes.

---

## 1. Executive summary

The repository is substantially implemented and its principal offline test surfaces are healthy. No critical (P0) defect was found in the audited code paths.

The strongest verified results are:

- `commerce`: **540 tests / 129 suites, 0 failures**, plus typecheck, lint, schema check, a production build, and **86 live-PostgreSQL tests / 26 suites, 0 failures**.
- `control-plane`: **119 tests / 21 suites, 0 failures**, typecheck, lint, production build, **52/52 contrast pairings**, **30/30 live-verdict pairs**, and **0 data leaks across 7 routes**.
- `local`: **2,874 tests with an isolated database**, with **4 environment-related failures** and **103 skips**; schema application and seeding passed.
- Storefront catalog, product detail, checkout validation, RTL layout, and mobile overflow were exercised in the local browser.
- Payment and notification write endpoints fail closed when their secrets are absent.

The most important unresolved issues are not failing unit tests:

1. **Release-state documentation contradicts itself.** `docs/README.md` and the pilot readiness report say G0 was accepted on 2026-11-03, while `MASTER_PLAN.md` still says **“G0 remains OPEN.”**
2. **The static dashboard is stale and presents old operational evidence** (`Phase 12`, commit `f17a9a0`, 142 products, 498 tests) next to current repository state.
3. **Unknown product slugs return HTTP 200**, so a product-page soft 404 is observable.
4. **Local database tooling collides on port 55432** between the commerce smoke harness and the Python local stack’s canonical database.
5. **The forwarded `127.0.0.1` commerce dev origin blocks Next.js development resources and prevents client hydration**; `localhost` hydrates correctly. This is a local-development usability defect, not a production-build failure.
6. **The control plane has no authentication layer** and must be confined to loopback by deployment policy; the application itself does not enforce that boundary.
7. **External integrations remain unverified**: live ZarinPal, SMS, AI, Instagram, Telegram, Notion, shipping, and Dokploy runtime checks require owner credentials, authorization, or registry access.

**Overall judgement:** the codebase is in a credible offline-verified state, but the release record and the owner-facing dashboard are not trustworthy enough to support a launch decision until documentation and observability truth are corrected.

---

## 2. Baseline and audit environment

| Item | Observation |
|---|---|
| Branch / HEAD | `main` / `1b2d0f9` |
| Working tree at start | Only `.cloud-attachments/` untracked |
| Application source changes | None |
| Commerce dev server | Existing Colima `commerce-dev-web`, forwarded at `127.0.0.1:13001` |
| Commerce database | Existing dev PostgreSQL at `127.0.0.1:55433` |
| Audit database | Disposable PostgreSQL container `aobe-audit-pg` at `127.0.0.1:55434` |
| Control-plane audit server | Temporary process on port `13003` (bound to all interfaces by `next start`), stopped after audit |
| Static dashboard audit server | Temporary process on `127.0.0.1:18081`, stopped after audit |
| Browser storage writes | Disposable cart entries only; no order was submitted |
| Standing data/media | Preserved; counts unchanged after audit |
| Secrets | Not printed, copied, or committed |

The documented local port `55432` was already occupied by the Colima commerce harness, so the isolated audit database used `55434`. The standing forwarded ports were not reset or mutated.

---

## 3. Phase, status, and documentation reconciliation

### 3.1 G0 status is contradictory

- `docs/README.md` says the fashion Phase 6 build is complete and **G0 was ACCEPTED on 2026-11-03**.
- `docs/deployment/local-pilot-readiness.md` repeats the 2026-11-03 acceptance.
- `MASTER_PLAN.md` contains both an append-only 2026-11-02 amendment and later lines stating **“G0 remains OPEN”** and that Phase 6 remains owner-gated.
- `TODO.md` and the roadmap still carry owner-gated gates that are not reconciled with the “accepted” wording.

This is not a cosmetic wording issue. It changes whether the next remediation batch is allowed to treat production activation gates as satisfied. The conflict must be resolved by the owner or by a single authoritative status record before any release decision.

### 3.2 Verification evidence is stale

`docs/deployment/local-pilot-readiness.md` records **497 tests / 117 suites** and **77 live tests / 24 suites** at commits `5c82312` / `015ea4a`. Current measured results are **540 / 129** and **86 / 26** at `1b2d0f9`. The numbers are not wrong for the historical commit, but the document does not make that distinction prominent enough for a reader looking for current evidence.

`commerce/README.md` also contains older **77/77** wording alongside the current Phase 6 state.

### 3.3 The static dashboard is not a current source of truth

`dashboard/state_summary.json` and the embedded state in `dashboard/index.html` still report:

- `version: 0.12.0-alpha`
- `current_phase: Phase 12 — Order Management System (OMS) Closed`
- `last_commit: f17a9a0`
- `total_products: 142`
- `sync_ladder_tests: 498 / 498`

The rendered page shows the same stale values. It is a static artifact, not a generated view of the current database or test run. It should not be used as launch evidence.

---

## 4. Inventory

| Area | Implementation | Persistence / external dependency | Verification surface | Result |
|---|---|---|---|---|
| `commerce/` | Next.js 16 storefront + admin + APIs + Drizzle schema | PostgreSQL; local filesystem media; outbox | 59 test files; 8 migrations | Strong offline and live-DB coverage |
| `control-plane/` | Next.js 16 RTL operations console | Mock datasets; optional read-only telemetry probes | 21 test suites; 7 routes; build | Strong rendering/contract coverage; mostly mock data |
| `local/` | Python engine, ladder, services, deployment checks, n8n assets | PostgreSQL; Docker; external providers | 107 test modules | Broad coverage; 4 environment failures |
| `dashboard/` | Static HTML/CSS/JS status page | Static JSON | Browser render | Renders, but stale |
| `docs/` | Architecture, decisions, runbooks, deployment specs | None | Manual reconciliation | Material contradictions |
| `local/n8n/` | Two workflow JSON assets | n8n runtime | Inventory only | Present, not end-to-end exercised |

Current commerce data at the audited dev database:

- products: **5**
- variants: **17**
- images: **3**
- categories: **4**
- orders: **1** (1 paid)
- pending notification outbox rows: **1**
- media files: **4**

---

## 5. Subsystem results

### 5.1 Commerce

| Check | Command | Result |
|---|---|---|
| Unit/integration/typecheck/lint/schema | `npm run verify` | **PASS** — 540 tests / 129 suites, 0 fail; typecheck, lint, `db:check` passed |
| Live PostgreSQL suite | `COMMERCE_DATABASE_URL=… npm run smoke:db` | **PASS** — 86 tests / 26 suites, 0 fail |
| Production build | `npm run build` | **PASS** — compiled successfully; standalone output produced |
| Storefront catalog | browser `localhost:13001/catalog` | **PASS** — 4 published products rendered |
| Product detail | browser / curl | **PASS** for known published slug |
| Unknown product slug | `GET /products/no-such-product` | **FAIL** — HTTP **200** instead of 404 |
| Unknown top-level route | `GET /this-route-does-not-exist` | **PASS** — HTTP 404 |
| Anonymous admin page | `GET /admin/products` | **PASS** — 307 redirect to login |
| Anonymous admin API | `POST /api/admin/media` | **PASS** — HTTP 401 |
| Payment webhook without secret | `POST /api/webhooks/payment` | **PASS (fail closed)** — HTTP 503 |
| Notification dispatch without token | `POST /api/internal/notifications/dispatch` | **PASS (fail closed)** — HTTP 503; GET is 405 |
| Checkout form | browser with one cart line | **PASS** — form hydrated, RTL, 390 px no horizontal overflow; empty submit produced four Persian field errors |
| Mobile catalog | browser at 390×844 | **PASS** — no horizontal overflow |
| Cart persistence | `localStorage` round trip in browser | **PASS** — one line hydrated; no server write |
| Concurrent same-key checkout | live-DB suite | **PASS** — one order for two concurrent submissions |
| Payload mismatch replay | live-DB suite | **PASS** — refused without stock consumption or order disclosure |
| Security headers | `GET /admin/login` | **GAP** — no CSP, X-Frame-Options/frame-ancestors, Referrer-Policy, or Permissions-Policy observed; only cache control |

Notes:

- The checkout flow was exercised only to client validation. A real browser order was not submitted, because that would mutate standing development data.
- The payment and notification endpoints are intentionally disabled until owner-selected provider secrets exist. HTTP 503 is the intended fail-closed state, not a successful integration.
- No evidence was found that a merchant can enter an arbitrary external image URL: the product image editor describes server-issued media references, while the uploader also exposes a manual storage-path input. This boundary was not fully penetration-tested.

### 5.2 Control plane

| Check | Result |
|---|---|
| Typecheck / lint | **PASS** |
| Tests | **PASS** — 119 tests / 21 suites, 0 fail |
| Contrast gate | **PASS** — 52/52 pairings, 0 violations |
| Live-verdict seam | **PASS** — 30/30 |
| View isolation | **PASS** — 7 routes, 0 leaks; technical proofs preserved |
| Production build | **PASS** |
| Dashboard render | **PASS** — RTL, Persian labels, explicit MOCK provenance |
| Technical view | **PASS** — toggle works; RTL preserved |
| Mobile dashboard | **PASS** — 390 px, no horizontal overflow |
| `/api/health` | **PASS** — HTTP 200, `{"status":"ok"}` |
| Authentication | **GAP** — no application auth; route access is controlled only by network binding |

The control-plane dashboard, orders, inventory, and HITL pages instantiate mock sources directly. Only `automations` resolves `CP_TELEMETRY_MODE` and can use the live probe source. That is visibly labelled as MOCK/`دادهٔ نمونه`, so it is not misrepresentation, but it means “LIVE mode” is not a whole-console mode.

### 5.3 Local Python engine and tooling

| Check | Result |
|---|---|
| Schema apply on isolated database | **PASS** |
| Seed on isolated database | **PASS** |
| Full suite without database | **2,842 tests, 4 failures, 2 errors, 113 skipped** |
| Full suite with isolated database | **2,874 tests, 4 failures, 103 skipped** |

The four database-run failures were classified as environment constraints, not confirmed product defects:

1. Dokploy runtime test could not pull the pinned WordPress/MinIO images.
2. Health-sidecar test asserts documented `PGPORT=55432`; the audit override pointed at 55434.
3. `test_ladder` hardcodes port 55432 and hit the harness credential mismatch.
4. Stage-D smoke expected `engine_staging` but inherited the audit `LOCAL_PGUSER=engine_local`.

The absence of a clean standard-port run is a tooling problem: the commerce harness and the local canonical stack both expect `55432`. A developer cannot run both at once without an override, and some tests hardcode the port rather than using the configured value.

### 5.4 Static dashboard

The page renders correctly and is RTL-safe, but its content is a stale snapshot. It reports 142 products, 498 tests, commit `f17a9a0`, and Phase 12 as current. This is an observability defect, not a rendering defect.

---

## 6. End-to-end matrix

| Flow | Evidence | Verdict |
|---|---|---|
| Commerce catalog → published PDP | Browser + HTTP | **PASS** |
| PDP → unknown slug | Browser + HTTP | **FAIL** — soft 404 (200) |
| Cart hydration → checkout → client validation | Browser at `localhost` | **PASS** |
| Checkout → order transaction | Live-DB suite | **PASS** offline/live-DB |
| Checkout retry → same key | Live-DB suite | **PASS** |
| Checkout same key → different payload | Live-DB suite | **PASS** |
| Payment webhook → order transition | Unit/integration tests only | **BLOCKED** — no secret/provider |
| Paid order → SMS/notification outbox | Tests and outbox schema | **PASS offline**; live SMS **BLOCKED** |
| Admin login page | Browser | **PASS** |
| Admin authenticated CRUD | Not run | **BLOCKED** — local credentials not exercised |
| Control-plane overview | Browser | **PASS as MOCK** |
| Control-plane live telemetry | `CP_TELEMETRY_MODE=LIVE` seam tests | **PASS seam**; dashboard stays mock |
| Static dashboard | Browser | **STALE** |
| Notification dispatch endpoint | HTTP | **PASS fail-closed** (503 without token) |
| Local n8n workflows | Inventory | **NOT EXERCISED** |

---

## 7. Findings

Severity scale: **Critical** = launch-blocking data/security failure; **High** = release decision or operational truth affected; **Medium** = material correctness, security, or operability risk; **Low** = maintainability or coverage gap.

### AUD-01 — High — G0 release status contradicts itself

**Evidence:** `docs/README.md:15` and `docs/deployment/local-pilot-readiness.md:19` state G0 was accepted on 2026-11-03. `MASTER_PLAN.md:1213`, `:1454`, and `:1765` say G0 remains open.
**Impact:** The owner cannot determine from the repository whether production activation gates are satisfied. This is a governance and release-safety defect.
**Reproduction:** Read the three cited locations at HEAD `1b2d0f9`.
**Classification:** Documentation truth / release process, not runtime code.

### AUD-02 — High — Static dashboard presents stale launch evidence

**Evidence:** `dashboard/state_summary.json` and `dashboard/index.html` show Phase 12, commit `f17a9a0`, 142 products, and 498 passing tests; current HEAD is `1b2d0f9` and the audited dev database has 5 products.
**Impact:** An owner or operator can mistake an old snapshot for current health and test evidence.
**Reproduction:** Serve `dashboard/` and read the rendered status values; compare with `git rev-parse --short HEAD`.
**Classification:** Observability / documentation truth.

### AUD-03 — Medium — Unknown product slugs return HTTP 200

**Evidence:** `GET http://localhost:13001/products/no-such-product` returns `200`; a known published product also returns `200`. An unknown top-level route returns `404`.
**Impact:** Search engines and clients treat missing products as valid pages; monitoring cannot distinguish a missing product from a rendered one. The page should return `notFound()`/404.
**Reproduction:** `curl -o /dev/null -w '%{http_code}' http://localhost:13001/products/no-such-product`.
**Classification:** Confirmed runtime defect; not remediated in this audit.

### AUD-04 — Medium — Local tooling collides on port 55432

**Evidence:** The Colima commerce smoke harness occupies `127.0.0.1:55432`, while the local canonical stack and several tests assume `55432` with `engine_local` credentials. Local tests then fail authentication. The audit had to use `55434` and environment overrides.
**Impact:** The documented local verification path is not runnable without stopping a standing stack or editing configuration; two tests hardcode the port rather than consuming `PGPORT`.
**Reproduction:** Start the existing harness on 55432, then run the local suite with documented defaults; observe `password authentication failed for user "engine_local"`.
**Classification:** Local tooling/configuration defect.

### AUD-05 — Medium — Forwarded `127.0.0.1` dev origin prevents client hydration

**Evidence:** At `http://127.0.0.1:13001/checkout` with a valid cart, the page remains at “در حال خواندن سبد خرید…” and the console reports blocked Next.js dev resources (`/_next/hmr`, `/__nextjs_font/...`) with `allowedDevOrigins` absent. At `http://localhost:13001/checkout` the cart hydrates and the form appears.
**Impact:** The documented forwarded dev URL is partially unusable for interactive storefront testing; a reviewer may incorrectly conclude the checkout is broken. Production builds are not affected by Next.js dev-origin protection.
**Reproduction:** Open the same cart URL on both hostnames and compare the hydrated form; inspect `commerce/next.config.mjs` (no `allowedDevOrigins`).
**Classification:** Development-environment defect / documentation mismatch, not a production runtime failure.

### AUD-06 — Medium — Payment and notification activation is incomplete

**Evidence:** `POST /api/webhooks/payment` returns 503 because `COMMERCE_PAYMENT_WEBHOOK_SECRET` is absent; `POST /api/internal/notifications/dispatch` returns 503 without its dispatch token. Provider selection remains owner-gated.
**Impact:** The Phase 6 “payment/notification” path is implemented and fail-closed, but no live provider has been exercised end to end. Treating the 503 as a passing integration would be false.
**Reproduction:** Issue the two POSTs without secrets, then inspect the provider configuration and integration tests.
**Classification:** Activation blocker, not a code failure.

### AUD-07 — Medium — Control plane has no authentication boundary

**Evidence:** There is no auth middleware/session guard in `control-plane/src`; the audit server was reachable on `*:13003` because Next.js bound all interfaces. Deployment documentation says local verification may publish on `127.0.0.1` only.
**Impact:** If the container is reachable beyond loopback, operational views, probe metadata, and future write controls are exposed. Network binding is currently the only control.
**Reproduction:** Start the control plane with its normal command and connect from a non-loopback interface; no login is requested.
**Classification:** Security hardening / deployment requirement gap.

### AUD-08 — Medium — No browser security header policy

**Evidence:** `GET /admin/login` returned `Cache-Control` but no CSP, frame-ancestors/X-Frame-Options, Referrer-Policy, or Permissions-Policy. `commerce/next.config.mjs` defines no headers.
**Impact:** The admin surface lacks defense-in-depth against clickjacking and script injection. HSTS is not applicable to plain-HTTP local testing but should be set at the TLS terminator in production.
**Reproduction:** Inspect response headers for `/admin/login`.
**Classification:** Security hardening gap.

### AUD-09 — Medium — Control-plane “LIVE” coverage is partial

**Evidence:** `dashboard`, `orders`, `inventory`, and `hitl-queue` call mock source factories directly. Only `automations` calls `getTelemetrySource()` and honors `CP_TELEMETRY_MODE=LIVE`. The UI labels mock data explicitly.
**Impact:** A `LIVE` environment does not mean the whole console reflects live state. This is honest in the UI but easy to misread in operations.
**Reproduction:** Inspect the source imports listed above and render the dashboard under `CP_TELEMETRY_MODE=LIVE`.
**Classification:** Integration limitation / documentation clarity.

### AUD-10 — Low — Current test counts in docs are stale

**Evidence:** Pilot readiness records 497/117 and 77/24; current results are 540/129 and 86/26. Commerce README retains 77/77 wording.
**Impact:** Reviewers cannot tell which counts belong to HEAD.
**Reproduction:** Compare the current `verify`/`smoke:db` output with the documented tables.
**Classification:** Documentation gap.

### AUD-11 — Low — Control plane has no component README

**Evidence:** `control-plane/README.md` is absent; the only operating detail is in `docs/deployment/control-plane-container-spec.md`.
**Impact:** New maintainers lack a local start/test/build guide.
**Classification:** Documentation gap.

### AUD-12 — Low — Idempotency concurrency has a narrow residual gap

**Evidence:** Live tests cover concurrent same-key submissions and sequential same-key/different-payload mismatch, but not two concurrent submissions with the **same key and different payloads**.
**Impact:** The advisory-lock design is credible and the separate paths pass, but the exact adversarial race is not directly asserted.
**Classification:** Test-coverage gap; do not claim it as a defect.

### AUD-13 — Low — External integrations remain unverified

No live ZarinPal, Kavenegar/SMS, AI provider, Instagram, Telegram, Notion, shipping, or real payment test was possible without owner credentials and explicit authorization. These are blocked, not passed.

### AUD-14 — Low — Dokploy runtime check is blocked by image pulls

The local Dokploy runtime test could not pull the pinned WordPress/MinIO images. This prevented the containerized pilot check from completing and must not be reported as a product failure.

---

## 8. Blocked and limited checks

| Check | Why it could not be completed |
|---|---|
| Admin authenticated CRUD | Admin credentials are local secrets; only login page and anonymous redirect were verified |
| Live payment callback / webhook | No webhook secret or provider credentials |
| Live SMS and notification delivery | Dispatch token and provider are absent |
| Live AI, Instagram, Telegram, Notion, shipping | Owner credentials/authorization absent |
| Dokploy runtime | Pinned images unavailable to the audit environment |
| Standard local suite on 55432 | Port occupied by the commerce harness |
| Full visual regression | Only layout/overflow and interaction snapshots were inspected; no screenshot-based visual diff |
| Concurrent same-key, different-payload checkout | No direct test; see AUD-12 |

---

## 9. Recommended remediation batches

These are proposals only. No remediation was performed.

### Batch 1 — Restore release truth (highest priority)

1. Choose one authoritative G0 status and update `MASTER_PLAN.md`, `docs/README.md`, `TODO.md`, and `docs/deployment/local-pilot-readiness.md` consistently.
2. Mark historical test counts with their commit, or replace them with current results and a date.
3. Regenerate or retire `dashboard/state_summary.json`; add a visible “static snapshot, commit X” warning until it is generated from current data.

### Batch 2 — Correct runtime behavior

1. Return a real 404 for unknown or unpublished product slugs.
2. Add reproducible local-stack port allocation so the commerce harness and Python canonical database do not both claim 55432.
3. Replace hardcoded `55432`/credential assumptions in local tests with the configured environment, then rerun the standard documented command.
4. Add `allowedDevOrigins` for the documented forwarded host, or document `localhost` as the only interactive dev origin.

### Batch 3 — Harden boundaries

1. Enforce loopback binding for the control plane, or add authentication before any non-local exposure.
2. Add CSP, frame-ancestors/X-Frame-Options, Referrer-Policy, and Permissions-Policy to the commerce admin surface; terminate HSTS at TLS.
3. Keep payment and notification endpoints fail-closed; add a deliberate activation checklist rather than weakening the 503 path.

### Batch 4 — Integration verification

1. Exercise one sandbox payment provider and one SMS provider with owner-supplied secrets.
2. Run a signed webhook replay, duplicate delivery, mismatch, and notification-outbox drain against a disposable database.
3. Verify admin CRUD, media upload, and order status transitions with authenticated browser sessions.

### Batch 5 — Test depth

1. Add concurrent same-key/different-payload coverage.
2. Add a standard-port local integration job that starts only the stack it needs.
3. Add a regression test for soft 404 status codes and a check that the static dashboard cannot claim a newer commit than HEAD.

---

## 10. Before/after health and preservation

| Metric | Before audit | After audit |
|---|---|---|
| Git HEAD | `1b2d0f9` | `1b2d0f9` |
| Working tree | `.cloud-attachments/` untracked | `.cloud-attachments/` untracked; audit report added separately |
| Commerce health | 200 | 200 |
| Commerce products / variants / images | 5 / 17 / 3 | 5 / 17 / 3 |
| Commerce orders / paid / pending outbox | 1 / 1 / 1 | 1 / 1 / 1 |
| Commerce media files | 4 | 4 |
| Audit database | `aobe-audit-pg` on 55434 | stopped and removed |
| Audit control-plane server | 13003 | stopped |
| Static dashboard server | 18081 | stopped |

The commerce container was briefly stopped for the production build and restarted; its health and data counts were rechecked afterward and are unchanged. No standing database row was created or deleted by the audit.

---

## 11. Commands and evidence

Representative commands (run from the repository root unless noted):

```bash
# Baseline
git rev-parse --short HEAD
git status --short

# Commerce
cd commerce
npm run verify
COMMERCE_DATABASE_URL=... npm run smoke:db
npm run build

# Control plane
cd ../control-plane
npm run typecheck
npm run lint
npm test
npm run check:contrast
npm run check:live-verdicts
npm run build

# Local engine (isolated DB, with PG* and LOCAL_* overrides)
python3 -m unittest discover -s local/tests -t .
python3 local/scripts/apply_schema.py
python3 local/scripts/seed_registry.py

# Runtime boundaries
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:13001/products/no-such-product
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:13001/api/webhooks/payment
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:13001/api/internal/notifications/dispatch
curl -sS -D - -o /dev/null http://127.0.0.1:13001/admin/login

# Data preservation
psql ... -c "select count(*) from commerce.products;"
find commerce -type f \( -iname '*.jpg' -o -iname '*.png' -o -iname '*.webp' \) -not -path '*/node_modules/*' -not -path '*/.next/*' | wc -l
```

Full local logs retained during the audit: `/tmp/audit-commerce-verify.log`, `/tmp/audit-commerce-smoke.log`, `/tmp/audit-commerce-build.log`, `/tmp/audit-cp-*.log`, `/tmp/audit-local-tests.log`, `/tmp/audit-local-tests-db.log`.

---

## 12. Final repository state

At the time of writing, the only pre-existing untracked path is `.cloud-attachments/`. This report is the only new tracked artifact from the audit. No application source, migration, environment file, credential, or standing media file was changed.
