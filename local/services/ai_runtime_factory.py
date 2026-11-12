"""Build the D-176 local-first AI runtime.

The canonical layer owns the provider-neutral boundary and the default
routing policy (`ollama`). This service layer wires the real localhost
transport into that boundary. Keeping the HTTP client here preserves the
D-116 canonical no-network rule while making the development default
actually usable.

No paid provider is constructed or selected. A missing daemon/model
surfaces from the transport as a clear Class-A/B error; there is no
fallback to a paid API or to the mock in this factory.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from canonical.ai_providers_multi import (OllamaProvider,
                                          resolve_ollama_settings)
from canonical.ai_runtime import ModelRouter
from services.ollama_transport import make_ollama_transport


def build_default_ai_router(
        *, transport: Optional[Callable[[Dict], Dict]] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_s: float = 60.0,
        ledger=None,
        budgets: Optional[Dict[str, float]] = None,
        policy=None) -> ModelRouter:
    """Return a router whose only registered provider is local Ollama."""
    model_name, resolved_base = resolve_ollama_settings(model, base_url)
    local_transport = transport or make_ollama_transport(
        resolved_base, model_name, timeout_s)
    provider = OllamaProvider(transport=local_transport,
                              model=model_name,
                              base_url=resolved_base,
                              timeout_s=timeout_s)
    return ModelRouter({"ollama": provider}, policy=policy, ledger=ledger,
                       budgets=budgets)


__all__ = ["build_default_ai_router"]
