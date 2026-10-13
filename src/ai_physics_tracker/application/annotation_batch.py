"""应用层：选定帧的连续人工标注进度，不创建观测或改变审核记录。"""

from dataclasses import dataclass, replace
from uuid import UUID


@dataclass(frozen=True)
class AnnotationBatch:
    """瞬时选择与进度；真实标签和审核记录仍由 ProjectSession 保存。"""

    track_id: UUID
    frames: tuple[int, ...]
    run_id: UUID | None = None
    index: int = 0
    corrected: int = 0
    paused: bool = False

    def __post_init__(self) -> None:
        if not self.frames or len(set(self.frames)) != len(self.frames):
            raise ValueError("Select a non-empty batch of unique frames")
        if any(type(frame) is not int or frame < 0 for frame in self.frames):
            raise ValueError("Batch frames must be non-negative integers")
        if not 0 <= self.index <= len(self.frames) or not 0 <= self.corrected <= self.index:
            raise ValueError("Invalid batch progress")

    @property
    def finished(self) -> bool:
        return self.index == len(self.frames)

    @property
    def current_frame(self) -> int | None:
        return None if self.finished else self.frames[self.index]

    def advance(self, *, corrected: bool) -> "AnnotationBatch":
        if self.finished or self.paused:
            raise ValueError("Resume an unfinished batch before placing or skipping")
        return replace(self, index=self.index + 1, corrected=self.corrected + int(corrected))
