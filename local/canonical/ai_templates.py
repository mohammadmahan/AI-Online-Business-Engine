"""Phase 8 M3 — prompt/template versioning registry (D-067).

Prompts move OUT of executable code into a versioned registry:
`local/templates/<task_type>/vX.Y.Z.json`. Invariants (battery-
asserted): strict schema validation at load (the D-062 subset),
monotonic semver per task (a shipped version is immutable — a change
is a NEW version), content hashes pinned at load, unknown template
ids refused Class-B by the engine.

Every rendered request carries (template_id, template_hash) so any
AiProposal/D-065 record is reproducible and quality regressions are
attributable to a template change. Template ACTIVATION (which version
a task uses) is deterministic configuration, never model choice.
"""

import hashlib
import json
import os
import re
from typing import Dict, Optional, Tuple

from canonical.ai_contracts import (SchemaError, validate_output,
                                    validate_ai_output)

TEMPLATES_ROOT = os.path.join("local", "templates")
_TEMPLATE_FILE_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\.json$")


class TemplateError(ValueError):
    """Registry/contract violation (Class-B, never silently repaired)."""


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _contract_probe(schema: dict):
    """Shape probe for template contract validation: build the minimal
    skeleton the schema demands so validate_output exercises
    _check_schema on every node (permissive schemas and unknown
    keywords are load-time errors, mirroring D-062)."""
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        out = {}
        for name, sub in (schema.get("properties") or {}).items():
            out[name] = _contract_probe(sub)
        return out
    if t == "array" or "items" in schema:
        item = schema.get("items") or {"type": "string"}
        return [_contract_probe(item)]
    if t == "integer" or t == "number":
        return 0
    if t == "boolean":
        return True
    return ""


def content_hash(template: Dict) -> str:
    """sha256 over the canonical JSON of the template EXCLUDING any
    pre-recorded template_hash key (self-referential exclusion, D-067):
    the hash pins the CONTENT, so it must be computable both before a
    hash exists and when verifying a recorded one."""
    body = {k: v for k, v in template.items()
            if k != "template_hash"}
    return hashlib.sha256(_canonical(body).encode(
        "utf-8")).hexdigest()


def _validate_template(t: Dict, path: str) -> None:
    required = ("template_id", "version", "schema_id", "prompt_text",
                "response_contract")
    missing = [k for k in required if k not in t]
    if missing:
        raise TemplateError(f"{path}: template missing {missing}")
    if not isinstance(t["prompt_text"], str) or not t["prompt_text"]:
        raise TemplateError(f"{path}: prompt_text must be non-empty")
    if not isinstance(t["response_contract"], dict):
        raise TemplateError(f"{path}: response_contract must be an object")
    try:
        validate_output(t["response_contract"],
                        _contract_probe(t["response_contract"]))
    except SchemaError as exc:
        raise TemplateError(f"{path}: response_contract invalid: {exc}")
    # placeholders must be simple {names} — renderable deterministically
    for name in re.findall(r"\{(\w+)\}", t["prompt_text"]):
        if not name:
            raise TemplateError(f"{path}: empty placeholder")
    # hash drift guard: a RECORDED hash must match the CONTENT
    # (self-referential key excluded) — tampering fails loudly
    if t.get("template_hash") is not None \
            and t["template_hash"] != content_hash(t):
        raise TemplateError(
            f"{path}: recorded template_hash does not match content "
            "(regression guard)")
    m = _TEMPLATE_FILE_RE.match(os.path.basename(path))
    if m and f"v{m.group(1)}.{m.group(2)}.{m.group(3)}" != t["version"]:
        raise TemplateError(
            f"{path}: version field {t['version']!r} does not match "
            "the file name")


class TemplateRegistry:
    """Load and enforce the versioned template registry (D-067)."""

    def __init__(self, root: str = TEMPLATES_ROOT):
        self.root = root
        self._templates: Dict[Tuple[str, str], Dict] = {}
        self._hashes: Dict[Tuple[str, str], str] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not os.path.isdir(self.root):
            return
        for task_dir in sorted(os.listdir(self.root)):
            task_path = os.path.join(self.root, task_dir)
            if not os.path.isdir(task_path):
                continue
            for fname in sorted(os.listdir(task_path)):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(task_path, fname)
                with open(path, encoding="utf-8") as f:
                    t = json.load(f)
                _validate_template(t, path)
                key = (t["template_id"], t["version"])
                if key in self._templates:
                    raise TemplateError(
                        f"duplicate template {key} at {path}")
                t["template_hash"] = content_hash(t)
                self._templates[key] = t
                self._hashes[key] = t["template_hash"]

    def versions(self, template_id: str) -> list:
        return sorted(v for (tid, v) in self._templates
                      if tid == template_id)

    def get(self, template_id: str, version: Optional[str] = None) -> Dict:
        """Fetch a template; default = highest shipped semver
        (deterministic activation). Unknown id → TemplateError (B)."""
        versions = self.versions(template_id)
        if not versions:
            raise TemplateError(
                f"unknown template_id {template_id!r} (Class B)")
        if version is None:
            version = versions[-1]
        t = self._templates.get((template_id, version))
        if t is None:
            raise TemplateError(
                f"unknown version {version!r} for {template_id!r}; "
                f"shipped: {versions} (Class B)")
        return dict(t)

    def hash_of(self, template_id: str,
                version: Optional[str] = None) -> str:
        return self._hashes[(template_id, version or
                             self.versions(template_id)[-1])]

    def register(self, template: Dict) -> Dict:
        """Register a NEW version (monotonic semver; immutable past).

        Overwriting or removing a shipped version is refused — prompt
        changes are new versions, never silent edits (D-067).
        """
        # validate CONTENT: any pre-recorded hash from a copied
        # template describes the OLD content and is not authoritative
        # here — a new version gets a FRESH hash after validation
        body = {k: v for k, v in template.items()
                if k != "template_hash"}
        _validate_template(body, "<register:%s>" % template.get(
            "template_id"))
        tid, ver = template["template_id"], template["version"]
        existing = self.versions(tid)
        if ver in existing:
            raise TemplateError(
                f"template {tid} v{ver} already shipped — immutable "
                "(a change is a NEW version, D-067)")
        bare = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
        m = bare.match(ver) if isinstance(ver, str) else None
        if not m:
            raise TemplateError(
                f"version {ver!r} is not semver vX.Y.Z")
        new = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        for old in existing:
            om = bare.match(old)
            if om and (int(om.group(1)), int(om.group(2)),
                       int(om.group(3))) >= new:
                raise TemplateError(
                    f"non-monotonic semver: {ver} <= shipped {old}")
        template = dict(template, template_hash=content_hash(template))
        self._templates[(tid, ver)] = template
        self._hashes[(tid, ver)] = template["template_hash"]
        return dict(template)


class TemplateEngine:
    """Deterministic prompt rendering (D-067).

    render() fills {placeholders} from context; a missing placeholder
    key raises (never silently renders a half-filled prompt). The
    response contract is validated against the model output by the
    router (D-062), so template and contract travel together.
    """

    def __init__(self, registry: TemplateRegistry):
        self.registry = registry

    def render(self, template_id: str, context: Dict,
               version: Optional[str] = None
               ) -> Tuple[str, str, str, Dict]:
        """Returns (prompt_text, template_id, template_hash, contract).

        The prompt_text embeds its own ids so the provider sees the
        exact template identity in-band.
        """
        t = self.registry.get(template_id, version)
        text = t["prompt_text"]
        for name in re.findall(r"\{(\w+)\}", text):
            if name not in context:
                raise TemplateError(
                    f"template {t['template_id']} {t['version']}: missing "
                    f"context key {name!r} (never render half-filled)")
            text = text.replace("{" + name + "}",
                                str(context[name]))
        return (text, t["template_id"], t["template_hash"],
                t["response_contract"])

    def validate_against_contract(self, template_id: str,
                                  output, version: Optional[str] = None):
        """Validate model output against the template's pinned
        response contract (same strict validator as D-062)."""
        t = self.registry.get(template_id, version)
        return validate_ai_output(t["schema_id"], output)


def render_into_request(request, engine: TemplateEngine,
                        template_id: str, context: Dict,
                        version: Optional[str] = None):
    """D-067 integration bridge: render a template INTO an existing
    AiRequest (a NEW request object is returned — the original is
    untouched) so the REQUEST trail carries template_id +
    template_hash for reproducibility. NOTE: the router validates the
    MODEL output against the strict response contract — extra request
    metadata keys never reach the proposal payload (the mock echoes
    only contract fields), so tasks carry the ids on the REQUEST side
    and in D-065 observability records, not in model output."""
    import dataclasses
    prompt_text, tid, thash, _contract = engine.render(
        template_id, context, version)
    payload = dict(request.prompt_payload)
    payload["prompt"] = prompt_text
    payload["template_id"] = tid
    payload["template_hash"] = thash
    return dataclasses.replace(request, prompt_payload=payload)
