"""AI 跟踪引擎适配器的抽象协议定义与训练参数对象。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


@dataclass(frozen=True)
class TrainingParams:
    """训练参数值对象，支持快照入 TrackingRun.config。"""

    epochs: int = 50
    batch_size: int = 8
    device: str = "auto"
    display_iters: int = 10
    save_iters: int = 50
    learning_rate: float = 0.001
    shuffle: int = 1
    trainingsetindex: int = 0
    extra_params: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.epochs <= 0:
            raise ValueError("epochs must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.display_iters <= 0:
            raise ValueError("display_iters must be positive")
        if self.save_iters <= 0:
            raise ValueError("save_iters must be positive")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if self.shuffle < 0:
            raise ValueError("shuffle must be non-negative")

    def to_config(self) -> JsonObject:
        """导出为可序列化入 TrackingRun.config 的字典快照。"""
        res: JsonObject = {
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "device": self.device,
            "display_iters": self.display_iters,
            "save_iters": self.save_iters,
            "learning_rate": self.learning_rate,
            "shuffle": self.shuffle,
            "trainingsetindex": self.trainingsetindex,
        }
        if self.extra_params:
            res["extra_params"] = dict(self.extra_params)
        return res

    @classmethod
    def from_config(cls, config: JsonObject) -> "TrainingParams":
        """从 JsonObject 反序列化 TrainingParams。"""
        epochs = int(config.get("epochs", 50))  # type: ignore[arg-type]
        batch_size = int(config.get("batch_size", 8))  # type: ignore[arg-type]
        device = str(config.get("device", "auto"))
        display_iters = int(config.get("display_iters", 10))  # type: ignore[arg-type]
        save_iters = int(config.get("save_iters", 50))  # type: ignore[arg-type]
        learning_rate = float(config.get("learning_rate", 0.001))  # type: ignore[arg-type]
        shuffle = int(config.get("shuffle", 1))  # type: ignore[arg-type]
        trainingsetindex = int(config.get("trainingsetindex", 0))  # type: ignore[arg-type]
        extra_params = config.get("extra_params")
        return cls(
            epochs=epochs,
            batch_size=batch_size,
            device=device,
            display_iters=display_iters,
            save_iters=save_iters,
            learning_rate=learning_rate,
            shuffle=shuffle,
            trainingsetindex=trainingsetindex,
            extra_params=extra_params if isinstance(extra_params, dict) else {},
        )


@dataclass(frozen=True)
class TrainOutcome:
    """训练执行结果值对象。"""

    status: str  # "completed" | "cancelled" | "failed"
    epochs_completed: int
    snapshot_path: str | None = None
    engine_version: str = ""
    error_message: str | None = None


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
    ) -> bool:
        """生成 DLC 训练集文件，成功返回 True。"""
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

    def engine_version(self) -> str:
        """返回引擎版本号字符串（如 '3.0.1'）。"""
        ...
