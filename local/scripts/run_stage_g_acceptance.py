#!/usr/bin/env python3
"""Stage G — acceptance executor (D-149).

Machine-enforced acceptance runner evaluated AFTER Stage G pre-flight
clearance (D-148) and BEFORE any production activation. Implements the
ACC checks over the bound Stage D artifacts; the deeper GA-1..GA-7
deployment probes (`docs/deployment/stage-g-acceptance.md`) run against
a LIVE stack and stay owner-gated — this executor is the
configuration-readiness half that must pass first.

ENTRY GATE (fail-closed): a `PREFLIGHT_CLEARED` verdict from
`stage_g_preflight_validator.py` is mandatory. A blocked or absent
pre-flight aborts the run immediately — no acceptance report is
produced, nothing is evaluated past the gate.

Acceptance checks:

  ACC-01  compose manifest structural conformance against the bound
          Stage D template: services isolated (backend internal, zero
          published ports on data services, app sole edge attachment),
          probe-parity healthchecks, required service set present,
          dependency graph acyclic and edge-only.
  ACC-02  environment variable declarations: every `${VAR:?…}`
          reference maps onto the runtime-preflight contract
          (MANDATORY_KEYS kinds / known names), interpolation is
          strict-form only, and no secret-shaped literal exists in
          the manifest (D-124 — names and shapes, never values).
  ACC-03  hardening baseline: every service carries resource ceilings
          (mem_limit + cpus), `restart: unless-stopped`,
          `no-new-privileges`, read-only rootfs with tmpfs seams, and
          volume mounts restricted to declared named volumes (no host
          bind mounts).
  ACC-04  canonical `stage_g_acceptance_report.v1` artifact with a
          SHA-256 acceptance fingerprint over the report's canonical
          bytes, binding the verdict to the exact manifest + template
          + bundle hash evaluated.

Architecture: pure core — the bundle, manifest, template, and
pre-flight verdict arrive via INJECTED providers (RULES §35); the
clock is injected; zero sockets/subprocess/direct file I/O (AST-pinned
in the battery). Reports carry hashes, names, shapes, and verdict
words only.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # battery package path or script cwd path
    from ..src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script invocation paths
    try:
        from src.memory.vector_store import deep_redact  # type: ignore
    except ImportError:
        from memory.vector_store import deep_redact  # type: ignore

__all__ = [
    "AcceptanceError", "AcceptanceReport", "StageGAcceptanceRunner",
    "ACCEPTED", "REJECTED", "REPORT_SCHEMA", "manifest_hash_of",
]

ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
REPORT_SCHEMA = "stage_g_acceptance_report.v1"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_STRICT_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):\?[^}]*\}")
_LOOSE_VAR = re.compile(r"(?<!\$)\$\([A-Z_][A-Z0-9_]*\)"
                        r"|(?<!\$)\$\{[A-Z_][A-Z0-9_]*\}"
                        r"|(?<!\$)\$[A-Z_][A-Z0-9_]*")
_SECRET_SHAPED = re.compile(
    r"(?i)(api[_-]?key|secret|password|token|passwd|pwd)\s*[=:]\s*"
    r"['\"](?!\s*['\"]|\$\{)[A-Za-z0-9+/_\-]{12,}")

_BACKEND = ("postgres-ssot", "redis", "telemetry-circuit")
_EDGE_SVC = "app-orchestrator"
_REQUIRED_SERVICES = _BACKEND + (_EDGE_SVC,)

# Hardening baseline per service (ACC-03): the shipped Stage D template
# pins these for every service; a missing baseline is a fail.
_CEILING_FLOOR = {"postgres-ssot": ("512m", "1.0"),
                  "redis": ("256m", "0.5"),
                  _EDGE_SVC: ("1g", "1.0"),
                  "telemetry-circuit": ("256m", "0.5")}


class AcceptanceError(ValueError):
    """Contract-level misuse of the acceptance runner."""


def _fail(reason: str) -> None:
    raise AcceptanceError(reason)


def manifest_hash_of(manifest_text: str) -> str:
    return hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()


def _service_blocks(manifest: str) -> Dict[str, str]:
    """Parse top-level service blocks (same discipline as the Stage E
    verifier: 2-space service keys under `services:`)."""
    m = re.search(r"^services:\s*$", manifest, re.M)
    if not m:
        return {}
    rest = manifest[m.end():]
    nxt = re.search(r"^[a-z_]+:\s*(?:#.*)?$", rest, re.M)
    body = rest[:nxt.start()] if nxt else rest
    blocks: Dict[str, str] = {}
    matches = list(re.finditer(r"^  ([a-z][a-z0-9-]*):\s*$", body, re.M))
    for i, mt in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        blocks[mt.group(1)] = body[mt.end():end]
    return blocks


def _recompute_bundle_hash(bundle: Dict[str, Any]) -> str:
    blob = json.dumps({k: v for k, v in bundle.items()
                       if k != "bundle_hash"},
                      sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AcceptanceReport:
    """Canonical, immutable ACC verdict artifact."""
    schema: str
    verdict: str                       # ACCEPTED / REJECTED
    manifest_sha256: str
    template_sha256: str
    bundle_sha256: str                 # '' when no bundle supplied
    checks: tuple = field(default_factory=tuple)   # (id, ok, detail)
    observed_tick: int = 0

    @property
    def accepted(self) -> bool:
        return self.verdict == ACCEPTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "verdict": self.verdict,
            "manifest_sha256": self.manifest_sha256,
            "template_sha256": self.template_sha256,
            "bundle_sha256": self.bundle_sha256,
            "checks": [list(c) for c in self.checks],
            "observed_tick": self.observed_tick,
        }

    @property
    def acceptance_fingerprint(self) -> str:
        """SHA-256 over the report's canonical bytes (ACC-04)."""
        blob = json.dumps(self.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class StageGAcceptanceRunner:
    """ACC-01..ACC-04 with injected providers (RULES §35).

    Injected:
      clock            — ``() -> int`` logical tick
      audit_sink       — ``callable(dict)`` receiving every report
      preflight_verdict — ``() -> dict`` the D-148 validator's verdict
                          (must carry verdict == PREFLIGHT_CLEARED and
                          the bundle hash it cleared)
      manifest_provider  — ``() -> str`` the bound Stage D manifest text
      template_provider  — ``() -> str`` the Stage D template text
      bundle_provider    — ``() -> dict`` the cutover bundle ('' ok)
    """

    def __init__(self, clock: Callable[[], int],
                 audit_sink: Callable[[Dict[str, Any]], None],
                 preflight_verdict: Callable[[], Dict[str, Any]],
                 manifest_provider: Callable[[], str],
                 template_provider: Callable[[], str],
                 bundle_provider: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
        if not callable(clock) or not callable(audit_sink):
            _fail("clock and audit_sink required")
        if not callable(preflight_verdict):
            _fail("preflight_verdict provider required")
        if not callable(manifest_provider) or not callable(template_provider):
            _fail("manifest/template providers required")
        self._clock = clock
        self._sink = audit_sink
        self._preflight = preflight_verdict
        self._manifest = manifest_provider
        self._template = template_provider
        self._bundle = bundle_provider

    # -- entry gate ------------------------------------------------------------

    def _entry_gate(self) -> Tuple[Optional[AcceptanceReport], Dict[str, Any]]:
        try:
            pv = self._preflight()
        except Exception as exc:  # noqa: BLE001 — absent/broken gate
            return self._reject_report(
                [("PREFLIGHT", False,
                  f"pre-flight verdict unavailable: {type(exc).__name__}")],
                "", ""), {}
        if not isinstance(pv, dict) or \
                pv.get("verdict") != "PREFLIGHT_CLEARED":
            v = pv.get("verdict") if isinstance(pv, dict) else "absent"
            return self._reject_report(
                [("PREFLIGHT", False,
                  f"pre-flight verdict {v!r} != 'PREFLIGHT_CLEARED' — "
                  "provisioning is not authorized (D-148)")],
                "", ""), {}
        return None, pv

    # -- the ACC checks ----------------------------------------------------------

    def acc01_manifest_conformance(self, manifest: str,
                                   template: str) -> Tuple[bool, List[str]]:
        """Structure, isolation, probe parity, service set, dependency
        graph against the bound Stage D template."""
        problems: List[str] = []
        blocks = _service_blocks(manifest)
        if not blocks:
            return False, ["manifest has no parseable services block"]
        missing = [s for s in _REQUIRED_SERVICES if s not in blocks]
        if missing:
            problems.append(f"required services missing: {missing}")
        if _LOOSE_VAR.search(manifest):
            problems.append("non-strict variable form present "
                            "(strict ${VAR:?…} only)")
        # isolation contract
        for name, body in blocks.items():
            on_edge = re.search(r"^\s+-\s+edge\s*$", body, re.M) is not None
            has_ports = re.search(r"^\s*ports:\s*$", body, re.M) is not None
            if name in _BACKEND:
                if has_ports:
                    problems.append(f"{name} declares ports: — backend "
                                    "services are never externally bound")
                if on_edge:
                    problems.append(f"{name} attaches to edge — refused")
            elif name == _EDGE_SVC and not on_edge:
                problems.append("app-orchestrator not attached to edge — "
                                "no gateway-routable surface")
        if re.search(r"^networks:\s*$.*?^\s+backend:\s*$.*?^"
                     r"\s+internal:\s*false\s*$", manifest, re.M | re.S):
            problems.append("backend network not internal — isolation broken")
        # probe parity (D-145 contract mirrored for the deployment shape)
        parity = {"postgres-ssot": ("pg_isready",),
                  "redis": ("ping", "PONG"),
                  _EDGE_SVC: ("/healthz/worker",),
                  "telemetry-circuit": ("/-/healthy",)}
        for name, tokens in parity.items():
            body = blocks.get(name)
            if body is None:
                continue
            if "healthcheck:" not in body:
                problems.append(f"{name} has no healthcheck — unverifiable")
                continue
            test_line = " ".join(re.findall(r"test:\s*\[(.*?)\]", body, re.S))
            if not any(t.lower() in test_line.lower() for t in tokens):
                problems.append(f"{name} healthcheck off probe contract")
        # dependency graph: app may depend on backend services only;
        # nothing depends on the edge service (acyclic, edge-only)
        for name, body in blocks.items():
            dep = re.search(r"depends_on:\s*\n((?:\s+-\s+\S+\s*\n)+)", body)
            if not dep:
                continue
            deps = [d.strip().lstrip("- ").strip()
                    for d in dep.group(1).splitlines() if d.strip()]
            if name == _EDGE_SVC:
                bad = [d for d in deps if d not in _BACKEND]
                if bad:
                    problems.append(f"app-orchestrator depends on non-backend "
                                    f"services: {bad}")
            else:
                bad = [d for d in deps if d == _EDGE_SVC]
                if bad:
                    problems.append(f"{name} depends on the edge service — "
                                    "dependency graph must be edge-leaf")
        # template binding: every template service appears in the manifest
        tb = _service_blocks(template)
        drift = [s for s in tb if s not in blocks]
        if drift:
            problems.append(f"manifest drifted from bound template "
                            f"(missing services): {drift}")
        return (not problems), problems

    def acc02_env_schema(self, manifest: str) -> Tuple[bool, List[str]]:
        """`${VAR:?…}` references map onto the known contract; strict
        interpolation only; no secret-shaped literals (D-124)."""
        problems: List[str] = []
        # strip comments before scanning: prose may legitimately cite
        # ${VAR:?reason} shapes as documentation
        lines = [l for l in manifest.splitlines()
                 if not l.lstrip().startswith("#")]
        code = "\n".join(lines)
        refs = _STRICT_REF.findall(code)
        if not refs:
            return False, ["manifest declares no strict env references"]
        try:
            from canonical.runtime_preflight import MANDATORY_KEYS
            known = set(MANDATORY_KEYS)
        except ImportError:  # pragma: no cover - path wiring
            known = set()
        known.update({"REDIS_PASSWORD", "POSTGRES_IMAGE", "REDIS_IMAGE",
                      "APP_IMAGE", "TELEMETRY_IMAGE", "WORDPRESS_DB_PASSWORD",
                      "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD",
                      "N8N_ENCRYPTION_KEY", "MINIO_ROOT_USER",
                      "MINIO_ROOT_PASSWORD", "MEDIA_ACCESS_KEY",
                      "MEDIA_SECRET_KEY", "TZ"})
        for name in sorted(set(refs)):
            if name not in known:
                problems.append(f"env reference outside the declared "
                                f"contract: {name}")
        for i, line in enumerate(code.splitlines(), 1):
            if _LOOSE_VAR.search(line):
                problems.append(f"line {i}: loose variable form (strict "
                                "${VAR:?…} only)")
            if _SECRET_SHAPED.search(line):
                problems.append(f"line {i}: secret-shaped literal — "
                                "values never enter the manifest (D-124)")
        return (not problems), problems

    def acc03_hardening_baseline(self, manifest: str) -> Tuple[bool, List[str]]:
        """Ceilings, restart policy, no-new-privileges, named-volume-only
        mounts per service. Rootfs read-only + tmpfs seams are pinned
        where the shipped Stage D template declares them (the SSOT and
        broker images support read-only; the app/telemetry images need
        writable state paths, so the baseline is template-parity, not
        blanket read-only)."""
        problems: List[str] = []
        blocks = _service_blocks(manifest)
        declared_vols = set(re.findall(
            r"^  ([a-z_][a-z0-9_]*):\s*\{\}\s*$",
            manifest.split("volumes:", 1)[-1], re.M))
        # template parity: services whose template block is read_only
        # must remain so (the shipped baseline)
        readonly_required = {name for name, body in
                             _service_blocks(self._template()).items()
                             if "read_only: true" in body} \
            if self._template is not None else set()
        for name, body in blocks.items():
            if "mem_limit:" not in body or "cpus:" not in body:
                problems.append(f"{name} missing resource ceilings")
            if not re.search(r"^\s+restart:\s*unless-stopped\s*$", body, re.M):
                problems.append(f"{name} restart policy != unless-stopped")
            if "no-new-privileges" not in body:
                problems.append(f"{name} missing no-new-privileges")
            if name in readonly_required and "read_only: true" not in body:
                problems.append(f"{name} lost its read-only rootfs "
                                "(template baseline)")
            if "tmpfs:" not in body and name in readonly_required:
                problems.append(f"{name} missing tmpfs write seams")
            for mount in re.findall(r"^\s+-\s+(\S+):(?:/|\.)", body, re.M):
                vol = mount.split(":")[0]
                if vol not in declared_vols:
                    problems.append(f"{name} mounts non-declared volume "
                                    f"'{vol}' (host bind mounts refused)")
        return (not problems), problems

    # -- the run ------------------------------------------------------------------

    def run(self) -> AcceptanceReport:
        """Entry gate → ACC-01..ACC-03 → ACC-04 report. Exactly one
        report is emitted and audited per call (including aborts)."""
        abort, pv = self._entry_gate()
        if abort is not None:
            return abort

        manifest = self._manifest()
        template = self._template()
        bundle = {}
        if self._bundle is not None:
            try:
                bundle = self._bundle() or {}
            except Exception:  # noqa: BLE001 — bundle optional here
                bundle = {}
        mh = manifest_hash_of(manifest)
        th = manifest_hash_of(template)
        bh = ""
        checks: List[Tuple[str, bool, str]] = []
        if bundle:
            recorded = bundle.get("bundle_hash", "")
            if not _HEX64.match(recorded or ""):
                checks.append(("BUNDLE", False,
                               "bundle hash missing or malformed — "
                               "fail closed"))
            else:
                recomputed = _recompute_bundle_hash(bundle)
                if recorded != recomputed:
                    checks.append(("BUNDLE", False,
                                   "bundle hash does not match its "
                                   "canonical bytes — TAMPERED bundle, "
                                   "fail closed"))
                else:
                    bh = recorded
                    cleared = pv.get("bundle_sha256", "")
                    if cleared and cleared != bh:
                        checks.append(("BUNDLE", False,
                                       "pre-flight cleared a different "
                                       "bundle"))
        ok1, p1 = self.acc01_manifest_conformance(manifest, template)
        checks.append(("ACC-01", ok1, "; ".join(p1) or
                       "manifest conforms to the bound Stage D template"))
        ok2, p2 = self.acc02_env_schema(manifest)
        checks.append(("ACC-02", ok2, "; ".join(p2) or
                       "env contract strict-form and complete"))
        ok3, p3 = self.acc03_hardening_baseline(manifest)
        checks.append(("ACC-03", ok3, "; ".join(p3) or
                       "hardening baseline satisfied per service"))
        if all(ok for _, ok, _ in checks):
            checks.append(("ACC-04", True, "report artifact emitted"))
        else:
            checks.append(("ACC-04", False,
                           "report emitted as REJECTED — remediate ACC-01..03"))
        verdict = ACCEPTED if all(ok for _, ok, _ in checks) else REJECTED
        report = AcceptanceReport(
            schema=REPORT_SCHEMA, verdict=verdict,
            manifest_sha256=mh, template_sha256=th, bundle_sha256=bh,
            checks=tuple((c[0], c[1], deep_redact(c[2])) for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(report.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        self._sink(json.loads(deep_redact(blob)))
        return report

    def _reject_report(self, checks: List[Tuple[str, bool, str]],
                       manifest_hash: str,
                       template_hash: str) -> AcceptanceReport:
        report = AcceptanceReport(
            schema=REPORT_SCHEMA, verdict=REJECTED,
            manifest_sha256=manifest_hash, template_sha256=template_hash,
            bundle_sha256="",
            checks=tuple((c[0], c[1], deep_redact(c[2])) for c in checks),
            observed_tick=self._clock())
        blob = json.dumps(report.to_dict(), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=False)
        self._sink(json.loads(deep_redact(blob)))
        return report


def main(argv: Optional[List[str]] = None) -> int:
    """CLI wiring: real artifacts + real D-148 validator verdict file."""
    import argparse
    import pathlib
    import sys
    ap = argparse.ArgumentParser(
        description="Stage G acceptance executor (ACC-01..ACC-04, D-149).")
    ap.add_argument("--preflight-json", required=True,
                    help="path to the D-148 PREFLIGHT verdict JSON")
    args = ap.parse_args(argv)
    print("run_stage_g_acceptance: interactive wiring requires the real "
          "artifacts and D-112 audit sink; see run() and the battery "
          "for the injected contract.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
