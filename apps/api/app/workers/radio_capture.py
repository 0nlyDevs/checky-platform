"""Server capture for « À l'antenne »: record a minute of each partner radio's stream.

`RADIO_STREAMS` is a comma list of "Station|https://stream.url|Region|language" (region and
language optional; language `fr` or `mg`, default `fr`). For each stream, ffmpeg records
`CAPTURE_SECONDS` to a small mono mp3, which is stored like any upload and becomes an audio source
(transcribed by the usual `ingest_file` job) and a clip with `origin="capture"`. A French clip
takes its transcript once ready; a Malagasy one waits for a veilleur's sentence. Off unless
streams are set; skipped quietly without ffmpeg or storage.
"""

import asyncio
import hashlib
import logging
import shutil
import uuid
from dataclasses import dataclass
from typing import Any

from app.core import dates, storage
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import File, RadioClip, Source
from app.workers.queue import JobContext, enqueue, handler

log = logging.getLogger("checky.radio_capture")
CAPTURE_SECONDS = 60


@dataclass(frozen=True)
class Stream:
    station: str
    url: str
    region: str | None
    language: str


def parse_streams(raw: str | None) -> list[Stream]:
    """« Station|https://…|Region|mg , … » → streams; entries without a station or an http(s)
    URL are left out."""
    streams = []
    for part in (raw or "").split(","):
        fields = [f.strip() for f in part.split("|")]
        if len(fields) < 2 or not fields[0]:
            continue
        station, url = fields[0], fields[1]
        if not url.startswith(("http://", "https://")):
            continue
        region = fields[2] if len(fields) > 2 and fields[2] else None
        language = fields[3].lower() if len(fields) > 3 and fields[3] else "fr"
        streams.append(
            Stream(
                station=station[:120],
                url=url,
                region=region,
                language=language if language in ("fr", "mg") else "fr",
            )
        )
    return streams


async def record_stream(url: str, seconds: int, ffmpeg: str) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-v",
        "error",
        "-t",
        str(seconds),
        "-i",
        url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "48k",
        "-f",
        "mp3",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=seconds + 60)
    if proc.returncode or not out:
        raise ValueError(f"ffmpeg failed: {err.decode(errors='replace')[-200:]}")
    return out


async def _put(key: str, data: bytes) -> None:
    await asyncio.to_thread(
        storage.client().put_object,
        Bucket=get_settings().storage_bucket,
        Key=key,
        Body=data,
        ContentType="audio/mpeg",
    )


async def _capture(ctx: JobContext, stream: Stream, ffmpeg: str, seconds: int) -> str:
    from app.modules.veille import canonical_region, region_of_text

    audio = await record_stream(stream.url, seconds, ffmpeg)
    heard = dates.now()
    file_id = uuid.uuid4()
    key = f"ws/{ctx.workspace_id}/{file_id}/capture-{heard:%Y%m%d-%H%M}.mp3"
    await _put(key, audio)
    location = region_of_text(stream.region, stream.station) or {}
    if stream.region and not location:
        location = {"name": stream.region, "region": canonical_region(stream.region)}
    async with SessionLocal() as db:
        db.add(
            File(
                id=file_id,
                workspace_id=ctx.workspace_id,
                uploaded_by=ctx.created_by,
                storage_key=key,
                filename=f"{stream.station} {heard:%Y-%m-%d %H:%M}.mp3",
                mime="audio/mpeg",
                size_bytes=len(audio),
                sha256=hashlib.sha256(audio).hexdigest(),
                status="ready",
            )
        )
        source = Source(
            workspace_id=ctx.workspace_id,
            file_id=file_id,
            created_by=ctx.created_by,
            kind="audio",
            title=f"Antenne · {stream.station} · {dates.fr(heard.date())} {heard:%H:%M}"[:500],
            published_at=heard.date().isoformat(),
        )
        db.add(source)
        await db.flush()
        db.add(
            RadioClip(
                workspace_id=ctx.workspace_id,
                created_by=ctx.created_by,
                source_id=source.id,
                station=stream.station,
                location=location,
                recorded_at=heard,
                language=stream.language,
                origin="capture",
                clip_at_s=0.0,
            )
        )
        await db.commit()
        await enqueue(
            db,
            ctx.workspace_id,
            ctx.created_by,
            "ingest_file",
            {"source_id": str(source.id), "language": stream.language},
        )
    return str(source.id)


@handler("radio_capture")
async def radio_capture(ctx: JobContext) -> dict[str, Any]:
    streams = parse_streams(get_settings().radio_streams)
    if not streams:
        return {"skipped": "no_streams"}
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {"skipped": "no_ffmpeg"}
    if not storage.configured():
        return {"skipped": "no_storage"}
    seconds = int(ctx.input.get("seconds") or CAPTURE_SECONDS)
    captured, failed = [], []
    for stream in streams:
        try:
            captured.append(await _capture(ctx, stream, ffmpeg, seconds))
        except Exception as e:  # noqa: BLE001 - one silent station must not stop the others
            log.warning("capture of %s failed: %s", stream.station, e)
            failed.append(stream.station)
    return {"captured": len(captured), "failed": failed}
