"""应用层时序探测端口：验证结果只在当前媒体会话内有效。"""

from dataclasses import dataclass
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


class VideoTimingProbe(Protocol):
    """后台只读探测；缺工具/无法确认返回 unknown，取消不留下子进程。"""

    def probe(self, path: Path, cancel: Event | None = None) -> TimingReport: ...
