"""用于测试与 CI 环境的 Mock 引擎适配器实现。"""

from math import isfinite
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.engine_adapter import EngineAdapter
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


class MockEngineAdapter:
    """Mock AI 跟踪引擎适配器，模拟项目创建、标注导出与轨迹生成。"""

    def __init__(self, default_confidence: float = 0.98) -> None:
        self.default_confidence = default_confidence
        self.created_projects: list[Path] = []
        self.exported_counts: list[int] = []

    def create_project(
        self,
        project_name: str,
        experimenter: str,
        video_path: Path,
        working_dir: Path,
        bodyparts: list[str] | None = None,
    ) -> Path:
        """创建 Mock 项目目录与 config.yaml。"""

        proj_dir = working_dir / project_name
        proj_dir.mkdir(parents=True, exist_ok=True)
        config_path = proj_dir / "config.yaml"
        config_path.write_text(
            f"Task: {project_name}\n"
            f"scorer: {experimenter}\n"
            f"project_path: {proj_dir.as_posix()}\n"
            f"bodyparts: {bodyparts or ['target']}\n",
            encoding="utf-8",
        )
        self.created_projects.append(config_path)
        return config_path

    def export_annotations(
        self,
        track_points: tuple[TrackPoint, ...],
        video_reader: OpenCVVideoReader,
        config_path: Path,
        scorer: str = "AIPhysicsTracker",
        bodyparts: list[str] | None = None,
    ) -> int:
        """模拟导出 active manual 标注。"""

        manual_points = [p for p in track_points if p.source == "manual" and p.status == "active"]
        count = len(manual_points)
        self.exported_counts.append(count)
        return count

    def import_results(
        self,
        prediction_data: Any,
        track_id: UUID,
        timeline: Timeline,
        source_detail: str,
        bodypart: str = "target",
        min_confidence: float = 0.0,
    ) -> tuple[TrackPoint, ...]:
        """将 mock 字典序列解析为 TrackPoint 元组。"""

        points: list[TrackPoint] = []
        now = utc_now()

        if isinstance(prediction_data, (list, tuple)):
            for item in prediction_data:
                if isinstance(item, dict):
                    f_idx = item.get("frame_index", item.get("frame", 0))
                    x_val = item.get("x", item.get("pixel_x", 0.0))
                    y_val = item.get("y", item.get("pixel_y", 0.0))
                    conf = float(item.get("confidence", self.default_confidence))
                    if conf >= min_confidence and isfinite(x_val) and isfinite(y_val):
                        points.append(
                            TrackPoint(
                                point_id=uuid4(),
                                track_id=track_id,
                                frame_index=int(f_idx),
                                time_s=frame_to_time(int(f_idx), timeline),
                                pixel_x=float(x_val),
                                pixel_y=float(y_val),
                                source="dlc",
                                source_detail=source_detail,
                                confidence=conf,
                                visibility="visible",
                                status="active",
                                created_at=now,
                                modified_at=now,
                            )
                        )

        return tuple(points)
