import io

import httpx
import pytest
from PIL import Image, PngImagePlugin

from app.modules import imagecheck
from app.workers import ingest
from tests.test_workspaces import _workspace


@pytest.fixture
def image_web(monkeypatch):
    monkeypatch.setattr(ingest, "_resolve", lambda _: ["93.184.216.34"])
    pages = {}

    def respond(request):
        data, mime = pages.get(str(request.url), (b"", "text/html"))
        return httpx.Response(200, content=data, headers={"Content-Type": mime})

    monkeypatch.setattr(ingest, "_transport", httpx.MockTransport(respond))
    return pages


def png(marker=None):
    info = PngImagePlugin.PngInfo()
    if marker:
        info.add_text("parameters", marker)
    data = io.BytesIO()
    Image.new("RGB", (8, 6)).save(data, "PNG", pnginfo=info)
    return data.getvalue()


def test_metadata_hints_are_not_a_truth_verdict(as_user, image_web):
    alice = as_user("alice")
    ws = _workspace(alice)
    url = "https://images.example.test/photo.png"
    image_web[url] = (png("Stable Diffusion XL"), "image/png")
    response = alice.post(f"/api/v1/workspaces/{ws}/image-check", json={"url": url})
    assert response.status_code == 200
    result = response.json()
    assert result["assessment"] == "detected"
    assert result["image"]["ai_markers"] == ["Stable Diffusion"]
    assert result["image"]["width"] == 8
    assert "detector" not in result and "verdict" not in result
    assert "absence_of_markers_does_not_prove_authenticity" in result["limitations"]
    assert len(result["reverse_search"]) == 3
    assert alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"] == []


def test_no_markers_is_not_an_authenticity_claim(as_user, image_web):
    alice = as_user("alice")
    ws = _workspace(alice)
    url = "https://images.example.test/photo.png"
    image_web[url] = (png(), "image/png")
    result = alice.post(f"/api/v1/workspaces/{ws}/image-check", json={"url": url}).json()
    # Missing metadata says nothing about whether pixels were generated.
    assert result["assessment"] == "inconclusive" and result["image"]["ai_markers"] == []
    assert "detector" not in result


def test_personal_metadata_is_not_returned(as_user, image_web, monkeypatch):
    monkeypatch.setattr(
        ingest,
        "image_meta",
        lambda _: {
            "width": 8,
            "height": 6,
            "format": "PNG",
            "ai_markers": [],
            "content_credentials": False,
            "exif": {"Model": "Camera", "GPS": {"Latitude": "private"}, "Artist": "private"},
        },
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    url = "https://images.test/photo.png"
    image_web[url] = (png(), "image/png")
    result = alice.post(f"/api/v1/workspaces/{ws}/image-check", json={"url": url}).json()
    assert result["image"]["exif"] == {"Model": "Camera"}
    assert "private" not in str(result)


def test_private_urls_bad_files_and_outsiders_are_rejected(as_user, image_web, monkeypatch):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    endpoint = f"/api/v1/workspaces/{ws}/image-check"
    assert bob.post(endpoint, json={"url": "https://images.test/x"}).status_code == 404
    for url in ("file:///etc/passwd", "data:image/png,a", "https://user:pass@site.test/a"):
        assert alice.post(endpoint, json={"url": url}).status_code == 422
    monkeypatch.setattr(ingest, "_resolve", lambda _: ["127.0.0.1"])
    assert alice.post(endpoint, json={"url": "http://localhost/x"}).status_code == 422
    monkeypatch.setattr(ingest, "_resolve", lambda _: ["93.184.216.34"])
    url = "https://images.test/x"
    image_web[url] = (b"not an image", "image/png")
    assert alice.post(endpoint, json={"url": url}).status_code == 422
    image_web[url] = (b"<html>hello</html>", "text/html")
    assert alice.post(endpoint, json={"url": url}).status_code == 422


def test_an_image_file_is_examined_without_a_link(as_user, image_web):
    alice = as_user("alice")
    ws = _workspace(alice)
    response = alice.post(
        f"/api/v1/workspaces/{ws}/image-check/file",
        content=png("Stable Diffusion XL"),
        headers={"Content-Type": "image/png"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["url"] is None and result["source"] == "file"
    assert result["assessment"] == "detected"
    assert result["image"]["ai_markers"] == ["Stable Diffusion"]
    # No address exists to pass along: the links only open the services' upload pages.
    assert [link["name"] for link in result["reverse_search"]] == [
        "Google Lens",
        "TinEye",
        "Yandex",
    ]
    assert all("url=" not in link["url"] for link in result["reverse_search"])
    assert alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"] == []


def test_image_files_are_bounded_and_members_only(as_user, image_web, monkeypatch):
    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    endpoint = f"/api/v1/workspaces/{ws}/image-check/file"
    image = {"Content-Type": "image/png"}
    assert bob.post(endpoint, content=png(), headers=image).status_code == 404
    assert (
        alice.post(
            endpoint, content=b"%PDF-1.7", headers={"Content-Type": "application/pdf"}
        ).status_code
        == 415
    )
    assert alice.post(endpoint, content=b"", headers=image).status_code == 422
    assert alice.post(endpoint, content=b"not an image", headers=image).status_code == 422
    monkeypatch.setattr(imagecheck, "MAX_IMAGE_BYTES", 64)
    assert alice.post(endpoint, content=png() + b"\0" * 64, headers=image).status_code == 413
