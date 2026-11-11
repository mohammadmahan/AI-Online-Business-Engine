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
| AUD-14 | Dokploy runtime check blocked by pinned image pulls. | Investigated without deploying. The failure remains an image-registry pull, not application logic. | `test_runtime_mode_with_local_daemon` fails on `Image quay.io/minio/minio@sha256:14cea493…` pull; earlier pinned WordPress image also failed. Suite totals: 2,877 run, 2,773 passed, 1 failed, 103 skipped. | **BLOCKED** — registry access or a locally preloaded, approved image set; runtime not verified |

## Coverage gap outside AUD numbering

| Gap | Result | State |
|---|---|---|
| Authenticated admin CRUD, media upload, order transition in an isolated browser setup | Not exercised end to end. The standing dev database was deliberately not written to. A local disposable admin session with generated credentials, a separate app origin and media target was not available/created for this pass. Unit/auth and live repository/media paths passed, but this is not a completed authenticated browser flow. | **BLOCKED / NOT VERIFIED** |
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
4. Provide registry access or an approved preloaded image set for Dokploy runtime
   verification.
5. Authorize a separate isolated admin-browser rehearsal if authenticated CRUD,
   upload and transitions need end-to-end evidence.
