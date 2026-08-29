"""Cross-platform test configuration and runtime-generated video fixtures."""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def synthetic_video_path(tmp_path: Path) -> Path:
    """Create a tiny CFR MJPEG video without committing media fixtures."""

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
