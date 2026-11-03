"""Read image provenance hints without turning absence of markers into authenticity.

An image arrives either as a public URL (fetched here) or as the file itself (a WhatsApp photo,
a screenshot), sent as the raw request body. Only metadata and provenance hints are inspected.
No image, result or dossier is persisted by this endpoint.
"""

import asyncio
import io
import warnings
from collections import defaultdict, deque
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Request
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator

from app.core.access import AnyMember
from app.core.errors import ApiError
from app.modules.linkcheck import reverse_search
from app.modules.public import _allow
from app.workers import ingest

router = APIRouter(tags=["image-check"])
Assessment = Literal["detected", "inconclusive"]
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
    "content_credentials_signature_not_verified",
    "image_origin_is_not_claim_truth",
]
_IMAGES: dict[str, deque[float]] = defaultdict(deque)


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
    url: str | None  # None when the image was sent as a file
    source: Literal["url", "file"] = "url"
    assessment: Assessment
    image: ImageFacts
    reverse_search: list[SearchLink]
    limitations: list[str]


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


async def inspect_image(body: ImageIn) -> ImageOut:
    """Shared read-only examination; callers provide their own authorization and budget."""
    try:
        final, declared_mime, raw, _ = await ingest.fetch_raw(body.url)
        if not declared_mime.startswith("image/"):
            raise ValueError("The URL does not return an image")
    except (ValueError, OSError, httpx.HTTPError) as exc:
        raise ApiError(422, "image_unreadable", "The public image could not be read") from exc
    return await examine(raw, url=final)


async def examine(raw: bytes, *, url: str | None) -> ImageOut:
    """Examine image bytes, fetched from `url` or sent as a file (`url` None)."""
    try:
        facts, _mime = await asyncio.to_thread(_facts, raw)
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ApiError(422, "image_unreadable", "The image could not be read") from exc
    # Missing metadata proves nothing: social networks and screenshots routinely strip it.
    assessment: Assessment = "detected" if facts.ai_markers else "inconclusive"
    return ImageOut(
        url=url,
        source="url" if url else "file",
        assessment=assessment,
        image=facts,
        reverse_search=[SearchLink(**link) for link in reverse_search(url)]
        if url
        else manual_reverse_search(),
        limitations=LIMITATIONS,
    )
