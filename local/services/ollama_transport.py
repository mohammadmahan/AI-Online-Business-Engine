"""Local Ollama HTTP transport (D-176).

This is the ONLY layer that opens a socket for the AI default. It lives
outside `local/canonical` so the canonical runtime stays free of network
libraries (D-116) and every test can inject a fake transport instead.

The transport is loopback-only by construction: the provider has already
validated `OLLAMA_BASE_URL`, and this module never accepts credentials.
Failures are typed D-052 errors with actionable messages; there is no
fallback to a paid provider or to the mock.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict

from canonical.ai_providers_multi import classify_provider_error
from canonical.ai_runtime import AiProviderError


def make_ollama_transport(base_url: str, model: str,
                          timeout_s: float = 60.0):
    """Build a one-call localhost transport for the Ollama adapter."""

    def transport(request_dict: Dict) -> Dict:
        url = str(request_dict.get("url", ""))
        payload = {k: v for k, v in request_dict.items()
                   if k != "url" and not str(k).startswith("_")}
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:
                pass
            if exc.code == 404 or "not found" in body.lower():
                raise AiProviderError(
                    f"Ollama model {model!r} is not available at "
                    f"{base_url}; run `ollama pull {model}` "
                    "(D-176 fail-closed)", failure_class="B") from exc
            raise classify_provider_error(exc.code, body) from exc
        except TimeoutError as exc:
            raise AiProviderError(
                f"Ollama daemon timed out at {base_url} after "
                f"{timeout_s:g}s (D-176 fail-closed)",
                failure_class="A") from exc
        except urllib.error.URLError as exc:
            raise AiProviderError(
                f"Ollama daemon unreachable at {base_url}: "
                f"{getattr(exc, 'reason', exc)}. Start `ollama serve` and "
                f"pull model {model!r} (D-176 fail-closed)",
                failure_class="A") from exc
        except OSError as exc:
            raise AiProviderError(
                f"Ollama local transport error at {base_url}: {exc} "
                "(D-176 fail-closed)", failure_class="A") from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AiProviderError(
                "Ollama returned a non-JSON response (D-176 fail-closed)",
                failure_class="B") from exc
        if not isinstance(body, dict):
            raise AiProviderError(
                "Ollama returned an unexpected response shape "
                "(D-176 fail-closed)", failure_class="B")
        if body.get("error"):
            raise AiProviderError(
                f"Ollama error: {body['error']} (D-176 fail-closed)",
                failure_class="B")
        return body

    return transport


__all__ = ["make_ollama_transport"]
