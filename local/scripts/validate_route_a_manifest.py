#!/usr/bin/env python3
"""validate_route_a_manifest.py — Route A control-plane gate (D-171 / D-141).

Focused, fail-closed validation of the Route A deployment manifest
(`docs/deployment/dokploy-control-plane.compose.yaml`). It reads THAT
manifest and only that manifest.

NOT THE STAGING VALIDATOR: `validate_staging_compose.py` is hard-coded to
`local/infra/compose.staging.yml` and proves the Stage B contract. It is
neither extended nor replaced here, and a green run of it is not evidence
about Route A.

Gates proven:
  R-A1  SCHEMA      — `docker compose config` resolves the manifest
                      (client-side resolution, no daemon required).
  R-A2  FAIL-CLOSED — each required injected variable
                      (CONTROL_PLANE_IMAGE, CP_PROBE_ENDPOINTS,
                      CP_PROBE_TOKENS) is declared in the strict
                      `${VAR:?reason}` form AND individually makes
                      resolution REFUSE when absent.
  R-A3  ISOLATION   — zero published ports, no volumes, exactly one
                      `edge` network, nothing else attached.
  R-A4  HARDENING   — read-only rootfs, non-root `1000:1000`, cap_drop
                      ALL, no-new-privileges, bounded resources
                      (mem_limit + cpus), an explicit restart policy.
  R-A5  HEALTH      — the healthcheck targets /api/health through
                      `node -e` (no curl/wget dependency, so it survives a
                      hardened rootfs and a base-image swap).
  R-A6  IMAGE       — the deployable reference must be immutable
                      (`@sha256:` + 64 lowercase hex). A reference with no
                      registry host is a LOCAL DEVELOPMENT FIXTURE: valid
                      for local runs, and NEVER evidence of a published
                      OCI manifest digest — `--require-deployable` refuses
                      it by design.
  R-A7  DEV-SURFACE — no `CP_*_SCENARIO` mock switch is present in a
                      deployed environment.

Exit codes: 0 = valid · 1 = validation failure (including a local-only
image under `--require-deployable`) · 2 = environment problem (docker CLI
or compose plugin missing). Never a silent pass.

Usage:
  python3 local/scripts/validate_route_a_manifest.py
  python3 local/scripts/validate_route_a_manifest.py --require-deployable
  python3 local/scripts/validate_route_a_manifest.py --manifest <path> --image <ref>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTE_A = REPO / "docs" / "deployment" / "dokploy-control-plane.compose.yaml"

REQUIRED_VARS = ("CONTROL_PLANE_IMAGE", "CP_PROBE_ENDPOINTS",
                 "CP_PROBE_TOKENS")

# STAGING_VERSION is deliberately absent from this manifest: the only
# non-secret injected values are the probe maps, which must be `{}` when a
# probe is not wired yet — an explicit decision, never a silent default.
SYNTHETIC_ENV = {
    "CP_PROBE_ENDPOINTS": "{}",
    "CP_PROBE_TOKENS": "{}",
}

_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")
# A registry host is the first path component carrying a dot (or a
# host:port pair) — `ghcr.io/owner/name`, `localhost:5000/name`.
_REGISTRY_HOST_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:[0-9]+)?/")
_TAG_ONLY_RE = re.compile(r"^[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+$")
_STRICT_IMAGE_LINE_RE = re.compile(
    r"^    image: \$\{CONTROL_PLANE_IMAGE:\?[^}]*\}$", re.M)


def local_fixture_image() -> str:
    """A LOCAL-STYLE fixture reference: immutable by shape, no registry
    host, and synthetic by construction — the digest is derived here and
    is never a published OCI manifest digest."""
    seed = b"route-a-local-development-fixture"
    return "control-plane@sha256:" + hashlib.sha256(seed).hexdigest()


def classify_image(ref: str) -> str:
    """MUTABLE | LOCAL_FIXTURE | DEPLOYABLE."""
    if "@sha256:" not in ref or not _DIGEST_RE.search(ref):
        if _TAG_ONLY_RE.match(ref):
            return "MUTABLE"
        return "MUTABLE"
    return "DEPLOYABLE" if _REGISTRY_HOST_RE.match(ref) else "LOCAL_FIXTURE"


def _resolve(manifest: Path, image: str,
             drop: tuple = ()) -> tuple:
    """Resolve the manifest through `docker compose config`. Returns
    (rc, parsed-json-or-None, stderr-text)."""
    env = dict(os.environ)
    env.update(SYNTHETIC_ENV)
    env["CONTROL_PLANE_IMAGE"] = image
    for name in drop:
        env.pop(name, None)
    proc = subprocess.run(
        ["docker", "compose", "-f", str(manifest),
         "config", "--format", "json"],
        capture_output=True, text=True, env=env, cwd=str(REPO))
    parsed = None
    if proc.returncode == 0:
        try:
            parsed = json.loads(proc.stdout)
        except ValueError:
            parsed = None
    return proc.returncode, parsed, proc.stderr


class Gate:
    """Accumulates findings; every finding is fatal (fail-closed)."""

    def __init__(self) -> None:
        self.findings: list[str] = []

    def ok(self, msg: str) -> None:
        print(f"  [OK  ] {msg}")

    def note(self, msg: str) -> None:
        print(f"  [NOTE] {msg}")

    def fail(self, msg: str) -> None:
        self.findings.append(msg)
        print(f"  [FAIL] {msg}")


def _check_raw(gate: Gate, text: str) -> None:
    """R-A2 (form) + R-A6 (injection form) on the raw manifest text."""
    if _STRICT_IMAGE_LINE_RE.search(text):
        gate.ok("image is injected in the strict `${CONTROL_PLANE_IMAGE:?…}` "
                "form — no literal reference can be committed")
    else:
        gate.fail("the image is not declared as a strict "
                  "`${CONTROL_PLANE_IMAGE:?reason}` reference — a literal or "
                  "loose form would let a mutable tag reach the service")
    if re.search(r"^\s*image:\s*[^\s$]", text, re.M):
        gate.fail("a literal image reference is present in the manifest")


def _check_resolved(gate: Gate, svc: dict, image: str) -> None:
    """R-A3..R-A6 on the resolved service."""
    # R-A3 isolation
    if svc.get("ports"):
        gate.fail(f"published ports present: {svc['ports']} — the gateway is "
                  "the only surface")
    else:
        gate.ok("no published ports (gateway-only surface)")
    if svc.get("volumes"):
        gate.fail(f"volumes declared: {svc['volumes']} — the read-only "
                  "surface keeps no state")
    else:
        gate.ok("no volumes (no state on disk)")
    nets = sorted((svc.get("networks") or {}).keys())
    if nets == ["edge"]:
        gate.ok("attached to `edge` only")
    else:
        gate.fail(f"networks are {nets} — expected exactly ['edge']")

    # R-A4 hardening
    checks = (
        ("read-only rootfs", svc.get("read_only") is True),
        ("non-root user 1000:1000", svc.get("user") == "1000:1000"),
        ("cap_drop ALL", [str(c).upper() for c in (svc.get("cap_drop") or [])]
         == ["ALL"]),
        ("no-new-privileges",
         "no-new-privileges:true" in (svc.get("security_opt") or [])),
        ("restart policy declared", bool(svc.get("restart"))),
    )
    for label, good in checks:
        if good:
            gate.ok(f"hardening: {label}")
        else:
            gate.fail(f"hardening invariant missing or wrong: {label}")
    try:
        mem = int(svc.get("mem_limit", 0))
    except (TypeError, ValueError):
        mem = 0
    if 0 < mem <= 2 * 1024 * 1024 * 1024:
        gate.ok(f"bounded memory: {mem} bytes")
    else:
        gate.fail("mem_limit missing, zero or unbounded")
    try:
        cpus = float(svc.get("cpus", 0))
    except (TypeError, ValueError):
        cpus = 0.0
    if 0 < cpus <= 4:
        gate.ok(f"bounded cpu: {cpus}")
    else:
        gate.fail("cpus missing, zero or unbounded")

    # R-A5 health
    test = " ".join((svc.get("healthcheck") or {}).get("test") or [])
    if "/api/health" in test and "node -e" in test:
        gate.ok("healthcheck targets /api/health via `node -e`")
    else:
        gate.fail(f"healthcheck does not target /api/health via node -e: "
                  f"{test[:120]}")
    if "wget" in test or "curl" in test:
        gate.fail("healthcheck depends on a shell utility (wget/curl) — it "
                  "would break on a hardened rootfs or a base-image swap")

    # R-A6 image
    kind = classify_image(image)
    if kind == "MUTABLE":
        gate.fail(f"image reference is mutable or unpinned: {image!r} — an "
                  "immutable `@sha256:<64 lowercase hex>` reference is required")
    elif kind == "LOCAL_FIXTURE":
        gate.note(f"image {image!r} is a LOCAL DEVELOPMENT FIXTURE (no "
                  "registry host). It is valid for local runs and is NOT "
                  "evidence of a published OCI manifest digest.")
    else:
        gate.ok(f"image is digest-pinned to a registry: {image}")

    # R-A7 dev surface
    env = svc.get("environment") or {}
    leaked = sorted(k for k in env if "SCENARIO" in k)
    if leaked:
        gate.fail(f"mock/scenario switches present in a deployed environment: "
                  f"{leaked}")
    else:
        gate.ok("no CP_*_SCENARIO mock switch in the deployed environment")


def main(argv: list | None = None, image: str | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    manifest = ROUTE_A
    require_deployable = False
    cli_image: str | None = None
    it = iter(args)
    for a in it:
        if a == "--manifest":
            manifest = Path(next(it, "")).resolve()
        elif a == "--image":
            cli_image = next(it, "").strip()
        elif a == "--require-deployable":
            require_deployable = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(f"  [ENV ] unknown argument: {a}", file=sys.stderr)
            return 2

    print("=== Route A control-plane manifest validation (D-171 / D-141) ===")
    print(f"  manifest: {manifest}")
    if not manifest.is_file():
        print(f"  [ENV ] manifest not found: {manifest}", file=sys.stderr)
        return 2
    if shutil.which("docker") is None:
        print("  [ENV ] docker CLI not found — cannot validate (exit 2)",
              file=sys.stderr)
        return 2
    probe = subprocess.run(["docker", "compose", "version"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        print("  [ENV ] docker compose plugin unavailable — cannot validate "
              "(exit 2)", file=sys.stderr)
        return 2

    gate = Gate()
    gate.ok("docker CLI + compose plugin available")

    resolved_image = (cli_image or image
                      or os.environ.get("CONTROL_PLANE_IMAGE", "").strip()
                      or local_fixture_image())

    # R-A1 schema
    rc, parsed, err = _resolve(manifest, resolved_image)
    if rc != 0 or parsed is None:
        gate.fail(f"`docker compose config` refused the manifest: "
                  f"{err.strip()[:200]}")
        print("=== REFUSED: Route A manifest does not resolve ===")
        return 1
    gate.ok("schema: `docker compose config` resolves the manifest")
    services = parsed.get("services") or {}
    if list(services.keys()) != ["control-plane"]:
        gate.fail(f"service set is {sorted(services.keys())} — Route A "
                  "carries exactly one service")
        print("=== REFUSED: unexpected service set ===")
        return 1

    # R-A2 fail-closed, one variable at a time
    text = manifest.read_text(encoding="utf-8")
    _check_raw(gate, text)
    for name in REQUIRED_VARS:
        rc_drop, _, _ = _resolve(manifest, resolved_image, drop=(name,))
        if rc_drop == 0:
            gate.fail(f"missing {name} still resolved — the variable is not "
                      "strictly required (fail-closed broken)")
        else:
            gate.ok(f"missing {name} refuses startup (fail-closed)")

    # R-A3..R-A7
    _check_resolved(gate, services["control-plane"], resolved_image)

    if gate.findings:
        print(f"  ---\n  {len(gate.findings)} finding(s)")
        print("=== REFUSED: Route A manifest violates the pinned contract ===")
        return 1

    if classify_image(resolved_image) == "LOCAL_FIXTURE":
        if require_deployable:
            print("  [FAIL] --require-deployable: the resolved image is a "
                  "local development fixture; a registry push is required "
                  "before any deployment")
            print("=== REFUSED: no published OCI manifest digest ===")
            return 1
        print("  [NOTE] local fixture image accepted for local development; "
              "re-run with --require-deployable before a deployment")

    print("=== VALID: Route A manifest satisfies the pinned contract ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
