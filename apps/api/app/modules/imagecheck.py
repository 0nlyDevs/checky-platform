"""Read image provenance hints without turning absence of markers into authenticity.

An optional, operator-configured pixel detector accepts raw image bytes and returns
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

from app.core.access import AnyMember
from app.core.config import get_settings
from app.core.errors import ApiError
from app.modules.linkcheck import reverse_search
from app.modules.public import _allow
from app.workers import ingest

router = APIRouter(tags=["image-check"])
Assessment = Literal["detected", "none", "inconclusive"]
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


class ImageFacts(BaseModel):
    width: int
    height: int
    format: str
    ai_markers: list[str]
    content_credentials: bool
    # Deliberately exclude GPS, authors and other personal EXIF fields from the response.
    exif: dict[str, str]


class SearchLink(BaseModel):
    name: str
    url: str


class ImageOut(BaseModel):
    url: str
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


async def detect_pixels(raw: bytes, mime: str) -> DetectorOut:
    settings = get_settings()
    if not settings.image_detector_url:
        return DetectorOut(status="not_configured")
    if not settings.image_detector_validated:
        return DetectorOut(status="not_validated")
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
    headers = {"Content-Type": mime}
    if settings.image_detector_token:
        headers["Authorization"] = f"Bearer {settings.image_detector_token}"
    try:
        async with (
            httpx.AsyncClient(
                transport=_detector_transport, timeout=20, follow_redirects=False
            ) as http,
            http.stream(
                "POST", settings.image_detector_url, content=raw, headers=headers
            ) as response,
        ):
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 16_384:
                    raise ValueError("Detector response too large")
        answer = DetectorReply.model_validate(json.loads(data))
        # Conservative operational thresholds, not a claimed calibration or probability.
        assessment: Assessment = (
            "detected"
            if answer.ai_score >= 0.9
            else "none"
            if answer.ai_score <= 0.1
            else "inconclusive"
        )
        return DetectorOut(status="assessed", assessment=assessment, model=answer.model)
    except (httpx.HTTPError, ValueError, TypeError):
        return DetectorOut(status="unavailable")


def _limited(request: Request) -> None:
    addr = request.client.host if request.client else "unknown"
    if not _allow(_IMAGES, addr, 20, 600.0):
        raise ApiError(429, "too_many_checks", "Too many image analyses, try again later")


@router.post("/workspaces/{ws}/image-check", dependencies=[Depends(_limited)])
async def image_check(body: ImageIn, _member: AnyMember) -> ImageOut:
    return await inspect_image(body)


async def inspect_image(body: ImageIn, *, allow_detector: bool = True) -> ImageOut:
    """Shared read-only examination; callers provide their own authorization and budget."""
    try:
        final, declared_mime, raw, _ = await ingest.fetch_raw(body.url)
        if not declared_mime.startswith("image/"):
            raise ValueError("The URL does not return an image")
        facts, mime = await asyncio.to_thread(_facts, raw)
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        httpx.HTTPError,
    ) as exc:
        raise ApiError(422, "image_unreadable", "The public image could not be read") from exc
    detector = (
        await detect_pixels(raw, mime) if allow_detector else DetectorOut(status="not_configured")
    )
    assessment: Assessment = (
        "detected"
        if facts.ai_markers or detector.assessment == "detected"
        else "inconclusive"
        if detector.status in ("unavailable", "not_validated")
        or (detector.status == "assessed" and detector.assessment == "inconclusive")
        else "none"
    )
    return ImageOut(
        url=final,
        assessment=assessment,
        image=facts,
        detector=detector,
        reverse_search=[SearchLink(**link) for link in reverse_search(final)],
        limitations=[
            "metadata_can_be_removed_or_forged",
            "absence_of_markers_does_not_prove_authenticity",
            "content_credentials_signature_not_verified",
            "pixel_detector_is_probabilistic",
            "image_origin_is_not_claim_truth",
        ],
    )
