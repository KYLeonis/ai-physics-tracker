"""AI 跟踪引擎适配器的抽象协议定义与训练参数对象。"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.application.tracking_types import (
    TrainingParams, TrainOutcome, InferenceParams, InferenceRequest, InferenceOutcome,
    FrameSelectionRequest, FrameSelectionResult,
)
from ai_physics_tracker.infrastructure.dlc_predictions import RawPrediction
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

    def create_training_dataset(
        self,
        config_path: Path,
        num_shuffles: int = 1,
        net_type: str = "resnet_50",
        augmenter_type: str = "default",
        train_indices: list[int] | None = None,
        test_indices: list[int] | None = None,
    ) -> bool:
        """生成 DLC 训练集文件，支持显式切分索引，成功返回 True。"""
        ...

    def train(
        self,
        run_id: UUID,
        queue: Any,
        cancel_event: Any,
        config_path: Path,
        params: TrainingParams,
    ) -> TrainOutcome:
        """执行训练，流式汇报进度与日志，支持取消。"""
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

    def infer(
        self, run_id: UUID, queue: Any, cancel_event: Any, request: InferenceRequest,
    ) -> InferenceOutcome:
        """执行全帧推理并解析结果；不写活动项目，异常/取消不返回部分结果。"""
        ...

    def evaluate(self, config_path: Path, snapshot_path: Path, params: TrainingParams) -> JsonObject:
        """评价确切快照，返回原生指标和样本量；失败不改变训练结果。"""
        ...

    def engine_version(self) -> str:
        """返回引擎版本号字符串（如 '3.0.1'）。"""
        ...

    def suggest_frames(
        self,
        request: FrameSelectionRequest,
        queue: Any,
        cancel_event: Any,
    ) -> FrameSelectionResult:
        """按请求参数在 working zone 内建议代表帧号；不修改磁盘、不创建 TrackPoint（Phase 5.1 R1）。"""
        ...

    def read_raw_predictions(
        self,
        prediction_path: Path,
        bodypart: str = "target",
        *,
        frame_count: int,
    ) -> tuple[RawPrediction, ...]:
        """读取预测产物的全帧原始值（含低置信度与缺测），整批校验（Phase 5.2 R2.2）。

        frame_count 必传：不完整帧批次必须被整体拒绝（AC-2），不允许静默跳过覆盖率校验。
        """
        ...
