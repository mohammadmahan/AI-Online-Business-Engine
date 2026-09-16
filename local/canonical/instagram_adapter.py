"""Phase 9 M2 — Instagram Graph API adapter boundary (D-071).

`InstagramAdapter` interface with pluggable transports (the D-066
pattern): zero network in tests. `MockInstagramAdapter` is a
deterministic, high-fidelity local implementation of the two-step
container workflow with scriptable failures. `GraphApiAdapter` is the
live adapter, gated behind INSTAGRAM_LIVE_ENABLED=true AND env keys —
otherwise deterministic Class-B refusal (D-045: no credential exists,
none requested).

Container status codes follow the Graph API semantics:
IN_PROGRESS → FINISHED (ready) | ERROR | EXPIRED.

Token redaction (D-071/D-045): `redact()` strips every access-token
material from a string before it can reach logs, errors, or
observability records.
"""

import json
import os
import time
from typing import Callable, Dict, List, Optional

from canonical.instagram_contracts import InstagramContractError

LIVE_ENV_FLAG = "INSTAGRAM_LIVE_ENABLED"
TOKEN_ENV = "INSTAGRAM_ACCESS_TOKEN"
BUSINESS_ENV = "INSTAGRAM_BUSINESS_ID"

TOKEN_MARKERS = ("access_token=", "graph.facebook.com/", "IGQV", "EAAG")
_REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Strip access-token material from any string (D-071/D-045).

    Applies to logs, error messages, and observability records — a
    token must never survive into any persisted or displayed text.
    """
    out = str(text)
    for marker in TOKEN_MARKERS:
        idx = out.find(marker)
        while idx != -1:
            # cut everything after the marker up to the next separator
            end = idx + len(marker)
            while end < len(out) and out[end] not in ("&", " ", '"', "'",
                                                      "\n", ")", "]"):
                end += 1
            out = out[:idx] + marker.rstrip("=/") + _REDACTED + out[end:]
            idx = out.find(marker, end)
    return out


def live_enabled() -> bool:
    return os.environ.get(LIVE_ENV_FLAG, "").strip().lower() == "true"


def require_live_keys() -> Dict[str, str]:
    """D-071 construction gate: flag AND keys present, else Class-B."""
    if not live_enabled():
        raise InstagramContractError(
            f"live Instagram adapter disabled: {LIVE_ENV_FLAG}!=true "
            "(D-071 owner gate)")
    token = os.environ.get(TOKEN_ENV, "").strip()
    business = os.environ.get(BUSINESS_ENV, "").strip()
    if not token or not business:
        raise InstagramContractError(
            f"live Instagram adapter disabled: {TOKEN_ENV}/"
            f"{BUSINESS_ENV} missing (D-071 owner gate; D-045 — no "
            "credential exists)")
    return {"access_token": token, "business_id": business}


class InstagramAdapter:
    """Provider-neutral boundary (RULES §35): three operations, one
    per D-069 workflow step."""

    name = "instagram"

    def create_media_container(self, media_ref: str, caption: str,
                               aspect_ratio: str) -> Dict:
        raise NotImplementedError

    def container_status(self, container_id: str) -> Dict:
        raise NotImplementedError

    def publish_container(self, container_id: str) -> Dict:
        raise NotImplementedError


class MockInstagramAdapter(InstagramAdapter):
    """Deterministic local adapter (D-053): containers become FINISHED
    after `polls_until_ready` status calls; failures are scriptable."""

    name = "mock"

    def __init__(self, polls_until_ready: int = 1,
                 fail_with: Optional[str] = None,
                 status_after_error: str = "ERROR"):
        self.polls_until_ready = polls_until_ready
        self.fail_with = fail_with  # None | create_error | timeout | rate_limit | publish_error
        self.status_after_error = status_after_error
        self._containers: Dict[str, Dict] = {}
        self._poll_counts: Dict[str, int] = {}
        self.calls: List[str] = []
        self._next = 1

    def create_media_container(self, media_ref: str, caption: str,
                               aspect_ratio: str) -> Dict:
        self.calls.append("create")
        if self.fail_with == "create_error":
            raise InstagramContractError(
                redact("container create failed: access_token=SECRET "
                       "invalid media"))
        if self.fail_with == "timeout":
            raise TimeoutError(redact(
                "graph request timed out access_token=SECRET"))
        cid = f"MOCK_CONTAINER_{self._next}"
        self._next += 1
        self._containers[cid] = {"status_code": "IN_PROGRESS",
                                 "media_ref": media_ref,
                                 "aspect_ratio": aspect_ratio}
        self._poll_counts[cid] = 0
        return {"container_id": cid, "status_code": "IN_PROGRESS"}

    def container_status(self, container_id: str) -> Dict:
        self.calls.append("status")
        if self.fail_with == "rate_limit":
            raise _RateLimited(
                redact("429 rate limit access_token=SECRET"))
        rec = self._containers.get(container_id)
        if rec is None:
            raise InstagramContractError(
                f"unknown container {container_id}")
        self._poll_counts[container_id] += 1
        if rec["status_code"] == "IN_PROGRESS" \
                and self._poll_counts[container_id] \
                >= max(1, self.polls_until_ready):
            rec["status_code"] = "FINISHED"
        return dict(rec, container_id=container_id)

    def publish_container(self, container_id: str) -> Dict:
        self.calls.append("publish")
        if self.fail_with == "publish_error":
            raise InstagramContractError(
                redact("publish failed: media ERROR access_token=SECRET"))
        rec = self._containers.get(container_id)
        if rec is None or rec["status_code"] != "FINISHED":
            raise InstagramContractError(
                f"container {container_id} not FINISHED — refusing to "
                "publish (D-069 workflow)")
        return {"publication_id": f"MOCK_PUB_{self._next}",
                "container_id": container_id}


class _RateLimited(Exception):
    """Scriptable 429 (Class-C) carrier: rate limited → cooldown."""

    failure_class = "C"

    def __init__(self, message: str, cooldown_s: float = 60.0):
        super().__init__(message)
        self.cooldown_s = cooldown_s


class GraphApiAdapter(InstagramAdapter):
    """Live Meta Graph API adapter (D-071). Transport-injectable; the
    default transport is owner-gated production wiring."""

    name = "graph_api"

    def __init__(self, transport: Optional[Callable[[Dict], Dict]] = None,
                 api_key: Optional[str] = None):
        creds = require_live_keys()
        self._token = api_key if api_key is not None \
            else creds["access_token"]
        self.business_id = creds["business_id"]
        self._transport = transport or self._http_transport

    def _http_transport(self, request_dict: Dict) -> Dict:
        raise InstagramContractError(
            redact("GraphApiAdapter requires an injected transport in "
                   "the local environment; the default HTTP transport "
                   "is owner-gated production wiring (D-053/D-071)"))

    def create_media_container(self, media_ref: str, caption: str,
                               aspect_ratio: str) -> Dict:
        return self._dispatch("POST", f"{self.business_id}/media", {
            "media_ref": media_ref, "caption": caption,
            "aspect_ratio": aspect_ratio})

    def container_status(self, container_id: str) -> Dict:
        return self._dispatch("GET", container_id, {})

    def publish_container(self, container_id: str) -> Dict:
        return self._dispatch("POST", f"{self.business_id}/media_publish",
                              {"container_id": container_id})

    def _dispatch(self, method: str, path: str, payload: Dict) -> Dict:
        try:
            body = self._transport({
                "method": method, "path": path, "payload": payload,
                "access_token": self._token})
        except TimeoutError as exc:
            raise TimeoutError(redact(str(exc))) from exc
        except ConnectionError as exc:
            raise ConnectionError(redact(str(exc))) from exc
        except OSError as exc:
            raise OSError(redact(str(exc))) from exc
        err = body.get("error")
        if err:
            raise InstagramContractError(
                redact(f"graph api error: {json.dumps(err)[:300]}"))
        return body


# --- container status poller (D-069 step 2) -------------------------------------

class ContainerNotReady(Exception):
    """Poll budget exhausted before FINISHED (Class-A — retryable)."""

    failure_class = "A"


def poll_until_ready(adapter: InstagramAdapter, container_id: str,
                     max_polls: int = 10,
                     sleep_fn: Optional[Callable[[float], None]] = None,
                     backoff_s: float = 0.0) -> Dict:
    """Poll CONTAINER_STATUS until FINISHED (D-069).

    Bounded: after `max_polls` polls without FINISHED, raises
    ContainerNotReady (Class-A — retryable, never an infinite loop).
    ERROR/EXPIRED map to a terminal Class-B contract error. sleep_fn is
    injectable so tests never actually wait.
    """
    for _ in range(max_polls):
        status = adapter.container_status(container_id)
        code = status.get("status_code")
        if code == "FINISHED":
            return status
        if code in ("ERROR", "EXPIRED"):
            raise InstagramContractError(
                redact(f"container {container_id} reached {code} — "
                       "terminal (D-069)"))
        if sleep_fn is not None and backoff_s:
            sleep_fn(backoff_s)
    raise ContainerNotReady(
        redact(f"container {container_id} not FINISHED after "
               f"{max_polls} polls"))
