#!/usr/bin/env python3
"""validate_orchestration_live.py — Phase 11 orchestration E2E drill
(D-077/D-078 pipeline).

Two verification layers:

  OFFLINE MODE (default, no credentials, no network)
    Full generation→publish synthetic drill over the real shipped
    engines:
      1. AI proposal generated (router) and submitted durably;
      2. review gate: PROPOSED/IN_REVIEW proposals refused (D-050);
      3. accepted proposal → fan-out SUCCESS across instagram+telegram
         via the REAL outbox publishers (D-070/D-074);
      4. duplicate job refused (anti-race lock);
      5. duplicate CONTENT across jobs deduplicated by the publishers
         (duplicate_publish_blocked, no double posts);
      6. target crash isolation (one target's failure is that target's
         outcome; other targets complete, D-077);
      7. Instagram Class-C cooldown (transient, no DLQ) and Telegram
         Class-E freeze+DLQ (human intervention) boundaries;
      8. compensation markers durable + idempotent, no ledger mutation;
      9. receipts carry no credential material (D-124);
     10. RED-tier staging authority (D-050) proposal-gated.

  LIVE MODE (opt-in, owner-gated, D-045)
    Read-only reachability probe of the local core services in the
    deployment manifest (postgres 127.0.0.1:55432, n8n 127.0.0.1:15678,
    WordPress 127.0.0.1:18080, MinIO 127.0.0.1:19000). No writes, no
    publishes, no secrets printed; exits 2 if the gate is closed.

Usage:
    python3 local/scripts/validate_orchestration_live.py
    python3 local/scripts/validate_orchestration_live.py --live
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "local"))

from canonical.content_pipeline import (  # noqa: E402
    ContentToChannelPipeline,
    PipelineAuthorityError,
)
from canonical.ai_runtime import (  # noqa: E402
    AiRequest,
    MockAiProvider,
    ModelRouter,
)
from canonical.ai_proposal_lifecycle import ProposalLifecycle  # noqa: E402
from canonical.orchestration_engine import (  # noqa: E402
    FanOutEngine,
    _JsonFanOutLock,
)
from canonical.orchestration_contracts import (  # noqa: E402
    OrchestrationContractError,
)
from canonical.instagram_publisher import (  # noqa: E402
    InstagramOutboxPublisher,
    _JsonVault as _IgVault,
)
from canonical.telegram_publisher import TelegramOutboxPublisher  # noqa: E402
from canonical.instagram_adapter import MockInstagramAdapter  # noqa: E402
from canonical.telegram_adapter import MockTelegramAdapter  # noqa: E402
from services.sync_engine import (  # noqa: E402
    EventStore,
    MappingRegistry,
    ProvenanceEngine,
    SyncEngine,
)
from services import mock_woo  # noqa: E402

_MEDIA = {"kind": "photo", "bytes_hash": "a" * 64,
          "aspect_ratio": "4:5", "file_size_bytes": 480_000}
_TP = {"telegram": {"chat_id": "@myshop", "parse_mode": "HTML"}}

_LINES: list = []


def _line(text: str, ok: bool) -> None:
    _LINES.append((text, ok))
    print(f"  [{'OK  ' if ok else 'FAIL'}] {text}")


def _product(pid: str) -> dict:
    return {"product_id": pid, "name": f"محصول {pid}",
            "primary_category": "پوشاک مردانه", "leaf_category": "تیشرت",
            "attributes": {"برند": None}, "list_price": 300000,
            "product_sale": None, "product_sale_until": None,
            "status": "active", "publication_status": "published",
            "media_refs": ["media.local/x.jpg"], "description": None,
            "short_description": None, "name_en": None}


def _world(tmp: str):
    store = EventStore(os.path.join(tmp, "e.json"))
    prov = ProvenanceEngine(os.path.join(tmp, "p.jsonl"))
    sync = SyncEngine(mock_woo.MockWooAdapter(), MappingRegistry(path=None),
                      store, prov)
    router = ModelRouter({"mock": MockAiProvider()})
    lifecycle = ProposalLifecycle(store, prov,
                                  applier=lambda pid, ref: {"ok": True})
    ig_pub = InstagramOutboxPublisher(
        EventStore(os.path.join(tmp, "ig.json")),
        _IgVault(os.path.join(tmp, "igv.json")), prov)
    tg_pub = TelegramOutboxPublisher(
        EventStore(os.path.join(tmp, "tg.json")),
        _IgVault(os.path.join(tmp, "tgv.json")), prov)
    ig_adapter = MockInstagramAdapter()
    tg_adapter = MockTelegramAdapter()

    def ig_bind(adapted, actor="pipeline"):
        ig_pub.enqueue(adapted, actor=actor)
        return ig_pub.publish(adapted, ig_adapter, actor=actor)

    def tg_bind(adapted, actor="pipeline"):
        tg_pub.enqueue(adapted, actor=actor)
        return tg_pub.publish(adapted, tg_adapter, actor=actor)

    binds = {"instagram": ig_bind, "telegram": tg_bind}
    fanout = FanOutEngine(store, binds,
                          lock=_JsonFanOutLock(os.path.join(tmp, "l.json")))
    pipe = ContentToChannelPipeline(
        store, sync_engine=sync, fanout_engine=fanout,
        publish_binds=binds, lifecycle=lifecycle, provenance=prov)
    return pipe, router, lifecycle, ig_pub, tg_pub


def _accept(pipe, router, lifecycle, tag: str) -> str:
    prop = pipe.generate_proposal(router, AiRequest(
        task_type="propose_content_idea",
        schema_id="content_idea_proposal.v1",
        prompt_payload={"topic": f"d-{tag}"},
        idempotency_tag=f"p11d-{tag}"))
    pid = lifecycle.submit(prop)["proposal_id"]
    lifecycle.decide(pid, action="submit_review", reviewer="H-1")
    lifecycle.decide(pid, action="accept", reviewer="H-1")
    return pid


def _kw(job_id, pid, **over):
    kw = dict(campaign_id="camp-drill", content_id="POST-1",
              proposal_id=pid, text="کت پاییزی جدید",
              hashtags=["mod", "new"],
              scheduled_slot="2026-09-16T12:00:00+00:00",
              media=_MEDIA, targets=["instagram", "telegram"],
              target_params=_TP)
    kw.update(over)
    kw["job_id"] = job_id
    return kw


def drill() -> int:
    tmp = tempfile.mkdtemp(prefix="orch-drill-")
    pipe, router, lifecycle, ig_pub, tg_pub = _world(tmp)

    # 1) generation + review gate
    prop = pipe.generate_proposal(router, AiRequest(
        task_type="propose_content_idea",
        schema_id="content_idea_proposal.v1",
        prompt_payload={"topic": "d-gate"}, idempotency_tag="p11d-gate"))
    pid_gate = lifecycle.submit(prop)["proposal_id"]
    try:
        pipe.fanout_job(**_kw("drill-gate", pid_gate))
        _line("review gate refuses PROPOSED proposal (D-050)", False)
    except PipelineAuthorityError:
        _line("review gate refuses PROPOSED proposal (D-050)", True)
    lifecycle.decide(pid_gate, action="submit_review", reviewer="H-1")
    try:
        pipe.fanout_job(**_kw("drill-gate", pid_gate))
        _line("review gate refuses IN_REVIEW proposal", False)
    except PipelineAuthorityError:
        _line("review gate refuses IN_REVIEW proposal", True)

    # 2) happy path via REAL outbox publishers
    pid = _accept(pipe, router, lifecycle, "happy")
    r = pipe.fanout_job(**_kw("drill-happy", pid))
    _line("accepted proposal → instagram+telegram published "
          f"({r['aggregate']})",
          r["outcomes"] == {"instagram": "published",
                            "telegram": "published"}
          and r["aggregate"] == "SUCCESS")

    # 3) duplicate job refused (anti-race lock)
    r2 = pipe.fanout_job(**_kw("drill-happy", pid))
    _line("duplicate job_id refused (already_claimed)",
          r2.get("routed") is False
          and r2.get("reason") == "already_claimed")

    # 4) duplicate content deduped by publishers (no double posts)
    r3 = pipe.fanout_job(**_kw("drill-dup", pid,
                               targets=["instagram"]))
    _line("duplicate content blocked by D-070 outbox (no double posts)",
          r3["outcomes"]["instagram"] == "duplicate_publish_blocked")

    # 5) local Class-B before any dispatch
    try:
        pipe.fanout_job(**_kw("drill-classb", pid,
                              hashtags=["bad tag!"]))
        _line("invalid payload rejected locally (Class-B prevention)",
              False)
    except OrchestrationContractError:
        _line("invalid payload rejected locally (Class-B prevention)",
              True)

    # 6) crash isolation + compensation (fresh content id: the D-070
    #    terminal guard must not mask the crash with a duplicate block)
    pid2 = _accept(pipe, router, lifecycle, "iso")
    orig = pipe.fanout.publish_binds["telegram"]

    def crashing(adapted, actor="pipeline"):
        raise RuntimeError("transport down (drill)")

    pipe.fanout.publish_binds["telegram"] = crashing
    r4 = pipe.fanout_job(**_kw("drill-iso", pid2,
                               content_id="POST-ISO"))
    pipe.fanout.publish_binds["telegram"] = orig
    _line("target crash isolated (instagram completed, telegram failed)",
          r4["outcomes"].get("instagram") == "published"
          and r4["outcomes"].get("telegram") ==
          "target_dispatch_crashed")
    try:
        c = pipe.compensate_job("drill-iso")
        _line("compensation markers durable + deterministic",
              c["compensation"] == {"instagram": "COMPLETED",
                                    "telegram": "REFUNDED"})
    except Exception:
        # a regression that leaves no durable receipts must FAIL the
        # drill, never crash it (fail-closed reporting)
        _line("compensation markers durable + deterministic", False)
    eids = [d.get("event_id") for d in
            pipe.fanout._store_refs()]
    _line("COMPENSATED marker is an append-only durable event",
          "orchestration|drill-iso|compensated" in eids)

    # 7) Class-C cooldown (instagram) — transient, no DLQ
    tmp2 = tempfile.mkdtemp(prefix="orch-drill-c-")
    pipe2, router2, life2, ig2, _ = _world(tmp2)
    ig2_rate = MockInstagramAdapter(fail_with="rate_limit")

    def ig2_bind(adapted, actor="pipeline"):
        ig2.enqueue(adapted, actor=actor)
        return ig2.publish(adapted, ig2_rate, actor=actor)

    pipe2.fanout.publish_binds["instagram"] = ig2_bind
    pid3 = _accept(pipe2, router2, life2, "classc")
    r5 = pipe2.fanout_job(**_kw("drill-c", pid3, targets=["instagram"]))
    _line("Instagram Class-C rate limit → cooldown, no DLQ",
          r5["outcomes"].get("instagram") == "cooldown"
          and len(ig2.dlq) == 0)
    try:
        c2 = pipe2.compensate_job("drill-c")
        _line("Class-C compensation verdict = RETRY_SCHEDULED",
              c2["compensation"].get("instagram") == "RETRY_SCHEDULED")
    except Exception:
        _line("Class-C compensation verdict = RETRY_SCHEDULED", False)

    # 8) Class-E freeze + DLQ (telegram blocked chat)
    tmp3 = tempfile.mkdtemp(prefix="orch-drill-e-")
    pipe3, router3, life3, _, tg3 = _world(tmp3)
    tg3_blk = MockTelegramAdapter(fail_with="blocked")

    def tg3_bind(adapted, actor="pipeline"):
        tg3.enqueue(adapted, actor=actor)
        return tg3.publish(adapted, tg3_blk, actor=actor)

    pipe3.fanout.publish_binds["telegram"] = tg3_bind
    pid4 = _accept(pipe3, router3, life3, "classe")
    r6 = pipe3.fanout_job(**_kw("drill-e", pid4, targets=["telegram"]))
    _line("Telegram Class-E chat blocked → queue_frozen + DLQ",
          r6["outcomes"]["telegram"] == "queue_frozen"
          and len(tg3.dlq) == 1)

    # 9) RED-tier staging authority (D-050), proposal-gated
    pid5 = _accept(pipe, router, lifecycle, "stage")
    try:
        pipe.stage_product(_product("P82001"), [], "2026-09-16",
                           proposal_id=pid5, authorized=False)
        _line("unauthorized RED-tier staging refused (D-050)", False)
    except Exception as exc:
        _line("unauthorized RED-tier staging refused (D-050)",
              type(exc).__name__ == "AuthorityError")
    staged = pipe.stage_product(_product("P82002"), [], "2026-09-16",
                                proposal_id=pid5, authorized=True)
    _line("authorized staging creates hidden Woo draft",
          staged.get("action") == "created_hidden")

    # 10) hygiene: receipts carry no credential material
    blob = json.dumps(r, ensure_ascii=False)
    clean = all(m not in blob for m in
                ("sk-", "Bearer ", "consumer_key", "api_key"))
    _line("receipts carry no credential material (D-124)", clean)

    good = all(ok for _, ok in _LINES)
    print(f"\n=== {'OFFLINE VERIFIED' if good else 'OFFLINE FAILURES'} "
          f"({sum(1 for _, ok in _LINES if ok)}/{len(_LINES)}) ===")
    return 0 if good else 1


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_get(url: str, timeout: float = 3.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read(200)


def live_probe() -> int:
    """Opt-in, read-only, D-045 fail-closed."""
    if os.environ.get("ORCH_LIVE_ENABLED", "").strip().lower() != "true":
        print("LIVE probe is owner-gated (D-045): set "
              "ORCH_LIVE_ENABLED=true to probe local services "
              "(read-only).")
        return 2
    targets = [
        ("postgres", "127.0.0.1", 55432, None),
        ("n8n", "127.0.0.1", 15678, "http://127.0.0.1:15678/healthz"),
        ("wordpress", "127.0.0.1", 18080, None),
        ("minio", "127.0.0.1", 19000, None),
    ]
    ok = True
    for name, host, port, url in targets:
        if not _port_open(host, port):
            print(f"  [FAIL] {name}: {host}:{port} unreachable")
            ok = False
            continue
        if url:
            try:
                status, body = _http_get(url)
                print(f"  [OK  ] {name}: HTTP {status} {body[:40]!r}")
            except Exception as exc:
                print(f"  [FAIL] {name}: http probe failed: {exc}")
                ok = False
        else:
            print(f"  [OK  ] {name}: {host}:{port} reachable")
    print("LIVE probe is READ-ONLY: no publishes, no writes, no "
          "secrets read or printed.")
    return 0 if ok else 1


def main() -> int:
    if "--live" in sys.argv:
        return live_probe()
    return drill()


if __name__ == "__main__":
    sys.exit(main())
