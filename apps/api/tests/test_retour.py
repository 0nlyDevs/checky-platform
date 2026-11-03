"""Stop 5 « Retour »: the journalist's voice note, the carnet and the attestation as PDFs, and the
verification number on the public verdict."""

import asyncio
import io
import json
import uuid

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select

from app.core import attest, storage
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import Activity, File, Job, Source
from tests.ref_fixture import set_ref
from tests.test_workspaces import _verify, _workspace

OBJECTS: dict[str, bytes] = {}
REASON = "Le communiqué N° 2026-118 de la JIRAMA prévoit 4 heures par jour, pas 72 heures."
TITLE = "72 heures de délestage dès demain sur tout Antananarivo, selon la JIRAMA"


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    OBJECTS.clear()

    async def head(key):
        return {"size": len(OBJECTS[key]), "content_type": None} if key in OBJECTS else None

    async def delete(key):
        OBJECTS.pop(key, None)

    monkeypatch.setattr(storage, "configured", lambda: True)
    monkeypatch.setattr(
        storage, "presign_upload", lambda key, mime, expires=600: f"https://s3.test/{key}?put"
    )
    monkeypatch.setattr(
        storage,
        "presign_download",
        lambda key, filename=None, expires=3600: f"https://s3.test/{key}?get",
    )
    monkeypatch.setattr(storage, "head", head)
    monkeypatch.setattr(storage, "delete", delete)


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "seal_secret", "test-seal-secret-that-is-long-enough")
    monkeypatch.setattr(get_settings(), "public_web_url", "https://checky.example")


def _dossier(alice, ws, *, publish=True, sign=True):
    alice.patch(f"/api/v1/workspaces/{ws}", json={"is_public": True})
    _verify(ws)
    item = alice.post(f"/api/v1/workspaces/{ws}/items", json={"title": TITLE}).json()["id"]
    set_ref(item, "FAN-0145")
    if sign:
        r = alice.post(
            f"/api/v1/workspaces/{ws}/items/{item}/sign",
            json={"verdict": "false", "reason": REASON, "publish": publish},
        )
        assert r.status_code == 200, r.text
    return item


def _recorded(alice, ws, data=b"OggS fake opus voice", mime="audio/webm"):
    """The browser's upload of a recording: an upload URL, then the PUT to storage."""
    r = alice.post(
        f"/api/v1/workspaces/{ws}/files/upload-url",
        json={"filename": "dementi-mg.webm", "mime": mime, "size_bytes": len(data)},
    )
    assert r.status_code == 201, r.text
    up = r.json()
    OBJECTS[up["upload_url"].removeprefix("https://s3.test/").removesuffix("?put")] = data
    return up["file_id"]


def _count(model, *where) -> int:
    async def go():
        async with SessionLocal() as db:
            return await db.scalar(select(func.count()).select_from(model).where(*where))

    return asyncio.run(go())


def test_voice_note_is_attached_never_transcribed_and_played_publicly(as_user, client):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _dossier(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}/voice-note"
    file_id = _recorded(alice, ws)

    r = alice.put(path, json={"file_id": file_id, "seconds": 27.4})
    assert r.status_code == 200, r.text
    note = r.json()
    assert note["language"] == "mg" and note["seconds"] == 27.4
    assert note["url"].endswith("?get") and note["mime"] == "audio/webm"
    # Never a source, never a job: spoken Malagasy is not machine-transcribed.
    assert _count(Source) == 0
    assert _count(Job) == 0
    assert alice.get(path).json()["file_id"] == file_id
    lines = [
        e["text"]
        for e in alice.get(f"/api/v1/workspaces/{ws}/items/{item}/carnet").json()["entries"]
    ]
    assert "Note vocale en malgache enregistrée (27 s)" in lines

    # Server-owned: a PATCH cannot point the dossier at another file.
    r = alice.patch(f"/api/v1/workspaces/{ws}/items/{item}", json={"data": {"voice_note": {}}})
    assert r.status_code == 422

    public = client.get(f"/api/v1/public/verdicts/{item}").json()
    assert public["voice_note"]["url"].endswith("?get")
    assert public["check_label"] == "vérification 145"
    # The archive list stays light: no presigned URL per entry.
    listed = client.get("/api/v1/public/verdicts").json()["items"][0]
    assert listed["voice_note"] is None and listed["check_label"] == "vérification 145"

    # A new take replaces the old one, whose object is deleted.
    old_keys = set(OBJECTS)
    second = _recorded(alice, ws, b"second take")
    assert alice.put(path, json={"file_id": second}).status_code == 200
    assert not (old_keys & set(OBJECTS)) and len(OBJECTS) == 1
    assert _count(File, File.id == uuid.UUID(file_id)) == 0

    assert alice.delete(path).status_code == 204
    assert OBJECTS == {}
    assert alice.get(path).status_code == 404
    assert client.get(f"/api/v1/public/verdicts/{item}").json()["voice_note"] is None


def test_voice_note_rules(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    unsigned = _dossier(alice, ws, sign=False)
    file_id = _recorded(alice, ws)
    r = alice.put(f"/api/v1/workspaces/{ws}/items/{unsigned}/voice-note", json={"file_id": file_id})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_signed"

    item = _dossier(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}/voice-note"
    # Not uploaded yet.
    up = alice.post(
        f"/api/v1/workspaces/{ws}/files/upload-url",
        json={"filename": "x.webm", "mime": "audio/webm", "size_bytes": 10},
    ).json()
    assert (
        alice.put(path, json={"file_id": up["file_id"]}).json()["error"]["code"] == "not_uploaded"
    )
    # Not audio.
    pic = _recorded(alice, ws, b"\x89PNG", "image/png")
    assert alice.put(path, json={"file_id": pic}).status_code == 415
    # Longer than 30 seconds (and a margin).
    assert alice.put(path, json={"file_id": file_id, "seconds": 90}).status_code == 422
    # A file completed as a source (and so transcribed) is never a voice note.
    used = _recorded(alice, ws, b"source audio")
    assert alice.post(f"/api/v1/workspaces/{ws}/files/{used}/complete", json={}).status_code == 201
    assert alice.put(path, json={"file_id": used}).json()["error"]["code"] == "already_completed"
    # Another newsroom's file.
    bob = as_user("bob")
    other = _workspace(bob, "Radio Bob")
    theirs = _recorded(bob, other)
    assert alice.put(path, json={"file_id": theirs}).status_code == 404
    # Outsiders get 404 on the dossier.
    assert bob.put(path, json={"file_id": theirs}).status_code == 404


def test_voice_note_goes_out_as_a_route_on_the_trajet(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"ai_enabled": False}})
    item = _dossier(alice, ws)
    base = f"/api/v1/workspaces/{ws}/items/{item}"
    body = {
        "routes": [{"channel": "whatsapp", "place": "Groupe Analakely"}],
        "formats": ["voice_note"],
    }
    assert alice.post(base + "/diffuse", json=body).json()["dropped"] == ["voice_note"]
    alice.put(base + "/voice-note", json={"file_id": _recorded(alice, ws), "seconds": 20})
    out = alice.post(base + "/diffuse", json=body).json()
    assert out["formats"] == ["voice_note"] and out["dropped"] == []
    stops = out["trajet"]["truth"]
    assert any(
        s["channel"] == "whatsapp" and "voice_note" in s["proof"].get("formats", []) for s in stops
    )


def test_carnet_exports_as_a_pdf(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _dossier(alice, ws)
    r = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/carnet.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="carnet-FAN-0145.pdf"' in r.headers["content-disposition"]
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(r.content)).pages)
    assert "Carnet de diligence" in text and "FAN-0145" in text
    assert "72 heures de délestage" in text
    assert "Verdict signé : Faux" in text and "Dossier ouvert" in text
    assert "ne dit pas que" in text  # never a statement that the claim is true


def test_attestation_is_a_one_page_sealed_pdf(as_user, secret):
    alice = as_user("alice")
    ws = _workspace(alice)
    unsigned = _dossier(alice, ws, sign=False)
    r = alice.get(f"/api/v1/workspaces/{ws}/items/{unsigned}/attestation.pdf")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_signed"

    item = _dossier(alice, ws)
    r = alice.get(f"/api/v1/workspaces/{ws}/items/{item}/attestation.pdf")
    assert r.status_code == 200, r.text
    assert 'filename="attestation-FAN-0145.pdf"' in r.headers["content-disposition"]
    pdf = PdfReader(io.BytesIO(r.content))
    assert len(pdf.pages) == 1
    text = pdf.pages[0].extract_text()
    assert "Attestation de vérification" in text and "SHA-256" in text
    assert "n'affirme jamais que" in text
    signed = json.loads(pdf.attachments["attestation.json"][0])
    assert attest.verify(signed["payload"], signed["signature"])
    assert signed["payload"]["ref"] == "FAN-0145"


def test_activity_lines_name_the_voice_note(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _dossier(alice, ws)
    path = f"/api/v1/workspaces/{ws}/items/{item}/voice-note"
    alice.put(path, json={"file_id": _recorded(alice, ws), "language": "fr"})
    alice.delete(path)
    assert _count(Activity, Activity.action == "voice_note") == 2
