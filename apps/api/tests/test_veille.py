"""Veille: the feed, the map, À l'antenne, Mots surveillés and Météo des rumeurs."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core import dates, storage
from app.core.db import SessionLocal
from app.core.models import Item, Job, Route, Source
from app.modules import veille
from tests.test_workspaces import _join, _workspace

OBJECTS: dict[str, bytes] = {}


@pytest.fixture
def fake_storage(monkeypatch):
    OBJECTS.clear()

    async def head(key):
        return {"size": len(OBJECTS[key]), "content_type": None} if key in OBJECTS else None

    async def delete(key):
        OBJECTS.pop(key, None)

    monkeypatch.setattr(storage, "configured", lambda: True)
    monkeypatch.setattr(
        storage, "presign_upload", lambda key, mime, expires=600: f"https://s3.test/{key}?put"
    )
    monkeypatch.setattr(
        storage,
        "presign_download",
        lambda key, filename=None, expires=3600: f"https://s3.test/{key}?get",
    )
    monkeypatch.setattr(storage, "head", head)
    monkeypatch.setattr(storage, "delete", delete)


def _db(fn):
    async def run():
        async with SessionLocal() as db:
            out = await fn(db)
            await db.commit()
            return out

    return asyncio.run(run())


def _ago(**kw) -> str:
    return (datetime.now(UTC) - timedelta(**kw)).isoformat()


def _clip(c, ws, text, station="Radio Test", language="fr", **extra):
    r = c.post(
        f"/api/v1/workspaces/{ws}/radio-clips",
        json={
            "station": station,
            "heard_text": text,
            "language": language,
            "recorded_at": extra.pop("recorded_at", _ago(minutes=30)),
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- Mots surveillés
def test_watched_words_count_their_hits_and_are_broadcast(as_user, monkeypatch):
    sent = []

    async def fake_broadcast(ws, event, payload):
        sent.append((event, payload))

    monkeypatch.setattr(veille, "broadcast", fake_broadcast)
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    word = alice.post(base + "/signals", json={"word": "délestage"})
    assert word.status_code == 201
    assert alice.post(base + "/signals", json={"word": "Delestage "}).status_code == 409
    assert bob.get(base + "/signals").status_code == 404

    _clip(alice, ws, "La JIRAMA annonce des DÉLESTAGES de 72 heures à Antananarivo.")
    _clip(alice, ws, "Le pont de Mangasoavina serait fermé jusqu'à lundi.")
    [row] = alice.get(base + "/signals").json()
    assert row["hits"] == 1
    matched = [p for e, p in sent if e == "signal.matched"]
    assert matched[0]["word"] == "délestage" and matched[0]["where"] == "clip"
    assert "72 heures" in matched[0]["excerpt"]
    assert alice.delete(f"{base}/signals/{word.json()['id']}").status_code == 204
    assert alice.get(base + "/signals").json() == []


def test_match_signals_is_a_hook_for_other_roads(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.post(f"/api/v1/workspaces/{ws}/signals", json={"word": "enlèvement"})

    async def run(db):
        return await veille.match_signals(db, uuid.UUID(ws), "Un enlevement signalé par SMS", "sms")

    assert _db(run) == ["enlèvement"]
    assert _db(lambda db: veille.match_signals(db, uuid.UUID(ws), "Rien à voir", "sms")) == []


# --- clips
def test_a_malagasy_clip_keeps_the_veilleurs_sentence(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}/radio-clips"
    short = {"station": "Radio", "heard_text": "", "language": "mg", "recorded_at": _ago(minutes=5)}
    assert alice.post(base, json=short).status_code == 422
    future = {
        **short,
        "heard_text": "Nilaza ny mpihaino fa hisy fahatapahan-jiro.",
        "recorded_at": _ago(minutes=-30),
    }
    assert alice.post(base, json=future).status_code == 422
    clip = _clip(
        alice, ws, "Nilaza ny mpihaino fa hisy fahatapahan-jiro eto Toamasina.", language="mg"
    )
    assert clip["text_from"] == "veilleur"
    assert clip["location"]["region"] == "Atsinanana"  # named in the text


def test_a_veilleur_uploads_a_recording_and_the_french_clip_takes_its_transcript(
    as_user, fake_storage
):
    alice, eve = as_user("alice"), as_user("eve")
    ws = _workspace(alice)
    _join(alice, eve, ws, "veilleur")
    base = f"/api/v1/workspaces/{ws}"
    assert (
        eve.post(
            base + "/files/upload-url",
            json={"filename": "a.webm", "mime": "audio/webm", "size_bytes": 10},
        ).status_code
        == 403
    )
    assert (
        eve.post(
            base + "/radio-clips/upload-url",
            json={"filename": "a.pdf", "mime": "application/pdf", "size_bytes": 10},
        ).status_code
        == 415
    )
    up = eve.post(
        base + "/radio-clips/upload-url",
        json={"filename": "journal.webm", "mime": "audio/webm;codecs=opus", "size_bytes": 4},
    )
    assert up.status_code == 201
    key = up.json()["upload_url"].removeprefix("https://s3.test/").removesuffix("?put")
    OBJECTS[key] = b"OggS"
    clip = eve.post(
        base + "/radio-clips",
        json={
            "station": "RDJ",
            "language": "fr",
            "recorded_at": _ago(minutes=10),
            "file_id": up.json()["file_id"],
        },
    )
    assert clip.status_code == 201, clip.text
    clip = clip.json()
    assert clip["text_from"] == "pending" and clip["source_id"]
    assert (
        _db(lambda db: db.scalar(select(Job.kind).where(Job.status == "queued"))) == "ingest_file"
    )
    transcript = "Au journal de six heures, la JIRAMA annoncerait un délestage de 72 heures."

    async def ready(db):
        await db.execute(
            update(Source)
            .where(Source.id == uuid.UUID(clip["source_id"]))
            .values(status="ready", text=transcript)
        )

    _db(ready)
    got = eve.get(f"{base}/radio-clips/{clip['id']}").json()
    assert got["heard_text"] == transcript and got["text_from"] == "transcript"
    # the veilleur sees their clips only, and none of the desk
    _clip(alice, ws, "Une autre station a entendu autre chose ce matin.")
    assert [c["id"] for c in eve.get(base + "/radio-clips").json()] == [clip["id"]]


def test_antenne_groups_clips_by_claim_and_follow_opens_a_dossier(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    a = _clip(
        alice,
        ws,
        "Un auditeur affirme que la JIRAMA prévoit 72 heures de délestage à Antananarivo.",
        station="RDJ",
        recorded_at=_ago(hours=3),
    )
    b = _clip(
        alice,
        ws,
        "On entend que la JIRAMA prévoit un délestage de 72 heures sur Antananarivo.",
        station="Radio Tana",
        recorded_at=_ago(hours=1),
    )
    other = _clip(
        alice,
        ws,
        "Le pont de Mangasoavina serait fermé jusqu'à lundi prochain.",
        station="Radio Sud",
    )
    rows = alice.get(base + "/antenne").json()
    assert len(rows) == 2
    top = rows[0]
    assert top["status"] == "new" and top["reports"] == 2
    assert top["stations"] == ["Radio Tana", "RDJ"] and top["regions_24h"] == ["Analamanga"]
    assert top["latest"]["id"] == b["id"]

    followed = alice.post(f"{base}/radio-clips/{a['id']}/follow", json={})
    assert followed.status_code == 200, followed.text
    out = followed.json()
    assert (
        out["created"] and out["ref"] == "FAN-0001" and set(out["clip_ids"]) == {a["id"], b["id"]}
    )
    item = alice.get(f"{base}/items/{out['item_id']}").json()
    assert item["data"]["origin"] == "radio" and "énergie" in item["tags"]
    assert item["data"]["location"]["region"] == "Analamanga"
    assert item["data"]["first_seen_at"].startswith(
        dates.parse_moment(a["recorded_at"]).astimezone(dates.EAT).isoformat()[:16]
    )
    stops = alice.get(f"{base}/items/{out['item_id']}/routes").json()
    assert sorted(s["place"] for s in stops) == ["RDJ", "Radio Tana"]
    assert {s["channel"] for s in stops} == {"radio"} and {s["side"] for s in stops} == {"rumour"}

    rows = alice.get(base + "/antenne").json()
    assert [r["status"] for r in rows] == ["new", "followed"]
    assert alice.post(f"{base}/radio-clips/{a['id']}/ignore").status_code == 409
    ignored = alice.post(f"{base}/radio-clips/{other['id']}/ignore").json()
    assert ignored["status"] == "ignored"
    assert len(alice.get(base + "/antenne").json()) == 1


def test_your_report_served_once_the_dossier_is_signed(as_user):
    alice, eve = as_user("alice"), as_user("eve")
    ws = _workspace(alice)
    _join(alice, eve, ws, "veilleur")
    base = f"/api/v1/workspaces/{ws}"
    claim = alice.post(
        base + "/items", json={"title": "Le pont de Mangasoavina serait fermé"}
    ).json()
    clip = _clip(eve, ws, "Le pont de Mangasoavina serait fermé jusqu'à lundi selon un auditeur.")
    assert eve.post(f"{base}/radio-clips/{clip['id']}/follow", json={}).status_code == 403
    out = alice.post(
        f"{base}/radio-clips/{clip['id']}/follow", json={"item_id": claim["id"]}
    ).json()
    assert out["item_id"] == claim["id"] and not out["created"]
    served = eve.get(f"{base}/radio-clips/{clip['id']}").json()["served"]
    assert served["title"] == claim["title"] and served["verdict"] is None

    async def sign(db):
        await db.execute(
            update(Item)
            .where(Item.id == uuid.UUID(claim["id"]))
            .values(status="published", data={"verdict": "false", "ref": "FAN-0001"})
        )
        db.add(
            Route(
                workspace_id=uuid.UUID(ws),
                item_id=uuid.UUID(claim["id"]),
                added_by="alice",
                side="truth",
                channel="radio",
                place="RDJ",
            )
        )

    _db(sign)
    served = eve.get(f"{base}/radio-clips/{clip['id']}").json()["served"]
    assert served["verdict"] == "false" and served["truth_routes"] == 1
    assert as_user("bob").get(f"{base}/radio-clips/{clip['id']}").status_code == 404
    assert eve.get(base + "/antenne").status_code == 403


# --- the feed and the map


# --- Météo des rumeurs


# --- press and radio capture jobs


# --- demo
