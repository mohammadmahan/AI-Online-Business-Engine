"""Phase 20 M3 — security sweep worker (D-113/D-116).

Extended AST boundary sweep + secret-entropy scanner + cross-phase
bounds re-audit, all LOCAL and deterministic:

  - `ast_sweep`: recursive-descent over every Python module checking
    for dynamic exec (eval/exec/compile), shell & process escape
    (subprocess/os.system), unsafe deserialization (pickle/marshal),
    network sockets (requests/urllib/socket/httpx/http.client), and
    nondeterminism (random). Broad `except:` swallowing is reported
    separately as style findings (repo convention allows some).
  - `entropy_scan`: line-oriented high-entropy token scan for secrets
    (D-045 re-verification), with an allowlist for deliberate
    non-secrets (hash fixtures, test hex strings).
  - `bounds_re_audit`: AST re-audit of every prior-phase validator
    module (Phases 9–19) confirming each declares explicit bounds
    (max_length/limit constants) — unbounded-string gaps are defects.

Zero network, zero external providers — pure `ast`/`re` stdlib over
local files (D-116).
"""

import ast
import hashlib
import math
import os
import re
from typing import Callable, Dict, Iterable, List, Optional, Tuple

try:  # canonical-package sibling (canonical.*)
    from canonical.security_contracts import SecurityContractError
except ImportError:  # direct sibling
    from security_contracts import SecurityContractError  # type: ignore

try:
    from canonical import security_contracts as _contracts
except ImportError:  # direct sibling
    import security_contracts as _contracts  # type: ignore


# --- extended AST sweep (D-116) --------------------------------------------------------------

# module-or-attribute names that must NEVER appear in canonical code
_FORBIDDEN_MODULES: Dict[str, str] = {
    "subprocess": "process_escape",
    "socket": "network_socket",
    "requests": "network_library",
    "urllib": "network_library",
    "urllib3": "network_library",
    "httpx": "network_library",
    "http": "network_library",
    "ftplib": "network_library",
    "telnetlib": "network_library",
    "smtplib": "network_library",
    "asyncio": "event_loop_escape",
    "pickle": "unsafe_deserialization",
    "cPickle": "unsafe_deserialization",
    "marshal": "unsafe_deserialization",
    "shelve": "unsafe_deserialization",
    "random": "nondeterminism",
    "numpy": "unvetted_dependency",
    "pandas": "unvetted_dependency",
}

# calls: name / attribute → finding. `compile` is intentionally
# NOT here as a blanket rule: `re.compile()` is a legitimate stdlib
# call used throughout the repo — bare `compile(...)` (Name call)
# is detected separately as dynamic code compilation.
_FORBIDDEN_CALLS: Dict[str, str] = {
    "eval": "dynamic_eval",
    "exec": "dynamic_exec",
    "system": "os_system",
    "popen": "os_popen",
    "getenv": "env_access",
}

# broad except swallowing: `except:` (bare)
_BARE_EXCEPT = "bare_except"


# Process-control kinds allowed in TEST harness code only (the
# established Node/psql tooling since Phase 5): they are reported
# separately for canonical modules they are hard violations.
_TEST_ALLOWED_PROCESS = {"process_escape", "os_system", "os_popen"}


def _is_test_path(path: str) -> bool:
    return os.sep + "tests" + os.sep in path


def ast_sweep(paths: Iterable[str]) -> Dict[str, object]:
    """Sweep Python files for forbidden constructs. Returns a report
    with `findings` (hard violations), `style` (bare excepts), and
    `test_tooling` (subprocess use confined to test harnesses —
    informational, never present in canonical code)."""
    findings: List[Dict[str, str]] = []
    style: List[Dict[str, str]] = []
    test_tooling: List[Dict[str, str]] = []
    files_scanned = 0

    def _walk_file(path: str) -> None:
        nonlocal files_scanned
        with open(path, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source, filename=path)
        files_scanned += 1
        for node in ast.walk(tree):
            # imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in _FORBIDDEN_MODULES:
                        _record({
                            "file": path, "line": str(node.lineno),
                            "kind": _FORBIDDEN_MODULES[root],
                            "detail": f"import {alias.name}",
                        })
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in _FORBIDDEN_MODULES:
                    _record({
                        "file": path, "line": str(node.lineno),
                        "kind": _FORBIDDEN_MODULES[root],
                        "detail": f"from {node.module}",
                    })
            # calls
            elif isinstance(node, ast.Call):
                fn = node.func
                name = None
                if isinstance(fn, ast.Name):
                    name = fn.id
                elif isinstance(fn, ast.Attribute):
                    name = fn.attr
                if name in _FORBIDDEN_CALLS:
                    _record({
                        "file": path, "line": str(node.lineno),
                        "kind": _FORBIDDEN_CALLS[name],
                        "detail": f"call {name}()",
                    })
                elif name == "compile" and isinstance(fn, ast.Name):
                    # bare compile(...) only — re.compile is legitimate
                    _record({
                        "file": path, "line": str(node.lineno),
                        "kind": "dynamic_compile",
                        "detail": "call compile()",
                    })
            # broad except
            elif isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    style.append({
                        "file": path, "line": str(node.lineno),
                        "kind": _BARE_EXCEPT,
                        "detail": "bare `except:` swallows all errors",
                    })

    def _record(finding: Dict[str, str]) -> None:
        if _is_test_path(finding["file"]) and finding["kind"] in _TEST_ALLOWED_PROCESS:
            test_tooling.append(finding)
        else:
            findings.append(finding)

    for p in paths:
        if os.path.isdir(p):
            for dirpath, _dirnames, filenames in os.walk(p):
                for fn in sorted(filenames):
                    if fn.endswith(".py"):
                        _walk_file(os.path.join(dirpath, fn))
        elif p.endswith(".py") and os.path.isfile(p):
            _walk_file(p)

    return {
        "files_scanned": files_scanned,
        "findings": findings,
        "style": style,
        "test_tooling": test_tooling,
        "clean": not findings,
    }


# --- secret-entropy scanner (D-116 / D-045) --------------------------------------------------

_SECRET_TOKEN = re.compile(r"[A-Za-z0-9_/+=-]{20,}")
_ENTROPY_BITS = 3.5          # per-char Shannon entropy threshold
_MIN_TOKEN_LENGTH = 20

# deliberate non-secrets that legitimately trip entropy: hash/attestation
# fixtures in tests, checksum demo vectors, and our own tooling strings.
# `igqvj`/`eaag` are the SYNTHETIC mock platform token prefixes of the
# Phase 9–11 mock adapters (and their redaction tests) — fake by
# construction (D-045), never real credentials.
ALLOWLIST_SUBSTRINGS = (
    "test", "fixture", "example", "sample", "local-", "L000", "L100",
    "deadbeef", "0123456789abcdef", "sha256:", "row_hash", "attest",
    "igqvj", "eaag",
)


def _shannon(token: str) -> float:
    if not token:
        return 0.0
    freq: Dict[str, int] = {}
    for ch in token:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(token)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _secret_signature(token: str) -> bool:
    """Discriminate secret-shaped tokens from ordinary code
    identifiers. A real credential mixes letter case AND carries
    digits; UPPER_SNAKE constants, CamelCase names, and single-case
    identifiers are structure, not secrets."""
    has_lower = any(c.islower() for c in token)
    has_upper = any(c.isupper() for c in token)
    digits = sum(c.isdigit() for c in token)
    return has_lower and has_upper and digits >= 2


def entropy_scan(paths: Iterable[str]) -> Dict[str, object]:
    """Scan text files for high-entropy secret-like tokens (D-045)."""
    flagged: List[Dict[str, str]] = []
    files_scanned = 0
    skip_names = {".DS_Store", "__pycache__"}

    for p in paths:
        base = p if os.path.isfile(p) else None
        walk_root = p if os.path.isdir(p) else os.path.dirname(p)
        candidates: List[str] = []
        if base:
            candidates = [base]
        else:
            for dirpath, dirnames, filenames in os.walk(walk_root):
                dirnames[:] = [d for d in dirnames if d not in skip_names]
                for fn in sorted(filenames):
                    if fn in skip_names:
                        continue
                    if fn.endswith((".py", ".md", ".json", ".sql", ".yml",
                                    ".yaml", ".sh", ".html", ".txt")):
                        candidates.append(os.path.join(dirpath, fn))
        for cpath in candidates:
            try:
                with open(cpath, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except (UnicodeDecodeError, OSError):
                continue  # binary or unreadable → skip
            files_scanned += 1
            for lineno, line in enumerate(lines, start=1):
                low = line.lower()
                if any(a in low for a in ALLOWLIST_SUBSTRINGS):
                    continue
                for m in _SECRET_TOKEN.finditer(line):
                    tok = m.group(0)
                    if len(tok) < _MIN_TOKEN_LENGTH:
                        continue
                    if not _secret_signature(tok):
                        continue
                    if _shannon(tok) >= _ENTROPY_BITS:
                        flagged.append({
                            "file": cpath, "line": str(lineno),
                            "entropy": f"{_shannon(tok):.2f}",
                            "detail": tok[:8] + "…[redacted]",
                        })
    return {
        "files_scanned": files_scanned,
        "flagged": flagged,
        "clean": not flagged,
    }


# --- cross-phase bounds re-audit (D-114) -----------------------------------------------------

# Prior-phase validator modules (Phases 9–19) that must declare explicit
# input bounds. Every entry maps to the control tested in Phase 20 M4.
PRIOR_PHASE_VALIDATORS: Tuple[str, ...] = (
    "instagram_contracts",     # Phase 9
    "telegram_contracts",      # Phase 10
    "orchestration_contracts", # Phase 11
    "oms_contracts",           # Phase 12
    "analytics_contracts",     # Phase 13
    "notification_contracts",  # Phase 14
    "scheduling_contracts",    # Phase 15
    "asset_contracts",         # Phase 16
    "analyst_contracts",       # Phase 17
    "hitl_contracts",          # Phase 18
    "admin_contracts",         # Phase 19
)

# bound-declaring tokens that satisfy the re-audit (any one suffices)
_BOUND_TOKENS = re.compile(
    r"max_length|max_len|MAX_LENGTH|_LIMIT|limit\s*=|max_size|MAX_|"
    r"max_depth|max_width|_MAX\b|_LIMITS\b",
)


# --- channel/vendor isolation (D-131) --------------------------------------------------------

#: channel/vendor identifiers whose literals must stay CONFINED to
#: their declared home modules (D-131): routing is data/targets lists
#: handled by the channel + orchestration registries — other canonical
#: modules must never branch on a vendor name.
_CHANNEL_LITERALS: Tuple[str, ...] = ("instagram", "telegram")

#: declared homes where the literals are PART of the abstraction
#: (adapter/contract/publisher modules, the Phase 11 target registry,
#: the Phase 13 source vocabulary, the QA fuzz corpus).
_CHANNEL_HOME_MARKERS: Tuple[str, ...] = (
    "instagram", "telegram", "orchestration",
    "analytics_contracts", "qa_toolkit",
)


def _is_channel_home(path: str) -> bool:
    fname = os.path.basename(path)
    return ("security_worker" in fname  # this scanner's own table
            or any(marker in fname for marker in _CHANNEL_HOME_MARKERS))


def channel_isolation_scan(paths: Iterable[str]) -> Dict[str, object]:
    """D-131: channel/vendor string literals outside their declared
    home modules are findings. This is the battery-enforced rule that
    keeps adapter identity out of canonical workflow code — a new
    channel is added in its own module + registries, nowhere else.
    (This scanner's own literal table is, by construction, a home.)"""
    findings: List[Dict[str, str]] = []
    files_scanned = 0

    def _scan_file(path: str) -> None:
        nonlocal files_scanned
        fname = os.path.basename(path)
        if _is_channel_home(path):
            files_scanned += 1
            return  # declared home — literals are part of the abstraction
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (SyntaxError, OSError):
            return
        files_scanned += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.strip().lower()
                if low in _CHANNEL_LITERALS:
                    findings.append({
                        "file": path, "line": str(node.lineno),
                        "kind": "channel_literal_outside_home",
                        "detail": repr(node.value),
                    })

    for p in sorted(paths):
        if _is_test_path(p):
            continue  # test fixtures may name channels
        if os.path.isdir(p):
            for dirpath, _dirnames, filenames in os.walk(p):
                for fn in sorted(filenames):
                    if fn.endswith(".py"):
                        _scan_file(os.path.join(dirpath, fn))
        elif p.endswith(".py") and os.path.isfile(p):
            _scan_file(p)
    return {"files_scanned": files_scanned, "findings": findings,
            "clean": not findings}


def bounds_re_audit(canonical_dir: str) -> Dict[str, object]:
    """Confirm every prior-phase validator module declares explicit
    bounds. A module with NO bound token is a finding (D-114 gap)."""
    missing: List[Dict[str, str]] = []
    audited: List[str] = []
    for mod in PRIOR_PHASE_VALIDATORS:
        for candidate in (
            os.path.join(canonical_dir, f"{mod}.py"),
            os.path.join(canonical_dir, mod.replace("_contracts", "") + "_contracts.py"),
        ):
            if os.path.isfile(candidate):
                with open(candidate, "r", encoding="utf-8") as fh:
                    src = fh.read()
                audited.append(os.path.basename(candidate))
                if not _BOUND_TOKENS.search(src):
                    missing.append({
                        "module": os.path.basename(candidate),
                        "detail": "no explicit bound/limit declaration found",
                    })
                break
        else:
            missing.append({
                "module": mod,
                "detail": "module file not found",
            })
    return {
        "modules_audited": audited,
        "missing_bounds": missing,
        "clean": not missing,
    }


# --- worker facade ---------------------------------------------------------------------------

def full_security_sweep(project_root: str,
                        extra_paths: Optional[Iterable[str]] = None
                        ) -> Dict[str, object]:
    """D-116: one-shot sweep — extended AST, entropy, bounds re-audit.
    Used by the M4 suite; every control here maps to tests."""
    canonical_dir = os.path.join(project_root, "local", "canonical")
    targets = [canonical_dir, os.path.join(project_root, "local", "tests")]
    if extra_paths:
        targets.extend(extra_paths)
    ast_report = ast_sweep(targets)
    ent_report = entropy_scan(targets)
    bounds_report = bounds_re_audit(canonical_dir)
    channel_report = channel_isolation_scan(
        [os.path.join(project_root, "local", "canonical")])
    return {
        "ast": ast_report,
        "entropy": ent_report,
        "bounds": bounds_report,
        "channel_isolation": channel_report,
        "clean": bool(ast_report["clean"] and ent_report["clean"]
                      and bounds_report["clean"]
                      and channel_report["clean"]),
    }
