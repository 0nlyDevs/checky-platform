"""The SMS line on a real phone: « SMS Gateway for Android » webhooks in, its send API out (mocked)."""

import asyncio
import hashlib
import hmac
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.modules import sms_gateway
from app.workers import queue
from tests.test_sms import (
    CLAIM,
    PHONE,
    RUMOUR,
    _claim,
    _newsroom,
    secrets,  # noqa: F401 - fixture
)

URL = "/api/v1/public/sms/gateway"
NUMBER = "+261329999991"  # PHONE, as the app writes it


@pytest.fixture(autouse=True)
def gateway(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sms_gateway_url", "http://192.168.1.20:8080/")
    monkeypatch.setattr(s, "sms_gateway_user", "sms")
    monkeypatch.setattr(s, "sms_gateway_password", "phone-pass")
    monkeypatch.setattr(s, "sms_gateway_token", "")
    monkeypatch.setattr(s, "sms_gateway_signing_key", "")
    monkeypatch.setattr(s, "sms_gateway_sim", 0)

    async def no_wait(_):
        return None

    monkeypatch.setattr(sms_gateway, "_sleep", no_wait)
    sms_gateway._seen.clear()


def phone(monkeypatch, *answers):
    """The phone's API: answers in turn (status code or exception), every request kept."""
    sent, left = [], list(answers)

    def reply(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = left.pop(0) if left else 202
        if isinstance(answer, Exception):
            raise answer
        body = json.loads(request.content)
        return httpx.Response(answer, json={"id": body["id"], "state": "Pending"})

    monkeypatch.setattr(sms_gateway, "_transport", httpx.MockTransport(reply))
    return sent


def event(kind="sms:received", text=RUMOUR, sender=PHONE, event_id=None, **payload):
    return {
        "deviceId": "ffffffffceb0b1db0000018e937c815b",
        "event": kind,
        "id": event_id or f"evt-{time.time_ns()}",
        "payload": {
            "messageId": payload.pop("messageId", "abc123"),
            "message": text,
            "sender": sender,
            "recipient": None,
            "simNumber": 1,
            "receivedAt": "2026-11-03T07:42:00.000+03:00",
            **payload,
        },
        "webhookId": "checky",
    }


def post(body, secret="gw-test-secret", headers=None):
    path = f"{URL}?secret={secret}" if secret else URL
    return TestClient(app).post(path, content=json.dumps(body), headers=headers or {})


def run_jobs():
    while asyncio.run(queue.run_once()):
        pass


def outgoing(c, ws):
    return [
        m for m in c.get(f"/api/v1/workspaces/{ws}/sms/messages").json() if m["direction"] == "out"
    ]


def test_a_received_sms_is_answered_through_the_phone(as_user, monkeypatch):
    alice = as_user("alice")
    ws = _newsroom(alice)
    _claim(alice, ws, CLAIM, reason="Le communiqué annonce 4 heures par jour.")
    sent = phone(monkeypatch)
    r = post(event())
    assert r.status_code == 200 and r.json() == {"ok": True, "action": "verdict", "reason": None}
    run_jobs()
    assert len(sent) == 1
    req = sent[0]
    assert str(req.url) == "http://192.168.1.20:8080/messages"
    assert req.headers["Authorization"].startswith("Basic ")
    body = json.loads(req.content)
    assert body["phoneNumbers"] == [NUMBER] and body["withDeliveryReport"] is True
    assert body["textMessage"]["text"].startswith("Faux — 72 heures")
    out = outgoing(alice, ws)
    assert [m["status"] for m in out] == ["sent"] and out[0]["id"] == body["id"]
    # the phone reports delivery, then a late « sent » changes nothing
    msg = body["id"]
    assert post(event("sms:delivered", messageId=msg)).json()["action"] == "delivered"
    post(event("sms:sent", messageId=msg))
    assert outgoing(alice, ws)[0]["status"] == "delivered"
    # the outbox has nothing left for a polling gateway
    box = TestClient(app).get(
        "/api/v1/public/sms/outbox", headers={"X-Gateway-Secret": "gw-test-secret"}
    )
    assert box.json() == []


def test_the_phone_is_retried_then_the_reply_fails_with_its_reason(as_user, monkeypatch):
    alice = as_user("alice")
    ws = _newsroom(alice)
    _claim(alice, ws, CLAIM)
    sent = phone(monkeypatch, httpx.ConnectTimeout("no wifi"), 503, 202)
    post(event())
    run_jobs()
    assert len(sent) == 3 and len({json.loads(r.content)["id"] for r in sent}) == 1
    assert outgoing(alice, ws)[0]["status"] == "sent"
    # a refusal is final at once; a failure report from the phone is kept with its reason
    sent = phone(monkeypatch, 401)
    post(event(text=f"CHECKY {CLAIM}", sender="+261 32 99 999 92"))
    run_jobs()
    assert len(sent) == 1 and outgoing(alice, ws)[0]["status"] == "failed"
    msg = json.loads(sent[0].content)["id"]
    post(event("sms:failed", messageId=msg, reason="RESULT_ERROR_NO_SERVICE"))
    out = next(m for m in outgoing(alice, ws) if m["id"] == msg)
    assert out["status"] == "failed"


def test_bearer_token_and_sim_are_used_when_set(as_user, monkeypatch):
    _newsroom(as_user("alice"))  # a push job belongs to a newsroom, even for an AIDE
    s = get_settings()
    monkeypatch.setattr(s, "sms_gateway_url", "https://api.sms-gate.app/3rdparty/v1")
    monkeypatch.setattr(s, "sms_gateway_token", "jwt-token")
    monkeypatch.setattr(s, "sms_gateway_sim", 2)
    sent = phone(monkeypatch)
    post(event(text="AIDE"))
    run_jobs()
    assert str(sent[0].url) == "https://api.sms-gate.app/3rdparty/v1/messages"
    assert sent[0].headers["Authorization"] == "Bearer jwt-token"
    assert json.loads(sent[0].content)["simNumber"] == 2


def test_webhooks_need_the_secret_or_a_valid_signature(monkeypatch):
    phone(monkeypatch)
    assert post(event(text="AIDE"), secret="nope").status_code == 401
    assert post(event(text="AIDE"), secret=None).status_code == 401
    assert post(event(text="AIDE")).json()["action"] == "help"
    monkeypatch.setattr(get_settings(), "sms_gateway_signing_key", "app-signing-key")
    body = json.dumps(event(text="AIDE")).encode()

    def signed(stamp, key="app-signing-key"):
        sig = hmac.new(key.encode(), body + stamp.encode(), hashlib.sha256).hexdigest()
        return {"X-Signature": sig, "X-Timestamp": stamp, "Content-Type": "application/json"}

    now = str(int(time.time()))
    client = TestClient(app)
    assert client.post(URL, content=body, headers=signed(now, "other-key")).status_code == 401
    assert (
        client.post(URL, content=body, headers=signed(str(int(time.time()) - 900))).status_code
        == 401
    )
    # with a signing key, the URL secret alone is not enough
    assert client.post(f"{URL}?secret=gw-test-secret", content=body).status_code == 401
    r = client.post(URL, content=body, headers=signed(now))
    assert r.status_code == 200 and r.json()["action"] == "help"
    monkeypatch.setattr(get_settings(), "sms_gateway_signing_key", "")
    monkeypatch.setattr(get_settings(), "sms_gateway_secret", "")
    assert post(event(text="AIDE")).status_code == 503


def test_refused_and_repeated_messages_still_answer_2xx(monkeypatch):
    phone(monkeypatch)
    first = event(text="AIDE", event_id="evt-1")
    assert post(first).json()["action"] == "help"
    assert post(first).json() == {"ok": True, "action": "ignored", "reason": "duplicate"}
    for n in range(4):
        assert post(event(text=f"AIDE {n}")).status_code == 200
    r = post(event(text="encore"))
    assert r.status_code == 200 and r.json()["reason"] == "too_many_sms"
    r = post(event(text="Promo forfait", sender="TELMA"))
    assert r.status_code == 200 and r.json()["reason"] == "invalid_number"
    assert post({"event": "system:ping", "payload": {}}).json()["action"] == "ignored"


def test_without_a_gateway_url_the_outbox_hands_the_number_to_a_polling_gateway(monkeypatch):
    monkeypatch.setattr(get_settings(), "sms_gateway_url", "")
    sent = phone(monkeypatch)
    assert post(event(text="AIDE")).status_code == 200
    run_jobs()
    assert sent == []
    box = (
        TestClient(app)
        .get("/api/v1/public/sms/outbox", headers={"X-Gateway-Secret": "gw-test-secret"})
        .json()
    )
    assert [m["to"] for m in box] == [NUMBER]
