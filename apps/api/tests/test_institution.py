"""The institution portal: sealing a PDF, the number series, « Alerte faux », declared channels."""

import io

import pytest
from fpdf import FPDF
from pypdf import PdfReader

from app.core import storage
from app.core.config import get_settings
from app.modules import institution
from tests.test_verification import REQUEST, _admin
from tests.test_workspaces import _workspace

OBJECTS: dict[str, bytes] = {}
TEXT = (
    "COMMUNIQUÉ N° 2026-041. Le Ministère de démo informe les parents d'élèves qu'une campagne de "
    "vaccination gratuite aura lieu du 4 au 8 novembre 2026. Aucun paiement n'est demandé."
)
FAKE = (
    "URGENT. Le Ministère de démo informe les parents d'élèves qu'une campagne de vaccination "
    "payante, 10 000 Ar par enfant, aura lieu du 4 au 8 novembre 2026. Partagez !"
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    OBJECTS.clear()
    monkeypatch.setattr(get_settings(), "seal_secret", "test-seal-secret-that-is-long-enough")

    async def head(key):
        return {"size": len(OBJECTS[key]), "content_type": None} if key in OBJECTS else None

    async def read(key):
        return OBJECTS[key]

    monkeypatch.setattr(storage, "configured", lambda: True)
    monkeypatch.setattr(
        storage, "presign_upload", lambda key, mime, expires=600: f"https://s3.test/{key}"
    )
    monkeypatch.setattr(storage, "head", head)
    monkeypatch.setattr(storage, "read", read)


def _pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in (
        "Ministere de demo",
        "Communique N° 2026-041",
        "Objet : Campagne de vaccination dans les ecoles",
        "Le 28 octobre 2026",
        "Une campagne de vaccination gratuite aura lieu du 4 au 8 novembre 2026.",
    ):
        pdf.multi_cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _institution(client, name="Ministère de démo (démo)", approve=None):
    r = client.post("/api/v1/workspaces", json={"name": name, "kind": "institution"})
    assert r.status_code == 201 and r.json()["kind"] == "institution"
    ws = r.json()["id"]
    if approve:
        sent = client.put(
            f"/api/v1/workspaces/{ws}/verification", json={**REQUEST, "kind": "institution"}
        )
        assert sent.status_code == 200
        assert approve.post(f"/api/v1/platform/requests/{ws}/approve").status_code == 200
    return ws


def _upload(client, ws):
    up = client.post(
        f"/api/v1/workspaces/{ws}/files/upload-url",
        json={"filename": "c.pdf", "mime": "application/pdf", "size_bytes": 2000},
    ).json()
    OBJECTS[f"ws/{ws}/{up['file_id']}/c.pdf"] = _pdf()
    return up["file_id"]


def test_the_pdf_is_read_sealed_and_returned_stamped(as_user, make_token, client):
    alice = as_user("alice")
    admin = _admin(as_user, make_token)
    ws = _institution(alice, approve=admin)
    base = f"/api/v1/workspaces/{ws}/institution"
    draft = alice.post(f"{base}/read", json={"file_id": _upload(alice, ws)}).json()
    assert draft["number"] == "2026-041" and draft["issued_on"] == "2026-10-28"
    assert draft["title"].startswith("Campagne de vaccination")
    assert draft["sequence"]["status"] == "ok"

    body = {
        "file_id": draft["file_id"],
        "number": None,
        "issued_on": "2026-10-28",
        "title": draft["title"],
        "text": TEXT,
    }
    done = alice.post(f"{base}/communiques", json=body)
    assert done.status_code == 201
    sealed = done.json()
    # No number given: the series starts at 2026-001; the entry counts as verified (issuer-signed).
    assert sealed["communique"]["number"] == "2026-001"
    assert sealed["communique"]["confirmed"] and sealed["communique"]["sealed"]
    assert sealed["seal"]["public"]

    pdf = alice.get(f"{base}/communiques/{sealed['communique']['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(pdf.content))
    assert "vaccination" in reader.pages[0].extract_text().lower()
    assert "Scellé par" in reader.pages[0].extract_text()

    # The phones get the key; revoking it moves it to the revoked list.
    keys = client.get("/api/v1/public/seal-keys").json()
    key = next(k for k in keys["keys"] if k["issuer"] == "Ministère de démo (démo)")
    assert key["key_id"] == sealed["seal"]["sealed"]["key_id"]
    assert (
        alice.post(f"/api/v1/workspaces/{ws}/registry/keys/{key['key_id']}/revoke").status_code
        == 200
    )
    keys = client.get("/api/v1/public/seal-keys").json()
    assert key["key_id"] in [k["key_id"] for k in keys["revoked"]]


def test_the_number_must_follow_the_series(as_user):
    alice = as_user("alice")
    ws = _institution(alice)
    base = f"/api/v1/workspaces/{ws}/institution"

    def publish(number, day):
        return alice.post(
            f"{base}/communiques",
            json={"number": number, "issued_on": day, "title": "Un communiqué", "text": TEXT},
        )

    assert publish("2026-045", "2026-10-20").status_code == 201
    assert publish("2026-050", "2026-10-25").status_code == 201
    # N° 048 dated after N° 050: out of order. A repeat and a foreign format are refused too.
    late = publish("2026-048", "2026-10-30")
    assert late.status_code == 409 and late.json()["error"]["code"] == "inconsistent_number"
    assert publish("2026-050", "2026-10-26").json()["error"]["code"] == "duplicate_number"
    assert publish("118/MEN", "2026-10-27").json()["error"]["code"] == "inconsistent_number"
    seq = alice.post(f"{base}/sequence", json={"issued_on": "2026-10-28"}).json()
    assert seq["status"] == "assigned" and seq["number"] == "2026-051"
    # A bare newsroom has no portal.
    assert (
        as_user("bob")
        .get(f"/api/v1/workspaces/{_workspace(as_user('bob'))}/institution")
        .status_code
        == 404
    )


def test_a_fake_using_the_name_alerts_the_press_office_who_denies_it(as_user, make_token):
    alice, bob = as_user("alice"), as_user("bob")
    admin = _admin(as_user, make_token)
    ws = _institution(alice, approve=admin)
    base = f"/api/v1/workspaces/{ws}/institution"
    original = alice.post(
        f"{base}/communiques",
        json={"issued_on": "2026-10-28", "title": "Campagne de vaccination", "text": TEXT},
    ).json()["communique"]
    desk = _workspace(bob)
    # Any newsroom's check of the text reaches the institution.
    found = bob.post(f"/api/v1/workspaces/{desk}/registry/match", json={"text": FAKE}).json()
    assert found["status"] == "modified"
    bob.post(f"/api/v1/workspaces/{desk}/registry/match", json={"text": FAKE})
    open_alerts = alice.get(f"{base}/alerts").json()
    assert len(open_alerts) == 1 and open_alerts[0]["count"] == 2
    assert (
        open_alerts[0]["status"] == "modified"
        and open_alerts[0]["original"]["id"] == original["id"]
    )
    assert "desk" == open_alerts[0]["channel"]

    denial = alice.post(
        f"{base}/communiques",
        json={
            "issued_on": "2026-10-29",
            "title": "Démenti : la vaccination est gratuite",
            "text": "DÉMENTI. Le Ministère de démo dément le message qui circule : la vaccination est gratuite.",
            "denies": open_alerts[0]["id"],
        },
    )
    assert denial.status_code == 201
    assert alice.get(f"{base}/alerts").json() == []
    done = alice.get(f"{base}/alerts", params={"state": "all"}).json()
    assert done[0]["denial"]["id"] == denial.json()["communique"]["id"]
    # An authentic copy of the original raises nothing.
    bob.post(f"/api/v1/workspaces/{desk}/registry/match", json={"text": TEXT})
    assert alice.get(f"{base}/alerts").json() == []


def test_declared_channels_feed_the_annuaire_once_verified(as_user, make_token):
    alice, bob = as_user("alice"), as_user("bob")
    admin = _admin(as_user, make_token)
    ws = _institution(alice)
    base = f"/api/v1/workspaces/{ws}/institution"
    profile = {
        "pages": ["https://www.facebook.com/ministere.demo.officiel"],
        "phones": ["034 99 111 22"],
        "topics": ["santé"],
        "officer": {
            "name": "Hanta Rakoto (démo)",
            "role": "Chargée de communication",
            "phone": "034 00 000 01",
        },
    }
    out = alice.put(base, json=profile).json()
    assert out["pages"][0]["display"] == "facebook.com/ministere.demo.officiel"
    assert out["phones"][0]["url"] == "+261349911122" and out["officer"]["role"]

    desk = _workspace(bob)
    names = lambda: [c["name"] for c in bob.get(f"/api/v1/workspaces/{desk}/contacts").json()]
    assert names() == []  # not verified yet: nothing leaves
    alice.put(f"/api/v1/workspaces/{ws}/verification", json={**REQUEST, "kind": "institution"})
    admin.post(f"/api/v1/platform/requests/{ws}/approve")
    contacts = bob.get(f"/api/v1/workspaces/{desk}/contacts").json()
    assert {c["kind"] for c in contacts} == {"institution", "officer"}
    assert all(
        c["verified_at"] and c["stats"]["declared_by"] == "Ministère de démo (démo)"
        for c in contacts
    )
    # « Page officielle ? » and « Numéro officiel ? » read them.
    gestures = bob.post(
        f"/api/v1/workspaces/{desk}/gestures",
        json={
            "text": "Appelez le 034 99 111 22 ou écrivez sur facebook.com/ministere.demo.officiel"
        },
    ).json()
    kinds = {(g["kind"], g["status"]) for g in gestures}
    assert ("official_page", "declared") in kinds and ("number", "declared") in kinds


def test_the_demo_reset_seeds_one_fictional_institution(as_user, make_token):
    alice = as_user("alice")
    ws = _workspace(alice)
    assert alice.post(f"/api/v1/workspaces/{ws}/demo/reset").status_code == 200
    me = alice.get("/api/v1/me").json()
    demo = [m for m in me["memberships"] if m["kind"] == "institution"]
    assert [m["name"] for m in demo] == ["Ministère de démo (démo)"]
    base = f"/api/v1/workspaces/{demo[0]['workspace_id']}/institution"
    assert len(alice.get(f"{base}/communiques").json()) == 1
    assert len(alice.get(f"{base}/alerts").json()) == 1
    alice.post(f"/api/v1/workspaces/{ws}/demo/reset")
    assert (
        len(
            [m for m in alice.get("/api/v1/me").json()["memberships"] if m["kind"] == "institution"]
        )
        == 1
    )
    assert institution.DEMO_NAME.endswith("(démo)")
