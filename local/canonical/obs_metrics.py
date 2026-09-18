"""Phase 22 M2 — deterministic metrics registry & localhost exporter
(D-122).

Zero-dependency operational metrics:

  - DECLARED metrics only: names/labels are registered up front
    (bounded cardinality — undeclared names, undeclared labels or
    over-cardinal label values are Class-B `MetricError`s).
  - DETERMINISTIC updates: counters/gauges/histograms advance via
    explicit `incr`/`set_gauge`/`observe` calls on the LOGICAL
    timeline; histograms use FIXED declared bucket edges (no
    quantile estimation, no wall-clock sampling).
  - `exposition()` renders the Prometheus text exposition format
    (v0.0.4) deterministically — same registry state ⇒ byte-identical
    output (sorted by name, then label set).
  - The loopback-only HTTP exporter serving this text lives in
    `local/services/metrics_exporter.py` (I/O belongs to the services
    layer; canonical modules stay import-free of servers).

Counts are monotone: there is no API to decrease a counter.
"""

import bisect
import threading
from typing import Dict, Optional, Tuple

SCHEMA = "obs.metrics.v1"

_NAME_RULE = "metric names must match [a-zA-Z_][a-zA-Z0-9_]*"
_MAX_METRICS = 256
_MAX_LABELS = 8
_MAX_LABEL_VALUES = 64
DEFAULT_BUCKETS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


class MetricError(ValueError):
    """A metrics-registry violation (Class-B programming error)."""


def _check_name(name: str) -> str:
    import re
    if not isinstance(name, str) or not re.fullmatch(
            r"[a-zA-Z_][a-zA-Z0-9_]*", name):
        raise MetricError(_NAME_RULE)
    return name


def _check_labels(labels) -> Tuple[str, ...]:
    import re
    ls = tuple(labels or ())
    if len(ls) > _MAX_LABELS:
        raise MetricError(f"too many labels (max {_MAX_LABELS})")
    for l in ls:
        if not isinstance(l, str) or not re.fullmatch(
                r"[a-zA-Z_][a-zA-Z0-9_]*", l):
            raise MetricError(f"label name invalid: {l!r}")
    return ls


def _labels_key(labels: Optional[Dict[str, str]],
                declared: Tuple[str, ...]) -> Tuple[Tuple[str, str], ...]:
    labels = labels or {}
    unknown = set(labels) - set(declared)
    if unknown:
        raise MetricError(f"undeclared labels: {sorted(unknown)}")
    missing = set(declared) - set(labels)
    if missing:
        raise MetricError(f"missing labels: {sorted(missing)}")
    # D-124: label values are a telemetry channel — credential-shaped
    # spans are redacted, control characters and oversized values are
    # Class-B rejections (labels carry declared enum/status values only).
    from canonical.obs_contracts import redact
    out = []
    for k, v in labels.items():
        sv = redact(str(v))
        if any(ord(c) < 32 or ord(c) == 127 for c in sv):
            raise MetricError(f"label value has control chars: {k!r}")
        if len(sv) > 128:
            raise MetricError(f"label value too long: {k!r}")
        out.append((k, sv))
    return tuple(sorted(out))


def _escape_label(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt_value(v) -> str:
    if isinstance(v, int):
        return str(v)
    return repr(float(v))


class MetricsRegistry:
    """Declared, bounded, deterministic metric store."""

    def __init__(self):
        self._lock = threading.Lock()
        self._declared: Dict[str, Dict] = {}
        # per-NAME stores: two metrics with identical declared labels
        # must never collide on a bare label key.
        self._counters: Dict[str, Dict[Tuple, int]] = {}
        self._gauges: Dict[str, Dict[Tuple, float]] = {}
        self._hist: Dict[str, Dict] = {}
        self._card: Dict[str, set] = {}

    # -- declaration ------------------------------------------------------

    def _declare(self, name, mtype, help_text, labels, buckets=None):
        _check_name(name)
        ls = _check_labels(labels)
        with self._lock:
            if name in self._declared:
                raise MetricError(f"metric already declared: {name}")
            if len(self._declared) >= _MAX_METRICS:
                raise MetricError(f"registry full (max {_MAX_METRICS})")
            self._declared[name] = {
                "type": mtype, "help": help_text or name, "labels": ls,
                "buckets": tuple(buckets) if buckets else None}
            self._card[name] = set()
        return name

    def declare_counter(self, name: str, help_text: str = "",
                        labels=()) -> str:
        return self._declare(name, "counter", help_text, labels)

    def declare_gauge(self, name: str, help_text: str = "",
                      labels=()) -> str:
        return self._declare(name, "gauge", help_text, labels)

    def declare_histogram(self, name: str, help_text: str = "",
                          labels=(), buckets=DEFAULT_BUCKETS) -> str:
        if not buckets or list(buckets) != sorted(buckets) \
                or len(set(buckets)) != len(buckets):
            raise MetricError("histogram buckets must be non-empty, "
                              "strictly increasing")
        return self._declare(name, "histogram", help_text, labels,
                             buckets=buckets)

    # -- updates (monotone / deterministic) -------------------------------

    def _guard_cardinality(self, name: str, key: Tuple) -> None:
        seen = self._card[name]
        if key not in seen:
            if len(seen) >= _MAX_LABEL_VALUES:
                raise MetricError(
                    f"label-value cardinality exceeded for {name}")
            seen.add(key)

    def incr(self, name: str, labels: Optional[Dict[str, str]] = None,
             by: int = 1) -> int:
        with self._lock:
            d = self._declared.get(name)
            if not d or d["type"] != "counter":
                raise MetricError(f"counter not declared: {name}")
            if not isinstance(by, int) or isinstance(by, bool) or by <= 0:
                raise MetricError("counter increments must be positive "
                                  "integers (counters are monotone)")
            key = _labels_key(labels, d["labels"])
            self._guard_cardinality(name, key)
            cells = self._counters.setdefault(name, {})
            cells[key] = cells.get(key, 0) + by
            return cells[key]

    def set_gauge(self, name: str, value,
                  labels: Optional[Dict[str, str]] = None) -> float:
        with self._lock:
            d = self._declared.get(name)
            if not d or d["type"] != "gauge":
                raise MetricError(f"gauge not declared: {name}")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MetricError("gauge value must be a real number")
            key = _labels_key(labels, d["labels"])
            self._guard_cardinality(name, key)
            cells = self._gauges.setdefault(name, {})
            cells[key] = float(value)
            return cells[key]

    def observe(self, name: str, value,
                labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            d = self._declared.get(name)
            if not d or d["type"] != "histogram":
                raise MetricError(f"histogram not declared: {name}")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MetricError("observation must be a real number")
            v = float(value)
            if v != v or v in (float("inf"), float("-inf")) or v < 0:
                raise MetricError(
                    "observation must be finite and non-negative")
            key = _labels_key(labels, d["labels"])
            self._guard_cardinality(name, key)
            h = self._hist.setdefault(name, {
                "counts": {}, "sum": {}, "n": {}})
            edges = d["buckets"]
            idx = bisect.bisect_left(edges, v)
            cells = h["counts"].setdefault(key, [0] * (len(edges) + 1))
            cells[idx] += 1
            h["sum"][key] = h["sum"].get(key, 0.0) + v
            h["n"][key] = h["n"].get(key, 0) + 1

    # -- Prometheus text exposition (deterministic) ------------------------

    def exposition(self) -> str:
        with self._lock:
            lines = []
            for name in sorted(self._declared):
                d = self._declared[name]
                lines.append(f"# HELP {name} {d['help']}")
                lines.append(f"# TYPE {name} {d['type']}")

                def lbl(key) -> str:
                    if not key:
                        return ""
                    inner = ",".join(f'{k}="{_escape_label(v)}"'
                                     for k, v in key)
                    return "{" + inner + "}"

                if d["type"] == "counter":
                    for key in sorted(self._counters.get(name, {})):
                        lines.append(f"{name}{lbl(key)} "
                                     f"{_fmt_value(self._counters[name][key])}")
                elif d["type"] == "gauge":
                    for key in sorted(self._gauges.get(name, {})):
                        lines.append(f"{name}{lbl(key)} "
                                     f"{_fmt_value(self._gauges[name][key])}")
                else:  # histogram
                    h = self._hist.get(name, {})
                    edges = d["buckets"]
                    for key in sorted(h.get("counts", {})):
                        base = key[0][0] if key else ""
                        cells = h["counts"][key]
                        cum = 0
                        for i, edge in enumerate(edges):
                            cum += cells[i]
                            lines.append(
                                f'{name}_bucket{lbl(key + (("le", str(edge)),))} '
                                f"{cum}")
                        cum += cells[-1]
                        lines.append(f'{name}_bucket{lbl(key + (("le", "+Inf"),))} '
                                     f"{cum}")
                        lines.append(f"{name}_sum{lbl(key)} "
                                     f"{_fmt_value(h['sum'][key])}")
                        lines.append(f"{name}_count{lbl(key)} "
                                     f"{h['n'][key]}")
            return "\n".join(lines) + ("\n" if lines else "")

    # -- introspection -----------------------------------------------------

    def declared_metrics(self) -> Dict[str, Dict]:
        with self._lock:
            return {n: dict(d) for n, d in self._declared.items()}
