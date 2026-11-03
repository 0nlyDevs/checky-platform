from tests.test_workspaces import _join, _workspace


def _item(c, ws, **fields):
    r = c.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Claim", **fields})
    assert r.status_code == 201
    return r.json()


def test_crud_filters_and_search(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    _item(alice, ws, title="Rice prices doubled", tags=["economy"])
    _item(alice, ws, title="Cyclone warning", status="verified", tags=["weather"])
    base = f"/api/v1/workspaces/{ws}/items"
    assert alice.get(base).json()["total"] == 2
    assert [i["title"] for i in alice.get(base, params={"tag": "economy"}).json()["items"]] == [
        "Rice prices doubled"
    ]
    assert alice.get(base, params={"status": "verified"}).json()["total"] == 1
    assert alice.get(base, params={"q": "cyclone"}).json()["total"] == 1


def test_new_field_needs_no_migration(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _item(alice, ws, data={"verdict": "false"})
    r = alice.patch(
        f"/api/v1/workspaces/{ws}/items/{item['id']}", json={"data": {"source_count": 3}}
    )
    data = r.json()["data"]
    assert (data["verdict"], data["source_count"]) == ("false", 3)
    assert data["ref"].startswith("FAN-")


def test_workspace_isolation(as_user):
    alice, mallory = as_user("alice"), as_user("mallory")
    ws_a = _workspace(alice)
    ws_m = _workspace(mallory, "Other")
    item = _item(alice, ws_a)
    # Mallory uses her own workspace id with Alice's item id.
    assert mallory.get(f"/api/v1/workspaces/{ws_m}/items/{item['id']}").status_code == 404
    assert mallory.get(f"/api/v1/workspaces/{ws_a}/items").status_code == 404


def test_every_member_edits_and_deletes(as_user):
    alice, bob, carol = as_user("alice"), as_user("bob"), as_user("carol")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    _join(alice, carol, ws)
    item = _item(bob, ws)
    url = f"/api/v1/workspaces/{ws}/items/{item['id']}"
    assert carol.patch(url, json={"title": "x"}).status_code == 200
    assert bob.patch(url, json={"title": "Edited"}).json()["title"] == "Edited"
    assert carol.delete(url).status_code == 204


def test_comments_and_activity_log(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _item(alice, ws)
    url = f"/api/v1/workspaces/{ws}/items/{item['id']}"
    alice.patch(url, json={"status": "in_progress"})
    alice.post(f"{url}/comments", json={"body": "Calling the ministry"})
    assert [c["body"] for c in alice.get(f"{url}/comments").json()] == ["Calling the ministry"]
    log = alice.get(f"/api/v1/workspaces/{ws}/activity").json()
    assert [(a["entity"], a["action"]) for a in log] == [
        ("item", "comment"),
        ("item", "update"),
        ("item", "create"),
    ]
    assert log[1]["diff"] == {"status": {"from": "to_check", "to": "in_progress"}}
    # One claim's history, comments included.
    other = _item(alice, ws, title="Other")
    scoped = alice.get(f"/api/v1/workspaces/{ws}/activity", params={"entity_id": item["id"]}).json()
    assert len(scoped) == 3
    assert other["id"] not in {a["entity_id"] for a in scoped}


def test_any_member_resets_the_demo_and_replaces_items(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _join(alice, bob, ws)
    _item(alice, ws, title="Will be replaced")
    n = bob.post(f"/api/v1/workspaces/{ws}/demo/reset").json()["items"]
    items = alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"]
    assert len(items) == n
    assert all(i["data"]["demo"] and i["data"]["first_seen_at"] for i in items)


def test_demo_reset_seeds_sources_on_claims(as_user):
    from tests.test_workspaces import _workspace

    alice = as_user("alice")
    ws = _workspace(alice)
    assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").json() == {"items": 9}
    sources = alice.get(f"/api/v1/workspaces/{ws}/sources").json()
    assert len(sources) == 8
    assert all(s["title"].startswith("Démo ·") and "fictif" in s["title"] for s in sources)
    items = alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"]
    assert sum(i["data"]["source_count"] for i in items) == 8
    # A second reset replaces them instead of piling up.
    alice.post(f"/api/v1/workspaces/{ws}/demo/reset")
    assert len(alice.get(f"/api/v1/workspaces/{ws}/sources").json()) == 8


def test_demo_published_verdicts_are_signed(as_user):
    """A published demo verdict carries a valid signature, so nothing public says « Faux » unsigned."""
    from app.modules.signing import digest

    alice = as_user("alice")
    ws = _workspace(alice)
    alice.post(f"/api/v1/workspaces/{ws}/demo/reset")
    published = [
        i
        for i in alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"]
        if i["status"] == "published"
    ]
    assert published
    for i in published:
        d = i["data"]
        assert d["signed_by"] and d["signed_at"] and d["byline"]["journalist"]
        assert d["signed_digest"] == digest(i["title"], i["body"], d)


def test_similar_claims_warn_of_a_duplicate(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    for title in (
        "Le pont de Mangasoavina serait fermé jusqu'à lundi",
        "Le prix du riz a doublé à Antananarivo",
    ):
        alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": title})

    def similar(q):
        r = alice.get(f"/api/v1/workspaces/{ws}/items/similar", params={"q": q})
        assert r.status_code == 200
        return [s["item"]["title"] for s in r.json()]

    assert similar("Le pont de MANGASOAVINA est coupé depuis ce matin") == [
        "Le pont de Mangasoavina serait fermé jusqu'à lundi"
    ]
    assert similar("Le pont") == []
    assert similar("Coupure d'électricité à Toamasina") == []
    assert (
        as_user("mallory")
        .get(f"/api/v1/workspaces/{ws}/items/similar", params={"q": "pont Mangasoavina"})
        .status_code
        == 404
    )
