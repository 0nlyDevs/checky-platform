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
