"""Public features: only opted-in newsrooms and published, confirmed verdicts leave the newsroom."""

from fastapi.testclient import TestClient

from app.main import app


def _newsroom(c, public=True):
    ws = c.post("/api/v1/workspaces", json={"name": "Desk du matin"}).json()["id"]
    if public:
        assert c.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True}).json()["is_public"]
    return ws, c.get(f"/api/v1/workspaces/{ws}").json()["slug"]


def _claim(c, ws, title, status="published", verdict="false", **data):
    r = c.post(
        f"/api/v1/workspaces/{ws}/items",
        json={
            "title": title,
            "status": status,
            "data": {"ref": "FAN-0001", "verdict": verdict, **data},
        },
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_archive_shows_only_published_verdicts_of_public_newsrooms(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, slug = _newsroom(alice)
    hidden, _ = _newsroom(bob, public=False)
    shown = _claim(
        alice, ws, "Une vidéo montre l'inondation d'Analakely ce matin", reason="Images de 2019."
    )
    _claim(alice, ws, "Le bac est reporté", status="in_progress")
    _claim(bob, hidden, "Un secret de rédaction")
    anon = TestClient(app)
    page = anon.get("/api/v1/public/verdicts").json()
    assert page["total"] == 1 and page["items"][0]["id"] == shown
    assert (
        page["items"][0]["reason"] == "Images de 2019."
        and page["items"][0]["newsroom"]["slug"] == slug
    )
    assert anon.get(f"/api/v1/public/verdicts/{shown}").status_code == 200
    assert [n["slug"] for n in anon.get("/api/v1/public/newsrooms").json()] == [slug]


def test_a_rumour_checked_by_several_newsrooms_shows_once(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    first, _ = _newsroom(alice)
    second, _ = _newsroom(bob)
    rumour = "Une vidéo montre l'inondation d'Analakely ce matin"
    _claim(alice, first, rumour)
    newest = _claim(bob, second, rumour.upper())  # same words, accents and case aside
    _claim(bob, second, "Une vidéo montre l'inondation d'Analakely ce matin !", verdict="true")
    anon = TestClient(app)
    page = anon.get("/api/v1/public/verdicts").json()
    assert page["total"] == 2  # the same claim with another verdict is another file
    assert newest in [v["id"] for v in page["items"]]
    hits = anon.post("/api/v1/public/match", json={"text": "inondation Analakely vidéo"}).json()
    assert len(hits) == 2


def test_match_finds_a_published_verdict_and_never_invents_one(as_user):
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _claim(alice, ws, "Une vidéo montre l'inondation d'Analakely ce matin")
    anon = TestClient(app)
    hits = anon.post(
        "/api/v1/public/match", json={"text": "regardez l'inondation à Analakely, la vidéo !!"}
    ).json()
    assert len(hits) == 1 and hits[0]["verdict"]["verdict"] == "false"
    assert (
        anon.post("/api/v1/public/match", json={"text": "le prix du carburant baisse"}).json() == []
    )


def test_tip_lands_in_the_desk_and_can_be_followed(as_user):
    alice = as_user("alice")
    ws, slug = _newsroom(alice)
    anon = TestClient(app)
    r = anon.post(
        "/api/v1/public/tips",
        json={"newsroom": slug, "text": "On dit que le pont est fermé", "origin": "whatsapp"},
    )
    assert r.status_code == 201
    token, ref = r.json()["token"], r.json()["ref"]
    items = alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"]
    tip = next(i for i in items if i["data"].get("tip_token") == token)
    assert (
        tip["status"] == "to_check" and tip["author_id"] == "public" and tip["data"]["ref"] == ref
    )
    status = anon.get(f"/api/v1/public/tips/{token}").json()
    assert status["status"] == "to_check" and status["verdict"] is None
    alice.patch(
        f"/api/v1/workspaces/{ws}/items/{tip['id']}",
        json={"status": "published", "data": {"verdict": "true"}},
    )
    assert anon.get(f"/api/v1/public/tips/{token}").json()["verdict"]["verdict"] == "true"


def test_tips_only_reach_public_newsrooms_and_are_limited(as_user):
    alice = as_user("alice")
    _, private = _newsroom(alice, public=False)
    anon = TestClient(app)
    assert (
        anon.post(
            "/api/v1/public/tips", json={"newsroom": private, "text": "une rumeur"}
        ).status_code
        == 404
    )
    _, slug = _newsroom(as_user("bob"))
    codes = [
        anon.post("/api/v1/public/tips", json={"newsroom": slug, "text": f"rumeur {i}"}).status_code
        for i in range(7)
    ]
    assert codes.count(201) <= 5 and 429 in codes


def test_any_member_opens_the_newsroom(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice, public=False)
    token = alice.post(f"/api/v1/workspaces/{ws}/invitations").json()["token"]
    bob.post(f"/api/v1/invitations/{token}/accept")
    assert bob.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True}).json()["is_public"]


def test_ask_answers_only_from_published_files(as_user, monkeypatch):
    import json

    import httpx

    from app.core import ai
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "k")
    monkeypatch.setattr(s, "llm_providers", "gemini")
    monkeypatch.setattr(s, "ai_cache", False)
    prompts = []

    def chat(request):
        prompts.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "C'est faux : la vidéo date de 2019 [1]."}}]},
        )

    monkeypatch.setattr(ai, "_transport", httpx.MockTransport(chat))
    alice = as_user("alice")
    ws, _ = _newsroom(alice)
    _claim(
        alice, ws, "Une vidéo montre l'inondation d'Analakely ce matin", reason="Images de 2019."
    )
    anon = TestClient(app)
    r = anon.post("/api/v1/public/ask", json={"question": "Analakely est inondé ce matin ?"}).json()
    assert r["checked"] and r["answer"].endswith("[1].") and r["verdicts"][0]["verdict"] == "false"
    assert "Images de 2019." in prompts[0]["messages"][1]["content"]
    # nothing published on the subject: no AI call, an invitation to send a tip instead
    r = anon.post(
        "/api/v1/public/ask", json={"question": "Le carburant baisse-t-il demain ?"}
    ).json()
    assert r == {"answer": None, "verdicts": [], "checked": False} and len(prompts) == 1


def test_dictation_transcribes_a_short_recording(monkeypatch):
    import httpx

    from app.core import stt
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "groq_api_key", "k")
    seen = {}

    def whisper(request):
        seen["body"] = request.content
        return httpx.Response(
            200, json={"text": " Misy vola vaovao ve ? ", "language": "malagasy", "segments": []}
        )

    monkeypatch.setattr(stt, "_transport", httpx.MockTransport(whisper))
    anon = TestClient(app)
    r = anon.post(
        "/api/v1/public/transcribe?lang=mg",
        content=b"\x1a\x45\xdf\xa3fake",
        headers={"content-type": "audio/webm;codecs=opus"},
    )
    assert r.status_code == 200 and r.json()["text"] == "Misy vola vaovao ve ?"
    assert b'name="language"' in seen["body"] and b"mg" in seen["body"]
    assert (
        anon.post(
            "/api/v1/public/transcribe", content=b"x", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )


def test_speak_uses_elevenlabs_once_per_answer_and_falls_back_without_a_key(monkeypatch):
    import json

    import httpx

    from app.core.config import get_settings
    from app.modules import public

    anon = TestClient(app)
    monkeypatch.setattr(
        public, "_tts_transport", httpx.MockTransport(lambda r: httpx.Response(500))
    )
    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "")
    assert anon.post("/api/v1/public/speak", json={"text": "Bonjour"}).status_code == 501
    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "xi")
    calls = []

    def tts(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, content=b"ID3fake-mp3")

    monkeypatch.setattr(public, "_tts_transport", httpx.MockTransport(tts))
    for _ in range(2):
        r = anon.post("/api/v1/public/speak", json={"text": "C'est faux [1].", "lang": "fr"})
        assert (
            r.status_code == 200
            and r.headers["content-type"] == "audio/mpeg"
            and r.content == b"ID3fake-mp3"
        )
    assert (
        len(calls) == 1 and calls[0]["text"] == "C'est faux." and calls[0]["language_code"] == "fr"
    )


def test_flashes_of_the_day_and_short_links(as_user, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "public_web_url", "https://checky.example")
    alice = as_user("alice")
    ws, slug = _newsroom(alice)
    first = _claim(
        alice,
        ws,
        "Une vidéo montre l'inondation d'Analakely ce matin",
        reason="Images de 2019. Elles circulent chaque année.",
    )
    alice.patch(f"/api/v1/workspaces/{ws}/items/{first}", json={"data": {"ref": "FAN-0142"}})
    _claim(alice, ws, "Le bac est reporté", status="in_progress")
    anon = TestClient(app)
    out = anon.get(f"/api/v1/public/flashs?newsroom={slug}").json()
    assert out["newsroom"]["slug"] == slug and len(out["items"]) == 1
    line = out["items"][0]
    assert line["fr"] == (
        "1. Faux — Une vidéo montre l'inondation d'Analakely ce matin. Images de 2019. "
        "https://checky.example/v/142"
    )
    assert line["mg"].startswith("1. Diso — ") and line["link"] == "https://checky.example/v/142"
    assert anon.get("/api/v1/public/flashs").json()["items"][0]["id"] == first
    assert anon.get("/api/v1/public/flashs?newsroom=nope").status_code == 404
    assert anon.get("/api/v1/public/v/142").json()["id"] == first
    assert anon.get("/api/v1/public/v/FAN-0142").json()["id"] == first
    assert anon.get("/api/v1/public/v/143").status_code == 404
