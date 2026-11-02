import asyncio

from fastapi.testclient import TestClient

from app.main import app


def _workspace(c, name="Desk"):
    r = c.post("/api/v1/workspaces", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


def _verify(ws):
    """Stand in for the Checky team approving the newsroom (see test_verification.py)."""
    from sqlalchemy import text

    from app.core.db import engine

    async def run():
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE app.workspace SET verification = 'approved' WHERE id = :id"),
                {"id": ws},
            )

    asyncio.run(run())


def _join(member, user, ws):
    token = member.post(f"/api/v1/workspaces/{ws}/invitations").json()["token"]
    assert user.post(f"/api/v1/invitations/{token}/accept").status_code == 200


def test_creator_is_a_member_listed_in_me(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    me = alice.get("/api/v1/me").json()
    assert me["memberships"] == [
        {
            "workspace_id": ws,
            "name": "Desk",
            "slug": me["memberships"][0]["slug"],
            "verification": "none",
        }
    ]


def test_outsider_gets_404_not_403(as_user):
    ws = _workspace(as_user("alice"))
    r = as_user("mallory").get(f"/api/v1/workspaces/{ws}/members")
    assert r.status_code == 404


def test_invitation_carries_no_role_and_is_single_use(as_user):
    alice, bob, carol = as_user("alice"), as_user("bob"), as_user("carol")
    ws = _workspace(alice)
    inv = alice.post(f"/api/v1/workspaces/{ws}/invitations").json()
    assert set(inv) == {"token", "expires_at"}
    joined = bob.post(f"/api/v1/invitations/{inv['token']}/accept").json()
    assert joined["id"] == ws and "role" not in joined
    assert carol.post(f"/api/v1/invitations/{inv['token']}/accept").status_code == 404
    members = alice.get(f"/api/v1/workspaces/{ws}/members").json()
    assert {m["user_id"]: m["name"] for m in members} == {
        "alice": "Alice Rabe",
        "bob": "Bob Rakoto",
    }
    assert all("role" not in m for m in members)


def test_every_member_can_do_what_the_newsroom_does(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    assert bob.post(f"/api/v1/workspaces/{ws}/invitations").status_code == 201
    assert bob.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True}).status_code == 200
    _verify(ws)
    item = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Le bac est reporté"})
    path = f"/api/v1/workspaces/{ws}/items/{item.json()['id']}"
    assert bob.patch(path, json={"title": "Le bac est reporté à lundi"}).status_code == 200
    assert bob.delete(path).status_code == 204
    assert bob.get(f"/api/v1/workspaces/{ws}/permissions").status_code == 404


def test_last_member_cannot_be_removed(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.delete(f"/api/v1/workspaces/{ws}/members/alice")
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_member"


def test_a_member_removes_a_colleague_or_leaves(as_user):
    alice, bob, carol = as_user("alice"), as_user("bob"), as_user("carol")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    _join(alice, carol, ws)
    assert bob.delete(f"/api/v1/workspaces/{ws}/members/carol").status_code == 204
    assert carol.get(f"/api/v1/workspaces/{ws}/members").status_code == 404
    assert bob.delete(f"/api/v1/workspaces/{ws}/members/bob").status_code == 204
    assert alice.delete(f"/api/v1/workspaces/{ws}/members/alice").status_code == 409
    assert alice.delete(f"/api/v1/workspaces/{ws}/members/nobody").status_code == 404


def test_settings_default_and_partial_patch(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    s = alice.get(f"/api/v1/workspaces/{ws}").json()["settings"]
    assert "double_signature" not in s and s["ai_enabled"] is True
    assert s["timezone"] == "Indian/Antananarivo" and s["country"] == "Madagascar"
    assert "énergie" in s["beats"] and s["region"] is None
    r = alice.patch(
        f"/api/v1/workspaces/{ws}",
        json={"settings": {"beats": [" Énergie ", "santé", "énergie", "Cyclones  et routes"]}},
    )
    s = r.json()["settings"]
    assert s["beats"] == ["énergie", "santé", "cyclones et routes"]
    # a field left out keeps its value
    r = alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"ai_enabled": False}})
    s = r.json()["settings"]
    assert s["ai_enabled"] is False and s["beats"][0] == "énergie"
    r = alice.patch(
        f"/api/v1/workspaces/{ws}",
        json={"settings": {"timezone": "Europe/Paris", "country": "France", "region": "Bretagne"}},
    )
    assert r.json()["settings"]["timezone"] == "Europe/Paris"
    assert r.json()["settings"]["region"] == "Bretagne"


def test_settings_refuse_unknown_zone_and_empty_beat(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    bad_zone = {"settings": {"timezone": "Mars/Olympus"}}
    assert alice.patch(f"/api/v1/workspaces/{ws}", json=bad_zone).status_code == 422
    bad_beat = {"settings": {"beats": ["  "]}}
    assert alice.patch(f"/api/v1/workspaces/{ws}", json=bad_beat).status_code == 422


def test_partner_radios_with_a_token_link(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    body = {"name": "Radio Fanambarana (démo)", "frequency": "FM 98.4", "region": "Toamasina"}
    r = alice.post(f"/api/v1/workspaces/{ws}/radios", json=body)
    assert r.status_code == 201
    radio = r.json()
    assert radio["location"]["region"] == "Atsinanana"
    assert "/flashs?radio=" in radio["link"] and radio["broadcasts"] == 0
    assert radio["languages"] == ["mg", "fr"] and radio["last_broadcast_at"] is None
    # every journalist reads and manages the partners
    assert [x["name"] for x in bob.get(f"/api/v1/workspaces/{ws}/radios").json()] == [body["name"]]
    extra = bob.post(f"/api/v1/workspaces/{ws}/radios", json={**body, "name": "Radio Doublon"})
    assert extra.status_code == 201
    assert bob.delete(f"/api/v1/workspaces/{ws}/radios/{extra.json()['id']}").status_code == 204
    # the radio opens its link without an account
    token = radio["link"].rsplit("=", 1)[1]
    anon = TestClient(app)
    seen = anon.get(f"/api/v1/public/radios/{token}").json()
    assert seen["name"] == body["name"] and seen["newsroom"]["name"] == "Desk"
    assert anon.get("/api/v1/public/radios/nope").status_code == 404
    # a flash the radio marked « Diffusé » is counted (the stop is named after the station)
    asyncio.run(_aired(ws, alice, radio["id"], "Radio Fanambarana (démo) FM 98.4"))
    listed = alice.get(f"/api/v1/workspaces/{ws}/radios").json()[0]
    assert listed["broadcasts"] == 1 and listed["last_broadcast_at"]
    assert bob.delete(f"/api/v1/workspaces/{ws}/radios/{radio['id']}").status_code == 204
    assert alice.get(f"/api/v1/workspaces/{ws}/radios").json() == []


async def _aired(ws, client, radio_id, station):
    from app.core.db import SessionLocal
    from app.core.models import Route

    item = client.post(
        f"/api/v1/workspaces/{ws}/items", json={"title": "Flash lu à l'antenne", "data": {}}
    ).json()["id"]
    async with SessionLocal() as db:
        db.add(
            Route(
                workspace_id=ws,
                item_id=item,
                added_by=f"radio:{radio_id}",
                side="truth",
                channel="radio",
                place=station,
                status="broadcast",
                proof={"partner_id": radio_id},
            )
        )
        await db.commit()
