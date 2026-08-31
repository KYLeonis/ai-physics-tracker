"""AI 跟踪引擎适配器的抽象协议定义。"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


@runtime_checkable
class EngineAdapter(Protocol):
    """AI 跟踪引擎适配器的抽象契约协议。"""

    def create_project(
        self,
        project_name: str,
        experimenter: str,
        video_path: Path,
        working_dir: Path,
        bodyparts: list[str] | None = None,
    ) -> Path:
        """在 working_dir 中创建 DLC 项目目录与初始 config.yaml，返回 config_path。"""
        ...

    def export_annotations(
        self,
        track_points: tuple[TrackPoint, ...],
        video_reader: OpenCVVideoReader,
        config_path: Path,
        scorer: str = "AIPhysicsTracker",
        bodyparts: list[str] | None = None,
    ) -> int:
        """按规范导出 labeled-data 结构（抽帧 PNG 与 MultiIndex 标注 CSV/HDF5），返回导出帧数。"""
        ...

    def import_results(
        self,
        prediction_data: Any,
        track_id: UUID,
        timeline: Timeline,
        source_detail: str,
        bodypart: str = "target",
        min_confidence: float = 0.0,
    ) -> tuple[TrackPoint, ...]:
        """将引擎预测产出的数据解析并转换为不可变 TrackPoint 元组。"""
        ...
