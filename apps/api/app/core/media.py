"""Pictures as evidence: keyframes of a video, a 64-bit image memory, faces blurred by default.

Derived files live next to the original in object storage, described in `file.meta`:

    image  {"dhash": "…16 hex…", "flat": bool, "faces": 0|n|None, "safe_key": key|None}
    video  {"keyframes": [{"at_s", "dhash", "flat", "faces", "key", "safe_key"}]}

`safe_key` is the only picture that is shown or leaves the desk: one frame, re-encoded as a JPEG
without EXIF, every detected face blurred. `faces` is None when detection could not run (or could
not cover the whole file, as with an animated GIF): there is then no safe copy, and the picture
stays hidden inside the desk until a journalist reveals the original.

Contract for other modules:
    frames_out(file) / image_out(file)        -> desk URLs, faces, reverse search on the blurred copy
    safe_url(file)                            -> a URL safe to leave the desk (faces blurred), or None
    await memory_matches(db, ws, source_id)   -> older pictures of the newsroom (and of verdicts
                                                 published by verified newsrooms) that look the same
"""

import asyncio
import io
import logging
import re
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageStat
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import dates, storage
from app.core.models import File, Item, Source, Workspace

log = logging.getLogger("checky.media")

MAX_IMAGE_PIXELS = 20_000_000
# Measured in tests/test_media.py: a re-encoded or resized copy stays within 6 bits, an unrelated
# picture lands beyond 20. 10 leaves room for a light crop or a logo added in a corner.
SAME_IMAGE = 10
# A flat picture (a black frame, a white slide) hashes to almost nothing and would match anything.
MIN_STDDEV = 6.0
FRAMES_MIN, FRAMES_MAX = 4, 6
SCENE_THRESHOLD = 0.3
# The plain containers an uploaded video may be (libavformat demuxer names: `mov` reads mp4, m4a,
# 3gp and QuickTime, `matroska` reads webm). Playlist and meta demuxers (hls, concat, image2…) are
# left out on purpose: their file can point ffmpeg at local paths or URLs.
VIDEO_DEMUXERS = ("mov", "matroska", "avi", "mpegts", "mpeg", "flv", "ogg")


# --- fingerprints ---------------------------------------------------------------------------------


def _gray(raw: bytes) -> Image.Image:
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.width * opened.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds 20 megapixels")
        return ImageOps.exif_transpose(opened).convert("L")


def dhash(raw: bytes) -> str:
    """Return a 64-bit difference hash; near copies have a small Hamming distance."""
    return dhash_image(_gray(raw))


def dhash_image(image: Image.Image) -> str:
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.get_flattened_data())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return f"{bits:016x}"


def flat(raw: bytes) -> bool:
    """True for a picture with almost no detail (its hash would match any other flat picture)."""
    return ImageStat.Stat(_gray(raw).resize((64, 64))).stddev[0] < MIN_STDDEV


def hamming(a: str, b: str) -> int:
    """Distance between two 64-bit fingerprints; malformed stored values never match."""
    if not isinstance(a, str) or not isinstance(b, str) or len(a) != 16 or len(b) != 16:
        return 64
    try:
        return (int(a, 16) ^ int(b, 16)).bit_count()
    except ValueError:
        return 64


def informative(h: str | None) -> bool:
    """A hash with too few (or too many) set bits comes from a near-uniform picture."""
    if not isinstance(h, str) or len(h) != 16:
        return False
    try:
        bits = int(h, 16).bit_count()
    except ValueError:
        return False
    return 6 <= bits <= 58


# --- faces -------------------------------------------------------------------------------------


def blur_faces(raw: bytes) -> tuple[bytes, int]:
    """A single-frame JPEG copy (no EXIF) with every detected face blurred, and how many were
    found. Raises when detection cannot run or cannot see every frame (animated GIF/WebP/PNG,
    multi-page TIFF): the caller then lets no picture leave the desk."""
    import cv2
    import numpy as np

    # Pillow reads what OpenCV cannot (GIF, upright EXIF orientation) and enforces the pixel cap.
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.width * opened.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds 20 megapixels")
        # Only the first frame would be checked; a face on a later one would pass unseen.
        if getattr(opened, "is_animated", False) or getattr(opened, "n_frames", 1) > 1:
            raise ValueError("Multi-frame image: faces cannot be checked")
        rgb = ImageOps.exif_transpose(opened).convert("RGB")
    pixels = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    detector = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    if detector.empty():
        raise RuntimeError("Face detector unavailable")
    gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
    height, width = pixels.shape[:2]
    for x, y, w, h in faces:
        # Enlarge the face box to include hair and chin; keep the source file untouched.
        pad = max(8, int(max(w, h) * 0.25))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(width, x + w + pad), min(height, y + h + pad)
        region = pixels[y0:y1, x0:x1]
        if region.size:
            pixels[y0:y1, x0:x1] = cv2.GaussianBlur(region, (0, 0), sigmaX=max(12, w / 3))
    ok, encoded = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise ValueError("Could not encode redacted preview")
    return encoded.tobytes(), len(faces)


def safe_key_of(key: str) -> str:
    return re.sub(r"(\.[A-Za-z0-9]{2,5})?$", ".safe.jpg", key, count=1)


async def faces_and_blur(raw: bytes, key: str) -> dict[str, Any]:
    """{faces, safe_key}: the safe copy (faces blurred, re-encoded) is stored next to `key`, even
    when no face was found, so the original never has to be shared."""
    try:
        blurred, n = await asyncio.to_thread(blur_faces, raw)
        safe_key = safe_key_of(key)
        await storage.write(safe_key, blurred, "image/jpeg")
    except Exception:
        # No safe copy means no picture leaves the desk; the upload itself is still read.
        log.warning("face blur failed for %s", key, exc_info=True)
        return {"faces": None, "safe_key": None}
    return {"faces": n, "safe_key": safe_key}


# --- frames ------------------------------------------------------------------------------------


def untrusted_input(container: str | None = None) -> list[str]:
    """ffmpeg/ffprobe options to put before `-i` for an uploaded file: it may only be read as a
    plain container (forced when probing named one), and only the file itself may be opened."""
    args = ["-protocol_whitelist", "file,pipe", "-format_whitelist", ",".join(VIDEO_DEMUXERS)]
    return [*args, "-f", container] if container else args


def video_demuxer(format_name: str | None) -> str | None:
    """The demuxer to force for what ffprobe found (`mov,mp4,m4a,3gp,3g2,mj2` -> `mov`), or None
    when it is not one of the plain containers."""
    names = [n for n in (format_name or "").split(",") if n]
    if not names or not set(names) & set(VIDEO_DEMUXERS):
        return None
    return next(n for n in names if n in VIDEO_DEMUXERS)


async def _frame(ffmpeg: str, video: Path, at_s: float, container: str | None) -> bytes | None:
    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-ss",
        f"{at_s:.3f}",
        *untrusted_input(container),
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        "scale='min(640,iw)':-2",
        "-q:v",
        "4",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=25)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return None
    return out if proc.returncode == 0 and out else None


async def scene_changes(ffmpeg: str, video: Path, container: str | None = None) -> list[float]:
    """Times (s) where the picture changes a lot, from ffmpeg's scene score. [] when unreadable."""
    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-nostdin",
        *untrusted_input(container),
        "-i",
        str(video),
        "-vf",
        f"scale=320:-2,select='gt(scene,{SCENE_THRESHOLD})',showinfo",
        "-an",
        "-f",
        "null",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return []
    return [float(x) for x in re.findall(rb"pts_time:([0-9.]+)", err)]


def frame_times(duration_s: float, scenes: list[float]) -> list[float]:
    """4 to 6 moments: the opening, then the scene changes; evenly spaced ones fill the gaps."""
    gap = max(0.3, duration_s / 20)
    picked = [0.0]
    for t in sorted(scenes):
        if len(picked) >= FRAMES_MAX:
            break
        if t < duration_s - 0.05 and all(abs(t - p) >= gap for p in picked):
            picked.append(t)
    if len(picked) < FRAMES_MIN:
        count = FRAMES_MAX - 1
        for i in range(1, count):
            t = duration_s * i / count
            if len(picked) < FRAMES_MAX and all(abs(t - p) >= gap for p in picked):
                picked.append(t)
    return sorted(round(t, 2) for t in picked)


async def sample_frames(
    raw: bytes, duration_s: float, ffmpeg: str, container: str | None = None
) -> list[dict]:
    """Keyframes of a video (scene changes, else evenly spaced), as JPEGs with their hash.
    Bounded at six frames; an unreadable frame is skipped, never fatal. `container` is the demuxer
    ffprobe found (`video_demuxer`); either way only the plain containers are read."""
    if not 0 < duration_s <= 6 * 3600:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "source-video"
        video.write_bytes(raw)
        times = frame_times(duration_s, await scene_changes(ffmpeg, video, container))
        limit = asyncio.Semaphore(2)

        async def sample(at_s: float) -> bytes | None:
            async with limit:
                return await _frame(ffmpeg, video, at_s, container)

        sampled = await asyncio.gather(*(sample(at_s) for at_s in times))
    frames = []
    for at_s, jpeg in zip(times, sampled, strict=True):
        if jpeg:
            frames.append({"at_s": at_s, "jpeg": jpeg, "dhash": dhash(jpeg), "flat": flat(jpeg)})
    return frames


# --- what ingest stores ----------------------------------------------------------------------


async def derive_image(raw: bytes, key: str) -> dict[str, Any]:
    """The meta an uploaded image gains: its hash, its faces and its safe copy."""
    out: dict[str, Any] = {}
    try:
        out["dhash"] = await asyncio.to_thread(dhash, raw)
        out["flat"] = await asyncio.to_thread(flat, raw)
    except Exception:
        log.warning("no hash for %s", key, exc_info=True)
    out.update(await faces_and_blur(raw, key))
    return out


async def derive_video(
    raw: bytes, duration_s: float, key: str, ffmpeg: str, container: str | None = None
) -> list[dict]:
    """Keyframes stored under `<key>/frames/`, each with its hash, faces and safe copy."""
    out = []
    for i, frame in enumerate(await sample_frames(raw, duration_s, ffmpeg, container)):
        frame_key = f"{key}/frames/{i}.jpg"
        await storage.write(frame_key, frame["jpeg"], "image/jpeg")
        out.append(
            {
                "at_s": frame["at_s"],
                "dhash": frame["dhash"],
                "flat": frame.get("flat", False),
                "key": frame_key,
                **await faces_and_blur(frame["jpeg"], frame_key),
            }
        )
    return out


def derived_keys(file: File) -> list[str]:
    """Every object ingest made from this file (keyframes, safe copies): they go with it, since an
    original frame shows faces unblurred."""
    meta = file.meta or {}
    keys = [meta.get("safe_key")]
    for i, frame in enumerate(meta.get("keyframes") or []):
        keys += [frame.get("key") or f"{file.storage_key}/frames/{i}.jpg", frame.get("safe_key")]
    return [k for k in keys if k]


# --- reading it back --------------------------------------------------------------------------


def shown_key(entry: dict[str, Any]) -> str | None:
    """The picture to show and share: the safe copy, never the original; nothing while faces are
    unchecked."""
    return entry.get("safe_key") if entry.get("faces") is not None else None


def _shown(key: str | None) -> dict[str, Any]:
    """The desk URL of a picture and the reverse-search links built on that same picture: what
    Google Lens, TinEye or Yandex receive leaves the desk, so it is the blurred copy, and nothing
    at all while faces are unchecked (a journalist reveals the original on purpose instead)."""
    from app.modules.linkcheck import reverse_search

    if not key:
        return {"image_url": None, "reverse_search": []}
    url = storage.presign_download(key)
    return {"image_url": url, "reverse_search": reverse_search(url)}


def frames_out(file: File) -> list[dict[str, Any]]:
    """A video file's keyframes for the desk: the default picture, faces, reverse search."""
    out = []
    for i, frame in enumerate((file.meta or {}).get("keyframes") or []):
        out.append(
            {
                "index": i,
                "at_s": frame["at_s"],
                "dhash": frame.get("dhash", ""),
                "faces": frame.get("faces"),
                **_shown(shown_key(frame)),
            }
        )
    return out


def image_out(file: File) -> dict[str, Any] | None:
    """An image file's default picture for the desk (blurred when it shows faces)."""
    if not file.mime.startswith("image/") or file.status != "ready":
        return None
    meta = file.meta or {}
    return {"faces": meta.get("faces"), **_shown(shown_key(meta))}


def safe_url(file: File | None) -> str | None:
    """A picture of this file that may leave the desk: faces blurred, or None (no picture, or
    faces not checked). Videos give their first informative keyframe."""
    if file is None or file.status != "ready":
        return None
    meta = file.meta or {}
    if file.mime.startswith("image/"):
        key = shown_key(meta)
        return storage.presign_download(key) if key else None
    for frame in meta.get("keyframes") or []:
        if not frame.get("flat") and (key := shown_key(frame)):
            return storage.presign_download(key)
    return None


def _hashes(file: File) -> list[tuple[str, float | None]]:
    meta = file.meta or {}
    if meta.get("dhash") and not meta.get("flat"):
        return [(meta["dhash"], None)]
    return [
        (f["dhash"], f.get("at_s"))
        for f in meta.get("keyframes") or []
        if f.get("dhash") and not f.get("flat")
    ]


def _date_of(source: Source, file: File) -> tuple[date | None, str]:
    if day := dates.parse(source.published_at):
        return day, "published"
    meta = file.meta or {}
    exif = meta.get("exif") or {}
    for value, basis in (
        (exif.get("DateTimeOriginal") or exif.get("DateTime"), "exif"),
        ((meta.get("tags") or {}).get("creation_time"), "video"),
    ):
        if day := dates.parse(value):
            return day, basis
    added = source.created_at.astimezone(dates.EAT).date() if source.created_at else None
    return added, "added"


async def memory_matches(
    db: AsyncSession, ws: uuid.UUID, source_id: uuid.UUID, limit: int = 5
) -> list[dict[str, Any]]:
    """The newsroom's own pictures and frames, and those of verdicts published by public
    newsrooms, that look like this source's (Hamming ≤ SAME_IMAGE), oldest first.

    Each: {source_id, title, kind, item_id, ref, verdict_id, newsroom, own, date, date_basis,
    days_before (their date before today), distance, at_s (ours), their_at_s, line}."""
    source = await db.get(Source, source_id)
    file = await db.get(File, source.file_id) if source and source.file_id else None
    if file is None:
        return []
    ours = [(h, t) for h, t in _hashes(file) if informative(h)]
    if not ours:
        return []
    has_picture = or_(File.meta.has_key("dhash"), File.meta.has_key("keyframes"))
    published = and_(Workspace.publishes, Item.status == "published", Source.workspace_id != ws)
    rows = (
        await db.execute(
            select(Source, File, Item, Workspace)
            .join(File, File.id == Source.file_id)
            .join(Workspace, Workspace.id == Source.workspace_id)
            .outerjoin(Item, Item.id == Source.item_id)
            .where(
                has_picture,
                Source.id != source.id,
                File.id != file.id,
                Source.status == "ready",
                or_(Source.workspace_id == ws, published),
            )
            .order_by(Source.created_at.desc())
            .limit(2000)
        )
    ).all()
    today = dates.today()
    found: dict[uuid.UUID, dict[str, Any]] = {}
    for other, other_file, item, newsroom in rows:
        best = None
        for theirs, their_at in _hashes(other_file):
            if not informative(theirs):
                continue
            for h, at in ours:
                d = hamming(h, theirs)
                if d <= SAME_IMAGE and (best is None or d < best[0]):
                    best = (d, at, their_at)
        if best is None:
            continue
        day, basis = _date_of(other, other_file)
        own = other.workspace_id == ws
        match = {
            "source_id": str(other.id),
            "title": other.title,
            "kind": other.kind,
            "item_id": str(item.id) if item and own else None,
            "ref": (item.data or {}).get("ref") if item else None,
            "verdict_id": str(item.id) if item and not own else None,
            "newsroom": None if own else newsroom.name,
            "own": own,
            "date": day.isoformat() if day else None,
            "date_basis": basis,
            "days_before": (today - day).days if day else None,
            "distance": best[0],
            "at_s": best[1],
            "their_at_s": best[2],
        }
        match["line"] = memory_line(match)
        found[other.id] = match
    return sorted(found.values(), key=lambda m: (m["date"] or "9999", m["distance"]))[:limit]


def memory_line(match: dict[str, Any]) -> str:
    """« Image déjà vue le 14 mars 2023 dans [titre] » (the date comes from code)."""
    day = dates.parse(match.get("date"))
    if day and match.get("date_basis") == "added":
        when = f" (entrée dans la rédaction le {dates.fr(day)})"
    else:
        when = f" le {dates.fr(day)}" if day else ""
    where = match["title"] + (f" ({match['newsroom']})" if match.get("newsroom") else "")
    return f"Image déjà vue{when} dans {where}"
