import asyncio
import io
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.core import media
from app.core.media import blur_faces, dhash, frame_times, hamming, informative, sample_frames

FACE = Path(__file__).parent / "fixtures" / "face-public-domain.jpg"


def test_difference_hash_tolerates_a_copy_but_not_an_unrelated_image():
    image = Image.new("RGB", (64, 64))
    image.putdata([(x * 4, y * 4, 20) for y in range(64) for x in range(64)])
    original = io.BytesIO()
    image.save(original, format="PNG")
    copied = io.BytesIO()
    image.save(copied, format="JPEG", quality=80)
    inverted = Image.new("RGB", (64, 64))
    inverted.putdata([(255 - x * 4, y * 4, 20) for y in range(64) for x in range(64)])
    other = io.BytesIO()
    inverted.save(other, format="PNG")

    assert hamming(dhash(original.getvalue()), dhash(copied.getvalue())) <= 6
    assert hamming(dhash(original.getvalue()), dhash(other.getvalue())) > 20
    assert hamming("bad", dhash(original.getvalue())) == 64


def test_video_frames_cover_its_length_and_are_jpegs(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is not installed")
    video = tmp_path / "four-seconds.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x90:rate=2:duration=4",
            "-c:v",
            "mpeg4",
            str(video),
        ],
        check=True,
        timeout=15,
    )
    frames = asyncio.run(sample_frames(video.read_bytes(), 4, ffmpeg))
    assert 4 <= len(frames) <= 6
    times = [frame["at_s"] for frame in frames]
    assert times[0] == 0.0 and times == sorted(times) and times[-1] < 4
    assert all(frame["jpeg"].startswith(b"\xff\xd8") for frame in frames)
    assert len({frame["dhash"] for frame in frames}) > 1


def test_detected_face_region_is_blurred_before_the_preview_is_saved(monkeypatch):
    import cv2
    import numpy as np

    class Detector:
        def empty(self):
            return False

        def detectMultiScale(self, gray, **kwargs):
            return [(24, 24, 32, 32)]

    monkeypatch.setattr(cv2, "CascadeClassifier", lambda path: Detector())
    pixels = np.indices((96, 96)).sum(axis=0) % 2 * 255
    image = Image.fromarray(pixels.astype("uint8"), mode="L")
    source = io.BytesIO()
    image.save(source, format="JPEG", quality=95)
    preview, count = blur_faces(source.getvalue())
    before = np.array(Image.open(io.BytesIO(source.getvalue())).convert("L"))
    after = np.array(Image.open(io.BytesIO(preview)).convert("L"))
    assert count == 1
    assert after[40:55, 40:55].var() < before[40:55, 40:55].var() / 4


def test_frame_times_prefer_scene_changes_and_fill_with_even_spacing():
    # Enough scene changes: the opening plus the changes, at most six.
    assert frame_times(60, [5, 12, 20, 33, 41, 50, 55]) == [0.0, 5, 12, 20, 33, 41]
    # Too few: evenly spaced moments fill up to the minimum, away from the changes found.
    picked = frame_times(10, [3.9])
    assert 4 <= len(picked) <= 6 and picked[0] == 0.0 and 3.9 in picked
    # Changes too close to each other or to the end are not taken twice.
    assert frame_times(10, [0.1, 9.99]) == [0.0, 2.0, 4.0, 6.0, 8.0]


def test_flat_pictures_never_count_as_a_match():
    black = io.BytesIO()
    Image.new("RGB", (64, 64), "black").save(black, format="PNG")
    assert media.flat(black.getvalue())
    assert not informative(dhash(black.getvalue()))
    assert not informative("bad")


def test_a_real_face_is_found_and_blurred():
    raw = FACE.read_bytes()
    preview, count = blur_faces(raw)
    assert count >= 1
    assert hamming(dhash(raw), dhash(preview)) > 0


def test_only_plain_video_containers_are_read():
    assert media.video_demuxer("mov,mp4,m4a,3gp,3g2,mj2") == "mov"
    assert media.video_demuxer("matroska,webm") == "matroska"
    for playlist in ("hls", "concat", "image2", "", None):
        assert media.video_demuxer(playlist) is None
    args = media.untrusted_input("mov")
    assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
    assert "hls" not in args[args.index("-format_whitelist") + 1].split(",")
    assert args[-2:] == ["-f", "mov"]


def test_every_ffmpeg_call_on_a_video_is_confined_before_its_input(monkeypatch):
    calls = []

    class Proc:
        returncode = 0

        async def communicate(self):
            return b"\xff\xd8", b""

    async def spawn(*cmd, **kwargs):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr(media.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(media, "dhash", lambda raw: "0" * 16)
    monkeypatch.setattr(media, "flat", lambda raw: False)
    asyncio.run(sample_frames(b"video", 10, "ffmpeg", "matroska"))
    assert calls
    for cmd in calls:
        i = cmd.index("-i")
        assert "-protocol_whitelist" in cmd[:i] and "-format_whitelist" in cmd[:i]
        assert cmd[i - 2 : i] == ("-f", "matroska")


def test_a_playlist_upload_is_refused_before_ffmpeg_reads_it(monkeypatch):
    import json

    from app.workers import ingest

    runs = []

    async def run(*cmd):
        runs.append(cmd)
        return json.dumps({"format": {"format_name": "hls"}, "streams": []}).encode()

    monkeypatch.setattr(ingest, "_run", run)
    monkeypatch.setattr(ingest.shutil, "which", lambda name: f"/usr/bin/{name}")
    with pytest.raises(ValueError, match="container"):
        asyncio.run(ingest.video_meta_and_audio(b"#EXTM3U", "video/mp4"))
    [probe] = runs
    assert "-protocol_whitelist" in probe and "-format_whitelist" in probe


def test_real_ffprobe_refuses_a_playlist_pointing_at_a_local_file(tmp_path):
    from app.workers import ingest

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg is not installed")
    secret = tmp_path / "secret.mp4"
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1"]
        + ["-c:v", "mpeg4", str(secret)],
        check=True,
        timeout=15,
    )
    playlist = f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile://{secret}\n#EXT-X-ENDLIST\n"
    named = tmp_path / "upload.m3u8"  # an extension ffprobe trusts; ingest never keeps the name
    named.write_text(playlist)
    probe = [shutil.which("ffprobe"), "-v", "error", "-show_entries", "format=format_name"]
    found = subprocess.run([*probe, str(named)], capture_output=True, check=True, timeout=15)
    assert b"hls" in found.stdout
    refused = subprocess.run(
        [*probe, *media.untrusted_input(), str(named)], capture_output=True, check=False, timeout=15
    )
    assert refused.returncode != 0 and b"whitelist" in refused.stderr
    with pytest.raises(ValueError):
        asyncio.run(ingest.video_meta_and_audio(playlist.encode(), "video/mp4"))
    assert asyncio.run(sample_frames(playlist.encode(), 1, ffmpeg)) == []
    meta, *_ = asyncio.run(ingest.video_meta_and_audio(secret.read_bytes(), "video/mp4"))
    assert meta["container"] == "mov"


def test_the_safe_copy_is_one_frame_without_exif():
    exif = Image.Exif()
    exif[0x010F] = "Canon"
    photo = io.BytesIO()
    Image.new("RGB", (48, 48), "white").save(photo, format="JPEG", exif=exif)
    copy, faces = blur_faces(photo.getvalue())
    assert faces == 0 and copy.startswith(b"\xff\xd8")
    assert not Image.open(io.BytesIO(copy)).getexif()

    pages = io.BytesIO()
    first, second = Image.new("RGB", (32, 32), "red"), Image.new("RGB", (32, 32), "blue")
    first.save(pages, format="TIFF", save_all=True, append_images=[second])
    with pytest.raises(ValueError, match="Multi-frame"):
        blur_faces(pages.getvalue())
