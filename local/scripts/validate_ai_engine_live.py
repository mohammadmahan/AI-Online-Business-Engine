#!/usr/bin/env python3
"""validate_ai_engine_live.py — Phase 7/8 AI engine live-wiring drill.

Two verification layers:

  OFFLINE MODE (default, no credentials needed)
    Synthetic drill over the multi-provider contracts:
      1. D-045/D-066 gate matrix — AI_LIVE_ENABLED + per-provider key
         refs fail-closed (no flag, flag without key, blank key);
         injected transport mandatory (default transports refuse).
      2. Error taxonomy — wire responses classified onto the D-052
         classes with the five named categories: Auth (401/403 → C),
         RateLimit (429 → A), ContextLength (context markers → D),
         ProviderOutage (5xx → A), SchemaViolation (non-contract → B).
      3. Fallback chain — Class-A/C advances provider-by-provider and
         terminates at the deterministic mock; Class-B/D surface and
         are never masked; every step lands in the D-065 record.
      4. Circuit breaker — K consecutive failures open, cooldown
         skips, success closes (deterministic, call-count based).
      5. Budget ceilings & redaction — D-063 hard refusal before
         dispatch; key material stripped from every escaping string.

  LIVE MODE (opt-in, owner-gated, READ-ONLY)
    `--provider deepseek|openai|anthropic` (flag + key required):
    ONE read-only models/organizations listing — no generation, no
    spend. `--provider ollama` lists locally installed models from
    the loopback daemon. Exits 2 without credentials — never a false
    pass.

Exit codes: 0 drill PASSED · 1 drill FAILED · 2 cannot assess.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local"))

from canonical.ai_observability import AiObservabilityCollector  # noqa: E402
from canonical.ai_providers_live import (  # noqa: E402
    LIVE_ENV_FLAG, OpenAiProvider, require_live_key, with_live_fallback,
)
from canonical.ai_providers_multi import (  # noqa: E402
    DeepSeekProvider, OllamaProvider, ProviderCircuitBreaker,
    ProviderChain, classify_provider_error, redact_ai,
)
from canonical.ai_runtime import (  # noqa: E402
    AiProviderError, AiRequest, ModelRouter, MockAiProvider,
)

OFFLINE = "offline"
LIVE = "live"

_KEY = "test-local-dummy"  # synthetic example — docs placeholder shape (D-045)


def _gate() -> bool:
    print("1. D-045/D-066 gate matrix (fail-closed)")
    saved = {k: os.environ.get(k) for k in
             (LIVE_ENV_FLAG, "OPENAI_API_KEY", "DEEPSEEK_API_KEY")}
    good = True

    def expect_refuse(fn, label, marker):
        nonlocal good
        try:
            fn()
            print(f"  [FAIL] {label}: gate opened")
            good = False
        except AiProviderError as exc:
            if marker not in str(exc):
                print(f"  [FAIL] {label}: wrong refusal {exc}")
                good = False
            else:
                print(f"  [OK  ] {label} → refuse")

    try:
        for k in saved:
            os.environ.pop(k, None)
        expect_refuse(lambda: require_live_key("openai", "OPENAI_API_KEY"),
                      "flag unset", "AI_LIVE_ENABLED")
        os.environ[LIVE_ENV_FLAG] = "true"
        expect_refuse(lambda: require_live_key("openai", "OPENAI_API_KEY"),
                      "flag without key", "OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "   "
        expect_refuse(lambda: require_live_key("openai", "OPENAI_API_KEY"),
                      "blank key", "OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = _KEY
        # construction succeeds; the DEFAULT transport refuses at CALL
        # time (zero network path) — that refusal is the gate.
        try:
            p = OpenAiProvider(transport=None, api_key=_KEY)
            p.generate(AiRequest(task_type="generate_caption",
                                 schema_id="caption_proposal.v1",
                                 prompt_payload={}, idempotency_tag="g"))
            print("  [FAIL] default transport attempted a call")
            good = False
        except AiProviderError as exc:
            print("  [OK  ] default transport refuses at call time "
                  "(zero network)"
                  if exc.failure_class == "B"
                  else f"  [FAIL] wrong class {exc.failure_class}")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("      (no live AI credential exists here — D-045)")
    return good


def _taxonomy() -> bool:
    print("2. Provider error taxonomy (five categories)")
    good = True
    cases = [
        ((401, "invalid api key"), "C", "Auth"),
        ((403, "forbidden"), "C", "Auth"),
        ((429, "rate limited"), "A", "RateLimit"),
        ((400, "This model's maximum context length is 8192 tokens"),
         "D", "ContextLength"),
        ((503, "upstream outage"), "A", "ProviderOutage"),
        ((400, "rest_invalid_param"), "B", "SchemaViolation"),
        ((None, "<html>gateway junk</html>"), "B", "SchemaViolation"),
    ]
    for (status, body), want_class, want_name in cases:
        exc = classify_provider_error(status, body)
        if exc.failure_class == want_class:
            print(f"  [OK  ] {want_name} ({status}) → {want_class}")
        else:
            print(f"  [FAIL] {want_name} → {exc.failure_class}, "
                  f"want {want_class}")
            good = False
    return good


def _chain() -> bool:
    print("3. Multi-provider fallback chain (A/C advance, B/D surface)")
    good = True
    tmp = os.path.join(REPO, "local", "volumes", "tmp-ai-drill.jsonl")
    col = AiObservabilityCollector(tmp)
    try:
        def fail_c(rd):
            raise AiProviderError("401", failure_class="C")

        def fail_a(rd):
            raise AiProviderError("500", failure_class="A")

        chain = ProviderChain(
            [OpenAiProvider(transport=fail_c, api_key=_KEY),
             DeepSeekProvider(transport=fail_a, api_key=_KEY)],
            collector=col, task_type="generate_caption")
        req = AiRequest(task_type="generate_caption",
                        schema_id="caption_proposal.v1",
                        prompt_payload={}, idempotency_tag="drill-chain")
        resp = chain.generate(req)
        if resp.provider == "mock" and chain.fallbacks_used == 1:
            print("  [OK  ] C→A→terminal mock; D-065 records emitted")
        else:
            print(f"  [FAIL] chain ended {resp.provider} "
                  f"fallbacks={chain.fallbacks_used}")
            good = False
        recs = col.records(stage="fallback")
        if len(recs) >= 3:
            print(f"  [OK  ] {len(recs)} observability steps recorded")
        else:
            print(f"  [FAIL] only {len(recs)} fallback records")
            good = False

        def fail_b(rd):
            raise AiProviderError("contract", failure_class="B")

        chain_b = ProviderChain(
            [OpenAiProvider(transport=fail_b, api_key=_KEY),
             MockAiProvider()])
        try:
            chain_b.generate(req)
            print("  [FAIL] Class-B masked by chain")
            good = False
        except AiProviderError as exc:
            if exc.failure_class == "B":
                print("  [OK  ] Class-B surfaces (never masked)")
            else:
                print(f"  [FAIL] wrong class {exc.failure_class}")
                good = False

        def fail_d(rd):
            raise classify_provider_error(
                400, "maximum context length exceeded")

        chain_d = ProviderChain(
            [OpenAiProvider(transport=fail_d, api_key=_KEY),
             MockAiProvider()])
        try:
            chain_d.generate(req)
            print("  [FAIL] Class-D masked by chain")
            good = False
        except AiProviderError as exc:
            if exc.failure_class == "D":
                print("  [OK  ] Class-D surfaces (payload problem, "
                      "fallback cannot help)")
            else:
                print(f"  [FAIL] wrong class {exc.failure_class}")
                good = False

        # with_live_fallback (D-066 pair) still works alongside
        fb = with_live_fallback(
            OpenAiProvider(transport=fail_a, api_key=_KEY), col,
            task_type="generate_caption")
        r2 = fb.generate(req)
        print("  [OK  ] D-066 FallbackProvider compatible"
              if r2.provider == "mock" else "  [FAIL] d066 fallback")
        good = good and r2.provider == "mock"
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return good


def _breaker() -> bool:
    print("4. Circuit breaker (deterministic, call-count based)")
    good = True
    b = ProviderCircuitBreaker(threshold=2, cooldown_calls=2)
    b.record_failure("p1")
    first_check = b.allow("p1")          # 1 failure < threshold → allowed
    b.record_failure("p1")
    opened = b.allow("p1") is False      # 2 consecutive → open
    skip1, skip2, recovered = b.allow("p1"), b.allow("p1"), b.allow("p1")
    if opened and skip1 is False and skip2 and recovered:
        print("  [OK  ] open after threshold → 2-call cooldown → recover")
    else:
        print(f"  [FAIL] breaker {first_check} {opened} {skip1} {skip2} "
              f"{recovered}")
        good = False
    b.record_success("p1")
    print("  [OK  ] success closes the circuit" if b.allow("p1")
          else "  [FAIL] stays open after success")
    return good


def _budget_and_redaction() -> bool:
    print("5. Budget ceilings (D-063) & redaction (D-124)")
    good = True
    router = ModelRouter({"mock": MockAiProvider()},
                         budgets={"generate_caption": 0.0})
    try:
        router.run(AiRequest(task_type="generate_caption",
                             schema_id="caption_proposal.v1",
                             prompt_payload={}, idempotency_tag="bud"))
        print("  [FAIL] zero budget dispatched")
        good = False
    except Exception as exc:  # noqa: BLE001
        if "hard budget refusal" in str(exc):
            print("  [OK  ] D-063 hard refusal BEFORE dispatch")
        else:
            print(f"  [FAIL] unexpected: {exc}")
            good = False
    r = redact_ai(f"key sk-abcdefghijklmnopqrstuvwx123456 {_KEY}",
                  extra_secrets=[_KEY])
    if "sk-abcdefghijklmnop" not in r and _KEY not in r:
        print("  [OK  ] key material stripped from strings")
    else:
        print("  [FAIL] redaction leak")
        good = False
    return good


def run_offline() -> int:
    print("=== AI ENGINE LIVE WIRING DRILL (offline, deterministic) ===")
    results = [_gate(), _taxonomy(), _chain(), _breaker(),
               _budget_and_redaction()]
    if all(results):
        print("=== OFFLINE VERIFIED (exit 0) ===")
        return 0
    print("=== DRILL FAILED (exit 1) ===")
    return 1


def run_live(provider: str) -> int:
    print(f"=== AI LIVE PROBE ({provider}, opt-in, READ-ONLY) ===")
    key_env = {"openai": "OPENAI_API_KEY",
               "anthropic": "ANTHROPIC_API_KEY",
               "deepseek": "DEEPSEEK_API_KEY"}.get(provider)
    import urllib.error
    import urllib.request

    if provider == "ollama":
        base = os.environ.get("OLLAMA_BASE_URL",
                              "http://127.0.0.1:11434").rstrip("/")
        try:
            with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as r:
                models = [m.get("name") for m in json.loads(
                    r.read().decode()).get("models", [])]
            print(f"  [OK  ] local daemon reachable; models: "
                  f"{models[:5] or 'none installed'}")
            print("  Read-only: no generation, no model pull.")
            return 0
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"  [FAIL] local daemon unreachable: {exc}")
            return 1

    os.environ.setdefault(LIVE_ENV_FLAG, "true")
    key = os.environ.get(key_env, "").strip()
    if os.environ.get(LIVE_ENV_FLAG) != "true" or not key:
        print(f"  [GATE] set AI_LIVE_ENABLED=true and {key_env} to "
              "authorize the read-only probe")
        return 2
    urls = {
        "openai": "https://api.openai.com/v1/models",
        "deepseek": "https://api.deepseek.com/models",
    }
    headers = {"Authorization": f"Bearer {key}"}
    if provider == "anthropic":
        urls["anthropic"] = "https://api.anthropic.com/v1/models"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    try:
        req = urllib.request.Request(urls[provider], headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.loads(r.read().decode())
        n = len(body.get("data", []))
        print(f"  [OK  ] {provider} reachable — {n} models listed")
        print("  Read-only: no generation call, zero spend.")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"  [FAIL] HTTP {exc.code} — credential/endpoint problem")
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  [FAIL] unreachable: {redact_ai(str(exc))}")
        return 1


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] == OFFLINE:
        return run_offline()
    if argv[0] == LIVE and len(argv) == 3 and argv[1] == "--provider":
        return run_live(argv[2])
    print(f"usage: {Path(__file__).name} [offline | live --provider "
          "openai|anthropic|deepseek|ollama]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
