"""Stage C acceptance & health probes (rehearsal stack) — operator
command, D-141 ladder.

Runs health and connectivity probes against ALL FIVE staging planes on
the sanctioned engine-local REHEARSAL stack (the only stack that exists
at Stage C — the staging VPS itself is provisioned later under its own
G-gates; `validate_vps_*` are its host probes). Read-only except the
self-deleting MinIO contract probe (put → verify → delete → verify 404:
zero residue). Fail closed: exit 0 all green · 1 findings · 2 cannot
assess (stack down, wrong stack, or probe-transport failure).

Probes (names follow the repository audit-log conventions —
`qa.launch_attestation.v1` probe records via
`canonical.obs_health.ProbeRegistry`):

  stack_identity        — the running compose project IS the sanctioned
                          engine-local rehearsal stack (the synthetic-
                          data-only guarantee at the boundary: these
                          probes never touch a staging/production host)
  canonical_pg          — connectivity via the sanctioned container-psql
                          transport (seed_registry.container_psql)
  canonical_schema      — schema readiness, mirroring apply_schema.py's
                          idempotency verification READ-ONLY: the five
                          core schemas exist (canonical, events,
                          provenance, registry, seed)
  canonical_event_store — read-only counts over events.event_record and
                          registry.mapping_entry (no writes, no seeds)
  mysql_woo             — MySQL/WooCommerce responsiveness via the
                          manifest's own healthcheck semantics
                          (mysqladmin ping inside the container)
  wordpress_rest        — WordPress/Woo REST surface answers on the
                          loopback-bound gateway port
  media_store           — MinIO bucket readiness through the
                          MediaStoreContract interface (put/get/head/
                          delete round-trip with deterministic key,
                          ZERO RESIDUE: delete verified by a 404 head)
  n8n_tunnel            — n8n healthz reachable on the loopback tunnel
                          AND not publicly exposed (the port mapping
                          must be loopback-bound; any 0.0.0.0 binding
                          is a FAIL)
  decision_ledger       — decision_ledger_drill --consistency-only:
                          the un-mutated decided-vs-happened check
                          (verify_chain + reconciliation reads only)

  synthetic_data_guard  — final sweep: no probe evidence carries
                          production-signature markers or credential-
                          shaped values (D-045/D-124) — probe details
                          are verdicts, never payloads.

Secrets: only the throwaway engine-local values transit (inside
container exec); they are NEVER echoed into evidence. No AI
credentials exist to leak (G-B4).

Usage:
  python3 local/scripts/stage_c_acceptance.py [--json] [--media-prefix P]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

SCHEMA = "stage_c.acceptance_run.v1"

SANCTIONED_CONTAINERS = {
    "engine-local-postgres", "engine-local-mysql",
    "engine-local-wordpress", "engine-local-minio", "engine-local-n8n",
}
LOOPBACK_MARKERS = ("127.0.0.1", "::1")
FORBIDDEN_SIGNATURES = re.compile(
    r"(APP_ENV=production|engine-prod|sk-[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)")

COMPOSE = ["docker", "compose", "-f", "local/infra/docker-compose.yml"]


# --------------------------------------------------------------------------
# real transports (all injectable in the battery)
# --------------------------------------------------------------------------
def stack_containers() -> List[str]:
    """Running+healthy container names of the compose project."""
    try:
        proc = subprocess.run(
            COMPOSE + ["ps", "--format", "{{.Name}} {{.State}}"],
            capture_output=True, text=True, timeout=30,
            cwd=str(ROOT))
    except (OSError, subprocess.TimeoutExpired):
        return []
    names = []
    for line in proc.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == "running":
            names.append(parts[0])
    return names


def container_psql(sql: str) -> str:
    from seed_registry import container_psql as _psql
    return _psql(sql)


def mysql_ping() -> tuple:
    cmd = (COMPOSE + ["exec", "-T", "woodb", "sh", "-c",
                      'mysqladmin ping -h 127.0.0.1 -uroot '
                      '-p"$MYSQL_ROOT_PASSWORD"'])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                          cwd=str(ROOT))
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def http_status(url: str, timeout: int = 8) -> int:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code  # a 4xx from the server still proves reachability


def port_binding_published() -> Dict[str, str]:
    """{service: raw `docker compose port` output} for exposure checks."""
    out: Dict[str, str] = {}
    for svc, port in (("n8n", "5678"), ("wordpress", "80"),
                      ("media", "9000")):
        proc = subprocess.run(
            COMPOSE + ["port", svc, port], capture_output=True, text=True,
            timeout=15, cwd=str(ROOT))
        out[svc] = proc.stdout.strip()
    return out


def media_roundtrip(prefix: str) -> Dict:
    """MediaStoreContract round-trip against the local MinIO. Zero
    residue: the probe object is deleted and the delete verified."""
    from services.media_store import MediaStore
    from datetime import datetime, timezone
    import hashlib
    import hmac

    endpoint = "http://127.0.0.1:19000"
    bucket = "engine-local-media"
    access = os.environ.get("LOCAL_MINIO_USER", "engine-local-media")
    secret = os.environ.get("LOCAL_MINIO_PASSWORD", "engine-local-media-only")

    class S3EnvMediaStore(MediaStore):
        """Minimal SigV4 MediaStore over the engine-local MinIO —
        stdlib-only, staging-equivalent of the D-056 surface."""

        def __init__(self, bucket: str):
            self.bucket = bucket
            self.base = f"{endpoint}/{bucket}"

        def _sign(self, payload: bytes, key: str, method: str,
                  ctype: str = "application/octet-stream") -> Dict:
            # SigV4 requires the request time within MinIO's skew window
            # — real UTC now (object-key determinism comes from uuid5,
            # not from the signature)
            now = datetime.now(timezone.utc)
            t = now.strftime("%Y%m%dT%H%M%SZ")
            kdate = now.strftime("%Y%m%d")
            scope = f"{kdate}/us-east-1/s3/aws4_request"
            canonical = (f"{method}\n/{self.bucket}/{key}\n\n"
                         f"host:127.0.0.1:19000\nx-amz-content-sha256:"
                         f"{hashlib.sha256(payload).hexdigest()}\n"
                         f"x-amz-date:{t}\n\nhost;x-amz-content-sha256;"
                         f"x-amz-date\n"
                         f"{hashlib.sha256(payload).hexdigest()}")
            sts = (f"AWS4-HMAC-SHA256\n{t}\n{scope}\n"
                   f"{hashlib.sha256(canonical.encode()).hexdigest()}")
            k = hmac.new(f"AWS4{secret}".encode(), kdate.encode(),
                         hashlib.sha256).digest()
            k = hmac.new(k, b"us-east-1", hashlib.sha256).digest()
            k = hmac.new(k, b"s3", hashlib.sha256).digest()
            k = hmac.new(k, b"aws4_request", hashlib.sha256).digest()
            sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
            return {
                "Authorization": (f"AWS4-HMAC-SHA256 Credential="
                                  f"{access}/{scope}, SignedHeaders="
                                  f"host;x-amz-content-sha256;x-amz-date, "
                                  f"Signature={sig}"),
                "x-amz-date": t, "x-amz-content-sha256":
                    hashlib.sha256(payload).hexdigest(),
                "Content-Type": ctype,
            }

        def _req(self, key: str, method: str, data: bytes = b"",
                 ctype: str = "application/octet-stream") -> tuple:
            req = urllib.request.Request(
                f"{self.base}/{key}", data=data or None, method=method)
            for h, v in self._sign(data, key, method, ctype).items():
                req.add_header(h, v)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()

        def put(self, data: bytes, content_type: str,
                metadata: Dict = None) -> str:
            key = f"{prefix}/{uuid.uuid5(uuid.NAMESPACE_URL, 'stage-c-acceptance')}"
            rc, body = self._req(key, "PUT", data, content_type)
            if rc not in (200, 201):
                raise RuntimeError(f"media put rc={rc}: {body[:200]!r}")
            return key

        def get(self, object_key: str) -> bytes:
            rc, body = self._req(object_key, "GET")
            if rc != 200:
                raise KeyError(f"media get rc={rc}")
            return body

        def delete(self, object_key: str) -> bool:
            rc, _ = self._req(object_key, "DELETE")
            return rc in (200, 204)

        def head(self, object_key: str) -> dict:
            rc, _ = self._req(object_key, "HEAD")
            if rc == 404:
                return {"exists": False}
            if rc != 200:
                raise RuntimeError(f"media head rc={rc}")
            return {"exists": True}

        def list(self) -> list:
            return []

    store = S3EnvMediaStore(bucket)

    # Ensure the bucket exists; if the probe created it, the probe
    # removes it again (zero residue on a fresh rehearsal stack).
    rc, _ = store._req("", "HEAD")
    bucket_created = False
    if rc == 404:
        rc, body = store._req("", "PUT")
        if rc != 200:
            raise RuntimeError(f"bucket create rc={rc}: {body[:160]!r}")
        bucket_created = True
    elif rc != 200:
        raise RuntimeError(f"bucket head rc={rc}")

    try:
        blob = b"stage-c-acceptance-probe"
        key = store.put(blob, "application/octet-stream")
        got = store.get(key)
        ok_head = store.head(key).get("exists") is True
        deleted = store.delete(key)
        gone = store.head(key).get("exists") is False
    finally:
        if bucket_created:
            store._req("", "DELETE")

    ok = bool(got == blob and ok_head and deleted and gone)
    residue_note = ("bucket created+removed by probe, "
                    if bucket_created else "")
    return {"ok": ok,
            "detail": (f"contract round-trip ok, zero residue "
                       f"({residue_note}put/get/head/delete/delete-404)")
            if ok else f"round-trip incomplete: get={got == blob} "
                       f"head={ok_head} del={deleted} gone={gone}"}


def ledger_consistency() -> Dict:
    from decision_ledger_drill import consistency_decided_vs_happened
    from canonical.admin_engine import ControlPlaneEngine, default_vault
    from canonical.notion_ingest import PgEventStore
    engine = ControlPlaneEngine(PgEventStore(), default_vault())
    return consistency_decided_vs_happened(engine)


# --------------------------------------------------------------------------
# probe core (pure-ish; every transport injectable)
# --------------------------------------------------------------------------
def run_probes(*, containers_fn: Callable[[], List[str]] = stack_containers,
               psql_fn: Callable[[str], str] = container_psql,
               mysql_fn: Callable[[], tuple] = mysql_ping,
               http_fn: Callable[[str], int] = http_status,
               port_fn: Callable[[], Dict[str, str]] = port_binding_published,
               media_fn: Optional[Callable[[str], Dict]] = None,
               ledger_fn: Optional[Callable[[], Dict]] = None,
               media_prefix: str = "stage-c-acceptance") -> Dict:
    probes: List[Dict] = []

    def record(name: str, ok: Optional[bool], detail: str) -> None:
        probes.append({"name": name,
                       "verdict": ("PASS" if ok else "FAIL")
                       if ok is not None else "CANNOT_ASSESS",
                       "detail": detail, "checked_at_logical": ""})

    def fail_stop(name: str, detail: str) -> Dict:
        record(name, None, detail)
        return _finish(probes)

    # -- boundary guard ---------------------------------------------------
    running = containers_fn()
    missing = SANCTIONED_CONTAINERS - set(running)
    if missing:
        return fail_stop(
            "stack_identity",
            f"sanctioned engine-local rehearsal stack not fully running "
            f"(missing {sorted(missing)}) — refusing to probe anything "
            "else (synthetic-data-only guarantee, fail closed)")
    record("stack_identity", True,
           "engine-local rehearsal stack 5/5 running — sanctioned "
           "synthetic-only probe surface")

    # -- canonical PostgreSQL ---------------------------------------------
    try:
        psql_fn("SELECT 1")
        record("canonical_pg", True,
               "connectivity via sanctioned container-psql transport")
    except Exception as e:  # noqa: BLE001 — probe transport failure
        return fail_stop("canonical_pg",
                         f"psql transport failed: {type(e).__name__}")

    try:
        schemas = psql_fn(
            "SELECT string_agg(nspname, ',' ORDER BY nspname) "
            "FROM pg_namespace WHERE nspname IN ('seed','canonical',"
            "'registry','events','provenance');")
        schema_ok = schemas == "canonical,events,provenance,registry,seed"
        record("canonical_schema", schema_ok,
               f"five core schemas present (apply_schema idempotency "
               f"mirror): {schemas}" if schema_ok
               else f"schemas present = {schemas!r} — apply the schema "
                    "(local/scripts/apply_schema.py)")
    except Exception as e:  # noqa: BLE001
        return fail_stop("canonical_schema",
                         f"schema probe failed: {type(e).__name__}")

    try:
        events = psql_fn("SELECT COUNT(*) FROM events.event_record;")
        mappings = psql_fn("SELECT COUNT(*) FROM registry.mapping_entry;")
        record("canonical_event_store", True,
               f"read-only counts: events.event_record={events} "
               f"registry.mapping_entry={mappings} (zero writes)")
    except Exception as e:  # noqa: BLE001
        return fail_stop("canonical_event_store",
                         f"event-store probe failed: {type(e).__name__}")

    # -- MySQL / WooCommerce ----------------------------------------------
    rc, out = mysql_fn()
    record("mysql_woo", rc == 0 and "alive" in out.lower(),
           "mysqld responsive (mysqladmin ping, manifest healthcheck "
           "semantics)" if rc == 0 else f"mysqladmin rc={rc}: {out[:120]}")

    # -- WordPress / Woo REST ---------------------------------------------
    try:
        code = http_fn("http://127.0.0.1:18080/wp-login.php")
        record("wordpress_rest", code in (200, 302),
               f"REST surface answers (loopback gateway, HTTP {code})")
    except Exception as e:  # noqa: BLE001
        record("wordpress_rest", False,
               f"gateway probe failed: {type(e).__name__}")

    # -- Media store (MediaStoreContract) ---------------------------------
    try:
        if media_fn is None:
            media_fn = media_roundtrip
        media = media_fn(media_prefix)
        record("media_store", media.get("ok"), media.get("detail", ""))
    except Exception as e:  # noqa: BLE001
        record("media_store", False,
               f"MediaStoreContract probe failed: "
               f"{type(e).__name__}: {str(e)[:160]}")

    # -- n8n tunnel-only ---------------------------------------------------
    try:
        code = http_fn("http://127.0.0.1:15678/healthz")
        tunnel_ok = code == 200
        bindings = port_fn().get("n8n", "")
        loopback_only = bool(bindings) and any(
            m in bindings for m in LOOPBACK_MARKERS) \
            and "0.0.0.0" not in bindings
        record("n8n_tunnel", tunnel_ok and loopback_only,
               f"healthz HTTP {code} over the loopback tunnel; binding "
               f"{bindings or 'unresolved'}"
               + ("" if loopback_only else " — PUBLIC EXPOSURE REFUSED"))
    except Exception as e:  # noqa: BLE001
        record("n8n_tunnel", False,
               f"n8n probe failed: {type(e).__name__}")

    # -- decision ledger (un-mutated consistency-only) ---------------------
    try:
        if ledger_fn is None:
            ledger_fn = ledger_consistency
        res = ledger_fn()
        record("decision_ledger", bool(res.get("ok")),
               res.get("reason")
               or f"decided-vs-happened consistent "
                  f"({res.get('decisions_checked', '?')} decisions)")
    except Exception as e:  # noqa: BLE001
        record("decision_ledger", False,
               f"ledger consistency probe failed: {type(e).__name__}")

    # -- synthetic-data guard (final sweep over evidence) -------------------
    leaked = [p["name"] for p in probes
              if FORBIDDEN_SIGNATURES.search(p["detail"])]
    record("synthetic_data_guard", not leaked,
           "no production signatures or credential-shaped values in "
           "probe evidence (D-045/D-124)" if not leaked
           else f"PRODUCTION/SECRET SIGNATURES in evidence of: {leaked}")

    return _finish(probes)


def _finish(probes: List[Dict]) -> Dict:
    bad = [p["name"] for p in probes if p["verdict"] != "PASS"]
    return {"schema_version": SCHEMA,
            "compatible_with": "qa.launch_attestation.v1",
            "ok": not bad,
            "verdict": "ACCEPTED" if not bad else
                       ("CANNOT_ASSESS" if any(
                           p["verdict"] == "CANNOT_ASSESS"
                           and p["name"] in ("stack_identity",
                                             "canonical_pg",
                                             "canonical_schema")
                           for p in probes) else "FINDINGS"),
            "probes": probes,
            "failing": bad}


def render(report: Dict) -> str:
    lines = ["=== STAGE C ACCEPTANCE & HEALTH PROBES "
             "(engine-local rehearsal stack) ==="]
    for p in report["probes"]:
        mark = {"PASS": "ok  ", "FAIL": "FAIL",
                "CANNOT_ASSESS": "ENV "}.get(p["verdict"], "????")
        lines.append(f"  [{mark}] {p['name']:<22} {p['detail']}")
    lines.append(f"verdict {report['verdict']} — "
                 f"{len(report['probes']) - len(report['failing'])}/"
                 f"{len(report['probes'])} green")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage C acceptance & health probes (fail closed, "
                    "synthetic data only).")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--media-prefix", default="stage-c-acceptance",
                    help="object-key prefix for the self-deleting "
                         "media contract probe")
    args = ap.parse_args(argv)

    report = run_probes(media_prefix=args.media_prefix)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    if report["verdict"] == "CANNOT_ASSESS":
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
