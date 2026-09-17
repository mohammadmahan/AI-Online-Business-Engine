"""Phase 16 M1 — asset & versioning contracts (D-097).

Canonical MediaAsset / ContentVersion schemas, content-addressability
rules, append-only version-graph validation, mime/hash discipline,
and variant specifications — pure functions only (no I/O, no
adapters, no network), mirroring the D-069..D-096 contract
discipline. Binaries stay behind the Phase 3 MediaStore abstraction
(D-049/D-056); this module handles identity and rules only.
"""

import hashlib
import re
from typing import Dict, Optional, Tuple

SOURCE_SYSTEM = "assets"
OP_ASSET = "asset"

# --- limits & allow-lists (D-098) --------------------------------------------

MAX_ASSET_BYTES = 50 * 1024 * 1024      # 50 MB cap (matches D-073 boundary)

MIME_ALLOW_LIST = (
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/quicktime",
    "application/pdf",
    "text/plain",
)

# magic-byte signatures for the mime cross-check (pure prefix rules —
# NOT a full type detector; anything unrecognised passes if the mime
# is textual or unknown to the table, per D-098's "contradicting"
# standard)
_CONTENT_SIGNATURES: Tuple[Tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),      # WEBP: RIFF....WEBP
    (b"%PDF-", "application/pdf"),
)

_ID_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,128}$")


class AssetContractError(ValueError):
    """Local Class-B rejection — the asset never reaches storage."""


def checksum_bytes(data: bytes) -> str:
    """SHA-256 content-addressable identity (D-097)."""
    return hashlib.sha256(data).hexdigest()


def validate_mime(mime_type: str) -> str:
    if not isinstance(mime_type, str) or mime_type not in MIME_ALLOW_LIST:
        raise AssetContractError(
            f"mime_type must be one of {list(MIME_ALLOW_LIST)} (D-098)")
    return mime_type


def mime_contradicts(data: bytes, mime_type: str) -> bool:
    """True only when a KNOWN signature contradicts the declared mime
    (e.g. bytes are a PNG but declared image/jpeg). Unrecognised
    content never contradicts (D-098: reject contradictions, not
    unknowns)."""
    for magic, detected in _CONTENT_SIGNATURES:
        if data[:len(magic)] == magic:
            if mime_type != detected:
                return True
            return False
    # WEBP needs the RIFF....WEBP shape check
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" \
            and mime_type != "image/webp":
        return True
    return False


def validate_asset(asset: Dict, data: Optional[bytes] = None) -> Dict:
    """Strict local validation (D-098). When `data` is supplied the
    declared checksum/size/mime are cross-checked against it."""
    if not isinstance(asset, dict):
        raise AssetContractError("asset must be a dict")
    asset_id = asset.get("asset_id")
    if not isinstance(asset_id, str) or not _ID_RE.match(asset_id):
        raise AssetContractError(
            "asset_id must be 1-128 chars of [A-Za-z0-9_.:@-]")
    checksum = asset.get("checksum")
    if not isinstance(checksum, str) or \
            not re.match(r"^[0-9a-f]{64}$", checksum):
        raise AssetContractError(
            "checksum must be a lowercase SHA-256 hex digest")
    mime = validate_mime(asset.get("mime_type"))
    size = asset.get("file_size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise AssetContractError("file_size_bytes must be a positive int")
    if size > MAX_ASSET_BYTES:
        raise AssetContractError(
            f"file_size_bytes {size} exceeds cap {MAX_ASSET_BYTES} "
            "(D-098)")
    if data is not None:
        if checksum_bytes(data) != checksum:
            raise AssetContractError(
                "declared checksum does not match content (D-098 "
                "Class-B before storage)")
        if len(data) != size:
            raise AssetContractError(
                "declared file_size_bytes does not match content")
        if mime_contradicts(data, mime):
            raise AssetContractError(
                f"declared mime {mime} contradicts detected content "
                "signature (D-098 Class-B before storage)")
    if not isinstance(asset.get("metadata", {}), dict):
        raise AssetContractError("metadata must be a dict")
    return asset


def validate_version(version: Dict) -> Dict:
    """ContentVersion validation: monotonic integer version number,
    parent links consistent (D-097 append-only discipline)."""
    if not isinstance(version, dict):
        raise AssetContractError("version must be a dict")
    content_id = version.get("content_id")
    if not isinstance(content_id, str) or not _ID_RE.match(content_id):
        raise AssetContractError(
            "content_id must be 1-128 chars of [A-Za-z0-9_.:@-]")
    vnum = version.get("version_number")
    if not isinstance(vnum, int) or isinstance(vnum, bool) or vnum < 1:
        raise AssetContractError(
            "version_number must be a positive integer (monotonic, "
            "append-only, D-097)")
    asset_id = version.get("asset_id")
    if not isinstance(asset_id, str) or not _ID_RE.match(asset_id):
        raise AssetContractError("asset_id must reference a MediaAsset")
    parent = version.get("parent_version_id")
    if vnum == 1:
        if parent not in (None, ""):
            raise AssetContractError(
                "v1 must not declare a parent (chain root, D-097)")
    else:
        if not isinstance(parent, str) or not parent:
            raise AssetContractError(
                f"v{vnum} must reference parent_version_id (append-only "
                "chain, D-097)")
    if not isinstance(version.get("metadata", {}), dict):
        raise AssetContractError("metadata must be a dict")
    return version


def validate_version_graph(versions: Dict[int, Dict]) -> None:
    """The chain must be 1..N contiguous with correct parent links —
    a single chain per content_id, no forks, no gaps (D-097)."""
    if not versions:
        raise AssetContractError("empty version graph")
    expected_parent = None
    for n in range(1, max(versions) + 1):
        v = versions.get(n)
        if v is None:
            raise AssetContractError(
                f"version gap: v{n} missing (single chain, D-097)")
        if v.get("parent_version_id") != expected_parent:
            raise AssetContractError(
                f"v{n} parent link broken (expected "
                f"{expected_parent!r}, D-097)")
        expected_parent = v.get("version_id") or f"v{n}"


# --- variant specifications (D-099) -------------------------------------------

VARIANT_SPECS: Dict[str, Dict] = {
    "thumbnail": {"max_edge_px": 320, "mime": "image/webp"},
    "standard": {"max_edge_px": 1280, "mime": "image/webp"},
    "compressed": {"quality": 70, "mime": "image/webp"},
}


def canonical_params(spec: Dict) -> str:
    """Deterministic parameter serialization for the derivation key."""
    return json_dumps(spec)


def derivation_key(parent_checksum: str, kind: str,
                   spec: Dict) -> str:
    """D-099 idempotency: SHA-256(parent checksum, kind, canonical
    parameters). Same parent + spec ⇒ same variant reference."""
    material = "\x1f".join([
        "asset-variant-v1", parent_checksum, kind, canonical_params(spec)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_variant_kind(kind: str) -> Dict:
    if kind not in VARIANT_SPECS:
        raise AssetContractError(
            f"variant kind must be one of {sorted(VARIANT_SPECS)} "
            "(D-099)")
    return VARIANT_SPECS[kind]


# --- durable reference kinds (D-097/D-100 audit) -------------------------------

REF_KINDS = {
    "upload": "asset_upload",
    "dedup": "asset_deduplicated",
    "version": "content_version",
    "lifecycle": "asset_lifecycle",
    "variant": "asset_variant",
}


# --- lifecycle vocabulary (D-99/D-100) ------------------------------------------

AS_ACTIVE = "ACTIVE"
AS_QUARANTINED = "QUARANTINED"
AS_GC_ELIGIBLE = "GC_ELIGIBLE"

VS_PENDING_DERIVATION = "PENDING_DERIVATION"
VS_PROCESSING = "PROCESSING"
VS_READY = "READY"
VS_FAILED = "FAILED"


def json_dumps(obj) -> str:
    return json_dumps_(obj)


def json_dumps_(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)
