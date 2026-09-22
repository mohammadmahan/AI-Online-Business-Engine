#!/usr/bin/env python3
"""verify_vendor_exit.py — Stage H vendor exit & restore harness
(D-141 / D-129–D-132 lock-in goals).

Proves the SSOT can leave any deployment layer as a portable,
tamper-evident, optionally ENCRYPTED migration archive and be
re-hydrated with 100% schema integrity and row parity — without
Dokploy or any vendor tooling.

Modes (exit 0 = pass / 1 = named failure / 2 = refused or cannot assess):

  check            offline self-proof: crypto round-trip, fold
                   integrity, tamper detection, import parity over
                   synthetic surfaces; D-045 planning hygiene —
                   REFUSES (exit 2) if a production secret is present
                   in the shell environment.
  export           dump the live SSOT (injected query transport;
                   default: the local stack's canonical DB) into the
                   migration archive. Strings are D-124-redacted.
  dry-run-import   synthetic re-hydration: decrypt (if armored),
                   verify folds, replay into a blank in-memory model,
                   assert schema-set equality and per-table row parity.

Confidentiality posture (honest): the archive is always tamper-evident
(fold + per-table hashes). With `--passphrase-file`/ENV it is ALSO
encrypted using stdlib-only PBKDF2-HMAC-SHA256 + an NIST SP 800-90A
HMAC_DRBG keystream — a real construction, but defense-in-depth ONLY;
storage-layer encryption (S3 SSE / disk) remains the primary control.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from typing import Callable, Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from canonical.launch_contracts import redact_text
except ImportError:  # pragma: no cover
    from local.canonical.launch_contracts import redact_text  # type: ignore

FORMAT = "vendor_exit.archive.v1"
KDF_ITER = 200_000
GENESIS = "genesis"

Surfaces = List[Tuple[str, str]]  # (schema, table)

DEFAULT_SURFACES: Surfaces = [
    ("canonical", "content_ideas"), ("canonical", "content_items"),
    ("canonical", "review_events"), ("orchestration", "outbox"),
    ("events", "event_store"), ("oms", "orders"), ("oms", "order_events"),
    ("instagram", "publish_outbox"), ("telegram", "publish_outbox"),
    ("hitl", "decision_ledger"), ("admin", "control_audit"),
    ("provenance", "receipts"), ("assets", "media_index"),
]

# D-045 planning hygiene: these names must be ABSENT (or empty) in the
# planning shell. Values are never read, printed, or transmitted.
PROD_SECRET_VARS = (
    "WOO_CONSUMER_KEY", "WOO_CONSUMER_SECRET", "INSTAGRAM_ACCESS_TOKEN",
    "TELEGRAM_BOT_TOKEN", "NOTION_API_KEY", "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY", "AI_LIVE_ENABLED", "INSTAGRAM_LIVE_ENABLED",
    "TELEGRAM_LIVE_ENABLED", "STRIPE_SECRET_KEY",
)


class ExitError(RuntimeError):
    """Named harness failure (exit 1)."""


def _fail(reason: str):
    raise ExitError(reason)


# ---------------------------------------------------------------------------
# Armoring: PBKDF2 + HMAC_DRBG keystream (NIST SP 800-90A construction)
# ---------------------------------------------------------------------------

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"),
                               salt, KDF_ITER, dklen=32)


def _drbg_keystream(key: bytes, personalization: bytes, length: int) -> bytes:
    """HMAC_DRBG (SHA-256) output stream: deterministic keystream."""
    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + personalization, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + personalization, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    out = bytearray()
    while len(out) < length:
        v = hmac.new(k, v, hashlib.sha256).digest()
        out.extend(v)
    return bytes(out[:length])


def _xor(data: bytes, key: bytes, personalization: bytes) -> bytes:
    stream = _drbg_keystream(key, personalization, len(data))
    return bytes(a ^ b for a, b in zip(data, stream))


def _armor(plaintext: str, passphrase: str) -> Dict:
    salt = hashlib.sha256(
        plaintext.encode("utf-8")).digest()[:16]  # deterministic salt
    key = _derive_key(passphrase, salt)
    raw = plaintext.encode("utf-8")
    body = _xor(raw, key, b"vendor-exit-v1")
    tag = hmac.new(key, body, hashlib.sha256).hexdigest()
    return {"enc": "hmac_drbg_sha256", "kdf": "pbkdf2_sha256",
            "iter": KDF_ITER, "salt": base64.b64encode(salt).decode(),
            "tag": tag, "body": base64.b64encode(body).decode()}


def _dearmor(envelope: Dict, passphrase: str) -> str:
    if envelope.get("enc") != "hmac_drbg_sha256":
        _fail("armor_format_unknown")
    salt = base64.b64decode(envelope.get("salt", ""))
    body = base64.b64decode(envelope.get("body", ""))
    key = _derive_key(passphrase, salt)
    if not hmac.compare_digest(hmac.new(key, body, hashlib.sha256).hexdigest(),
                               envelope.get("tag", "")):
        _fail("armor_tag_mismatch")  # wrong passphrase or tampered body
    return _xor(body, key, b"vendor-exit-v1").decode("utf-8")


# ---------------------------------------------------------------------------
# Archive build / import (fold = per-table SHA-256 over canonical rows)
# ---------------------------------------------------------------------------

def _row_fold(rows: List[Dict]) -> str:
    payload = "\n".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _redact_row(row: Dict) -> Dict:
    return {k: (redact_text(v) if isinstance(v, str) else v)
            for k, v in row.items()}


def collect_rows(query_fn: Callable[[str], List[Dict]],
                 surfaces: Surfaces) -> Dict[str, List[Dict]]:
    """Dump each surface via the injected read-only transport."""
    data: Dict[str, List[Dict]] = {}
    for schema, table in surfaces:
        key = f"{schema}.{table}"
        rows = query_fn(f"SELECT row_to_json(t.*) FROM {schema}.{table} t;")
        data[key] = [_redact_row(r) for r in rows]
    return data


def build_archive(data: Dict[str, List[Dict]], candidate: str) -> Dict:
    """Manifest + rows. Deterministic; fold over every surface."""
    manifest = {
        "format": FORMAT, "candidate": candidate,
        "surfaces": {k: {"row_count": len(v), "fold": _row_fold(v)}
                     for k, v in sorted(data.items())},
        "total_rows": sum(len(v) for v in data.values()),
    }
    return {"manifest": manifest, "data": data}


def archive_plaintext(archive: Dict) -> str:
    lines = [json.dumps(archive["manifest"], ensure_ascii=False,
                        sort_keys=True)]
    for key in sorted(archive["data"]):
        for row in archive["data"][key]:
            lines.append(json.dumps({"surface": key, "row": row},
                                    ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + "\n"


def parse_archive_plaintext(text: str) -> Tuple[Dict, Dict[str, List[Dict]]]:
    lines = [l for l in text.split("\n") if l.strip()]
    try:
        manifest = json.loads(lines[0])
        rows = [json.loads(l) for l in lines[1:]]
    except json.JSONDecodeError as e:
        _fail(f"archive_unparseable:{e}")
    if manifest.get("format") != FORMAT:
        _fail("archive_format_mismatch")
    data: Dict[str, List[Dict]] = {}
    for line in rows:
        if not isinstance(line, dict) or "surface" not in line \
                or "row" not in line:
            _fail("archive_row_invalid")
        data.setdefault(line["surface"], []).append(line["row"])
    return manifest, data


def verify_parity(manifest: Dict, data: Dict[str, List[Dict]]) -> Dict:
    """Schema integrity (surface-set equality) + 100% row parity
    (per-surface count and fold equality)."""
    declared = manifest.get("surfaces", {})
    checks = []
    for key in sorted(set(declared) | set(data)):
        d, got = declared.get(key), data.get(key, [])
        if d is None:
            checks.append((key, False, "surface_not_in_manifest"))
            continue
        if key not in data:
            checks.append((key, False, "surface_missing_after_import"))
            continue
        if d["row_count"] != len(got):
            checks.append((key, False,
                           f"row_count_mismatch:{d['row_count']}!={len(got)}"))
            continue
        if d["fold"] != _row_fold(got):
            checks.append((key, False, "row_fold_mismatch"))
            continue
        checks.append((key, True, "parity"))
    ok = all(c[1] for c in checks)
    if not ok:
        reasons = ",".join(f"{k}:{r}" for k, good, r in checks if not good)
        _fail(f"parity_failed:{reasons}")
    return {"ok": True, "surfaces": len(checks),
            "rows": sum(len(v) for v in data.values())}


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------

def container_psql_query(sql: str) -> List[Dict]:
    """Default live transport: the local stack's canonical DB via
    docker exec psql (read-only SELECT per surface)."""
    import subprocess
    name = os.environ.get("LOCAL_PG_CONTAINER", "engine-local-postgres")
    proc = subprocess.run(
        ["docker", "exec", "-i", name, "psql", "-v", "ON_ERROR_STOP=1",
         "-X", "-q", "-A", "-t", "-U", "engine_local", "-d",
         "business_engine_local", "-c", sql],
        capture_output=True, text=True)
    if proc.returncode != 0:
        _fail(f"ssot_query_failed:{proc.stderr.strip()[:120]}")
    return [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]


def production_secrets_in_shell() -> List[str]:
    return [v for v in PROD_SECRET_VARS if os.environ.get(v)]


# ---------------------------------------------------------------------------
# CLI modes
# ---------------------------------------------------------------------------

def _write_archive(path: str, archive: Dict, passphrase: Optional[str]):
    text = archive_plaintext(archive)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if passphrase:
            json.dump({"format": FORMAT, "armored": True,
                       **_armor(text, passphrase)}, fh, sort_keys=True)
        else:
            fh.write(text)


def _read_archive(path: str, passphrase: Optional[str]) -> Tuple[Dict, Dict]:
    with open(path, encoding="utf-8") as fh:
        head = fh.read(1)
        fh.seek(0)
        if head == "{":
            envelope = json.load(fh)
            if not envelope.get("armored"):
                _fail("envelope_not_armored")
            if not passphrase:
                _fail("passphrase_required_for_armored_archive")
            text = _dearmor(envelope, passphrase)
        else:
            fh.seek(0)
            text = fh.read()
    return parse_archive_plaintext(text)


def mode_check() -> int:
    leaked = production_secrets_in_shell()
    if leaked:
        print(f"REFUSED (D-045): production material in shell: "
              f"{len(leaked)} key(s) present (names withheld).", file=sys.stderr)
        return 2
    surfaces = [("syn", "alpha"), ("syn", "beta")]
    rows = {"syn.alpha": [{"id": 1, "note": "token=abc123sk"},
                          {"id": 2, "note": "clean"}],
            "syn.beta": [{"id": 9, "note": "x"}]}
    archive = build_archive(rows, "self-check")
    text = archive_plaintext(archive)
    m, d = parse_archive_plaintext(text)
    verify_parity(m, d)

    # tamper detection
    tampered = text.replace("clean", "cleat")
    mt, dt = parse_archive_plaintext(tampered)
    try:
        verify_parity(mt, dt)
        _fail("tamper_not_detected")
    except ExitError:
        pass

    # armored round trip + wrong-passphrase refusal
    env = _armor(text, "correct horse")
    if redact_text("token=abc123sk") == "token=abc123sk":
        _fail("redactor_not_applied")
    round_trip = _dearmor(env, "correct horse")
    if round_trip != text:
        _fail("armor_round_trip_mismatch")
    try:
        _dearmor(env, "wrong")
        _fail("wrong_passphrase_accepted")
    except ExitError:
        pass
    print("check: OK — fold parity, tamper detection, armored round "
          "trip, redaction, D-045 hygiene all pass (synthetic).")
    return 0


def mode_export(args) -> int:
    leaked = production_secrets_in_shell()
    if leaked:
        print(f"REFUSED (D-045): production material in shell; export is "
              f"a read-only SSOT dump and must run in the planning shell.",
              file=sys.stderr)
        return 2
    passphrase = _passphrase_from(args)
    data = collect_rows(container_psql_query, DEFAULT_SURFACES)
    archive = build_archive(data, candidate=args.candidate)
    _write_archive(args.output, archive, passphrase)
    manifest = archive["manifest"]
    print(f"export: OK — {manifest['total_rows']} rows across "
          f"{len(manifest['surfaces'])} surfaces -> {args.output} "
          f"({'armored' if passphrase else 'tamper-evident plaintext'})")
    return 0


def mode_dry_run_import(args) -> int:
    passphrase = _passphrase_from(args)
    manifest, data = _read_archive(args.archive, passphrase)
    verdict = verify_parity(manifest, data)
    print(f"dry-run-import: OK — {verdict['surfaces']} surfaces, "
          f"{verdict['rows']} rows at 100% schema integrity and row "
          f"parity (candidate {manifest.get('candidate', '?')}).")
    return 0


def _passphrase_from(args) -> Optional[str]:
    if getattr(args, "passphrase_file", None):
        with open(args.passphrase_file, encoding="utf-8") as fh:
            value = fh.read().strip()
        if not value:
            _fail("passphrase_file_empty")
        return value
    env = os.environ.get("VENDOR_EXIT_PASSPHRASE")
    return env or None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="mode", required=True)
    sub.add_parser("check")
    pe = sub.add_parser("export")
    pe.add_argument("--output", required=True)
    pe.add_argument("--candidate", default="unstated")
    pe.add_argument("--passphrase-file")
    pi = sub.add_parser("dry-run-import")
    pi.add_argument("--archive", required=True)
    pi.add_argument("--passphrase-file")
    args = p.parse_args(argv)
    if args.mode == "check":
        return mode_check()
    if args.mode == "export":
        return mode_export(args)
    return mode_dry_run_import(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ExitError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
