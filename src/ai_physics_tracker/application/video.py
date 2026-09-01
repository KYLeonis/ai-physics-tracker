"""应用层视频端口与稳定的 RGB 帧值对象。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt

TimingStatus = Literal["unknown", "cfr", "near_cfr", "vfr_suspected"]


class VideoError(Exception):
    """用户可见视频操作的基础错误。"""


class VideoOpenError(VideoError):
    """视频无法打开或元数据非法时抛出。"""


class VideoFrameError(VideoError):
    """请求的帧无法解码时抛出。"""


@dataclass(frozen=True)
class VideoStreamInfo:
    """解码器元数据，尚不是可持久化的领域 Video。"""

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
    """一个 0-based 视频帧，像素为连续内存的 RGB uint8。"""

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
    """Phase 2.1 的最小同步读取器契约。"""

    @property
    def is_open(self) -> bool:
        """此读取器当前是否持有已打开的视频资源。"""

        ...

    @property
    def info(self) -> VideoStreamInfo:
        """当前已打开视频的元数据。"""

        ...

    @property
    def path(self) -> Path:
        """当前打开视频的本地路径；未打开时抛 VideoOpenError。

        媒体身份属于端口概念：标注导出（labeled-data 目录按视频定位）
        与溯源校验都依赖它，替代实现必须提供。
        """

        ...

    def open(self, path: Path) -> VideoStreamInfo:
        """打开视频，并先释放此前持有的资源。"""

        ...

    def read_frame(self, frame_index: int) -> DecodedFrame:
        """解码指定的 0-based 帧，失败时抛出 VideoFrameError。"""

        ...

    def close(self) -> None:
        """释放全部解码器/文件资源；可重复调用。"""

        ...
