"""使用运行时生成的 CFR 视频测试 OpenCV 适配器。"""

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


def test_reader_sequential_fast_path_matches_seek_path_pixels(
    synthetic_video_path: Path,
) -> None:
    # 顺序读（fast path）与跳读（seek 路径）对同一帧必须返回相同像素
    reader = OpenCVVideoReader()
    reader.open(synthetic_video_path)

    sequential_pixels = [reader.read_frame(i).pixels_rgb for i in range(5)]

    reader2 = OpenCVVideoReader()
    reader2.open(synthetic_video_path)
    reader2.read_frame(0)  # 建立 _next_frame_position=1 后跳出顺序
    jumped = reader2.read_frame(3)
    resumed_sequential = reader2.read_frame(4)
    back_to_start = reader2.read_frame(0)

    for i, pixels in enumerate(sequential_pixels):
        assert pixels.shape == (48, 64, 3)
    assert jumped.frame_index == 3
    assert resumed_sequential.frame_index == 4
    assert back_to_start.frame_index == 0
    # 跳读路径拿到的帧 3/4 与顺序路径像素一致（MJPEG 无损于纯色帧）
    assert np.array_equal(jumped.pixels_rgb, sequential_pixels[3])
    assert np.array_equal(resumed_sequential.pixels_rgb, sequential_pixels[4])
    assert np.array_equal(back_to_start.pixels_rgb, sequential_pixels[0])


def test_reader_interleaved_order_keeps_frame_identity(
    synthetic_video_path: Path,
) -> None:
    # 交错请求顺序（前进、回退、再前进）帧内容始终与帧号一致
    reader = OpenCVVideoReader()
    reader.open(synthetic_video_path)

    # conftest 调色板 BGR → RGB：帧 0..4
    expected_rgb = [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (150, 100, 50),
        (0, 0, 0),
    ]

    order = (0, 1, 2, 1, 2, 3, 4, 0)
    center_colors = [reader.read_frame(i).pixels_rgb[24, 32] for i in order]

    for frame_index, color in zip(order, center_colors):
        assert tuple(int(c) for c in color) == pytest.approx(
            expected_rgb[frame_index], abs=5
        )
