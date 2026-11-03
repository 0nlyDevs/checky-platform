"""Verify the Content Credentials (C2PA) a picture or a video carries.

Finding the manifest's markers only says a manifest is there. Here the manifest is read and its
signature and hashes are checked by the C2PA library: the file must still match what the signer
signed. The signer counts as recognised only when its certificate chains to the official C2PA trust
list (`data/c2pa-trust-anchors.pem`, the list's certificates only). So three outcomes:

- `trusted`: intact and signed by a recognised issuer (a camera maker, an editor, a newsroom);
- `valid`: intact, but the signer is not on the list: the file matches what was signed, nobody vouches
  for who signed;
- `invalid`: the manifest does not match the file (it was edited after signing) or its signature fails.

No manifest, or a file type the library cannot read, gives None. Never raises, and never touches
the network: a manifest that lives elsewhere (a URL in the file) is not fetched.
"""

import io
import json
import logging
from functools import lru_cache
from importlib import resources
from typing import Any

log = logging.getLogger("checky.c2pa")
UNTRUSTED = "signingCredential.untrusted"
AI_SOURCE = "trainedalgorithmicmedia"  # IPTC digital source type, also inside « composite… »


@lru_cache(maxsize=1)
def _context() -> Any:
    import c2pa

    anchors = (resources.files("app.core") / "data" / "c2pa-trust-anchors.pem").read_text()
    # The files are uploads and links from strangers: the library must never go and fetch what they
    # point to (a remote manifest URL in the XMP, an OCSP responder), or the server becomes a proxy.
    settings = c2pa.Settings.from_dict(
        {
            "trust": {"trust_anchors": anchors},
            "verify": {"verify_trust": True, "remote_manifest_fetch": False, "ocsp_fetch": False},
        }
    )
    return c2pa.Context(settings)


def summarize(report: dict[str, Any], state: str) -> dict[str, Any]:
    """The facts a journalist reads, from the library's JSON report and validation state."""
    manifests = report.get("manifests") or {}
    manifest = manifests.get(report.get("active_manifest") or "") or {}
    signature = manifest.get("signature_info") or {}
    actions: list[dict[str, Any]] = []
    for assertion in manifest.get("assertions") or []:
        if str(assertion.get("label", "")).startswith("c2pa.actions"):
            actions += (assertion.get("data") or {}).get("actions") or []
    software = sorted(
        {a["softwareAgent"] for a in actions if isinstance(a.get("softwareAgent"), str)}
    )
    ai = any(AI_SOURCE in str(a.get("digitalSourceType", "")).lower() for a in actions)
    problems = [
        v["code"]
        for v in report.get("validation_status") or []
        if v.get("code") and v["code"] != UNTRUSTED
    ]
    outcome = {"Trusted": "trusted", "Valid": "valid"}.get(state, "invalid")
    if problems:
        outcome = "invalid"
    return {
        "state": outcome,
        "signer": signature.get("common_name") or signature.get("issuer"),
        "issuer": signature.get("issuer"),
        "signed_at": signature.get("time"),
        "generator": manifest.get("claim_generator"),
        "software": software[:5],
        "ai": ai,
        "edited": any(
            a.get("action") not in (None, "c2pa.created", "c2pa.opened") for a in actions
        ),
        "problems": problems[:5],
    }


def read(raw: bytes, mime: str | None = None) -> dict[str, Any] | None:
    """The verified Content Credentials of these bytes, or None when there are none to read."""
    try:
        import c2pa

        with c2pa.Reader(mime or None, io.BytesIO(raw), context=_context()) as reader:
            report = json.loads(reader.json())
            state = str(reader.get_validation_state())
    except Exception as exc:  # noqa: BLE001 - no manifest, unsupported type or unreadable: nothing to say
        log.debug("no readable content credentials: %s", type(exc).__name__)
        return None
    if not report.get("manifests"):
        return None
    return summarize(report, state)
