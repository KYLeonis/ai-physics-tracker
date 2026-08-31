"""AI 引擎运行（训练与推理）的不可变溯源值对象。"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID, uuid4

from ai_physics_tracker.domain.types import JsonObject, require_aware_datetime, utc_now

RUN_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}
TASK_TYPES = {"train", "infer"}


@dataclass(frozen=True)
class TrackingRun:
    """一次引擎训练或推理运行的完整元数据记录。"""

    run_id: UUID
    video_id: UUID
    track_id: UUID
    engine: str
    engine_version: str
    task_type: str
    config: JsonObject
    source_detail: str
    created_at: datetime
    status: str = "pending"
    model_snapshot: str | None = None
    error_message: str | None = None
    completed_at: datetime | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.engine.strip():
            raise ValueError("engine must not be blank")
        if not self.engine_version.strip():
            raise ValueError("engine_version must not be blank")
        if not self.source_detail.strip():
            raise ValueError("source_detail must not be blank")
        if self.task_type not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {sorted(TASK_TYPES)}, got '{self.task_type}'")
        if self.status not in RUN_STATUSES:
            raise ValueError(f"status must be one of {sorted(RUN_STATUSES)}, got '{self.status}'")
        require_aware_datetime(self.created_at, "created_at")
        if self.completed_at is not None:
            require_aware_datetime(self.completed_at, "completed_at")
            if self.completed_at < self.created_at:
                raise ValueError("completed_at cannot be earlier than created_at")


def create_tracking_run(
    video_id: UUID,
    track_id: UUID,
    task_type: str,
    *,
    engine: str = "dlc",
    engine_version: str = "3.0.1",
    config: JsonObject | None = None,
    source_detail: str | None = None,
    model_snapshot: str | None = None,
) -> TrackingRun:
    """构造初始 pending 状态的 TrackingRun。"""

    now = utc_now()
    run_id = uuid4()
    actual_source_detail = source_detail or f"{engine}:{task_type}:{run_id}"
    return TrackingRun(
        run_id=run_id,
        video_id=video_id,
        track_id=track_id,
        engine=engine,
        engine_version=engine_version,
        task_type=task_type,
        config=config or {},
        source_detail=actual_source_detail,
        created_at=now,
        status="pending",
        model_snapshot=model_snapshot,
    )


def mark_run_running(run: TrackingRun) -> TrackingRun:
    """将 TrackingRun 状态流转为 running。"""

    if run.status != "pending":
        raise ValueError(f"cannot start run in '{run.status}' status")
    return replace(run, status="running")


def mark_run_completed(
    run: TrackingRun,
    *,
    model_snapshot: str | None = None,
) -> TrackingRun:
    """将 TrackingRun 状态流转为 completed。"""

    if run.status not in {"pending", "running"}:
        raise ValueError(f"cannot complete run in '{run.status}' status")
    snapshot = model_snapshot if model_snapshot is not None else run.model_snapshot
    return replace(
        run,
        status="completed",
        model_snapshot=snapshot,
        completed_at=utc_now(),
        error_message=None,
    )


def mark_run_failed(run: TrackingRun, error_message: str) -> TrackingRun:
    """将 TrackingRun 状态流转为 failed 并记录错误信息。"""

    if run.status in {"completed", "cancelled"}:
        raise ValueError(f"cannot fail run already in '{run.status}' status")
    return replace(
        run,
        status="failed",
        error_message=error_message,
        completed_at=utc_now(),
    )


def mark_run_cancelled(run: TrackingRun) -> TrackingRun:
    """将 TrackingRun 状态流转为 cancelled。"""

    if run.status in {"completed", "failed"}:
        raise ValueError(f"cannot cancel run already in '{run.status}' status")
    return replace(
        run,
        status="cancelled",
        completed_at=utc_now(),
    )
