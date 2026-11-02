"""Pictures as evidence: keyframes of a video, a 64-bit image fingerprint, faces blurred.

Derived files live next to the original in object storage, described in `file.meta`:

    image  {"dhash": "…16 hex…", "flat": bool, "faces": 0|n|None, "blur_key": key|None}
    video  {"keyframes": [{"at_s", "dhash", "flat", "faces", "key", "blur_key"}]}

`faces` is None when detection could not run: such a picture never leaves the desk.
"""

import asyncio
import io
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageStat

from app.core import storage

log = logging.getLogger("checky.media")

MAX_IMAGE_PIXELS = 20_000_000
# Measured in tests/test_media.py: a re-encoded or resized copy stays within 6 bits, an unrelated
# picture lands beyond 20. 10 leaves room for a light crop or a logo added in a corner.
SAME_IMAGE = 10
# A flat picture (a black frame, a white slide) hashes to almost nothing and would match anything.
MIN_STDDEV = 6.0
FRAMES_MIN, FRAMES_MAX = 4, 6
SCENE_THRESHOLD = 0.3


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
    """A JPEG copy with every detected face blurred, and how many were found.
    Raises when detection cannot run (the caller then lets no picture leave the desk)."""
    import cv2
    import numpy as np

    # Pillow reads what OpenCV cannot (GIF, upright EXIF orientation) and enforces the pixel cap.
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.width * opened.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds 20 megapixels")
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


def blur_key_of(key: str) -> str:
    return re.sub(r"(\.[A-Za-z0-9]{2,5})?$", ".blur.jpg", key, count=1)


async def faces_and_blur(raw: bytes, key: str) -> dict[str, Any]:
    """{faces, blur_key}: the blurred copy is stored next to `key` when a face was found."""
    try:
        blurred, n = await asyncio.to_thread(blur_faces, raw)
        if not n:
            return {"faces": 0, "blur_key": None}
        blur_key = blur_key_of(key)
        await storage.write(blur_key, blurred, "image/jpeg")
    except Exception:
        # No blurred copy means no picture leaves the desk; the upload itself is still read.
        log.warning("face blur failed for %s", key, exc_info=True)
        return {"faces": None, "blur_key": None}
    return {"faces": n, "blur_key": blur_key}


# --- frames ------------------------------------------------------------------------------------


async def _frame(ffmpeg: str, video: Path, at_s: float) -> bytes | None:
    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-ss",
        f"{at_s:.3f}",
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


async def scene_changes(ffmpeg: str, video: Path) -> list[float]:
    """Times (s) where the picture changes a lot, from ffmpeg's scene score. [] when unreadable."""
    proc = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-nostdin",
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


async def sample_frames(raw: bytes, duration_s: float, ffmpeg: str) -> list[dict]:
    """Keyframes of a video (scene changes, else evenly spaced), as JPEGs with their hash.
    Bounded at six frames; an unreadable frame is skipped, never fatal."""
    if not 0 < duration_s <= 6 * 3600:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "source-video"
        video.write_bytes(raw)
        times = frame_times(duration_s, await scene_changes(ffmpeg, video))
        limit = asyncio.Semaphore(2)

        async def sample(at_s: float) -> bytes | None:
            async with limit:
                return await _frame(ffmpeg, video, at_s)

        sampled = await asyncio.gather(*(sample(at_s) for at_s in times))
    frames = []
    for at_s, jpeg in zip(times, sampled, strict=True):
        if jpeg:
            frames.append({"at_s": at_s, "jpeg": jpeg, "dhash": dhash(jpeg), "flat": flat(jpeg)})
    return frames


# --- what ingest stores ----------------------------------------------------------------------


async def derive_image(raw: bytes, key: str) -> dict[str, Any]:
    """The meta an uploaded image gains: its hash, its faces and their blurred copy."""
    out: dict[str, Any] = {}
    try:
        out["dhash"] = await asyncio.to_thread(dhash, raw)
        out["flat"] = await asyncio.to_thread(flat, raw)
    except Exception:
        log.warning("no hash for %s", key, exc_info=True)
    out.update(await faces_and_blur(raw, key))
    return out


async def derive_video(raw: bytes, duration_s: float, key: str, ffmpeg: str) -> list[dict]:
    """Keyframes stored under `<key>/frames/`, each with its hash, faces and blurred copy."""
    out = []
    for i, frame in enumerate(await sample_frames(raw, duration_s, ffmpeg)):
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
