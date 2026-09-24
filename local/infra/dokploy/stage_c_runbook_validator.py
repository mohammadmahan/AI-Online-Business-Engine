#!/usr/bin/env python3
"""stage_c_runbook_validator.py — Stage C runbook-prerequisites validator
(D-143; Dokploy Deployment Integration, D-141).

Machine-enforced check of the Stage C runbook prerequisites BEFORE any
real provisioning happens. Complements (never replaces) the existing
Stage C harnesses:

  - `local/scripts/validate_vps_target.py`  — offline plan verification
    + opt-in READ-ONLY SSH target probe (C-01..C-07)
  - `docs/runbooks/dokploy-vps-provisioning.md` — the G1–G6 owner-gated
    procedure this validator machine-checks

Design contract (battery-pinned):

  HERMETIC    — zero network sockets, zero subprocess, zero wall-clock.
                Host observations arrive via an INJECTED `HostAdapter`
                (`collect() -> HostFacts`); the CLI reads a facts JSON
                file. Test battery runs entirely in memory/dry-run.
  FAIL-CLOSED — unparseable or missing host observations are findings
                (CANNOT_ASSESS / NOT_READY), never silent passes.
  NO SECRETS  — environment VALUES are never emitted: the report
                carries variable NAMES, presence booleans, and a
                sha256-based fingerprint only (D-124/D-045); every
                finding detail is deep-redacted.

Checks (all produce stable `VC-xx` findings, sorted deterministically):

  VC-01  OS family supported (Debian/Ubuntu per official Dokploy docs)
  VC-02  kernel >= 5.10
  VC-03  Docker engine >= 24.0 (parsed; garbage input fails closed)
  VC-04  Docker Compose v2 plugin available
  VC-05  cgroup v2 unified hierarchy (manifest limits depend on it)
  VC-06  gateway ports 80/443 FREE on the host
  VC-07  forbidden ports 3000/5432/6379 NOT publicly bound
         (loopback-only binding degrades to a warning)
  VC-08  UFW active
  VC-09  UFW default incoming policy = deny/drop
  VC-10  UFW ingress allowlist ⊆ {22, 80, 443}
  VC-11  required planning env variables present (names only)
  VC-12  installer ref pinned (semver tag; `latest` refused)
  VC-13  deployment domain well-formed (no scheme, no credentials)
  VC-14  owner sign-off attestations present for G1–G5

Verdicts: READY (exit 0) · NOT_READY (exit 1, critical findings) ·
CANNOT_ASSESS (exit 2, host observations unparseable/missing).

Usage:
  python3 stage_c_runbook_validator.py --facts-file facts.json [--json]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Protocol, Tuple

try:  # battery / repo-root path
    from local.src.memory.vector_store import deep_redact  # type: ignore
except ImportError:  # standalone cwd — same shapes, stdlib only
    _SECRET_SHAPES = (
        re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*\S+"),
        re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----.*", re.S),
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"(?i)postgres(ql)?://[^\s]*:[^\s@]+@[^\s]*"),
        re.compile(r"(?i)redis://:[^\s@]+@[^\s]*"),
        re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    )

    def deep_redact(text: str) -> str:  # type: ignore[misc]
        out = text
        for pattern in _SECRET_SHAPES:
            out = pattern.sub("[REDACTED]", out)
        return out


__all__ = [
    "Finding", "HostFacts", "HostAdapter", "StageCReport",
    "StageCRunbookValidator", "main",
]

GATEWAY_PORTS = (80, 443)            # must be FREE (gateway/TLS binds them)
FORBIDDEN_PUBLIC = (3000, 5432, 6379)  # mgmt + SSOT + broker: never public
ALLOWED_INGRESS = {"22", "80", "443"}
OS_FAMILIES = ("debian", "ubuntu")
DOCKER_MIN = (24, 0)
KERNEL_MIN = (5, 10)

REQUIRED_ENV = (
    "DOKPLOY_HOST_IP",
    "DOKPLOY_SSH_USER",
    "DOKPLOY_INSTALLER_REF",
    "DOKPLOY_DOMAIN",
)
REQUIRED_GATES = ("G1_HOST", "G2_INSTALLER", "G3_FIREWALL", "G4_SSH", "G5_DNS")

VERDICT_READY = "READY"
VERDICT_NOT_READY = "NOT_READY"
VERDICT_CANNOT_ASSESS = "CANNOT_ASSESS"

_SEV_CRITICAL = "critical"
_SEV_WARNING = "warning"

_LISTEN_RE = re.compile(
    r"^(?P<state>\S+)\s+\d+\s+\d+\s+(?P<local>\S+?):(?P<port>\d+)\s+\S")
_PUBLIC_LOCAL = ("0.0.0.0", "::", "*", "[::]")


# ---------------------------------------------------------------------------
# Host facts (pure data — what an adapter must observe and inject)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HostFacts:
    """Observed host state. Every field is plain data; the validator
    never collects anything itself (hermetic by construction)."""

    os_pretty_name: str = ""
    kernel_release: str = ""
    docker_version_text: str = ""
    docker_compose_ok: bool = False
    cgroup_controllers: str = ""
    listening_lines: Tuple[str, ...] = ()
    ufw_status_text: str = ""
    env: Mapping[str, str] = field(default_factory=dict)
    attestations: Mapping[str, str] = field(default_factory=dict)


class HostAdapter(Protocol):
    """Injection seam — the ONLY source of host observations.

    Production adapter (owner-authorized run) may shell out; the test
    battery and dry-run mode inject in-memory facts. The validator
    itself performs zero I/O beyond reading an optional facts file.
    """

    def collect(self) -> HostFacts: ...


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail", deep_redact(self.detail))


@dataclass(frozen=True)
class StageCReport:
    verdict: str
    findings: Tuple[Finding, ...]
    env_fingerprint: str
    counts: Mapping[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "counts": dict(self.counts),
            "env_fingerprint": self.env_fingerprint,
            "findings": [
                {"code": f.code, "severity": f.severity, "detail": f.detail}
                for f in self.findings
            ],
        }


def _env_fingerprint(env: Mapping[str, str]) -> str:
    """sha256 over sorted `NAME=sha256(value)` pairs — deterministic
    binding WITHOUT exposing any value."""
    h = hashlib.sha256()
    for name in sorted(env):
        vh = hashlib.sha256(env[name].encode("utf-8")).hexdigest()
        h.update(f"{name}={vh}\n".encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Parsers (fail closed — unparseable input yields None/empty, callers
# turn that into findings, never silent passes)
# ---------------------------------------------------------------------------

def parse_docker_version(text: str) -> Tuple[int, int] | None:
    m = re.search(r"version\s+(\d+)\.(\d+)", text or "", re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_kernel(text: str) -> Tuple[int, int] | None:
    m = re.match(r"(\d+)\.(\d+)", (text or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_os_family(text: str) -> str | None:
    low = (text or "").lower()
    for fam in OS_FAMILIES:
        if fam in low:
            return fam
    return None


def parse_listening(text: Tuple[str, ...]) -> Tuple[Tuple[str, int], ...] | None:
    """`ss -tlnp` lines -> ((local_addr, port), ...). Unparseable lines
    are skipped; wholly unparseable output (no valid line at all) is
    indistinguishable from empty — callers treat empty as CANNOT_ASSESS."""
    out = []
    for line in text or ():
        m = _LISTEN_RE.match(line.strip())
        if m:
            out.append((m.group("local"), int(m.group("port"))))
    return tuple(out) if out else None


def parse_ufw(text: str) -> Tuple[bool, str, Tuple[str, ...]] | None:
    """`ufw status verbose` -> (active, default_incoming, allow_ports).
    Returns None when the output is not recognizable UFW output."""
    if "Status:" not in (text or ""):
        return None
    m = re.search(r"Status:\s*(\w+)", text)
    active = bool(m and m.group(1).lower() == "active")
    d = re.search(r"Default:\s*(\w+)\s*\(incoming\)", text)
    default_in = d.group(1).lower() if d else ""
    ports = []
    for row in text.splitlines():
        if "ALLOW" not in row:
            continue
        to_col = row.split("ALLOW")[0].strip()
        pm = re.match(r"([\d,]+)(?:/tcp)?(?:/udp)?$", to_col)
        if pm:
            ports.extend(p for p in pm.group(1).split(",") if p)
    return active, default_in, tuple(ports)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class StageCRunbookValidator:
    """Pure checker over injected `HostFacts`. No I/O, no clock."""

    def validate(self, facts: HostFacts) -> StageCReport:
        findings: list[Finding] = []
        cannot_assess = False

        # VC-01 OS family
        fam = parse_os_family(facts.os_pretty_name)
        if not facts.os_pretty_name.strip():
            findings.append(Finding("VC-01", _SEV_CRITICAL,
                                    "os_pretty_name missing — cannot assess OS family"))
            cannot_assess = True
        elif fam is None:
            findings.append(Finding("VC-01", _SEV_CRITICAL,
                                    f"unsupported OS family: {facts.os_pretty_name!r}"))

        # VC-02 kernel floor
        kern = parse_kernel(facts.kernel_release)
        if kern is None:
            findings.append(Finding("VC-02", _SEV_CRITICAL,
                                    "kernel release unparseable — cannot assess floor"))
            cannot_assess = True
        elif kern < KERNEL_MIN:
            findings.append(Finding("VC-02", _SEV_CRITICAL,
                                    f"kernel {facts.kernel_release} < {'.'.join(map(str, KERNEL_MIN))}"))

        # VC-03 Docker floor
        dock = parse_docker_version(facts.docker_version_text)
        if dock is None:
            findings.append(Finding("VC-03", _SEV_CRITICAL,
                                    "docker version unparseable — cannot assess baseline"))
            cannot_assess = True
        elif dock < DOCKER_MIN:
            findings.append(Finding("VC-03", _SEV_CRITICAL,
                                    f"docker {dock[0]}.{dock[1]} < {DOCKER_MIN[0]}.{DOCKER_MIN[1]}"))

        # VC-04 compose v2
        if not facts.docker_compose_ok:
            findings.append(Finding("VC-04", _SEV_CRITICAL,
                                    "docker compose v2 plugin not available"))

        # VC-05 cgroup v2
        ctrl = facts.cgroup_controllers.strip()
        if not ctrl:
            findings.append(Finding("VC-05", _SEV_CRITICAL,
                                    "cgroup.controllers missing/empty — cannot confirm v2 hierarchy"))
            cannot_assess = True
        elif "cpu" not in ctrl.split():
            findings.append(Finding("VC-05", _SEV_CRITICAL,
                                    "cgroup v2 unified hierarchy not confirmed (no cpu controller)"))

        # VC-06/VC-07 port boundaries
        listening = parse_listening(facts.listening_lines)
        if listening is None:
            findings.append(Finding("VC-06", _SEV_CRITICAL,
                                    "listening-socket observations missing/unparseable"))
            cannot_assess = True
        else:
            bound = {}
            for local, port in listening:
                bound.setdefault(port, []).append(local)
            for port in GATEWAY_PORTS:
                if port in bound:
                    findings.append(Finding("VC-06", _SEV_CRITICAL,
                                            f"gateway port {port} already bound on {bound[port]}"))
            for port in FORBIDDEN_PUBLIC:
                publics = [a for a in bound.get(port, []) if a in _PUBLIC_LOCAL]
                if publics:
                    findings.append(Finding("VC-07", _SEV_CRITICAL,
                                            f"port {port} publicly bound on {publics} — must stay internal"))
                elif port in bound:
                    findings.append(Finding("VC-07", _SEV_WARNING,
                                            f"port {port} bound on loopback only — verify intentional"))

        # VC-08..VC-10 firewall profile
        fw = parse_ufw(facts.ufw_status_text)
        if fw is None:
            findings.append(Finding("VC-08", _SEV_CRITICAL,
                                    "ufw status unparseable — cannot assess firewall profile"))
            cannot_assess = True
        else:
            active, default_in, ports = fw
            if not active:
                findings.append(Finding("VC-08", _SEV_CRITICAL, "ufw is not active"))
            if default_in not in ("deny", "drop", "reject"):
                findings.append(Finding("VC-09", _SEV_CRITICAL,
                                        f"ufw default incoming policy {default_in!r} is not deny/drop"))
            bad = sorted(p for p in ports if p not in ALLOWED_INGRESS)
            if bad:
                findings.append(Finding("VC-10", _SEV_CRITICAL,
                                        f"ingress allowlist outside {{22,80,443}}: {bad}"))

        # VC-11 required planning env (names only — values never read out)
        env = facts.env or {}
        for name in REQUIRED_ENV:
            if not str(env.get(name, "")).strip():
                findings.append(Finding("VC-11", _SEV_CRITICAL,
                                        f"required planning env variable missing/empty: {name}"))

        # VC-12 installer ref pinned
        ref = str(env.get("DOKPLOY_INSTALLER_REF", "")).strip()
        if ref and not re.fullmatch(r"v\d+\.\d+\.\d+", ref):
            findings.append(Finding("VC-12", _SEV_CRITICAL,
                                    f"installer ref {ref!r} is not a pinned semver tag"))

        # VC-13 domain shape (no scheme, no credentials)
        dom = str(env.get("DOKPLOY_DOMAIN", "")).strip()
        if dom and ("://" in dom or "@" in dom or "/" in dom or " " in dom):
            findings.append(Finding("VC-13", _SEV_CRITICAL,
                                    "deployment domain malformed (scheme, path or credential material)"))

        # VC-14 owner attestations
        att = facts.attestations or {}
        for gate in REQUIRED_GATES:
            if not str(att.get(gate, "")).strip():
                findings.append(Finding("VC-14", _SEV_CRITICAL,
                                        f"owner sign-off attestation missing: {gate}"))

        if cannot_assess:
            verdict = VERDICT_CANNOT_ASSESS
        elif any(f.severity == _SEV_CRITICAL for f in findings):
            verdict = VERDICT_NOT_READY
        else:
            verdict = VERDICT_READY

        ordered = tuple(sorted(findings, key=lambda f: (f.code, f.severity, f.detail)))
        counts = {
            "total": len(ordered),
            "critical": sum(1 for f in ordered if f.severity == _SEV_CRITICAL),
            "warning": sum(1 for f in ordered if f.severity == _SEV_WARNING),
        }
        return StageCReport(verdict, ordered, _env_fingerprint(env), counts)


# ---------------------------------------------------------------------------
# CLI (dry-run — the only I/O is reading a facts JSON; no sockets ever)
# ---------------------------------------------------------------------------

def _facts_from_json(data: Mapping[str, Any]) -> HostFacts:
    return HostFacts(
        os_pretty_name=str(data.get("os_pretty_name", "")),
        kernel_release=str(data.get("kernel_release", "")),
        docker_version_text=str(data.get("docker_version_text", "")),
        docker_compose_ok=bool(data.get("docker_compose_ok", False)),
        cgroup_controllers=str(data.get("cgroup_controllers", "")),
        listening_lines=tuple(str(x) for x in data.get("listening_lines", ())),
        ufw_status_text=str(data.get("ufw_status_text", "")),
        env={str(k): str(v) for k, v in data.get("env", {}).items()},
        attestations={str(k): str(v) for k, v in data.get("attestations", {}).items()},
    )


def main(argv: Tuple[str, ...] | None = None) -> int:
    argv = tuple(sys.argv[1:] if argv is None else argv)
    facts_file: Path | None = None
    as_json = False
    it = iter(argv)
    for a in it:
        if a == "--facts-file":
            facts_file = Path(next(it, ""))
        elif a == "--json":
            as_json = True
    if facts_file is None or not facts_file.is_file():
        print("usage: stage_c_runbook_validator.py --facts-file FACTS.json [--json]",
              file=sys.stderr)
        return 2
    try:
        data = json.loads(facts_file.read_text(encoding="utf-8"))
        facts = _facts_from_json(data)
    except (ValueError, OSError) as exc:
        # fail closed on unparseable configs — never guess
        print(f"cannot-assess: unparseable facts file ({type(exc).__name__})", file=sys.stderr)
        return 2
    report = StageCRunbookValidator().validate(facts)
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"VERDICT: {report.verdict}  findings={report.counts}")
        for f in report.findings:
            print(f"  [{f.severity.upper():8s}] {f.code}: {f.detail}")
    return {VERDICT_READY: 0, VERDICT_NOT_READY: 1}.get(report.verdict, 2)


if __name__ == "__main__":
    sys.exit(main())
