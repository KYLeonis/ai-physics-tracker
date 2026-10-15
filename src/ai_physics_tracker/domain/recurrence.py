"""领域层：同方向参考线交叉的事件与重复间隔，不推断基本周期。"""

import math
from concurrent.futures import CancelledError
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class RecurrenceSpec:
    """hysteresis是参考线两侧的确认带宽；不改变交叉时刻的参考线。"""

    level: float = 0.0
    direction: str = "rising"
    hysteresis: float = 0.0
    min_separation_s: float = 0.0
    wrapped_angle: bool = False

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.level, self.hysteresis, self.min_separation_s)):
            raise ValueError("Recurrence settings must be finite")
        if self.hysteresis < 0 or self.min_separation_s < 0:
            raise ValueError("Hysteresis and minimum separation must be nonnegative")
        if self.direction not in ("rising", "falling"):
            raise ValueError("Crossing direction must be rising or falling")


@dataclass(frozen=True)
class CrossingEvent:
    """实际相邻源样本夹点；time_s是线上线性插值，不是整数帧观测。"""

    lower_frame_index: int
    upper_frame_index: int
    lower_time_s: float
    upper_time_s: float
    time_s: float
    segment_index: int


@dataclass(frozen=True)
class RecurrenceOutcome:
    """std为None表示不足两个间隔；零间隔时mean也为None。"""

    events: tuple[CrossingEvent, ...]
    intervals_s: tuple[float, ...]
    mean_interval_s: float | None
    sample_std_s: float | None
    measurement_status: str
    message: str


def measure_recurrence(
    frame_indices: np.ndarray, time_s: np.ndarray, values: np.ndarray, spec: RecurrenceSpec,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> RecurrenceOutcome:
    """仅在连续有效段配对；NaN、帧缺口、角分支跳变、在线平台均断段。

    先观察低于负带宽的样本，再记录零线交叉，越过正带宽后确认事件。
    单个恰好在线样本可定位事件；连续在线平台无法确定唯一时刻，拒绝跨越。
    """
    frames = np.asarray(frame_indices)
    time, signal = np.asarray(time_s, dtype=float), np.asarray(values, dtype=float)
    if (frames.ndim != 1 or time.shape != frames.shape or signal.shape != frames.shape
            or not np.issubdtype(frames.dtype, np.integer) or np.any(frames < 0)
            or not np.all(np.isfinite(time)) or np.any(np.diff(time) <= 0)
            or np.any(np.diff(frames) <= 0) or np.any(np.isinf(signal))):
        raise ValueError("Recurrence samples require increasing source frames and finite paired times")
    try:
        with np.errstate(over="raise", invalid="raise"):
            oriented = (signal - spec.level) * (1 if spec.direction == "rising" else -1)
    except FloatingPointError as error:
        raise ValueError("Signal and reference exceed the supported numeric range") from error
    events: list[CrossingEvent] = []
    segment = 0
    armed = False
    candidate: CrossingEvent | None = None
    previous: int | None = None
    for index, value in enumerate(oriented):
        if index % 256 == 0 and is_cancelled():
            raise CancelledError()
        if np.isnan(value):
            segment += 1
            armed, candidate, previous = False, None, None
            continue
        if previous is not None and (
            frames[index] - frames[previous] != 1
            or (spec.wrapped_angle and abs(signal[index] - signal[previous]) > math.pi)
            or (value == 0.0 and oriented[previous] == 0.0)
        ):
            segment += 1
            armed, candidate, previous = False, None, None
        if value < -spec.hysteresis:
            armed = True
        if value < 0:
            candidate = None
        if armed and previous is not None and oriented[previous] < 0 <= value:
            # 以有限夹点计算零线事件；确认带只负责抑制重复计数。
            magnitude = max(abs(oriented[previous]), abs(value))
            below, above = -oriented[previous] / magnitude, value / magnitude
            fraction = float(below / (below + above))
            crossing_time = float(time[previous] + fraction * (time[index] - time[previous]))
            candidate = CrossingEvent(int(frames[previous]), int(frames[index]),
                                      float(time[previous]), float(time[index]), crossing_time, segment)
        if candidate is not None and value > spec.hysteresis:
            last = events[-1] if events and events[-1].segment_index == segment else None
            if last is None or candidate.time_s - last.time_s >= spec.min_separation_s:
                events.append(candidate)
            armed, candidate = False, None
        previous = index
    if is_cancelled():
        raise CancelledError()
    intervals = tuple(right.time_s - left.time_s for left, right in zip(events, events[1:])
                      if left.segment_index == right.segment_index)
    mean = float(np.mean(intervals)) if intervals else None
    std = float(np.std(intervals, ddof=1)) if len(intervals) > 1 else None
    return RecurrenceOutcome(tuple(events), intervals, mean, std,
                             "measured" if intervals else "insufficient_events",
                             "Same-direction crossing intervals; a fundamental period is not inferred"
                             if intervals else "No interval between two events in one valid segment")
