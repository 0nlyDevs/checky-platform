"""The SMS line: a basic phone asks « est-ce vérifié ? » and receives the signed verdict.

Two ways in: a phone with a local SIM running « SMS Gateway for Android » posts its
`sms:received` webhooks to `POST /public/sms/gateway` (`sms_gateway.py`, which also pushes the
replies to the phone's send API through the `sms_push` job); any other gateway (or the simulator in
Paramètres) forwards each message to `POST /public/sms/inbound` with the header `X-Gateway-Secret`
and polls `GET /public/sms/outbox` for the replies to send. Keywords: `ABONNE [région]` (the
verdicts of a region), `STOP`, `vérification 145` (the number read on air), `CHECKY <texte>` or
plain text. Plain text is matched against the published verdicts (no AI): a match is answered at
once in the sender's language; otherwise the message joins the claim a public newsroom already
follows, or becomes a `to_check` tip in the best public newsroom (by region, else the first), and
the sender gets the verdict once it is signed (`notify_signed`, called lazily by signing).

Numbers are never stored in clear: rows carry an HMAC and a masked form (`app/core/contact.py`),
and numbers or addresses typed inside a message are masked before it is stored. The one copy
needed to answer later is sealed (Fernet under SEAL_SECRET) on the inbound row, or in
`PublicQuestion.location` for a number left on the site; the push job and the outbox's `to` unseal
it at sending time. The block `+261 34 00 000 xx` is fictional (demo and simulator): what is
written to those numbers is kept as `simulated` and never handed to the gateway.
"""

import hmac
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from app.core import contact, places
from app.core.access import AnyMember, Db
from app.core.activity import broadcast, record
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import (
    Item,
    PublicQuestion,
    RadioPartner,
    Route,
    SmsMessage,
    SmsSubscriber,
    Workspace,
)
from app.modules import public
from app.modules.verify_public import followed, newsroom_for, place_in

log = logging.getLogger("checky.sms")
router = APIRouter(tags=["sms"])

DAILY_LIMIT = 5  # messages per number per day
SMS_MAX = 480  # SmsMessage.text; a reply aims at two SMS at most
FICTIONAL = re.compile(r"^\+2613400000\d\d$")  # « +261 34 00 000 xx », never a real subscriber
# Words only Malagasy uses among the languages people text in (machine-drafted, à relire par un
# locuteur).
MG_WORDS = {
    "ny", "sy", "dia", "fa", "tsy", "ve", "izay", "aho", "ianao", "isika", "izahay", "marina",
    "misy", "tena", "inona", "aiza", "rahampitso", "androany", "vaovao", "manao", "efa", "ireo",
    "mba", "azafady", "misaotra", "koa", "mbola", "angamba", "hoe", "amin", "ary", "ity", "ilay",
    "raha", "satria", "nefa", "kosa", "maro", "hono", "olona", "vola", "jiro", "herinandro",
}  # fmt: skip
VERDICT_WORDS = {
    "fr": {
        "true": "Vrai",
        "misleading": "Trompeur",
        "false": "Faux",
        "unverifiable": "Invérifiable",
    },
    # à relire par un locuteur
    "mg": {
        "true": "Marina",
        "misleading": "Mamitaka",
        "false": "Diso",
        "unverifiable": "Tsy voamarina",
    },
}
REPLIES = {
    "fr": {
        "received": "Reçu. Une rédaction va vérifier. Vous recevrez la réponse par SMS.",
        "followed": "Reçu. Une rédaction vérifie déjà ce message. Vous recevrez la réponse par SMS.",
        "nobody": "Reçu. Aucune rédaction ne reçoit de SMS pour l'instant.",
        "subscribed": "Abonnement enregistré{where}. Vous recevrez les verdicts par SMS. "
        "STOP pour arrêter.",
        "stopped": "Désabonnement enregistré. Vous ne recevrez plus de SMS de Checky.",
        "help": "Envoyez le message reçu pour savoir s'il a été vérifié. ABONNE <région> pour "
        "les alertes, STOP pour arrêter.",
        "where": " pour {region}",
        "unknown_number": "Aucune vérification publiée sous le numéro {n}. Envoyez le message "
        "reçu pour le faire vérifier.",
    },
    # à relire par un locuteur
    "mg": {
        "received": "Voaray. Hojeren'ny mpanao gazety. Handray ny valiny amin'ny SMS ianao.",
        "followed": "Voaray. Efa mijery io hafatra io ny mpanao gazety. Handray ny valiny amin'ny "
        "SMS ianao.",
        "nobody": "Voaray. Mbola tsy misy mpanao gazety mandray SMS amin'izao.",
        "subscribed": "Voasoratra ianao{where}. Handray ny valiny amin'ny SMS ianao. "
        "STOP raha hijanona.",
        "stopped": "Voafafa ny fisoratanao. Tsy handray SMS avy amin'i Checky intsony ianao.",
        "help": "Alefaso ilay hafatra voarainao raha te hahafantatra raha voamarina izy. "
        "ABONNE <faritra> ho an'ny fampitandremana, STOP raha hijanona.",
        "where": " ho an'i {region}",
        "unknown_number": "Tsy misy fanamarinana navoaka amin'ny laharana {n}. Alefaso ilay "
        "hafatra voarainao mba hojerena.",
    },
}
SUBSCRIBE = ("ABONNE", "ABONNER", "MANARAKA")
UNSUBSCRIBE = ("STOP", "AJANONY", "ARRET", "ARRÊT")
ASK = ("CHECKY", "FANILO", "VERIFIER", "VÉRIFIER")
# « vérification 145 », « fanamarinana 145 », « V145 » or the bare number: the one read on air.
BY_NUMBER = re.compile(
    r"^(?:v[ée]rification|fanamarinana|verif|v)?\s*(?:n[°o]\.?\s*)?#?\s*(\d{1,6})\s*[.!?]?$",
    re.IGNORECASE,
)
HELP = ("AIDE", "HELP", "?", "FANAMPIANA")


def language(text: str) -> Literal["fr", "mg"]:
    tokens = re.findall(r"[a-zà-ÿ]+", text.lower())
    hits = sum(1 for t in tokens if t in MG_WORDS)
    return "mg" if hits >= 2 or (hits and len(tokens) <= 4) else "fr"


def short_link(v: public.VerdictOut) -> str:
    """`<site>/v/145` for FAN-0145: short enough for an SMS or to say on air."""
    base = get_settings().public_web_url.rstrip("/")
    m = re.search(r"(\d+)$", v.ref or "")
    return f"{base}/v/{int(m[1])}" if m else f"{base}/verifies/{v.id}"


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


def verdict_line(v: public.VerdictOut, lang: str = "fr") -> str:
    """« Faux — <titre>. <raison courte> (vérification 145) <lien court> », about two SMS."""
    word = VERDICT_WORDS.get(lang, VERDICT_WORDS["fr"])[v.verdict]
    first = re.split(r"(?<=[.!?])\s", (v.reason or "").strip(), maxsplit=1)[0]
    reason = f" {_clip(first, 110)}" if first else ""
    title = _clip(v.title, 90).rstrip(".")
    from app.core.seal import check_label

    label = check_label(v.ref, lang)
    number = f" ({label})" if label else ""
    return f"{word} — {title}.{reason}{number} {short_link(v)}"[:SMS_MAX]


# --- the gateway's door
def gateway(x_gateway_secret: str | None = Header(default=None)) -> None:
    expected = get_settings().sms_gateway_secret
    if not expected:
        raise ApiError(503, "sms_not_configured", "The SMS line is not configured")
    if not x_gateway_secret or not hmac.compare_digest(x_gateway_secret, expected):
        raise ApiError(401, "bad_gateway_secret", "Unknown SMS gateway")


class InboundIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from", min_length=3, max_length=40)
    text: str = Field(default="", max_length=1600)
    received_at: datetime | None = None


class InboundOut(BaseModel):
    action: Literal[
        "verdict", "received", "followed", "subscribed", "stopped", "help", "unknown_number"
    ]
    reply: str
    language: Literal["fr", "mg"]
    phone_hash: str  # the gateway keeps hash → number to deliver later replies
    masked: str
    verdict_id: uuid.UUID | None = None  # the published verdict sent back, if any


class SmsOut(BaseModel):
    id: uuid.UUID
    direction: str
    phone_hash: str
    masked: str
    to: str | None = None
    text: str
    status: str
    created_at: datetime


_fictional: dict[str, set[str]] = {}


def fictional_hashes() -> set[str]:
    """The hashes of the fictional block, so a hash alone tells a demo number from a real one."""
    key = get_settings().seal_secret
    if key not in _fictional:
        _fictional.clear()
        _fictional[key] = {contact.digest("phone", f"+2613400000{n:02d}") for n in range(100)}
    return _fictional[key]


def _queue(db: Db, phone_hash: str, masked: str, text: str, ws_id=None, item_id=None) -> None:
    db.add(
        SmsMessage(
            workspace_id=ws_id,
            item_id=item_id,
            direction="out",
            phone_hash=phone_hash,
            phone_masked=masked,
            text=text[:SMS_MAX],
            status="simulated" if phone_hash in fictional_hashes() else "queued",
        )
    )


async def _rumour_stop(db: Db, ws_id: uuid.UUID, item_id: uuid.UUID, where: dict) -> None:
    """The rumour travels by SMS in that region: one stop on Le trajet (slice « dossier »), at most
    one a day per claim and region."""
    seen = await db.scalar(
        select(func.count(Route.id)).where(
            Route.item_id == item_id,
            Route.side == "rumour",
            Route.channel == "sms",
            Route.at >= datetime.now(UTC) - timedelta(hours=24),
            func.coalesce(Route.location["region"].astext, "") == (where.get("region") or ""),
        )
    )
    if seen:
        return
    try:
        from app.modules.trajet import add_stop

        await add_stop(
            db, ws_id, item_id, side="rumour", channel="sms", place="SMS", location=where or None
        )
    except (ImportError, AttributeError):
        pass
    except Exception:  # another slice's helper: logged, never blocks the reply
        log.exception("sms: rumour stop failed")


async def _signals(db: Db, ws_id: uuid.UUID, text: str) -> None:
    try:
        from app.modules.veille import match_signals

        await match_signals(db, ws_id, text, "sms")
    except (ImportError, AttributeError):
        pass
    except Exception:
        log.exception("sms: watched words failed")


async def _tip(db: Db, ws: Workspace, text: str, at: datetime, where: dict) -> Item:
    item = Item(
        workspace_id=ws.id,
        author_id=public.PUBLIC_AUTHOR,
        type="claim",
        title=_clip(text, 300),
        body=text,
        status="to_check",
        tags=["signalement", "sms"],
        data={
            "ref": await public._next_ref(db, ws.id),
            "first_seen_at": at.isoformat(),
            "origin": "other",
            "source_count": 0,
            "public_tip": True,
            "sms": True,
            **({"location": where} if where else {}),
        },
    )
    db.add(item)
    await db.flush()
    await record(db, ws.id, public.PUBLIC_AUTHOR, "item", item.id, "create")
    return item


async def handle(db: Db, sender: str, text: str, at: datetime | None) -> InboundOut:
    """One SMS in, its reply queued: shared by the gateway route and the simulator."""
    try:
        kind, number = contact.normalise(sender)
    except ValueError as exc:
        raise ApiError(422, "invalid_number", "The sender is not a phone number") from exc
    if kind != "phone":
        raise ApiError(422, "invalid_number", "The sender is not a phone number")
    digest, masked = contact.digest("phone", number), contact.mask("phone", number)
    count = await db.scalar(
        select(func.count(SmsMessage.id)).where(
            SmsMessage.phone_hash == digest,
            SmsMessage.direction == "in",
            SmsMessage.created_at >= datetime.now(UTC) - timedelta(days=1),
        )
    )
    if count >= DAILY_LIMIT and not FICTIONAL.match(number):
        raise ApiError(429, "too_many_sms", "Five messages per number per day")
    at = at or datetime.now(UTC)
    text = contact.redact(re.sub(r"\s+", " ", text or ""))
    inbound = SmsMessage(
        direction="in",
        phone_hash=digest,
        phone_masked=masked,
        text=text[:SMS_MAX],
        status="received",
        sent_at=at,
        # a push gateway needs the number to answer: kept sealed, never for the fictional block
        phone_sealed=None if FICTIONAL.match(number) else contact.seal(number),
    )
    db.add(inbound)
    subscriber = await db.get(SmsSubscriber, digest)
    keyword, _, rest = text.partition(" ")
    keyword = keyword.upper().rstrip(":")
    if keyword in SUBSCRIBE + UNSUBSCRIBE:
        lang = language(rest) if rest.strip() else (subscriber.language if subscriber else "fr")
    else:
        lang = language(text)
    say = REPLIES[lang]
    ws_id = item_id = verdict_id = None
    if keyword in SUBSCRIBE:
        where = place_in(rest)
        region = where.get("region") or (rest.strip().title()[:120] or None)
        if subscriber is None:
            subscriber = SmsSubscriber(phone_hash=digest, phone_masked=masked)
            db.add(subscriber)
        subscriber.region, subscriber.active, subscriber.language = region, True, lang
        action = "subscribed"
        reply = say["subscribed"].format(where=say["where"].format(region=region) if region else "")
    elif keyword in UNSUBSCRIBE:
        if subscriber is not None:
            subscriber.active = False
        action, reply = "stopped", say["stopped"]
    else:
        if keyword in ASK:
            text = rest.strip()
        if len(text) < 3 or keyword in HELP:
            action, reply = "help", say["help"]
        else:
            where = place_in(text) or (
                {"name": subscriber.region, "region": subscriber.region}
                if subscriber and subscriber.region
                else {}
            )
            asked_number = BY_NUMBER.match(text)
            if asked_number:
                by_number = await public.by_number(db, int(asked_number[1]))
                found = [(1.0, by_number)] if by_number else []
            else:
                found = await public.best_published(db, text, k=1)
            if asked_number and not found:
                action, reply = "unknown_number", say["unknown_number"].format(n=asked_number[1])
            elif found:
                verdict = found[0][1]
                item = await db.get(Item, verdict.id)
                action, reply = "verdict", verdict_line(verdict, lang)
                ws_id, item_id, verdict_id = item.workspace_id, item.id, item.id
            elif tracked := await followed(db, text):
                action, reply = "followed", say["followed"]
                ws_id, item_id = tracked[0].workspace_id, tracked[0].id
            elif ws := await newsroom_for(db, where):
                item = await _tip(db, ws, text, at, where)
                action, reply = "received", say["received"]
                ws_id, item_id = ws.id, item.id
            else:  # nobody to read it: the reply says so, and no question is kept
                action, reply = "received", say["nobody"]
            if ws_id:
                db.add(
                    PublicQuestion(
                        workspace_id=ws_id,
                        item_id=item_id,
                        text=text[:2000],
                        channel="sms",
                        location={**where, "lang": lang, "kind": "phone"},
                        contact_hash=digest,
                        contact_masked=masked,
                        notified_at=datetime.now(UTC) if action == "verdict" else None,
                    )
                )
                await _rumour_stop(db, ws_id, item_id, where)
                await _signals(db, ws_id, text)
    inbound.workspace_id, inbound.item_id = ws_id, item_id
    _queue(db, digest, masked, reply, ws_id, item_id)
    await db.commit()
    await _push(db, ws_id)
    if ws_id:
        if action == "received":
            from app.modules.items import _out

            await broadcast(ws_id, "item.created", _out(await db.get(Item, item_id)))
        await broadcast(ws_id, "question.created", {"item_id": str(item_id), "channel": "sms"})
    return InboundOut(
        action=action,
        reply=reply,
        language=lang,
        phone_hash=digest,
        masked=masked,
        verdict_id=verdict_id,
    )


@router.post("/public/sms/inbound", dependencies=[Depends(gateway)])
async def inbound(body: InboundIn, db: Db) -> InboundOut:
    return await handle(db, body.from_, body.text, body.received_at)


def _sms_out(m: SmsMessage, to: str | None = None) -> SmsOut:
    return SmsOut(
        id=m.id,
        direction=m.direction,
        phone_hash=m.phone_hash,
        masked=m.phone_masked,
        to=to,
        text=m.text,
        status=m.status,
        created_at=m.created_at,
    )


async def _reach(db: Db, phone_hash: str) -> str | None:
    """The number itself, unsealed: a sealed outbound radio destination, the last inbound
    SMS, or a number left on the site; None when only the gateway's own book knows it."""
    sealed = (
        await db.scalar(
            select(SmsMessage.phone_sealed)
            .where(
                SmsMessage.phone_hash == phone_hash,
                SmsMessage.direction == "out",
                SmsMessage.phone_sealed.is_not(None),
            )
            .order_by(SmsMessage.created_at.desc())
            .limit(1)
        )
        or await db.scalar(
            select(SmsMessage.phone_sealed)
            .where(
                SmsMessage.phone_hash == phone_hash,
                SmsMessage.direction == "in",
                SmsMessage.phone_sealed.is_not(None),
            )
            .order_by(SmsMessage.created_at.desc())
            .limit(1)
        )
        or await db.scalar(
            select(PublicQuestion.location["reach"].astext)
            .where(
                PublicQuestion.contact_hash == phone_hash, PublicQuestion.location.has_key("reach")
            )
            .limit(1)
        )
    )
    return contact.unseal(sealed)


async def _push(db: Db, ws_id: uuid.UUID | None) -> None:
    """Wake the push sender when a phone gateway is configured; never blocks a reply."""
    try:
        from app.modules.sms_gateway import push_soon

        await push_soon(db, ws_id)
    except Exception:
        log.exception("sms: could not queue the push to the gateway")


@router.get("/public/sms/outbox", dependencies=[Depends(gateway)])
async def outbox(db: Db, limit: int = Query(default=50, ge=1, le=200)) -> list[SmsOut]:
    """The replies to send, oldest first; handing them over marks them sent."""
    rows = (
        await db.scalars(
            select(SmsMessage)
            .where(SmsMessage.direction == "out", SmsMessage.status == "queued")
            .order_by(SmsMessage.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    out, now = [], datetime.now(UTC)
    for m in rows:
        out.append(_sms_out(m, await _reach(db, m.phone_hash)))
        m.status, m.sent_at = "sent", now
    await db.commit()
    return out


# --- the verdict goes back down the road: askers and the subscribers of the rumour's regions
async def notify_signed(db, item: Item) -> int:
    """Queue the signed verdict for everyone who asked about this claim and for the subscribers of
    the regions on its rumour routes. Only a published verdict of a public newsroom leaves; one SMS
    per number per claim, so calling it again (after a release, a re-sign) is safe. E-mail askers
    stay « waiting » (no mail service). Commits; returns the number of SMS queued."""
    d = item.data or {}
    if item.status != "published" or d.get("verdict") not in VERDICT_WORDS["fr"]:
        return 0
    ws = await db.get(Workspace, item.workspace_id)
    if ws is None or not ws.publishes:
        return 0
    verdict = await public._verdict(db, item, ws)
    done = set(
        await db.scalars(
            select(SmsMessage.phone_hash).where(
                SmsMessage.direction == "out",
                SmsMessage.item_id == item.id,
                SmsMessage.text.contains(short_link(verdict)),
            )
        )
    )
    queued, now = 0, datetime.now(UTC)
    asked = await db.scalars(
        select(PublicQuestion).where(
            PublicQuestion.item_id == item.id,
            PublicQuestion.contact_hash.is_not(None),
            PublicQuestion.notified_at.is_(None),
        )
    )
    for q in asked:
        where = q.location or {}
        if where.get("kind") == "email":
            continue
        if q.contact_hash not in done:
            line = verdict_line(verdict, "mg" if where.get("lang") == "mg" else "fr")
            _queue(db, q.contact_hash, q.contact_masked or "", line, ws.id, item.id)
            done.add(q.contact_hash)
            queued += 1
        q.notified_at = now
    regions = {
        places.fold(r)
        for r in await db.scalars(
            select(Route.location["region"].astext).where(
                Route.item_id == item.id, Route.side == "rumour"
            )
        )
        if r
    }
    home = d.get("location") if isinstance(d.get("location"), dict) else {}
    if home.get("region"):
        regions.add(places.fold(home["region"]))
    if regions:
        for sub in await db.scalars(select(SmsSubscriber).where(SmsSubscriber.active.is_(True))):
            if sub.region and places.fold(sub.region) in regions and sub.phone_hash not in done:
                line = verdict_line(verdict, "mg" if sub.language == "mg" else "fr")
                _queue(db, sub.phone_hash, sub.phone_masked, line, ws.id, item.id)
                done.add(sub.phone_hash)
                queued += 1
    await db.commit()
    if queued:
        await _push(db, ws.id)
    return queued


# --- Paramètres: try the line from the desk, and read what it wrote
class SimulateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(default="+261 34 00 000 09", alias="from", max_length=40)
    text: str = Field(min_length=1, max_length=480)


class SimulateOut(BaseModel):
    inbound: InboundOut
    replies: list[SmsOut]


@router.post("/workspaces/{ws}/sms/simulate")
async def simulate(body: SimulateIn, member: AnyMember, db: Db) -> SimulateOut:
    """The phone-shaped form in Paramètres: the gateway's own handling, with the secret kept on the
    server, from the fictional block only, so its replies are shown and never sent."""
    gateway(get_settings().sms_gateway_secret)
    try:
        _, number = contact.normalise(body.from_)
    except ValueError as exc:
        raise ApiError(
            422, "fictional_only", "The simulator writes from +261 34 00 000 xx"
        ) from exc
    if not FICTIONAL.match(number):
        raise ApiError(422, "fictional_only", "The simulator writes from +261 34 00 000 xx")
    started = datetime.now(UTC) - timedelta(seconds=1)
    result = await handle(db, number, body.text, None)
    replies = await db.scalars(
        select(SmsMessage)
        .where(
            SmsMessage.direction == "out",
            SmsMessage.phone_hash == result.phone_hash,
            SmsMessage.created_at >= started,
        )
        .order_by(SmsMessage.created_at)
    )
    return SimulateOut(inbound=result, replies=[_sms_out(m) for m in replies])


@router.get("/workspaces/{ws}/sms/messages")
async def messages(
    member: AnyMember, db: Db, limit: int = Query(default=30, ge=1, le=200)
) -> list[SmsOut]:
    """The newsroom's latest SMS in and out (numbers masked), simulated ones included."""
    rows = await db.scalars(
        select(SmsMessage)
        .where(SmsMessage.workspace_id == member.workspace_id)
        .order_by(SmsMessage.created_at.desc())
        .limit(limit)
    )
    return [_sms_out(m) for m in rows]


# --- demo: fictional subscribers and askers on the pitch rumour, and one partner radio
DEMO_SUBSCRIBERS = (
    ("+261340000001", "Atsimo-Andrefana", "mg"),
    ("+261340000002", "Analamanga", "fr"),
)
DEMO_QUESTIONS = (
    ("+261340000003", "Marina ve fa 72 ora tsy hisy jiro eto Toliara ?", "Toliara", "mg", "sms"),
    (
        "+261340000004",
        "72 heures de délestage, c'est vrai ? On est à Toliara",
        "Toliara",
        "fr",
        "sms",
    ),
    (
        "+261340000005",
        "Délestage de 72 heures selon la JIRAMA, vrai ou faux ?",
        "Toliara",
        "fr",
        "sms",
    ),
    (
        "+261340000006",
        "La JIRAMA coupe vraiment 72 heures à Antananarivo ?",
        "Antananarivo",
        "fr",
        "web",
    ),
)


async def seed_demo(db, workspace_id: uuid.UUID, user_id: str, items: dict[str, Item]) -> None:
    """Idempotent: the demo radio and the demo questions of this newsroom are replaced; the two
    fictional subscribers are updated in place. Without SEAL_SECRET no contact is hashed, so the
    subscribers are skipped and the questions carry no contact (they still count for the desk)."""
    rumour = items.get("FAN-0145")
    await db.execute(
        delete(PublicQuestion).where(
            PublicQuestion.workspace_id == workspace_id,
            PublicQuestion.location["demo"].astext == "true",
        )
    )
    await db.execute(
        delete(RadioPartner).where(
            RadioPartner.workspace_id == workspace_id, RadioPartner.is_demo.is_(True)
        )
    )
    db.add(
        RadioPartner(
            workspace_id=workspace_id,
            name="Radio Fanambarana (démo)",
            frequency="FM 98.4 (démo)",
            location=places.gazetteer("Toamasina") or {},
            languages=["mg", "fr"],
            contact_role="Rédaction en chef (démo)",
            whatsapp="+261 34 00 000 07",
            format_pref="script",
            hours="06:00, 12:00, 18:00",
            token=secrets.token_urlsafe(24),
            is_demo=True,
        )
    )
    protected = contact.configured()
    if protected:
        for number, region, lang in DEMO_SUBSCRIBERS:
            digest = contact.digest("phone", number)
            sub = await db.get(SmsSubscriber, digest)
            if sub is None:
                sub = SmsSubscriber(phone_hash=digest, phone_masked=contact.mask("phone", number))
                db.add(sub)
            sub.region, sub.language, sub.active = region, lang, True
    else:
        log.info("demo: SEAL_SECRET is empty, no demo SMS subscribers")
    for number, text, town, lang, channel in DEMO_QUESTIONS:
        where = places.gazetteer(town) or {}
        db.add(
            PublicQuestion(
                workspace_id=workspace_id,
                item_id=rumour.id if rumour else None,
                text=text,
                channel=channel,
                location={**where, "lang": lang, "kind": "phone", "demo": True},
                contact_hash=contact.digest("phone", number) if protected else None,
                contact_masked=contact.mask("phone", number),
            )
        )
    await db.flush()
