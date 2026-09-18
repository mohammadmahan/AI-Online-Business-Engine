"""Media abstraction (D-049/D-056): provider-neutral media storage.

The application communicates only through this MediaStore interface;
the local implementation is the S3-compatible emulator (D-056) and the
future production provider (Phase 4) is a drop-in implementation —
no business logic changes.

Binaries never enter Git; objects are content-addressed (duplicate
prevention per D-049 notes); metadata (alt text) is stored alongside.
"""

import hashlib
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class MediaStore(ABC):
    @abstractmethod
    def put(self, data: bytes, content_type: str,
            metadata: dict = None) -> dict: ...

    @abstractmethod
    def get(self, object_key: str) -> bytes: ...

    @abstractmethod
    def delete(self, object_key: str) -> bool: ...

    @abstractmethod
    def head(self, object_key: str) -> dict: ...

    @abstractmethod
    def list(self) -> list:
        """Return all object keys in the store (sorted)."""


class LocalObjectStore(MediaStore):
    """S3-compatible emulator backend (endpoint/keys via env only).

    All credentials are local development-only values supplied through
    the environment (D-045); nothing is hard-coded.
    """

    def __init__(self, bucket: str = None, root: str = None):
        self.bucket = bucket or os.environ.get(
            "LOCAL_MEDIA_BUCKET", "engine-local-media")
        self.root = root or os.environ.get(
            "LOCAL_MEDIA_ROOT",
            os.path.join(os.path.dirname(__file__), "..", "volumes",
                         "media"))

    def _path(self, object_key: str) -> str:
        safe = os.path.normpath(object_key).lstrip("/")
        if safe.startswith(".."):
            raise ValueError("invalid object key")
        return os.path.join(self.root, self.bucket, safe)

    def put(self, data: bytes, content_type: str,
            metadata: dict = None) -> dict:
        content_hash = hashlib.sha256(data).hexdigest()
        object_key = f"{content_hash[:2]}/{content_hash}"
        path = self._path(object_key)
        if os.path.exists(path):
            # Content-addressed: identical object = idempotent put.
            existing = self._read_meta(object_key)
            return {"object_key": object_key, "content_hash":
                    content_hash, "duplicate": True,
                    "metadata": existing.get("metadata", {})}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        meta = {
            "content_type": content_type,
            "size": len(data),
            "metadata": metadata or {},
            "stored_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
        }
        with open(path + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return {"object_key": object_key, "content_hash": content_hash,
                "duplicate": False, "metadata": meta["metadata"]}

    def _read_meta(self, object_key: str) -> dict:
        try:
            with open(self._path(object_key) + ".meta.json",
                      encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def get(self, object_key: str) -> bytes:
        with open(self._path(object_key), "rb") as f:
            return f.read()

    def head(self, object_key: str) -> dict:
        path = self._path(object_key)
        if not os.path.exists(path):
            raise FileNotFoundError(object_key)
        return self._read_meta(object_key)

    def delete(self, object_key: str) -> bool:
        path = self._path(object_key)
        existed = os.path.exists(path)
        for p in (path, path + ".meta.json"):
            if os.path.exists(p):
                os.remove(p)
        return existed

    def list(self) -> list:
        bucket_dir = os.path.join(self.root, self.bucket)
        keys = []
        if os.path.isdir(bucket_dir):
            for dirpath, _dirnames, filenames in os.walk(bucket_dir):
                for fn in filenames:
                    if fn.endswith(".meta.json") or fn.endswith(".tmp"):
                        continue
                    full = os.path.join(dirpath, fn)
                    keys.append(os.path.relpath(full, bucket_dir))
        return sorted(keys)


def media_store() -> MediaStore:
    """Factory: the abstraction boundary (RULES §35).

    The future production provider registers here without touching
    business logic.
    """
    backend = os.environ.get("LOCAL_MEDIA_BACKEND", "local-object-store")
    if backend == "local-object-store":
        return LocalObjectStore()
    raise ValueError(f"unknown media backend: {backend}")
