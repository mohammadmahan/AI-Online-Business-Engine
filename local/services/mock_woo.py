"""Mock WooCommerce adapter — D-052 layer 2, D-043/D-047 interface.

Implements the SAME interface contract as the future real adapter so
it is a drop-in replacement (RULES §35). Deterministic, fixture-driven
failure injection covers every D-044 error class. This is NOT real
WooCommerce and never connects to any real instance.
"""

import hashlib
import itertools
import json
import os
import threading
import time
import uuid


class MockWooError(Exception):
    """Woo-style error response."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class MockWooAdapter:
    """In-memory WooCommerce simulation.

    state_path: optional JSON file — persisting state makes duplicate-
    resource simulation realistic across restarts (the D-027/D-046
    second guard runs against real lookups).
    failure_scenario: None or one of the D-044 class names; applied on
    the NEXT write call, then cleared (deterministic single-shot).
    """

    def __init__(self, state_path: str = None,
                 failure_scenario: str = None, latency_s: float = 0.0):
        self.state_path = state_path
        self.failure_scenario = failure_scenario
        self.latency_s = latency_s
        self._lock = threading.Lock()
        self._counter = itertools.count(1000)
        self._products = {}
        self._variations = {}
        self._categories = {}
        self._attributes = {}
        self._terms = {}
        self._media = {}
        self._inventory = {}  # read-only surface (D-041)
        if state_path and os.path.exists(state_path):
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
            self._products = state.get("products", {})
            self._variations = state.get("variations", {})
            self._categories = state.get("categories", {})
            self._attributes = state.get("attributes", {})
            self._terms = state.get("terms", {})
            self._media = state.get("media", {})

    # ------------------------------------------------------------- --
    # Failure injection (D-044 classes, deterministic single-shot)
    # ------------------------------------------------------------- --

    def _maybe_fail(self, op: str):
        if self.latency_s:
            time.sleep(self.latency_s)
        sc = self.failure_scenario
        self.failure_scenario = None  # single-shot, deterministic
        if sc is None:
            return
        if sc == "woo_unavailable":
            raise MockWooError(503, "woocommerce_api_unavailable",
                               "mock: service unavailable")
        if sc == "authentication_failure":
            raise MockWooError(401, "woocommerce_rest_cannot_view",
                               "mock: invalid credentials")
        if sc == "timeout_before_response":
            raise TimeoutError("mock: timeout before response")
        if sc == "ambiguous_timeout":
            # Simulate: write happened, response was lost. The caller
            # must reconcile by read-back (never blind re-create).
            self._commit(op)
            raise TimeoutError("mock: ambiguous timeout (write committed)")
        if sc == "rate_limited":
            raise MockWooError(429, "rate_limited", "mock: slow down")
        if sc == "malformed_response":
            raise json.JSONDecodeError("mock: malformed", "{", 0)
        if sc == "validation_failure":
            raise MockWooError(400, "rest_invalid_param",
                               "mock: invalid payload")
        # All other scenarios are handled per-op (duplicate/partial).

    def _persist(self):
        if self.state_path:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({
                    "products": self._products,
                    "variations": self._variations,
                    "categories": self._categories,
                    "attributes": self._attributes,
                    "terms": self._terms,
                    "media": self._media,
                }, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------- --
    # Products / variations (D-047 CRUD contract)
    # ------------------------------------------------------------- --

    def create_product(self, payload: dict) -> dict:
        self._maybe_fail("create_product")
        with self._lock:
            sku = payload.get("sku")
            if sku:
                hit = self._find_by_sku(sku)
                if hit:
                    # Duplicate resource → human review, never adoption.
                    raise MockWooError(400, "product_invalid_sku",
                                       f"mock: SKU {sku} already exists "
                                       "as product " + str(hit["id"]))
            pid = str(next(self._counter))
            product = {"id": int(pid), "sku": sku,
                       "payload": payload, "status": "draft",
                       "variations": []}
            self._products[pid] = product
            self._persist()
            return dict(product)

    def read_product(self, woo_id: int) -> dict:
        with self._lock:
            p = self._products.get(str(woo_id))
            if not p:
                raise MockWooError(404, "woocommerce_rest_product_invalid_id",
                                   "mock: no such product")
            return dict(p)

    def update_product(self, woo_id: int, changes: dict) -> dict:
        self._maybe_fail("update_product")
        with self._lock:
            p = self._products.get(str(woo_id))
            if not p:
                raise MockWooError(404, "woocommerce_rest_product_invalid_id",
                                   "mock: no such product")
            p["payload"].update(changes)
            p["status"] = changes.get("status", p["status"])
            self._persist()
            return dict(p)

    def create_variation(self, product_woo_id: int, payload: dict) -> dict:
        self._maybe_fail("create_variation")
        with self._lock:
            p = self._products.get(str(product_woo_id))
            if not p:
                raise MockWooError(404, "woocommerce_rest_product_invalid_id",
                                   "mock: no such product")
            sku = payload.get("sku")
            if sku and self._find_by_sku(sku):
                raise MockWooError(400, "product_invalid_sku",
                                   f"mock: SKU {sku} already exists")
            vid = str(next(self._counter))
            variation = {"id": int(vid), "parent_id": p["id"],
                         "payload": payload}
            self._variations[vid] = variation
            p["variations"].append(int(vid))
            self._persist()
            return dict(variation)

    def read_variation(self, variation_woo_id: int) -> dict:
        with self._lock:
            v = self._variations.get(str(variation_woo_id))
            if not v:
                raise MockWooError(404,
                                   "woocommerce_rest_variation_invalid_id",
                                   "mock: no such variation")
            return dict(v)

    def update_variation(self, variation_woo_id: int,
                         changes: dict) -> dict:
        self._maybe_fail("update_variation")
        with self._lock:
            v = self._variations.get(str(variation_woo_id))
            if not v:
                raise MockWooError(404,
                                   "woocommerce_rest_variation_invalid_id",
                                   "mock: no such variation")
            v["payload"].update(changes)
            self._persist()
            return dict(v)

    def _find_by_sku(self, sku: str):
        for p in self._products.values():
            if p.get("sku") == sku:
                return p
        for v in self._variations.values():
            if v["payload"].get("sku") == sku:
                return v
        return None

    # ------------------------------------------------------------- --
    # Categories / attributes / terms (one-time seed surface, D-043)
    # ------------------------------------------------------------- --

    def create_category(self, name: str, parent_id: int = None) -> dict:
        self._maybe_fail("create_category")
        with self._lock:
            for c in self._categories.values():
                if c["name"] == name and c["parent_id"] == parent_id:
                    return c  # create-if-absent by exact (parent, name)
            cid = str(next(self._counter))
            cat = {"id": int(cid), "name": name, "parent_id": parent_id}
            self._categories[cid] = cat
            self._persist()
            return cat

    def read_category(self, woo_id: int) -> dict:
        with self._lock:
            c = self._categories.get(str(woo_id))
            if not c:
                raise MockWooError(404, "invalid_id", "mock: no category")
            return c

    def create_attribute(self, slug: str, name: str) -> dict:
        self._maybe_fail("create_attribute")
        with self._lock:
            for a in self._attributes.values():
                if a["slug"] == slug:
                    return a
            aid = str(next(self._counter))
            attr = {"id": int(aid), "slug": slug, "name": name}
            self._attributes[aid] = attr
            self._persist()
            return attr

    def create_term(self, attribute_slug: str, name: str,
                    slug: str) -> dict:
        self._maybe_fail("create_term")
        with self._lock:
            key = f"{attribute_slug}:{slug}"
            for t in self._terms.values():
                if t["attribute_slug"] == attribute_slug and t["slug"] == slug:
                    return t  # create-if-absent by exact slug
            tid = str(next(self._counter))
            term = {"id": int(tid), "attribute_slug": attribute_slug,
                    "name": name, "slug": slug}
            self._terms[tid] = term
            self._persist()
            return term

    def read_term(self, attribute_slug: str, slug: str) -> dict:
        with self._lock:
            key = f"{attribute_slug}:{slug}"
            t = self._terms.get(key)
            if not t:
                raise MockWooError(404, "invalid_id", "mock: no term")
            return t

    # ------------------------------------------------------------- --
    # Media (references; D-040/D-049: Woo holds references)
    # ------------------------------------------------------------- --

    def attach_media(self, product_woo_id: int, refs: list) -> dict:
        self._maybe_fail("attach_media")
        with self._lock:
            p = self._products.get(str(product_woo_id))
            if not p:
                raise MockWooError(404, "invalid_id", "mock: no product")
            p["payload"]["images"] = [{"ref": r, "position": i}
                                      for i, r in enumerate(refs)]
            self._persist()
            return {"featured": refs[0] if refs else None,
                    "gallery": refs[1:], "count": len(refs)}

    # ------------------------------------------------------------- --
    # Inventory READS only (D-041: PM never writes stock)
    # ------------------------------------------------------------- --

    def read_inventory(self, sku: str) -> dict:
        with self._lock:
            return {"sku": sku,
                    "stock_quantity": self._inventory.get(sku),
                    "note": "Woo-owned transactional data; read-only "
                            "surface (D-041/D-016.I open)"}

    def _inventory_seed(self, sku: str, qty) -> None:
        self._inventory[sku] = qty  # test-fixture helper, not a write API
