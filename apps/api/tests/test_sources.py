import asyncio
import io
import uuid

import httpx
import pytest
from PIL import Image
from pypdf import PdfWriter

from app.core import storage
from app.workers import ingest, queue
from tests.test_workspaces import _workspace

OBJECTS: dict[str, bytes] = {}


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    """In-memory bucket: presigned URLs are fake, `put` simulates the browser's upload."""
    OBJECTS.clear()

    async def head(key):
        return {"size": len(OBJECTS[key]), "content_type": None} if key in OBJECTS else None

    async def read(key):
        return OBJECTS[key]

    async def delete(key):
        OBJECTS.pop(key, None)

    async def write(key, body, content_type):
        OBJECTS[key] = body

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
    monkeypatch.setattr(storage, "write", write)


def _upload(client, ws, filename, mime, data, item_id=None):
    r = client.post(
        f"/api/v1/workspaces/{ws}/files/upload-url",
        json={"filename": filename, "mime": mime, "size_bytes": len(data)},
    )
    assert r.status_code == 201, r.text
    up = r.json()
    key = up["upload_url"].removeprefix("https://s3.test/").removesuffix("?put")
    OBJECTS[key] = data
    body = {"item_id": item_id} if item_id else {}
    return client.post(f"/api/v1/workspaces/{ws}/files/{up['file_id']}/complete", json=body)


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (40, 30), "red")
    exif = Image.Exif()
    exif[0x010F] = "Canon"  # Make
    exif[0x0110] = "EOS 80D"  # Model
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.add_metadata({"/Title": "Rapport INSTAT octobre"})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _claim(client, ws):
    r = client.post(f"/api/v1/workspaces/{ws}/items", json={"title": "Le prix du riz a doublé"})
    return r.json()["id"]


def test_image_upload_reads_exif_and_counts_on_the_claim(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    r = _upload(alice, ws, "photo marché.jpg", "image/jpeg", _jpeg_with_exif(), item)
    assert r.status_code == 201, r.text
    src = r.json()
    assert (src["kind"], src["status"], src["item_id"]) == ("image", "queued", item)
    assert src["file"]["download_url"].endswith("?get")
    assert (
        "/photo-march-.jpg" in src["file"]["download_url"] or "photo" in src["file"]["download_url"]
    )

    assert asyncio.run(queue.run_once()) is True
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert src["status"] == "ready"
    assert src["file"]["meta"]["exif"] == {"Make": "Canon", "Model": "EOS 80D"}
    assert len(src["file"]["sha256"]) == 64
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]["source_count"] == 1


def test_same_image_twice_is_flagged_as_duplicate(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    data = _jpeg_with_exif()
    _upload(alice, ws, "a.jpg", "image/jpeg", data)
    second = _upload(alice, ws, "b.jpg", "image/jpeg", data).json()
    while asyncio.run(queue.run_once()):
        pass
    assert alice.get(f"/api/v1/workspaces/{ws}/sources/{second['id']}").json()["duplicates"] == 1


def test_pdf_upload_extracts_title(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    src = _upload(alice, ws, "rapport.pdf", "application/pdf", _pdf()).json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert (src["status"], src["title"], src["file"]["meta"]["pages"]) == (
        "ready",
        "Rapport INSTAT octobre",
        1,
    )


def test_upload_rules(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    url = f"/api/v1/workspaces/{ws}/files/upload-url"
    assert (
        alice.post(
            url, json={"filename": "x.exe", "mime": "application/x-msdownload", "size_bytes": 10}
        ).status_code
        == 415
    )
    assert (
        alice.post(
            url,
            json={"filename": "big.pdf", "mime": "application/pdf", "size_bytes": 26 * 1024 * 1024},
        ).status_code
        == 413
    )
    up = alice.post(
        url, json={"filename": "a.pdf", "mime": "application/pdf", "size_bytes": 10}
    ).json()
    # Completing before the browser uploaded anything is refused.
    r = alice.post(f"/api/v1/workspaces/{ws}/files/{up['file_id']}/complete", json={})
    assert r.status_code == 409


def test_text_source_is_ready_at_once(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(
        f"/api/v1/workspaces/{ws}/sources",
        json={"text": "Communiqué du ministère\nLe prix est stable."},
    )
    assert r.status_code == 201
    assert (r.json()["kind"], r.json()["status"], r.json()["title"]) == (
        "text",
        "ready",
        "Communiqué du ministère",
    )
    assert alice.post(f"/api/v1/workspaces/{ws}/sources", json={}).status_code == 422


ARTICLE = """<html><head><title>Riz : les prix stables selon l'INSTAT</title>
<meta name="author" content="Hery Rabe"></head><body><article><h1>Riz : les prix stables selon l'INSTAT</h1>
<p>Selon le dernier relevé de l'Institut national de la statistique, le prix du riz local est resté stable
à Antananarivo entre septembre et octobre, autour de 3 200 ariary le kilo.</p>
<p>Les commerçants du marché d'Analakely confirment une légère hausse sur le riz importé seulement.</p>
</article></body></html>"""


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setattr(ingest, "_resolve", lambda host: ["93.184.216.34"])
    pages = {}

    def handler(request):
        page = pages.get(str(request.url))
        if page is None:
            return httpx.Response(404)
        return page

    monkeypatch.setattr(ingest, "_transport", httpx.MockTransport(handler))
    return pages


def test_url_source_extracts_the_article(as_user, web):
    web["https://news.test/riz"] = httpx.Response(301, headers={"location": "/riz-stable"})
    web["https://news.test/riz-stable"] = httpx.Response(
        200, text=ARTICLE, headers={"content-type": "text/html; charset=utf-8"}
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    src = alice.post(
        f"/api/v1/workspaces/{ws}/sources", json={"url": "https://news.test/riz"}
    ).json()
    assert (src["kind"], src["status"]) == ("url", "queued")
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert src["status"] == "ready"
    assert "INSTAT" in src["title"]
    assert "3 200 ariary" in src["excerpt"]
    text = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}/text").json()["text"]
    assert "Analakely" in text


def test_url_to_a_private_address_is_refused(as_user, monkeypatch):
    monkeypatch.setattr(ingest, "_resolve", lambda host: ["127.0.0.1"])
    alice = as_user("alice")
    ws = _workspace(alice)
    r = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"url": "http://localhost:8000/api"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "bad_url")
    r = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"url": "file:///etc/passwd"})
    assert r.status_code == 422


def test_redirect_to_a_private_address_fails_the_job(as_user, web, monkeypatch):
    web["https://news.test/x"] = httpx.Response(
        302, headers={"location": "http://internal.test/admin"}
    )
    monkeypatch.setattr(
        ingest,
        "_resolve",
        lambda host: ["10.0.0.5"] if host == "internal.test" else ["93.184.216.34"],
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    src = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"url": "https://news.test/x"}).json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert src["status"] == "failed"
    assert "public internet" in src["error"]


def test_delete_removes_the_object_and_updates_the_count(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    item = _claim(alice, ws)
    src = _upload(alice, ws, "a.pdf", "application/pdf", _pdf(), item).json()
    assert len(OBJECTS) == 1
    assert alice.delete(f"/api/v1/workspaces/{ws}/sources/{src['id']}").status_code == 204
    assert OBJECTS == {}
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]["source_count"] == 0


def test_sources_are_workspace_scoped(as_user):
    alice, mallory = as_user("alice"), as_user("mallory")
    ws = _workspace(alice)
    ws_m = _workspace(mallory, "Other")
    src = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"text": "secret"}).json()
    assert mallory.get(f"/api/v1/workspaces/{ws_m}/sources/{src['id']}").status_code == 404
    assert mallory.get(f"/api/v1/workspaces/{ws}/sources").status_code == 404
    item = _claim(alice, ws)
    r = mallory.post(f"/api/v1/workspaces/{ws_m}/sources", json={"text": "x", "item_id": item})
    assert r.status_code == 404


@pytest.fixture
def whisper(monkeypatch):
    from app.core import stt
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "groq_api_key", "key-groq")
    monkeypatch.setattr(get_settings(), "ai_attempts", 2)

    async def no_sleep(_):
        pass

    monkeypatch.setattr(stt, "_sleep", no_sleep)
    calls = []
    replies = []

    def handler(request):
        body = request.content.decode(errors="replace")
        calls.append(body)
        reply = replies.pop(0) if replies else None
        if reply is not None:
            return reply
        return httpx.Response(
            200,
            json={
                "text": " Bonjour, le prix du riz est stable. ",
                "language": "french",
                "duration": 4.2,
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": " Bonjour,"},
                    {"start": 1.5, "end": 4.2, "text": " le prix du riz est stable."},
                ],
            },
        )

    monkeypatch.setattr(stt, "_transport", httpx.MockTransport(handler))
    return calls, replies


def test_audio_upload_is_transcribed_with_timestamps(as_user, whisper):
    calls, _ = whisper
    alice = as_user("alice")
    ws = _workspace(alice)
    src = _upload(alice, ws, "interview.m4a", "audio/mp4", b"fake-audio").json()
    assert src["kind"] == "audio"
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert (src["status"], src["excerpt"]) == ("ready", "Bonjour, le prix du riz est stable.")
    assert src["file"]["meta"] == {"duration_s": 4.2, "language": "french"}
    tr = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}/transcript").json()
    assert tr["segments"][1] == {"start": 1.5, "end": 4.2, "text": "le prix du riz est stable."}
    assert 'name="model"' in calls[0] and "whisper-large-v3" in calls[0]
    assert 'name="language"' not in calls[0]


def test_retranscribe_with_a_language_hint(as_user, whisper):
    calls, _ = whisper
    alice = as_user("alice")
    ws = _workspace(alice)
    src = _upload(alice, ws, "fanazavana.ogg", "audio/ogg", b"fake-audio").json()
    asyncio.run(queue.run_once())
    r = alice.post(
        f"/api/v1/workspaces/{ws}/sources/{src['id']}/transcribe", json={"language": "mg"}
    )
    assert (r.status_code, r.json()["status"]) == (202, "queued")
    asyncio.run(queue.run_once())
    assert 'name="language"' in calls[1] and "\r\n\r\nmg\r\n" in calls[1]
    assert (
        alice.post(
            f"/api/v1/workspaces/{ws}/sources/{src['id']}/transcribe", json={"language": "french"}
        ).status_code
        == 422
    )
    text = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"text": "x"}).json()
    assert (
        alice.post(f"/api/v1/workspaces/{ws}/sources/{text['id']}/transcribe", json={}).status_code
        == 409
    )


def test_a_video_is_transcribed_from_its_soundtrack(as_user, whisper, monkeypatch):
    calls, _ = whisper
    seen = []

    async def fake_video(raw, mime):
        seen.append((raw, mime))
        meta = {"duration_s": 4.0, "ai_markers": ["OpenAI Sora"], "content_credentials": False}
        return meta, b"fake-mp3", "audio.mp3", "audio/mpeg"

    monkeypatch.setattr(ingest, "video_meta_and_audio", fake_video)
    alice = as_user("alice")
    ws = _workspace(alice)
    src = _upload(alice, ws, "VID-2026.mp4", "video/mp4", b"fake-video").json()
    assert src["kind"] == "video"
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert (src["status"], src["excerpt"]) == ("ready", "Bonjour, le prix du riz est stable.")
    assert src["file"]["meta"]["ai_markers"] == ["OpenAI Sora"]
    assert src["file"]["meta"]["language"] == "french"
    assert seen == [(b"fake-video", "video/mp4")] and 'filename="audio.mp3"' in calls[0]
    assert alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}/transcript").status_code == 200
    r = alice.post(f"/api/v1/workspaces/{ws}/sources/{src['id']}/transcribe", json={})
    assert r.status_code == 202


def test_video_keyframes_are_stored_with_their_blurred_copy_and_reverse_search(
    as_user, whisper, monkeypatch
):
    async def fake_video(raw, mime):
        return {"duration_s": 4.0}, b"", "", ""

    async def frames(raw, duration, ffmpeg):
        assert raw == b"fake-video" and duration == 4.0
        return [
            {"at_s": i, "jpeg": b"\xff\xd8frame%d" % i, "dhash": f"{i:016x}", "flat": False}
            for i in range(4)
        ]

    def blur(raw):
        # The second frame shows a face.
        return (b"blurred", 1) if raw.endswith(b"1") else (raw, 0)

    monkeypatch.setattr(ingest, "video_meta_and_audio", fake_video)
    monkeypatch.setattr(ingest.media, "sample_frames", frames)
    monkeypatch.setattr(ingest.media, "blur_faces", blur)
    monkeypatch.setattr(ingest.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    alice = as_user("alice")
    ws = _workspace(alice)
    made = _upload(alice, ws, "clip.mp4", "video/mp4", b"fake-video").json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{made['id']}").json()
    previews = src["file"]["keyframes"]
    assert [f["at_s"] for f in previews] == [0, 1, 2, 3]
    assert [f["faces"] for f in previews] == [0, 1, 0, 0]
    shown = [f["image_url"].removeprefix("https://s3.test/").removesuffix("?get") for f in previews]
    # The frame with a face is shown blurred; the original stays next to it, inside the desk.
    assert OBJECTS[shown[1]] == b"blurred" and shown[1].endswith("1.blur.jpg")
    assert OBJECTS[shown[0]] == b"\xff\xd8frame0"
    assert OBJECTS[shown[1].replace(".blur.jpg", ".jpg")] == b"\xff\xd8frame1"
    assert all("lens.google.com/uploadbyurl" in f["reverse_search"][0]["url"] for f in previews)
    # Reverse-search engines only ever receive the blurred copy.
    assert all("1.blur.jpg" in link["url"] for link in previews[1]["reverse_search"])
    assert not any(
        "frames%2F1.jpg" in link["url"] for f in previews for link in f["reverse_search"]
    )


def test_failed_face_detection_hides_the_frame_but_keeps_the_source(as_user, whisper, monkeypatch):
    async def fake_video(raw, mime):
        return {"duration_s": 3.0}, b"", "", ""

    async def frames(raw, duration, ffmpeg):
        return [{"at_s": 0.0, "jpeg": b"raw-face", "dhash": "0f0f0f0f0f0f0f0f", "flat": False}]

    def unavailable(raw):
        raise RuntimeError("no detector")

    monkeypatch.setattr(ingest, "video_meta_and_audio", fake_video)
    monkeypatch.setattr(ingest.media, "sample_frames", frames)
    monkeypatch.setattr(ingest.media, "blur_faces", unavailable)
    monkeypatch.setattr(ingest.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    alice = as_user("alice")
    ws = _workspace(alice)
    made = _upload(alice, ws, "clip.mp4", "video/mp4", b"fake-video").json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{made['id']}").json()
    assert src["status"] == "ready"
    [frame] = src["file"]["keyframes"]
    assert frame["faces"] is None and frame["image_url"] is None
    assert frame["reverse_search"] == []


def test_an_image_with_a_face_is_shown_and_searched_blurred(as_user, monkeypatch):
    from app.modules import linkcheck

    monkeypatch.setattr(ingest.media, "blur_faces", lambda raw: (b"blurred", 2))
    alice = as_user("alice")
    ws = _workspace(alice)
    made = _upload(alice, ws, "foule.jpg", "image/jpeg", _jpeg_with_exif()).json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{made['id']}").json()
    picture = src["file"]["picture"]
    assert picture["faces"] == 2 and picture["image_url"].endswith("foule.blur.jpg?get")
    assert OBJECTS[picture["image_url"].removeprefix("https://s3.test/").removesuffix("?get")] == (
        b"blurred"
    )
    assert all("foule.blur.jpg" in link["url"] for link in picture["reverse_search"])
    # The link check hands reverse-search engines the same blurred copy, never the upload.
    page = asyncio.run(linkcheck.read_source(uuid.UUID(ws), uuid.UUID(made["id"])))
    assert page["image_url"].endswith("foule.blur.jpg?get")


def test_an_image_whose_faces_could_not_be_checked_never_leaves_the_desk(as_user, monkeypatch):
    from app.modules import linkcheck

    def unavailable(raw):
        raise RuntimeError("no detector")

    monkeypatch.setattr(ingest.media, "blur_faces", unavailable)
    alice = as_user("alice")
    ws = _workspace(alice)
    made = _upload(alice, ws, "foule.jpg", "image/jpeg", _jpeg_with_exif()).json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{made['id']}").json()
    assert src["file"]["picture"] == {"faces": None, "image_url": None, "reverse_search": []}
    page = asyncio.run(linkcheck.read_source(uuid.UUID(ws), uuid.UUID(made["id"])))
    assert "image_url" not in page


def test_a_silent_video_is_ready_without_a_transcript(as_user, whisper, monkeypatch):
    calls, _ = whisper

    async def silent(raw, mime):
        return {"duration_s": 2.0, "ai_markers": [], "content_credentials": False}, b"", "", ""

    monkeypatch.setattr(ingest, "video_meta_and_audio", silent)
    alice = as_user("alice")
    ws = _workspace(alice)
    src = _upload(alice, ws, "clip.mov", "video/quicktime", b"fake-video").json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert (src["status"], src["excerpt"], calls) == ("ready", "", [])


def test_whisper_outage_marks_the_source_failed(as_user, whisper):
    _, replies = whisper
    replies.extend([httpx.Response(503), httpx.Response(503)])
    alice = as_user("alice")
    ws = _workspace(alice)
    src = _upload(alice, ws, "a.mp3", "audio/mpeg", b"fake-audio").json()
    asyncio.run(queue.run_once())
    src = alice.get(f"/api/v1/workspaces/{ws}/sources/{src['id']}").json()
    assert src["status"] == "failed"
    assert "503" in src["error"]


def test_a_source_date_is_set_by_hand(as_user):
    from tests.test_workspaces import _join

    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    src = alice.post(
        f"/api/v1/workspaces/{ws}/sources", json={"text": "Un texte collé sans date."}
    ).json()
    assert src["published_at"] is None
    url = f"/api/v1/workspaces/{ws}/sources/{src['id']}"
    r = alice.patch(url, json={"published_at": "2019-01-14"})
    assert r.status_code == 200 and r.json()["published_at"] == "2019-01-14"
    assert alice.get(url).json()["published_at"] == "2019-01-14"
    assert alice.patch(url, json={"published_at": "2999-01-01"}).status_code == 422
    assert alice.patch(url, json={"published_at": None}).json()["published_at"] is None
    assert as_user("mallory").patch(url, json={"published_at": None}).status_code == 404
    _join(alice, bob, ws)
    assert (
        bob.patch(url, json={"published_at": "2020-01-01"}).json()["published_at"] == "2020-01-01"
    )


def test_a_source_is_attached_to_a_claim_later(as_user):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    src = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"text": "Le pont est fermé."}).json()
    item = _claim(alice, ws)
    url = f"/api/v1/workspaces/{ws}/sources/{src['id']}"
    r = alice.patch(url, json={"item_id": item})
    assert (r.status_code, r.json()["item_id"]) == (200, item)
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]["source_count"] == 1
    actions = [
        a["action"] for a in alice.get(f"/api/v1/workspaces/{ws}/activity?entity_id={item}").json()
    ]
    assert "source" in actions
    other = _claim(alice, ws)
    alice.patch(url, json={"item_id": other})
    assert alice.get(f"/api/v1/workspaces/{ws}/items/{item}").json()["data"]["source_count"] == 0
    assert alice.patch(url, json={"item_id": str(uuid.uuid4())}).status_code == 404
    assert bob.patch(url, json={"item_id": item}).status_code == 404


def test_a_source_patch_changes_only_what_it_is_sent(as_user):
    alice = as_user("alice")
    ws = _workspace(alice)
    src = alice.post(f"/api/v1/workspaces/{ws}/sources", json={"text": "Le pont est fermé."}).json()
    url = f"/api/v1/workspaces/{ws}/sources/{src['id']}"
    alice.patch(url, json={"published_at": "2019-01-14"})
    item = _claim(alice, ws)
    r = alice.patch(url, json={"item_id": item})  # the phone sends only the claim
    assert (r.json()["item_id"], r.json()["published_at"]) == (item, "2019-01-14")
    r = alice.patch(url, json={"published_at": None})
    assert (r.json()["item_id"], r.json()["published_at"]) == (item, None)
    other = _claim(alice, ws)
    r = alice.patch(url, json={"published_at": "2020-02-02", "item_id": other})
    assert (r.json()["item_id"], r.json()["published_at"]) == (other, "2020-02-02")
    assert alice.patch(url, json={}).status_code == 422
    assert alice.patch(url, json={"item_id": None}).status_code == 422
    # an unknown claim changes nothing, not even the date sent with it
    r = alice.patch(url, json={"published_at": "2021-03-03", "item_id": str(uuid.uuid4())})
    assert r.status_code == 404
    assert alice.get(url).json()["published_at"] == "2020-02-02"
