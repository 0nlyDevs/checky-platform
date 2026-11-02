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


def test_only_admins_open_the_newsroom(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws, _ = _newsroom(alice, public=False)
    token = alice.post(f"/api/v1/workspaces/{ws}/invitations", json={"role": "editor"}).json()[
        "token"
    ]
    bob.post(f"/api/v1/invitations/{token}/accept")
    assert bob.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True}).status_code == 403
