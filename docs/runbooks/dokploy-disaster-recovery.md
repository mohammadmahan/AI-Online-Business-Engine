# Runbook: Dokploy Disaster Recovery (PLANNED — not yet executable)

- Status: **PLANNED.** Procedures are defined for Stages D/G execution
  after D-141 approval and stage authorizations. Nothing has been
  performed; no backup destination is connected.
- Principle: Dokploy backup features **supplement** — never replace —
  the project's recovery machinery (D-125 verified-freeze archives,
  DR drills, D-138 evidence, EV-BAC-001 conventions).
- Companion: `docs/deployment/dokploy-plan.md` §12 (facts source:
  official docs, review date there).

## 0. Scope and hard rules

1. The append-only Phase 19 decision ledger is **never** tested by
   deleting, truncating, compacting, or destructively modifying live
   data. Its only catastrophe semantics: the existing atomic
   full-chain verified-freeze round-trip
   (`local/scripts/decision_ledger_drill.py`).
2. A successful backup upload, a green dashboard, or a zero exit code
   is **not** restoration evidence. Evidence = an isolated restore
   plus application-level integrity verification, recorded with
   timestamps and artifact identifiers.
3. Restores happen into **isolated targets** (separate namespace/
   host), never over live state.
4. Bind mounts are not covered by Dokploy Volume Backups (official
   docs); the project mandates named volumes — any future bind mount
   requires its own backup strategy before use.

## 1. Backup architecture (PLANNED)

| Surface | Mechanism (candidate) | Verification |
|---|---|---|
| PostgreSQL canonical DB | Dokploy database backup → S3 AND/OR project `pg_dump` | restore into isolated PG; battery-compatible checks; source-system isolation |
| Decision ledger (rows inside `canonical_data`) | raw volume snapshot is a *bonus*; authoritative path = D-125 verified-freeze snapshot + `verify_snapshot` | `verify_chain()` + `--consistency-only` post-restore |
| MySQL (Woo) | Dokploy database backup → S3 | isolated restore + Woo-level checks |
| n8n volume | Volume Backup (named volume) + stop-container option for consistency | isolated restore; workflow import check |
| MinIO media volume | Volume Backup; D-056 adapter stays provider-neutral | object listing + checksum comparison |
| Dokploy control plane | Control-plane backup (`dokploy-postgres` + `/etc/dokploy` → S3) | documented restore incl. IP/DNS/provider reconfiguration steps |

Backup credentials: dedicated per environment, least-privilege
(put/get/list on the exact bucket/prefix), rotation runbook entry,
never reused across environments (plan §11).

Retention, encryption, and RPO/RTO: **proposed values require owner
approval** (plan §17.5) — none are declared here.

## 2. Scenario: Dokploy server loss

1. Provision replacement host from the runbook checklist (ports,
   sizing, distro).
2. Restore Dokploy control plane from its S3 backup; expect the
   documented consequences: `/etc/dokploy` replaced, control DB
   recreated, possible re-login; update server IP, Git-provider
   settings (if IP-based), and DNS records per official docs.
3. Recreate data services from off-host backups into **named
   volumes** (restore preconditions per docs: target volume must not
   exist; consuming containers stopped; compose volume naming
   `{appName}_{volumeName}`).
4. Integrity verification before "recovered" is claimed:
   - `decision_ledger_drill.py --consistency-only` → `ok: true`
   - transactional store verification (drills) on restored data
   - D-123-style health probes green
5. Record recovery evidence (timestamps, backup artifact ids, drill
   outputs) — EV-BAC-001 conventions.
6. **RPO note:** recovery point is bounded by backup cadence; the
   approved RPO governs acceptability (pending owner approval).
7. Stop condition: if chain verification fails on restored data, the
   restore is a FAILURE — escalate; never "fix" by editing ledger
   rows.

## 3. Scenario: corrupted volume

1. Stop the affected service (documented stop-container behavior).
2. Quarantine the corrupted volume (rename/retain for forensics); do
   not delete before evidence capture.
3. Restore into a NEW volume from the latest verified backup
   (preconditions as §2.3).
4. Repoint/verify; run the integrity battery scoped to the affected
   store; record evidence.
5. Root-cause entry into the risk register (plan §15).

## 4. Scenario: failed deployment / failed database migration

- **Failed deployment:** the service keeps the previous container
  (Dokploy keeps the old one running; in-progress deploys cannot be
  canceled — queue-only); roll back by redeploying the last verified
  artifact; record deploy-event outcome in the D-121 ledger.
- **Failed migration:** engines must run backward-compatible
  migrations by default; on failure, recovery = restore the DB backup
  taken *before* migration into the isolated target, validate, then
  decide forward-fix vs rollback with the owner. Untested rollback
  paths are never declared safe (plan §16).
- Either way: the Phase 25 fault-ladder semantics apply at the
  application layer (no cursor advancement on failed ingest; Class
  routes per D-052).

## 5. Scenario: compromised deployment credential

1. Revoke/rotate the exposed credential immediately (GitHub token /
   webhook URL / S3 key / SSH key — each has a rotation entry).
2. Assume attacker deployment capability: audit recent deployments
   (Dokploy history) against the D-121 deploy-event ledger; any
   deployment without a matching ledger event is hostile.
3. Verify artifact identity of the running stack (digest/definition
   hash) against the last verified record.
4. Rotate all credentials in the same trust boundary (webhook URLs
   are secrets — treat exposure as credential loss, D-045).
5. Evidence + incident record per SECURITY.md conventions; owner
   notification with a full timeline.

## 6. Restoration evidence requirements (uniform)

For every restore: isolated target, timestamped log, backup artifact
identifier, tool versions, integrity check outputs (transactional +
decision-ledger chain + probes), and an explicit
PASS/FAIL/STOP verdict. A restore without this pack is not a restore.

## 7. Control-plane independence (mandatory design property)

The project's data never depends on Dokploy's survival: canonical
data, ledger, media, and their recovery paths are exercised by the
project's own drills against D-125 archives regardless of any
deployment tool. See `dokploy-exit-plan.md`.
