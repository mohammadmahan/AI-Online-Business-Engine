# Staging Volume Backup & Retention Policy (template)

- Work package: **Dokploy Deployment Integration** (D-141, Approved) —
  Stage B artifact (G-B3).
- Status: **PLANNED template** — no staging host exists, no backup
  destination is connected, no schedule is active. Everything below is a
  configuration template and policy proposal; activation happens at Stage C
  (backup-credential owner gate) and proof at Stage D (restore drills).

## 1. Relationship to the project's recovery authority (supplement-only)

Dokploy volume backups (or any equivalent scheduled dump) **supplement —
never replace** — the project's authoritative recovery machinery:

| Authority | Surface | What only it provides |
|---|---|---|
| D-125 verified-freeze archives | `write_snapshot`/`verify_snapshot` (fold-attested) | Tamper-evident fold equality; tear-down-proof rehydration of durable rows |
| Transactional DR drill | `local/scripts/resilience_drill.py` | Proven catastrophic-loss recovery of the event store (EV-BAC-001) |
| Decision-ledger DR drill | `local/scripts/decision_ledger_drill.py` | Full-chain loss in ONE transaction + identical-head-hash re-verification + decided-vs-happened consistency |
| Unified attestation | `local/scripts/launch_attestation.py` | D-138 GO binding: BOTH drills fresh and green |

A successful backup **upload is not restoration evidence** (D-137
principle). Restore drills (Stage D) are the only proof, and they must
re-verify ledger chain hashes and fold equality after rehydration.

## 2. Per-volume schedule and retention (proposal — owner-approved RPO/RTO pending)

All six volumes are Docker named volumes (Stage A F-4) and therefore
eligible for named-volume backups per official Dokploy documentation.
Restore preconditions documented there apply: **the destination volume must
not exist and consuming containers must be stopped** for a named-volume
restore; Dokploy names restored volumes `{appName}_{volumeName}`.

| Volume | Contents | Schedule (proposed) | Retention (proposed) | Notes |
|---|---|---|---|---|
| `canonical_data` | PostgreSQL: D-027 event store, registry, provenance, Phase 19 `admin.control_audit` chain | Every 6 h + pre/post maintenance windows | 30 daily, 8 weekly, 6 monthly | Highest criticality: also covered by D-125 archives + both drills. A pg_dump-equivalent consistent snapshot is acceptable; volume-file copy only with containers stopped |
| `woo_data_db` | MySQL: Woo projection database | Every 12 h | 14 daily, 6 weekly | Projection target — rebuildable from canonical; backup is for projection continuity, not truth |
| `woo_data` | WordPress/Woo files | Daily | 14 daily | Projection asset files |
| `media_data` | Object storage (media assets) | Daily | 14 daily, 4 weekly | Off-host copy mandatory — assets are not reconstructable from canonical data |
| `n8n_data` | n8n workflows, credentials refs, execution state | Every 12 h | 14 daily | Workflows are version-controlled where possible; this backs the runtime state |
| `mock_state` | Mock-Woo fixtures (profile-deferred) | Weekly | 4 | Lowest priority; deterministic fixtures are regenerable |

- **RPO (proposed):** canonical data ≤ 6 h; media ≤ 24 h. **RTO (proposed):**
  canonical store ≤ 2 h (restore + schema apply + fold verification); full
  stack ≤ 4 h. Both **require owner approval** before Stage C activation.
- **Off-host requirement:** every backup destination must be off-host
  (S3-compatible object storage, e.g. the Phase 24 `MediaStoreContract`
  pattern). Same-host copies never count as disaster protection.
- **Separate credentials:** backup destination credentials are distinct
  from application credentials, minimum-permission (write + list on one
  bucket prefix only), and never stored in Git or the application env.
- **Encryption:** enabled where the destination supports it; at minimum
  server-side encryption + TLS in transit.
- **Failure monitoring:** backup failures must surface as alerts (routed
  via the Phase 14 notification model) — a silently failing schedule is
  worse than none.

## 3. Restore procedure prerequisites (from official documentation)

1. Named-volume restore requires the destination volume to **not exist**
   and its consuming containers to be **stopped** — schedule a stop window.
2. Restored volume naming follows `{appName}_{volumeName}` — compose
   project name determines the prefix; record it in the Stage C runbook.
3. After any restore of `canonical_data`: run `scripts/apply_schema.py`
   (idempotent), then **verify the decision-ledger chain hash and fold
   equality** (`decision_ledger_drill.py --consistency-only`) before
   declaring recovery.
4. After any restore: run the Stage D acceptance checks — never trust
   dashboard status or command exit codes alone.

## 4. Stage mapping

- **Stage C:** connect the approved S3 destination (owner gate); enable
  the `canonical_data` schedule first; verify one scheduled run + one
  manual run exist in the destination (list-only proof).
- **Stage D:** execute the restore drills: full stop → volume wipe →
  restore → schema apply → ledger chain verification → fold check;
  repeat for a media volume; record evidence with timestamps and artifact
  identifiers (existing `EV-*`/`qa.*` conventions).
- **Stage H:** the exit drill must restore from these off-host archives
  WITHOUT any deployment layer, proving the policy is layer-independent.
