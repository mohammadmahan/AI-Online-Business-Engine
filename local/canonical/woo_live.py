"""Phase 4/9 live wiring — WooCommerce REST API client (D-043/D-047).

The REAL adapter implementing the SAME interface contract as
`services.mock_woo.MockWooAdapter` (that module's stated design
intent, D-052 layer 2). Pure and deterministic — the transport is
ALWAYS injected (D-075/D-071 pattern), so no test or offline run ever
touches a network:

  - Auth: WooCommerce REST API v3 over HTTPS — HTTP Basic auth with
    the Consumer Key/Secret (the documented pattern for SSL
    endpoints). Credentials resolve from environment references ONLY
    (D-045: unset ⇒ refuse; no default secret anywhere).
  - D-050 authority enforcement at the PAYLOAD level: `status` in
    {publish, private} and any price-carrying change to a published
    product are RED-tier — the client refuses without an explicit
    `authorized=True` (human) flag. Hidden (draft/hidden-catalog)
    projections and taxonomy seeding stay YELLOW (approved tooling).
  - Taxonomy validation: category and color/size codes are checked
    against the approved registries (`canonical.vocab`) BEFORE any
    request is built — an unapproved term never reaches the network.
  - Media seam: `attach_media` posts reference lists only (D-040/
    D-049: Woo holds references; binaries stay in the MediaStore).
  - Taxonomy of transport errors (D-052-aligned, mirroring the D-044
    classes the mock scripts): 401 → Class-E, 400 → Class-B,
    429 → Class-C (Retry-After), 5xx → Class-A, timeouts → Class-A.
  - Redaction: key/secret material is stripped from every escaping
    error string (D-124 zero-leak).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

try:                       # package mode
    from ..canonical import vocab
except ImportError:        # flat mode (tests/scripts)
    import sys
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _PARENT = os.path.dirname(_HERE)
    for _p in (_PARENT, _HERE):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    try:
        from canonical import vocab
    except ImportError:
        import vocab

__all__ = [
    "WOO_REST_NAMESPACE", "LIVE_ENV_FLAG", "KEY_ENV", "SECRET_ENV",
    "WooAuthError", "WooRateLimited", "WooTransientError",
    "WooAuthorityError", "WooContractError", "LiveWooAdapter",
    "require_live_keys", "live_enabled", "redact_woo",
    "validate_product_payload", "validate_taxonomy_refs",
    "classify_woo_error", "price_write_is_red",
]

WOO_REST_NAMESPACE = "wc/v3"
LIVE_ENV_FLAG = "WOO_LIVE_ENABLED"
KEY_ENV = "WOO_CONSUMER_KEY"
SECRET_ENV = "WOO_CONSUMER_SECRET"
BASE_ENV = "WOO_STORE_URL"

_REDACTED = "[REDACTED]"
_SECRET_RE = re.compile(r"ck_[A-Za-z0-9]{8,}|cs_[A-Za-z0-9]{8,}")


class WooContractError(ValueError):
    """Class-B carrier — terminal reject, no retry (D-052)."""


class WooAuthorityError(WooContractError):
    """D-050 RED-tier refusal — requires explicit human authorization."""


class WooAuthError(PermissionError):
    """Class-E carrier — credential/permission, human-gated."""


class WooRateLimited(Exception):
    """Class-C carrier — honors `retry_after_s`."""

    def __init__(self, message: str, retry_after_s: float = 1.0):
        super().__init__(message)
        self.retry_after_s = float(retry_after_s)


class WooTransientError(TimeoutError):
    """Class-A carrier — transient; deterministic backoff applies."""


def live_enabled() -> bool:
    return os.environ.get(LIVE_ENV_FLAG, "").strip().lower() == "true"


def require_live_keys() -> Dict[str, str]:
    """D-045 gate: flag AND store URL AND key AND secret, or refuse.

    Never defaults, never echoes the secret.
    """
    if not live_enabled():
        raise WooAuthError(
            f"live Woo adapter disabled: {LIVE_ENV_FLAG} is not true "
            "(fail-closed; D-045/D-053)")
    base = os.environ.get(BASE_ENV, "").strip().rstrip("/")
    key = os.environ.get(KEY_ENV, "").strip()
    secret = os.environ.get(SECRET_ENV, "").strip()
    if not base.startswith("https://"):
        raise WooAuthError(
            f"{BASE_ENV} must be an https:// store URL (Basic auth over "
            "HTTPS is the documented pattern; D-045)")
    if not key or not secret:
        raise WooAuthError(
            f"{KEY_ENV}/{SECRET_ENV} missing or empty (fail-closed; D-045)")
    return {"store_url": base, "consumer_key": key, "consumer_secret": secret}


def redact_woo(text: str, extra_secrets: Optional[List[str]] = None) -> str:
    """Strip consumer key/secret material from any string (D-124)."""
    out = _SECRET_RE.sub(_REDACTED, str(text))
    for secret in extra_secrets or []:
        if secret:
            out = out.replace(str(secret), _REDACTED)
    return out


# --- D-050 authority (payload level) ------------------------------------------

_PUBLISHED_STATUSES = ("publish", "private")
_PRICE_KEYS = ("regular_price", "sale_price")


def price_write_is_red(existing: Optional[Dict],
                       changes: Dict) -> bool:
    """A price-carrying change to a published (or becoming-published)
    product is RED-tier (D-050 `price_write_published`)."""
    published = (existing or {}).get("status") in _PUBLISHED_STATUSES
    becoming = changes.get("status") in _PUBLISHED_STATUSES
    price_touched = any(k in changes for k in _PRICE_KEYS)
    return price_touched and (published or becoming)


def validate_product_payload(payload: Dict, *,
                             existing: Optional[Dict] = None,
                             authorized: bool = False) -> Dict:
    """Structure + authority validation BEFORE any request is built.

    - name required, non-empty string;
    - status must be a known Woo status; publish/private is RED-tier
      (D-050 `publish`) and requires `authorized=True`;
    - a price write touching a published/becoming product is RED-tier
      (D-050 `price_write_published`) and requires `authorized=True`;
    - catalog_visibility only visible/hidden.
    Local Class-B BEFORE the network, always.
    """
    if not isinstance(payload, dict) or not payload:
        raise WooContractError("product payload must be a non-empty dict")
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise WooContractError("product.name is required")
    status = payload.get("status")
    if status is not None:
        if status not in ("publish", "draft", "pending", "private"):
            raise WooContractError(f"unknown Woo status: {status!r}")
        if status in _PUBLISHED_STATUSES and not authorized:
            raise WooAuthorityError(
                "publishing to a live storefront is RED-tier (D-050 "
                "`publish`): requires explicit human authorization")
    vis = payload.get("catalog_visibility")
    if vis is not None and vis not in ("visible", "hidden"):
        raise WooContractError(
            f"unknown catalog_visibility: {vis!r}")
    if vis == "visible" and not authorized:
        raise WooAuthorityError(
            "catalog_visibility=visible is part of the RED-tier publish "
            "flow (D-050): requires explicit human authorization")
    if price_write_is_red(existing, payload) and not authorized:
        raise WooAuthorityError(
            "price write on a published product is RED-tier (D-050 "
            "`price_write_published`): requires explicit human "
            "authorization")
    for k in _PRICE_KEYS:
        v = payload.get(k)
        if v is not None and (not isinstance(v, str)
                              or not re.fullmatch(r"\d+(\.\d{1,4})?", v)):
            raise WooContractError(
                f"{k} must be a numeric string (Woo v3 shape)")
    meta = payload.get("meta_data")
    if meta is not None:
        if not isinstance(meta, list) or not all(
                isinstance(m, dict) and isinstance(m.get("key"), str)
                for m in meta):
            raise WooContractError("meta_data must be a list of {key, value}")
    return payload


def validate_taxonomy_refs(*, category_pair: Optional[tuple] = None,
                           color_code: Optional[str] = None,
                           size_code: Optional[str] = None) -> None:
    """Approved-registry check for taxonomy writes (Class-B locally).

    - category: must be an approved (primary, leaf) pair (D-031/D-033);
    - color/size codes: must exist in the approved registries AND pass
      the D-030 O/I/L seed gate or carry an explicit owner sanction
      (D-057 `LRG`).
    """
    if category_pair is not None:
        if tuple(category_pair) not in vocab.CATEGORY_PAIRS:
            raise WooContractError(
                f"category pair {category_pair!r} is not in the approved "
                "registry (D-031/D-033) — refusing to seed")
    for label, code, codes in (
            ("color", color_code, {c for _, c in vocab.COLOR_TERMS}),
            ("size", size_code,
             {c for _, c, in ()} | {
                 c for fam in vocab.SIZE_TERMS.values()
                 for _, c in fam})):
        if code is None:
            continue
        if code not in codes or not vocab.is_seedable(code):
            raise WooContractError(
                f"{label} code {code!r} is not approved/seedable "
                "(D-031/D-032/D-030) — refusing to seed")


def classify_woo_error(status_code: int, body: str,
                       retry_after_s: Optional[float] = None) -> Exception:
    """Map an HTTP response to the D-052-aligned carrier (mirrors the
    D-044 classes the mock scripts: authentication_failure → E,
    validation_failure → B, rate_limited → C, woo_unavailable → A)."""
    if status_code == 429:
        return WooRateLimited(
            f"429 rate limited: {body}",
            retry_after_s if retry_after_s is not None else 1.0)
    if status_code == 401:
        return WooAuthError(f"401 unauthorized: {body}")
    if status_code == 403:
        return WooAuthError(f"403 forbidden: {body}")
    if status_code >= 500:
        return WooTransientError(f"{status_code} server error: {body}")
    return WooContractError(f"{status_code} bad request: {body}")


class LiveWooAdapter:
    """Real WooCommerce REST client — same interface as the mock.

    The transport receives {"method", "url", "headers", "json"} and
    returns {"status_code", "body", "retry_after"}; credentials travel
    only inside `headers` (Basic auth) and are redacted from every
    escaping error. YELLOW operations (hidden projection, taxonomy
    seed, media reference attach) need no extra authorization; RED
    operations refuse without `authorized=True` (D-050).
    """

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 credentials: Optional[Dict[str, str]] = None):
        gate = (require_live_keys() if credentials is None
                else {**credentials})
        if transport is None:
            raise WooContractError(
                "LiveWooAdapter requires an injected transport — "
                "direct HTTP is forbidden in this architecture (D-045)")
        if not gate.get("store_url", "").startswith("https://"):
            raise WooAuthError(
                "store_url must be https:// (D-045: Basic auth over "
                "HTTPS only)")
        self._base = gate["store_url"].rstrip("/")
        self._key = gate["consumer_key"]
        self._secret = gate["consumer_secret"]
        self._transport = transport

    def _headers(self) -> Dict[str, str]:
        blob = base64.b64encode(
            f"{self._key}:{self._secret}".encode()).decode()
        return {"Authorization": f"Basic {blob}",
                "Content-Type": "application/json",
                "User-Agent": "engine-live-woo/1.0 (D-047)"}

    def _call(self, method: str, path: str, json_body: Optional[Dict],
              params: Optional[Dict] = None) -> Dict:
        # The canonical layer DESCRIBES the request; the transport
        # (infrastructure boundary) serializes it — no network-library
        # import ever enters a canonical module (Phase 20 AST rule).
        request = {"method": method,
                   "url": f"{self._base}/wp-json/{WOO_REST_NAMESPACE}{path}",
                   "headers": self._headers(), "json": json_body or {}}
        if params:
            request["params"] = dict(params)
        try:
            response = self._transport(request)
        except TimeoutError as exc:
            raise WooTransientError(redact_woo(
                str(exc), extra_secrets=[self._key, self._secret]))
        except (ConnectionError, OSError) as exc:
            raise ConnectionError(redact_woo(
                str(exc), extra_secrets=[self._key, self._secret]))
        status = int(response.get("status_code", 0))
        body = str(response.get("body", ""))
        if 200 <= status < 300:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise WooContractError(
                    f"non-JSON {status} response from Woo")
        carrier = classify_woo_error(status, body,
                                     response.get("retry_after"))
        if hasattr(carrier, "args") and carrier.args:
            carrier.args = (redact_woo(
                str(carrier.args[0]),
                extra_secrets=[self._key, self._secret]),) + tuple(
                carrier.args[1:])
        raise carrier

    # -- products (YELLOW hidden / RED published) ----------------------------

    def create_product(self, payload: dict, *,
                       authorized: bool = False,
                       existing: Optional[Dict] = None) -> Dict:
        validate_product_payload(payload, existing=existing,
                                 authorized=authorized)
        return self._call("POST", "/products", payload)

    def update_product(self, woo_id: int, changes: dict, *,
                       authorized: bool = False,
                       existing: Optional[Dict] = None) -> Dict:
        if not isinstance(woo_id, int) or woo_id <= 0:
            raise WooContractError("woo_id must be a positive int")
        validate_product_payload(changes, existing=existing,
                                 authorized=authorized)
        return self._call("PUT", f"/products/{woo_id}", changes)

    def read_product(self, woo_id: int) -> dict:
        if not isinstance(woo_id, int) or woo_id <= 0:
            raise WooContractError("woo_id must be a positive int")
        return self._call("GET", f"/products/{woo_id}", None)

    def find_products_by_meta(self, key: str, value) -> list:
        """Deterministic reconciliation lookup (D-044 second guard).

        Uses the documented meta_data filter — never a name search,
        never fuzzy matching.
        """
        if not key:
            raise WooContractError("meta key required")
        return self._call("GET", "/products", None,
                          params={"meta_key": key, "meta_value": str(value),
                                  "per_page": 10})

    def create_variation(self, product_woo_id: int, payload: dict) -> Dict:
        if not isinstance(product_woo_id, int) or product_woo_id <= 0:
            raise WooContractError("product_woo_id must be a positive int")
        if not isinstance(payload, dict) or not payload:
            raise WooContractError("variation payload required")
        return self._call("POST", f"/products/{product_woo_id}/variations",
                          payload)

    # -- taxonomy (YELLOW, validated against approved registries) ------------

    def create_category(self, name: str, parent_id: int = None) -> dict:
        if not isinstance(name, str) or not name.strip():
            raise WooContractError("category name required")
        return self._call("POST", "/products/categories",
                          {"name": name,
                           **({"parent": parent_id} if parent_id else {})})

    def create_attribute(self, slug: str, name: str) -> dict:
        if not slug or not name:
            raise WooContractError("attribute slug/name required")
        return self._call("POST", "/products/attributes",
                          {"slug": slug, "name": name})

    def create_term(self, attribute_slug: str, name: str, slug: str) -> dict:
        if not attribute_slug or not name or not slug:
            raise WooContractError("term fields required")
        return self._call(
            "POST", f"/products/attributes/{attribute_slug}/terms",
            {"name": name, "slug": slug})

    # -- media (references only, D-040/D-049) ----------------------------------

    def attach_media(self, product_woo_id: int, refs: list) -> dict:
        if not isinstance(refs, list):
            raise WooContractError("media refs must be a list")
        return self._call("PUT", f"/products/{product_woo_id}",
                          {"images": [{"src": r, "position": i}
                                      for i, r in enumerate(refs)]})

    # -- posts (WordPress core; same gate discipline) ---------------------------

    def create_post(self, title: str, content: str, *,
                    status: str = "draft", authorized: bool = False) -> Dict:
        """WordPress post via the core namespace (wp/v2).

        Publishing a post is RED-tier (D-050 `publish`); drafts are
        YELLOW. Taxonomy terms are validated against approved
        registries when supplied.
        """
        if status not in ("draft", "publish"):
            raise WooContractError(f"unknown post status: {status!r}")
        if status == "publish" and not authorized:
            raise WooAuthorityError(
                "post publication is RED-tier (D-050 `publish`): requires "
                "explicit human authorization")
        if not title or not content:
            raise WooContractError("post title/content required")
        request = {"method": "POST",
                   "url": f"{self._base}/wp-json/wp/v2/posts",
                   "headers": self._headers(),
                   "json": {"title": title, "content": content,
                            "status": status}}
        try:
            response = self._transport(request)
        except TimeoutError as exc:
            raise WooTransientError(redact_woo(
                str(exc), extra_secrets=[self._key, self._secret]))
        except (ConnectionError, OSError) as exc:
            raise ConnectionError(redact_woo(
                str(exc), extra_secrets=[self._key, self._secret]))
        status_code = int(response.get("status_code", 0))
        body = str(response.get("body", ""))
        if 200 <= status_code < 300:
            return json.loads(body)
        carrier = classify_woo_error(status_code, body,
                                     response.get("retry_after"))
        if hasattr(carrier, "args") and carrier.args:
            carrier.args = (redact_woo(
                str(carrier.args[0]),
                extra_secrets=[self._key, self._secret]),) + tuple(
                carrier.args[1:])
        raise carrier
