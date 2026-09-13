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


def q(sql: str) -> str:
    """Run via host psql if available, else inside the container."""
    try:
        subprocess.run(["psql", "--version"], capture_output=True, check=True)
        return psql(sql)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return container_psql(sql)


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
        # size_terms: approved count MINUS blocked-conflict terms held
        # at the D-030 gate pending owner clarification.
        "size_terms": (vocab.EXPECTED_COUNTS["size_terms"]
                       - len(vocab.blocked_seed_terms())),
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

    # O/I/L audit directly in the database (D-030).
    bad = int(q(
        "SELECT count(*) FROM seed.color_term "
        "WHERE code ~ '[OIL]' OR code <> upper(code);"))
    bad += int(q(
        "SELECT count(*) FROM seed.size_term "
        "WHERE code ~ '[OIL]' OR code <> upper(code);"))
    print(f"  [{'OK ' if bad == 0 else 'FAIL'}] O/I/L-safe codes in DB: "
          f"{bad} violations")
    if bad:
        ok = False
    blocked = vocab.blocked_seed_terms()
    for family, term, code, reason in blocked:
        print(f"  [GATE] BLOCKED at seed: {family}/{term} → {code}")
        print(f"         {reason}")
    if blocked:
        ok = False  # seed is intentionally incomplete until resolved
    return 0 if ok else 1


def main() -> int:
    rows = []
    for i, (key, label) in enumerate(sorted(vocab.SIZE_FAMILIES)):
        rows.append(
            f"('{key}','{label}',{i}) ON CONFLICT (family_key) DO NOTHING")
    sql = ["BEGIN;"]
    sql.append(
        "INSERT INTO seed.size_family (family_key,label_fa,sort_order) VALUES "
        + ", ".join(rows) + ";")
    # D-030 seed gate: tracked code conflicts (approved D-032 value vs
    # D-030 rule 1) are NOT inserted — they wait for owner
    # clarification. Surfaced here, never silently resolved.
    blocked = {(f, t) for f, t, _, _ in vocab.blocked_seed_terms()}
    allowed = [
        (f, t, c)
        for f in vocab.SIZE_TERMS
        for t, c in vocab.SIZE_TERMS[f]
        if (f, t) not in blocked
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
