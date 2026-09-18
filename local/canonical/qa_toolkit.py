"""Phase 21 M1 — QA toolkit: tier taxonomy, state-machine audit,
deterministic fault injection, seeded fuzzing (D-117..D-120).

Pure stdlib, fully deterministic: no os, no time/datetime, no
random, no network (D-116 discipline — AST-audited). Every helper
here is exercised by the Phase 21 battery.

  - Tier taxonomy (D-120): the declared four tiers and a
    machine-readable report reconciling the discovery census + tier
    counts + a skip census that MUST be zero for a green run.
  - StateMachineAudit (D-117): proves an edge matrix is CLOSED —
    the legal set is exactly the declared set, terminals have no
    exits, and every undeclared (from, to) pair is refused.
  - Fault injection (D-118): failure seams as INJECTED callables —
    `FaultScript` schedules deterministic failures per call index;
    `flaky_dispatch` fails transiently then succeeds (retry
    ladders); `always_fail` produces recorded, never-silent errors.
  - SeedCorpus/mutate/fuzz_entry (D-119): a deterministic
    mutational fuzzer — seeded corpus, fixed mutation ladder. Every
    mutator produces a BOUNDED payload (size/depth capped at
    generation time), so execution cannot hang. The TARGET
    classifies each verdict: normal return = accepted; one of the
    caller-supplied allowed contract exceptions = rejected; ANY
    other exception = an unhandled fuzz failure (surfaced, never
    swallowed).
"""

import json
from typing import Callable, Dict, Iterable, List, Sequence, Set, Tuple

# --- D-120: suite taxonomy ------------------------------------------------------

TIER_UNIT = "T1_UNIT"
TIER_LADDER = "T2_SUBSYSTEM_LADDER"
TIER_INTEGRATION = "T3_LOCAL_PG_INTEGRATION"
TIER_E2E = "T4_FULL_E2E"
TIERS = (TIER_UNIT, TIER_LADDER, TIER_INTEGRATION, TIER_E2E)

# module-prefix → tier (a test file maps to exactly one tier);
# unmatched modules default to TIER_UNIT (pure contract tests)
TIER_BY_MODULE: Tuple[Tuple[str, str], ...] = (
    ("test_ladder", TIER_LADDER),
)


def tier_for_module(module_name: str) -> str:
    """Deterministic tier assignment by module prefix. Live-PG E2E
    classes are counted separately via the census rows'
    `integration_tests` field (T3), not by module name."""
    for prefix, tier in TIER_BY_MODULE:
        if module_name == prefix or module_name.endswith("." + prefix) \
                or module_name.startswith(prefix):
            return tier
    return TIER_UNIT


def build_tier_report(census: Sequence[Dict],
                      total_tests: int,
                      skipped: int,
                      failures: int) -> Dict:
    """Machine-readable run report (D-120). `census` rows:
    {"module": name, "tests": n, "integration_tests": m,
    "e2e_tests": k}. Green requires zero skips AND zero failures
    AND the tier counts to reconcile with the census totals."""
    tiers = {t: 0 for t in TIERS}
    module_total = 0
    for row in census:
        tests = int(row.get("tests", 0))
        integration = int(row.get("integration_tests", 0))
        e2e = int(row.get("e2e_tests", 0))
        module_total += tests
        tiers[TIER_E2E] += e2e
        tiers[TIER_INTEGRATION] += integration
        tiers[tier_for_module(row["module"])] += \
            tests - integration - e2e
    reconciles = module_total == int(total_tests)
    green = bool(reconciles and skipped == 0 and failures == 0)
    return {
        "tiers": tiers,
        "total_tests": int(total_tests),
        "census_total": module_total,
        "skipped": int(skipped),
        "failures": int(failures),
        "reconciles": reconciles,
        "green": green,
        "schema": "qa.tier_report.v1",
    }


# --- D-120: discovery-output census ------------------------------------------------

import re

_LOCATOR_RE = re.compile(r"^\S+ \((?P<mod>[\w.]+)\.(?P<cls>\w+)\)")


def build_census(verbose_output: str) -> List[Dict]:
    """Parse `unittest -v` discovery output into D-120 census rows.

    Census rule (part of D-120, battery-asserted):
      - classes ending `LivePgE2E`  → T3_LOCAL_PG_INTEGRATION;
      - classes ending `EndToEnd`   → T4_FULL_E2E (cross-subsystem
        flows, e.g. the ladder L11 flow and the Phase 5 n8n bridge);
      - everything else in the module → the module's tier
        (`tier_for_module`), defaulting to T1_UNIT.

    Returns one row per module: {"module", "tests",
    "integration_tests", "e2e_tests"} sorted by module name —
    deterministic regardless of discovery order.
    """
    per_class: Dict[Tuple[str, str], int] = {}
    for line in verbose_output.splitlines():
        m = _LOCATOR_RE.match(line)
        if m:
            key = (m.group("mod"), m.group("cls"))
            per_class[key] = per_class.get(key, 0) + 1
    rows: Dict[str, Dict] = {}
    for (mod, cls), n in sorted(per_class.items()):
        row = rows.setdefault(mod, {"module": mod, "tests": 0,
                                    "integration_tests": 0,
                                    "e2e_tests": 0})
        row["tests"] += n
        if cls.endswith("LivePgE2E"):
            row["integration_tests"] += n
        elif cls.endswith("EndToEnd"):
            row["e2e_tests"] += n
    return [rows[k] for k in sorted(rows)]


# --- D-117: state-machine audit ---------------------------------------------------

class StateMachineAudit:
    """Proves a transition matrix is CLOSED (D-117):
    - legal edges are exactly the declared set;
    - terminal states have no outgoing edges;
    - every undeclared (from, to) pair is REFUSED by the predicate.
    """

    def __init__(self, name: str, states: Sequence[str],
                 legal_edges: Set[Tuple[str, str]],
                 terminals: Sequence[str],
                 refuses: Callable[[str, str], bool]):
        self.name = name
        self.states = tuple(states)
        self.legal = set(legal_edges)
        self.terminals = tuple(terminals)
        self._refuses = refuses

    def audit(self) -> Dict:
        illegal: List[Tuple[str, str]] = []
        terminals_with_exits: List[str] = []
        for frm in self.states:
            for to in self.states:
                edge = (frm, to)
                declared = edge in self.legal
                refused = bool(self._refuses(frm, to))
                if declared and refused:
                    illegal.append(edge)     # declared but refused
                elif not declared and not refused:
                    illegal.append(edge)     # UNDECLARED but allowed
            if frm in self.terminals:
                exits = [t for t in self.states
                         if (frm, t) in self.legal]
                if exits:
                    terminals_with_exits.append(frm)
        return {
            "machine": self.name,
            "states": len(self.states),
            "legal_edges": len(self.legal),
            "checked_pairs": len(self.states) ** 2,
            "illegal": illegal,
            "terminals_with_exits": terminals_with_exits,
            "closed": not illegal and not terminals_with_exits,
        }


# --- D-118: deterministic fault injection ------------------------------------------

class FaultScript:
    """A deterministic per-call-index fault schedule: the Nth call
    of the wrapped callable raises the scripted exception; all
    other calls pass through. Reproducible by construction — same
    script, same failures."""

    def __init__(self, outcome: BaseException,
                 indices: Iterable[int]):
        self.outcome = outcome
        self.schedule: Dict[int, bool] = {int(i): True
                                          for i in indices}
        self.calls = 0

    def wrap(self, fn: Callable) -> Callable:
        def inner(*a, **kw):
            idx = self.calls
            self.calls += 1
            if self.schedule.get(idx):
                raise self.outcome
            return fn(*a, **kw)
        return inner


def flaky_dispatch(fail_times: int, success_value: Dict):
    """Transient-then-success dispatcher: fails the first
    `fail_times` calls with a connection-shaped error, then
    succeeds forever (with the attempt count attached). Exercises
    retry ladders deterministically."""
    state = {"calls": 0}

    def dispatch(payload):
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise ConnectionError(
                f"transient outage (call {state['calls']})")
        return dict(success_value, attempts=state["calls"])

    return dispatch


def always_fail(message: str) -> Callable:
    def fn(*a, **kw):
        raise RuntimeError(message)
    return fn


# --- D-119: deterministic mutational fuzzer -----------------------------------------

# Every mutator produces a BOUNDED payload (size/depth capped at
# generation time), so each fuzz case is guaranteed to terminate —
# the bound IS the hang guard, no clock involved.
MUTATORS: Tuple[str, ...] = (
    "noop", "truncate", "oversize", "empty", "control_char",
    "confusable", "deep_nest", "wide_dict", "dup_key_json",
    "type_flip", "bad_utf8", "huge_int", "unicode_bmp",
)

SEED_CORPUS: Tuple[str, ...] = (
    "ord-1", "customer-local-1", "post-1", "ins-1", "tkt-1",
    "actor:admin:1", "L0001", "queue:notifications",
    "2026-09-17T09:00:00+00:00", '{"a": 1}', "plain text",
    "sku-1", "instagram", "0", "-1",
)


def _oversize(value: str) -> str:
    return value * (520 // max(len(value), 1) + 1)


_MUTATION_TABLE: Dict[str, Callable[[str], str]] = {
    "noop": lambda s: s,
    "truncate": lambda s: s[: len(s) // 2],
    "oversize": _oversize,
    "empty": lambda s: "",
    "control_char": lambda s: "a\x00b\x1f" + s,
    "confusable": lambda s: "p\u0430y" + s,
    "deep_nest": lambda s: "[" * 16 + "]" * 16,
    "wide_dict": lambda s: json.dumps({f"k{i}": 1 for i in range(80)}),
    "dup_key_json": lambda s: '{"a": 1, "a": 2}',
    "type_flip": lambda s: json.dumps([s, 1, None, True, {"k": []}]),
    "bad_utf8": lambda s: s + "\udcff",
    "huge_int": lambda s: json.dumps({"n": 10 ** 40}),
    "unicode_bmp": lambda s: s + "\u0ca0\u00ef\u0301",
}


def mutate(seed: str, mutator: str) -> str:
    """One deterministic mutation (never randomness)."""
    fn = _MUTATION_TABLE.get(mutator)
    if fn is None:
        raise ValueError(f"unknown mutator {mutator!r}")
    return fn(seed)


def fuzz_entry(targets: Sequence[Tuple[str, Callable]],
               corpus: Sequence[str] = SEED_CORPUS,
               mutators: Sequence[str] = MUTATORS,
               allowed_exceptions: Sequence[type] = (),
               ) -> Dict:
    """Run the deterministic mutation grid over every target.

    `targets`: [(target_name, callable(value) -> anything)]. Each
    callable must EITHER return normally (verdict "accepted") OR
    raise one of `allowed_exceptions` (verdict "rejected"). Any
    OTHER exception kind is an unhandled fuzz failure — recorded
    with target/seed/mutator/exception and surfaced in the result
    (never swallowed). Verdicts are frozen into the returned grid:
    (target, seed, mutator) → verdict, which the battery re-runs
    and asserts stable.
    """
    grid: Dict[str, str] = {}
    unhandled: List[Dict] = []
    cases = 0
    for tname, fn in targets:
        for seed in corpus:
            for mut in mutators:
                value = mutate(seed, mut)
                cases += 1
                try:
                    fn(value)
                    verdict = "accepted"
                except tuple(allowed_exceptions):
                    verdict = "rejected"
                except Exception as exc:
                    unhandled.append({
                        "target": tname, "seed": seed,
                        "mutator": mut,
                        "exception": type(exc).__name__,
                        "detail": str(exc)[:120]})
                    verdict = "unhandled"
                grid[f"{tname}|{seed}|{mut}"] = verdict
    return {
        "target_count": len(targets),
        "cases": cases,
        "unhandled": unhandled,
        "accepted": sum(1 for v in grid.values() if v == "accepted"),
        "rejected": sum(1 for v in grid.values() if v == "rejected"),
        "grid": grid,
        "clean": not unhandled,
    }
