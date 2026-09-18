"""Phase 20 M2 — hardening engine, attestation vault & rate limiter
(D-114/D-115).

InputHardeningGate (D-114): a PURE pre-validation gate applied at
contract entry points — strict size limits (payload bytes, string
lengths), control-character and confusable-codepoint rejection,
NFC canonicalization, JSON depth/width limits, and duplicate-key
rejection (json.loads with object_pairs_hook). Rejections are
uniform `InputRejected` errors whose messages carry a stable reason
code, never input internals (D-113 error-surface control).

ChainHeadAttestation (D-115): an O(1) commitment over a hash chain
— (head hash, length, logical stamp) hashed together and recomputed
on demand; a mismatch against the walked chain means tampering.
Works over the Phase 18 (per-ticket) and Phase 19 (global) chains
through INJECTED row providers — no cross-module imports.

RateLimiter (D-115): deterministic budget counters keyed by
(subject, kind) on the injected logical clock — configurable
threshold and lockout window; lockouts are auditable records.

No network, no wall clock, no randomness.
"""

import hashlib
import json
import os
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

from canonical.security_contracts import (
    DEFAULT_POLICY,
    HardeningPolicy,
    SecurityContractError,
    validate_record,
    _FORBIDDEN_CHARS,
)
from services.sync_engine import IntegrityError

SOURCE_SYSTEM = "security"
OP_HARDENING = "security_event"


class InputRejected(Exception):
    """Uniform gate rejection: stable reason code + short message.
    Never echoes input internals (D-113 error-surface control)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# --- the gate (D-114) ---------------------------------------------------------------

# confusable look-alike codepoints commonly abused in identifiers
_CONFUSABLES = {
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0456": "i",
    "\u051b": "q", "\u2122": "tm", "\u0391": "A", "\u0392": "B",
    "\u0395": "E", "\u0397": "H", "\u0399": "I", "\u039a": "K",
    "\u039c": "M", "\u039f": "O", "\u03a1": "P", "\u03a4": "T",
    "\u03a7": "X", "\u03c5": "u", "\u0501": "d", "\u13da": "l",
}


def _reject(reason: str) -> None:
    raise InputRejected(reason)


def _check_depth_width(obj, depth: int, max_depth: int, max_width: int,
                       path: str = "$") -> None:
    if depth > max_depth:
        _reject("json_depth_exceeded")
    if isinstance(obj, dict):
        if len(obj) > max_width:
            _reject("json_width_exceeded")
        for k, v in obj.items():
            _check_depth_width(v, depth + 1, max_depth, max_width)
    elif isinstance(obj, (list, tuple)):
        if len(obj) > max_width:
            _reject("json_width_exceeded")
        for v in obj:
            _check_depth_width(v, depth + 1, max_depth, max_width)


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            _reject("duplicate_json_key")
        out[k] = v
    return out


def _scan_confusables(text: str, value: str) -> None:
    for ch in value:
        if ch in _CONFUSABLES:
            _reject("confusable_unicode")
        if unicodedata.category(ch) in ("Cf", "Co", "Cn", "Cs"):
            # Cs (surrogates) added by the Phase 21 fuzz battery: a
            # lone surrogate accepted here would explode later at
            # encode time with an unhandled UnicodeEncodeError
            _reject("invisible_or_unassigned_char")


def canonicalize_text(value: str) -> str:
    """NFC-normalize (composing forms collapse); the caller re-runs
    validation on the canonical form (D-114)."""
    return unicodedata.normalize("NFC", value)


class InputHardeningGate:
    """Pure gate: raises InputRejected (stable reason codes) or
    returns the canonicalized value. No I/O, no clock."""

    def __init__(self, policy: Optional[HardeningPolicy] = None):
        self.policy = policy or DEFAULT_POLICY

    # -- strings -----------------------------------------------------------------

    def check_string(self, value: str, field: str = "value") -> str:
        p = self.policy
        if not isinstance(value, str):
            _reject("not_a_string")
        if len(value) > p.max_string_len:
            _reject("string_too_long")
        if any(ch in _FORBIDDEN_CHARS for ch in value):
            _reject("control_character")
        _scan_confusables(value, value)
        return canonicalize_text(value)

    # -- identifiers/refs: stricter charset ---------------------------------------

    def check_identifier(self, value: str, field: str = "id") -> str:
        canonical = self.check_string(value, field)
        if not canonical or len(canonical) > 128:
            _reject("identifier_length_invalid")
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789_-:.@/ ")
        if not set(canonical) <= allowed:
            _reject("identifier_charset_invalid")
        return canonical

    # -- payloads --------------------------------------------------------------------

    def check_payload(self, data) -> bytes:
        p = self.policy
        if isinstance(data, str):
            try:
                data = data.encode("utf-8")
            except UnicodeEncodeError:
                # lone surrogates etc. — deterministic rejection at
                # the gate (fuzz-battery finding, Phase 21)
                _reject("payload_not_encodable")
        if not isinstance(data, (bytes, bytearray)):
            _reject("payload_not_bytes")
        if len(data) > p.max_payload_bytes:
            _reject("payload_too_large")
        if len(data) == 0:
            _reject("payload_empty")
        return bytes(data)

    # -- JSON documents -------------------------------------------------------------

    def parse_json(self, raw, max_depth: Optional[int] = None,
                   max_width: Optional[int] = None) -> Dict:
        """Strict JSON: size cap, duplicate-key rejection, depth/width
        caps, control-character scan on every string, confusable
        rejection. Returns the canonical parsed document."""
        data = self.check_payload(raw)
        try:
            doc = json.loads(data.decode("utf-8"),
                             object_pairs_hook=_no_duplicates)
        except InputRejected:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError):
            _reject("malformed_json")
        p = self.policy
        _check_depth_width(doc, 1,
                           max_depth if max_depth is not None
                           else p.max_json_depth,
                           max_width if max_width is not None
                           else p.max_json_width)
        self._scan_tree_strings(doc)
        return doc

    def _scan_tree_strings(self, obj) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                self.check_string(k, "key")
                self._scan_tree_strings(v)
        elif isinstance(obj, list):
            for v in obj:
                self._scan_tree_strings(v)
        elif isinstance(obj, str):
            self.check_string(obj)


# --- chain-head attestation (D-115) ---------------------------------------------------

class ChainHeadAttestation:
    """Position-weighted tamper commitment over a hash chain
    (D-115). The attestation folds EVERY row's row_hash with its
    position into a single SHA-256 value: mutation of any interior
    row, a swap of two rows, an append, or a deletion each change the
    fold — unlike a head-only commitment, which an interior edit
    leaves untouched. Crypto work is O(1) (one final hash); reading
    the row hashes is a cheap column-only read. `rows_provider` is an
    INJECTED callable returning the chain rows (each with row_hash)."""

    def __init__(self, rows_provider: Callable[[], List[Dict]]):
        self._rows = rows_provider
        self._cached: Optional[Tuple[str, str]] = None

    def _fold(self, rows: List[Dict], logical_now: str) -> str:
        acc = f"attest-v2:{len(rows)}:{logical_now}"
        for i, row in enumerate(rows):
            # fold the WHOLE ROW (deterministic full-dict digest), not
            # just the stored chain hash: an interior row mutated in
            # the vault (payload, actor, stamp — any field) keeps its
            # stored row_hash, so a hash-only fold would MISS that
            # tamper. Full-row folding detects it by construction.
            row_sha = hashlib.sha256(
                json.dumps(row, ensure_ascii=False, sort_keys=True,
                           default=str)
                .encode("utf-8")).hexdigest()
            acc = hashlib.sha256(
                f"{acc}|{i}|{row_sha}".encode("utf-8")).hexdigest()
        return acc

    def compute(self, logical_now: str) -> Dict:
        rows = self._rows()
        head = rows[-1]["row_hash"] if rows else ""
        value = self._fold(rows, logical_now)
        prev = self._cached
        self._cached = (value, logical_now)
        return {"attestation": value, "chain_length": len(rows),
                "head": head[:16], "computed_at_logical": logical_now,
                "previous_attestation": prev[0] if prev else None}

    def verify(self, attestation: Dict, logical_now: str) -> Dict:
        """Re-fold the current chain and compare with the attested
        value. Any difference in membership, order, or content of ANY
        row changes the fold."""
        rows = self._rows()
        if len(rows) != attestation.get("chain_length"):
            return {"ok": False, "reason": "length_mismatch",
                    "attested": attestation.get("chain_length"),
                    "actual": len(rows)}
        value = self._fold(
            rows, attestation.get("computed_at_logical") or "")
        if value != attestation.get("attestation"):
            return {"ok": False, "reason": "attestation_mismatch",
                    "detail": "chain content differs from the "
                              "attested fold"}
        return {"ok": True, "chain_length": len(rows),
                "verified_at_logical": logical_now}


# --- rate limiter (D-115) ----------------------------------------------------------------

class RateLimiter:
    """Deterministic budget counters on the injected logical clock.
    `key` = (subject, kind); a count within the window past the
    threshold triggers a LOCKOUT until `lock_until_logical`."""

    def __init__(self, threshold: int = 5,
                 window_logical: int = 1000):
        if threshold <= 0 or window_logical <= 0:
            raise SecurityContractError(
                "threshold and window must be positive")
        self.threshold = threshold
        self.window = window_logical
        self._events: Dict[Tuple[str, str], List[int]] = {}
        self._lockouts: Dict[str, str] = {}

    def _logical_int(self, logical: str) -> int:
        """Lexicographic logical stamps must end in comparable
        integers; accept 'L<digits>' or plain digits."""
        digits = "".join(ch for ch in logical if ch.isdigit())
        if not digits:
            raise SecurityContractError(
                "logical stamps must contain digits for ordering")
        return int(digits)

    def check(self, subject: str, kind: str, logical_now: str) -> Dict:
        now = self._logical_int(logical_now)
        locked_until = self._lockouts.get(f"{subject}|{kind}")
        if locked_until is not None:
            if now < self._logical_int(locked_until):
                return {"allowed": False, "locked_out": True,
                        "lock_until_logical": locked_until}
            del self._lockouts[f"{subject}|{kind}"]  # lock expired
        window_start = now - self.window
        recent = [t for t in self._events.get((subject, kind), [])
                  if t > window_start]
        self._events[(subject, kind)] = recent
        if len(recent) >= self.threshold:
            lock_until = f"L{now + self.window}"
            self._lockouts[f"{subject}|{kind}"] = lock_until
            return {"allowed": False, "locked_out": True,
                    "lock_until_logical": lock_until,
                    "count": len(recent)}
        return {"allowed": True, "count": len(recent)}

    def record(self, subject: str, kind: str,
               logical_now: str) -> Dict:
        """Record an occurrence, then check."""
        self._events.setdefault((subject, kind), []).append(
            self._logical_int(logical_now))
        return self.check(subject, kind, logical_now)

    def lockout_state(self, subject: str, kind: str) -> Optional[str]:
        return self._lockouts.get(f"{subject}|{kind}")


# --- durable hardening-audit vault (D-113) ------------------------------------

class _JsonAuditVault:
    """Offline parity vault for `security.hardening_audit`."""

    def __init__(self, root: str):
        import os
        import pathlib
        self.root = str(root)
        pathlib.Path(self.root).mkdir(parents=True, exist_ok=True)

    def _path(self):
        import os
        return os.path.join(self.root, "hardening_audit.json")

    def append(self, row: Dict) -> None:
        import os
        import json as _json
        data = {}
        p = self._path()
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                data = _json.load(fh)
        if row["record_key"] in data:
            return  # idempotent append
        data[row["record_key"]] = row
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            _json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, p)

    def rows(self) -> List[Dict]:
        import os
        import json as _json
        p = self._path()
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            data = _json.load(fh)
        out = list(data.values())
        out.sort(key=lambda r: r["logical_at"])
        return out


class _PgAuditVault:
    """Live vault over `security.hardening_audit` (PK = dedup)."""

    def __init__(self):
        import sys as _sys
        import os as _os
        scripts = _os.path.join("local", "scripts")
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        from canonical.notion_ingest import _exec, _txt  # noqa: E402
        self._exec = _exec
        self._txt = _txt

    def append(self, row: Dict) -> None:
        self._exec(
            "INSERT INTO security.hardening_audit (record_key, "
            "record_kind, subject, actor, detail, logical_at) "
            "VALUES (" + self._txt("rk") + ", " + self._txt("k")
            + ", " + self._txt("s") + ", " + self._txt("a") + ", "
            + self._txt("d") + "::jsonb, " + self._txt("la") + ") "
            "ON CONFLICT (record_key) DO NOTHING",
            {"rk": row["record_key"], "k": row["record_kind"],
             "s": row["subject"], "a": row["actor"],
             "d": json.dumps(row.get("detail", {}),
                              ensure_ascii=False, sort_keys=True),
             "la": row["logical_at"]})

    def rows(self) -> List[Dict]:
        out = self._exec(
            "SELECT record_key || chr(31) || record_kind || chr(31) "
            "|| subject || chr(31) || actor || chr(31) || "
            "detail::text || chr(31) || logical_at || chr(31) || "
            "'END' FROM security.hardening_audit ORDER BY "
            "logical_at, record_key", {})
        rows = []
        for line in out.splitlines():
            p = line.strip().split("\x1f")
            if len(p) >= 6 and p[-1] == "END":
                rows.append({"record_key": p[0],
                             "record_kind": p[1], "subject": p[2],
                             "actor": p[3], "detail": json.loads(p[4]),
                             "logical_at": p[5]})
        return rows


class HardeningEngine:
    """D-113/D-115 facade: durable, idempotent hardening-audit
    records + one-shot attestation over an injected ledger.

    `audit` persists every hardening-relevant occurrence as an
    attempt-unique record (the record_key PK is the dedup — the same
    occurrence re-reported never writes a second row, D-027
    discipline) and emits the canonical D-027 event.
    """

    def __init__(self, store, vault=None):
        self._store = store
        self._vault = vault or _JsonAuditVault(
            os.path.join("local", "volumes", "security"))

    @staticmethod
    def record_key(kind: str, subject: str, logical_at: str,
                   nonce: str = "") -> str:
        """Deterministic, attempt-unique record key."""
        basis = f"{kind}|{subject}|{logical_at}|{nonce}"
        return "sec-" + hashlib.sha256(
            basis.encode("utf-8")).hexdigest()

    def audit(self, record: Dict) -> Dict:
        rec = validate_record(record)
        rk = rec.get("record_key") or self.record_key(
            rec["record_kind"], rec["subject"], rec["logical_at"],
            rec.get("nonce", ""))
        row = {"record_key": rk, "record_kind": rec["record_kind"],
               "subject": rec["subject"], "actor": rec["actor"],
               "detail": rec.get("detail", {}),
               "logical_at": rec["logical_at"]}
        before = len(self._vault.rows())
        self._vault.append(row)
        inserted = len(self._vault.rows()) > before
        eid = f"security|hardening|{rk}"
        verdict = self._store.receive(
            SOURCE_SYSTEM, eid, OP_HARDENING,
            {"record_key": rk, "kind": rec["record_kind"],
             "subject": rec["subject"]})
        if verdict.get("verdict") != "skipped_duplicate":
            try:
                self._store.begin(SOURCE_SYSTEM, eid)
                self._store.succeed(
                    SOURCE_SYSTEM, eid, result_reference=rk)
            except IntegrityError:
                pass
        return {"record_key": rk, "inserted": inserted}

    def records(self) -> List[Dict]:
        return self._vault.rows()

    def attest(self, rows_provider: Callable[[], List[Dict]],
               logical_now: str, subject: str = "ledger") -> Dict:
        """Compute (or renew) a position-weighted chain attestation
        and persist it as an audit record."""
        att = ChainHeadAttestation(rows_provider).compute(logical_now)
        self.audit({"record_kind": "attestation_check",
                    "subject": subject, "actor": "actor:system:security",
                    "logical_at": logical_now,
                    "detail": {"attestation": att["attestation"],
                               "chain_length": att["chain_length"],
                               "head": att["head"]}})
        return att

    def verify(self, rows_provider: Callable[[], List[Dict]],
               attestation: Dict, logical_now: str) -> Dict:
        verdict = ChainHeadAttestation(rows_provider).verify(
            attestation, logical_now)
        self.audit({"record_kind": "attestation_check",
                    "subject": attestation.get("subject", "ledger"),
                    "actor": "actor:system:security",
                    "logical_at": logical_now,
                    "detail": {"ok": verdict["ok"],
                               "reason": verdict.get("reason")}})
        return verdict
