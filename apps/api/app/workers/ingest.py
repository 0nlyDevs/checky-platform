"""Ingest jobs: turn an uploaded file or a URL into a ready source.

`ingest_file`: hash the object, read EXIF (images) or text (PDFs).
`ingest_url`:  fetch the page (public addresses only) and extract its main text.
"""

import asyncio
import hashlib
import io
import ipaddress
import socket
import uuid
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import update

from app.core import storage, stt
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import File, Source, Transcript
from app.realtime.server import emit
from app.workers.queue import JobContext, handler

MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
# Many news sites refuse unknown bots; fetch the page the way the journalist's browser would.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,mg;q=0.8,en;q=0.7",
}

# Tests swap this for an httpx.MockTransport, and `_resolve` for a fake resolver.
_transport: httpx.AsyncBaseTransport | None = None


def _resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


async def check_public_url(url: str) -> None:
    """Refuse anything but http(s) to a public address, so a pasted link cannot reach
    the API's own network (SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only http and https links can be added")
    addresses = await asyncio.to_thread(_resolve, parsed.hostname)
    for a in addresses:
        ip = ipaddress.ip_address(a)
        if not ip.is_global or ip.is_multicast:
            raise ValueError("This address is not reachable from the public internet")


async def fetch_page(url: str) -> tuple[str, str]:
    """GET a page, following up to 5 redirects, each one checked. Returns (final url, html)."""
    async with httpx.AsyncClient(transport=_transport, timeout=15, headers=HEADERS) as http:
        for _ in range(6):
            await check_public_url(url)
            async with http.stream("GET", url) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code >= 400:
                    raise ValueError(f"The page answered HTTP {resp.status_code}")
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_PAGE_BYTES:
                        raise ValueError("The page is larger than 5 MB")
                return url, body.decode(resp.encoding or "utf-8", errors="replace")
    raise ValueError("Too many redirects")


def extract_page(html: str, url: str) -> dict[str, Any]:
    import trafilatura

    doc = trafilatura.bare_extraction(html, url=url, with_metadata=True, include_tables=False)
    if doc is None:
        return {"title": "", "author": None, "published_at": None, "text": ""}
    data = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
    return {
        "title": (data.get("title") or "")[:500],
        "author": (data.get("author") or None),
        "published_at": data.get("date") or None,
        "text": (data.get("text") or "")[:MAX_TEXT_CHARS],
    }


def image_meta(raw: bytes) -> dict[str, Any]:
    """Readable EXIF tags, camera, date and GPS when present."""
    from PIL import ExifTags, Image

    with Image.open(io.BytesIO(raw)) as img:
        meta: dict[str, Any] = {"width": img.width, "height": img.height, "format": img.format}
        exif = img.getexif()
        tags = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
        ifd = exif.get_ifd(ExifTags.IFD.Exif)
        tags.update({ExifTags.TAGS.get(k, str(k)): v for k, v in ifd.items()})
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    picked = {
        k: str(tags[k])[:200]
        for k in ("Make", "Model", "Software", "DateTimeOriginal", "DateTime", "Artist")
        if k in tags
    }
    if gps:
        picked["GPS"] = {ExifTags.GPSTAGS.get(k, str(k)): str(v)[:100] for k, v in gps.items()}
    meta["exif"] = picked
    return meta


def pdf_text(raw: bytes) -> tuple[dict[str, Any], str, str]:
    """(meta, title, text) of a PDF."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    pages = [p.extract_text() or "" for p in reader.pages]
    info = reader.metadata or {}
    title = str(info.get("/Title") or "").strip()
    return {"pages": len(pages)}, title, "\n\n".join(pages)[:MAX_TEXT_CHARS]


async def _finish(source_id: uuid.UUID, ws: uuid.UUID, **values: Any) -> dict[str, Any]:
    from app.modules.sources import source_payload  # avoid an import cycle at module load

    async with SessionLocal() as db:
        await db.execute(update(Source).where(Source.id == source_id).values(**values))
        await db.commit()
        source = await db.get(Source, source_id)
        payload = await source_payload(db, source)
    await emit(ws, "source.updated", payload)
    return {"source_id": str(source_id)}


async def _fail(source_id: uuid.UUID, ws: uuid.UUID, error: str) -> None:
    await _finish(source_id, ws, status="failed", error=error[:500])


@handler("ingest_file")
async def ingest_file(ctx: JobContext) -> dict[str, Any]:
    source_id = uuid.UUID(ctx.input["source_id"])
    async with SessionLocal() as db:
        source = await db.get(Source, source_id)
        file = await db.get(File, source.file_id)
        key, mime, filename = file.storage_key, file.mime, file.filename
    try:
        raw = await storage.read(key)
        await ctx.progress(40)
        meta: dict[str, Any] = {}
        title, text = "", ""
        if mime.startswith("image/"):
            meta = await asyncio.to_thread(image_meta, raw)
        elif mime == "application/pdf":
            meta, title, text = await asyncio.to_thread(pdf_text, raw)
        elif mime.startswith("audio/"):
            await ctx.progress(50)
            result = await stt.transcribe(raw, filename, mime, ctx.input.get("language"))
            text = result["text"]
            meta = {"duration_s": result["duration_s"], "language": result["language"]}
            await _save_transcript(source_id, result)
        async with SessionLocal() as db:
            await db.execute(
                update(File)
                .where(File.id == file.id)
                .values(sha256=hashlib.sha256(raw).hexdigest(), meta=meta)
            )
            await db.commit()
    except Exception as e:
        await _fail(source_id, ctx.workspace_id, f"{type(e).__name__}: {e}")
        raise
    values: dict[str, Any] = {"status": "ready", "text": text, "error": None}
    if title:
        values["title"] = title[:500]
    return await _finish(source_id, ctx.workspace_id, **values)


@handler("ingest_url")
async def ingest_url(ctx: JobContext) -> dict[str, Any]:
    source_id = uuid.UUID(ctx.input["source_id"])
    async with SessionLocal() as db:
        url = (await db.get(Source, source_id)).url
    try:
        final_url, html = await fetch_page(url)
        await ctx.progress(50)
        page = await asyncio.to_thread(extract_page, html, final_url)
    except Exception as e:
        await _fail(
            source_id, ctx.workspace_id, str(e) if isinstance(e, ValueError) else type(e).__name__
        )
        raise
    values = {"status": "ready", "error": None, **{k: v for k, v in page.items() if v}}
    if not page["text"]:
        values["error"] = "No main text found on this page"
    return await _finish(source_id, ctx.workspace_id, **values)


async def _save_transcript(source_id: uuid.UUID, result: dict[str, Any]) -> None:
    from sqlalchemy import delete

    async with SessionLocal() as db:
        await db.execute(delete(Transcript).where(Transcript.source_id == source_id))
        db.add(
            Transcript(
                source_id=source_id,
                language=result["language"],
                duration_s=result["duration_s"],
                model=get_settings().stt_model,
                segments=result["segments"],
            )
        )
        await db.commit()
