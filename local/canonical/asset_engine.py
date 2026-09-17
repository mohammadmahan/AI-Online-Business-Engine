"""Phase 16 M2 — asset engine & versioning vault (D-097/D-098/D-100).

AssetVault: content-addressable registration (one checksum = one
asset, dedup by construction), append-only ContentVersion chains,
lifecycle transitions. Atomicity via PostgreSQL unique constraints
(`assets.media_asset` PK checksum, `assets.content_version` unique
(content_id, version_number)) with a JSON parity vault. Class-B
validation runs BEFORE any byte reaches storage (D-098). The binary
store is the INJECTED Phase 3 MediaStore (D-049/D-056) — this engine
persists references only, never deletes binaries (D-100). Every
action is a D-027 event; no wall clock enters any key (injected
instants only).
"""

import json
from typing import Dict, List, Optional, Tuple

from canonical.asset_contracts import (
    AS_ACTIVE,
    AS_GC_ELIGIBLE,
    AS_QUARANTINED,
    OP_ASSET,
    REF_KINDS,
    SOURCE_SYSTEM,
    AssetContractError,
    checksum_bytes,
    validate_asset,
    validate_version,
)
from services.sync_engine import IntegrityError


# --- backends -------------------------------------------------------------------

class _JsonVault:
    """Offline parity vault: JSON files with the same uniqueness
    semantics (checksum PK; (content_id, version_number) unique)."""

    def __init__(self, root: str):
        import pathlib
        self.root = str(root)
        pathlib.Path(self.root).mkdir(parents=True, exist_ok=True)

    def _read(self, name: str) -> Dict:
        import os
        path = os.path.join(self.root, name)
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, name: str, data: Dict) -> None:
        import os
        path = os.path.join(self.root, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)

    def register_asset(self, row: Dict) -> str:
        data = self._read("assets.json")
        if row["checksum"] in data:
            return "duplicate"
        data[row["checksum"]] = row
        self._write("assets.json", data)
        return "created"

    def get_asset(self, checksum: str) -> Optional[Dict]:
        return self._read("assets.json").get(checksum)

    def all_assets(self) -> Dict[str, Dict]:
        return self._read("assets.json")

    def insert_version(self, row: Dict) -> str:
        data = self._read("versions.json")
        key = f"{row['content_id']}\x1f{row['version_number']}"
        if key in data:
            return "duplicate"
        data[key] = row
        self._write("versions.json", data)
        return "created"

    def versions_for(self, content_id: str) -> List[Dict]:
        out = []
        for row in self._read("versions.json").values():
            if row["content_id"] == content_id:
                out.append(row)
        out.sort(key=lambda r: r["version_number"])
        return out

    def set_lifecycle(self, checksum: str, lifecycle: str,
                      quarantine_at: Optional[str]) -> int:
        data = self._read("assets.json")
        row = data.get(checksum)
        if row is None:
            return 0
        row["lifecycle"] = lifecycle
        row["quarantine_at"] = quarantine_at
        self._write("assets.json", data)
        return 1


class _PgVault:
    """Live vault: the unique constraints ARE the atomicity (D-098)."""

    def __init__(self):
        import sys as _sys
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def register_asset(self, row: Dict) -> str:
        out = self._exec(
            "INSERT INTO assets.media_asset (checksum, asset_id, "
            "mime_type, file_size_bytes, storage_uri, lifecycle, "
            "metadata) VALUES (" + self._txt("c") + ", "
            + self._txt("a") + ", " + self._txt("m") + ", "
            + self._txt("s") + "::bigint, " + self._txt("u") + ", "
            + self._txt("l") + ", " + self._txt("j") + "::jsonb) "
            "ON CONFLICT (checksum) DO NOTHING RETURNING checksum",
            {"c": row["checksum"], "a": row["asset_id"],
             "m": row["mime_type"], "s": str(row["file_size_bytes"]),
             "u": row["storage_uri"], "l": row.get("lifecycle",
                                                   AS_ACTIVE),
             "j": json.dumps(row.get("metadata", {}),
                             ensure_ascii=False, sort_keys=True)}).strip()
        return "created" if out else "duplicate"

    def get_asset(self, checksum: str) -> Optional[Dict]:
        rows = self._exec(
            "SELECT checksum || chr(31) || asset_id || chr(31) || "
            "mime_type || chr(31) || file_size_bytes::text || chr(31) "
            "|| storage_uri || chr(31) || lifecycle || chr(31) || "
            "coalesce(quarantine_at, '') || chr(31) || metadata::text "
            "|| chr(31) || 'END' FROM assets.media_asset WHERE "
            "checksum = " + self._txt("c"), {"c": checksum}).strip()
        if not rows:
            return None
        p = rows.split("\x1f")
        if len(p) < 8 or p[-1] != "END":
            return None
        return {"checksum": p[0], "asset_id": p[1], "mime_type": p[2],
                "file_size_bytes": int(p[3]), "storage_uri": p[4],
                "lifecycle": p[5], "quarantine_at": p[6] or None,
                "metadata": json.loads(p[7])}

    def all_assets(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT checksum || chr(31) || asset_id || chr(31) || "
            "mime_type || chr(31) || file_size_bytes::text || chr(31) "
            "|| storage_uri || chr(31) || lifecycle || chr(31) || "
            "coalesce(quarantine_at, '') || chr(31) || 'END' "
            "FROM assets.media_asset ORDER BY checksum", {})
        out: Dict[str, Dict] = {}
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 8 and p[-1] == "END":
                out[p[0]] = {"checksum": p[0], "asset_id": p[1],
                             "mime_type": p[2],
                             "file_size_bytes": int(p[3]),
                             "storage_uri": p[4], "lifecycle": p[5],
                             "quarantine_at": p[6] or None}
        return out

    def insert_version(self, row: Dict) -> str:
        out = self._exec(
            "INSERT INTO assets.content_version (content_id, "
            "version_number, version_id, asset_id, parent_version_id, "
            "metadata) VALUES (" + self._txt("c") + ", "
            + self._txt("v") + "::int, " + self._txt("i") + ", "
            + self._txt("a") + ", " + self._txt("p") + ", "
            + self._txt("j") + "::jsonb) ON CONFLICT (content_id, "
            "version_number) DO NOTHING RETURNING version_id",
            {"c": row["content_id"], "v": str(row["version_number"]),
             "i": row["version_id"], "a": row["asset_id"],
             "p": row.get("parent_version_id"),
             "j": json.dumps(row.get("metadata", {}),
                             ensure_ascii=False, sort_keys=True)}).strip()
        return "created" if out else "duplicate"

    def versions_for(self, content_id: str) -> List[Dict]:
        rows = self._exec(
            "SELECT content_id || chr(31) || version_number::text || "
            "chr(31) || version_id || chr(31) || asset_id || chr(31) "
            "|| coalesce(parent_version_id, '') || chr(31) || "
            "metadata::text || chr(31) || 'END' FROM "
            "assets.content_version WHERE content_id = "
            + self._txt("c") + " ORDER BY version_number",
            {"c": content_id})
        out: List[Dict] = []
        for line in rows.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 7 and p[-1] == "END":
                out.append({"content_id": p[0],
                            "version_number": int(p[1]),
                            "version_id": p[2], "asset_id": p[3],
                            "parent_version_id": p[4] or None,
                            "metadata": json.loads(p[5])})
        return out

    def set_lifecycle(self, checksum: str, lifecycle: str,
                      quarantine_at: Optional[str]) -> int:
        out = self._exec(
            "UPDATE assets.media_asset SET lifecycle = "
            + self._txt("l") + ", quarantine_at = "
            + self._txt("q") + " WHERE checksum = " + self._txt("c")
            + " RETURNING checksum",
            {"l": lifecycle, "q": quarantine_at, "c": checksum}).strip()
        return 1 if out else 0


def default_vault():
    try:
        vault = _PgVault()
        vault._exec("SELECT 1", {})
        return vault
    except Exception:
        import os
        return _JsonVault(os.path.join("local", "volumes", "assets"))


# --- engine ------------------------------------------------------------------------

class AssetEngine:
    """D-097/D-098/D-100 core. store: D-027 store; vault: backend;"""

    def __init__(self, store, vault=None):
        self._store = store
        self._vault = vault or default_vault()

    # -- durable audit ----------------------------------------------------------

    def _refs(self) -> List[Dict]:
        out: List[Dict] = []
        for raw in self._store.succeeded_references("assets"):
            if isinstance(raw, dict):
                out.append(raw)
                continue
            try:
                out.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    @staticmethod
    def _eid(kind: str, ident: str, seq: int = 0) -> str:
        return f"assets|{kind}|{ident}|{int(seq)}"

    def _record(self, eid: str, ref: Dict) -> bool:
        """Durable audit write. Conflicting duplicates surface as
        IntegrityError (D-027) — callers use attempt-unique ids.
        A concurrent writer winning the SAME event id with the SAME
        payload is one logical delivery: the loser's begin/succeed
        hits the terminal guard and returns False — the audit row is
        already durable, nothing is lost (exactly-once, D-027)."""
        verdict = self._store.receive("assets", eid, OP_ASSET, ref)
        if verdict.get("verdict") == "skipped_duplicate":
            return False
        try:
            self._store.begin("assets", eid)
            self._store.succeed("assets", eid, result_reference=json.dumps(
                ref, ensure_ascii=False, sort_keys=True))
        except IntegrityError:
            return False
        return True

    # -- asset registration (D-097/D-098) ----------------------------------------

    def register_asset(self, data: bytes, declared: Dict,
                       storage_uri: str) -> Dict:
        """Content-addressable registration. The checksum is COMPUTED
        from the bytes — a declared mismatch is a Class-B rejection
        before storage (D-098). Duplicate checksums collapse to the
        existing asset (dedup by construction)."""
        if not data:
            raise AssetContractError("empty asset payload")
        checksum = checksum_bytes(data)
        declared_checksum = declared.get("checksum")
        if declared_checksum is not None and declared_checksum != checksum:
            raise AssetContractError(
                "declared checksum contradicts content bytes "
                "(corrupt registration, Class-B before storage, D-098)")
        asset = {
            "asset_id": declared.get("asset_id") or
            f"asset-{checksum[:16]}",
            "checksum": checksum,
            "mime_type": declared.get("mime_type"),
            "file_size_bytes": len(data),
            "storage_uri": storage_uri,
            "metadata": declared.get("metadata", {}),
        }
        validate_asset(asset, data)  # Class-B before storage (D-098)
        result = self._vault.register_asset(dict(
            asset, lifecycle=AS_ACTIVE))
        if result == "duplicate":
            existing = self._vault.get_asset(checksum)
            self._record(self._eid("dedup", checksum), {
                "kind": REF_KINDS["dedup"], "checksum": checksum,
                "asset_id": existing["asset_id"] if existing
                else asset["asset_id"]})
            return {"status": "DEDUPLICATED",
                    "asset_id": existing["asset_id"] if existing
                    else asset["asset_id"],
                    "checksum": checksum}
        self._record(self._eid("upload", checksum), {
            "kind": REF_KINDS["upload"], "checksum": checksum,
            "asset_id": asset["asset_id"], "mime_type": asset["mime_type"],
            "file_size_bytes": asset["file_size_bytes"],
            "storage_uri": storage_uri})
        return {"status": "CREATED", "asset_id": asset["asset_id"],
                "checksum": checksum}

    # -- content versions (D-097) ---------------------------------------------------

    def append_version(self, content_id: str, asset_id: str,
                       previous: Optional[Dict] = None,
                       metadata: Optional[Dict] = None) -> Dict:
        """Append the next version. `previous` = the current head row
        (or None for v1). The version number is derived from the
        DURABLE chain — never from a caller counter."""
        versions = self._vault.versions_for(content_id)
        if previous is None:
            if versions:
                raise AssetContractError(
                    f"content {content_id} already has versions — "
                    "append with the current head (append-only, D-097)")
            vnum, parent = 1, None
        else:
            if not versions:
                raise AssetContractError(
                    "previous supplied but chain is empty")
            head = versions[-1]
            if head["version_id"] != previous.get("version_id"):
                raise AssetContractError(
                    "stale head: chain moved (append-only, D-097)")
            vnum, parent = head["version_number"] + 1, \
                head["version_id"]
        version = {"content_id": content_id, "version_number": vnum,
                   "version_id": f"{content_id}-v{vnum}",
                   "asset_id": asset_id, "parent_version_id": parent,
                   "metadata": metadata or {}}
        validate_version(version)
        res = self._vault.insert_version(version)
        if res == "duplicate":
            return {"status": "EXISTS",
                    "version_id": version["version_id"],
                    "version_number": vnum}
        self._record(self._eid("version", version["version_id"]), {
            "kind": REF_KINDS["version"], **version})
        return {"status": "CREATED",
                "version_id": version["version_id"],
                "version_number": vnum}

    # -- lifecycle (D-100) ------------------------------------------------------------

    def set_lifecycle(self, checksum: str, lifecycle: str,
                      quarantine_at: Optional[str] = None) -> Dict:
        n = self._vault.set_lifecycle(checksum, lifecycle,
                                      quarantine_at)
        if not n:
            return {"ok": False, "reason": "unknown_checksum"}
        self._record(self._eid("lifecycle", checksum,
                               self._lifecycle_seq(checksum)), {
            "kind": REF_KINDS["lifecycle"], "checksum": checksum,
            "lifecycle": lifecycle, "quarantine_at": quarantine_at})
        return {"ok": True, "lifecycle": lifecycle}

    def _lifecycle_seq(self, checksum: str) -> int:
        n = 0
        for ref in self._refs():
            if ref.get("kind") == REF_KINDS["lifecycle"] and \
                    ref.get("checksum") == checksum:
                n += 1
        return n

    # -- reconstruction (D-100) ----------------------------------------------------------

    def content_head(self, content_id: str) -> Optional[Dict]:
        versions = self._vault.versions_for(content_id)
        return versions[-1] if versions else None

    def reconstruct_version(self, content_id: str, version_number: int
                            ) -> Optional[Dict]:
        """Full content state at a historical version, from durable
        data only (D-100): the version row plus its asset record."""
        for v in self._vault.versions_for(content_id):
            if v["version_number"] == version_number:
                # resolve the version's asset by the asset_id → the
                # asset row keyed by its content checksum
                for asset in self._vault.all_assets().values():
                    if asset.get("asset_id") == v["asset_id"]:
                        return {"version": v, "asset": asset}
                return {"version": v, "asset": None}
        return None

    # -- calendar of refs for the worker ------------------------------------------------

    def asset_refs(self) -> List[Dict]:
        return self._refs()
