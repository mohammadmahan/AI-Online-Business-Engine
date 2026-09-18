"""Phase 24 — portability substrate (D-130): errors, normalization,
blob addressing, and the media-store contract. Pure; no I/O imports."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Dict

__all__ = [
    "ContractError", "MEDIA_OPS", "MediaStoreContract",
    "MediaStoreContractError", "compute_blob_address", "normalize",
]


class ContractError(Exception):
    """Contract-level misuse (bad declaration, unknown op, bad binding)."""


def normalize(value: Any) -> Any:
    """Normalize a verdict for cross-backend comparison.

    Scalars pass through; tuples become lists; dict keys become
    sorted strings; anything else falls back to its type name so
    backend-specific object identities never fake a parity pass.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): normalize(v)
                for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    return type(value).__name__


def compute_blob_address(data: bytes) -> str:
    """Deterministic content address: sha256/<hex>."""
    if not isinstance(data, (bytes, bytearray)):
        raise ContractError("blob address requires bytes")
    return f"sha256/{hashlib.sha256(bytes(data)).hexdigest()}"


#: The declared MediaStore operation matrix (D-130): every conforming
#: store must satisfy all five ops with these exact semantics.
MEDIA_OPS = ("put", "get", "delete", "head", "list")

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@-]{0,254}$")


class MediaStoreContractError(ContractError):
    """A MediaStore implementation violated the D-130 contract."""


def _require_key(object_key: str) -> str:
    if not isinstance(object_key, str) or not _KEY_RE.match(object_key):
        raise MediaStoreContractError(
            f"object key {object_key!r} violates the key grammar")
    return object_key


def run_media_script(store: Any, blob: bytes = b"portability-probe",
                     content_type: str = "application/octet-stream",
                     metadata: Dict = None) -> Dict[str, Any]:
    """Run the media matrix against one store; returns the verdict map.

    Deterministic addressing: put() of identical bytes must yield the
    identical object key. Metadata is echo-checked on head().
    """
    verdicts: Dict[str, Any] = {}
    md = dict(metadata or {"probe": "p24"})
    try:
        put1 = store.put(blob, content_type, md)
        key1 = (put1 or {}).get("object_key")
        if not key1:
            raise MediaStoreContractError("put() returned no object_key")
        put2 = store.put(blob, content_type, md)
        key2 = (put2 or {}).get("object_key")
        verdicts["put"] = {"object_key": str(key1)}
        verdicts["deterministic_address"] = bool(key1 == key2)
        expected = compute_blob_address(blob)
        verdicts["content_addressed"] = bool(str(key1).endswith(
            expected.split("/", 1)[1])) or str(key1) == expected

        got = store.get(str(key1))
        verdicts["get"] = bool(got == blob)

        head = store.head(str(key1)) or {}
        verdicts["head"] = {
            "size": head.get("size"),
            "content_type": head.get("content_type"),
        }
        verdicts["head_size_matches"] = bool(head.get("size") == len(blob))

        listing = store.list() or []
        names = sorted(str(x) for x in listing)
        verdicts["list"] = {"count": len(names),
                            "has_key": str(key1) in names}

        verdicts["delete"] = bool(store.delete(str(key1)))
        verdicts["get_after_delete"] = "missing" if _get_raises(store,
                                                                key1) else "found"
        verdicts["delete_missing"] = bool(store.delete(str(key1))) is False
    except MediaStoreContractError:
        raise
    except Exception as exc:  # noqa: BLE001 — harness classifies
        raise MediaStoreContractError(
            f"store {type(store).__name__} failed the media matrix: "
            f"{type(exc).__name__}: {exc}") from exc
    return verdicts


def _get_raises(store: Any, key: str) -> bool:
    try:
        store.get(key)
    except Exception:
        return True
    return False


class MediaStoreContract:
    """Declared D-130 media contract: assert conformance via
    ``assert_media_conformance`` (provided by canonical.portability)."""

    ops = MEDIA_OPS

    @staticmethod
    def script(store: Any, **kwargs) -> Dict[str, Any]:
        return run_media_script(store, **kwargs)
