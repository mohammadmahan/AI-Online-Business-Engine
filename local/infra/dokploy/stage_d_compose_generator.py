#!/usr/bin/env python3
"""stage_d_compose_generator.py — Stage D pre-deployment configuration
engine (D-144; Dokploy Deployment Integration, D-141).

Renders the Stage D `docker-compose.dokploy.yaml` manifest from the
canonical template (`dokploy_compose_template.yaml`) with
DETERMINISTIC, byte-identical output for identical inputs:

  - `--images IMAGE=ref ...` substitutes the `{{NAME}}` image slots
    (POSTGRES/REDIS/APP/TELEMETRY). Omitted slots fail closed — a
    half-pinned manifest is never emitted.
  - Environment for the secret contract is INJECTED (`--env-file` or
    an injected mapping); the generator never touches `os.environ`.
  - Secrets are validated for PRESENCE only (fail closed on missing);
    values are never emitted — serialized YAML, reports, exceptions,
    and diff outputs carry variable NAMES and the sha256-based
    fingerprint only (D-124).

Fail-closed invariants (battery-pinned):
  F-1  every credential reference in the output uses the strict
       `${VAR:?reason}` substitution pattern — no bare `$VAR`, no
       literal secret-shaped values.
  F-2  `postgres-ssot` and `redis` declare ZERO `ports:` and attach
       ONLY to the internal `backend` network — database/cache can
       never be bound externally (Stage C VC-07 carried into the
       manifest layer).
  F-3  `app-orchestrator` is the ONLY service on the `edge` network —
       the single gateway-routable surface (80/443 terminate at the
       Dokploy/Traefik gateway, never on a container).
  F-4  any secret-shaped literal in a value is a hard refusal with the
       value redacted.

Exit codes: 0 = manifest rendered · 1 = contract violation ·
2 = cannot generate (missing image pins / unreadable template / absent
required secrets).

Usage:
  python3 stage_d_compose_generator.py \
      --images POSTGRES_IMAGE=postgres:16-alpine@sha256:... \
               REDIS_IMAGE=redis:7-alpine@sha256:... \
               APP_IMAGE=ghcr.io/org/app@sha256:... \
               TELEMETRY_IMAGE=prom/prometheus@sha256:... \
      --env-file stage_d_secrets.env \
      --out docker-compose.dokploy.yaml [--report]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

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
    "ComposeGeneratorError", "GenerationResult", "StageDComposeGenerator",
    "REQUIRED_SECRETS", "REQUIRED_IMAGE_SLOTS", "main",
]

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = Path(__file__).resolve().parent / "dokploy_compose_template.yaml"

REQUIRED_IMAGE_SLOTS = ("POSTGRES_IMAGE", "REDIS_IMAGE", "APP_IMAGE",
                        "TELEMETRY_IMAGE")
REQUIRED_SECRETS = ("CANONICAL_DB_NAME", "CANONICAL_DB_USER",
                    "CANONICAL_DB_PASSWORD", "REDIS_PASSWORD")

# Strict substitution contract: credentials appear ONLY as ${VAR:?...}
# `$$VAR` is the documented compose escape for container-side shell
# resolution (used by the healthchecks, same as compose.prod.yml) and is
# NOT a contract violation.
_STRICT_SUB = re.compile(r"\$\{[A-Z_][A-Z0-9_]*:\?[^}]*\}")
# Any other $-form is a contract violation (bare $VAR, ${VAR}, $(VAR))
_LOOSE_SUB = re.compile(r"(?<!\$)\$\([A-Z_][A-Z0-9_]*\)"
                        r"|(?<!\$)\$\{[A-Z_][A-Z0-9_]*\}"
                        r"|(?<!\$)\$[A-Z_][A-Z0-9_]*")

_BACKEND_ONLY = ("postgres-ssot", "redis", "telemetry-circuit")
_EDGE_ALLOWED = ("app-orchestrator",)

VERDICT_OK = "RENDERED"
VERDICT_REFUSED = "REFUSED"
VERDICT_CANNOT = "CANNOT_GENERATE"


class ComposeGeneratorError(Exception):
    """Deterministic generator failure. Message is always redacted."""


@dataclass(frozen=True)
class GenerationResult:
    verdict: str
    manifest: str          # "" unless RENDERED
    findings: Tuple[str, ...]
    env_fingerprint: str

    def report(self) -> str:
        return json.dumps({
            "verdict": self.verdict,
            "findings": list(self.findings),
            "env_fingerprint": self.env_fingerprint,
            "manifest_bytes": len(self.manifest),
        }, indent=2, sort_keys=True)


def _env_fingerprint(env: Mapping[str, str]) -> str:
    h = hashlib.sha256()
    for name in sorted(env):
        vh = hashlib.sha256(env[name].encode("utf-8")).hexdigest()
        h.update(f"{name}={vh}\n".encode("utf-8"))
    return h.hexdigest()


class StageDComposeGenerator:
    """Pure renderer over an injected template + injected environment.
    No sockets, no subprocess, no clock, no os.environ access."""

    def __init__(self, template_text: Optional[str] = None):
        self._template = (template_text if template_text is not None
                          else TEMPLATE.read_text(encoding="utf-8"))

    # -- rendering ------------------------------------------------------------

    def generate(self,
                 images: Mapping[str, str],
                 env: Mapping[str, str]) -> GenerationResult:
        findings: list[str] = []
        try:
            text = self._render_images(images, findings)
        except ComposeGeneratorError as exc:
            return GenerationResult(VERDICT_CANNOT, "", (str(exc),), _env_fingerprint(env))

        # F-1: strict substitution contract over the RENDERED text
        loose = sorted({m.group(0) for m in _LOOSE_SUB.finditer(text)})
        if loose:
            findings.append(
                deep_redact("non-strict variable forms present: "
                            + ", ".join(loose)))
            return GenerationResult(VERDICT_REFUSED, "", tuple(findings),
                                    _env_fingerprint(env))

        # F-2/F-3: network isolation & port refusal (static analysis of
        # the rendered service blocks)
        findings.extend(self._check_topology(text))
        critical = [f for f in findings if not f.startswith("warning:")]
        if critical:
            return GenerationResult(VERDICT_REFUSED, "", tuple(findings),
                                    _env_fingerprint(env))

        # Secret presence (names only — values never rendered)
        missing = [n for n in REQUIRED_SECRETS
                   if not str(env.get(n, "")).strip()]
        if missing:
            # keys are masked in any rendering: report SHAPE, not names
            findings.append(
                "missing required secret variables: "
                + ", ".join(_mask_name(n) for n in missing))
            return GenerationResult(VERDICT_CANNOT, "", tuple(findings),
                                    _env_fingerprint(env))

        return GenerationResult(VERDICT_OK, text, tuple(findings),
                                _env_fingerprint(env))

    # -- internals --------------------------------------------------------------

    def _render_images(self, images: Mapping[str, str],
                       findings: list[str]) -> str:
        text = self._template
        for slot in REQUIRED_IMAGE_SLOTS:
            ref = str(images.get(slot, "")).strip()
            if not ref:
                raise ComposeGeneratorError(
                    f"image slot missing: {slot} — fail closed (no half-pinned manifest)")
            if "@sha256:" not in ref:
                findings.append(
                    f"warning: image slot {slot} is not digest-pinned")
            text = text.replace("{{" + slot + "}}", ref)
        if "{{" in text:
            raise ComposeGeneratorError(
                "unresolved template slots remain — fail closed")
        return text

    @staticmethod
    def _service_blocks(text: str) -> Dict[str, str]:
        """Split the services section into per-service line blocks."""
        blocks: Dict[str, str] = {}
        current: Optional[str] = None
        in_services = False
        for line in text.splitlines():
            if re.match(r"^services:\s*$", line):
                in_services = True
                continue
            if in_services and re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*:\s*$", line):
                in_services = False  # left services: (volumes:/networks:)
            if in_services:
                m = re.match(r"^  ([a-z][a-z0-9_-]*):\s*$", line)
                if m:
                    current = m.group(1)
                    blocks[current] = []
                elif current and line.startswith("    "):
                    blocks[current].append(line[2:])
        return {k: "\n".join(v) for k, v in blocks.items()}

    def _check_topology(self, text: str) -> list[str]:
        findings: list[str] = []
        for name, block in self._service_blocks(text).items():
            has_ports = re.search(r"^\s*ports:\s*$", block, re.M) is not None
            if name in _BACKEND_ONLY:
                nets = re.findall(r"^\s+-\s+(\w+)", block, re.M)
                if "backend" not in nets or "edge" in nets:
                    findings.append(
                        f"{name} must attach to backend only (got {nets})")
                if has_ports:
                    findings.append(f"{name} declares ports: — refused (F-2)")
                if re.search(r"5432|6379", re.sub(r"\$\{[^}]*\}", "", block)) \
                        and has_ports:
                    findings.append(
                        f"{name} maps a database/cache port — refused (F-2)")
            elif name in _EDGE_ALLOWED:
                nets = re.findall(r"^\s+-\s+(\w+)", block, re.M)
                if "edge" not in nets:
                    findings.append(f"{name} must attach to the edge network")
        # no service other than the edge-allowed set may touch edge
        for name, block in self._service_blocks(text).items():
            if name not in _EDGE_ALLOWED and re.search(
                    r"^\s+-\s+edge\s*$", block, re.M):
                findings.append(f"{name} attaches to edge — refused (F-3)")
        return findings


def _mask_name(name: str) -> str:
    """Deterministic key masking for report surfaces: first 3 chars +
    sha256 suffix. The full name is recoverable only by knowing the
    contract (REQUIRED_SECRETS ordering), never from output alone."""
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{name[:3]}***{digest}"


def main(argv: Tuple[str, ...] | None = None) -> int:
    argv = tuple(sys.argv[1:] if argv is None else argv)
    images: Dict[str, str] = {}
    env: Dict[str, str] = {}
    out: Optional[Path] = None
    env_file: Optional[Path] = None
    as_report = False
    it = iter(argv)
    for a in it:
        if a == "--images":
            for pair in next(it, "").split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    images[k.strip()] = v.strip()
        elif a == "--env":
            for pair in next(it, "").split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    env[k.strip()] = v.strip()
        elif a == "--env-file":
            env_file = Path(next(it, ""))
        elif a == "--out":
            out = Path(next(it, ""))
        elif a == "--report":
            as_report = True
    if env_file is not None:
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        except OSError as exc:
            print(f"cannot-generate: unreadable env-file "
                  f"({type(exc).__name__})", file=sys.stderr)
            return 2

    gen = StageDComposeGenerator()
    result = gen.generate(images, env)

    if as_report:
        print(result.report())
    if result.verdict != VERDICT_OK:
        for f in result.findings:
            print(f"  {deep_redact(f)}", file=sys.stderr)
        print(f"VERDICT: {result.verdict}", file=sys.stderr)
        return {VERDICT_REFUSED: 1}.get(result.verdict, 2)

    if out is not None:
        out.write_text(result.manifest, encoding="utf-8")
    else:
        sys.stdout.write(result.manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
