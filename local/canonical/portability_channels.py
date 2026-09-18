"""Phase 24 — D-131 pluggable channel adapters & hot-swap registry.

Pure module (no I/O); audit rows are appended by the caller to the
D-121 log ledger via :func:`swap_audit_row`. Swap verdicts are
deterministic: the logical tick is supplied, never sampled.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from canonical.portability import PortabilityError, PortabilityViolation

__all__ = [
    "ChannelAdapterContract", "ChannelRegistry", "SwapVerdict",
    "swap_audit_record", "hot_swap",
]


@dataclass(frozen=True)
class SwapVerdict:
    """Deterministic hot-swap outcome (D-131)."""

    swapped_from: str
    swapped_to: str
    swapped_at_logical: int


class ChannelAdapterContract(ABC):
    """What every channel adapter (mock/live pair) must satisfy."""

    #: declared lowercase identifier, shared by the mock/live variant pair
    channel: str = ""

    @abstractmethod
    def dispatch(self, target: Dict[str, Any],
                 envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Return the canonical dispatch envelope (same shape for the
        mock and live variant of a channel)."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return {"status": <str>, ...} — same shape for both variants."""


def assert_channel_envelope_parity(mock: ChannelAdapterContract,
                                   live: ChannelAdapterContract,
                                   target: Dict[str, Any],
                                   envelope: Dict[str, Any]) -> None:
    """The mock and live variants must return IDENTICAL envelope shapes."""
    if mock.channel != live.channel:
        raise PortabilityViolation(
            f"variant pair channels differ: {mock.channel!r} vs "
            f"{live.channel!r}")
    a = mock.dispatch(target, envelope)
    b = live.dispatch(target, envelope)
    if type(a) is not type(b) or _shape(a) != _shape(b):
        raise PortabilityViolation(
            f"channel {mock.channel!r}: mock/live envelope shapes differ")
    ha, hb = mock.health(), live.health()
    if type(ha) is not type(hb) or _shape(ha) != _shape(hb):
        raise PortabilityViolation(
            f"channel {mock.channel!r}: mock/live health shapes differ")


def _shape(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        return {str(k): _shape(v, depth + 1)
                for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_shape(v, depth + 1) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return type(value).__name__
    return type(value).__name__


class ChannelRegistry:
    """Hot-swappable channel registry (D-131).

    Names are lowercase identifiers; the same channel name may be
    rebound to a different adapter (mock⇄live, provider A⇄B) and every
    rebind yields a deterministic :class:`SwapVerdict`.
    """

    def __init__(self) -> None:
        import re as _re

        self._re = _re.compile(r"^[a-z][a-z0-9_]{1,39}$")
        self._adapters: Dict[str, ChannelAdapterContract] = {}
        self._active: Dict[str, str] = {}       # channel -> variant name
        self._swaps: List[SwapVerdict] = []

    def register(self, variant: str, adapter: ChannelAdapterContract) -> None:
        if not isinstance(variant, str) or not self._re.match(variant):
            raise PortabilityError(f"variant name {variant!r} invalid")
        channel = getattr(adapter, "channel", "")
        if not isinstance(channel, str) or not self._re.match(channel):
            raise PortabilityError(
                f"adapter {adapter!r} has no declared channel")
        self._adapters[variant] = adapter

    def bind(self, channel: str, variant: str) -> SwapVerdict:
        """Activate a registered variant for a channel (initial bind or
        hot-swap). Raises on unknown variants; verdict is deterministic."""
        if not self._re.match(channel or ""):
            raise PortabilityError(f"channel {channel!r} invalid")
        if variant not in self._adapters:
            raise PortabilityError(f"variant {variant!r} not registered")
        if getattr(self._adapters[variant], "channel", "") != channel:
            raise PortabilityError(
                f"variant {variant!r} is not a {channel!r} adapter")
        previous = self._active.get(channel, channel)
        self._active[channel] = variant
        tick = len(self._swaps) + 1  # deterministic logical clock
        verdict = SwapVerdict(swapped_from=previous, swapped_to=variant,
                              swapped_at_logical=tick)
        self._swaps.append(verdict)
        return verdict

    def adapter(self, channel: str) -> ChannelAdapterContract:
        if channel not in self._active:
            raise PortabilityError(f"channel {channel!r} not bound")
        return self._adapters[self._active[channel]]

    def active_variant(self, channel: str) -> str:
        if channel not in self._active:
            raise PortabilityError(f"channel {channel!r} not bound")
        return self._active[channel]

    @property
    def swaps(self) -> List[SwapVerdict]:
        return list(self._swaps)


def swap_audit_record(ctx, verdict: SwapVerdict, channel: str,
                      logical_at: str) -> Dict[str, Any]:
    """D-121 ``engine.log.v1`` record for one hot-swap — built by the
    SHIPPED emitter (obs_contracts.build_record), so D-114 sanitization
    and the closed enums apply. Domain: ``dispatch`` (the publication
    path channel adapters serve); logical_at is the caller's injected
    logical clock, never wall time."""
    from canonical.obs_contracts import build_record

    return build_record(
        ctx.child(f"swap|{verdict.swapped_at_logical}"),
        domain="dispatch", event="channel_swap",
        logical_at=logical_at, level="INFO", status="SUCCESS",
        entity_ref=channel,
        payload={"channel": channel,
                 "swapped_from": verdict.swapped_from,
                 "swapped_to": verdict.swapped_to,
                 "swap_seq": verdict.swapped_at_logical})


def hot_swap(registry: ChannelRegistry, channel: str, variant: str,
             ctx, logical_at: str, log_ledger=None) -> SwapVerdict:
    """Rebind + audit in one deterministic step. ``log_ledger`` is the
    D-121 :class:`LogLedger` (JSONL parity and/or durable vault); the
    rebind happens BEFORE the audit record is emitted (fail-closed:
    audit failure cannot unswap) and the verdict is deterministic
    either way."""
    verdict = registry.bind(channel, variant)
    if log_ledger is not None:
        log_ledger.emit(ctx, domain="dispatch", event="channel_swap",
                        logical_at=logical_at, entity_ref=channel,
                        payload={"channel": channel,
                                 "swapped_from": verdict.swapped_from,
                                 "swapped_to": verdict.swapped_to,
                                 "swap_seq": verdict.swapped_at_logical})
    return verdict
