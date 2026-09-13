#!/usr/bin/env python3
"""Apply local/db/schema.sql to the canonical local database
(idempotent) and run seed verification. Host psql first, container
psql as fallback."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCHEMA = os.path.join(ROOT, "local", "db", "schema.sql")
sys.path.insert(0, os.path.join(HERE))
from seed_registry import db_env, container_psql, q  # noqa: E402


def main() -> int:
    with open(SCHEMA, encoding="utf-8") as f:
        sql = f.read()
    q(sql)
    print("Schema applied (idempotent).")
    # Sanity: the five schemas exist.
    out = q("SELECT string_agg(nspname, ',' ORDER BY nspname) "
            "FROM pg_namespace "
            "WHERE nspname IN ('seed','canonical','registry','events',"
            "'provenance');")
    expected = "canonical,events,provenance,registry,seed"
    if out != expected:
        print(f"FAIL: schemas present = {out!r}, expected {expected!r}")
        return 1
    print(f"  [OK ] schemas: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
