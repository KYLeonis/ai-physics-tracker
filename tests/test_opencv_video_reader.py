"""OpenCV adapter tests using a runtime-generated CFR video."""

from pathlib import Path

import numpy as np
import pytest

from ai_physics_tracker.application.video import VideoFrameError, VideoOpenError
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


def test_reader_opens_metadata_and_decodes_zero_based_rgb_frames(
    synthetic_video_path: Path,
) -> None:
    reader = OpenCVVideoReader()

    info = reader.open(synthetic_video_path)
    first = reader.read_frame(0)
    second = reader.read_frame(1)
    last = reader.read_frame(4)
    first_again = reader.read_frame(0)

    assert (info.width_px, info.height_px) == (64, 48)
    assert info.frame_count == 5
    assert info.fps_container == pytest.approx(10.0, abs=1e-9)
    assert info.timing_status == "unknown"
    assert first.frame_index == 0
    assert first.pixels_rgb.shape == (48, 64, 3)
    assert first.pixels_rgb[24, 32] == pytest.approx(
        np.array([255, 0, 0]), abs=5
    )
    assert second.pixels_rgb[24, 32] == pytest.approx(
        np.array([0, 255, 0]), abs=5
    )
    assert not first.pixels_rgb.flags.writeable
    assert last.frame_index == 4
    assert first_again.frame_index == 0


def test_reader_rejects_out_of_range_frames(synthetic_video_path: Path) -> None:
    reader = OpenCVVideoReader()
    reader.open(synthetic_video_path)

    with pytest.raises(VideoFrameError, match="outside"):
        reader.read_frame(-1)
    with pytest.raises(VideoFrameError, match="outside"):
        reader.read_frame(5)


def test_reader_close_is_idempotent_and_releases_file(synthetic_video_path: Path) -> None:
    reader = OpenCVVideoReader()
    reader.open(synthetic_video_path)

    reader.close()
    reader.close()
    renamed = synthetic_video_path.with_name("renamed.avi")
    synthetic_video_path.rename(renamed)

    assert not reader.is_open
    assert renamed.is_file()
    with pytest.raises(VideoFrameError, match="no video"):
        reader.read_frame(0)


def test_reader_rejects_missing_and_corrupt_files(tmp_path: Path) -> None:
    reader = OpenCVVideoReader()
    corrupt = tmp_path / "corrupt.avi"
    corrupt.write_bytes(b"not a video")

    with pytest.raises(VideoOpenError, match="not found"):
        reader.open(tmp_path / "missing.avi")
    with pytest.raises(VideoOpenError, match="could not open"):
        reader.open(corrupt)
