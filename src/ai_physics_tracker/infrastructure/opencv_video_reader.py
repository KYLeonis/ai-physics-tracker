"""OpenCV adapter implementing the application VideoReader port."""

import logging
from math import isfinite
from pathlib import Path

import cv2
import numpy as np

from ai_physics_tracker.application.video import (
    DecodedFrame,
    VideoFrameError,
    VideoOpenError,
    VideoStreamInfo,
)

logger = logging.getLogger(__name__)


class OpenCVVideoReader:
    """Synchronous random-access reader with explicit file ownership."""

    def __init__(self) -> None:
        self._capture: cv2.VideoCapture | None = None
        self._info: VideoStreamInfo | None = None
        self._path: Path | None = None

    @property
    def is_open(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    @property
    def info(self) -> VideoStreamInfo:
        if self._info is None:
            raise VideoOpenError("no video is open")
        return self._info

    def open(self, path: Path) -> VideoStreamInfo:
        """Open a local file and validate metadata required by Timeline."""

        self.close()
        if not path.is_file():
            raise VideoOpenError(f"video file not found: {path}")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            capture.release()
            raise VideoOpenError(f"OpenCV could not open video: {path}")

        width_px = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height_px = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_container = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if (
            width_px <= 0
            or height_px <= 0
            or not isfinite(fps_container)
            or fps_container <= 0
            or frame_count <= 0
        ):
            capture.release()
            raise VideoOpenError(f"video metadata is invalid or incomplete: {path}")

        info = VideoStreamInfo(
            width_px=width_px,
            height_px=height_px,
            fps_container=fps_container,
            frame_count=frame_count,
            container_format=path.suffix.removeprefix(".").lower() or None,
            timing_status="unknown",
        )
        self._capture = capture
        self._info = info
        self._path = path
        logger.info(
            "opened video path=%s frames=%d fps_container=%.6f size=%dx%d",
            path,
            frame_count,
            fps_container,
            width_px,
            height_px,
        )
        return info

    def read_frame(self, frame_index: int) -> DecodedFrame:
        """Seek to and decode an exact 0-based frame, converting BGR to RGB."""

        if not self.is_open or self._capture is None:
            raise VideoFrameError("cannot read frame because no video is open")
        if frame_index < 0 or frame_index >= self.info.frame_count:
            raise VideoFrameError(
                f"frame_index {frame_index} is outside [0, {self.info.frame_count - 1}]"
            )
        if not self._capture.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index)):
            raise VideoFrameError(f"OpenCV could not seek to frame {frame_index}")
        success, pixels_bgr = self._capture.read()
        if not success or pixels_bgr is None:
            raise VideoFrameError(f"OpenCV could not decode frame {frame_index}")
        next_frame_position = float(self._capture.get(cv2.CAP_PROP_POS_FRAMES))
        if (
            isfinite(next_frame_position)
            and next_frame_position >= 1.0
            and abs(next_frame_position - (frame_index + 1)) > 0.5
        ):
            raise VideoFrameError(
                f"OpenCV seek mismatch for frame {frame_index}: "
                f"decoder advanced to {next_frame_position:.3f}"
            )
        pixels_rgb = np.ascontiguousarray(
            cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8
        )
        return DecodedFrame(frame_index=frame_index, pixels_rgb=pixels_rgb)

    def close(self) -> None:
        """Release OpenCV and clear metadata; idempotent for GUI cleanup paths."""

        if self._capture is not None:
            self._capture.release()
        self._capture = None
        self._info = None
        self._path = None
