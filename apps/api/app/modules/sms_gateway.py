"""The SMS line on a real phone: « SMS Gateway for Android » (sms-gate.app, capcom6, Apache-2.0).

An Android phone with a local SIM runs the app, in local-server mode (its REST API on the
newsroom's Wi-Fi, http://<phone>:8080) or cloud mode (https://api.sms-gate.app/3rdparty/v1, the
phone keeps a connection to their relay). Both speak the same API:

- in: the app posts a webhook per event to `POST /public/sms/gateway`. `sms:received` goes through
  `sms.handle` (the same handling as the simulator and `/public/sms/inbound`); `sms:sent`,
  `sms:delivered` and `sms:failed` update the reply they are about (we give each reply our own id).
  The app signs every webhook (HMAC-SHA256 of the raw body followed by `X-Timestamp`, hex, in
  `X-Signature`, with the key of Settings → Webhooks): with SMS_GATEWAY_SIGNING_KEY set the
  signature is required; otherwise the URL carries `?secret=<SMS_GATEWAY_SECRET>`. A message the
  line refuses (sixth of the day, a sender that is not a number) still gets a 2xx, or the app would
  retry it for two days.
- out: every queued reply wakes the `sms_push` job, which hands it to `POST <SMS_GATEWAY_URL>/messages`
  (basic auth from the app, or a bearer token) with retries on timeouts, 429 and 5xx, and marks it
  sent or failed. Without SMS_GATEWAY_URL nothing is pushed: a polling gateway takes the replies
  from `GET /public/sms/outbox` as before.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Header, Query, Request
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.core import http
from app.core.access import Db
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Job, SmsMessage, Workspace
from app.modules import sms
from app.workers.queue import JobContext, enqueue, handler

log = logging.getLogger("checky.sms_gateway")
router = APIRouter(tags=["sms"])

KIND = "sms_push"
SKEW = 300  # seconds a signed webhook may be late or early
DELAYS = (2.0, 10.0)  # between the three attempts of one SMS
STUCK = timedelta(minutes=5)  # a reply left « sending » by a dead process is taken again
BATCH = 200  # replies per job run
_transport: httpx.AsyncBaseTransport | None = None  # tests swap in an httpx.MockTransport
_sleep = asyncio.sleep
_seen: OrderedDict[str, float] = OrderedDict()  # webhook event ids already handled (app retries)


def configured() -> bool:
    s = get_settings()
    return bool(s.sms_gateway_url and (s.sms_gateway_token or s.sms_gateway_user))


# --- in: the app's webhooks
def _authorised(raw: bytes, signature: str | None, stamp: str | None, secret: str | None) -> None:
    s = get_settings()
    if s.sms_gateway_signing_key:
        try:
            late = abs(time.time() - int(stamp or ""))
        except ValueError:
            late = SKEW + 1
        expected = hmac.new(
            s.sms_gateway_signing_key.encode(), raw + (stamp or "").encode(), hashlib.sha256
        ).hexdigest()
        if late > SKEW or not signature or not hmac.compare_digest(signature.lower(), expected):
            raise ApiError(401, "bad_signature", "Unknown SMS gateway")
        return
    if not s.sms_gateway_secret:
        raise ApiError(503, "sms_not_configured", "The SMS line is not configured")
    if not secret or not hmac.compare_digest(secret, s.sms_gateway_secret):
        raise ApiError(401, "bad_gateway_secret", "Unknown SMS gateway")


def _first_time(key: str) -> bool:
    if not key:
        return True
    if key in _seen:
        return False
    _seen[key] = time.time()
    while len(_seen) > 2000:
        _seen.popitem(last=False)
    return True


def _moment(value: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


class WebhookOut(BaseModel):
    ok: bool = True
    # what the line did with it: an SMS action (verdict, received…), a status update, or ignored
    action: str
    reason: str | None = None


STATUS = {"sms:sent": "sent", "sms:delivered": "delivered", "sms:failed": "failed"}


@router.post("/public/sms/gateway")
async def webhook(
    request: Request,
    db: Db,
    secret: str | None = Query(default=None),
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    x_gateway_secret: str | None = Header(default=None),
) -> WebhookOut:
    raw = await request.body()
    _authorised(raw, x_signature, x_timestamp, secret or x_gateway_secret)
    try:
        event = json.loads(raw or b"{}")
    except ValueError as exc:
        raise ApiError(422, "invalid_webhook", "The webhook body is not JSON") from exc
    if not isinstance(event, dict):
        raise ApiError(422, "invalid_webhook", "The webhook body is not an object")
    kind = str(event.get("event") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if kind == "sms:received":
        if not _first_time(str(event.get("id") or payload.get("messageId") or "")):
            return WebhookOut(action="ignored", reason="duplicate")
        sender = payload.get("sender") or payload.get("phoneNumber") or ""
        try:
            out = await sms.handle(
                db,
                str(sender),
                str(payload.get("message") or ""),
                _moment(payload.get("receivedAt")),
            )
        except ApiError as exc:  # refused for good: a retry would be refused again
            await db.rollback()
            return WebhookOut(action="ignored", reason=exc.code)
        return WebhookOut(action=out.action)
    if kind in STATUS:
        try:
            ours = uuid.UUID(str(payload.get("messageId") or ""))
        except ValueError:
            return WebhookOut(action="ignored", reason="unknown_message")
        msg = await db.get(SmsMessage, ours)
        if msg is None or msg.direction != "out" or msg.status == "simulated":
            return WebhookOut(action="ignored", reason="unknown_message")
        # « delivered » is final; a late « sent » never takes it back
        if not (msg.status == "delivered" and STATUS[kind] == "sent"):
            msg.status = STATUS[kind]
            if kind == "sms:failed":
                msg.error = str(payload.get("reason") or "failed")[:200]
            elif msg.sent_at is None:
                msg.sent_at = datetime.now(UTC)
            await db.commit()
        return WebhookOut(action=STATUS[kind])
    return WebhookOut(action="ignored", reason="event")  # system:ping, mms…


# --- out: the replies pushed to the phone
async def push_soon(db, ws_id: uuid.UUID | None) -> None:
    """Queue one `sms_push` job when a gateway is configured, replies wait and no push is queued.
    A job belongs to a newsroom: the reply's, else the oldest one (a STOP or AIDE has none)."""
    if not configured():
        return
    waiting = await db.scalar(
        select(SmsMessage.id)
        .where(SmsMessage.direction == "out", SmsMessage.status == "queued")
        .limit(1)
    )
    pending = await db.scalar(
        select(Job.id).where(Job.kind == KIND, Job.status == "queued").limit(1)
    )
    if waiting is None or pending is not None:
        return
    ws_id = ws_id or await db.scalar(select(Workspace.id).order_by(Workspace.created_at).limit(1))
    if ws_id is not None:
        await enqueue(db, ws_id, "sms", KIND, {})


def _auth() -> dict[str, Any]:
    s = get_settings()
    if s.sms_gateway_token:
        return {"headers": {"Authorization": f"Bearer {s.sms_gateway_token}"}}
    return {"auth": httpx.BasicAuth(s.sms_gateway_user, s.sms_gateway_password)}


async def send(message_id: uuid.UUID, number: str, text: str) -> tuple[str, str | None]:
    """Hand one SMS to the phone: ("sent", None) or ("failed", why). Timeouts, 429 and 5xx are
    tried three times; our id makes a repeat harmless (the app answers 409 to an id it has)."""
    s = get_settings()
    body: dict[str, Any] = {
        "id": str(message_id),
        "textMessage": {"text": text},
        "phoneNumbers": [number],
        "withDeliveryReport": True,
    }
    if s.sms_gateway_sim:
        body["simNumber"] = s.sms_gateway_sim
    client = http.shared("sms_gateway", _transport, 20.0)
    url = s.sms_gateway_url.rstrip("/") + "/messages"
    why = "unreachable"
    for attempt in range(len(DELAYS) + 1):
        if attempt:
            await _sleep(DELAYS[attempt - 1])
        try:
            r = await client.post(url, json=body, **_auth())
        except httpx.HTTPError as exc:
            why = f"unreachable: {type(exc).__name__}"
            continue
        if r.status_code in (200, 201, 202, 409):
            state = r.json().get("state") if r.status_code != 409 and r.content else None
            return ("failed", "refused by the phone") if state == "Failed" else ("sent", None)
        if r.status_code == 429 or r.status_code >= 500:
            why = f"gateway {r.status_code}"
            continue
        return "failed", f"gateway {r.status_code}: {r.text[:120]}"
    return "failed", why


async def _claim() -> SmsMessage | None:
    async with SessionLocal() as db:
        row = await db.scalar(
            select(SmsMessage)
            .where(
                SmsMessage.direction == "out",
                or_(
                    SmsMessage.status == "queued",
                    (SmsMessage.status == "sending")
                    & (SmsMessage.updated_at < datetime.now(UTC) - STUCK),
                ),
            )
            .order_by(SmsMessage.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        row.status = "sending"
        await db.commit()
        await db.refresh(row)
        return row


@handler(KIND)
async def push(ctx: JobContext) -> dict:
    """Every reply waiting, oldest first, handed to the phone one by one."""
    counts = {"sent": 0, "failed": 0}
    if not configured():
        return counts
    for _ in range(BATCH):
        row = await _claim()
        if row is None:
            break
        async with SessionLocal() as db:
            number = await sms._reach(db, row.phone_hash)
        status, why = await send(row.id, number, row.text) if number else ("failed", "no number")
        async with SessionLocal() as db:
            msg = await db.get(SmsMessage, row.id)
            # a status webhook may have landed meanwhile (delivered): keep the furthest news
            if msg.status == "sending":
                msg.status, msg.error = status, why
                msg.sent_at = datetime.now(UTC) if status == "sent" else msg.sent_at
            await db.commit()
        counts[status] += 1
        if why:
            log.warning("sms push %s: %s", row.id, why)
    return counts
