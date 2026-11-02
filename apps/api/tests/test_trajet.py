import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.core.models import Item
from app.modules import trajet
from tests.test_workspaces import _workspace


def _claim(c, ws, **data):
    r = c.post(
        f"/api/v1/workspaces/{ws}/items",
        json={"title": "72 heures de délestage à Antananarivo", "data": data},
    )
    assert r.status_code == 201
    return r.json()["id"]


def _stop(ws, item_id, **kw):
    async def run():
        async with SessionLocal() as db:
            route = await trajet.add_stop(db, uuid.UUID(ws), uuid.UUID(item_id), **kw)
            await db.commit()
            return route.id

    return asyncio.run(run())


def test_add_stop_counts_repeats_and_gaps_follow_channel_and_region(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    base = f"/api/v1/workspaces/{ws}/items/{item}"
    _stop(ws, item, side="rumour", channel="facebook", place="Page « Tana Flash » (démo)")
    _stop(ws, item, side="rumour", channel="radio", place="Radio RDJ", location=None)
    first = _stop(ws, item, side="rumour", channel="sms", place="SMS Toliara")
    again = _stop(ws, item, side="rumour", channel="sms", place="SMS Toliara")
    assert first == again  # three SMS from one region are one stop « × n »
    out = alice.get(base + "/trajet").json()
    assert [s["channel"] for s in out["rumour"]] == ["facebook", "radio", "sms"]
    sms = out["rumour"][2]
    assert sms["proof"]["count"] == 2
    assert sms["location"]["region"] == "Atsimo-Andrefana"  # gazetteer from the place's words
    assert len(out["gaps"]) == 3 and out["covered"] == 0
    assert out["summary"] == "La rumeur est passée par 3 routes ; la vérité n'en a repris aucune."

    # A correction on the radio of another region does not cover it; a national one does.
    _stop(ws, item, side="truth", channel="sms", place="SMS Toamasina")
    _stop(ws, item, side="truth", channel="radio", place="Flash national", location={})
    out = alice.get(base + "/trajet").json()
    assert {g["channel"] for g in out["gaps"]} == {"facebook", "sms"}
    assert out["summary"] == "La rumeur est passée par 3 routes ; la vérité en a repris 1."
    assert [s["status"] for s in out["truth"]] == ["sent", "sent"]


def test_origin_and_first_seen_make_the_first_stop_when_none_is_noted(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    seen = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    item = _claim(alice, ws, origin="whatsapp", first_seen_at=seen)
    out = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/trajet").json()
    assert out["rumour"][0]["derived"] is True and out["rumour"][0]["channel"] == "whatsapp"
    assert out["summary"].startswith("La rumeur est passée par 1 route ;")
    assert as_user("bob").get(f"/api/v1/workspaces/{ws}/items/{item}/trajet").status_code == 404


def test_hand_entered_route_needs_a_past_time_and_a_published_verdict_for_truth(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}/routes"
    at = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    row = {"side": "rumour", "channel": "tiktok", "place": "Compte TikTok", "note": "Vu ce matin"}
    assert alice.post(path, json={**row, "at": at}).status_code == 201
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    assert alice.post(path, json={**row, "at": future}).status_code == 422
    assert alice.post(path, json={**row, "side": "truth", "at": at}).status_code == 409
    assert [r["status"] for r in alice.get(path).json()] == ["reported"]


def test_public_trajet_shows_the_truth_side_of_published_verdicts_only(as_user, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    _stop(ws, item, side="rumour", channel="facebook", place="Page")
    assert client.get(f"/api/v1/public/verdicts/{item}/trajet").status_code == 404
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    alice.post(
        f"/api/v1/workspaces/{ws}/items/{item}/sign",
        json={
            "verdict": "false",
            "reason": "Le communiqué original dit 4 heures.",
            "publish": True,
        },
    )
    out = client.get(f"/api/v1/public/verdicts/{item}/trajet").json()
    assert out["rumour_routes"] == 1
    assert all("proof" not in s for s in out["truth"])


def test_demo_seed_draws_the_pitch_rumours_road(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").status_code == 200

    async def find():
        async with SessionLocal() as db:
            from sqlalchemy import select

            return await db.scalar(select(Item).where(Item.data["ref"].astext == "FAN-0145"))

    item = asyncio.run(find())
    out = alice.get(f"/api/v1/workspaces/{ws}/items/{item.id}/trajet").json()
    assert [s["channel"] for s in out["rumour"]] == ["facebook", "whatsapp", "radio", "sms"]
    assert out["rumour"][3]["proof"]["count"] == 3
    first = datetime.fromisoformat(out["rumour"][0]["at"])
    assert first == datetime.fromisoformat(item.data["first_seen_at"])
    # Running the seed again replaces the stops instead of doubling them.
    assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").status_code == 200
    item = asyncio.run(find())
    assert len(alice.get(f"/api/v1/workspaces/{ws}/items/{item.id}/trajet").json()["rumour"]) == 4


def test_public_trajet_hides_a_published_claim_without_a_confirmed_verdict(as_user, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    item = _claim(alice, ws, verdict_suggested="false")

    async def force_published():
        async with SessionLocal() as db:
            row = await db.get(Item, uuid.UUID(item))
            row.status = "published"  # as an older route could leave it, with no verdict
            await db.commit()

    asyncio.run(force_published())
    assert client.get(f"/api/v1/public/verdicts/{item}/trajet").status_code == 404
