"""用于测试与 CI 环境的 Mock 引擎适配器实现。"""

from math import isfinite
from pathlib import Path
import time
from typing import Any
from uuid import UUID, uuid4

from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.engine_adapter import (
    EngineAdapter,
    TrainingParams,
    TrainOutcome,
)
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.task_runner import (
    send_log,
    send_progress,
)


class MockEngineAdapter:
    """Mock AI 跟踪引擎适配器，模拟项目创建、标注导出与轨迹生成。"""

    def __init__(
        self,
        default_confidence: float = 0.98,
        version: str = "3.0.1-mock",
    ) -> None:
        self.default_confidence = default_confidence
        self._version = version
        self.created_projects: list[Path] = []
        self.exported_counts: list[int] = []
        self.created_datasets: list[Path] = []

    def engine_version(self) -> str:
        """返回 Mock 引擎版本。"""
        return self._version

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

    def create_training_dataset(
        self,
        config_path: Path,
        num_shuffles: int = 1,
        net_type: str = "resnet_50",
        augmenter_type: str = "default",
    ) -> bool:
        """模拟生成 DLC 训练集。"""
        self.created_datasets.append(config_path)
        dataset_dir = config_path.parent / "training-datasets" / "iteration-0"
        dataset_dir.mkdir(parents=True, exist_ok=True)
        return True

    def train(
        self,
        run_id: UUID,
        queue: Any,
        cancel_event: Any,
        config_path: Path,
        params: TrainingParams,
    ) -> TrainOutcome:
        """模拟执行训练，支持流式进度、取消与快照产出。"""

        send_log(queue, run_id, "INFO", f"Mock training started for {config_path.name}")
        epochs = params.epochs
        delay = float(params.extra_params.get("simulate_delay", 0.01))

        if params.extra_params.get("simulate_failure"):
            send_log(queue, run_id, "ERROR", "Simulated training failure")
            return TrainOutcome(
                status="failed",
                epochs_completed=0,
                engine_version=self.engine_version(),
                error_message=str(params.extra_params["simulate_failure"]),
            )

        for epoch in range(1, epochs + 1):
            if cancel_event.is_set():
                send_log(queue, run_id, "WARNING", "Mock training cancelled")
                return TrainOutcome(
                    status="cancelled",
                    epochs_completed=epoch - 1,
                    engine_version=self.engine_version(),
                )
            loss = 0.5 / (epoch**0.5)
            send_progress(
                queue,
                run_id,
                step=epoch,
                total_steps=epochs,
                loss=loss,
                message=f"Epoch {epoch}/{epochs} - Loss: {loss:.4f}",
            )
            if delay > 0:
                time.sleep(delay)

        snapshot_dir = config_path.parent / "dlc-models"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file = snapshot_dir / f"snapshot-{epochs}.pt"
        snapshot_file.touch()

        send_log(queue, run_id, "INFO", f"Mock training completed: {snapshot_file}")
        return TrainOutcome(
            status="completed",
            epochs_completed=epochs,
            snapshot_path=snapshot_file.as_posix(),
            engine_version=self.engine_version(),
        )

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
                    f_idx = item.get("frame_index") if "frame_index" in item else item.get("frame", 0)
                    x_val = item.get("x") if "x" in item else item.get("pixel_x", 0.0)
                    y_val = item.get("y") if "y" in item else item.get("pixel_y", 0.0)
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
