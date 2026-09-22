"""Video 元数据值对象；刻意不包含帧像素数据。"""

from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from uuid import UUID

from ai_physics_tracker.domain.paths import validate_managed_relative_path
from ai_physics_tracker.domain.types import JsonObject


@dataclass(frozen=True)
class Video:
    """视频元数据，附带项目托管相对路径或外部绝对路径之一的定位器。"""

    video_id: UUID
    file_path: PurePosixPath | None
    display_name: str
    width_px: int
    height_px: int
    fps_container: float
    frame_count: int
    original_path: str | None = None
    container_format: str | None = None
    sha256: str | None = None
    vfr_suspected: bool = False
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.file_path is not None and self.file_path.is_absolute():
            raise ValueError("file_path must be relative to the project root")
        if self.file_path is not None:
            validate_managed_relative_path(self.file_path, "file_path")
        if self.file_path is None and self.original_path is None:
            raise ValueError("external video requires an absolute original_path")
        if self.original_path is not None and not _is_absolute_path(self.original_path):
            raise ValueError("original_path must be absolute when provided")
        if not self.display_name.strip():
            raise ValueError("display_name must not be blank")
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("video dimensions must be positive")
        if self.fps_container <= 0:
            raise ValueError("fps_container must be positive")
        if self.frame_count <= 0:
            raise ValueError("frame_count must be positive")


def _is_absolute_path(value: str) -> bool:
    """在任意宿主平台上识别 POSIX 与 Windows 两种风格的绝对路径。"""

    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
