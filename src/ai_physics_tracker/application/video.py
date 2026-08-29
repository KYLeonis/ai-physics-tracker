"""Application-layer video port and stable RGB frame values."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

TimingStatus = Literal["unknown", "cfr", "vfr_suspected"]


class VideoError(Exception):
    """Base error for user-visible video operations."""


class VideoOpenError(VideoError):
    """Raised when a video cannot be opened or has invalid metadata."""


class VideoFrameError(VideoError):
    """Raised when a requested frame cannot be decoded."""


@dataclass(frozen=True)
class VideoStreamInfo:
    """Decoder metadata that is not yet a persistable domain Video."""

    width_px: int
    height_px: int
    fps_container: float
    frame_count: int
    container_format: str | None
    timing_status: TimingStatus = "unknown"

    def __post_init__(self) -> None:
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("video dimensions must be positive")
        if not np.isfinite(self.fps_container) or self.fps_container <= 0:
            raise ValueError("fps_container must be a finite positive value")
        if self.frame_count <= 0:
            raise ValueError("frame_count must be positive")


@dataclass(frozen=True)
class DecodedFrame:
    """One 0-based video frame as contiguous RGB uint8 pixels."""

    frame_index: int
    pixels_rgb: npt.NDArray[np.uint8]

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        if self.pixels_rgb.dtype != np.uint8:
            raise ValueError("pixels_rgb must have uint8 dtype")
        if self.pixels_rgb.ndim != 3 or self.pixels_rgb.shape[2] != 3:
            raise ValueError("pixels_rgb must have shape (height, width, 3)")
        owned_pixels = np.array(self.pixels_rgb, dtype=np.uint8, copy=True, order="C")
        owned_pixels.setflags(write=False)
        object.__setattr__(self, "pixels_rgb", owned_pixels)


class VideoReader(Protocol):
    """Minimal synchronous reader contract for Phase 2.1."""

    @property
    def is_open(self) -> bool:
        """Whether this reader currently owns an open video resource."""

        ...

    @property
    def info(self) -> VideoStreamInfo:
        """Metadata for the currently open video."""

        ...

    def open(self, path: Path) -> VideoStreamInfo:
        """Open a video, closing any previously owned resource."""

        ...

    def read_frame(self, frame_index: int) -> DecodedFrame:
        """Decode an exact 0-based frame or raise VideoFrameError."""

        ...

    def close(self) -> None:
        """Release all decoder/file resources; safe to call repeatedly."""

        ...
