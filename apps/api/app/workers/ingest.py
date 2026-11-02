"""Ingest jobs: turn an uploaded file or a URL into a ready source.

`ingest_file`: hash the object, read EXIF (images) or text (PDFs), transcribe audio and the
soundtrack of videos (ffmpeg pulls it out when installed; Whisper reads mp4/webm as they are).
`ingest_url`:  fetch the page (public addresses only) and extract its main text.
"""

import asyncio
import hashlib
import io
import ipaddress
import json
import logging
import re
import shutil
import socket
import tempfile
import uuid
from datetime import timedelta
from html import unescape as html_unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import update

from app.core import dates, media, storage, stt
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import File, Source, Transcript
from app.realtime.server import emit
from app.workers.queue import JobContext, handler

MAX_PAGE_BYTES = 5 * 1024 * 1024
log = logging.getLogger("checky.ingest")
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
    await _public_addresses(url)


async def _public_addresses(url: str) -> list[str]:
    parsed = urlparse(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Only public http and https links without credentials can be added")
    addresses = await asyncio.to_thread(_resolve, parsed.hostname)
    if not addresses:
        raise ValueError("The address did not resolve")
    for a in addresses:
        ip = ipaddress.ip_address(a)
        if not ip.is_global or ip.is_multicast:
            raise ValueError("This address is not reachable from the public internet")
    return sorted(set(addresses), key=lambda address: ipaddress.ip_address(address).version)


async def fetch_raw(url: str) -> tuple[str, str, bytes, str | None]:
    """GET a public URL, following up to 5 redirects, each one checked.
    Returns (final url, content type, body, encoding)."""
    async with httpx.AsyncClient(transport=_transport, timeout=15, headers=HEADERS) as http:
        for _ in range(6):
            addresses = await _public_addresses(url)
            original = httpx.URL(url)
            # Pin the checked IP instead of resolving the domain a second time in the HTTP
            # transport (DNS rebinding). Preserve the domain for Host and TLS verification.
            # Mock transports do no networking and keep the original URL for fixture routing.
            target = original.copy_with(host=addresses[0]) if _transport is None else original
            async with http.stream(
                "GET",
                target,
                headers={"Host": original.netloc.decode("ascii")},
                extensions={"sni_hostname": original.raw_host.decode("ascii")},
            ) as resp:
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
                kind = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                return url, kind, bytes(body), resp.encoding
    raise ValueError("Too many redirects")


async def fetch_page(url: str) -> tuple[str, str]:
    """GET a page (see fetch_raw). Returns (final url, html)."""
    final, _, body, encoding = await fetch_raw(url)
    return final, body.decode(encoding or "utf-8", errors="replace")


def page_meta(html: str) -> dict[str, str]:
    """Open Graph tags: social networks often only show these to visitors without an account."""
    out: dict[str, str] = {}
    for tag in re.findall(r"<meta\b[^>]*>", html[:300_000], re.IGNORECASE):
        prop = re.search(r'(?:property|name)\s*=\s*["\']([^"\']+)', tag, re.IGNORECASE)
        content = re.search(r'content\s*=\s*["\']([^"\']*)', tag, re.IGNORECASE)
        if prop and content:
            key = prop.group(1).lower()
            if key in (
                "og:title",
                "og:description",
                "og:image",
                "og:site_name",
                "article:published_time",
                "description",
            ):
                out.setdefault(key, html_unescape(content.group(1)).strip()[:2000])
    return out


def page_date(html: str, guessed: str | None) -> str | None:
    """The page's publication date (ISO day). The page's own metadata (Open Graph, JSON-LD) wins.
    A date found only by trafilatura's heuristics that falls today or yesterday is usually the
    site's header showing the current day, on an article of any age: unknown is safer, since a
    wrong "today" would make an old page look current."""
    ld = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html[:500_000])
    structured = dates.parse(page_meta(html).get("article:published_time")) or dates.parse(
        ld.group(1) if ld else None
    )
    if structured:
        return structured.isoformat()
    found = dates.parse(guessed)
    if found is None or found >= dates.today() - timedelta(days=1):
        return None
    return found.isoformat()


def extract_page(html: str, url: str) -> dict[str, Any]:
    import trafilatura

    doc = trafilatura.bare_extraction(html, url=url, with_metadata=True, include_tables=False)
    if doc is None:
        return {"title": "", "author": None, "published_at": page_date(html, None), "text": ""}
    data = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
    return {
        "title": (data.get("title") or "")[:500],
        "author": (data.get("author") or None),
        "published_at": page_date(html, data.get("date")),
        "text": (data.get("text") or "")[:MAX_TEXT_CHARS],
    }


# Traces generators and editors leave inside a file (EXIF, PNG text chunks, XMP, C2PA manifests).
# Finding one is a strong hint; finding none proves nothing (re-saving or a screenshot strips them).
# (marker, label, searched in the whole file too); ordinary words are only matched in metadata text.
AI_MARKERS = [
    ("trainedalgorithmicmedia", "IPTC : média généré par IA", True),
    ("compositewithtrainedalgorithmicmedia", "IPTC : retouché par IA", True),
    ("midjourney", "Midjourney", True),
    ("stable diffusion", "Stable Diffusion", True),
    ("adobe firefly", "Adobe Firefly", True),
    ("dall-e", "DALL·E", True),
    ("dall·e", "DALL·E", True),
    ("gpt-image", "OpenAI", True),
    ("comfyui", "ComfyUI", False),
    ("imagen", "Google Imagen", False),
    ("grok", "Grok", False),
    ("flux", "FLUX", False),
    # Video generators, only trusted in the container's metadata tags.
    ("sora", "OpenAI Sora", False),
    ("veo", "Google Veo", False),
    ("runway", "Runway", False),
    ("kling", "Kling", False),
    ("pika", "Pika", False),
    ("hailuo", "Hailuo", False),
    ("luma", "Luma", False),
]
C2PA_MARKERS = (b"c2pa", b"jumbf")


def ai_signals(raw: bytes, texts: list[str]) -> dict[str, Any]:
    """Generator names found in the file, and whether it carries Content Credentials (C2PA)."""
    blob = raw[:4_000_000].lower()
    meta_text = " ".join(texts).lower()
    whole = meta_text + " " + blob.decode("latin-1")
    found = []
    for marker, label, anywhere in AI_MARKERS:
        hay = whole if anywhere else meta_text
        if re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", hay) and label not in found:
            found.append(label)
    return {"ai_markers": found, "content_credentials": any(m in blob for m in C2PA_MARKERS)}


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
        # PNG text chunks: Stable Diffusion writes "parameters", ComfyUI "prompt" and "workflow".
        chunks = [str(v)[:2000] for v in img.info.values() if isinstance(v, (str, bytes))]
    picked = {
        k: str(tags[k])[:200]
        for k in ("Make", "Model", "Software", "DateTimeOriginal", "DateTime", "Artist")
        if k in tags
    }
    if gps:
        picked["GPS"] = {ExifTags.GPSTAGS.get(k, str(k)): str(v)[:100] for k, v in gps.items()}
    meta["exif"] = picked
    texts = [str(v) for v in tags.values() if isinstance(v, (str, bytes))] + chunks
    meta.update(ai_signals(raw, texts))
    return meta


# Whisper takes these containers as they are; anything else needs ffmpeg.
WHISPER_VIDEO = {"video/mp4": "mp4", "video/webm": "webm"}


async def _run(*cmd: str) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=120)
    if proc.returncode:
        raise ValueError(f"{Path(cmd[0]).name} failed: {err.decode(errors='replace')[-200:]}")
    return out


async def video_meta_and_audio(raw: bytes, mime: str) -> tuple[dict[str, Any], bytes, str, str]:
    """The container's facts (duration, size, encoder tags, AI traces) and its soundtrack as a
    small mono mp3. Without ffmpeg, mp4/webm go to Whisper whole and the facts are the AI traces.
    Tests swap this out."""
    if not (ffmpeg := shutil.which("ffmpeg")):
        if mime not in WHISPER_VIDEO:
            raise ValueError("ffmpeg is needed to read this video format")
        return ai_signals(raw, []), raw, f"video.{WHISPER_VIDEO[mime]}", mime
    with tempfile.TemporaryDirectory() as tmp:
        src, mp3 = Path(tmp) / "in", Path(tmp) / "audio.mp3"
        src.write_bytes(raw)
        meta: dict[str, Any] = {}
        texts: list[str] = []
        if ffprobe := shutil.which("ffprobe"):
            probe = json.loads(
                await _run(
                    ffprobe,
                    "-v",
                    "quiet",
                    *media.untrusted_input(),
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(src),
                )
            )
            fmt = probe.get("format") or {}
            # A playlist or meta file (hls, concat…) could make ffmpeg read local files or URLs.
            if not (container := media.video_demuxer(fmt.get("format_name"))):
                raise ValueError("Unsupported video container")
            meta["container"] = container
            video = next(
                (x for x in probe.get("streams") or [] if x.get("codec_type") == "video"), {}
            )
            tags = {**(fmt.get("tags") or {}), **(video.get("tags") or {})}
            texts = [f"{k} {v}" for k, v in tags.items()]
            if fmt.get("duration"):
                meta["duration_s"] = round(float(fmt["duration"]), 2)
            if video.get("width"):
                meta.update(width=video["width"], height=video.get("height"))
            picked = {
                k: str(v)[:200]
                for k, v in tags.items()
                if k.lower()
                in (
                    "encoder",
                    "creation_time",
                    "com.apple.quicktime.make",
                    "com.apple.quicktime.model",
                    "com.apple.quicktime.software",
                    "handler_name",
                    "comment",
                    "artist",
                )
            }
            if picked:
                meta["tags"] = picked
            if not any(x.get("codec_type") == "audio" for x in probe.get("streams") or []):
                meta.update(ai_signals(raw, texts))
                return meta, b"", "", ""
        meta.update(ai_signals(raw, texts))
        await _run(
            ffmpeg,
            "-v",
            "error",
            *media.untrusted_input(meta.get("container")),
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "48k",
            "-y",
            str(mp3),
        )
        return meta, mp3.read_bytes(), "audio.mp3", "audio/mpeg"


def pdf_text(raw: bytes) -> tuple[dict[str, Any], str, str]:
    """(meta, title, text) of a PDF."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    pages = [p.extract_text() or "" for p in reader.pages]
    info = reader.metadata or {}
    title = str(info.get("/Title") or "").strip()
    meta: dict[str, Any] = {"pages": len(pages)}
    if created := dates.parse(str(info.get("/CreationDate") or "")):
        meta["created_at"] = created.isoformat()
    return meta, title, "\n\n".join(pages)[:MAX_TEXT_CHARS]


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
            meta.update(await media.derive_image(raw, key))
        elif mime == "application/pdf":
            meta, title, text = await asyncio.to_thread(pdf_text, raw)
        elif mime.startswith("audio/"):
            await ctx.progress(50)
            result = await stt.transcribe(raw, filename, mime, ctx.input.get("language"))
            text = result["text"]
            meta = {"duration_s": result["duration_s"], "language": result["language"]}
            await _save_transcript(source_id, result)
        elif mime.startswith("video/"):
            meta, audio, audio_name, audio_mime = await video_meta_and_audio(raw, mime)
            if ffmpeg := shutil.which("ffmpeg"):
                try:
                    duration = float(meta.get("duration_s") or 0)
                    container = meta.get("container")
                    if frames := await media.derive_video(raw, duration, key, ffmpeg, container):
                        meta["keyframes"] = frames
                except Exception:
                    # A damaged frame never loses the video, soundtrack or transcript.
                    log.warning(
                        "could not derive keyframes for source %s", source_id, exc_info=True
                    )
            await ctx.progress(50)
            if audio:
                result = await stt.transcribe(
                    audio, audio_name, audio_mime, ctx.input.get("language")
                )
                text = result["text"]
                meta.update(
                    duration_s=meta.get("duration_s") or result["duration_s"],
                    language=result["language"],
                )
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
    if meta.get("created_at"):
        values["published_at"] = meta["created_at"]  # a PDF's own creation date
    result = await _finish(source_id, ctx.workspace_id, **values)
    if text:
        await _queue_embedding(ctx, source_id)
    return result


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
    result = await _finish(source_id, ctx.workspace_id, **values)
    if page["text"]:
        await _queue_embedding(ctx, source_id)
    return result


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


async def _queue_embedding(ctx: JobContext, source_id: uuid.UUID) -> None:
    from app.modules.rag import queue_embedding  # avoid an import cycle at module load

    async with SessionLocal() as db:
        await queue_embedding(db, ctx.workspace_id, ctx.created_by, source_id)
