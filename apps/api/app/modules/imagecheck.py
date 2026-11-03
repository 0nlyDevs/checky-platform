"""Read image provenance hints without turning absence of markers into authenticity.

An image arrives either as a public URL (fetched here) or as the file itself (a WhatsApp photo,
a screenshot), sent as the raw request body. An optional, operator-configured pixel detector accepts raw image bytes and returns
{"ai_score": 0..1, "model": "versioned identifier"}. It is never contacted until
IMAGE_DETECTOR_VALIDATED=true. Scores are signals, not calibrated probabilities of truth.
No image, result or dossier is persisted by this endpoint.
"""

import asyncio
import io
import json
import warnings
from collections import defaultdict, deque
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Request
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator

from app.core import keys
from app.core.access import AnyMember
from app.core.config import get_settings
from app.core.errors import ApiError
from app.modules.linkcheck import reverse_search
from app.modules.public import _allow
from app.workers import ingest

router = APIRouter(tags=["image-check"])
Assessment = Literal["detected", "none", "inconclusive"]
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
MAX_IMAGE_BYTES = ingest.MAX_PAGE_BYTES  # 5 MB, the same cap as a downloaded image
# Documents the raw body so the generated client types know these routes take a file.
FILE_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            mime: {"schema": {"type": "string", "format": "binary"}} for mime in IMAGE_TYPES
        },
    }
}
LIMITATIONS = [
    "metadata_can_be_removed_or_forged",
    "absence_of_markers_does_not_prove_authenticity",
    "pixel_detector_is_probabilistic",
    "image_origin_is_not_claim_truth",
]
_IMAGES: dict[str, deque[float]] = defaultdict(deque)
_detector_transport: httpx.AsyncBaseTransport | None = None


class ImageIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("url")
    @classmethod
    def public_http(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Only public HTTP(S) image URLs without credentials are accepted")
        return value


class DetectorOut(BaseModel):
    status: Literal["not_configured", "not_validated", "unavailable", "assessed"]
    assessment: Assessment = "inconclusive"
    model: str | None = None
    # The detector's own "AI-generated" score, 0..1, shown as is: a signal, not a probability of truth.
    score: float | None = None


class CredentialsOut(BaseModel):
    """Content Credentials whose signature and hashes were checked (`core/content_credentials.py`)."""

    state: Literal["trusted", "valid", "invalid"]
    signer: str | None = None
    issuer: str | None = None
    signed_at: str | None = None
    generator: str | None = None
    software: list[str] = []
    ai: bool = False
    edited: bool = False
    problems: list[str] = []


class ImageFacts(BaseModel):
    width: int
    height: int
    format: str
    ai_markers: list[str]
    content_credentials: bool
    credentials: CredentialsOut | None = None
    # Deliberately exclude GPS, authors and other personal EXIF fields from the response.
    exif: dict[str, str]


class SearchLink(BaseModel):
    name: str
    url: str


class ImageOut(BaseModel):
    url: str | None  # None when the image was sent as a file
    source: Literal["url", "file"] = "url"
    assessment: Assessment
    image: ImageFacts
    detector: DetectorOut
    reverse_search: list[SearchLink]
    limitations: list[str]


class DetectorReply(BaseModel):
    ai_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    model: str = Field(min_length=1, max_length=160)


def _facts(raw: bytes) -> tuple[ImageFacts, str]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("Image exceeds 20 megapixels")
            mime = Image.MIME.get(image.format or "", "")
            if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                raise ValueError("Unsupported image format")
            image.verify()
        meta = ingest.image_meta(raw)
    meta["exif"] = {
        key: value
        for key, value in meta.get("exif", {}).items()
        if key in ("Make", "Model", "Software", "DateTimeOriginal", "DateTime")
        and isinstance(value, str)
    }
    return ImageFacts(**meta), mime


SIGHTENGINE_URL = "https://api.sightengine.com/1.0/check.json"


def _grade(answer: DetectorReply) -> DetectorOut:
    # Conservative operational thresholds, not a claimed calibration or probability.
    assessment: Assessment = (
        "detected"
        if answer.ai_score >= 0.9
        else "none"
        if answer.ai_score <= 0.1
        else "inconclusive"
    )
    return DetectorOut(
        status="assessed",
        assessment=assessment,
        model=answer.model,
        score=round(answer.ai_score, 3),
    )


# A refused key (bad key, rate limit, used-up quota) hands over to the next one in turn; any other
# failure says the detector is unavailable without burning a key on, say, an unreadable image.
REFUSED = {401, 403, 429}
REFUSAL_WORDS = ("limit", "quota", "usage", "credential", "auth", "key", "plan")


def _set_aside(service: str, key: str, status: int) -> None:
    keys.set_aside(service, key, get_settings().ai_cooldown if status == 429 else 3600.0)


async def _sightengine(raw: bytes, mime: str) -> DetectorOut:
    """Sightengine's `genai` model: multipart upload, answers {"type": {"ai_generated": 0..1}}.

    SIGHTENGINE_API_USER and SIGHTENGINE_API_SECRET are comma lists paired in order (one account
    each), used in turn like every other key list."""
    settings = get_settings()
    secrets = dict(
        zip(keys.split(settings.sightengine_api_user), keys.split(settings.sightengine_api_secret))
    )
    for user in keys.rotation("sightengine", list(secrets)):
        try:
            async with httpx.AsyncClient(
                transport=_detector_transport, timeout=20, follow_redirects=False
            ) as http:
                response = await http.post(
                    SIGHTENGINE_URL,
                    data={"models": "genai", "api_user": user, "api_secret": secrets[user]},
                    files={"media": ("image", raw, mime)},
                )
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return DetectorOut(status="unavailable")
        error = json.dumps(body.get("error") or "").casefold() if isinstance(body, dict) else ""
        if response.status_code in REFUSED or any(word in error for word in REFUSAL_WORDS):
            _set_aside("sightengine", user, response.status_code)
            continue
        try:
            response.raise_for_status()
            if body.get("status") != "success":
                raise ValueError("Sightengine refused the request")
            score = body["type"]["ai_generated"]
            return _grade(DetectorReply(ai_score=score, model="sightengine-genai"))
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            return DetectorOut(status="unavailable")
    return DetectorOut(status="unavailable")


async def _custom_detector(raw: bytes, mime: str) -> DetectorOut:
    """IMAGE_DETECTOR_URL: raw bytes in, {ai_score, model} out; IMAGE_DETECTOR_TOKEN may be a list."""
    settings = get_settings()
    target = urlparse(settings.image_detector_url)
    if (
        target.username
        or target.password
        or not target.hostname
        or (
            target.scheme != "https"
            and not (target.scheme == "http" and target.hostname in ("localhost", "127.0.0.1"))
        )
    ):
        return DetectorOut(status="unavailable")
    tokens = keys.split(settings.image_detector_token)
    for token in keys.rotation("image-detector", tokens) if tokens else [""]:
        headers = {"Content-Type": mime}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            async with (
                httpx.AsyncClient(
                    transport=_detector_transport, timeout=20, follow_redirects=False
                ) as http,
                http.stream(
                    "POST", settings.image_detector_url, content=raw, headers=headers
                ) as response,
            ):
                if token and response.status_code in REFUSED:
                    _set_aside("image-detector", token, response.status_code)
                    continue
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 16_384:
                        raise ValueError("Detector response too large")
            return _grade(DetectorReply.model_validate(json.loads(data)))
        except (httpx.HTTPError, ValueError, TypeError):
            return DetectorOut(status="unavailable")
    return DetectorOut(status="unavailable")


async def detect_pixels(raw: bytes, mime: str) -> DetectorOut:
    settings = get_settings()
    sightengine = bool(
        keys.split(settings.sightengine_api_user) and keys.split(settings.sightengine_api_secret)
    )
    if not settings.image_detector_url and not sightengine:
        return DetectorOut(status="not_configured")
    if not settings.image_detector_validated:
        return DetectorOut(status="not_validated")
    return await (_sightengine if sightengine else _custom_detector)(raw, mime)


def _limited(request: Request) -> None:
    addr = request.client.host if request.client else "unknown"
    if not _allow(_IMAGES, addr, 20, 600.0):
        raise ApiError(429, "too_many_checks", "Too many image analyses, try again later")


@router.post("/workspaces/{ws}/image-check", dependencies=[Depends(_limited)])
async def image_check(body: ImageIn, _member: AnyMember) -> ImageOut:
    return await inspect_image(body)


@router.post(
    "/workspaces/{ws}/image-check/file", dependencies=[Depends(_limited)], openapi_extra=FILE_BODY
)
async def image_file_check(request: Request, _member: AnyMember) -> ImageOut:
    return await examine(await read_upload(request), url=None)


def manual_reverse_search() -> list[SearchLink]:
    """A file has no address to hand over: these pages take an image the user drops on them."""
    return [
        SearchLink(name="Google Lens", url="https://lens.google.com/"),
        SearchLink(name="TinEye", url="https://tineye.com/"),
        SearchLink(name="Yandex", url="https://yandex.com/images/"),
    ]


async def read_upload(request: Request) -> bytes:
    """Read an image sent as the raw body, refusing anything over 5 MB before buffering it all."""
    mime = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if mime not in IMAGE_TYPES:
        raise ApiError(415, "unsupported_media", "Send a JPEG, PNG, WebP or GIF image")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
        raise ApiError(413, "too_large", "Images are limited to 5 MB")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_IMAGE_BYTES:
            raise ApiError(413, "too_large", "Images are limited to 5 MB")
    if not raw:
        raise ApiError(422, "image_unreadable", "The image file is empty")
    return bytes(raw)


async def inspect_image(body: ImageIn, *, allow_detector: bool = True) -> ImageOut:
    """Shared read-only examination; callers provide their own authorization and budget."""
    try:
        final, declared_mime, raw, _ = await ingest.fetch_raw(body.url)
        if not declared_mime.startswith("image/"):
            raise ValueError("The URL does not return an image")
    except (ValueError, OSError, httpx.HTTPError) as exc:
        raise ApiError(422, "image_unreadable", "The public image could not be read") from exc
    return await examine(raw, url=final, allow_detector=allow_detector)


async def examine(raw: bytes, *, url: str | None, allow_detector: bool = True) -> ImageOut:
    """Examine image bytes, fetched from `url` or sent as a file (`url` None)."""
    try:
        facts, mime = await asyncio.to_thread(_facts, raw)
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ApiError(422, "image_unreadable", "The image could not be read") from exc
    detector = (
        await detect_pixels(raw, mime) if allow_detector else DetectorOut(status="not_configured")
    )
    # "none" needs a detector that looked at the pixels and found nothing: metadata alone are
    # stripped by WhatsApp, social networks, screenshots and image proxies, so their absence says nothing.
    assessment: Assessment = (
        "detected"
        if facts.ai_markers or detector.assessment == "detected"
        else "none"
        if detector.status == "assessed" and detector.assessment == "none"
        else "inconclusive"
    )
    return ImageOut(
        url=url,
        source="url" if url else "file",
        assessment=assessment,
        image=facts,
        detector=detector,
        reverse_search=[SearchLink(**link) for link in reverse_search(url)]
        if url
        else manual_reverse_search(),
        limitations=LIMITATIONS
        + (
            ["content_credentials_signature_not_verified"]
            if facts.content_credentials and not facts.credentials
            else []
        ),
    )
