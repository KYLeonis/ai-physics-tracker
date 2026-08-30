"""应用层时序探测端口：验证结果只在当前媒体会话内有效。"""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from threading import Event
from typing import Protocol

from ai_physics_tracker.application.video import TimingStatus


@dataclass(frozen=True)
class TimingReport:
    """逐帧探测结论；unknown 不是 CFR，不授权测量。"""

    status: TimingStatus
    reason: str
    frame_count: int = 0
    fps_measured: float | None = None
    fps_reference: float | None = None
    max_grid_error_s: float | None = None
    max_interval_error_s: float | None = None


MAX_APPROXIMATION_ERROR_S = 0.001
MAX_APPROXIMATION_FRAME_FRACTION = 0.01


def approximation_errors(report: TimingReport, fps_nominal: float) -> tuple[float, float] | None:
    """ADR-0007：用三角不等式将全片误差保守转换到实际保存的 Timeline。"""

    if (report.status != "near_cfr" or isinstance(report.frame_count, bool)
            or not isinstance(report.frame_count, int) or report.frame_count < 2):
        return None
    values = (report.fps_reference, report.fps_measured,
              report.max_grid_error_s, report.max_interval_error_s)
    if any(value is None or not isfinite(value) for value in values):
        return None
    if (report.fps_reference <= 0 or report.fps_measured <= 0
            or not isfinite(fps_nominal) or fps_nominal <= 0):
        return None
    if report.max_grid_error_s < 0 or report.max_interval_error_s < 0:
        return None
    period_difference_s = abs(1 / fps_nominal - 1 / report.fps_reference)
    grid_s = report.max_grid_error_s + (report.frame_count - 1) * period_difference_s
    interval_s = report.max_interval_error_s + period_difference_s
    budget_s = min(MAX_APPROXIMATION_ERROR_S, MAX_APPROXIMATION_FRAME_FRACTION / fps_nominal)
    return (grid_s, interval_s) if max(grid_s, interval_s) <= budget_s else None


class VideoTimingProbe(Protocol):
    """后台只读探测；缺工具/无法确认返回 unknown，取消不留下子进程。"""

    def probe(self, path: Path, cancel: Event | None = None) -> TimingReport: ...
