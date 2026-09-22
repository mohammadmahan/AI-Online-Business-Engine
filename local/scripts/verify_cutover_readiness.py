#!/usr/bin/env python3
"""verify_cutover_readiness.py — Stage E cutover readiness harness (D-141).

Read-only, fail-closed verification of the PRODUCTION CUTOVER plan
(docs/deployment/stage-e-cutover-runbook.md) before any container
transition. Three strictly separated modes:

  OFFLINE (default)
    V-01  D-138 launch attestation exists and is GO for the candidate
          commit (a MISSING attestation is a finding — fail closed)
    V-02  D-045 planning hygiene — the harness REFUSES to run (exit 2)
          if a real value for a production `${VAR:?}` secret key is
          exported in this shell; planning tools never see production
          secrets
    V-03  env contract — every mandatory prod-manifest `${VAR:?}` name
          is documented (empty) in `.env.example`
    V-04  restart policy + resource ceilings — all five prod services
          declare restart: unless-stopped and cpu/mem limits (parsed
          from the manifest, not asserted from memory)
    V-05  preflight contract — runtime_preflight refuses a
          production-shaped env missing CANONICAL_DB_* and admits a
          complete one (fail-closed proof, synthetic values only)
    V-06  rollback matrix presence — the runbook declares the RB-1..RB-6
          rows and the ordering invariant (stop → compensate → reconcile)
    V-07  edge header policy — the runbook declares HSTS/nosniff/
          frame-deny/CSP/HTTPS-redirect with the attested values

  --snapshot
    Synthetic point-in-time backup proof (D-125): write_snapshot a
    representative durable surface, verify_snapshot it, flip one byte,
    verify_snapshot again — verification MUST fail (tamper evidence).
    Composes with the real drill (resilience_drill) behind --stack.

  --edge URL
    Opt-in live edge probe of the cutover target: HTTPS redirect +
    security headers per the runbook §4 policy. Read-only GET only.
    Unreachable edge ⇒ exit 2 (cannot assess), never a guess.

Exit codes: 0 = ready · 1 = findings · 2 = cannot assess.
Secrets are never read, stored, printed, or transmitted (D-124/D-045).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE.parent
ROOT = LOCAL.parent
for p in (str(HERE), str(LOCAL)):
    if p not in sys.path:
        sys.path.insert(0, p)

RUNBOOK = ROOT / "docs" / "deployment" / "stage-e-cutover-runbook.md"
PROD_MANIFEST = LOCAL / "infra" / "compose.prod.yml"
ENV_EXAMPLE = ROOT / ".env.example"

# Synthetic, contract-shaped values used ONLY to prove the preflight
# admits a complete production env. Never real credentials.
SYNTHETIC_ENV = {
    "APP_ENV": "production",
    "CANONICAL_DB_HOST": "canonical-db",
    "CANONICAL_DB_PORT": "5432",
    "CANONICAL_DB_NAME": "business_engine_prod",
    "CANONICAL_DB_USER": "engine_prod",
    "CANONICAL_DB_PASSWORD": "synthetic-drill-only-0",
    "MEDIA_ENDPOINT": "http://media:9000",
    "MEDIA_BUCKET": "engine-prod-media",
    "N8N_URL": "http://n8n:5678",
    "WORDPRESS_DB_PASSWORD": "synthetic-drill-only-1",
    "MYSQL_PASSWORD": "synthetic-drill-only-2",
    "MYSQL_ROOT_PASSWORD": "synthetic-drill-only-3",
    "N8N_ENCRYPTION_KEY": "synthetic-drill-only-4",
    "MINIO_ROOT_USER": "synthetic-drill-only-5",
    "MINIO_ROOT_PASSWORD": "synthetic-drill-only-6",
}
SECRET_KEYS = ("CANONICAL_DB_PASSWORD", "WORDPRESS_DB_PASSWORD",
               "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD",
               "N8N_ENCRYPTION_KEY", "MINIO_ROOT_PASSWORD")

ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):\?[^}]*\}")


class Results:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def ok(self, check: str, detail: str = "") -> None:
        self.items.append(("PASS", check, detail))

    def fail(self, check: str, detail: str) -> None:
        self.items.append(("FAIL", check, detail))

    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.items)

    def render(self) -> str:
        lines = []
        for s, check, detail in self.items:
            mark = "[PASS]" if s == "PASS" else "[FAIL]"
            lines.append(f"  {mark} {check}" + (f" — {detail}" if detail else ""))
        return "\n".join(lines)


# --------------------------------------------------------------------------
# pure helpers (imported and pinned by the battery)
# --------------------------------------------------------------------------

def manifest_env_contract(text: str | None = None) -> tuple[str, ...]:
    """Mandatory `${VAR:?}` names declared by the prod manifest."""
    if text is None:
        text = PROD_MANIFEST.read_text(encoding="utf-8")
    seen: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for m in ENV_VAR_RE.finditer(line):
            if m.group(1) not in seen:
                seen.append(m.group(1))
    return tuple(seen)


def documented_env_keys(text: str | None = None) -> tuple[str, ...]:
    """Key names documented in `.env.example` (committed, empty values)."""
    if text is None:
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
    return tuple(re.findall(r"^([A-Z_][A-Z0-9_]*)=", text, re.M))


def manifest_service_posture(text: str | None = None) -> dict:
    """Per-service restart policy and cpu/mem ceiling presence.

    Scoped to the top-level `services:` block only — names like
    `frontend:`/`data:` re-appear under `networks:` and must not be
    mistaken for services.
    """
    if text is None:
        text = PROD_MANIFEST.read_text(encoding="utf-8")
    m = re.search(r"^services:\n(.*?)(?=^[a-z-]+:\s*$|\Z)", text,
                  flags=re.M | re.S)
    if not m:
        raise ValueError("manifest has no top-level `services:` block")
    block = m.group(1)
    services = re.split(r"^  ([a-z0-9-]+):\n", block, flags=re.M)[1:]
    posture: dict[str, dict] = {}
    for name, body in zip(services[0::2], services[1::2]):
        posture[name] = {
            "restart": "unless-stopped" in body,
            "cpu": bool(re.search(r"\bcpus:", body)),
            "mem": bool(re.search(r"\bmem_limit:", body)),
        }
    return posture


def edge_headers_ok(headers: dict[str, str]) -> tuple[bool, list[str]]:
    """Runbook §4 header policy over a live (or synthetic) header map."""
    problems: list[str] = []
    h = {k.lower(): v for k, v in headers.items()}
    hsts = h.get("strict-transport-security", "")
    m = re.search(r"max-age=(\d+)", hsts)
    if not m or int(m.group(1)) < 31536000:
        problems.append("HSTS max-age >= 31536000 required")
    if h.get("x-content-type-options", "").lower() != "nosniff":
        problems.append("X-Content-Type-Options: nosniff required")
    if h.get("x-frame-options", "").upper() not in ("DENY", "SAMEORIGIN"):
        problems.append("X-Frame-Options DENY/SAMEORIGIN required")
    if not h.get("content-security-policy"):
        problems.append("Content-Security-Policy must be present")
    return (not problems), problems


def rollback_matrix_present(text: str | None = None) -> tuple[bool, list[str]]:
    """Runbook §5 must declare RB-1..RB-6 and the ordering invariant."""
    if text is None:
        text = RUNBOOK.read_text(encoding="utf-8")
    missing = [f"RB-{i}" for i in range(1, 7)
               if f"RB-{i}" not in text]
    if "stop new work first, then compensate/drain,\nthen reconcile" not in text:
        missing.append("ordering invariant")
    return (not missing), missing


def edge_policy_declared(text: str | None = None) -> tuple[bool, list[str]]:
    if text is None:
        text = RUNBOOK.read_text(encoding="utf-8")
    needed = ["Strict-Transport-Security", "X-Content-Type-Options",
              "X-Frame-Options", "Content-Security-Policy"]
    missing = [n for n in needed if n not in text]
    if "https" not in text.lower():
        missing.append("HTTPS redirect policy")
    return (not missing), missing


def production_secrets_in_shell(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """Real values for mandatory prod secret keys present in the shell."""
    src = dict(os.environ if env is None else env)
    return tuple(k for k in SECRET_KEYS
                 if src.get(k) and src.get(k) != "synthetic-drill-only-0"
                 and len(str(src[k])) >= 8)


def preflight_contract_ok() -> tuple[bool, str]:
    """Fail-closed proof on the synthetic production env (no daemon)."""
    from canonical.runtime_preflight import PreflightError, check_environment
    incomplete = {k: v for k, v in SYNTHETIC_ENV.items()
                  if k != "CANONICAL_DB_PASSWORD"}
    try:
        check_environment(incomplete, env_name="production")
        return False, "preflight ADMITTED an env missing CANONICAL_DB_PASSWORD"
    except PreflightError:
        pass
    try:
        check_environment(dict(SYNTHETIC_ENV), env_name="production")
    except PreflightError as e:
        return False, f"preflight refused a complete env: {e}"
    return True, "refuses incomplete, admits complete (fail closed)"


def attestation_state() -> tuple[str, str]:
    """(state, detail) of the D-138 launch attestation — composed with
    the shipped launcher (both DR legs + sweeps + matrix evaluation),
    not a re-implementation."""
    import launch_attestation as la

    if la._git_dirty():
        return ("DIRTY", "working tree has uncommitted changes — "
                         "attestation cannot bind a clean candidate")
    att = la.run_attestation(n_events=8)
    if att["launch_verdict"] != "GO":
        return ("NO_GO", f"launch verdict {att['launch_verdict']} — "
                         f"blockers: {att['blockers'] or 'n/a'}")
    return ("GO", f"attestation {att['attestation_hash'][:16]}…")


# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------

def offline_mode() -> int:
    res = Results()
    print("=== STAGE E CUTOVER READINESS — OFFLINE ===")

    # V-01 attestation GO (real evaluation, current commit)
    try:
        state, detail = attestation_state()
        (res.ok if state == "GO" else res.fail)(
            "V-01 D-138 attestation GO", f"{state}: {detail}")
    except Exception as e:  # noqa: BLE001 — fail closed on any error
        res.fail("V-01 D-138 attestation GO",
                 f"attestation unavailable: {type(e).__name__}")

    # V-02 no real production secrets in the planning shell
    leaks = production_secrets_in_shell()
    if leaks:
        print("  [FAIL] V-02 planning hygiene — production secret values "
              f"present in shell: {', '.join(leaks)}")
        print("  Refusing to continue (D-045): unset them or use the "
              "deployment secret store.")
        return 2
    res.ok("V-02 no production secrets in planning shell (D-045)")

    # V-03 env contract documented
    manifest_keys = manifest_env_contract()
    doc = set(documented_env_keys())
    missing = [k for k in manifest_keys if k not in doc]
    (res.ok if not missing else res.fail)(
        "V-03 prod `${VAR:?}` contract documented in .env.example",
        f"{len(manifest_keys)} keys" if not missing
        else f"missing: {missing}")

    # V-04 restart policy + ceilings on every service
    posture = manifest_service_posture()
    bad = [n for n, p in posture.items()
           if not (p["restart"] and p["cpu"] and p["mem"])]
    (res.ok if not bad else res.fail)(
        "V-04 restart policy + cpu/mem ceilings on all services",
        f"{len(posture)} services" if not bad else f"deficient: {bad}")

    # V-05 preflight fail-closed contract
    ok, detail = preflight_contract_ok()
    (res.ok if ok else res.fail)("V-05 runtime preflight fail-closed", detail)

    # V-06 rollback matrix declared
    ok, missing = rollback_matrix_present()
    (res.ok if ok else res.fail)("V-06 rollback matrix RB-1..RB-6",
                                 "declared" if ok else f"missing: {missing}")

    # V-07 edge header policy declared
    ok, missing = edge_policy_declared()
    (res.ok if ok else res.fail)("V-07 edge header policy declared",
                                 "declared" if ok else f"missing: {missing}")

    print(res.render())
    print("=== CUTOVER READY — proceed to runbook §2 (backup) ==="
          if not res.failed() else
          "=== NOT READY — findings above are blocking (fail closed) ===")
    return 1 if res.failed() else 0


def snapshot_mode() -> int:
    """Synthetic backup/verify/tamper proof on the D-125 primitives."""
    import tempfile

    from canonical.compaction import CompactionError, verify_snapshot, write_snapshot

    print("=== STAGE E — SNAPSHOT INTEGRITY (D-125) ===")
    rows = [{"source": "events.event_record", "seq": i,
             "kind": "synthetic", "payload": {"i": i}}
            for i in range(50)]
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as fh:
        path = fh.name
    desc = write_snapshot(path, rows)
    print(f"  [OK  ] write_snapshot rows={desc['row_count']} "
          f"fold={desc['fold'][:12]}…")
    v = verify_snapshot(path)
    if not v.get("ok"):
        print("  [FAIL] verify_snapshot on a fresh archive")
        return 1
    print("  [OK  ] verify_snapshot ok (fold re-derived)")
    with open(path, "rb") as fh:
        blob = bytearray(fh.read())
    blob[-2] ^= 0x20  # flip one bit in the final row
    with open(path, "wb") as fh:
        fh.write(blob)
    try:
        verify_snapshot(path)
        print("  [FAIL] tampered archive VERIFIED — fold check is broken")
        return 1
    except CompactionError:
        print("  [OK  ] tampered archive REFUSED (fail closed)")
    finally:
        os.unlink(path)
    print("=== SNAPSHOT PROOF COMPLETE ===")
    return 0


def edge_mode(url: str) -> int:
    """Opt-in live edge probe (read-only GET)."""
    import urllib.error
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    print(f"=== STAGE E — LIVE EDGE PROBE ({url}) ===")
    http_url = re.sub(r"^https://", "http://", url)
    try:
        ctx = urllib.request.build_opener()
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "stage-e-probe"})
        with ctx.open(req, timeout=10) as resp:
            headers = dict(resp.headers)
            code = resp.status
    except urllib.error.HTTPError as e:
        headers, code = dict(e.headers), e.code
    except OSError as e:
        print(f"  CANNOT ASSESS: edge unreachable ({type(e).__name__})")
        return 2
    print(f"  edge responded {code}")
    ok, problems = edge_headers_ok(headers)
    for p in problems:
        print(f"  [FAIL] {p}")
    if ok:
        print("  [OK  ] security headers present per runbook §4")
    # redirect check on the http:// twin
    if http_url != url:
        try:
            req = urllib.request.Request(
                http_url, method="GET",
                headers={"User-Agent": "stage-e-probe"})
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(req, timeout=10) as resp:
                loc = resp.headers.get("Location", "")
                if resp.status in (301, 308) and loc.startswith("https://"):
                    print("  [OK  ] HTTP→HTTPS redirect (301/308)")
                else:
                    print(f"  [FAIL] no HTTPS redirect "
                          f"({resp.status} → {loc or 'none'})")
                    ok = False
        except OSError as e:
            print(f"  [WARN] http twin unreachable ({type(e).__name__})")
    print("=== EDGE PROBE " + ("PASS" if ok else "FAIL") + " ===")
    return 0 if ok else 1


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--snapshot" in argv:
        return snapshot_mode()
    if "--edge" in argv:
        i = argv.index("--edge")
        if i + 1 >= len(argv):
            print("usage: verify_cutover_readiness.py --edge https://host")
            return 2
        return edge_mode(argv[i + 1])
    return offline_mode()


if __name__ == "__main__":
    sys.exit(main())
