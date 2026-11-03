import io

import pytest
from PIL import Image

from app.core import storage
from app.modules.profile import normalise_phone

OBJECTS: dict[str, bytes] = {}


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    OBJECTS.clear()

    async def head(key):
        return {"size": len(OBJECTS[key]), "content_type": None} if key in OBJECTS else None

    async def read(key):
        return OBJECTS[key]

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
    monkeypatch.setattr(storage, "read", read)
    monkeypatch.setattr(storage, "delete", delete)


def _img(fmt="JPEG", size=(900, 580), colour=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, fmt)
    return buf.getvalue()


def _card(client, data=None, mime="image/jpeg", name="carte.jpg"):
    data = _img() if data is None else data
    r = client.post(
        "/api/v1/me/press-card/upload-url",
        json={"filename": name, "mime": mime, "size_bytes": len(data)},
    )
    assert r.status_code == 201, r.text
    key = r.json()["card_key"]
    OBJECTS[key] = data
    return key


def _profile(key, **over):
    return {
        "phone": "+261 34 00 000 00",
        "outlet": "Radio Checky",
        "card_number": "MG-2026-014",
        "card_key": key,
        "card_filename": "carte.jpg",
        **over,
    }


def test_phone_is_normalised():
    assert normalise_phone("+261 34 00 000 00") == "+261340000000"
    assert normalise_phone("034 00 000 00") == "034000000 0".replace(" ", "")
    for bad in ("abc", "12", "+261", "034-00-000-00-00-00-00-00-00"):
        with pytest.raises(ValueError):
            normalise_phone(bad)


def test_profile_needs_a_token(client):
    assert client.put("/api/v1/me/profile", json={}).status_code == 401


def test_signup_profile_with_card(as_user):
    alice = as_user("alice")
    key = _card(alice)
    assert key.startswith("press-cards/alice/")
    r = alice.put("/api/v1/me/profile", json=_profile(key))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phone"] == "+261340000000"
    assert body["outlet"] == "Radio Checky"
    assert body["card_url"].startswith("https://s3.test/press-cards/alice/")
    assert alice.get("/api/v1/me/profile").json()["card_number"] == "MG-2026-014"


def test_card_must_have_arrived(as_user):
    alice = as_user("alice")
    key = _card(alice)
    OBJECTS.clear()
    r = alice.put("/api/v1/me/profile", json=_profile(key))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "card_missing"


def test_cannot_use_someone_elses_card(as_user):
    bob_key = _card(as_user("bob"))
    r = as_user("alice").put("/api/v1/me/profile", json=_profile(bob_key))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_card"


def test_only_photos_and_pdfs_under_8mb(as_user):
    alice = as_user("alice")
    r = alice.post(
        "/api/v1/me/press-card/upload-url",
        json={"filename": "x.exe", "mime": "application/x-msdownload", "size_bytes": 10},
    )
    assert r.status_code == 415
    r = alice.post(
        "/api/v1/me/press-card/upload-url",
        json={"filename": "x.jpg", "mime": "image/jpeg", "size_bytes": 9 * 1024 * 1024},
    )
    assert r.status_code == 413


def test_replacing_the_card_removes_the_old_one(as_user):
    alice = as_user("alice")
    first = _card(alice)
    alice.put("/api/v1/me/profile", json=_profile(first))
    second = _card(alice, _img(colour=(10, 90, 200)), name="carte2.jpg")
    assert alice.put("/api/v1/me/profile", json=_profile(second)).status_code == 200
    assert first not in OBJECTS and second in OBJECTS


def test_bad_phone_is_422(as_user):
    alice = as_user("alice")
    r = alice.put("/api/v1/me/profile", json=_profile(_card(alice), phone="hello"))
    assert r.status_code == 422


def test_only_the_checky_team_reads_another_profile(as_user, monkeypatch):
    from app.core.config import get_settings

    bob = as_user("bob")
    bob.put("/api/v1/me/profile", json=_profile(_card(bob)))
    assert as_user("alice").get("/api/v1/platform/profiles/bob").status_code == 404
    monkeypatch.setattr(get_settings(), "platform_admins", "alice")
    r = as_user("alice").get("/api/v1/platform/profiles/bob")
    assert r.status_code == 200 and r.json()["card_url"].endswith("?get")
    assert as_user("alice").get("/api/v1/platform/profiles/nobody").status_code == 404


def _rejected(as_user, data, mime="image/jpeg", name="carte.jpg", status=422, code="invalid_card"):
    alice = as_user("alice")
    key = _card(alice, data, mime, name)
    r = alice.put("/api/v1/me/profile", json=_profile(key))
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code
    assert key not in OBJECTS  # a refused file is not kept
    assert alice.get("/api/v1/me/profile").status_code == 404


def test_renamed_garbage_is_refused(as_user):
    _rejected(as_user, b"MZ not an image at all")


def test_truncated_image_is_refused(as_user):
    _rejected(as_user, _img()[:300])


def test_png_sent_as_jpeg_is_refused(as_user):
    _rejected(as_user, _img("PNG"))


def test_thumbnail_is_refused(as_user):
    _rejected(as_user, _img(size=(64, 64)))


def test_fake_pdf_is_refused(as_user):
    _rejected(as_user, b"<html>nope</html>", "application/pdf", "carte.pdf")


def test_real_pdf_is_accepted(as_user):
    alice = as_user("alice")
    key = _card(
        alice, b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", "application/pdf", "c.pdf"
    )
    assert (
        alice.put("/api/v1/me/profile", json=_profile(key, card_filename="c.pdf")).status_code
        == 200
    )


def test_same_card_cannot_back_two_accounts(as_user):
    data = _img()
    alice, bob = as_user("alice"), as_user("bob")
    assert alice.put("/api/v1/me/profile", json=_profile(_card(alice, data))).status_code == 200
    r = bob.put("/api/v1/me/profile", json=_profile(_card(bob, data)))
    assert r.status_code == 409 and r.json()["error"]["code"] == "card_already_used"
    # The owner can send the same card again.
    assert alice.put("/api/v1/me/profile", json=_profile(_card(alice, data))).status_code == 200
