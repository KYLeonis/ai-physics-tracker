"""跨平台测试配置与运行时生成的视频 fixture。"""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def synthetic_video_path(tmp_path: Path) -> Path:
    """生成一个微型 CFR MJPEG 视频，避免向仓库提交媒体 fixture。"""

    path = tmp_path / "synthetic.avi"
    size = (64, 48)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        size,
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV MJPEG VideoWriter is unavailable")
    colors_bgr = (
        (0, 0, 255),
        (0, 255, 0),
        (255, 0, 0),
        (50, 100, 150),
        (0, 0, 0),
    )
    for color in colors_bgr:
        frame = np.full((size[1], size[0], 3), color, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    if not path.is_file():
        raise RuntimeError("OpenCV did not create the synthetic video")
    return path
