"""Content Credentials checked for real: the signature, the hashes and the signer."""

import asyncio
from pathlib import Path

from app.core import content_credentials
from app.modules import crew
from app.workers import ingest

SIGNED = (Path(__file__).parent / "fixtures" / "c2pa-signed.jpg").read_bytes()


def test_a_signed_picture_is_read_and_its_signer_is_not_on_the_trust_list():
    found = content_credentials.read(SIGNED, "image/jpeg")
    # The sample is signed with C2PA's test certificate: intact, but nobody official vouches for it.
    assert found["state"] == "valid"
    assert found["signer"] == "C2PA Signer" and found["signed_at"].startswith("2023-09-29")
    assert found["generator"].startswith("make_test_images")
    assert found["ai"] is False and found["edited"] is False and found["problems"] == []


def test_a_picture_changed_after_signing_is_invalid():
    changed = bytearray(SIGNED)
    changed[60_000] ^= 0xFF
    found = content_credentials.read(bytes(changed), "image/jpeg")
    assert found["state"] == "invalid" and "assertion.dataHash.mismatch" in found["problems"]


def test_no_manifest_and_garbage_give_nothing():
    assert content_credentials.read(b"not a picture", "image/jpeg") is None
    assert content_credentials.read(b"\xff\xd8\xff\xd9", None) is None


def test_summary_marks_a_recognised_signer_and_edits():
    report = {
        "active_manifest": "m",
        "manifests": {
            "m": {
                "claim_generator": "Leica",
                "signature_info": {
                    "common_name": "Leica Camera AG",
                    "time": "2026-03-01T10:00:00+00:00",
                },
                "assertions": [
                    {
                        "label": "c2pa.actions.v2",
                        "data": {
                            "actions": [
                                {"action": "c2pa.created"},
                                {"action": "c2pa.cropped", "softwareAgent": "Lightroom"},
                            ]
                        },
                    }
                ],
            }
        },
        "validation_status": [],
    }
    report["manifests"]["m"]["assertions"][0]["data"]["actions"][0]["digitalSourceType"] = (
        "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
    )
    found = content_credentials.summarize(report, "Trusted")
    assert found["state"] == "trusted" and found["signer"] == "Leica Camera AG"
    assert found["edited"] is True and found["software"] == ["Lightroom"] and found["ai"] is True
    signals = crew._credential_signals(found)
    assert signals[0]["detail"].startswith("Signée par Leica Camera AG, le 1er mars 2026")
    assert any("généré par une IA" in s["detail"] for s in signals)


def test_ingest_checks_the_manifest_when_markers_are_found():
    meta = ingest.ai_signals(SIGNED, [])
    assert meta["content_credentials"] is True and meta["credentials"]["state"] == "valid"
    assert "credentials" not in ingest.ai_signals(b"plain bytes", [])


def test_provenance_states_who_signed_and_flags_a_broken_signature():
    page = {
        "kind": "image",
        "final_url": "https://x.test/a.jpg",
        "image": ingest.ai_signals(SIGNED, []),
    }
    found = asyncio.run(crew.provenance_of(page, "Ce soir"))
    details = [s["detail"] for s in found["signals"]]
    assert any("signés par C2PA Signer, le 29 septembre 2023" in d for d in details)
    broken = {
        "kind": "image",
        "final_url": "https://x.test/a.jpg",
        "image": {
            "content_credentials": True,
            "credentials": {"state": "invalid"},
        },
    }
    found = asyncio.run(crew.provenance_of(broken, "Ce soir"))
    assert any("modifié après la signature" in s["detail"] for s in found["signals"])
    unread = {
        "kind": "image",
        "final_url": "https://x.test/a.jpg",
        "image": {"content_credentials": True},
    }
    found = asyncio.run(crew.provenance_of(unread, "Ce soir"))
    assert any("signature non vérifiée" in s["detail"] for s in found["signals"])


def test_a_remote_manifest_url_in_the_file_is_never_fetched():
    import http.server
    import io
    import socketserver
    import threading

    from PIL import Image

    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(buf, "JPEG")
        jpeg = buf.getvalue()
        xmp = (
            '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description xmlns:dcterms="http://purl.org/dc/terms/" '
            f'dcterms:provenance="http://127.0.0.1:{server.server_address[1]}/m.c2pa"/>'
            '</rdf:RDF></x:xmpmeta><?xpacket end="w"?>'
        ).encode()
        payload = b"http://ns.adobe.com/xap/1.0/\x00" + xmp
        segment = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
        assert content_credentials.read(jpeg[:2] + segment + jpeg[2:], "image/jpeg") is None
    finally:
        server.shutdown()
    assert hits == []
