import io

import httpx
import pytest
from PIL import Image, PngImagePlugin

from app.core.config import get_settings
from app.modules import imagecheck
from app.workers import ingest
from tests.test_workspaces import _workspace


@pytest.fixture
def image_web(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "image_detector_url", "")
    monkeypatch.setattr(settings, "image_detector_validated", False)
    monkeypatch.setattr(ingest, "_resolve", lambda _: ["93.184.216.34"])
    pages = {}

    def respond(request):
        data, mime = pages.get(str(request.url), (b"", "text/html"))
        return httpx.Response(200, content=data, headers={"Content-Type": mime})

    monkeypatch.setattr(ingest, "_transport", httpx.MockTransport(respond))
    monkeypatch.setattr(
        imagecheck,
        "_detector_transport",
        httpx.MockTransport(lambda _: pytest.fail("Unconfigured detector must not be called")),
    )
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
    assert result["detector"]["status"] == "not_configured"
    assert "verdict" not in result and "ai_score" not in result["detector"]
    assert "absence_of_markers_does_not_prove_authenticity" in result["limitations"]
    assert len(result["reverse_search"]) == 3
    assert alice.get(f"/api/v1/workspaces/{ws}/items").json()["items"] == []


def test_no_markers_is_not_an_authenticity_claim(as_user, image_web):
    alice = as_user("alice")
    ws = _workspace(alice)
    url = "https://images.example.test/photo.png"
    image_web[url] = (png(), "image/png")
    result = alice.post(f"/api/v1/workspaces/{ws}/image-check", json={"url": url}).json()
    assert result["assessment"] == "none" and result["image"]["ai_markers"] == []
    assert result["detector"]["assessment"] == "inconclusive"


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


def test_unvalidated_detector_is_never_contacted(as_user, image_web, monkeypatch):
    monkeypatch.setattr(get_settings(), "image_detector_url", "https://detector.test/check")
    alice = as_user("alice")
    ws = _workspace(alice)
    url = "https://images.test/a.png"
    image_web[url] = (png(), "image/png")
    result = alice.post(f"/api/v1/workspaces/{ws}/image-check", json={"url": url}).json()
    assert result["detector"]["status"] == "not_validated"
    assert result["assessment"] == "inconclusive"


@pytest.mark.parametrize(
    ("score", "expected"), [(0.97, "detected"), (0.03, "none"), (0.6, "inconclusive")]
)
def test_validated_detector_is_a_separate_probabilistic_signal(
    as_user, image_web, monkeypatch, score, expected
):
    settings = get_settings()
    monkeypatch.setattr(settings, "image_detector_url", "https://detector.test/check")
    monkeypatch.setattr(settings, "image_detector_token", "test-only-secret")
    monkeypatch.setattr(settings, "image_detector_validated", True)
    raw = png()

    def detector(request):
        assert request.content == raw
        assert request.headers["authorization"] == "Bearer test-only-secret"
        assert request.headers["content-type"] == "image/png"
        return httpx.Response(200, json={"ai_score": score, "model": "test-model-v1"})

    monkeypatch.setattr(imagecheck, "_detector_transport", httpx.MockTransport(detector))
    alice = as_user("alice")
    ws = _workspace(alice)
    url = "https://images.test/a.png"
    image_web[url] = (raw, "image/png")
    result = alice.post(f"/api/v1/workspaces/{ws}/image-check", json={"url": url}).json()
    assert result["assessment"] == expected
    assert result["detector"] == {
        "status": "assessed",
        "assessment": expected,
        "model": "test-model-v1",
    }
    assert "test-only-secret" not in str(result)


@pytest.mark.parametrize("reply", [{"ai_score": 2, "model": "x"}, {"model": "x"}])
def test_bad_detector_results_do_not_claim_authenticity(as_user, image_web, monkeypatch, reply):
    monkeypatch.setattr(get_settings(), "image_detector_url", "https://detector.test/check")
    monkeypatch.setattr(get_settings(), "image_detector_validated", True)
    monkeypatch.setattr(
        imagecheck,
        "_detector_transport",
        httpx.MockTransport(lambda _: httpx.Response(200, json=reply)),
    )
    alice = as_user("alice")
    ws = _workspace(alice)
    url = "https://images.test/a.png"
    image_web[url] = (png(), "image/png")
    result = alice.post(f"/api/v1/workspaces/{ws}/image-check", json={"url": url}).json()
    assert result["detector"]["status"] == "unavailable"
    assert result["assessment"] == "inconclusive"
