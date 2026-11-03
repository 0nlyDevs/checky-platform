"""Studio: a live show checked as it airs (chunks, flags, producer and presenter), Mode débat and
the bilan."""

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from app.core import ai, storage, stt
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import Figure, Route, Show, Source
from app.modules import studio
from tests.ref_fixture import set_ref
from tests.test_workspaces import _verify, _workspace

OBJECTS: dict[str, bytes] = {}


@pytest.fixture
def whisper(monkeypatch):
    """Groq Whisper stand-in: each chunk is heard as the next scripted reply."""
    replies: list[list[tuple[float, float, str]]] = []
    calls: list[str] = []
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.content.decode(errors="replace"))
        segs = replies.pop(0) if replies else []
        return httpx.Response(
            200,
            json={
                "text": " ".join(t for _, _, t in segs),
                "language": "french",
                "duration": 10,
                "segments": [{"start": a, "end": b, "text": f" {t}"} for a, b, t in segs],
            },
        )

    monkeypatch.setattr(stt, "_transport", httpx.MockTransport(handler))
    return replies, calls


@pytest.fixture
def fake_storage(monkeypatch):
    OBJECTS.clear()

    class Client:
        def put_object(self, Bucket, Key, Body, ContentType):
            OBJECTS[Key] = Body

    async def delete(key):
        OBJECTS.pop(key, None)

    monkeypatch.setattr(storage, "configured", lambda: True)
    monkeypatch.setattr(storage, "client", lambda: Client())
    monkeypatch.setattr(storage, "delete", delete)
    monkeypatch.setattr(
        storage,
        "presign_download",
        lambda key, filename=None, expires=3600: f"https://s3.test/{key}",
    )


@pytest.fixture
def no_model(monkeypatch):
    """Any model call fails the test unless a test installs its own transport."""

    def handler(request):
        raise AssertionError("no model call expected")

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))


def _figures(ws):
    async def run():
        async with SessionLocal() as db:
            db.add_all(
                [
                    Figure(
                        workspace_id=ws,
                        topic="énergie",
                        label="Hausse du tarif de l'électricité",
                        value="+12",
                        unit="%",
                        as_of="2026-10",
                        country="Madagascar",
                        source_name="ORE (démo)",
                        keywords=["tarif", "électricité", "hausse"],
                    ),
                    Figure(
                        workspace_id=ws,
                        topic="énergie",
                        label="Délestage programmé à Antananarivo",
                        value="4",
                        unit="h/jour",
                        as_of="2026-11-01",
                        country="Madagascar",
                        source_name="JIRAMA (démo)",
                        keywords=["délestage", "coupure", "jirama"],
                    ),
                ]
            )
            await db.commit()

    asyncio.run(run())


def _show(c, ws, **extra):
    body = {"title": "Le débat du soir", "topics": ["énergie"], **extra}
    r = c.post(f"/api/v1/workspaces/{ws}/studio", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _chunk(c, ws, show, seq, start, body=b"opus-bytes", mime="audio/webm"):
    return c.post(
        f"/api/v1/workspaces/{ws}/studio/{show}/chunk?seq={seq}&start_s={start}&duration_s=10",
        content=body,
        headers={"Content-Type": mime},
    )


def test_chunk_is_transcribed_and_claims_are_flagged_by_code(
    as_user, whisper, fake_storage, no_model
):
    replies, calls = whisper
    alice = as_user("alice")
    ws = _workspace(alice)
    _figures(ws)
    show = _show(alice, ws)
    assert _chunk(alice, ws, show["id"], 0, 0).status_code == 409  # not started
    assert (
        alice.post(f"/api/v1/workspaces/{ws}/studio/{show['id']}/start").json()["status"] == "live"
    )
    replies.append(
        [
            (0.0, 3.0, "Bonsoir à tous."),
            (3.0, 8.0, "Le tarif va augmenter de 40 % en décembre."),
        ]
    )
    replies.append(
        [
            (0.5, 6.0, "Selon la JIRAMA, le délestage sera de 4 heures par jour."),
            (6.0, 9.5, "Nous avons raccordé 3 000 ménages au réseau cette année."),
        ]
    )
    r = _chunk(alice, ws, show["id"], 0, 0)
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["transcribed"] and first["stored"]
    assert [s["start"] for s in first["segments"]] == [0.0, 3.0]
    [tarif] = first["claims"]
    assert tarif["at_s"] == 3.0 and tarif["origin"] == "code"
    assert tarif["flag"]["kind"] == "contradicted"
    ev = tarif["flag"]["evidence"][0]
    assert (ev["type"], ev["official"], ev["source"]) == ("figure", "+12 %", "ORE (démo)")
    assert ev["date_label"]  # every flag carries its source's date
    assert 'name="language"' in calls[0] and "fr" in calls[0]

    second = _chunk(alice, ws, show["id"], 1, 10).json()
    kinds = {c["text"][:9]: c["flag"]["kind"] for c in second["claims"]}
    assert kinds == {"Selon la ": "consistent", "Nous avon": "no_source"}
    assert [c["at_s"] for c in second["claims"]] == [10.5, 16.0]
    full = alice.get(f"/api/v1/workspaces/{ws}/studio/{show['id']}").json()
    assert len(full["segments"]) == 4 and full["chunks"] == 2
    assert len(OBJECTS) == 2


def test_malagasy_show_is_never_transcribed_the_producer_types(
    as_user, whisper, fake_storage, no_model
):
    _, calls = whisper
    alice = as_user("alice")
    ws = _workspace(alice)
    _figures(ws)
    show = _show(alice, ws, language="mg")
    alice.post(f"/api/v1/workspaces/{ws}/studio/{show['id']}/start")
    r = _chunk(alice, ws, show["id"], 0, 0).json()
    assert (r["transcribed"], r["segments"], r["claims"], r["stored"]) == (False, [], [], True)
    assert calls == []
    typed = alice.post(
        f"/api/v1/workspaces/{ws}/studio/{show['id']}/claims",
        json={"text": "Hoy izy : hiakatra 40 % ny tarif amin'ny desambra", "at_s": 4},
    )
    assert typed.status_code == 201
    assert typed.json()["origin"] == "typed" and typed.json()["at_s"] == 4


def test_without_transcription_the_chunk_is_kept_and_typing_still_works(
    as_user, fake_storage, monkeypatch
):
    monkeypatch.setattr(get_settings(), "groq_api_key", "")
    alice = as_user("alice")
    ws = _workspace(alice)
    show = _show(alice, ws)
    alice.post(f"/api/v1/workspaces/{ws}/studio/{show['id']}/start")
    r = _chunk(alice, ws, show["id"], 0, 0).json()
    assert (r["error"], r["stored"], r["transcribed"]) == ("stt_unavailable", True, False)
    assert _chunk(alice, ws, show["id"], 1, 10, mime="text/plain").status_code == 415
    assert _chunk(alice, ws, show["id"], 1, 10, body=b"").status_code == 422


def test_producer_sends_and_presenter_sees_the_last_three(as_user, whisper, fake_storage, no_model):
    alice = as_user("alice")
    ws = _workspace(alice)
    show = _show(alice, ws)["id"]
    alice.post(f"/api/v1/workspaces/{ws}/studio/{show}/start")
    ids = []
    for i in range(5):
        r = alice.post(
            f"/api/v1/workspaces/{ws}/studio/{show}/claims",
            json={"text": f"Selon le ministère, {i + 2} 000 écoles ont été rénovées.", "at_s": i},
        )
        ids.append(r.json()["id"])
    base = f"/api/v1/workspaces/{ws}/studio/{show}/claims"
    assert alice.get(f"/api/v1/workspaces/{ws}/studio/{show}/presenter").json()["flags"] == []
    for cid in ids[:4]:
        assert (
            alice.post(f"{base}/{cid}/send", json={"question": "Quelle source ?"}).status_code
            == 200
        )
    alice.post(f"{base}/{ids[4]}/dismiss")
    flags = alice.get(f"/api/v1/workspaces/{ws}/studio/{show}/presenter").json()["flags"]
    assert [f["id"] for f in flags] == [ids[3], ids[2], ids[1]]
    assert flags[0]["question"] == "Quelle source ?"
    # dismissing a sent flag takes it off the presenter's screen
    alice.post(f"{base}/{ids[3]}/dismiss")
    flags = alice.get(f"/api/v1/workspaces/{ws}/studio/{show}/presenter").json()["flags"]
    assert ids[3] not in [f["id"] for f in flags]


def test_debate_counts_claims_per_speaker_without_a_score(as_user, whisper, fake_storage, no_model):
    replies, _ = whisper
    alice = as_user("alice")
    ws = _workspace(alice)
    _figures(ws)
    show = _show(
        alice,
        ws,
        speakers=[{"id": "a", "name": "Intervenant A"}, {"id": "b", "name": "Intervenante B"}],
    )["id"]
    base = f"/api/v1/workspaces/{ws}/studio/{show}"
    alice.post(f"{base}/start")
    assert alice.post(f"{base}/speaker", json={"speaker_id": "z"}).status_code == 422
    alice.post(f"{base}/speaker", json={"speaker_id": "a", "at_s": 0})
    alice.post(f"{base}/speaker", json={"speaker_id": "b", "at_s": 5})
    replies.append(
        [
            (1.0, 4.0, "Selon la JIRAMA, le délestage sera de 4 heures par jour."),
            (5.0, 9.0, "Le tarif va augmenter de 40 % en décembre."),
        ]
    )
    claims = _chunk(alice, ws, show, 0, 0).json()["claims"]
    assert [c["speaker_id"] for c in claims] == ["a", "b"]
    full = alice.get(base).json()
    rows = {r["speaker_id"]: r for r in full["by_speaker"]}
    assert (rows["a"]["claims"], rows["a"]["consistent"], rows["a"]["contradicted"]) == (1, 1, 0)
    assert (rows["b"]["claims"], rows["b"]["contradicted_official"]) == (1, 1)
    assert [r["speaker_id"] for r in full["by_speaker"]] == ["a", "b"]  # the producer's order
    assert not {"score", "rank", "honesty"} & set(full["by_speaker"][0])
    # a claim moved to the other speaker
    moved = alice.patch(f"{base}/claims/{claims[0]['id']}", json={"speaker_id": "b"}).json()
    assert moved["speaker_id"] == "b"


def test_model_adds_a_verbatim_claim_every_thirty_seconds_at_most(
    as_user, whisper, fake_storage, monkeypatch
):
    replies, _ = whisper
    asked: list[dict] = []

    def handler(request):
        asked.append(json.loads(request.content))
        content = json.dumps(
            {
                "claims": [
                    {"text": "les écoles du district ont toutes rouvert lundi dernier"},
                    {"text": "une phrase que personne n'a prononcée à l'antenne ce soir"},
                ]
            }
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                "model": "stand-in",
            },
        )

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(get_settings(), "llm_providers", "groq")
    alice = as_user("alice")
    ws = _workspace(alice)
    show = _show(alice, ws)["id"]
    alice.post(f"/api/v1/workspaces/{ws}/studio/{show}/start")
    replies.append([(0.0, 9.0, "Bon, les écoles du district ont toutes rouvert lundi dernier")])
    _chunk(alice, ws, show, 0, 0)
    assert asked == []  # 9 s of show: too early
    replies.append([(1.0, 9.0, "Et voilà ce que nous savons ce soir.")])
    _chunk(alice, ws, show, 1, 10)
    _chunk(alice, ws, show, 2, 20)
    replies.append([(1.0, 9.0, "Nous en reparlons après la pause.")])
    _chunk(alice, ws, show, 3, 30)
    assert len(asked) == 1
    full = alice.get(f"/api/v1/workspaces/{ws}/studio/{show}").json()
    found = [c for c in full["claim_list"] if c["origin"] == "model"]
    assert [c["text"] for c in found] == ["les écoles du district ont toutes rouvert lundi dernier"]
    assert found[0]["at_s"] == 0.0


def test_ai_off_skips_the_model_call(as_user, whisper, fake_storage, no_model):
    replies, _ = whisper
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"ai_enabled": False}})
    show = _show(alice, ws)["id"]
    alice.post(f"/api/v1/workspaces/{ws}/studio/{show}/start")
    replies.append([(0.0, 40.0, "Un très long passage sans aucun chiffre ni institution citée.")])
    assert _chunk(alice, ws, show, 0, 0).status_code == 200  # no_model would raise


def test_bilan_follow_makes_a_dossier_with_the_clip_and_a_radio_stop(
    as_user, whisper, fake_storage, no_model
):
    replies, _ = whisper
    alice = as_user("alice")
    ws = _workspace(alice)
    _figures(ws)
    show = _show(alice, ws, station="Radio Test")["id"]
    base = f"/api/v1/workspaces/{ws}/studio/{show}"
    alice.post(f"{base}/start")
    replies.append([(4.0, 8.0, "Le tarif va augmenter de 40 % en décembre.")])
    _chunk(alice, ws, show, 0, 0)
    replies.append([(2.0, 6.0, "Bonne soirée.")])
    _chunk(alice, ws, show, 1, 10)
    assert alice.post(f"{base}/end").json()["status"] == "ended"
    bilan = alice.get(f"{base}/bilan").json()
    [claim] = bilan["claim_list"]
    assert claim["clip"]["offset_s"] == 4.0 and claim["clip"]["url"].startswith("https://s3.test/")
    r = alice.post(f"{base}/claims/{claim['id']}/follow")
    assert r.status_code == 201, r.text
    made = r.json()
    item = alice.get(f"/api/v1/workspaces/{ws}/items/{made['item_id']}").json()
    assert item["data"]["origin"] == "radio" and item["data"]["ref"] == made["ref"]
    assert item["data"]["source_count"] == 1
    assert alice.post(f"{base}/claims/{claim['id']}/follow").status_code == 409

    async def check():
        async with SessionLocal() as db:
            src = await db.get(Source, __import__("uuid").UUID(made["source_id"]))
            stop = await db.scalar(select(Route).where(Route.item_id == src.item_id))
            return src, stop

    src, stop = asyncio.run(check())
    assert (src.kind, src.status, src.file_id is not None) == ("audio", "ready", True)
    assert (stop.channel, stop.side, stop.place) == ("radio", "rumour", "Radio Test")
    assert stop.proof["clip_at_s"] == 4.0
    assert alice.get(f"{base}/bilan").json()["claim_list"][0]["ref"] == made["ref"]


def test_pack_preloads_verdicts_figures_and_originals_on_the_topics(as_user, whisper, no_model):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    _figures(ws)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/items",
        json={
            "title": "72 heures de délestage à Antananarivo",
            "status": "published",
            "tags": ["énergie"],
            "data": {"verdict": "false"},
        },
    )
    assert r.status_code == 201, r.text
    set_ref(r.json()["id"], "FAN-0001")
    show = _show(alice, ws)["id"]
    p = alice.get(f"/api/v1/workspaces/{ws}/studio/{show}/pack").json()
    assert [v["ref"] for v in p["verdicts"]] == ["FAN-0001"]
    assert {f["label"] for f in p["figures"]} >= {"Hausse du tarif de l'électricité"}
    assert "registry" in p


def test_signed_verdict_contradicts_a_repeated_rumour(as_user, whisper, fake_storage, no_model):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/items",
        json={
            "title": "Les écoles d'Antananarivo fermées toute la semaine prochaine",
            "status": "published",
            "data": {"verdict": "false"},
        },
    )
    assert r.status_code == 201, r.text
    set_ref(r.json()["id"], "FAN-0009")
    show = _show(alice, ws)["id"]
    alice.post(f"/api/v1/workspaces/{ws}/studio/{show}/start")
    c = alice.post(
        f"/api/v1/workspaces/{ws}/studio/{show}/claims",
        json={
            "text": "Selon nos auditeurs, les écoles d'Antananarivo seront fermées la semaine prochaine"
        },
    ).json()
    assert c["flag"]["kind"] == "contradicted"
    assert c["flag"]["evidence"][0]["ref"] == "FAN-0009"


def test_outsiders_cannot_reach_a_show(as_user, whisper):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    show = _show(alice, ws)["id"]
    assert bob.get(f"/api/v1/workspaces/{ws}/studio/{show}").status_code == 404
    other = _workspace(bob)
    assert bob.get(f"/api/v1/workspaces/{other}/studio/{show}").status_code == 404
    assert asyncio.run(studio.can_join("alice", __import__("uuid").UUID(show)))
    assert not asyncio.run(studio.can_join("bob", __import__("uuid").UUID(show)))


def test_demo_show_has_three_flags_and_two_speakers(as_user, monkeypatch, no_model):
    alice = as_user("alice")
    ws = _workspace(alice)
    assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").status_code == 200
    shows = alice.get(f"/api/v1/workspaces/{ws}/studio").json()
    [demo] = [s for s in shows if s["is_demo"]]
    full = alice.get(f"/api/v1/workspaces/{ws}/studio/{demo['id']}").json()
    kinds = sorted(c["flag"]["kind"] for c in full["claim_list"])
    assert kinds == ["consistent", "contradicted", "no_source"]
    tarif = next(c for c in full["claim_list"] if c["flag"]["kind"] == "contradicted")
    assert tarif["flag"]["evidence"][0]["official"] == "+12 %"
    assert [s["name"] for s in full["speakers"]] == [
        "Intervenant A (démo)",
        "Intervenante B (démo)",
    ]
    # reset again: still one demo show
    alice.post(f"/api/v1/workspaces/{ws}/demo/reset")

    async def n():
        async with SessionLocal() as db:
            return len((await db.scalars(select(Show).where(Show.is_demo.is_(True)))).all())

    assert asyncio.run(n()) == 1
