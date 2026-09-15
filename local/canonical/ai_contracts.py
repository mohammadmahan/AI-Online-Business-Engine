"""Phase 7 M1 — AI structured-output contracts (strict JSON Schema).

Implements the three v1 output contracts from
docs/phases/phase-07-ai-runtime.md §3.2 with a deterministic,
pure-stdlib validator over a DOCUMENTED JSON-Schema subset:

    type, properties, required, additionalProperties:false (strict),
    enum, items, minItems, maxItems, minLength, maxLength, pattern

Strict mode is mandatory for AI output: `additionalProperties` must be
false at every object level, so a model cannot smuggle untyped fields
into canonical flows. Unknown keywords in a SCHEMA are rejected loudly
(SchemaError) — never silently ignored — so schema drift cannot widen
the contract unnoticed.

Failure classification (D-052 alignment, phase-07 doc §4): validation
failures of AI OUTPUT are Class B (data invariant, never retried
blindly). Malformed SCHEMAS are programmer errors (SchemaError) that
must fail fast at load time, not at inference time.

Controlled vocabulary: contracts reference codes, never display
labels; Color/Size/Category vocabulary never originates from the model
(RULES §8 — the runtime never fills vocabulary gaps with guesses).
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

# --- D-052-aligned error types ----------------------------------------------


class SchemaError(Exception):
    """Malformed schema (programmer error) — fail fast at load time."""


class OutputValidationError(Exception):
    """AI output failed its contract — Class B, never silently repaired."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []
        self.failure_class = "B"  # D-052: data invariant/schema


_ALLOWED_TYPES = {"object", "array", "string", "integer", "number",
                  "boolean"}
_ALLOWED_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "enum",
    "items", "minItems", "maxItems", "minLength", "maxLength", "pattern",
    "$schema", "title", "description",
}


def _check_schema(node, path: str = "schema") -> None:
    """Recursively reject anything outside the documented subset."""
    if not isinstance(node, dict):
        raise SchemaError(f"{path}: schema node must be an object")
    for key in node:
        if key not in _ALLOWED_KEYWORDS:
            raise SchemaError(
                f"{path}: unsupported schema keyword {key!r} — the "
                "documented JSON-Schema subset only (strict mode)")
    t = node.get("type")
    if t not in _ALLOWED_TYPES:
        raise SchemaError(f"{path}: 'type' must be one of "
                          f"{sorted(_ALLOWED_TYPES)}, got {t!r}")
    if "pattern" in node:
        try:
            re.compile(node["pattern"])
        except re.error as exc:
            raise SchemaError(f"{path}: bad pattern: {exc}")
    if t == "object":
        props = node.get("properties", {})
        if not isinstance(props, dict):
            raise SchemaError(f"{path}: 'properties' must be an object")
        if node.get("additionalProperties") is not False:
            raise SchemaError(
                f"{path}: strict mode requires additionalProperties:false")
        for name, sub in props.items():
            _check_schema(sub, f"{path}.properties.{name}")
        req = node.get("required", [])
        if not isinstance(req, list) or not set(req).issubset(props):
            raise SchemaError(
                f"{path}: 'required' entries must exist in 'properties'")
    if t == "array":
        if "items" not in node:
            raise SchemaError(f"{path}: array requires 'items'")
        _check_schema(node["items"], f"{path}.items")


def _validate(node, schema, path: str, errors: List[str]) -> None:
    t = schema.get("type")
    if t == "object":
        if not isinstance(node, dict):
            errors.append(f"{path}: expected object, got {type(node).__name__}")
            return
        for req in schema.get("required", []):
            if req not in node:
                errors.append(f"{path}.{req}: missing required field")
        for name, sub in schema.get("properties", {}).items():
            if name in node:
                _validate(node[name], sub, f"{path}.{name}", errors)
        extra = set(node) - set(schema.get("properties", {}))
        for name in sorted(extra):
            errors.append(f"{path}.{name}: additional property not allowed "
                          "(strict mode)")
    elif t == "array":
        if not isinstance(node, list):
            errors.append(f"{path}: expected array, got {type(node).__name__}")
            return
        if "minItems" in schema and len(node) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(node) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        for i, item in enumerate(node):
            _validate(item, schema["items"], f"{path}[{i}]", errors)
    elif t == "string":
        if not isinstance(node, str):
            errors.append(f"{path}: expected string, got "
                          f"{type(node).__name__}")
            return
        if "minLength" in schema and len(node) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(node) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], node):
            errors.append(f"{path}: does not match pattern {schema['pattern']!r}")
    elif t in ("integer", "number"):
        if isinstance(node, bool) or not isinstance(node, (int, float)):
            errors.append(f"{path}: expected {t}, got {type(node).__name__}")
            return
        if t == "integer" and not isinstance(node, int):
            errors.append(f"{path}: expected integer, got float")
    elif t == "boolean":
        if not isinstance(node, bool):
            errors.append(f"{path}: expected boolean, got "
                          f"{type(node).__name__}")
    if "enum" in schema and node not in schema["enum"]:
        errors.append(f"{path}: {node!r} not in enum {schema['enum']!r}")


def validate_output(schema: dict, output) -> Optional[List[str]]:
    """Validate AI output against a schema. Returns None when valid,
    else the deterministic error list (Class B evidence)."""
    _check_schema(schema)  # programmer error if malformed — fail fast
    errors: List[str] = []
    _validate(output, schema, "$", errors)
    return errors or None


# --- v1 contracts (phase-07 doc §3.2) ----------------------------------------

# Canonical Product ID shape is hex-with-dashes per D-014/D-017 fixtures;
# existence checks belong to the calling flow, never the model.
_PRODUCT_ID_PATTERN = "^[0-9a-fA-F-]{8,64}$"

CONTENT_IDEA_PROPOSAL_V1 = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "content_idea_proposal.v1",
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "target_lifecycle_state", "rationale"],
    "properties": {
        "title": {"type": "string", "minLength": 3, "maxLength": 200},
        "working_notes": {"type": "string", "maxLength": 2000},
        # AI may only PROPOSE new ideas at the lifecycle root (D-060):
        "target_lifecycle_state": {"type": "string", "enum": ["Backlog"]},
        "rationale": {"type": "string", "minLength": 10, "maxLength": 1000},
    },
}

CAPTION_PROPOSAL_V1 = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "caption_proposal.v1",
    "type": "object",
    "additionalProperties": False,
    "required": ["caption_fa", "hashtags", "alt_text"],
    "properties": {
        "caption_fa": {"type": "string", "minLength": 5, "maxLength": 2200},
        "hashtags": {"type": "array", "items": {"type": "string",
                                                "minLength": 1,
                                                "maxLength": 60},
                     "minItems": 0, "maxItems": 30},
        "alt_text": {"type": "string", "minLength": 5, "maxLength": 500},
        # opaque reference ONLY — the model never invents media
        "media_ref": {"type": "string", "maxLength": 200},
    },
}

PRODUCT_DESCRIPTION_ENRICHMENT_V1 = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "product_description_enrichment.v1",
    "type": "object",
    "additionalProperties": False,
    "required": ["product_id", "variant_ids", "description_fa",
                 "seo_title_fa", "seo_keywords", "rationale"],
    "properties": {
        "product_id": {"type": "string", "pattern": _PRODUCT_ID_PATTERN},
        "variant_ids": {"type": "array",
                        "items": {"type": "string",
                                  "pattern": _PRODUCT_ID_PATTERN},
                        "minItems": 0, "maxItems": 100},
        "description_fa": {"type": "string", "minLength": 20,
                           "maxLength": 5000},
        "seo_title_fa": {"type": "string", "minLength": 5, "maxLength": 70},
        "seo_keywords": {"type": "array",
                         "items": {"type": "string", "minLength": 2,
                                   "maxLength": 40},
                         "minItems": 1, "maxItems": 15},
        "rationale": {"type": "string", "minLength": 10, "maxLength": 1000},
    },
}

# versioned registry (contract evolution = new version id + amendment)
AI_OUTPUT_SCHEMAS: Dict[str, dict] = {
    "content_idea_proposal.v1": CONTENT_IDEA_PROPOSAL_V1,
    "caption_proposal.v1": CAPTION_PROPOSAL_V1,
    "product_description_enrichment.v1": PRODUCT_DESCRIPTION_ENRICHMENT_V1,
}


def get_schema(schema_id: str) -> dict:
    if schema_id not in AI_OUTPUT_SCHEMAS:
        raise SchemaError(f"unknown schema id: {schema_id!r}")
    schema = AI_OUTPUT_SCHEMAS[schema_id]
    _check_schema(schema)
    return schema


def validate_ai_output(schema_id: str, output) -> Dict:
    """Validate AI output against a registered contract.

    Returns {"valid": True, "schema": id} or
    {"valid": False, "schema": id, "errors": [...], "failure_class": "B"}.
    """
    schema = get_schema(schema_id)
    errors = validate_output(schema, output)
    if errors is None:
        return {"valid": True, "schema": schema_id}
    return {"valid": False, "schema": schema_id, "errors": errors,
            "failure_class": "B"}


def load_schemas_fixture(path: str) -> Dict[str, dict]:
    """Load schemas from a JSON file (for parity/CI vector pinning)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for sid, schema in data.items():
        _check_schema(schema)
    return data
