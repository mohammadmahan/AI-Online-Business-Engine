#!/usr/bin/env python3
"""Seed the canonical local database with OWNER-APPROVED Registry v1
values (D-031/D-032) and verify every invariant locally.

- Idempotent; verifies counts against local/canonical/vocab.py.
- Local-only throwaway credentials, never committed (D-045/RULES §16).
- No vocabulary is invented here; this is deterministic application of
  approved values.
"""
import hashlib
import os
import re
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from canonical import vocab  # noqa: E402


def db_env() -> dict:
    """Local dev-only connection settings (safe defaults; overridable)."""
    return {
        "PGHOST": os.environ.get("LOCAL_PGHOST", "127.0.0.1"),
        "PGPORT": os.environ.get("LOCAL_PGPORT", "55432"),
        "PGDATABASE": os.environ.get("LOCAL_PGDATABASE", "business_engine_local"),
        "PGUSER": os.environ.get("LOCAL_PGUSER", "engine_local"),
        "PGPASSWORD": os.environ.get("LOCAL_PGPASSWORD", "engine-local-only"),
    }


def psql(sql: str) -> str:
    env = dict(os.environ)
    env.update(db_env())
    proc = subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-A", "-t"],
        input=sql, capture_output=True, text=True, env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed:\n{proc.stderr}")
    return proc.stdout.strip()


def container_psql(sql: str) -> str:
    """Run SQL inside the postgres container (no host psql needed)."""
    name = os.environ.get("LOCAL_PG_CONTAINER", "engine-local-postgres")
    proc = subprocess.run(
        ["docker", "exec", "-i", name, "psql", "-v", "ON_ERROR_STOP=1",
         "-X", "-q", "-A", "-t", "-U", db_env()["PGUSER"],
         "-d", db_env()["PGDATABASE"]],
        input=sql, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"container psql failed:\n{proc.stderr}")
    return proc.stdout.strip()


# --- D-126 transport concurrency ceiling (Phase 23) ---------------------------
# Under upstream degradation, callers queue and then fail FAST with a
# deterministic verdict instead of exhausting connections. The ceiling is
# env-configurable (owner directive: bounds are environment parameters);
# a zero/negative value disables the ceiling (single-threaded tooling).

import threading  # noqa: E402
import time as _time  # noqa: E402

_CEILING_ENV = "PHASE23_PSQL_CONCURRENCY"
_CEILING_DEFAULT = 8
_QUEUE_WAIT_S = float(os.environ.get("PHASE23_PSQL_QUEUE_WAIT", "5"))
_CEILING = threading.BoundedSemaphore(
    max(1, int(os.environ.get(_CEILING_ENV, _CEILING_DEFAULT))))


class TransportSaturation(RuntimeError):
    """Deterministic fast-fail when the concurrency ceiling stays
    saturated for the whole bounded wait (D-126 Class-A verdict)."""


def q(sql: str) -> str:
    """Run via host psql if available, else inside the container.

    Gated by the D-126 concurrency ceiling: at most N concurrent psql
    children; the rest queue up to PHASE23_PSQL_QUEUE_WAIT seconds and
    then fail deterministically (TransportSaturation) — never a
    connection-pool death spiral.
    """
    deadline = _time.monotonic() + _QUEUE_WAIT_S
    while True:
        if _CEILING.acquire(blocking=False):
            break
        if _time.monotonic() >= deadline:
            raise TransportSaturation(
                f"psql transport saturated (ceiling "
                f"{int(os.environ.get(_CEILING_ENV, _CEILING_DEFAULT))}, "
                f"wait {_QUEUE_WAIT_S}s) — deterministic fast-fail")
        _time.sleep(0.05)
    try:
        try:
            subprocess.run(["psql", "--version"], capture_output=True,
                           check=True)
            return psql(sql)
        except (FileNotFoundError, subprocess.CalledProcessError):
            return container_psql(sql)
    finally:
        _CEILING.release()


def verify() -> int:
    counts = {
        "size_families": int(q(
            "SELECT count(*) FROM seed.size_family;")),
        "size_terms": int(q(
            "SELECT count(*) FROM seed.size_term;")),
        "colors": int(q(
            "SELECT count(*) FROM seed.color_term;")),
        "category_pairs": int(q(
            "SELECT count(*) FROM seed.category_term;")),
        "primaries": int(q(
            "SELECT count(DISTINCT primary_fa) FROM seed.category_term;")),
    }
    expected = {
        "size_families": vocab.EXPECTED_COUNTS["size_families"],
        # size_terms: exactly the terms the D-030 seed gate admits
        # (strict O/I/L-safe + explicit owner-sanctioned codes, D-057).
        "size_terms": sum(
            1 for f in vocab.SIZE_TERMS
            for _, c in vocab.SIZE_TERMS[f] if vocab.is_seedable(c)),
        "colors": vocab.EXPECTED_COUNTS["colors"],
        "category_pairs": vocab.EXPECTED_COUNTS["category_pairs"],
        "primaries": vocab.EXPECTED_COUNTS["primary_categories"],
    }
    ok = True
    for k in expected:
        mark = "OK " if counts[k] == expected[k] else "FAIL"
        if counts[k] != expected[k]:
            ok = False
        print(f"  [{mark}] {k}: {counts[k]} (expected {expected[k]})")

    # O/I/L audit directly in the database (D-030). Codes carrying
    # an explicit owner sanction (D-057: LRG) are audited separately
    # — they are allowed by decision, not by validator weakness.
    sanctioned = tuple(vocab.OWNER_SANCTIONED_CODES)
    exempt = "".join(
        " AND code <> '{}'".format(c) for c in sanctioned)
    bad = int(q(
        "SELECT count(*) FROM seed.color_term "
        "WHERE (code ~ '[OIL]' OR code <> upper(code))" + exempt + ";"))
    bad += int(q(
        "SELECT count(*) FROM seed.size_term "
        "WHERE (code ~ '[OIL]' OR code <> upper(code))" + exempt + ";"))
    print(f"  [{'OK ' if bad == 0 else 'FAIL'}] O/I/L-safe codes in DB: "
          f"{bad} violations")
    if bad:
        ok = False
    blocked = [
        (f, t, c)
        for f in vocab.SIZE_TERMS
        for t, c in vocab.SIZE_TERMS[f]
        if not vocab.is_seedable(c)
    ]
    for family, term, code in blocked:
        print(f"  [GATE] BLOCKED at seed: {family}/{term} → {code} "
              f"(no owner sanction)")
    if blocked:
        ok = False  # seed is intentionally incomplete until resolved
    return 0 if ok else 1


def main() -> int:
    # One statement, one trailing ON CONFLICT (a per-row clause inside
    # VALUES is a syntax error — caught on the first live seed run).
    rows = [
        f"('{key}','{label}',{i})"
        for i, (key, label) in enumerate(sorted(vocab.SIZE_FAMILIES))
    ]
    sql = ["BEGIN;"]
    sql.append(
        "INSERT INTO seed.size_family (family_key,label_fa,sort_order) VALUES "
        + ", ".join(rows) + " ON CONFLICT (family_key) DO NOTHING;")
    # D-030 seed gate: a term seeds only if its code is strictly
    # O/I/L-safe or carries an explicit owner sanction (D-057).
    # Surfaced here, never silently resolved.
    allowed = [
        (f, t, c)
        for f in vocab.SIZE_TERMS
        for t, c in vocab.SIZE_TERMS[f]
        if vocab.is_seedable(c)
    ]
    vals = ", ".join(f"('{f}','{t}','{c}')" for f, t, c in allowed)
    sql.append(
        "INSERT INTO seed.size_term (family_key,display_fa,code) VALUES "
        + vals + " ON CONFLICT (family_key,display_fa) DO NOTHING;")
    vals = ", ".join(f"('{t}','{c}')" for t, c in vocab.COLOR_TERMS)
    sql.append(
        "INSERT INTO seed.color_term (display_fa,code) VALUES "
        + vals + " ON CONFLICT (display_fa) DO NOTHING;")
    vals = ", ".join(f"('{p}','{l}')" for p, l in vocab.CATEGORY_PAIRS)
    sql.append(
        "INSERT INTO seed.category_term (primary_fa,leaf_fa) VALUES "
        + vals + " ON CONFLICT (primary_fa,leaf_fa) DO NOTHING;")
    sql.append("COMMIT;")
    q("\n".join(sql))
    print("Seed applied (idempotent). Verifying:")
    return verify()


if __name__ == "__main__":
    sys.exit(main())
