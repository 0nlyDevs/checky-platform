from urllib.parse import parse_qs, urlparse

import pytest

from app.core import storage
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(
        s, "storage_endpoint", "https://br-x.storage.c-7.eu-central-1.aws.neon.tech"
    )
    monkeypatch.setattr(s, "storage_region", "eu-central-1")
    monkeypatch.setattr(s, "storage_access_key_id", "nak_test")
    monkeypatch.setattr(s, "storage_secret_access_key", "nsk_test")
    monkeypatch.setattr(s, "storage_bucket", "uploads")


def test_upload_url_is_path_style_and_signed():
    url = urlparse(storage.presign_upload("sources/ws/a.pdf", "application/pdf", expires=120))
    q = parse_qs(url.query)
    assert url.netloc == "br-x.storage.c-7.eu-central-1.aws.neon.tech"
    assert url.path == "/uploads/sources/ws/a.pdf"
    assert q["X-Amz-Expires"] == ["120"]
    assert q["X-Amz-Credential"][0].startswith("nak_test/")
    assert "content-type" in q["X-Amz-SignedHeaders"][0]


def test_download_url_defaults_to_one_hour():
    q = parse_qs(urlparse(storage.presign_download("sources/ws/a.pdf")).query)
    assert q["X-Amz-Expires"] == ["3600"]
