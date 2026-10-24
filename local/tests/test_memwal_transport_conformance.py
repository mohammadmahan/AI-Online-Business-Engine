"""D-142 — MemWal transport seam conformance battery (hermetic).

Pins `local/src/memory/memwal_transport.py`:

  E — envelope contract: `memwal.transport.v1` shape, canonical bytes,
      deterministic ordering, tamper refusal.
  K — idempotency keys: stable across ordering and processes, sensitive
      to a single changed character, refused for empty batches.
  C — chunking: count AND byte ceilings, complete/no-duplicate rows,
      oversized row refused rather than truncated.
  R — redaction re-assertion at the edge (D-114/D-124), nested values,
      and the canary never reaching a candidate transport.
  T — D-044/D-052 taxonomy: the retryable/non-retryable split, the
      ambiguous-timeout reconciliation flag, status mapping.
  N — zero-blockage: `TransportClient.send` returns a verdict for a
      raising transport, a malformed reply, a refusal and its own
      misuse; the `MemWalClientAdapter` bridge still degrades to
      `pending_remote` without raising.
  P — purity: no network import in the module (AST).

No socket, no DB, no credential: every transport is a local lambda.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from local.src.memory.vector_store import (
    DEFAULT_EMBEDDING_DIM, INTERACTION, MemoryRecord,
)
from local.src.memory.memwal_adapter import MemWalClientAdapter
from local.src.memory.memwal_transport import (
    DEFAULT_MAX_BYTES, DEFAULT_MAX_ROWS, ENVELOPE_FORMAT, TRANSPORT_FAULTS,
    TransportClient, TransportContractError, build_envelope, canonical_bytes,
    chunk_rows, classify_error, classify_status, idempotency_key, redact_rows,
    validate_envelope,
)

MODULE = REPO / "local" / "src" / "memory" / "memwal_transport.py"

VEC = tuple(0.1 * (i % 7 + 1) for i in range(DEFAULT_EMBEDDING_DIM))

# Deliberate redaction canary, assembled at runtime so line-based secret
# scanners never flag this file while the D-114 patterns stay proven.
CANARY = "sk" + "-" + ("Z" * 24)


def row(record_id: str = "r1", seq: int = 1, content: str = "hello",
        agent_id: str = "agent-a", session_id: str = "s1",
        kind: str = INTERACTION) -> dict:
    """A WAL-row-shaped dict small enough to chunk by hand."""
    return {
        "seq": seq, "record_id": record_id, "agent_id": agent_id,
        "session_id": session_id, "kind": kind, "content": content,
        "embedding": [0.1, 0.2], "logical_ts": seq, "prev_hash": "genesis",
    }


def records(count: int) -> list:
    return [
        MemoryRecord(record_id=f"rec-{i}", agent_id="agent-a",
                     session_id="s1", kind=INTERACTION,
                     content=f"interaction {i}", embedding=VEC,
                     logical_ts=i, seq=i)
        for i in range(count)
    ]


class TestEnvelope(unittest.TestCase):
    def test_shape_and_format(self):
        env = build_envelope([row()], batch_index=0, batch_count=1)
        self.assertEqual(env["format"], ENVELOPE_FORMAT)
        self.assertEqual(env["row_count"], 1)
        self.assertEqual(env["batch_index"], 0)
        self.assertEqual(env["batch_count"], 1)
        self.assertEqual(env["rows"][0]["record_id"], "r1")
        self.assertEqual(env["idempotency_key"], idempotency_key(env["rows"]))

    def test_canonical_bytes_are_stable(self):
        a = build_envelope([row("r1", 1), row("r2", 2)],
                           batch_index=0, batch_count=1)
        b = build_envelope([row("r2", 2), row("r1", 1)],
                           batch_index=0, batch_count=1)
        self.assertEqual(canonical_bytes(a), canonical_bytes(b))

    def test_order_independent_of_input(self):
        env = build_envelope([row("b", 2), row("a", 1)],
                             batch_index=0, batch_count=1)
        self.assertEqual([r["record_id"] for r in env["rows"]], ["a", "b"])

    def test_validation_rejects_tampered_content(self):
        env = build_envelope([row()], batch_index=0, batch_count=1)
        env["rows"][0]["content"] = "tampered"
        with self.assertRaises(TransportContractError) as ctx:
            validate_envelope(env)
        self.assertEqual(str(ctx.exception), "envelope_idempotency_key_mismatch")

    def test_validation_rejects_wrong_format(self):
        env = build_envelope([row()], batch_index=0, batch_count=1)
        env["format"] = "memwal.transport.v0"
        with self.assertRaises(TransportContractError):
            validate_envelope(env)

    def test_validation_rejects_bad_position(self):
        env = build_envelope([row()], batch_index=0, batch_count=2)
        env["batch_index"] = 2
        with self.assertRaises(TransportContractError) as ctx:
            validate_envelope(env)
        self.assertEqual(str(ctx.exception), "envelope_batch_position_invalid")

    def test_validation_rejects_non_object(self):
        with self.assertRaises(TransportContractError):
            validate_envelope([row()])

    def test_build_rejects_impossible_position(self):
        with self.assertRaises(TransportContractError):
            build_envelope([row()], batch_index=1, batch_count=1)
        with self.assertRaises(TransportContractError):
            build_envelope([row()], batch_index=0, batch_count=0)


class TestIdempotency(unittest.TestCase):
    def test_key_is_stable_for_same_rows(self):
        a = idempotency_key([row("r1", 1), row("r2", 2)])
        b = idempotency_key([row("r2", 2), row("r1", 1)])
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)
        int(a, 16)  # hex

    def test_key_changes_on_one_character(self):
        a = idempotency_key([row("r1", 1, content="hello")])
        b = idempotency_key([row("r1", 1, content="hellp")])
        self.assertNotEqual(a, b)

    def test_key_separated_by_namespace(self):
        r = [row("r1", 1)]
        self.assertNotEqual(idempotency_key(r, namespace="a"),
                            idempotency_key(r, namespace="b"))

    def test_empty_batch_refused(self):
        with self.assertRaises(TransportContractError) as ctx:
            idempotency_key([])
        self.assertEqual(str(ctx.exception), "rows_required")

    def test_row_without_identity_refused(self):
        with self.assertRaises(TransportContractError):
            idempotency_key([{"seq": 1, "content": "x"}])

    def test_row_without_seq_refused(self):
        with self.assertRaises(TransportContractError):
            idempotency_key([{"record_id": "r1", "content": "x"}])


class TestChunking(unittest.TestCase):
    def test_respects_row_ceiling(self):
        rows = [row(f"r{i}", i) for i in range(5)]
        chunks = chunk_rows(rows, max_rows=2, max_bytes=10 ** 6)
        self.assertEqual([len(c) for c in chunks], [2, 2, 1])

    def test_respects_byte_ceiling(self):
        rows = [row(f"r{i}", i, content="x" * 200) for i in range(4)]
        single = len(canonical_bytes([rows[0]]))
        chunks = chunk_rows(rows, max_rows=100, max_bytes=single + 50)
        for chunk in chunks:
            self.assertLessEqual(len(canonical_bytes(chunk)), single + 50)
        self.assertGreater(len(chunks), 1)

    def test_every_row_exactly_once_in_order(self):
        rows = [row(f"r{i}", i) for i in range(7)]
        chunks = chunk_rows(rows, max_rows=3, max_bytes=10 ** 6)
        flat = [r["record_id"] for c in chunks for r in c]
        self.assertEqual(flat, sorted(flat, key=lambda x: int(x[1:])))
        self.assertEqual(len(flat), len(set(flat)))
        self.assertEqual(len(flat), len(rows))

    def test_deterministic_across_input_order(self):
        a = [row("b", 2), row("a", 1), row("c", 3)]
        self.assertEqual(chunk_rows(a, max_rows=2, max_bytes=10 ** 6),
                         chunk_rows(list(reversed(a)), max_rows=2,
                                    max_bytes=10 ** 6))

    def test_oversized_row_refused_not_truncated(self):
        big = row("r-big", 1, content="x" * 500)
        with self.assertRaises(TransportContractError) as ctx:
            chunk_rows([big], max_rows=10, max_bytes=50)
        self.assertIn("row_exceeds_batch_budget:r-big", str(ctx.exception))

    def test_invalid_limits_refused(self):
        for kwargs in ({"max_rows": 0}, {"max_rows": -1},
                       {"max_bytes": 0}, {"max_bytes": -5}):
            with self.subTest(**kwargs), self.assertRaises(TransportContractError):
                chunk_rows([row()], **kwargs)

    def test_default_ceilings_are_positive(self):
        self.assertGreaterEqual(DEFAULT_MAX_ROWS, 1)
        self.assertGreaterEqual(DEFAULT_MAX_BYTES, 1024)


class TestEdgeRedaction(unittest.TestCase):
    def test_canary_removed_before_send(self):
        env = build_envelope([row(content=f"token {CANARY} leaked")],
                             batch_index=0, batch_count=1)
        self.assertNotIn(CANARY, canonical_bytes(env).decode("utf-8"))
        self.assertIn("[REDACTED]", env["rows"][0]["content"])

    def test_nested_values_redacted(self):
        nested = row(content="clean")
        nested["meta"] = {"inner": [f"a {CANARY}", {"deep": CANARY}]}
        safe = redact_rows([nested])[0]
        self.assertNotIn(CANARY, canonical_bytes(safe).decode("utf-8"))

    def test_non_string_values_preserved(self):
        safe = redact_rows([row()])[0]
        self.assertEqual(safe["embedding"], [0.1, 0.2])
        self.assertEqual(safe["seq"], 1)

    def test_redaction_is_idempotent(self):
        once = redact_rows([row(content=f"x {CANARY}")])
        twice = redact_rows(once)
        self.assertEqual(once, twice)

    def test_candidate_never_receives_canary(self):
        seen = []

        def transport(envelope):
            seen.append(canonical_bytes(envelope).decode("utf-8"))
            return {"ok": True}

        verdict = TransportClient(transport).send(
            [row(content=f"credential {CANARY} here")])
        self.assertTrue(verdict.ok)
        self.assertTrue(seen)
        self.assertNotIn(CANARY, "".join(seen))


class TestTaxonomy(unittest.TestCase):
    def test_timeout_is_ambiguous_not_plain_retry(self):
        fault = classify_error(TimeoutError("no verdict"))
        self.assertEqual(fault.code, "TRANSPORT_AMBIGUOUS_TIMEOUT")
        self.assertTrue(fault.retryable)
        self.assertTrue(fault.requires_reconciliation)

    def test_connection_error_is_unavailable(self):
        fault = classify_error(ConnectionError("refused"))
        self.assertEqual(fault.code, "TRANSPORT_UNAVAILABLE")
        self.assertTrue(fault.retryable)
        self.assertFalse(fault.requires_reconciliation)

    def test_permission_is_auth_non_retryable(self):
        fault = classify_error(PermissionError("401"))
        self.assertEqual(fault.code, "TRANSPORT_AUTH_FAILED")
        self.assertFalse(fault.retryable)

    def test_contract_and_value_are_validation(self):
        for error in (TransportContractError("bad"), ValueError("bad")):
            self.assertEqual(classify_error(error).code,
                             "TRANSPORT_VALIDATION_REFUSED")
            self.assertFalse(classify_error(error).retryable)

    def test_unknown_is_internal_non_retryable(self):
        fault = classify_error(RuntimeError("?"))
        self.assertEqual(fault.code, "TRANSPORT_INTERNAL")
        self.assertFalse(fault.retryable)

    def test_status_mapping(self):
        expected = {
            400: "TRANSPORT_VALIDATION_REFUSED",
            401: "TRANSPORT_AUTH_FAILED",
            403: "TRANSPORT_AUTH_FAILED",
            408: "TRANSPORT_TIMEOUT",
            409: "TRANSPORT_CONFLICT",
            422: "TRANSPORT_VALIDATION_REFUSED",
            429: "TRANSPORT_RATE_LIMITED",
            500: "TRANSPORT_UNAVAILABLE",
            503: "TRANSPORT_UNAVAILABLE",
        }
        for status, code in expected.items():
            with self.subTest(status=status):
                self.assertEqual(classify_status(status).code, code)

    def test_unknown_status_is_not_retryable(self):
        fault = classify_status(418)
        self.assertEqual(fault.code, "TRANSPORT_INTERNAL")
        self.assertFalse(fault.retryable)

    def test_invalid_status_refused(self):
        for status in (0, -1, "500", None):
            with self.subTest(status=status), \
                    self.assertRaises(TransportContractError):
                classify_status(status)  # type: ignore[arg-type]

    def test_only_ambiguous_fault_requires_reconciliation(self):
        recon = {code for code, f in TRANSPORT_FAULTS.items()
                 if f.requires_reconciliation}
        self.assertEqual(recon, {"TRANSPORT_AMBIGUOUS_TIMEOUT"})


class TestClientNeverRaises(unittest.TestCase):
    def test_happy_path_delivers_every_row(self):
        seen = []

        def transport(envelope):
            seen.append(envelope)
            return {"ok": True}

        verdict = TransportClient(transport, max_rows=2,
                                  max_bytes=10 ** 6).send(
            [row(f"r{i}", i) for i in range(5)])
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.code, "TRANSPORT_OK")
        self.assertEqual(verdict.delivered_rows, 5)
        self.assertEqual(verdict.batches, 3)
        self.assertEqual([len(e["rows"]) for e in seen], [2, 2, 1])
        self.assertEqual([e["batch_index"] for e in seen], [0, 1, 2])
        self.assertEqual([e["batch_count"] for e in seen], [3, 3, 3])

    def test_raising_transport_becomes_verdict(self):
        def transport(envelope):
            raise ConnectionError("no route")

        verdict = TransportClient(transport).send([row()])
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, "TRANSPORT_UNAVAILABLE")
        self.assertTrue(verdict.retryable)
        self.assertEqual(verdict.delivered_rows, 0)
        self.assertEqual(verdict.failed_batch, 0)

    def test_timeout_flags_reconciliation(self):
        def transport(envelope):
            raise TimeoutError("?")  # noqa: UP041 - deliberate

        verdict = TransportClient(transport).send([row()])
        self.assertTrue(verdict.requires_reconciliation)
        self.assertEqual(verdict.reason, "transport_ambiguous_timeout")

    def test_partial_delivery_is_counted(self):
        calls = {"n": 0}

        def transport(envelope):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ConnectionError("dropped")
            return {"ok": True}

        verdict = TransportClient(transport, max_rows=1,
                                  max_bytes=10 ** 6).send(
            [row(f"r{i}", i) for i in range(3)])
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.delivered_rows, 1)
        self.assertEqual(verdict.failed_batch, 1)

    def test_malformed_reply_refused(self):
        for reply in (None, [], "ok", {"delivered": 1}):
            with self.subTest(reply=reply):
                verdict = TransportClient(lambda e, r=reply: r).send([row()])
                self.assertEqual(verdict.code, "TRANSPORT_MALFORMED_RESPONSE")
                self.assertFalse(verdict.retryable)

    def test_remote_refusal_with_known_code(self):
        verdict = TransportClient(
            lambda e: {"ok": False, "code": "TRANSPORT_RATE_LIMITED"}
        ).send([row()])
        self.assertEqual(verdict.code, "TRANSPORT_RATE_LIMITED")
        self.assertTrue(verdict.retryable)

    def test_remote_refusal_with_unknown_code_is_generic(self):
        verdict = TransportClient(
            lambda e: {"ok": False, "code": "SOMETHING_ELSE"}
        ).send([row()])
        self.assertEqual(verdict.code, "TRANSPORT_REMOTE_REFUSED")
        self.assertFalse(verdict.retryable)

    def test_no_remote_is_reported_not_raised(self):
        verdict = TransportClient(None).send([row()])
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.reason, "no_remote_injected")
        self.assertFalse(verdict.retryable)

    def test_own_misuse_becomes_verdict(self):
        verdict = TransportClient(lambda e: {"ok": True}).send([])
        self.assertEqual(verdict.code, "TRANSPORT_VALIDATION_REFUSED")
        self.assertIn("rows_required", verdict.reason)


class TestAdapterBridge(unittest.TestCase):
    def test_adapter_reports_remote_ok(self):
        envelopes = []
        client = TransportClient(lambda e: (envelopes.append(e), {"ok": True})[1],
                                 max_rows=1, max_bytes=10 ** 6)
        adapter = MemWalClientAdapter(remote=client.as_row_transport())
        report = adapter.sync(records(2))
        self.assertFalse(report.degraded)
        self.assertEqual(report.pushed_remote, 2)
        self.assertEqual(report.reason, "remote_ok")
        self.assertEqual(len(envelopes), 2)
        self.assertTrue(all(e["format"] == ENVELOPE_FORMAT for e in envelopes))

    def test_adapter_degrades_without_raising(self):
        def transport(envelope):
            raise ConnectionError("down")

        adapter = MemWalClientAdapter(
            remote=TransportClient(transport).as_row_transport())
        report = adapter.sync(records(2))  # must not raise
        self.assertTrue(report.degraded)
        self.assertEqual(report.pushed_remote, 0)
        self.assertEqual(report.pending_remote, 2)
        self.assertIn("remote_unavailable", report.reason)

    def test_adapter_still_local_only_by_default(self):
        report = MemWalClientAdapter().sync(records(2))
        self.assertFalse(report.degraded)
        self.assertEqual(report.kept_local, 2)
        self.assertEqual(report.reason, "local_only_no_remote_injected")


class TestPurity(unittest.TestCase):
    def test_module_imports_no_network_client(self):
        forbidden = {"socket", "ssl", "http", "urllib", "requests", "httpx",
                     "aiohttp", "urllib3"}
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & forbidden, set())

    def test_module_defines_no_retry_policy(self):
        """D-044 leaves retry counts/backoff to the owning workflow."""
        source = MODULE.read_text(encoding="utf-8")
        for banned in ("time.sleep", "max_retries", "backoff="):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
