"""派生数据的溯源值对象与失效标记辅助函数。"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject, require_aware_datetime


@dataclass(frozen=True)
class DerivedInput:
    """生成派生序列时所依据的原始观测选择条件。"""

    track_id: UUID
    source_filter: str | None = None
    include_superseded: bool = False
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.include_superseded:
            raise ValueError("Phase 1 derived inputs cannot include superseded points")


@dataclass(frozen=True)
class DerivedData:
    """可复现的派生序列；Phase 1 只存储，不计算。"""

    derived_id: UUID
    track_id: UUID
    kind: str
    input: DerivedInput
    pipeline: tuple[JsonObject, ...]
    frames: tuple[int, ...]
    values: tuple[tuple[float, ...], ...] | None
    payload_ref: str | None
    unit: str
    produced_by: str
    created_at: datetime
    status: str
    calibration_ref: UUID | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.track_id != self.input.track_id:
            raise ValueError("DerivedData track_id must match its input")
        if not self.kind.strip() or not self.unit.strip() or not self.produced_by.strip():
            raise ValueError("kind, unit, and produced_by must not be blank")
        if self.status not in {"valid", "stale"}:
            raise ValueError("DerivedData status must be valid or stale")
        if any(frame_index < 0 for frame_index in self.frames):
            raise ValueError("derived frame indices must be non-negative")
        if self.values is not None and len(self.values) != len(self.frames):
            raise ValueError("derived frames and values must have equal lengths")
        if self.values is not None and self.payload_ref is not None:
            raise ValueError("values and payload_ref are mutually exclusive")
        require_aware_datetime(self.created_at, "created_at")


def mark_calibrations_stale(
    derived: tuple[DerivedData, ...], calibration_ids: set[UUID]
) -> tuple[DerivedData, ...]:
    """仅将标定溯源发生变化的派生序列标记为 stale。"""

    return tuple(
        replace(item, status="stale")
        if item.calibration_ref in calibration_ids and item.status != "stale"
        else item
        for item in derived
    )


def mark_tracks_stale(
    derived: tuple[DerivedData, ...], track_ids: set[UUID]
) -> tuple[DerivedData, ...]:
    """将原始观测或时间输入发生变化的派生序列标记为 stale。"""

    return tuple(
        replace(item, status="stale")
        if item.track_id in track_ids and item.status != "stale"
        else item
        for item in derived
    )
