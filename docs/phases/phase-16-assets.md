# Phase 16 — Content Versioning & Media Asset Management (D-097–D-100)

- Status: **implemented (M1–M4), owner-approved decisions**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  content-addressable assets, append-only version chains, injected
  clock for lifecycle, binaries behind the Phase 3 MediaStore
  abstraction (D-049/D-056).

## 1. Objective

Give every piece of content immutable, versioned media with
content-addressable deduplication, deterministic variant derivation,
quarantine-based (never rushed) garbage collection, and a full audit
trail from which any historical version can be reconstructed.

## 2. Decision table

| Decision | Content | Module |
|---|---|---|
| D-097 | `MediaAsset` (checksum PK, mime, size, storage ref, metadata) + `ContentVersion` (content_id, monotonic version_number, asset_id, parent_version_id); append-only chains; one checksum = one asset | `asset_contracts.py` |
| D-098 | Atomic registration via PG unique constraints (`assets.media_asset` PK checksum; `assets.content_version` unique (content_id, version_number)) + JSON parity; Class-B pre-storage validation (checksum mismatch, size cap, mime allow-list + signature cross-check) | `asset_engine.py` |
| D-099 | Deterministic variant derivation behind an injected processor; derivation key SHA-256(parent checksum, kind, canonical params); lifecycle PENDING_DERIVATION → PROCESSING → READY \| FAILED; retries never duplicate | `asset_worker.py` |
| D-100 | Soft-delete/quarantine with injected-clock retention cooldown; GC-eligibility requires unreferenced + cooldown elapsed; every action a D-027 event; historical version reconstruction from durable events alone | engine + worker |

## 3. Architecture flow

```
producer (campaign / content pipeline)
        │  bytes + declared mime/metadata
        ▼
AssetVault.register ──► Class-B pre-storage validation (D-098)
        │                 checksum · size cap · mime allow-list
        ▼
  content-addressed store (MediaStore injected, D-049/D-056)
        │  one checksum = one asset (dedup by construction)
        ▼
ContentVersion.append (content_id, vN, parent link — append-only)
        │
        ▼
VariantProcessor (injected) ──► derivation key = SHA-256(parent, kind, params)
        │  PENDING_DERIVATION → PROCESSING → READY | FAILED
        ▼
QuarantineScanner (injected clock): unreferenced assets →
  QUARANTINED (cooldown) → GC-ELIGIBLE (still flagged, never removed here)
        │
        ▼
audit trail on D-027 · reconstruction of any historical version
```

## 4. Security boundaries

- Zero network in canonical modules; the MediaStore (D-049/D-056)
  and any transcoder are injected behind provider-neutral
  interfaces (RULES §35).
- No cloud SDKs, no credentials, no `os.environ` in the canonical
  asset modules (D-045).
- Class-B validation runs BEFORE any byte reaches storage; the
  vault never deletes binaries (only D-100 quarantine flags).
- Every durable string passes the store redaction discipline.

## 5. Milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | Contracts: schemas, hash/mime rules, version graph, variant specs | done |
| M2 | Engine: vault (PG + JSON parity), dedup, version increments, schema | done |
| M3 | Worker: variant derivation bridge, quarantine scanner, reconstruction | done |
| M4 | Suite incl. live-PG E2E, AST audit, full regression, docs | done |

## 6. Verification record (M4 closeout, 2026-09-17)

- Suite `local/tests/test_phase16_assets.py`: **20/20 OK, zero
  skipped** (17 offline across M1–M3 + live-PG E2E on real
  `PgEventStore` + real PG `assets.media_asset`: register→dedup→
  version chain, 8-thread same-checksum single-creator race,
  quarantine scan on shared durable state, restart parity).
- Full battery **596/596 OK, zero skips**; ladder 46/46 OK;
  containers 5/5 healthy (live layer ran, not skipped).
- AST audit CLEAN — zero network imports, zero cloud SDKs, zero
  platform/pricing/notification-module imports in the asset modules,
  zero `os.environ`; binaries stay behind the injected Phase 3
  MediaStore seam (D-049/D-056) — the engine persists references
  only. The two scan hits are the D-027 `services.sync_engine`
  EventStore dependency (injected in notification/analytics;
  imported here for IntegrityError typing — the established
  Phase 13–15 precedent). Secret scan CLEAN; `git diff --check`
  PASS.

### Defects exposed and fixed in-batch

1. **Engine (concurrency, live-exposed):** concurrent registrations
   of the same checksum all recorded dedup under ONE event id —
   losers collided with the winner's terminal row and raised
   IntegrityError out of the worker thread (D-027 terminal guard).
   `_record` now treats a lost exactly-once race as a clean loser:
   the audit row is already durable, `False` returned, nothing lost.
2. **Engine (contract gap):** `register_asset` silently DROPPED a
   caller-declared checksum that contradicted the bytes, violating
   its own "computed not declared" contract — a corrupt registration
   now raises Class-B before any storage (D-098), test-asserted.
3. **Test harness:** `_JsonVault` mkdirs its `.vault` root as a
   directory while cleanup `os.remove`d it (EPERM) — the teardown
   error cascade masked all M2/M3 results. Cleanup now handles
   dirs and files; the EPERM cascade is gone.
4. **Test premise:** `validate_variant_kind` returns the variant
   SPEC dict (D-099), not a kind set — the derivation-keys test
   asserted membership over the wrong value; corrected to assert
   the spec identity against `VARIANT_SPECS`.
5. **Engine (diag):** declared-checksum shadowing bug during the
   fix (rebound the `declared` dict) caught by the suite before
   commit; fixed with a distinct name.
