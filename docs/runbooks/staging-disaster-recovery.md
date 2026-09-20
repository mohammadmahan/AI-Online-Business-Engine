# Runbook: Staging Disaster Recovery & Backup (Stage D — PLANNED)

- Work package: **Dokploy Deployment Integration** (D-141, Approved).
- Status: **PLANNED hands-on procedure.** No staging host exists; no
  backup has ever been taken or restored. This runbook operationalizes
  `docs/deployment/staging-volume-backup-policy.md` (schedules/
  retention, G-B3) and the scenario catalog of
  `docs/runbooks/dokploy-disaster-recovery.md` into per-store backup
  and restoration DRILL procedures with RPO/RTO verification.
  Execution requires the Stage C/D owner gates (backup credentials
  connected, host exists). Until then this document is rehearsal
  material only.
- Non-negotiable boundaries: backups **supplement, never replace**
  D-125 verified-freeze archives, both DR drills, and EV-BAC-001
  evidence; a backup upload is **never** restoration evidence; the
  decision ledger (`admin.control_audit`) is append-only — **never
  delete, truncate, or compact it** as part of any restore; restore
  preconditions follow the deployment layer's official documentation
  (destination volume must not exist, consuming containers stopped).

## 0. When this runs

1. After the first successful staging deploy (Stage C complete).
2. Periodically per the policy schedules (maintenance windows).
3. After ANY restore, migration, or host change (re-baseline).
4. Before Stage E (production-readiness evaluation) — DR evidence
   feeds the D-137/D-138 launch gate.

## 1. Automated backup procedures (per store)

All commands run on the staging host (or via SSH) inside the compose
project. Schedules/retention are enforced by the deployment layer's
backup feature where available (named volumes → Volume Backups with
S3 destinations per policy) — the commands below are the
**manual/equivalent path** and the drill primitives.

### 1.1 PostgreSQL (`canonical_data` — the canonical store, D-027)

```bash
# Consistent logical dump (preferred) — does NOT require stopping PG.
docker compose -f compose.staging.yml exec -T canonical-db \
  pg_dump -U engine_staging -d business_engine_staging -Fc \
  > backups/pgsql_$(date -u +%Y%m%dT%H%M%SZ).dump

# Physical volume copy (secondary) — REQUIRES containers stopped.
docker compose -f compose.staging.yml stop canonical-db
docker run --rm -v <project>_canonical_data:/data -v "$PWD/backups:/out" \
  alpine tar czf /out/canonical_data_vol.tgz -C /data .
docker compose -f compose.staging.yml start canonical-db
```

Post-backup integrity gate (mandatory before declaring the backup
valid): restore the dump into a THROWAWAY database and verify.

### 1.2 MySQL (`woo_data_db` — Woo projection)

```bash
docker compose -f compose.staging.yml exec -T woodb \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction wordpress_staging' \
  > backups/mysql_$(date -u +%Y%m%dT%H%M%SZ).sql
```

The projection is rebuildable from canonical; backups exist for
continuity, not truth — label accordingly.

### 1.3 MinIO object storage (`media_data`)

```bash
docker run --rm --network <project>_data -v "$PWD/backups:/out" \
  minio/mc sh -c "mc alias set st http://media:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD && mc mirror st/engine-staging-media /out/media_$(date -u +%Y%m%dT%H%M%SZ)"
```

Media is NOT reconstructable from canonical — this store's off-host
copy is mandatory (policy §2).

### 1.4 n8n workflows & state (`n8n_data`)

```bash
docker run --rm -v <project>_n8n_data:/data -v "$PWD/backups:/out" \
  alpine tar czf /out/n8n_data_vol.tgz -C /data .
```

Workflows are version-controlled where possible; the volume carries
runtime state and credential references (values live in the staging
secret store — the archive must be treated as SENSITIVE and stored
encrypted off-host).

### 1.5 Off-host transfer & failure monitoring

Every archive goes to the owner-approved S3 destination with the
separate minimum-privilege backup credentials (G6); server-side
encryption on. Backup-job failures alert via the Phase 14 notification
model — a silently failing schedule is treated as a DR incident.

## 2. Restoration drill (Stage D acceptance — step by step)

Execute in a MAINTENANCE WINDOW. The drill restores into the real
staging volumes (they hold synthetic data only); production restores
follow the same steps with change-control.

1. **Pre-flight:** capture current fold/state checksums where
   applicable; announce window; verify backup artifact list + hashes.
2. **Stop consumers:** `docker compose -f compose.staging.yml stop`
   (named-volume restores require the destination volume ABSENT and
   containers stopped — official documentation precondition).
3. **Destroy synthetic volumes** (staging drill only):
   `docker compose -f compose.staging.yml down -v` — record what was
   destroyed (list + counts).
4. **Restore each store** from the verified off-host archives into
   freshly created named volumes (or via the deployment layer's
   restore flow — note the `{appName}_{volumeName}` naming it
   produces).
5. **Schema apply:** `python3 scripts/apply_schema.py` (idempotent)
   against the restored canonical DB.
6. **Integrity verification (the actual acceptance):**
   - Decision-ledger chain: `python3 local/scripts/decision_ledger_drill.py --consistency-only` → must verify.
   - Fold equality vs pre-disaster snapshot where captured.
   - `python3 local/scripts/validate_staging_health.py --live …` →
     all probes OK, isolation invariants hold (exit 0).
7. **Evidence record (uniform, per the scenario runbook §6):**
   timestamped log with artifact hashes, restore duration (→ RTO),
   data-age at restore (→ RPO), verification outputs. Attach to
   `qa.health_report.v1` history.
8. A drill WITHOUT step 7 evidence is a FAILED drill.

## 3. RPO / RTO verification checklist

| Metric | Target (owner-approved pending, policy §2) | How measured in the drill |
|---|---|---|
| RPO canonical | ≤ 6 h | newest restorable archive age at disaster time |
| RPO media | ≤ 24 h | same, for media archives |
| RTO canonical | ≤ 2 h | restore + schema apply + ledger/fold verification |
| RTO full stack | ≤ 4 h | all volumes restored + health exit 0 |

- [ ] Measured RPO ≤ target (per store)
- [ ] Measured RTO ≤ target (canonical + full stack)
- [ ] Restoration verified by INTEGRITY checks, not dashboard status
- [ ] Off-host archive provenance recorded (bucket, object key, hash)
- [ ] Post-restore staging serves the synthetic dataset correctly

## 4. Stop conditions

Missing/unverifiable archive · restore precondition impossible (volume
exists, consumers won't stop) · integrity verification fails · RPO/RTO
breach without owner-approved exception · any step that would modify
the decision ledger destructively. **Stop and report.**
