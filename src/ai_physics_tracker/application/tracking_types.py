"""应用层训练/推理参数与跨进程消息；无 GUI 或引擎依赖。"""

from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import TypeAlias
from uuid import UUID

from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import JsonObject

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


@dataclass(frozen=True)
class InferenceParams:
    """推理设置；阈值由调用方显式选择，不把实验默认值写死。"""

    min_confidence: float
    device: str = "auto"
    batch_size: int = 8

    def __post_init__(self) -> None:
        if (isinstance(self.min_confidence, bool)
                or not isinstance(self.min_confidence, (int, float))
                or not isfinite(self.min_confidence)
                or not 0 <= self.min_confidence <= 1):
            raise ValueError("min_confidence must be finite and in [0, 1]")
        if type(self.batch_size) is not int or self.batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if not isinstance(self.device, str) or self.device not in {"auto", "cpu", "mps", "cuda"}:
            raise ValueError("device must be auto, cpu, mps or cuda")


@dataclass(frozen=True)
class InferenceRequest:
    """子进程独占的单视频推理请求，不包含活动会话。"""

    config_path: Path
    video_path: Path
    model_snapshot: Path
    output_dir: Path
    track_id: UUID
    timeline: Timeline
    source_detail: str
    frame_count: int
    params: InferenceParams
    shuffle: int = 1
    trainingsetindex: int = 0
    model_sha256: str | None = None
    video_sha256: str | None = None
    archive_model: bool = False
    config_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.frame_count) is not int or self.frame_count <= 0:
            raise ValueError("frame_count must be a positive integer")
        if any(type(n) is not int or n < 0 for n in (self.shuffle, self.trainingsetindex)):
            raise ValueError("shuffle and trainingsetindex must be non-negative integers")
        if not self.source_detail.strip():
            raise ValueError("source_detail must not be blank")


@dataclass(frozen=True)
class InferenceOutcome:
    """成功推理的已校验观测与原始文件；失败通过异常返回。"""

    points: tuple[TrackPoint, ...]
    prediction_path: Path
    row_count: int
    missing_count: int
    low_confidence_count: int
    model_snapshot: Path
    engine_version: str
    device: str


@dataclass(frozen=True)
class TaskProgress:
    """任务执行进度消息。"""

    run_id: UUID
    step: int
    total_steps: int
    loss: float | None = None
    message: str = ""
    learning_rate: float | None = None


@dataclass(frozen=True)
class TaskLog:
    """任务执行日志消息。"""

    run_id: UUID
    level: str
    message: str
    timestamp: str


@dataclass(frozen=True)
class TaskResult:
    """任务执行最终结果消息。"""

    run_id: UUID
    success: bool
    payload: JsonObject | None = None
    error: str | None = None


TaskMessage: TypeAlias = TaskProgress | TaskLog | TaskResult


