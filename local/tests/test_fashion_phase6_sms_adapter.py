"""Fashion Phase 6 §6.2 — Kavenegar SMS channel adapter tests (row 74).

Contract under test: `local/canonical/sms_adapter.py`, the SMS binding of
the existing `ChannelAdapter` seam. Layers:

  M1  contracts: the three §6.2 templates (OTP / order confirmation /
      tracking) validate on the SMS channel, require `phone_ref`, and the
      OTP priority bypasses quiet hours while the order templates stay
      policy-gated.
  M2  mock + selection: the mock is the DEFAULT, sends nothing, records
      every dispatch, and the live adapter is behind a construction gate
      (flag AND credential AND an injected transport).
  M3  Kavenegar routes: verify/lookup for OTP (token never free text),
      sms/send for the Persian tracking body, and EVERY owner-supplied
      value that does not exist yet fails closed (Class-B) instead of
      guessing.
  M4  classification + worker: the provider code table, transport
      failures, API-key redaction, and the real drop-in proof — the same
      worker drains SMS through the mock and through the live adapter
      with nothing but the adapter swapped.

Zero network: the transport is a fake; nothing here reads os.environ.
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
for p in (LOCAL, os.path.join(LOCAL, "canonical"),
          os.path.join(LOCAL, "services"),
          os.path.join(LOCAL, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from canonical import sms_adapter as sms  # noqa: E402
from canonical.notification_contracts import (  # noqa: E402
    CH_IN_APP,
    CH_SMS,
    OUT_DELIVERED,
    OUT_PERMANENT_FAILURE,
    OUT_RATE_LIMITED,
    OUT_TRANSIENT_FAILURE,
    PR_HIGH,
    PR_NORMAL,
    ST_DELIVERED,
    ST_DUPLICATE_BLOCKED,
    ST_FAILED,
    ST_QUEUED,
    NotificationContractError,
    dedup_key,
    policy_decision,
    template_ids,
    validate_notification,
)
from canonical.notification_engine import (  # noqa: E402
    NotificationEngine,
    _JsonLocks,
)
from canonical.notification_worker import (  # noqa: E402
    DeadLetterQueue,
    LocalInAppAdapter,
    NotificationWorker,
)
from services.sync_engine import EventStore  # noqa: E402

PHONE = "09123456789"
API_KEY = "test-key-0000"
_OK_BODY = json.dumps({"return": {"status": 200, "message": "ok"},
                       "entries": [{"messageid": 9001, "status": 1}]})


def _ok():
    return {"status_code": 200, "body": _OK_BODY}


class _FakeTransport:
    """Records every request; scripted responses, zero network."""

    def __init__(self, responses=None, raises=None):
        self.requests = []
        self.responses = list(responses or [])
        self.raises = raises

    def __call__(self, request):
        self.requests.append(request)
        if self.raises is not None:
            raise self.raises
        if self.responses:
            return self.responses.pop(0)
        return _ok()


def _event(key, template_id="checkout.otp.v1", variables=None,
           priority=PR_HIGH, channel=CH_SMS, recipient="cust-1",
           occurred_at="2026-10-23T10:00:00+03:30"):
    return {"recipient": recipient, "channel": channel,
            "priority": priority, "template_id": template_id,
            "variables": ({"phone_ref": PHONE, "otp_code": "123456"}
                          if variables is None else variables),
            "occurred_at": occurred_at, "event_key": key}


def _otp_adapter(transport):
    return sms.KavenegarSmsAdapter(
        transport=transport, api_key=API_KEY, sender="10004346",
        template_map={"checkout.otp.v1": {"name": "otp-login",
                                          "tokens": ["otp_code"]}})


def _shipped(key, **extra):
    """A registry-ADMITTED SMS event — the only kind a producer can
    enqueue today (see `PENDING_REGISTRY_ADMISSION`)."""
    variables = {"phone_ref": PHONE, "order_ref": "ORD-1"}
    variables.update(extra.pop("variables", {}))
    return _event(key, template_id="order.shipped.v1", priority=PR_NORMAL,
                  variables=variables, **extra)


class _TmpPaths:
    def __init__(self):
        fd, self.store = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(self.store)
        self.locks = self.store + ".locks"
        self.dlq = self.store + ".dlq"

    def cleanup(self):
        for p in (self.store, self.locks, self.dlq,
                  self.store + ".tmp", self.locks + ".tmp",
                  self.dlq + ".tmp"):
            if os.path.exists(p):
                os.remove(p)


class _JsonDLQ(DeadLetterQueue):
    """Deterministic JSON DLQ (explicit path; no shared volume)."""

    def __init__(self, path):
        self._path = path

    def admit(self, key, reason, failure_class, attempts, event_ref):
        data = {}
        if os.path.exists(self._path):
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        data[key] = {"reason": reason, "failure_class": failure_class,
                     "attempts": int(attempts), "event_ref": event_ref}
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self._path)

    def items(self):
        if not os.path.exists(self._path):
            return {}
        with open(self._path, encoding="utf-8") as fh:
            return json.load(fh)

    def ping(self):
        return None


class _Harness:
    def __init__(self, adapter, max_attempts=4):
        self.paths = _TmpPaths()
        self.store = EventStore(self.paths.store)
        self.engine = NotificationEngine(
            self.store, locks=_JsonLocks(self.paths.locks))
        self.adapter = adapter
        self.worker = NotificationWorker(
            self.engine, {CH_SMS: adapter, CH_IN_APP: LocalInAppAdapter()},
            dlq=_JsonDLQ(self.paths.dlq), max_attempts=max_attempts)

    def enqueue(self, event):
        return self.engine.enqueue(event)

    def cleanup(self):
        self.paths.cleanup()


# --- M1: contracts -----------------------------------------------------------


class TestM1Contracts(unittest.TestCase):
    def test_shipped_template_is_sms_capable_today(self):
        ids = template_ids()
        self.assertIn("order.shipped.v1", ids)
        ev = _event("reg-shipped", template_id="order.shipped.v1",
                    priority=PR_NORMAL,
                    variables={"phone_ref": PHONE, "order_ref": "ORD-1"})
        self.assertEqual(validate_notification(ev), ev)

    def test_phase6_buyer_templates_are_not_admitted_yet(self):
        # Admitting them changes the Phase-17 count that the Phase-18
        # chain hashes, i.e. the SEALED D-168 digest recorded in
        # DECISIONS.md — an owner re-attestation, so it is deliberately
        # absent and this test pins that state instead of hiding it.
        ids = template_ids()
        for tid in sms.PENDING_REGISTRY_ADMISSION:
            self.assertNotIn(tid, ids)
            with self.assertRaises(NotificationContractError):
                validate_notification(
                    _event("reg-" + tid, template_id=tid, priority=PR_HIGH))

    def test_sms_channel_requires_phone_ref(self):
        ev = _event("k1", template_id="order.shipped.v1",
                    priority=PR_NORMAL, variables={"order_ref": "ORD-1"})
        with self.assertRaises(NotificationContractError):
            validate_notification(ev)

    def test_policy_gates_the_shipped_notification(self):
        night = _event("k3", template_id="order.shipped.v1",
                       priority=PR_NORMAL,
                       variables={"phone_ref": PHONE, "order_ref": "ORD-1"},
                       occurred_at="2026-10-23T23:00:00+03:30")
        self.assertEqual(policy_decision(night, 0)["verdict"], "defer")
        day = dict(night, event_key="k3b",
                   occurred_at="2026-10-23T10:00:00+03:30")
        self.assertEqual(policy_decision(day, 0)["verdict"], "allow")



# --- M2: mock + selection -----------------------------------------------------


class TestM2MockAndSelection(unittest.TestCase):
    def test_no_live_flag_selects_the_mock(self):
        self.assertIsInstance(sms.build_sms_adapter(env={}),
                              sms.MockSmsAdapter)
        # a credential without the flag is not enough to go live
        self.assertIsInstance(
            sms.build_sms_adapter(env={sms.API_KEY_ENV: API_KEY}),
            sms.MockSmsAdapter)

    def test_mock_records_the_dispatch_and_sends_nothing(self):
        adapter = sms.MockSmsAdapter()
        ev = _event("k5")
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_DELIVERED)
        self.assertTrue(result["detail"].startswith("mock_sms:"))
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(adapter.calls[0]["recipient"], PHONE)
        self.assertEqual(adapter.calls[0]["template_id"], "checkout.otp.v1")

    def test_mock_refuses_a_symbolic_recipient(self):
        adapter = sms.MockSmsAdapter()
        ev = _event("k6", variables={"phone_ref": "user-42-sms",
                                     "otp_code": "123456"})
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_PERMANENT_FAILURE)
        self.assertEqual(result["detail"], "invalid_recipient")
        self.assertEqual(adapter.calls, [])

    def test_mock_scripted_failures(self):
        ev = _event("k7")
        self.assertEqual(
            sms.MockSmsAdapter(fail_with="timeout").send(ev, ev)["outcome"],
            OUT_TRANSIENT_FAILURE)
        limited = sms.MockSmsAdapter(fail_with="rate_limited").send(ev, ev)
        self.assertEqual(limited["outcome"], OUT_RATE_LIMITED)
        self.assertEqual(limited["wait_s"], 3)
        self.assertEqual(
            sms.MockSmsAdapter(fail_with="no_credit").send(ev, ev)["outcome"],
            OUT_PERMANENT_FAILURE)

    def test_mock_rejects_an_unknown_control(self):
        with self.assertRaises(NotificationContractError):
            sms.MockSmsAdapter(fail_with="explode")


    def test_live_gate_needs_flag_credential_and_transport(self):
        with self.assertRaises(NotificationContractError):
            sms.build_sms_adapter(env={sms.LIVE_ENV_FLAG: "true"})
        fully = {sms.LIVE_ENV_FLAG: "true", sms.API_KEY_ENV: API_KEY}
        with self.assertRaises(NotificationContractError):
            sms.build_sms_adapter(env=fully)
        adapter = sms.build_sms_adapter(env=fully,
                                        transport=_FakeTransport())
        self.assertIsInstance(adapter, sms.KavenegarSmsAdapter)

    def test_live_adapter_requires_an_injected_transport(self):
        with self.assertRaises(NotificationContractError):
            sms.KavenegarSmsAdapter(api_key=API_KEY)
        with self.assertRaises(NotificationContractError):
            sms.KavenegarSmsAdapter(transport=_FakeTransport(), api_key="")

    def test_template_map_validation_fails_closed(self):
        with self.assertRaises(NotificationContractError):
            sms.parse_template_map("[1, 2]")
        for spec in ({"name": "bad name!", "tokens": ["otp_code"]},
                     {"name": "otp", "tokens": ["a", "b", "c", "d"]},
                     {"name": "otp", "tokens": ["OTP"]},
                     {"name": "otp", "tokens": []}):
            with self.assertRaises(NotificationContractError):
                sms.parse_template_map(
                    json.dumps({"checkout.otp.v1": spec}))
        with self.assertRaises(NotificationContractError):
            sms.KavenegarSmsAdapter(
                transport=_FakeTransport(), api_key=API_KEY,
                template_map={"x": {"name": "otp"}})

    def test_sms_channel_binding_is_the_only_entry_point(self):
        binding = sms.sms_channel_binding(env={})
        self.assertEqual(list(binding), [CH_SMS])
        self.assertIsInstance(binding[CH_SMS], sms.MockSmsAdapter)



# --- M3: Kavenegar routes -----------------------------------------------------


class TestM3KavenegarRoutes(unittest.TestCase):
    def test_otp_uses_verify_lookup_with_the_code_as_a_token(self):
        transport = _FakeTransport()
        adapter = _otp_adapter(transport)
        ev = _event("k8")
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_DELIVERED)
        self.assertEqual(result["detail"], "kavenegar_message_id:9001")
        request = transport.requests[0]
        self.assertEqual(request["method"], "verify/lookup")
        self.assertTrue(request["url"].endswith("/verify/lookup.json"))
        self.assertIn("/v1/" + API_KEY + "/", request["url"])
        self.assertEqual(request["params"],
                         {"receptor": PHONE, "template": "otp-login",
                          "token": "123456"})
        # the code is a provider-side token, never a free-text body
        self.assertNotIn("message", request["params"])

    def test_missing_template_variable_fails_closed_without_a_call(self):
        transport = _FakeTransport()
        adapter = _otp_adapter(transport)
        ev = _event("k9", variables={"phone_ref": PHONE})
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_PERMANENT_FAILURE)
        self.assertEqual(result["detail"],
                         "template_variable_missing:otp_code")
        self.assertEqual(transport.requests, [])

    def test_otp_without_a_registered_template_is_never_free_text(self):
        transport = _FakeTransport()
        adapter = sms.KavenegarSmsAdapter(transport=transport,
                                          api_key=API_KEY,
                                          sender="10004346")
        ev = _event("k10")
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_PERMANENT_FAILURE)
        self.assertEqual(result["detail"],
                         "body_unavailable:checkout.otp.v1")
        self.assertEqual(transport.requests, [])

    def test_tracking_body_is_persian_and_uses_the_sender_line(self):
        transport = _FakeTransport()
        adapter = sms.KavenegarSmsAdapter(transport=transport,
                                          api_key=API_KEY,
                                          sender="10004346")
        ev = _event("k11", template_id="order.tracking.v1",
                    priority=PR_NORMAL,
                    variables={"phone_ref": PHONE,
                               "order_ref": "ORD-1402-1",
                               "tracking_code": "24-1234567"})
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_DELIVERED)
        request = transport.requests[0]
        self.assertEqual(request["method"], "sms/send")
        self.assertEqual(request["params"]["sender"], "10004346")
        self.assertEqual(request["params"]["receptor"], PHONE)
        self.assertIn("ORD-1402-1", request["params"]["message"])
        self.assertIn("24-1234567", request["params"]["message"])
        self.assertIn("ارسال شد", request["params"]["message"])

    def test_shipped_template_carries_the_tracking_code_when_supplied(self):
        transport = _FakeTransport()
        adapter = sms.KavenegarSmsAdapter(transport=transport,
                                          api_key=API_KEY,
                                          sender="10004346")
        ev = _event("k11b", template_id="order.shipped.v1",
                    priority=PR_NORMAL,
                    variables={"phone_ref": PHONE,
                               "order_ref": "ORD-1402-2",
                               "tracking_code": "24-7654321"})
        self.assertEqual(adapter.send(ev, ev)["outcome"], OUT_DELIVERED)
        message = transport.requests[0]["params"]["message"]
        self.assertIn("ORD-1402-2", message)
        self.assertIn("24-7654321", message)

    def test_shipped_template_without_a_code_has_no_dangling_suffix(self):
        transport = _FakeTransport()
        adapter = sms.KavenegarSmsAdapter(transport=transport,
                                          api_key=API_KEY,
                                          sender="10004346")
        ev = _event("k11c", template_id="order.shipped.v1",
                    priority=PR_NORMAL,
                    variables={"phone_ref": PHONE, "order_ref": "ORD-3"})
        self.assertEqual(adapter.send(ev, ev)["outcome"], OUT_DELIVERED)
        message = transport.requests[0]["params"]["message"]
        self.assertIn("ORD-3", message)
        self.assertNotIn("کد رهگیری", message)

    def test_missing_sender_line_fails_closed(self):
        transport = _FakeTransport()
        adapter = sms.KavenegarSmsAdapter(transport=transport,
                                          api_key=API_KEY)
        ev = _event("k12", template_id="order.confirmed.v1",
                    priority=PR_NORMAL,
                    variables={"phone_ref": PHONE, "order_ref": "ORD-1"})
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_PERMANENT_FAILURE)
        self.assertEqual(result["detail"], "sender_line_not_configured")
        self.assertEqual(transport.requests, [])

    def test_invalid_recipient_is_refused_before_the_provider(self):
        transport = _FakeTransport()
        adapter = _otp_adapter(transport)
        ev = _event("k13", variables={"phone_ref": "user-42-sms",
                                      "otp_code": "1"})
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_PERMANENT_FAILURE)
        self.assertEqual(result["detail"], "invalid_recipient")
        self.assertEqual(transport.requests, [])

    def test_iranian_numbers_are_normalised(self):
        self.assertEqual(sms.normalize_recipient("+98 912 345 6789"), PHONE)
        self.assertEqual(sms.normalize_recipient("989123456789"), PHONE)
        self.assertEqual(sms.normalize_recipient("0912-345-6789"), PHONE)
        self.assertIsNone(sms.normalize_recipient("0212345678"))
        self.assertIsNone(sms.normalize_recipient(""))



# --- M4: classification, redaction and the worker ----------------------------


def _body(status, message="provider message", entries=None):
    payload = {"return": {"status": status, "message": message}}
    if entries is not None:
        payload["entries"] = entries
    return json.dumps(payload)


class TestM4Classification(unittest.TestCase):
    def test_provider_code_table(self):
        self.assertEqual(sms.classify_kavenegar_status(200)[0], "ok")
        for code, detail in ((401, "invalid_api_key"),
                             (411, "invalid_sender"),
                             (412, "invalid_recipient"),
                             (414, "message_too_long"),
                             (422, "template_not_registered"),
                             (432, "template_token_invalid"),
                             (451, "no_credit")):
            self.assertEqual(sms.classify_kavenegar_status(code),
                             ("permanent", detail, 0))
        self.assertEqual(sms.classify_kavenegar_status(426),
                         ("rate_limited", "kavenegar_status_426", 60))
        self.assertEqual(sms.classify_kavenegar_status(428)[2], 3600)
        self.assertEqual(sms.classify_kavenegar_status(500)[0], "transient")
        self.assertEqual(sms.classify_kavenegar_status(499)[0], "permanent")
        self.assertEqual(sms.classify_kavenegar_status(599)[0], "transient")

    def test_provider_rejection_never_leaks_the_api_key(self):
        transport = _FakeTransport(responses=[
            {"status_code": 200,
             "body": _body(432, "invalid token " + API_KEY)}])
        adapter = _otp_adapter(transport)
        ev = _event("k14")
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_PERMANENT_FAILURE)
        self.assertIn("432", result["detail"])
        self.assertNotIn(API_KEY, result["detail"])

    def test_rate_limit_outcome_carries_the_wait(self):
        transport = _FakeTransport(responses=[
            {"status_code": 200, "body": _body(426)}])
        adapter = _otp_adapter(transport)
        ev = _event("k15")
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_RATE_LIMITED)
        self.assertEqual(result["wait_s"], 60)

    def test_http_failures_are_classified(self):
        for response, expected in (
            ({"status_code": 503, "body": ""}, OUT_TRANSIENT_FAILURE),
            ({"status_code": 429, "body": ""}, OUT_RATE_LIMITED),
            ({"status_code": 400, "body": "not json"},
             OUT_PERMANENT_FAILURE),
        ):
            adapter = _otp_adapter(_FakeTransport(responses=[response]))
            ev = _event("k16-" + str(response["status_code"]))
            self.assertEqual(adapter.send(ev, ev)["outcome"], expected)

    def test_unusable_200_envelope_is_refused_not_reported_delivered(self):
        transport = _FakeTransport(responses=[
            {"status_code": 200, "body": "not json"}])
        adapter = _otp_adapter(transport)
        ev = _event("k17")
        result = adapter.send(ev, ev)
        self.assertEqual(result["outcome"], OUT_PERMANENT_FAILURE)
        self.assertEqual(result["detail"], "malformed_response")

    def test_transport_exceptions_become_transient_outcomes(self):
        for exc in (TimeoutError("slow"), ConnectionError("down"),
                    OSError("down")):
            adapter = _otp_adapter(_FakeTransport(raises=exc))
            ev = _event("k18-" + type(exc).__name__)
            self.assertEqual(adapter.send(ev, ev)["outcome"],
                             OUT_TRANSIENT_FAILURE)

    def test_redact_strips_the_url_form_and_the_bare_key(self):
        self.assertEqual(
            sms.redact("https://api.kavenegar.com/v1/"
                       "abcdefgh12345678/sms/send.json"),
            "https://api.kavenegar.com/v1/[REDACTED]/sms/send.json")
        self.assertEqual(sms.redact("key=" + API_KEY, [API_KEY]),
                         "key=[REDACTED]")



class TestM4WorkerIntegration(unittest.TestCase):
    """The seam proof: one worker, one adapter slot, nothing else changes."""

    def setUp(self):
        self._harnesses = []

    def tearDown(self):
        for harness in self._harnesses:
            harness.cleanup()

    def _harness(self, adapter, max_attempts=4):
        harness = _Harness(adapter, max_attempts=max_attempts)
        self._harnesses.append(harness)
        return harness

    def test_mock_delivers_through_the_canonical_worker(self):
        adapter = sms.MockSmsAdapter()
        harness = self._harness(adapter)
        ev = _shipped("w1")
        self.assertEqual(harness.enqueue(ev)["status"], ST_QUEUED)
        summary = harness.worker.drain()
        self.assertEqual(summary["delivered"], 1)
        self.assertEqual(
            harness.engine.status_view()[dedup_key(ev)]["status"],
            ST_DELIVERED)
        self.assertEqual(len(adapter.calls), 1)

    def test_duplicate_enqueue_never_reaches_the_provider(self):
        adapter = sms.MockSmsAdapter()
        harness = self._harness(adapter)
        ev = _shipped("w2")
        harness.enqueue(ev)
        self.assertEqual(harness.enqueue(ev)["status"],
                         ST_DUPLICATE_BLOCKED)
        harness.worker.drain()
        self.assertEqual(len(adapter.calls), 1)

    def test_live_adapter_is_a_drop_in_for_the_same_worker(self):
        transport = _FakeTransport()
        harness = self._harness(_otp_adapter(transport))
        ev = _event("w3", template_id="order.shipped.v1",
                    priority=PR_NORMAL,
                    variables={"phone_ref": PHONE, "order_ref": "ORD-9",
                               "tracking_code": "24-9"})
        harness.enqueue(ev)
        summary = harness.worker.drain()
        self.assertEqual(summary["delivered"], 1)
        self.assertEqual(transport.requests[0]["method"], "sms/send")
        self.assertIn("24-9",
                      transport.requests[0]["params"]["message"])
        receipts = [json.loads(raw) for raw in
                    harness.store.succeeded_references("notifications")]
        delivery = [r for r in receipts
                    if r.get("kind") == "delivery_receipt"]
        self.assertEqual(len(delivery), 1)
        # the receipt carries the provider id — never the phone, never the body
        self.assertEqual(delivery[0]["detail"],
                         "kavenegar_message_id:9001")
        receipt_text = json.dumps(delivery[0], ensure_ascii=False)
        self.assertNotIn(PHONE, receipt_text)
        self.assertNotIn("ارسال شد", receipt_text)

    def test_rate_limited_attempt_stays_queued_and_retries(self):
        transport = _FakeTransport(responses=[
            {"status_code": 200, "body": _body(426)}, _ok()])
        harness = self._harness(_otp_adapter(transport))
        ev = _shipped("w4", variables={"tracking_code": "24-4"})
        harness.enqueue(ev)
        first = harness.worker.drain()
        self.assertEqual(first["retried"], 1)
        self.assertEqual(
            harness.engine.status_view()[dedup_key(ev)]["status"],
            ST_QUEUED)
        second = harness.worker.drain()
        self.assertEqual(second["delivered"], 1)
        self.assertEqual(
            harness.engine.status_view()[dedup_key(ev)]["status"],
            ST_DELIVERED)
        self.assertEqual(len(transport.requests), 2)

    def test_permanent_refusal_goes_to_the_dlq_never_silently(self):
        harness = self._harness(sms.KavenegarSmsAdapter(
            transport=_FakeTransport(), api_key=API_KEY))
        ev = _shipped("w5")  # no sender line configured
        harness.enqueue(ev)
        summary = harness.worker.drain()
        self.assertEqual(summary["dlq"], 1)
        self.assertEqual(
            harness.engine.status_view()[dedup_key(ev)]["status"],
            ST_FAILED)
        self.assertEqual(len(harness.worker.dlq.items()), 1)

    def test_exhausted_transient_attempts_reach_the_dlq(self):
        harness = self._harness(
            sms.MockSmsAdapter(fail_with="timeout", fail_times=9),
            max_attempts=2)
        ev = _shipped("w6")
        harness.enqueue(ev)
        for _ in range(2):
            harness.worker.drain()
        self.assertEqual(
            harness.engine.status_view()[dedup_key(ev)]["status"],
            ST_FAILED)
        self.assertEqual(len(harness.worker.dlq.items()), 1)

