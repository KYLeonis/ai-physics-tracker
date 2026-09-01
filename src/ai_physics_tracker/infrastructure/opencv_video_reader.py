"""实现应用层 VideoReader 端口的 OpenCV 适配器。"""

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
    """显式持有文件资源的同步随机访问读取器。"""

    def __init__(self) -> None:
        self._capture: cv2.VideoCapture | None = None
        self._info: VideoStreamInfo | None = None
        self._path: Path | None = None
        # 读取器当前预期下一帧位置：恰好顺序请求时跳过 seek 直接 read，
        # 避免顺序播放每帧都触发关键帧回溯解码（H.264 随机 seek 的主要开销）
        self._next_frame_position: int | None = None

    @property
    def is_open(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    @property
    def info(self) -> VideoStreamInfo:
        if self._info is None:
            raise VideoOpenError("no video is open")
        return self._info

    @property
    def path(self) -> Path:
        """当前打开视频的本地路径；导出/溯源用它确认媒体身份。"""

        if self._path is None:
            raise VideoOpenError("no video is open")
        return self._path

    def open(self, path: Path) -> VideoStreamInfo:
        """打开本地文件并校验 Timeline 所需的元数据。"""

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
        """seek 并解码指定的 0-based 帧，同时将 BGR 转为 RGB。

        顺序请求（上次读取的下一帧）走直接 read 的 fast path；
        其余请求走显式 seek。
        """

        if not self.is_open or self._capture is None:
            raise VideoFrameError("cannot read frame because no video is open")
        if frame_index < 0 or frame_index >= self.info.frame_count:
            raise VideoFrameError(
                f"frame_index {frame_index} is outside [0, {self.info.frame_count - 1}]"
            )
        is_sequential = self._next_frame_position == frame_index
        if not is_sequential and not self._capture.set(
            cv2.CAP_PROP_POS_FRAMES, float(frame_index)
        ):
            raise VideoFrameError(f"OpenCV could not seek to frame {frame_index}")
        success, pixels_bgr = self._capture.read()
        if not success or pixels_bgr is None:
            self._next_frame_position = None
            raise VideoFrameError(f"OpenCV could not decode frame {frame_index}")
        self._next_frame_position = frame_index + 1
        if is_sequential:
            # fast path 无法通过 POS 校验自身（read 不回读位置语义稳定），
            # 顺序正确性由 _next_frame_position 的维护规则保证
            pixels_rgb = self._convert_to_rgb(pixels_bgr)
            return DecodedFrame(frame_index=frame_index, pixels_rgb=pixels_rgb)
        next_frame_position = float(self._capture.get(cv2.CAP_PROP_POS_FRAMES))
        if (
            isfinite(next_frame_position)
            and next_frame_position >= 1.0
            and abs(next_frame_position - (frame_index + 1)) > 0.5
        ):
            self._next_frame_position = None
            raise VideoFrameError(
                f"OpenCV seek mismatch for frame {frame_index}: "
                f"decoder advanced to {next_frame_position:.3f}"
            )
        pixels_rgb = self._convert_to_rgb(pixels_bgr)
        return DecodedFrame(frame_index=frame_index, pixels_rgb=pixels_rgb)

    def _convert_to_rgb(self, pixels_bgr: np.ndarray) -> np.ndarray:
        return np.ascontiguousarray(
            cv2.cvtColor(pixels_bgr, cv2.COLOR_BGR2RGB), dtype=np.uint8
        )

    def close(self) -> None:
        """释放 OpenCV 资源并清空元数据；对 GUI 清理路径保持幂等。"""

        if self._capture is not None:
            self._capture.release()
        self._capture = None
        self._info = None
        self._path = None
        self._next_frame_position = None
