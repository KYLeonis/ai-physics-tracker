"""Timeline value object and the only frame/time conversion functions."""

from dataclasses import dataclass, field
from math import floor, isfinite
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject

TIME_COMPARISON_TOLERANCE_S = 1e-9


@dataclass(frozen=True)
class Timeline:
    """CFR timing contract for one source video."""

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
    """Convert a 0-based source frame to absolute source-video seconds."""

    if frame_index < 0:
        raise ValueError("frame_index must be non-negative")
    return frame_index / timeline.fps_nominal


def time_to_frame(time_s: float, timeline: Timeline, frame_count: int) -> int:
    """Convert seconds using deterministic half-up rounding and clamp to the video."""

    if not isfinite(time_s):
        raise ValueError("time_s must be finite")
    if frame_count <= 0:
        raise ValueError("frame_count must be positive")
    rounded = floor(time_s * timeline.fps_nominal + 0.5)
    return min(max(rounded, 0), frame_count - 1)


def clamp_to_working_zone(frame_index: int, timeline: Timeline) -> int:
    """Clamp a frame for UI seek/step without changing its time basis."""

    in_frame, out_frame = timeline.working_zone
    return min(max(frame_index, in_frame), out_frame)


def step_frame(frame_index: int, delta: int, timeline: Timeline) -> int:
    """Move by an integer frame count and clamp to the working zone."""

    return clamp_to_working_zone(frame_index + delta, timeline)


def has_time_mismatch(frame_index: int, time_s: float, timeline: Timeline) -> bool:
    """Check the persisted-time tolerance from data-model.md §5.7."""

    expected = frame_to_time(frame_index, timeline)
    tolerance = 0.5 / timeline.fps_nominal + 1e-6
    return abs(time_s - expected) > tolerance
