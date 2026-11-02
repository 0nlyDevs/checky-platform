import asyncio

from fastapi.testclient import TestClient

from app.main import app


def _workspace(c, name="Desk"):
    r = c.post("/api/v1/workspaces", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


def _join(admin, user, ws, role="journalist"):
    token = admin.post(f"/api/v1/workspaces/{ws}/invitations", json={"role": role}).json()["token"]
    assert user.post(f"/api/v1/invitations/{token}/accept").status_code == 200


def test_creator_is_admin_and_listed_in_me(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    me = alice.get("/api/v1/me").json()
    assert me["memberships"] == [
        {"workspace_id": ws, "name": "Desk", "slug": me["memberships"][0]["slug"], "role": "admin"}
    ]


def test_outsider_gets_404_not_403(as_user):
    ws = _workspace(as_user("alice"))
    r = as_user("mallory").get(f"/api/v1/workspaces/{ws}/members")
    assert r.status_code == 404


def test_invitation_flow_and_single_use(as_user):
    alice, bob, carol = as_user("alice"), as_user("bob"), as_user("carol")
    ws = _workspace(alice)
    token = alice.post(f"/api/v1/workspaces/{ws}/invitations", json={"role": "editor"}).json()[
        "token"
    ]
    assert bob.post(f"/api/v1/invitations/{token}/accept").json()["role"] == "editor"
    assert carol.post(f"/api/v1/invitations/{token}/accept").status_code == 404
    members = alice.get(f"/api/v1/workspaces/{ws}/members").json()
    assert {m["user_id"]: m["role"] for m in members} == {"alice": "admin", "bob": "editor"}
    assert {m["user_id"]: m["name"] for m in members} == {
        "alice": "Alice Rabe",
        "bob": "Bob Rakoto",
    }


def test_journalist_cannot_call_admin_routes(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    r = bob.post(f"/api/v1/workspaces/{ws}/invitations", json={"role": "admin"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


def test_last_admin_cannot_be_demoted_or_removed(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.patch(f"/api/v1/workspaces/{ws}/members/alice", json={"role": "editor"})
    assert r.status_code == 409
    assert alice.delete(f"/api/v1/workspaces/{ws}/members/alice").status_code == 409


def test_admin_changes_role_and_removes_member(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    r = alice.patch(f"/api/v1/workspaces/{ws}/members/bob", json={"role": "editor"})
    assert r.json()["role"] == "editor"
    assert alice.delete(f"/api/v1/workspaces/{ws}/members/bob").status_code == 204
    assert bob.get(f"/api/v1/workspaces/{ws}/members").status_code == 404


def test_settings_default_and_partial_patch(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    s = alice.get(f"/api/v1/workspaces/{ws}").json()["settings"]
    assert s["double_signature"] is False and s["ai_enabled"] is True
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


def test_only_admin_changes_settings(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws, role="editor")
    r = bob.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"double_signature": True}})
    assert r.status_code == 403


def test_permission_matrix_follows_the_routes_dependencies(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws, role="veilleur")
    out = bob.get(f"/api/v1/workspaces/{ws}/permissions").json()  # every member may read it
    assert out["roles"] == ["admin", "editor", "journalist", "veilleur", "issuer"]
    grid = {c["key"]: c["roles"] for c in out["capabilities"]}
    assert grid["read_dossiers"] == {
        "admin": True,
        "editor": True,
        "journalist": True,
        "veilleur": False,
        "issuer": False,
    }
    assert grid["record_clip"]["veilleur"] and not grid["record_clip"]["issuer"]
    assert grid["register"]["issuer"] and grid["register"]["editor"]
    assert not grid["register"]["journalist"]
    assert grid["edit_own"]["journalist"] and not grid["edit_all"]["journalist"]
    assert grid["edit_all"]["editor"] and grid["delete"]["editor"]
    assert not grid["delete"]["journalist"]
    assert grid["release"] == {
        "admin": True,
        "editor": True,
        "journalist": False,
        "veilleur": False,
        "issuer": False,
    }
    assert grid["invite"] == {r: r == "admin" for r in out["roles"]}
    assert grid["demo_reset"] == grid["invite"] == grid["settings"]
    sign = next(c for c in out["capabilities"] if c["key"] == "sign")
    assert sign["scope"] == "own" and sign["roles"]["journalist"]
    assert out["double_signature"] is False
    assert as_user("mallory").get(f"/api/v1/workspaces/{ws}/permissions").status_code == 404


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
    # a journalist reads the list but does not add or remove partners
    assert [x["name"] for x in bob.get(f"/api/v1/workspaces/{ws}/radios").json()] == [body["name"]]
    assert bob.post(f"/api/v1/workspaces/{ws}/radios", json=body).status_code == 403
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
    assert bob.delete(f"/api/v1/workspaces/{ws}/radios/{radio['id']}").status_code == 403
    assert alice.delete(f"/api/v1/workspaces/{ws}/radios/{radio['id']}").status_code == 204
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
