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
