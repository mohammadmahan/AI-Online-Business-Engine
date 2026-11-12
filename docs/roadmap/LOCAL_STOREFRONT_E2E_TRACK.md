# Local Storefront & E2E Verification Track (LSE)

- **Status:** COMPLETED — owner-directed local/offline verification track (2026-11-12)
- **Parent program:** D-172 fashion commerce; fashion Phase 6 build/artifact track
- **Parent gate:** G0 ACCEPTED / RESOLVED (D-173); B1–B6 local/offline preparation
- **Authority:** `PROJECT_RULES.md` §2, §2.1, §3, §23, §38 · `MASTER_PLAN.md`
  §12/§13 · `docs/roadmap/FASHION_ECOMMERCE_ROADMAP.md` Phase 3 and Phase 6
- **Decision:** D-174 (local/offline scope only; changes no production gate)
- **Implementation home:** `commerce/`
- **Verification base:** `main` at `e30d42d269b1fce074cc61c152e9008f182d3de4`

This document is the execution checklist for LSE. It is not a new product
phase and does not rewrite the fashion roadmap. It turns an existing,
partly one-off browser/pilot exercise into a repeatable local check of the
storefront that is already implemented.

---

## 1. Why this track exists

The prior proposal to "build a local storefront and E2E testing" was checked
against the repository rather than accepted as a premise.

**Verified:** the storefront is already implemented in `commerce/`:

- `/` — homepage, category circles, real-data rails;
- `/catalog` — client-side facets, search, price/availability filters;
- `/products/[slug]` — PDP gallery, colour × size matrix, size chart, cart;
- `/checkout` — synthetic checkout, server-side totals/stock, mock/fail-closed
  payment;
- `/admin/**` — guarded merchant panel, including the order list.

**Verified gap:** there is no committed, repeatable browser E2E command. The
existing evidence is a mixture of:

- hermetic rule tests (`src/__tests__/funnel.test.ts`);
- opt-in live PostgreSQL integration suites (`src/__tests__/live-db/`);
- one-off browser/pilot records in
  `docs/deployment/local-pilot-readiness.md`, measured at older commits
  (`5c82312`, `015ea4a`), not at the current HEAD;
- narrow scripts (`check:http-status`, `check:admin-mobile`) that cover only
  status codes/one admin layout, not the customer journey.

There is also no `check:e2e` script. `playwright-core` is already a dependency
and `/Applications/Google Chrome.app` is available on this machine, so the
browser check can be added without a new framework or downloaded browser.

**Conclusion:** the next safe local objective is LSE — repeatable local
verification of the existing storefront, admin reconciliation, fail-closed
states, responsive/RTL behavior, and current evidence. It is not a request to
build a second storefront, adopt WooCommerce, introduce a new database, or
deploy anything.

---

## 2. Verified baseline and dependencies

### 2.1 Repository baseline (checked before planning)

| Item | Verified value |
| --- | --- |
| Branch / upstream | `main` / `origin/main` |
| HEAD | `e30d42d269b1fce074cc61c152e9008f182d3de4` |
| Working tree | clean except user-owned untracked `.cloud-attachments/` |
| App | Next.js 16.3.8 / React 19 / TypeScript / Tailwind, `commerce/` |
| Data | PostgreSQL 16 by Drizzle, `commerce` namespace; no WooCommerce in this track |
| Local DB harness | `commerce/docker-compose.db.yml`, loopback `127.0.0.1:55431` |
| Seed | `commerce/scripts/seed-catalog.sql` — 3 categories / 3 published products / 15 variants / 0 images |
| Media | local content-addressed filesystem provider (or local MinIO), fail-closed |
| Payment/SMS | mock/fail-closed only; no credential exists |
| Browser | system Google Chrome; `playwright-core` already installed |
| Docker | daemon available on this machine; no commerce services were running at baseline |
| Last recorded offline evidence | 547/547 tests, 129 suites, typecheck/lint/db-check/build passed at `e30d42d` |
| Live evidence | 7 live-db files exist; not run during this baseline check |
| Graph | `graphify-out/GRAPH_REPORT.md` is generated and stale at `c66c513`; it is not authoritative |

### 2.2 Current record conflicts found

These are recorded, not silently rewritten:

1. `docs/deployment/local-pilot-readiness.md` is explicitly a measurement of
   `5c82312`/`015ea4a`. Its 497/117 and 77/24 counts and 55432 port references
   are historical; current harness default is 55431.
2. Its §5.1 says DRAFT/unknown PDPs return HTTP 200. The current page resolves
   `notFound()` in `generateMetadata` and `scripts/check-storefront-status.mjs`
   exists to assert 404. This must be re-measured; the old observation is not
   current evidence.
3. `commerce/README.md` contains historical "Phases 5–6 not started" text that
   is explicitly superseded later in the same file and by the roadmap. It must
   not be read out of order.
4. `TODO.md` Phase 2 text still mentions the old external-URL path; later
   D-173 records remove it. Historical text remains historical.
5. The phase-6 checklist's **B1 credentials** gate is a production owner act;
   the owner-scoped "B1 stabilization" is a different, completed local slice.
   LSE does not rename or close the credential gate.

### 2.3 Dependencies and limits

- Docker daemon + the disposable `commerce-db-harness` for DB-backed E2E.
- A local synthetic admin identity supplied at run time (no committed password).
- System Chrome (or `CHROME_PATH`) for `playwright-core`.
- The full E2E run must be loopback-only. A remote base URL is refused.
- The fail-closed run starts a server **without** `DATABASE_URL`.
- No production/staging environment, real payment, real SMS, live webhook,
  paid AI, credential, destructive migration or data deletion is used.

---

## 3. Scope

### In scope

- Repeatable local browser E2E for the existing customer storefront.
- Synthetic checkout against the disposable harness and mock/fail-closed
  payment, followed by merchant-panel order reconciliation.
- Storefront fail-closed surfaces with no database configured.
- Unknown/DRAFT product HTTP behavior where supported.
- Responsive/RTL overflow checks at 320, 390 and 1440 CSS pixels.
- Basic accessible-name, heading, focus, empty-state and no-image behavior
  checks that the existing UI supports.
- A safe local runbook, seed/reset procedure, output format and evidence record.
- Documentation reconciliation for this track.

### Explicit non-goals

- Building a new storefront, framework, database, ORM or CSS system.
- Adopting WooCommerce or replacing the D-172 SSOT.
- Production deployment, staging, manifests, digests, DNS, TLS or ingress.
- Real ZarinPal/Kavenegar credentials, sending, capture, refunds or webhooks.
- Paid AI calls, live social publishing or OTP implementation.
- Backup/restore rehearsal, load testing, penetration testing or a real-customer
  pilot.
- Deleting orphan media, migrating legacy image rows, or changing the media
  provider decision.
- Exhaustive visual-regression screenshots or device-lab coverage.
- Fixing unrelated historical documentation or code outside LSE.

---

## 4. Ordered task register

Status values: `PLANNED` → `IN PROGRESS` → `DONE` / `BLOCKED`.

| ID | Task | Depends on | Status | Evidence |
| --- | --- | --- | --- | --- |
| LSE-01 | Baseline reconciliation and canonical LSE record | — | DONE | this document + D-174 + canonical-doc links |
| LSE-02 | Repeatable E2E harness foundation | LSE-01 | DONE | `check:e2e` + `check:e2e:fail-closed`, guards exercised |
| LSE-03 | Storefront golden path: home → catalog → PDP → cart → checkout | LSE-02 | DONE | 55/55 full E2E checks |
| LSE-04 | Fail-closed, status, responsive and basic accessibility guards | LSE-02 | DONE | 13/13 fail-closed + HTTP 200/404/CSP |
| LSE-05 | Merchant order reconciliation for the synthetic order | LSE-03 | DONE | synthetic order found with `PENDING` |
| LSE-06 | Final verification, evidence reconciliation and close-out | LSE-03/04/05 | DONE | 547 offline / 87 live-local / build |

Tasks LSE-03, LSE-04 and LSE-05 are independent after LSE-02 and may be run in
any order. LSE-06 waits for all three.

---

## 5. Task specifications

### LSE-01 — Baseline reconciliation and canonical LSE record

- **Objective:** establish the verified baseline, record conflicts and make LSE
  the canonical execution checklist.
- **Subsystem:** documentation/governance only.
- **Prerequisites:** current Git state; reads of `PROJECT_RULES.md`,
  `MASTER_PLAN.md`, `TODO.md`, `DECISIONS.md`, roadmap, pilot record, code and
  test inventory.
- **Expected changes:** this file; D-174; pointers in `MASTER_PLAN.md`,
  `TODO.md`, the fashion roadmap and `docs/README.md`; historical-record notes
  where a current statement would otherwise be false.
- **Verification:** Markdown links resolve; no owner gate is changed; no code is
  edited.
- **Acceptance:** a reader can identify the current phase, why LSE is next, what
  is excluded, and which older statements are historical.
- **Evidence to record:** baseline commit, branch/upstream, conflict list.

### LSE-02 — Repeatable E2E harness foundation

- **Objective:** add one committed browser runner and npm entry point that fails
  closed on unsafe configuration.
- **Subsystem:** `commerce/scripts/`, `commerce/package.json`, `commerce/README.md`.
- **Prerequisites:** LSE-01; `playwright-core` and system Chrome.
- **Expected changes:**
  - `commerce/scripts/check-storefront-e2e.mjs`;
  - `check:e2e` (full journey) and `check:e2e:fail-closed` (no-DB mode);
  - structured PASS/FAIL/SUMMARY output and non-zero exit on any failure;
  - guards: loopback-only base URL, no `NODE_ENV=production` assumption hidden,
    explicit admin credentials for the admin step, missing Chrome is a named
    refusal.
- **Verification:** run with no server (must fail clearly), non-loopback URL
  (must refuse), and against the disposable local stack after LSE-03–05 exist.
- **Acceptance:** no new dependency; no secret in args/logs; command is reusable
  without manual clicking; failures identify the step.
- **Evidence:** command, refusal results, final summary.

### LSE-03 — Storefront golden path

- **Objective:** prove the customer journey in a real browser against the local
  disposable database.
- **Subsystem:** `/`, `/catalog`, `/products/[slug]`, `/checkout`, cart storage.
- **Prerequisites:** LSE-02; harness migrated and seeded.
- **Expected checks:**
  - homepage renders the real hero/categories/rails and no unavailable notice;
  - catalog renders the three seeded products;
  - search narrows to the expected product; a no-match query shows the empty
    state; clearing filters restores the list;
  - PDP opens the seeded product, selects a sellable colour/size, adds to cart;
  - the cart drawer opens, quantity can increase, and the basket survives a
    reload through `localStorage`;
  - checkout accepts a synthetic customer, creates a `PENDING` order and shows
    the server-computed total and payment refusal status;
  - the cart clears after a successful placement.
- **Verification:** `npm run check:e2e` against the disposable stack.
- **Acceptance:** every check passes; no step relies on a fixed order UUID or
  seed mutation beyond a new synthetic order; a second run still passes.
- **Evidence:** PASS step list, order id captured by the run (synthetic only),
  final counts.

### LSE-04 — Fail-closed, status, responsive and basic accessibility guards

- **Objective:** verify the storefront's non-happy paths and layout safety.
- **Subsystem:** storefront routes/layout; existing HTTP status script.
- **Prerequisites:** LSE-02; a second local server without `DATABASE_URL` for
  fail-closed mode.
- **Expected checks:**
  - no-DB mode: `/`, `/catalog`, `/products/<known>`, `/checkout` all state that
    data/checkout is unavailable; `/checkout` renders no customer form;
  - unknown product returns HTTP 404, not a soft 200;
  - at 320, 390 and 1440 CSS px, `/`, `/catalog` and `/checkout` have no document
    horizontal overflow and keep `dir=rtl`;
  - exactly one `h1` per checked page; primary controls have accessible names;
  - keyboard focus reaches the main skip target/cart control (where applicable);
  - checkout with an empty basket shows the empty state and no form submit path.
- **Verification:** `npm run check:e2e:fail-closed` + full E2E layout checks +
  `npm run check:http-status`.
- **Acceptance:** all checks pass, or a real defect is fixed within the track
  and the check is rerun.
- **Evidence:** mode, widths, status codes and PASS/FAIL list.

### LSE-05 — Merchant order reconciliation

- **Objective:** prove the synthetic customer order is visible to the merchant.
- **Subsystem:** `/admin/login`, `/admin/orders`.
- **Prerequisites:** LSE-03; local synthetic admin credentials in the run
  environment.
- **Expected checks:** login succeeds; `/admin/orders` lists the order prefix
  returned by checkout, the synthetic customer and `PENDING`.
- **Verification:** part of `npm run check:e2e`.
- **Acceptance:** the exact order created in LSE-03 is found; no admin write is
  performed.
- **Evidence:** order prefix, status, PASS line.

### LSE-06 — Final verification and close-out

- **Objective:** run every applicable gate, reconcile documents with actual
  results, and leave a clean tracked change set.
- **Subsystem:** whole `commerce/` + governance docs.
- **Prerequisites:** LSE-01–05 complete.
- **Expected checks:** typecheck, lint, full offline tests, `drizzle-kit check`,
  production build, opt-in live PostgreSQL suite, E2E full, E2E fail-closed,
  HTTP status check, `git diff --check`, secret/scope review.
- **Acceptance:** no failed applicable check; skipped checks have exact reasons;
  documentation matches measured results; only intended files are committed.
- **Evidence:** commands + exact counts in §9 and `TODO.md`.

---

## 6. Dependency / order map

```text
LSE-01
  └── LSE-02
        ├── LSE-03 ── LSE-05
        ├── LSE-04
        └──────────────┐
LSE-03 + LSE-04 + LSE-05
  └── LSE-06
```

- LSE-03 and LSE-04 touch different modes and can be developed/run
  independently.
- LSE-05 reads the order LSE-03 creates; it runs in the same full E2E pass.
- LSE-06 must not close until every unblocked task has a recorded result.

---

## 7. Local environment, startup and safe failure

All commands run in `commerce/`. Nothing binds beyond loopback.

```bash
# 1. disposable database
npm run db:up
export COMMERCE_DATABASE_URL=postgresql://commerce_smoke:commerce_smoke_local_only@127.0.0.1:55431/commerce_smoke
export DATABASE_URL="$COMMERCE_DATABASE_URL"
npm run db:reset
npm run db:migrate
npm run db:seed

# 2. local synthetic admin identity (generated per run; never committed)
npm run admin:hash -- '<local-only-password>'
export ADMIN_USERNAME=owner
export ADMIN_PASSWORD_HASH='<output of the command above>'
export ADMIN_SESSION_SECRET='<local random value>'

# 3. built app on loopback
npm run build
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH" \
ADMIN_SESSION_SECRET="$ADMIN_SESSION_SECRET" \
DATABASE_URL="$DATABASE_URL" \
MEDIA_PROVIDER=local MEDIA_LOCAL_DIR=/tmp/aobe-lse-media MEDIA_LOCAL_UPLOAD_ENABLED=true \
SMS_LIVE_ENABLED=false \
  npx next start -H 127.0.0.1 -p 13002

# 4. checks
COMMERCE_BASE_URL=http://127.0.0.1:13002 \
ADMIN_USERNAME=owner ADMIN_PASSWORD='<same local password>' \
  npm run check:e2e
COMMERCE_BASE_URL=http://127.0.0.1:13002 \
KNOWN_PRODUCT_SLUG=manto-katan-jelo-baste \
  npm run check:http-status

# 5. fail-closed server: a second port, no DATABASE_URL
ADMIN_USERNAME=owner ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH" \
ADMIN_SESSION_SECRET="$ADMIN_SESSION_SECRET" \
  npx next start -H 127.0.0.1 -p 13003
COMMERCE_BASE_URL=http://127.0.0.1:13003 npm run check:e2e:fail-closed

# 6. teardown
npm run db:down     # keep the volume; never use -v for a shared/dev store
```

**Health:** `GET /healthz` must answer 200 only with a reachable DB. The E2E
runner waits on HTTP readiness with a bounded timeout; a banner alone is not
readiness.

**Seed/reset:** `db:reset` is destructive but restricted to the disposable
loopback harness. It drops only schema `commerce` and the Drizzle journal, then
re-applies committed migrations. `db:seed` is insert-only and does not restore
edited values. Existing development data is never the E2E target.

**Failure handling:** a missing Docker daemon, non-loopback URL, missing Chrome,
missing admin config or unavailable DB is a named refusal, not a skip reported
as PASS. A failed E2E step exits non-zero and retains the PASS/FAIL report.
Servers and the harness are stopped after the run; the harness volume is kept
unless the operator deliberately chooses otherwise.

---

## 8. Test strategy

| Layer | Tool / command | Runs when | Purpose |
| --- | --- | --- | --- |
| Pure/offline | `npm test` | every change | rules, services, memory repository |
| Type/lint/schema | `npm run typecheck`, `npm run lint`, `npm run db:check` | every change | static/offline gates |
| Build | `npm run build` | every change | route/compile contract |
| Live PG | `npm run smoke:db` | local harness available | real SQL, races, migrations |
| E2E full | `npm run check:e2e` | disposable DB + server | browser customer journey + admin reconciliation |
| E2E fail-closed | `npm run check:e2e:fail-closed` | no-DB server | fail-closed/empty surfaces |
| HTTP status | `npm run check:http-status` | built server | 200/404 semantics |
| Mobile/admin | `npm run check:admin-mobile` | optional local admin server | existing admin overflow guard |

Live-service tests that require credentials or a reachable provider remain
**disabled** and are not part of LSE. No test may send real money, SMS, email,
webhook or AI request.

---

## 9. Data, media and safety rules

- Use only the disposable loopback harness on `127.0.0.1:55431`; the reset/seed
  scripts refuse other targets.
- Use synthetic names, phone numbers, addresses and postal codes. Do not use
  real customer data.
- Existing development rows/media are not touched. `db:reset` runs only against
  the disposable harness.
- Media uses the local content-addressed provider only; no external URL is
  accepted. E2E must not create legacy/external image rows.
- Order creation consumes stock in the harness; this is expected synthetic
  state. Re-run `db:reset`/`db:seed` for a pristine catalog.
- Never commit the generated admin hash, session secret, local password,
  cookies, tokens or `.env` values.
- `.cloud-attachments/` and unrelated user files are never staged.
- No production, staging, real provider, destructive migration or live webhook
  action is permitted.

---

## 10. Definition of done and pause conditions

LSE is done when:

- LSE-01–06 are `DONE` or explicitly `BLOCKED` with a named external reason;
- the new E2E command exists and passes twice against a fresh disposable stack;
- fail-closed and HTTP-status checks pass;
- full offline and live-local verification results are recorded;
- documentation states measured behavior, not intended behavior;
- the diff is scoped, secret-free and `git diff --check` clean;
- a focused commit is pushed fast-forward, if policy permits.

**Pause and ask the owner** if:

- Docker/harness or Chrome cannot run and no safe local substitute exists;
- a required local admin identity cannot be generated;
- a check would require production/staging, a real credential, real payment/SMS,
  a live webhook, paid AI or destructive data work;
- a discovered defect requires a major architecture/vendor/security decision;
- documentation contains conflicting owner decisions that cannot be resolved by
  marking history vs current status.

---

## 11. Evidence log

Append-only; filled as tasks complete.

- **2026-11-12 — LSE-01:** baseline `main`/`origin/main` at
  `e30d42d269b1fce074cc61c152e9008f182d3de4`; clean except
  `.cloud-attachments/`. Storefront/admin/live suites and scripts verified to
  exist; no repeatable browser E2E command found. Historical pilot/graph
  records identified as stale and classified above. No code changed.
- **2026-11-12 — LSE-02:** `scripts/check-storefront-e2e.mjs` added with
  `check:e2e` and `check:e2e:fail-closed`. Non-loopback base URL and missing
  Chrome each exit 2 before opening a page; no dependency was added.
- **2026-11-12 — LSE-03/05 (local):** disposable harness reset/migrated/seeded
  (3 categories / 3 products / 15 variants), production build (22 routes), then
  **3 consecutive full E2E runs, 55/55 PASS each** (one intermediate selector
  fix, then clean). Each run created one synthetic `PENDING` order and found its
  first eight characters, the synthetic customer and `PENDING` in `/admin/orders`.
  Payment stayed `UNAVAILABLE`; no real provider was called.
- **2026-11-12 — LSE-04 (local):** second server with `DATABASE_URL=''`:
  `/healthz` **503** `db_unconfigured`; all four data surfaces showed the
  unavailable notice; checkout rendered no form; **13/13 fail-closed PASS** at
  320/390. Built server HTTP check: published **200**, unknown **404**, admin CSP
  PASS. Full E2E layout checks: 320/390/1440 × `/`, `/catalog`, `/checkout`,
  no horizontal overflow, RTL and one named `h1`; keyboard focus entered a link.
- **2026-11-12 — LSE-06:** `npm run verify` exit 0 — typecheck 0, lint 0,
  **547/547 tests across 129 suites**, `db:check` 0. `npm run smoke:db` exit 0 —
  **87/87 tests across 26 suites** on PostgreSQL 16.15. `npm run build` exit 0
  (22 routes; the pre-existing `src/server/media/serve.ts:88` Turbopack tracing
  warning remains). Neither server, the harness, nor any credential was left in
  the repository.
