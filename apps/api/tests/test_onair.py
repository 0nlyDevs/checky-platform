"""« Avant l'antenne »: a caller's claim checked against every newsroom's signed verdicts."""

import asyncio

from app.core.db import SessionLocal
from app.core.models import Item
from app.modules import onair, trajet
from tests.test_sms import (
    CLAIM,
    _claim,
    _newsroom,
    secrets,  # noqa: F401 - fixture
)

SAID = "Un auditeur dit que la JIRAMA annonce 72 heures de délestage à Antananarivo"


def ask(c, ws, text=SAID):
    r = c.post(f"/api/v1/workspaces/{ws}/avant-antenne", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_another_newsrooms_signed_verdict_comes_with_its_radio_line(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    theirs = _newsroom(bob, name="Radio du Sud")
    item = _claim(bob, theirs, CLAIM, reason="Le communiqué annonce 4 heures par jour.")
    mine = alice.post("/api/v1/workspaces", json={"name": "Matinale"}).json()["id"]
    out = ask(alice, mine)
    assert out["status"] == "signed" and out["careful_line"] is None
    v = out["signed"][0]
    assert v["id"] == item and v["verdict"] == "false" and v["newsroom"] == "Radio du Sud"
    assert v["own"] is False and v["check_label"] == "vérification 145"
    assert v["link"] == "https://checky.example/v/145"
    assert v["radio_line"].startswith("Radio du Sud a vérifié l'information selon laquelle")
    assert "Conclusion : faux. Le communiqué annonce 4 heures par jour." in v["radio_line"]
    # no Malagasy line before a speaker rereads it
    assert v["radio_line_mg"] is None and v["mg_status"] == "not_reread"

    async def reread(text):
        async with SessionLocal() as db:
            row = await db.get(Item, item)
            texts = {"radio_line_mg": text}
            row.data = {
                **row.data,
                "relu_mg": {
                    "by": "bob",
                    "at": "2026-11-03T07:00:00+03:00",
                    "digest": trajet._version(row),
                    "texts": texts,
                    "mg_hash": trajet.mg_hash(texts),
                },
            }
            await db.commit()

    asyncio.run(reread("Diso ny vaovao momba ny delestazy 72 ora (fanamarinana 145)."))
    v = ask(alice, mine)["signed"][0]
    assert v["mg_status"] == "relu" and v["radio_line_mg"].startswith("Diso ny vaovao")
    # a new explanation is another version: the reread no longer covers it
    bob.patch(f"/api/v1/workspaces/{theirs}/items/{item}", json={"data": {"reason": "Autre."}})
    assert ask(alice, mine)["signed"][0]["radio_line_mg"] is None


def test_no_signed_verdict_never_says_false(as_user):
    alice = as_user("alice")
    ws = alice.post("/api/v1/workspaces", json={"name": "Matinale"}).json()["id"]
    out = ask(alice, ws)
    assert out["status"] == "new" and out["signed"] == []
    assert out["careful_line"] == onair.CAREFUL["new"]
    assert "faux" not in out["careful_line"].lower()
    # a suggested verdict on a claim the desk follows is not a signed one
    item = _claim(alice, ws, CLAIM, status="in_progress", verdict=None, verdict_suggested="false")
    out = ask(alice, ws)
    assert out["status"] == "followed" and out["signed"] == []
    assert out["own"]["item_id"] == item and out["careful_line"] == onair.CAREFUL["followed"]


def test_own_signed_verdict_counts_even_when_the_desk_does_not_publish(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = alice.post("/api/v1/workspaces", json={"name": "Matinale"}).json()["id"]
    item = _claim(alice, ws, CLAIM, reason="Quatre heures.")
    out = ask(alice, ws)
    assert out["status"] == "signed" and out["signed"][0]["id"] == item
    assert out["signed"][0]["own"] is True
    # another desk never sees a verdict that was not made public
    other = bob.post("/api/v1/workspaces", json={"name": "Autre"}).json()["id"]
    assert ask(bob, other)["status"] == "new"
    assert (
        bob.post(f"/api/v1/workspaces/{ws}/avant-antenne", json={"text": SAID}).status_code == 404
    )


def test_fact_checkers_are_relayed_as_theirs(as_user, monkeypatch):
    from app.core import websearch

    async def fact_checks(query, k=6):
        return [
            {
                "url": "https://factuel.afp.com/delestage-72-heures",
                "title": "Non, la JIRAMA n'annonce pas 72 heures de délestage à Antananarivo",
                "snippet": "AFP Factuel : « Faux » Affirmation : 72 heures de délestage",
                "date": "2026-10-30",
            },
            {"url": "https://example.org/x", "title": "Recette du romazava", "snippet": ""},
        ]

    monkeypatch.setattr(websearch, "fact_checks", fact_checks)
    alice = as_user("alice")
    ws = alice.post("/api/v1/workspaces", json={"name": "Matinale"}).json()["id"]
    r = alice.post(f"/api/v1/workspaces/{ws}/avant-antenne/fact-checks", json={"text": SAID})
    out = r.json()
    assert out["status"] == "done" and len(out["reviews"]) == 1
    assert out["reviews"][0]["publisher"] == "AFP Factuel" and out["reviews"][0]["rating"] == "Faux"

    async def down(query, k=6):
        raise websearch.SearchUnavailable("down")

    monkeypatch.setattr(websearch, "fact_checks", down)
    r = alice.post(f"/api/v1/workspaces/{ws}/avant-antenne/fact-checks", json={"text": SAID})
    assert r.json() == {"status": "unavailable", "reviews": []}
