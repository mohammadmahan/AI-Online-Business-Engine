# Stage H — Vendor Exit & Restore Harness (D-141; PLANNED artifacts, drill owner-gated)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED readiness artifacts + OFFLINE-PROVEN harness.**
  No staging or production host exists; nothing has been exported from
  a real deployment. Execution against a real environment requires the
  per-item owner authorizations in `dokploy-plan.md` §17.
- Predecessors: `docs/runbooks/dokploy-exit-plan.md` (what lives where)
  and `docs/runbooks/dokploy-exit-drill.md` (I1–I5 invariants). This
  document adds the **data-plane** guarantee those runbooks require:
  the SSOT itself can leave with zero loss and re-hydrate anywhere.
- Guarantee being proven: **the business SSOT is portable by
  construction** — exportable as a tamper-evident, optionally
  encrypted archive, re-hydratable on a blank target with **100%
  schema integrity and row parity**, independent of Dokploy, the
  cloud, or the orchestrator (Phase 24 / D-129–D-132).

## 1. The harness (`local/scripts/verify_vendor_exit.py`)

Exit codes: `0` pass · `1` named failure · `2` refused / cannot
assess. Fail-closed throughout; secrets never enter logs or output.

| Mode | What it does | Boundary |
|---|---|---|
| `check` | Offline self-proof over synthetic surfaces: fold parity, tamper detection, armored round-trip, wrong-passphrase refusal, redaction, D-045 shell hygiene (refuses if production material is in the environment) | No docker, no DB, no network |
| `export` | Dumps the declared SSOT surfaces via the read-only `container_psql_query` transport into the migration archive; every string field passes the D-124 redactor | Read-only SELECTs; D-045 refusal first |
| `dry-run-import` | Synthetic re-hydration: (de)armor → parse → per-surface fold + row-count parity against the manifest — the "backup is not valid until a restore succeeded" rule (D-137), applied to migration archives | No target host needed |

## 2. Archive format (`vendor_exit.archive.v1`)

- **Manifest** (first line): format, launch-candidate id, per-surface
  `{row_count, fold}`, total rows. `fold` = SHA-256 over the
  canonical-JSON row stream — any flip, drop, reorder, or unparseable
  line fails `dry-run-import` (D-128 forgery discipline).
- **Rows**: one `{surface, row}` JSON object per line, deterministic
  ordering; string fields D-124-redacted at export (zero-leak, D-114).
- **Armoring (optional but required for off-host transfer):**
  `--passphrase-file` (or `VENDOR_EXIT_PASSPHRASE`) wraps the archive
  in PBKDF2-HMAC-SHA256 (200k iters, 16-byte salt) + an NIST SP
  800-90A **HMAC_DRBG** keystream, with an HMAC-SHA256 integrity tag.
  Honest posture: this is stdlib-only **defense-in-depth**, not a
  substitute for storage-layer encryption (S3 SSE / disk); the
  primary confidentiality control remains the operator's storage.

## 3. Declared export surfaces (v1)

The thirteen launch-relevant SSOT surfaces (`DEFAULT_SURFACES`):
canonical content/review, orchestration outbox, event store, OMS
orders + events, Instagram/Telegram publish outboxes, the HITL
decision ledger, the Phase 19 control-audit chain, provenance
receipts, and the media index. New durable surfaces MUST be added
here (test-pinned) before they are launch-relevant.

## 4. Exit procedure (owner-gated; ordered)

1. **Gate:** Stage H owner authorization (plan §17) + latest
   restore-verified backups (DR runbook §1) already off-host.
2. **Freeze writes** (maintenance window); record the launch-candidate
   commit and stack state (health drill).
3. **Export:** `verify_vendor_exit.py export --output ... --candidate
   <commit> --passphrase-file <file>`; transfer armored archive
   off-host (S3 dest, separate credentials).
4. **Prove before teardown:** `dry-run-import` on the archive —
   parity green — **and** the drill of `dokploy-exit-drill.md`
   (I1–I5) green. An archive that has not passed a restore proof is
   NOT a backup (D-137 control BAC-001 rule).
5. **Teardown** per exit-plan §3 (volumes retained until target
   parity proven). No forensic/ledger record is ever deleted.
6. **Re-hydrate on target** (vanilla Compose / K8s / plain Linux +
   Docker): apply `local/db/schema.sql`, import the archive into the
   blank SSOT, re-run the parity proof + `verify_snapshot` + decision
   ledger chain verification (D-027) on the restored store.
7. **Attest:** emit the exit evidence (harness output + parity
   verdict + commit + archive hash) to the D-121 log ledger; Phase 19
   control-audit row for the owner authorization.

## 5. Relationship to D-125

D-125 verified-freeze compaction remains the retention mechanism for
*in-place* history; the Stage H archive is the *whole-store
migration* envelope. Both share the same fold/verify discipline; an
exit archive never replaces retention policy and vice versa.

## 6. Non-goals

- No live export has been performed (no host exists).
- No claim that the stdlib armoring replaces managed encryption.
- No automatic teardown: every destructive step is a separate,
  explicitly authorized operator action recorded in the audit chain.
