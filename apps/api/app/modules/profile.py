"""A journalist's profile: phone, outlet and a photo of the press card (asked at sign-up).

Upload: `POST /me/press-card/upload-url` → the client PUTs the photo to the presigned URL →
`PUT /me/profile` checks the object is in the bucket and saves the profile. The card is private:
only its owner and the Checky team (`PLATFORM_ADMINS`) get a short-lived link to it.
"""

import asyncio
import hashlib
import io
import re
import uuid

from fastapi import APIRouter
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.core import storage
from app.core.access import Db
from app.core.errors import ApiError
from app.core.models import JournalistProfile
from app.core.security import User
from app.modules.verification import is_platform_admin

router = APIRouter(tags=["profile"])

MAX_CARD_BYTES = 8 * 1024 * 1024
CARD_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}
_PHONE = re.compile(r"^\+?[0-9][0-9 ().-]{5,22}$")


def normalise_phone(raw: str) -> str:
    """`+261 34 00 000 00` → `+261340000000`; a national number keeps its leading zero."""
    raw = raw.strip()
    if not _PHONE.match(raw):
        raise ValueError("invalid phone number")
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        raise ValueError("invalid phone number")
    return ("+" if raw.startswith("+") else "") + digits


# A readable card photo: a name and a number must be legible, so thumbnails and icons are refused.
MIN_SIDE, MIN_LONG_SIDE, MAX_PIXELS = 300, 480, 50_000_000
_FORMATS = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}


def check_card(data: bytes, ext: str) -> dict[str, int] | None:
    """Raise ValueError unless the bytes really are a readable image or PDF of the declared type.

    This proves the file is genuine and legible, not that the card is authentic: a newsroom admin
    still looks at it. Returns the pixel size for an image.
    """
    if ext == "pdf":
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            raise ValueError("not a PDF")
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != _FORMATS[ext]:
                raise ValueError("file type does not match its content")
            w, h = img.size
            if w * h > MAX_PIXELS:
                raise ValueError("image too large")
            img.load()  # decodes every pixel: a truncated or forged file fails here
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ValueError("not a readable image") from e
    if min(w, h) < MIN_SIDE or max(w, h) < MIN_LONG_SIDE:
        raise ValueError("image too small to read")
    return {"width": w, "height": h}


class CardUploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str
    size_bytes: int = Field(gt=0)


class CardUploadOut(BaseModel):
    card_key: str
    upload_url: str
    headers: dict[str, str]
    expires_in: int


class JournalistProfileIn(BaseModel):
    phone: str
    outlet: str = Field(min_length=2, max_length=160)
    card_number: str | None = Field(default=None, max_length=60)
    card_key: str = Field(min_length=1, max_length=400)
    card_filename: str = Field(min_length=1, max_length=255)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalise_phone(v)

    @field_validator("outlet", "card_number")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = v.strip() if v else v
        return v or None


class JournalistProfileOut(BaseModel):
    phone: str
    outlet: str
    card_number: str | None
    card_filename: str
    card_url: str | None = None


def _out(p: JournalistProfile, *, with_card: bool) -> JournalistProfileOut:
    url = None
    if with_card and storage.configured():
        url = storage.presign_download(p.card_key, p.card_filename)
    return JournalistProfileOut(
        phone=p.phone,
        outlet=p.outlet,
        card_number=p.card_number,
        card_filename=p.card_filename,
        card_url=url,
    )


@router.post("/me/press-card/upload-url", status_code=201)
async def card_upload_url(body: CardUploadIn, user: User) -> CardUploadOut:
    if not storage.configured():
        raise ApiError(503, "storage_unavailable", "File storage is not configured")
    mime = body.mime.split(";")[0].strip().lower()
    if mime not in CARD_TYPES:
        raise ApiError(415, "unsupported_type", "Send a photo (JPEG, PNG, WebP) or a PDF")
    if body.size_bytes > MAX_CARD_BYTES:
        raise ApiError(413, "too_large", "The card file is limited to 8 MB")
    key = f"press-cards/{user.id}/{uuid.uuid4()}.{CARD_TYPES[mime]}"
    return CardUploadOut(
        card_key=key,
        upload_url=storage.presign_upload(key, mime),
        headers={"Content-Type": mime},
        expires_in=storage.UPLOAD_SECONDS,
    )


@router.put("/me/profile")
async def save_profile(body: JournalistProfileIn, user: User, db: Db) -> JournalistProfileOut:
    # Only a key issued to this user: nobody can point their profile at someone else's card.
    if not body.card_key.startswith(f"press-cards/{user.id}/"):
        raise ApiError(400, "bad_card", "This card was not uploaded by you")
    meta = await storage.head(body.card_key)
    if meta is None:
        raise ApiError(400, "card_missing", "The card upload did not arrive; send it again")
    if meta["size"] > MAX_CARD_BYTES:
        await storage.delete(body.card_key)
        raise ApiError(413, "too_large", "The card file is limited to 8 MB")
    ext = body.card_key.rsplit(".", 1)[-1]
    mime = {v: k for k, v in CARD_TYPES.items()}.get(ext)
    if mime is None:
        raise ApiError(400, "bad_card", "Unsupported card file")
    data = await storage.read(body.card_key)
    try:
        await asyncio.to_thread(check_card, data, ext)
    except ValueError as e:
        await storage.delete(body.card_key)
        raise ApiError(
            422, "invalid_card", f"This file is not a usable press card photo ({e})"
        ) from e
    digest = hashlib.sha256(data).hexdigest()
    reused = await db.scalar(
        select(JournalistProfile.id).where(
            JournalistProfile.card_sha256 == digest, JournalistProfile.user_id != user.id
        )
    )
    if reused:
        await storage.delete(body.card_key)
        raise ApiError(
            409, "card_already_used", "This card is already registered to another account"
        )

    row = await db.scalar(select(JournalistProfile).where(JournalistProfile.user_id == user.id))
    old_key = None
    if row is None:
        row = JournalistProfile(user_id=user.id)
        db.add(row)
    elif row.card_key != body.card_key:
        old_key = row.card_key
    row.phone = body.phone
    row.outlet = body.outlet
    row.card_number = body.card_number
    row.card_key = body.card_key
    row.card_filename = body.card_filename
    row.card_mime = mime
    row.card_size_bytes = len(data)
    row.card_sha256 = digest
    await db.commit()
    if old_key:
        await storage.delete(old_key)
    return _out(row, with_card=True)


@router.get("/me/profile")
async def my_profile(user: User, db: Db) -> JournalistProfileOut:
    row = await db.scalar(select(JournalistProfile).where(JournalistProfile.user_id == user.id))
    if row is None:
        raise ApiError(404, "not_found", "No profile yet")
    return _out(row, with_card=True)


@router.get("/platform/profiles/{user_id}")
async def platform_profile(user_id: str, user: User, db: Db) -> JournalistProfileOut:
    """The Checky team reads a journalist's profile and card; anyone else gets a 404."""
    if not is_platform_admin(user):
        raise ApiError(404, "not_found", "Not found")
    row = await db.scalar(select(JournalistProfile).where(JournalistProfile.user_id == user_id))
    if row is None:
        raise ApiError(404, "not_found", "No profile for this user")
    return _out(row, with_card=True)
