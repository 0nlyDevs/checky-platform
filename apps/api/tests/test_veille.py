"""Veille: the feed, the map, À l'antenne, Mots surveillés and Météo des rumeurs."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update

from app.core import dates, storage
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import Item, Job, PublicQuestion, RadioClip, Route, Season, Signal, Source
from app.modules import veille
from app.workers import queue, radio_capture, veille_poll
from tests.test_public import _claim, _newsroom
from tests.test_workspaces import _join, _workspace

OBJECTS: dict[str, bytes] = {}


@pytest.fixture(autouse=True)
def _fresh():
    veille._POLLED.clear()
    yield
    veille_poll._transport = None


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


def test_a_journalist_uploads_a_recording_and_the_french_clip_takes_its_transcript(
    as_user, fake_storage
):
    alice, eve = as_user("alice"), as_user("eve")
    ws = _workspace(alice)
    _join(alice, eve, ws)
    base = f"/api/v1/workspaces/{ws}"
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
    # every journalist of the newsroom sees every clip
    other = _clip(alice, ws, "Une autre station a entendu autre chose ce matin.")
    assert {c["id"] for c in eve.get(base + "/radio-clips").json()} == {clip["id"], other["id"]}


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
    _join(alice, eve, ws)
    base = f"/api/v1/workspaces/{ws}"
    claim = alice.post(
        base + "/items", json={"title": "Le pont de Mangasoavina serait fermé"}
    ).json()
    clip = _clip(eve, ws, "Le pont de Mangasoavina serait fermé jusqu'à lundi selon un auditeur.")
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
    assert eve.get(base + "/antenne").status_code == 200


# --- the feed and the map
def test_the_feed_merges_tips_sms_clips_and_press_and_says_what_was_checked(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    other, _ = _newsroom(bob)
    _claim(bob, other, "Le pont de Mangasoavina est fermé jusqu'à lundi", verdict="misleading")
    ws, slug = _newsroom(alice)
    base = f"/api/v1/workspaces/{ws}"
    tip = alice.post(
        "/api/v1/public/tips",
        json={"newsroom": slug, "text": "On dit que l'eau est coupée à Toamasina toute la semaine"},
    )
    assert tip.status_code == 201
    _clip(alice, ws, "Un auditeur affirme que le pont de Mangasoavina est fermé jusqu'à lundi.")

    async def roads(db):
        db.add(
            PublicQuestion(
                workspace_id=uuid.UUID(ws),
                text="Est-ce vrai que le bac est reporté à Fianarantsoa ?",
                channel="sms",
                contact_masked="+261 34 •• ••• 12",
            )
        )
        db.add(
            Item(
                workspace_id=uuid.UUID(ws),
                author_id="press",
                type="press",
                title="Délestage : la JIRAMA publie son programme à Antananarivo",
                body="",
                tags=[],
                data={"link": "https://journal.test/a", "outlet": "Journal test"},
            )
        )

    _db(roads)
    feed = alice.get(base + "/veille").json()
    kinds = sorted(e["kind"] for e in feed["entries"])
    assert kinds == ["clip", "press", "sms", "tip"]
    assert feed["counts"] == {"clip": 1, "press": 1, "sms": 1, "tip": 1}
    clip = next(e for e in feed["entries"] if e["kind"] == "clip")
    assert (
        clip["already_checked"]["verdict"] == "misleading" and not clip["already_checked"]["mine"]
    )
    sms = next(e for e in feed["entries"] if e["kind"] == "sms")
    assert sms["place"]["region"] == "Haute Matsiatra" and sms["beats"] == ["éducation"]
    assert sms["already_checked"] is None
    press = next(e for e in feed["entries"] if e["kind"] == "press")
    assert press["station"] == "Journal test" and press["beats"] == ["énergie"]
    assert [e["kind"] for e in alice.get(base + "/veille?kind=sms").json()["entries"]] == ["sms"]
    only = alice.get(base + "/veille?region=Atsinanana").json()["entries"]
    assert [e["kind"] for e in only] == ["tip"]
    assert [e["kind"] for e in alice.get(base + "/veille?beat=énergie").json()["entries"]] == [
        "press"
    ]
    assert bob.get(base + "/veille").status_code == 404
    eve = as_user("eve")
    _join(alice, eve, ws)
    assert eve.get(base + "/veille").status_code == 200


def test_the_map_counts_what_circulates_per_region(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    alice.post(
        base + "/items",
        json={"title": "Délestage à Toamasina", "data": {"risk": {"level": "high"}}},
    )
    alice.post(base + "/items", json={"title": "Coupure d'eau annoncée à Tamatave"})
    alice.post(base + "/items", json={"title": "Une rumeur sans lieu"})
    _clip(alice, ws, "Un auditeur parle d'un délestage à Mahajanga ce soir.", station="Radio Boeny")
    _claim(alice, ws, "Vieille rumeur republiée", first_seen_at=_ago(days=400))
    out = alice.get(base + "/veille/map").json()
    by = {r["region"]: r for r in out["regions"]}
    assert by["Atsinanana"]["last_24h"] == 2 and by["Atsinanana"]["high_risk"] == 1
    assert by["Atsinanana"]["lat"] == pytest.approx(-18.15)
    assert by["Boeny"]["kinds"] == {"clip": 1}
    assert out["unplaced"] == 1 and out["total"] == 4
    assert out["country"] == out["home"] == "Madagascar"


def test_the_map_shows_one_country_or_the_world(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    alice.post(base + "/items", json={"title": "Délestage à Toamasina"})
    dakar = {"name": "Dakar", "country": "Sénégal", "region": "Dakar", "lat": 14.7, "lng": -17.4}
    alice.post(base + "/items", json={"title": "Rumeur à Dakar", "data": {"location": dakar}})
    home = alice.get(base + "/veille/map").json()
    assert [r["region"] for r in home["regions"]] == ["Atsinanana"]
    assert home["countries"] == [
        {"country": "Madagascar", "last_7d": 1},
        {"country": "Sénégal", "last_7d": 1},
    ]
    there = alice.get(base + "/veille/map", params={"country": "sénégal"}).json()
    assert [(r["region"], r["lat"]) for r in there["regions"]] == [("Dakar", 14.7)]
    world = alice.get(base + "/veille/map", params={"country": "monde"}).json()
    assert world["country"] == "monde" and len(world["regions"]) == 2


# --- Météo des rumeurs
def test_meteo_seeds_the_seasons_and_brings_back_last_years_verdicts(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    today = dates.today()
    try:
        last_year = today.replace(year=today.year - 1)
    except ValueError:
        last_year = today.replace(year=today.year - 1, day=28)
    seen = datetime(last_year.year, last_year.month, last_year.day, 9, tzinfo=dates.EAT)
    _claim(
        alice,
        ws,
        "Les sujets du bac auraient fuité",
        first_seen_at=(seen + timedelta(days=4)).isoformat(),
    )
    _claim(
        alice, ws, "Trop vieux pour revenir", first_seen_at=(seen - timedelta(days=60)).isoformat()
    )
    out = alice.get(f"/api/v1/workspaces/{ws}/meteo").json()
    assert out["today"] == today.isoformat()
    assert [r["title"] for r in out["returning"]] == ["Les sujets du bac auraient fuité"]
    assert out["returning"][0]["mine"] and out["returning"][0]["year"] == seen.year
    count = _db(lambda db: db.scalar(select(func.count()).select_from(Season)))
    assert count == len(veille.seasons.MG_SEASONS)
    in_effect = {s["name"] for s in out["seasons"]}
    expected = {
        n
        for n, _, a, b, _, _ in veille.seasons.MG_SEASONS
        if veille.seasons.in_months(a, b, today.month)
    }
    assert in_effect <= expected


# --- press and radio capture jobs
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Journal test</title>
<item><title>D\xc3\xa9lestage : la centrale de Toamasina en panne</title>
<link>https://journal.test/delestage</link><description>&lt;p&gt;La JIRAMA annonce des coupures.&lt;/p&gt;</description>
<pubDate>Mon, 02 Nov 2026 05:00:00 GMT</pubDate></item>
<item><title>Le festival de musique report\xc3\xa9</title><link>https://journal.test/festival</link></item>
<item><title>Sans lien</title></item>
</channel></rss>"""


def test_the_press_reader_stores_new_articles_once(as_user, monkeypatch):
    monkeypatch.setattr(
        get_settings(), "press_feeds", "Journal test|https://journal.test/rss, ftp://nope"
    )
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=RSS, headers={"content-type": "application/rss+xml"})

    veille_poll._transport = httpx.MockTransport(handler)
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    alice.post(base + "/signals", json={"word": "délestage"})
    assert alice.post(base + "/veille/refresh").json() == {"queued": ["veille_poll"]}
    assert asyncio.run(queue.run_once())
    alice.post(base + "/veille/refresh")
    assert asyncio.run(queue.run_once())
    assert calls == ["https://journal.test/rss"] * 2
    feed = alice.get(base + "/veille?kind=press").json()
    assert feed["feeds_configured"]
    titles = sorted(e["title"] for e in feed["entries"])
    assert titles == [
        "Délestage : la centrale de Toamasina en panne",
        "Le festival de musique reporté",
    ]
    article = next(e for e in feed["entries"] if e["url"] == "https://journal.test/delestage")
    assert (
        article["place"]["region"] == "Atsinanana"
        and article["text"] == "La JIRAMA annonce des coupures."
    )
    assert alice.get(base + "/signals").json()[0]["hits"] == 1
    # the GET drives the reader at most every 20 minutes
    alice.get(base + "/veille")
    assert not asyncio.run(queue.run_once())


def test_feed_and_stream_lists_are_parsed_leniently():
    assert veille_poll.parse_feeds(
        "https://www.journal.test/rss,  Midi|https://m.test/feed , nope"
    ) == [
        veille_poll.Feed("journal.test", "https://www.journal.test/rss"),
        veille_poll.Feed("Midi", "https://m.test/feed"),
    ]
    assert radio_capture.parse_streams(
        "RDJ|https://s.test/rdj|Analamanga, Fanambarana|https://s.test/f|Atsinanana|mg,|x,Bad|ftp://x"
    ) == [
        radio_capture.Stream("RDJ", "https://s.test/rdj", "Analamanga", "fr"),
        radio_capture.Stream("Fanambarana", "https://s.test/f", "Atsinanana", "mg"),
    ]
    assert radio_capture.parse_streams("") == []


def test_radio_capture_skips_quietly_without_ffmpeg(as_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "radio_streams", "RDJ|https://s.test/rdj|Analamanga")
    monkeypatch.setattr(radio_capture.shutil, "which", lambda name: None)
    alice = as_user("alice")
    ws = _workspace(alice)
    assert alice.post(f"/api/v1/workspaces/{ws}/veille/refresh").json() == {
        "queued": ["radio_capture"]
    }
    assert asyncio.run(queue.run_once())
    job = _db(lambda db: db.scalar(select(Job).where(Job.kind == "radio_capture")))
    assert job.status == "done" and job.result == {"skipped": "no_ffmpeg"}
    assert _db(lambda db: db.scalar(select(func.count()).select_from(RadioClip))) == 0


# --- demo
def test_the_demo_seeds_clips_words_and_seasons_idempotently(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}"
    for _ in range(2):
        assert alice.post(base + "/demo/reset").status_code == 200
    rows = alice.get(base + "/antenne").json()
    assert sum(r["reports"] for r in rows) == 3 and all(r["demo"] for r in rows)
    rdj = next(r for r in rows if r["stations"] == ["RDJ (démo)"])
    assert rdj["status"] == "followed" and rdj["ref"] == "FAN-0145"
    malagasy = next(r for r in rows if r["latest"]["language"] == "mg")
    assert malagasy["latest"]["text_from"] == "veilleur" and malagasy["status"] == "new"
    words = {s["word"]: s["hits"] for s in alice.get(base + "/signals").json()}
    assert words == {"délestage": 1, "enlèvement": 1}
    assert alice.get(base + "/meteo").json()["seasons"]
    feed = alice.get(base + "/veille").json()
    assert feed["counts"]["clip"] == 3 and all(e["demo"] for e in feed["entries"])
    assert [e["ref"] for e in feed["entries"] if e["station"] == "RDJ (démo)"] == ["FAN-0145"]
    assert _db(lambda db: db.scalar(select(func.count()).select_from(Signal))) == 2
