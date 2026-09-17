"""Phase 16 — content versioning & media asset tests (D-097..D-100).

Layers:
  M1  contracts: asset validation (checksum/size/mime cross-checks
      against the actual bytes, allow-list, cap), version validation
      (v1 root rule, parent links), single-chain graph validation,
      pure derivation keys.
  M2  engine: content-addressable dedup (same bytes ⇒ one asset),
      append-only chains with stale-head protection, durable
      version-number derivation, lifecycle transitions, historical
      reconstruction.
  M3  worker: idempotent variant derivation (same parent+spec ⇒ same
      reference), unknown-parent failure, quarantine lifecycle
      (referenced kept, orphan quarantined, cooldown elapsed →
      GC-eligible, resurrection on reference), reconciliation.
  M4  LIVE PostgreSQL E2E: real PgEventStore + real PG vault;
      concurrent same-checksum registration (one creator); version
      chain + dedup on live PG; quarantine scan on live PG; restart
      parity.

Zero network; binaries stay behind the injected MediaStore seam; the
canonical modules never touch a cloud SDK or the wall clock.
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical.asset_contracts import (  # noqa: E402
    AS_GC_ELIGIBLE,
    AS_QUARANTINED,
    MAX_ASSET_BYTES,
    VARIANT_SPECS,
    VS_FAILED,
    VS_READY,
    AssetContractError,
    checksum_bytes,
    derivation_key,
    mime_contradicts,
    validate_asset,
    validate_variant_kind,
    validate_version,
    validate_version_graph,
)
from canonical.asset_engine import AssetEngine, _JsonVault  # noqa: E402
from canonical.asset_worker import (  # noqa: E402
    QuarantineScanner,
    VariantProcessor,
)

PNG = b"\x89PNG\r\n\x1a\n"


def _png(tag: bytes) -> bytes:
    return PNG + tag * 16


class _Harness:
    def __init__(self):
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store_path)
        self.vault_path = self.store_path + ".vault"
        from services.sync_engine import EventStore
        self.store = EventStore(self.store_path)
        self.engine = AssetEngine(self.store,
                                  vault=_JsonVault(self.vault_path))

    def cleanup(self):
        import glob
        import shutil
        for p in glob.glob(self.store_path + "*"):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)


# --- M1: contracts ------------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def setUp(self):
        self.data = _png(b"m1")

    def test_valid_asset_passes(self):
        a = validate_asset({"asset_id": "a-1",
                            "checksum": checksum_bytes(self.data),
                            "mime_type": "image/png",
                            "file_size_bytes": len(self.data)},
                           self.data)
        self.assertEqual(a["asset_id"], "a-1")

    def test_class_b_asset_rejections(self):
        ck = checksum_bytes(self.data)
        cases = [
            ("checksum mismatch",
             {"asset_id": "a", "checksum": "ab" * 32,
              "mime_type": "image/png",
              "file_size_bytes": len(self.data)}, self.data),
            ("size mismatch",
             {"asset_id": "a", "checksum": ck,
              "mime_type": "image/png", "file_size_bytes": 3},
             self.data),
            ("mime contradiction",
             {"asset_id": "a", "checksum": ck,
              "mime_type": "image/jpeg",
              "file_size_bytes": len(self.data)}, self.data),
            ("mime not allow-listed",
             {"asset_id": "a", "checksum": ck,
              "mime_type": "video/x-mkv",
              "file_size_bytes": len(self.data)}, self.data),
            ("over cap",
             {"asset_id": "a", "checksum": ck,
              "mime_type": "image/png",
              "file_size_bytes": MAX_ASSET_BYTES + 1}, None),
            ("bad asset_id",
             {"asset_id": "", "checksum": ck,
              "mime_type": "image/png", "file_size_bytes": 1}, None),
            ("non-hex checksum",
             {"asset_id": "a", "checksum": "zz" * 32,
              "mime_type": "image/png", "file_size_bytes": 1}, None),
            ("metadata not dict",
             {"asset_id": "a", "checksum": ck,
              "mime_type": "image/png", "file_size_bytes": 1,
              "metadata": []}, None),
        ]
        for label, asset, data in cases:
            with self.subTest(label):
                with self.assertRaises(AssetContractError):
                    validate_asset(asset, data)

    def test_mime_signature_discipline(self):
        # known signature + matching mime: fine
        self.assertFalse(mime_contradicts(_png(b"x"), "image/png"))
        # known signature + wrong mime: contradiction
        self.assertTrue(mime_contradicts(_png(b"x"), "image/jpeg"))
        # unknown content never contradicts
        self.assertFalse(mime_contradicts(b"\x00\x01\x02",
                                          "text/plain"))

    def test_version_rules(self):
        validate_version({"content_id": "c-1", "version_number": 1,
                          "asset_id": "a-1"})
        validate_version({"content_id": "c-1", "version_number": 2,
                          "asset_id": "a-2",
                          "parent_version_id": "c-1-v1"})
        for bad in (
                {"content_id": "c-1", "version_number": 1,
                 "asset_id": "a", "parent_version_id": "x"},
                {"content_id": "c-1", "version_number": 3,
                 "asset_id": "a"},
                {"content_id": "c-1", "version_number": 0,
                 "asset_id": "a"},
                {"content_id": "c-1", "version_number": True,
                 "asset_id": "a"},
                {"content_id": "", "version_number": 1,
                 "asset_id": "a"}):
            with self.subTest(bad):
                with self.assertRaises(AssetContractError):
                    validate_version(bad)

    def test_graph_single_chain(self):
        good = {1: {"version_id": "v1"},
                2: {"version_id": "v2",
                    "parent_version_id": "v1"},
                3: {"version_id": "v3",
                    "parent_version_id": "v2"}}
        validate_version_graph(good)
        with self.assertRaises(AssetContractError):
            validate_version_graph({1: {"version_id": "v1"},
                                    3: {"version_id": "v3",
                                        "parent_version_id": "v1"}})
        with self.assertRaises(AssetContractError):
            validate_version_graph({1: {"version_id": "v1"},
                                    2: {"version_id": "v2"}})  # no parent
        with self.assertRaises(AssetContractError):
            validate_version_graph({})

    def test_derivation_keys(self):
        ck = checksum_bytes(self.data)
        spec = {"max_edge_px": 320}
        k1 = derivation_key(ck, "thumbnail", spec)
        k2 = derivation_key(ck, "thumbnail", dict(spec))
        self.assertEqual(k1, k2)               # stable
        self.assertNotEqual(k1, derivation_key(
            ck, "standard", spec))             # kind matters
        self.assertNotEqual(k1, derivation_key(
            "f" * 64, "thumbnail", spec))      # parent matters
        self.assertIn("thumbnail", VARIANT_SPECS)
        # validate_variant_kind returns the SPEC dict (D-099)
        self.assertEqual(validate_variant_kind("thumbnail"),
                         VARIANT_SPECS["thumbnail"])


# --- M2: engine ----------------------------------------------------------------


class TestM2Engine(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine

    def tearDown(self):
        self.h.cleanup()

    def test_register_and_dedup(self):
        data = _png(b"dup")
        r1 = self.engine.register_asset(
            data, {"mime_type": "image/png"}, "local://m/1")
        self.assertEqual(r1["status"], "CREATED")
        r2 = self.engine.register_asset(
            data, {"mime_type": "image/png"}, "local://m/ignored")
        self.assertEqual(r2["status"], "DEDUPLICATED")
        self.assertEqual(r1["asset_id"], r2["asset_id"])

    def test_checksum_is_computed_not_declared(self):
        data = _png(b"trust")
        with self.assertRaises(AssetContractError):
            self.engine.register_asset(data, {
                "mime_type": "image/png",
                "checksum": "ab" * 32}, "local://m/x")

    def test_class_b_before_storage(self):
        # mime contradiction must reject before any storage happens
        with self.assertRaises(AssetContractError):
            self.engine.register_asset(_png(b"bad"), {
                "mime_type": "image/jpeg"}, "local://m/x")

    def test_append_only_chain(self):
        a1 = self.engine.register_asset(
            _png(b"v1"), {"mime_type": "image/png"}, "local://m/1")
        a2 = self.engine.register_asset(
            _png(b"v2"), {"mime_type": "image/png"}, "local://m/2")
        v1 = self.engine.append_version("c-1", a1["asset_id"])
        self.assertEqual(v1["version_number"], 1)
        v2 = self.engine.append_version(
            "c-1", a2["asset_id"],
            previous={"version_id": v1["version_id"]})
        self.assertEqual(v2["version_number"], 2)
        # stale head protection
        with self.assertRaises(AssetContractError):
            self.engine.append_version(
                "c-1", a1["asset_id"],
                previous={"version_id": v1["version_id"]})
        # v1 of a fresh content must not carry a previous
        with self.assertRaises(AssetContractError):
            self.engine.append_version("c-2", a1["asset_id"],
                                       previous={"version_id": "x"})
        # durable chain
        versions = self.engine._vault.versions_for("c-1")
        self.assertEqual([v["version_number"] for v in versions],
                         [1, 2])
        validate_version_graph({v["version_number"]: v
                                for v in versions})

    def test_historical_reconstruction(self):
        a1 = self.engine.register_asset(
            _png(b"h1"), {"mime_type": "image/png"}, "local://m/1")
        a2 = self.engine.register_asset(
            _png(b"h2"), {"mime_type": "image/png"}, "local://m/2")
        v1 = self.engine.append_version("c-9", a1["asset_id"])
        self.engine.append_version(
            "c-9", a2["asset_id"],
            previous={"version_id": v1["version_id"]})
        rec1 = self.engine.reconstruct_version("c-9", 1)
        self.assertEqual(rec1["asset"]["asset_id"], a1["asset_id"])
        rec2 = self.engine.reconstruct_version("c-9", 2)
        self.assertEqual(rec2["asset"]["asset_id"], a2["asset_id"])
        self.assertIsNone(self.engine.reconstruct_version("c-9", 7))

    def test_lifecycle_transitions(self):
        a = self.engine.register_asset(
            _png(b"life"), {"mime_type": "image/png"}, "local://m/1")
        ck = a["checksum"]
        self.assertTrue(self.engine.set_lifecycle(
            ck, AS_QUARANTINED, "2026-09-17T12:00:00+00:00")["ok"])
        self.assertEqual(
            self.engine._vault.get_asset(ck)["lifecycle"],
            AS_QUARANTINED)
        self.assertTrue(self.engine.set_lifecycle(
            ck, AS_GC_ELIGIBLE)["ok"])
        self.assertFalse(self.engine.set_lifecycle(
            "f" * 64, AS_QUARANTINED)["ok"])


# --- M3: worker ----------------------------------------------------------------


class TestM3Worker(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()
        self.engine = self.h.engine
        self.vp = VariantProcessor(self.engine)

    def tearDown(self):
        self.h.cleanup()

    def _asset(self, tag):
        return self.engine.register_asset(
            _png(tag), {"mime_type": "image/png"},
            f"local://m/{tag.decode()}")

    def test_variant_idempotency(self):
        a = self._asset(b"var")
        d1 = self.vp.derive(a["checksum"], "thumbnail")
        self.assertEqual(d1["status"], VS_READY)
        d2 = self.vp.derive(a["checksum"], "thumbnail")
        self.assertTrue(d2["reused"])
        self.assertEqual(d1["variant_ref"], d2["variant_ref"])
        # different kind ⇒ different variant
        d3 = self.vp.derive(a["checksum"], "standard")
        self.assertNotEqual(d1["variant_ref"], d3["variant_ref"])

    def test_variant_unknown_parent_fails(self):
        d = self.vp.derive("f" * 64, "thumbnail")
        self.assertEqual(d["status"], VS_FAILED)
        self.assertEqual(d["reason"], "unknown_parent")

    def test_quarantine_lifecycle(self):
        referenced = self._asset(b"ref")
        orphan = self._asset(b"orp")
        self.engine.append_version("c-q", referenced["asset_id"])
        qs = QuarantineScanner(self.engine, cooldown_hours=72)
        # pass 1: the orphan is quarantined, the referenced stays ACTIVE
        s1 = qs.scan("2026-09-17T12:00:00+00:00")
        self.assertEqual(s1["quarantined"], 1)
        self.assertEqual(
            self.engine._vault.get_asset(
                referenced["checksum"])["lifecycle"], "ACTIVE")
        # pass 2 at +24h: cooldown NOT elapsed
        s2 = qs.scan("2026-09-18T12:00:00+00:00")
        self.assertEqual(s2["gc_eligible"], 0)
        # pass 3 at +96h: cooldown elapsed → GC-eligible (flag only)
        s3 = qs.scan("2026-09-21T12:00:00+00:00")
        self.assertEqual(s3["gc_eligible"], 1)
        self.assertEqual(
            self.engine._vault.get_asset(
                orphan["checksum"])["lifecycle"], AS_GC_ELIGIBLE)

    def test_quarantine_resurrection_on_reference(self):
        orphan = self._asset(b"res")
        qs = QuarantineScanner(self.engine, cooldown_hours=72)
        qs.scan("2026-09-17T12:00:00+00:00")
        self.assertEqual(
            self.engine._vault.get_asset(
                orphan["checksum"])["lifecycle"], AS_QUARANTINED)
        # the asset gets referenced → next scan resurrects it
        self.engine.append_version("c-r", orphan["asset_id"])
        s = qs.scan("2026-09-17T13:00:00+00:00")
        self.assertEqual(s["active_kept"], 1)
        self.assertEqual(
            self.engine._vault.get_asset(
                orphan["checksum"])["lifecycle"], "ACTIVE")

    def test_reconciliation_from_durable_data(self):
        self._asset(b"rec1")
        self._asset(b"rec2")
        qs = QuarantineScanner(self.engine)
        rec = qs.reconcile()
        self.assertEqual(rec["assets"], 2)
        self.assertEqual(rec.get("ACTIVE"), 2)


# --- M4: live PostgreSQL E2E -----------------------------------------------------


def _stack_up():
    try:
        import subprocess
        out = subprocess.run(
            ["docker", "compose", "-f", "local/infra/docker-compose.yml",
             "ps", "--format", "json"], capture_output=True, text=True,
            timeout=20, cwd=str(ROOT))
        return out.returncode == 0 and \
            "engine-local-postgres" in out.stdout and \
            "healthy" in out.stdout
    except Exception:
        return False


@unittest.skipUnless(_stack_up(), "live PostgreSQL stack not running")
class TestM4LivePgE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from canonical.asset_engine import _PgVault
        from canonical.notion_ingest import PgEventStore
        cls.PgEventStore = PgEventStore
        cls.PgVault = _PgVault
        cls.run_id = uuid.uuid4().hex[:8]

    def _engine(self):
        return AssetEngine(self.PgEventStore(), vault=self.PgVault())

    def test_live_register_dedup_and_version_chain(self):
        eng = self._engine()
        data = _png(f"live-{self.run_id}".encode())
        r1 = eng.register_asset(data, {"mime_type": "image/png"},
                                "local://m/live1")
        self.assertEqual(r1["status"], "CREATED")
        r2 = eng.register_asset(data, {"mime_type": "image/png"},
                                "local://m/live2")
        self.assertEqual(r2["status"], "DEDUPLICATED")
        self.assertEqual(r1["asset_id"], r2["asset_id"])
        cid = f"live-{self.run_id}"
        v1 = eng.append_version(cid, r1["asset_id"])
        v2 = eng.append_version(
            cid, r1["asset_id"],
            previous={"version_id": v1["version_id"]},
            metadata={"note": "re-encode"})
        self.assertEqual([v1["version_number"],
                          v2["version_number"]], [1, 2])
        rec = eng.reconstruct_version(cid, 1)
        self.assertEqual(rec["version"]["version_id"], v1["version_id"])
        # restart parity: a fresh engine sees the same chain
        fresh = self._engine()
        self.assertEqual(
            [v["version_id"] for v in
             fresh._vault.versions_for(cid)],
            [v1["version_id"], v2["version_id"]])

    def test_live_concurrent_same_checksum_single_creator(self):
        eng = self._engine()
        data = _png(f"race-{self.run_id}".encode())
        results = []
        barrier = threading.Barrier(8)

        def register(n):
            e = self._engine()
            barrier.wait()
            results.append(e.register_asset(
                data, {"mime_type": "image/png"},
                f"local://m/race-{n}")["status"])

        threads = [threading.Thread(target=register, args=(n,))
                   for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count("CREATED"), 1)
        self.assertEqual(results.count("DEDUPLICATED"), 7)

    def test_live_quarantine_scan(self):
        eng = self._engine()
        tag = f"q-{self.run_id}".encode()
        orphan = eng.register_asset(_png(tag),
                                    {"mime_type": "image/png"},
                                    "local://m/orphan")
        # a DIFFERENT run's asset may be mid-cooldown; assert only the
        # delta floor for THIS run's orphan (shared-table discipline)
        qs = QuarantineScanner(eng, cooldown_hours=72)
        qs.scan("2026-09-17T12:00:00+00:00")
        life = self._engine()._vault.get_asset(
            orphan["checksum"])["lifecycle"]
        self.assertIn(life, (AS_QUARANTINED, AS_GC_ELIGIBLE))
        rec = QuarantineScanner(self._engine()).reconcile()
        self.assertGreaterEqual(rec["assets"], 1)


if __name__ == "__main__":
    unittest.main()
