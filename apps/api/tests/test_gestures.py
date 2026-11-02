import asyncio
import uuid
from datetime import UTC, datetime

from app.core import countries
from app.core.db import SessionLocal
from app.core.models import Communique, Contact, Item
from tests.test_workspaces import _workspace

NOW = datetime(2026, 11, 2, 8, tzinfo=UTC)


async def _add(*rows):
    async with SessionLocal() as db:
        for row in rows:
            db.add(row)
        await db.commit()


def _seed(*rows):
    asyncio.run(_add(*rows))


def contact(ws, **fields):
    base = {
        "workspace_id": uuid.UUID(ws),
        "created_by": "alice",
        "kind": "institution",
        "name": "JIRAMA (démo)",
        "institution": "JIRAMA",
        "official_pages": [],
        "stats": {},
        "location": {},
        "topics": [],
        "languages": ["fr"],
    }
    return Contact(**{**base, **fields})


def jirama(ws, verified=True):
    return contact(
        ws,
        phone="+261 34 00 000 01",
        website="https://www.jirama.mg",
        official_pages=[
            {
                "kind": "facebook",
                "url": "https://www.facebook.com/jirama.officiel",
                "verified": verified,
            },
            {"kind": "phone", "url": "tel:+261202200000", "verified": verified},
        ],
        verified_at=NOW if verified else None,
        verified_by="alice" if verified else None,
    )


def _facts(c, ws, text=None, url=None, kind=None):
    r = c.post(f"/api/v1/workspaces/{ws}/gestures", json={"text": text, "url": url})
    assert r.status_code == 200, r.text
    return [f for f in r.json() if kind is None or f["kind"] == kind]


def test_numbers_in_a_text_are_read_without_years_or_amounts():
    found = countries.phones_in(
        "Appelez le 034 12 345 67, le +261 34 12 345 67, le 034.12.345.67 ou le 020 22 123 45"
    )
    assert found == [("034 12 345 67", "+261341234567"), ("020 22 123 45", "+261202212345")]
    assert countries.phones_in("N° 2026-118 du 03/11/2026 : 1 200 000 Ar, hausse de 40 %") == []
    assert countries.phones_in("Appelez le +33 6 12 34 56 78") == [
        ("+33 6 12 34 56 78", "+33612345678")
    ]
    assert countries.display("+261340000001") == "+261 34 00 000 01"


def test_official_page_declared_other_page_and_not_declared(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    _seed(jirama(ws))
    found = _facts(alice, ws, url="https://m.facebook.com/Jirama.Officiel/posts/12")
    assert found[0]["status"] == "declared"
    assert found[0]["text"].startswith(
        "Page déclarée officielle par JIRAMA, vérifiée le 2 novembre"
    )
    assert found[0]["proof"]["contact_id"]
    fake = _facts(alice, ws, url="https://facebook.com/JiramaOfficielleMada")[0]
    assert fake["status"] == "other_page" and "facebook.com/jirama.officiel" in fake["text"]
    site = _facts(alice, ws, url="https://jirama-mg.info/delestage")[0]
    assert site["status"] == "other_page" and "jirama.mg" in site["text"]
    assert _facts(alice, ws, url="https://facebook.com/cuisine.mada")[0]["status"] == (
        "not_declared"
    )
    # A website that is nobody's says nothing; a page in the text is read too.
    assert _facts(alice, ws, url="https://example.org/article") == []
    bare = _facts(alice, ws, "Suivez facebook.com/jirama.officiel pour les coupures")
    assert [f["status"] for f in bare] == ["declared"]
    assert _facts(alice, ws, url="https://www.jirama.mg/coupures")[0]["status"] == "declared"
    empty = alice.post(f"/api/v1/workspaces/{ws}/gestures", json={"text": "  "})
    assert empty.status_code == 422


def test_unverified_pages_are_said_to_be_unverified(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    _seed(jirama(ws, verified=False))
    found = _facts(alice, ws, url="https://www.facebook.com/jirama.officiel")[0]
    assert found["status"] == "declared_unverified"
    assert "pas encore vérifiée" in found["text"]
    # Another newsroom does not read a contact that was not shared.
    other = _workspace(bob)
    assert _facts(bob, other, url="https://www.facebook.com/jirama.officiel")[0]["status"] == (
        "not_declared"
    )


def test_numbers_say_whose_they_are_and_never_scam(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    _seed(jirama(ws))
    numbers = _facts(
        alice,
        ws,
        "La JIRAMA informe : pour être remboursé, appelez le 034 00 000 99 ou le 020 22 000 00.",
        kind="number",
    )
    assert [n["status"] for n in numbers] == ["not_declared", "declared"]
    assert numbers[0]["text"] == "Ce numéro n'est pas un numéro déclaré de JIRAMA."
    assert numbers[0]["subject"] == "+261 34 00 000 99"
    assert "+261 34 00 000 01" in numbers[0]["proof"]["declared"]
    assert numbers[1]["text"].startswith("Ce numéro est celui de JIRAMA")
    loose = _facts(alice, ws, "Gagnez un iPhone : 034 11 222 33", kind="number")
    assert loose[0]["status"] == "unknown" and loose[0]["text"] == "Numéro absent de l'Annuaire."
    every = _facts(alice, ws, "La JIRAMA informe : appelez le 034 00 000 99.")
    assert not any("arnaque" in f["text"].lower() for f in every)


def test_attribution_against_the_registry(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    text = (
        "COMMUNIQUÉ N° 2026-118. La JIRAMA informe ses abonnés d'Antananarivo qu'un délestage de 4 "
        "heures par jour et par quartier sera appliqué du 3 au 9 novembre 2026."
    )
    _seed(
        Communique(
            workspace_id=uuid.UUID(ws),
            added_by="alice",
            issuer="JIRAMA",
            number="2026-118",
            issued_on="2026-11-01",
            title="Délestage (démo)",
            text=text,
            status="original",
            confirmed_by=[],
            location={},
        )
    )
    same = _facts(alice, ws, text, kind="attribution")
    assert same[0]["status"] == "found" and same[0]["proof"]["number"] == "2026-118"
    other = _facts(
        alice,
        ws,
        "Selon la JIRAMA, l'électricité sera gratuite à Noël pour tous.",
        kind="attribution",
    )
    assert other[0]["status"] == "not_found"
    assert other[0]["text"] == (
        "Aucun communiqué de JIRAMA au registre ne dit cela (le registre peut être incomplet)."
    )
    nothing = _facts(
        alice, ws, "Selon le BNGRC, un cyclone arrive demain sur Toamasina.", kind="attribution"
    )
    assert nothing[0]["status"] == "no_reference"
    # A name without a statement is not an attribution.
    assert _facts(alice, ws, "Photo de la JIRAMA", kind="attribution") == []


def test_press_article_against_the_outlets_feed(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    _seed(
        contact(
            ws,
            kind="media",
            name="L'Écho du Matin (démo)",
            institution="",
            website="https://echo-du-matin.example",
        ),
        Item(
            workspace_id=uuid.UUID(ws),
            author_id="press",
            type="press",
            title="Délestage : la JIRAMA annonce 4 heures par jour à Antananarivo",
            body="",
            tags=[],
            data={
                "outlet": "L'Écho du Matin",
                "link": "https://echo-du-matin.example/delestage-4h",
                "published_at": "2026-11-01T06:00:00+03:00",
            },
        ),
    )
    real = _facts(
        alice,
        ws,
        "L'Écho du Matin — Délestage : la JIRAMA annonce 4 heures par jour à Antananarivo",
        kind="press_article",
    )[0]
    assert real["status"] == "published"
    assert real["text"] == "Publié par L'Écho du Matin le 1er novembre 2026."
    assert real["proof"]["url"] == "https://echo-du-matin.example/delestage-4h"
    fake = _facts(
        alice,
        ws,
        "L'Écho du Matin\nLe gouvernement offre l'électricité gratuite à tous les foyers",
        kind="press_article",
    )[0]
    assert fake["status"] == "not_found"
    assert fake["text"] == (
        "Titre introuvable dans le flux de L'Écho du Matin depuis le 1er novembre 2026."
    )
    on_site = _facts(alice, ws, url="https://echo-du-matin.example/une", kind="press_article")
    assert [f["status"] for f in on_site] == ["published"]
