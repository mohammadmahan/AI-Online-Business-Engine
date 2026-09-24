"""Stage F/G — durable replay store on the PostgreSQL SSOT (D-148).

The D-146 gate's single-use nonce burn has so far lived in memory
(`MemReplayStore`); a host restart would forget every consumption and
resurrect a spent authorization. This adapter persists the burn to the
D-055 SSOT so consumption survives restarts, hosts, and processes —
and composes into `OwnerApprovalGate` unchanged (same `consume(key)
-> bool` contract).

Design:

  SCHEMA      — `security.consumed_owner_nonces` (idempotent DDL, the
                established `CREATE ... IF NOT EXISTS` pattern):
                primary key on (nonce_hash, scope), the burn's
                canonical context, audit metadata, and a UTC
                timestamp. `nonce_hash` is the D-146 burn key —
                already a SHA-256 of the binding — so no raw nonce
                material is ever stored (D-124).
  ATOMICITY   — one statement: `INSERT ... ON CONFLICT DO NOTHING
                RETURNING nonce_hash`. Postgres adjudicates the race:
                exactly one concurrent contender sees a row returned
                (consumed=True); every loser sees zero rows
                (consumed=False). Verified live: 1 winner / 5 losers
                under a 6-thread race. No read-modify-write window.
  PURITY      — the engine performs no I/O itself: the SQL transport
                is an INJECTED callable `exec(sql) -> str` (in
                production `seed_registry.q`, in tests an in-process
                fake). No wall clock in the core — `utc_stamp` is
                injected; tests pin a fixed value.
  FAIL-CLOSED — transport exceptions NEVER open the gate: a failing
                consume raises (the gate's caller surfaces it as a
                BLOCKED verdict). A lost DB is never an approval.
  AUDIT       — each burn row carries the token id, session, target
                env, and scope so D-112/D-146 evidence can join on
                the (public) token id without touching secret
                material.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional

try:  # battery package path or script cwd path
    from ..memory.vector_store import deep_redact  # type: ignore
except ImportError:  # pragma: no cover - script invocation
    from memory.vector_store import deep_redact  # type: ignore

__all__ = ["ReplayStoreError", "PgReplayStore", "SCHEMA_DDL", "DEFAULT_SCOPE"]

DEFAULT_SCOPE = "stage-f-cutover"

SCHEMA_DDL = (
    "CREATE SCHEMA IF NOT EXISTS security;\n"
    "CREATE TABLE IF NOT EXISTS security.consumed_owner_nonces (\n"
    "    nonce_hash    text NOT NULL,\n"
    "    scope         text NOT NULL,\n"
    "    token_id      text NOT NULL,\n"
    "    session_id    text NOT NULL,\n"
    "    target_env    text NOT NULL,\n"
    "    logical_at    text NOT NULL,\n"
    "    burned_at_utc text NOT NULL,\n"
    "    PRIMARY KEY (nonce_hash, scope)\n"
    ");"
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ReplayStoreError(RuntimeError):
    """Durable burn failed — the gate MUST refuse (fail closed)."""


class PgReplayStore:
    """Crash-resilient single-use nonce store on the PostgreSQL SSOT.

    Injected (RULES §35):
      exec       — ``sql -> str`` transport (seed_registry.q in
                   production; in-process fake in tests).
      utc_stamp  — ``() -> str`` UTC stamp for audit metadata
                   (injected; never read from a wall clock inside
                   the core).
      scope      — burn namespace (default `stage-f-cutover`);
                   distinct scopes never share burns.
      ensure_schema — run the idempotent DDL on first use (default
                   True).
    """

    def __init__(self, exec_fn: Callable[[str], str],
                 utc_stamp: Callable[[], str],
                 scope: str = DEFAULT_SCOPE,
                 ensure_schema: bool = True) -> None:
        if not callable(exec_fn):
            raise ReplayStoreError("exec transport required")
        if not callable(utc_stamp):
            raise ReplayStoreError("utc_stamp callable required")
        if not isinstance(scope, str) or not scope or len(scope) > 64:
            raise ReplayStoreError("scope invalid")
        self._exec = exec_fn
        self._stamp = utc_stamp
        self._scope = scope
        self._ready = False
        if ensure_schema:
            self._run(SCHEMA_DDL)
            self._ready = True

    # -- internals -----------------------------------------------------------

    def _run(self, sql: str) -> str:
        try:
            return self._exec(sql)
        except ReplayStoreError:
            raise
        except Exception as exc:  # transport failure — never an approval
            raise ReplayStoreError(
                f"replay store transport failed: "
                f"{deep_redact(type(exc).__name__)}") from exc

    # -- the D-146 consume contract --------------------------------------------

    def consume(self, key: str, token_id: str = "", session_id: str = "",
                target_env: str = "", logical_at: str = "") -> bool:
        """Burn one nonce key atomically. True on FIRST use; False when
        the key already exists (replay). Raises on transport failure —
        the caller must refuse, never proceed on a lost store.
        """
        if not isinstance(key, str) or not _HEX64.match(key or ""):
            raise ReplayStoreError("nonce key must be sha256 hex64")
        if not self._ready:
            self._run(SCHEMA_DDL)
            self._ready = True
        out = self._run(
            "INSERT INTO security.consumed_owner_nonces "
            "(nonce_hash, scope, token_id, session_id, target_env, "
            "logical_at, burned_at_utc) VALUES ("
            f"'{key}', '{self._scope}', "
            f"'{_lit(token_id)}', '{_lit(session_id)}', "
            f"'{_lit(target_env)}', '{_lit(logical_at)}', "
            f"'{_lit(self._stamp())}') "
            "ON CONFLICT (nonce_hash, scope) DO NOTHING "
            "RETURNING nonce_hash").strip()
        return bool(out)

    def burned(self, key: str) -> bool:
        """Read-only check (evidence/inspection; never authoritative —
        consume() is the only adjudicator)."""
        if not _HEX64.match(key or ""):
            raise ReplayStoreError("nonce key must be sha256 hex64")
        out = self._run(
            "SELECT count(*) FROM security.consumed_owner_nonces "
            f"WHERE nonce_hash = '{key}' AND scope = '{self._scope}'"
        ).strip()
        return out.isdigit() and int(out) > 0


def _lit(value: str) -> str:
    """Escape a string literal for the injected transport (values are
    audit metadata: token ids, session/env names, ticks — never
    credentials; still escaped defensively)."""
    return str(value or "").replace("'", "''")


def from_seed_registry(utc_stamp: Callable[[], str],
                       scope: str = DEFAULT_SCOPE) -> "PgReplayStore":
    """Production wiring: the established psql/container transport."""
    import sys

    def _exec(sql: str) -> str:
        # local/scripts is on sys.path in every runner (battery
        # convention); import lazily so the core stays import-free.
        try:
            from seed_registry import q  # type: ignore
        except ImportError as exc:  # pragma: no cover - wiring error
            raise ReplayStoreError(
                "seed_registry transport unavailable") from exc
        return q(sql)

    return PgReplayStore(_exec, utc_stamp, scope=scope)
