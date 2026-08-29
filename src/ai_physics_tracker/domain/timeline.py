"""Timeline 值对象与全项目唯一的 frame/time 换算函数。"""

from dataclasses import dataclass, field
from math import floor, isfinite
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject

TIME_COMPARISON_TOLERANCE_S = 1e-9


@dataclass(frozen=True)
class Timeline:
    """单个源视频的 CFR（恒定帧率）时间契约。"""

    video_id: UUID
    fps_nominal: float
    working_zone: tuple[int, int]
    frame_indexing: str = "zero-based"
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not isfinite(self.fps_nominal) or self.fps_nominal <= 0:
            raise ValueError("fps_nominal must be a finite positive value")
        if self.frame_indexing != "zero-based":
            raise ValueError("frame_indexing must be 'zero-based'")
        in_frame, out_frame = self.working_zone
        if in_frame < 0 or out_frame < in_frame:
            raise ValueError("working_zone must be an inclusive non-negative range")


def frame_to_time(frame_index: int, timeline: Timeline) -> float:
    """将 0-based 源帧号换算为源视频绝对秒数。"""

    if frame_index < 0:
        raise ValueError("frame_index must be non-negative")
    return frame_index / timeline.fps_nominal


def time_to_frame(time_s: float, timeline: Timeline, frame_count: int) -> int:
    """将秒数换算为帧号，使用确定性的 half-up 舍入并钳位到视频范围。"""

    if not isfinite(time_s):
        raise ValueError("time_s must be finite")
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    rounded = floor(time_s * timeline.fps_nominal + 0.5)
    return min(max(rounded, 0), frame_count - 1)


def clamp_to_working_zone(frame_index: int, timeline: Timeline) -> int:
    """为 UI 跳转/步进钳位帧号，不改变其时间基准。"""

    in_frame, out_frame = timeline.working_zone
    return min(max(frame_index, in_frame), out_frame)


def step_frame(frame_index: int, delta: int, timeline: Timeline) -> int:
    """按整数帧数步进并钳位到 working_zone。"""

    return clamp_to_working_zone(frame_index + delta, timeline)


def has_time_mismatch(frame_index: int, time_s: float, timeline: Timeline) -> bool:
    """按 data-model.md §5.7 的容差检查持久化时间是否与帧号一致。"""

    expected = frame_to_time(frame_index, timeline)
    tolerance = 0.5 / timeline.fps_nominal + 1e-6
    return abs(time_s - expected) > tolerance
