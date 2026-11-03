"""The dossiers list: cursor pages, the order of each tab, server counts, search and assignee."""

from tests.test_workspaces import _workspace


def _claim(c, ws, title, seen, **data):
    r = c.post(
        f"/api/v1/workspaces/{ws}/items",
        json={"title": title, "type": "claim", "data": {"first_seen_at": seen, **data}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _pages(c, ws, **params):
    """Every page of the list, following `next` to the end."""
    out, after = [], None
    for _ in range(50):
        query = {"type": "claim", **params, **({"after": after} if after else {})}
        r = c.get(f"/api/v1/workspaces/{ws}/items", params=query)
        assert r.status_code == 200, r.text
        page = r.json()
        out.append(page)
        after = page["next"]
        if after is None:
            return out
    raise AssertionError("the cursor never ended")


def test_cursor_pages_cover_every_dossier_once_in_both_orders(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    made = [
        _claim(alice, ws, f"Rumeur {i}", f"2026-10-{i + 1:02d}T10:00:00+03:00") for i in range(7)
    ]
    # Two dossiers first seen at the same moment: the id breaks the tie, none is lost.
    made.append(_claim(alice, ws, "Jumelle", "2026-10-04T10:00:00+03:00"))
    ids = {m["id"] for m in made}

    newest = _pages(alice, ws, order="newest", limit=3)
    assert [len(p["items"]) for p in newest] == [3, 3, 2]
    seq = [i["id"] for p in newest for i in p["items"]]
    assert len(seq) == len(set(seq)) and set(seq) == ids
    assert all(p["total"] == 8 for p in newest)
    assert newest[0]["items"][0]["title"] == "Rumeur 6"

    oldest = _pages(alice, ws, order="oldest", limit=3)
    seq_old = [i["id"] for p in oldest for i in p["items"]]
    assert seq_old == list(reversed(seq))
    assert oldest[0]["items"][0]["title"] == "Rumeur 0"


def test_a_page_of_exactly_the_limit_has_no_next(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    for i in range(3):
        _claim(alice, ws, f"R{i}", f"2026-10-0{i + 1}T10:00:00+03:00")
    pages = _pages(alice, ws, order="newest", limit=3)
    assert len(pages) == 1 and pages[0]["next"] is None


def test_an_unreadable_first_seen_falls_back_to_creation(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    _claim(alice, ws, "Date cassée", "hier soir vers 20 h")
    _claim(alice, ws, "Très ancienne", "2001-01-01T00:00:00+03:00")
    titles = [i["title"] for p in _pages(alice, ws, order="oldest") for i in p["items"]]
    assert titles == ["Très ancienne", "Date cassée"]


def test_tabs_filter_and_count_on_the_server(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    _claim(alice, ws, "À traiter", "2026-10-01T10:00:00+03:00")
    _claim(alice, ws, "Suggestion", "2026-10-02T10:00:00+03:00", verdict_suggested="false")
    _claim(alice, ws, "Vérifié", "2026-10-03T10:00:00+03:00", verdict="true")
    _claim(
        alice,
        ws,
        "Vérifié aussi",
        "2026-10-04T10:00:00+03:00",
        verdict="false",
        verdict_suggested="true",
    )
    _claim(alice, ws, "Mot inconnu", "2026-10-05T10:00:00+03:00", verdict="peut-être")

    def page(tab, order="newest"):
        return alice.get(
            f"/api/v1/workspaces/{ws}/items", params={"type": "claim", "tab": tab, "order": order}
        ).json()

    counts = {"all": 5, "todo": 2, "confirm": 1, "done": 2}
    for tab, expected in counts.items():
        p = page(tab)
        assert p["counts"] == counts
        assert p["total"] == expected
    assert [i["title"] for i in page("todo", "oldest")["items"]] == ["À traiter", "Mot inconnu"]
    assert [i["title"] for i in page("confirm")["items"]] == ["Suggestion"]
    assert [i["title"] for i in page("done")["items"]] == ["Vérifié aussi", "Vérifié"]
    # Without `tab`, no counts are computed.
    plain = alice.get(f"/api/v1/workspaces/{ws}/items", params={"type": "claim"}).json()
    assert plain["counts"] is None and plain["next"] is None


def test_search_reads_ref_title_and_tags_and_escapes_wildcards(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    a = _claim(alice, ws, "Coupure à 100% demain", "2026-10-01T10:00:00+03:00")
    alice.patch(f"/api/v1/workspaces/{ws}/items/{a['id']}", json={"tags": ["energie"]})
    _claim(alice, ws, "Le riz double", "2026-10-02T10:00:00+03:00")

    def found(q):
        r = alice.get(
            f"/api/v1/workspaces/{ws}/items",
            params={"type": "claim", "q": q, "tab": "all", "order": "newest"},
        )
        return [i["title"] for i in r.json()["items"]]

    assert found(a["data"]["ref"].lower()) == ["Coupure à 100% demain"]
    assert found("ENERGIE") == ["Coupure à 100% demain"]
    assert found("100%") == ["Coupure à 100% demain"]
    assert found("%") == ["Coupure à 100% demain"]
    assert found("_") == []


def test_assignee_filter(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    me = alice.get("/api/v1/me").json()["id"]
    _claim(alice, ws, "À moi", "2026-10-01T10:00:00+03:00", assignee_id=me)
    _claim(alice, ws, "À personne", "2026-10-02T10:00:00+03:00")
    _claim(alice, ws, "À Bob", "2026-10-03T10:00:00+03:00", assignee_id="bob-id")

    def titles(who):
        r = alice.get(
            f"/api/v1/workspaces/{ws}/items",
            params={"type": "claim", "assignee": who, "tab": "all", "order": "newest"},
        )
        return [i["title"] for i in r.json()["items"]]

    assert titles("me") == ["À moi"]
    assert titles("none") == ["À personne"]
    assert titles("bob-id") == ["À Bob"]


def test_a_bad_cursor_is_a_clear_422(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    for bad in ("not-base64!!", "aGVsbG8", "MjAyNi0xMC0wMXxub3QtYS11dWlk"):
        r = alice.get(
            f"/api/v1/workspaces/{ws}/items",
            params={"type": "claim", "order": "newest", "after": bad},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "bad_cursor"
