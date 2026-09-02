"""用于测试与 CI 环境的 Mock 引擎适配器实现。"""

from concurrent.futures import CancelledError
import csv
from pathlib import Path
import time
from typing import Any
from uuid import UUID

from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.infrastructure.engine_adapter import (
    InferenceRequest,
    InferenceOutcome,
    TrainingParams,
    TrainOutcome,
    FrameSelectionRequest,
    FrameSelectionResult,
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
        self, prediction_data: Any, track_id: UUID, timeline: Timeline,
        source_detail: str, bodypart: str = "target", min_confidence: float = 0.0,
    ) -> tuple[TrackPoint, ...]:
        """测试记录允许省略分数；实际格式解析复用生产边界。"""
        from ai_physics_tracker.infrastructure.dlc_predictions import parse_predictions

        if isinstance(prediction_data, (list, tuple)):
            prediction_data = [dict(item, confidence=item.get("confidence", self.default_confidence))
                               if "likelihood" not in item else item for item in prediction_data]
        return parse_predictions(prediction_data, track_id, timeline, source_detail,
                                 bodypart, min_confidence).points

    def infer(
        self, run_id: UUID, queue: Any, cancel_event: Any, request: InferenceRequest,
    ) -> InferenceOutcome:
        """生成与真实 DLC 相同的三层 CSV；CI 无需 pandas/DLC。"""
        from ai_physics_tracker.infrastructure.dlc_predictions import parse_predictions

        if cancel_event.is_set():
            raise CancelledError("Inference cancelled")
        if not request.model_snapshot.is_file():
            raise ValueError("Model snapshot is missing")
        request.output_dir.mkdir(parents=True, exist_ok=False)
        path = request.output_dir / "prediction.csv"
        send_log(queue, run_id, "INFO", "Mock inference started")
        send_progress(queue, run_id, 0, request.frame_count)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerows([
                ["scorer", "MockDLC", "MockDLC", "MockDLC"],
                ["bodyparts", "target", "target", "target"],
                ["coords", "x", "y", "likelihood"],
            ])
            for frame_index in range(request.frame_count):
                if cancel_event.is_set():
                    raise CancelledError("Inference cancelled")
                writer.writerow([frame_index, 10 + frame_index, 20 + 2 * frame_index,
                                 self.default_confidence])
                send_progress(queue, run_id, frame_index + 1, request.frame_count)
        parsed = parse_predictions(path, request.track_id, request.timeline, request.source_detail,
                                   min_confidence=request.params.min_confidence,
                                   frame_count=request.frame_count)
        return InferenceOutcome(parsed.points, path, parsed.row_count, parsed.missing_count,
                                parsed.low_confidence_count, request.model_snapshot,
                                self.engine_version(), "cpu")

    def evaluate(self, config_path: Path, snapshot_path: Path, params: TrainingParams) -> dict[str, Any]:
        """模拟评价指标，供 GUI 生命周期测试使用。"""
        return {"status": "completed", "unit": "px", "metrics": {"train_rmse": 1.0, "test_rmse": 2.0},
                "snapshot": snapshot_path.name, "train_samples": 4, "test_samples": 1}

    def suggest_frames(
        self,
        request: FrameSelectionRequest,
        queue: Any,
        cancel_event: Any,
    ) -> FrameSelectionResult:
        """确定性 mock 选帧：在 working zone 内排除 manual 帧后均匀采样（不依赖 DLC/Qt）。

        结果由 seed 控制，保证测试可复现；两种 algorithm 均按此路径返回，
        便于 CI 在无 DLC 环境下测试任务生命周期与 GUI 逻辑。
        """
        from concurrent.futures import CancelledError as _CancelledError
        import math

        if cancel_event.is_set():
            raise _CancelledError("Frame selection cancelled")

        send_progress(queue, request.track_id, 0, 1, message="Mock frame selection started")

        zone_frames = list(range(request.zone_start, request.zone_end + 1))
        available = [f for f in zone_frames if f not in request.excluded_frames]

        n = min(request.n_frames, len(available))
        if n == 0 or not available:
            selected: list[int] = []
        else:
            # 均匀间隔采样，seed 不影响 uniform 实现（mock 保持两种 algorithm 均可测试）
            step = len(available) / n
            selected = sorted({available[math.floor(i * step)] for i in range(n)})

        if cancel_event.is_set():
            raise _CancelledError("Frame selection cancelled")

        send_progress(queue, request.track_id, 1, 1, message="Mock frame selection complete")

        zone_excl = set(range(request.zone_start, request.zone_end + 1)) & set(request.excluded_frames)
        params_snapshot: dict = {
            "algorithm": request.algorithm,
            "n_frames": request.n_frames,
            "seed": request.seed,
            "zone_start": request.zone_start,
            "zone_end": request.zone_end,
            "cluster_step": request.cluster_step,
            "color_mode": request.color_mode,
            "excluded_count": len(zone_excl),
            "actual_n": len(selected),
        }
        return FrameSelectionResult(
            request_algorithm=request.algorithm,
            suggested_frames=tuple(selected),
            actual_n=len(selected),
            excluded_count=len(zone_excl),
            params_snapshot=params_snapshot,
        )
