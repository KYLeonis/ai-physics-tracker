"""Phase 5.4 — Iteration History, Fixed Validation & Result Activation contracts.

Qt-free pure Python value objects and serialization helpers for:
1. Fixed validation series and immutable label snapshots.
2. Track refinement state (active infer run, activation history, validation series).
3. Training refinement iteration info (iteration index, validation series, training labels).
4. Inference prediction summary (coverage, eligible/missing/low-confidence counts).

Contracts follow ADR-0014 and project-format.md schema v1 tolerant extensions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
import math
from typing import Any, Iterable
from uuid import UUID, uuid4

from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import TrackingRun

logger = logging.getLogger(__name__)

REFINEMENT_STATE_KEY = "refinement_state_v1"
REFINEMENT_ITERATION_KEY = "refinement_iteration_v1"
PREDICTION_SUMMARY_KEY = "prediction_summary_v1"


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(val: Any) -> str:
    if not isinstance(val, str) or not val.strip():
        return _now_iso_utc()
    try:
        dt = datetime.fromisoformat(val)
        return dt.isoformat()
    except Exception:
        return _now_iso_utc()


def _parse_uuid(val: Any) -> UUID | None:
    if isinstance(val, UUID):
        return val
    if isinstance(val, str):
        try:
            return UUID(val)
        except (ValueError, TypeError):
            return None
    return None


@dataclass(frozen=True)
class ValidationLabelSnapshot:
    """固定验证集中的不可变单点快照。"""

    point_id: UUID
    frame_index: int
    pixel_x: float
    pixel_y: float
    modified_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.point_id, UUID):
            raise TypeError("point_id must be a UUID")
        if not isinstance(self.frame_index, int) or self.frame_index < 0:
            raise ValueError(f"frame_index must be a non-negative int, got {self.frame_index}")
        if not math.isfinite(self.pixel_x) or not math.isfinite(self.pixel_y):
            raise ValueError(f"coordinates must be finite floats: ({self.pixel_x}, {self.pixel_y})")


@dataclass(frozen=True)
class ValidationSeries:
    """不可变固定验证集。

    由用户从当前 active manual points 显式冻结产生。
    一旦创建即不可原地修改；若 manual points 变更，当前 series 标为无效，需创建新 series。
    """

    series_id: UUID
    name: str
    created_at: str
    label_snapshots: tuple[ValidationLabelSnapshot, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.series_id, UUID):
            raise TypeError("series_id must be a UUID")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.label_snapshots, tuple):
            object.__setattr__(self, "label_snapshots", tuple(self.label_snapshots))
        # 确保按 frame_index 递增排序
        sorted_snaps = tuple(sorted(self.label_snapshots, key=lambda s: s.frame_index))
        object.__setattr__(self, "label_snapshots", sorted_snaps)

    @property
    def frame_indices(self) -> tuple[int, ...]:
        return tuple(snap.frame_index for snap in self.label_snapshots)


@dataclass(frozen=True)
class ActivationRecord:
    """轨迹结果激活/替换/清空操作的历史快照记录。"""

    record_id: UUID
    timestamp: str
    action: str  # "activate" | "replace" | "clear"
    from_run_id: UUID | None
    to_run_id: UUID | None
    point_count: int
    manual_preserved_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, UUID):
            raise TypeError("record_id must be a UUID")
        if self.action not in {"activate", "replace", "clear"}:
            raise ValueError(f"action must be 'activate', 'replace', or 'clear', got {self.action}")


@dataclass(frozen=True)
class RefinementState:
    """Track 级别的迭代与结果激活状态（保存在 Track.extra_fields["refinement_state_v1"]）。"""

    active_infer_run_id: UUID | None = None
    activation_history: tuple[ActivationRecord, ...] = ()
    active_validation_series_id: UUID | None = None
    validation_series: tuple[ValidationSeries, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.activation_history, tuple):
            object.__setattr__(self, "activation_history", tuple(self.activation_history))
        if not isinstance(self.validation_series, tuple):
            object.__setattr__(self, "validation_series", tuple(self.validation_series))

    def get_series(self, series_id: UUID) -> ValidationSeries | None:
        for s in self.validation_series:
            if s.series_id == series_id:
                return s
        return None

    @property
    def active_series(self) -> ValidationSeries | None:
        if self.active_validation_series_id is None:
            return None
        return self.get_series(self.active_validation_series_id)


@dataclass(frozen=True)
class RefinementIterationInfo:
    """训练运行 (train run) 的迭代解释层快照。"""

    iteration_index: int
    previous_training_run_id: UUID | None = None
    source_infer_run_id: UUID | None = None
    validation_series_id: UUID | None = None
    training_labels: tuple[ValidationLabelSnapshot, ...] = ()
    review_summary: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.iteration_index, int) or self.iteration_index < 0:
            raise ValueError(f"iteration_index must be a non-negative int, got {self.iteration_index}")
        if not isinstance(self.training_labels, tuple):
            object.__setattr__(self, "training_labels", tuple(self.training_labels))


@dataclass(frozen=True)
class PredictionSummary:
    """推理运行 (infer run) 的原始预测与覆盖度统计快照。"""

    row_count: int
    eligible_count: int
    missing_count: int
    low_confidence_count: int
    threshold: float
    coverage: float

    def __post_init__(self) -> None:
        for name, val in [
            ("row_count", self.row_count),
            ("eligible_count", self.eligible_count),
            ("missing_count", self.missing_count),
            ("low_confidence_count", self.low_confidence_count),
        ]:
            if not isinstance(val, int) or val < 0:
                raise ValueError(f"{name} must be non-negative int, got {val}")
        if not math.isfinite(self.threshold) or not (0.0 <= self.threshold <= 1.0):
            raise ValueError(f"threshold must be in [0, 1], got {self.threshold}")
        if not math.isfinite(self.coverage) or not (0.0 <= self.coverage <= 1.0):
            raise ValueError(f"coverage must be in [0, 1], got {self.coverage}")


# --- 验证集一致性校验 ---


def check_validation_series_consistency(
    series: ValidationSeries,
    current_manual_points: Iterable[TrackPoint],
) -> tuple[bool, str | None]:
    """校验固定验证集与当前 active manual points 是否完全一致。

    返回: (is_valid, invalid_reason)
    若点被删除、移动帧号或修改坐标（容差 1e-5），判定为无效。
    """
    if not series.label_snapshots:
        return False, "Validation series has no label snapshots"

    point_map = {p.point_id: p for p in current_manual_points}
    frame_map = {p.frame_index: p for p in current_manual_points}
    for snap in series.label_snapshots:
        pt_id = point_map.get(snap.point_id)
        pt_frame = frame_map.get(snap.frame_index)

        # 帧上无任何点且原 point_id 也不存在 -> 被删除
        if pt_id is None and pt_frame is None:
            return False, f"Manual point for frame {snap.frame_index} was deleted"

        # 原 point_id 存在但在不同帧 -> 发生了移动
        if pt_id is not None and pt_id.frame_index != snap.frame_index:
            return (
                False,
                f"Manual point moved from frame {snap.frame_index} to frame {pt_id.frame_index}",
            )

        # 帧上有 active manual 点，但 ID 不同（重标）或坐标有差异 -> 发生了修改
        target_pt = pt_frame if pt_frame is not None else pt_id
        assert target_pt is not None
        if target_pt.point_id != snap.point_id or not math.isclose(
            target_pt.pixel_x, snap.pixel_x, abs_tol=1e-5
        ) or not math.isclose(target_pt.pixel_y, snap.pixel_y, abs_tol=1e-5):
            return (
                False,
                f"Coordinates of manual point on frame {snap.frame_index} were modified",
            )

    return True, None


# --- 序列化与反序列化 ---


def serialize_validation_snapshot(snap: ValidationLabelSnapshot) -> dict[str, Any]:
    return {
        "point_id": str(snap.point_id),
        "frame_index": snap.frame_index,
        "pixel_x": snap.pixel_x,
        "pixel_y": snap.pixel_y,
        "modified_at": snap.modified_at,
    }


def deserialize_validation_snapshot(data: Any) -> ValidationLabelSnapshot | None:
    if not isinstance(data, dict):
        return None
    p_id = _parse_uuid(data.get("point_id"))
    f_idx = data.get("frame_index")
    px = data.get("pixel_x")
    py = data.get("pixel_y")
    m_at = _parse_iso(data.get("modified_at"))
    if p_id is None or not isinstance(f_idx, int) or px is None or py is None:
        return None
    try:
        return ValidationLabelSnapshot(
            point_id=p_id,
            frame_index=f_idx,
            pixel_x=float(px),
            pixel_y=float(py),
            modified_at=m_at,
        )
    except (ValueError, TypeError):
        return None


def serialize_validation_series(series: ValidationSeries) -> dict[str, Any]:
    return {
        "series_id": str(series.series_id),
        "name": series.name,
        "created_at": series.created_at,
        "label_snapshots": [serialize_validation_snapshot(s) for s in series.label_snapshots],
    }


def deserialize_validation_series(data: Any) -> ValidationSeries | None:
    if not isinstance(data, dict):
        return None
    s_id = _parse_uuid(data.get("series_id"))
    name = data.get("name")
    c_at = _parse_iso(data.get("created_at"))
    raw_snaps = data.get("label_snapshots")
    if s_id is None or not name or not isinstance(name, str) or not isinstance(raw_snaps, list):
        return None
    snaps: list[ValidationLabelSnapshot] = []
    for item in raw_snaps:
        s = deserialize_validation_snapshot(item)
        if s is not None:
            snaps.append(s)
    try:
        return ValidationSeries(
            series_id=s_id,
            name=name,
            created_at=c_at,
            label_snapshots=tuple(snaps),
        )
    except (ValueError, TypeError):
        return None


def serialize_activation_record(rec: ActivationRecord) -> dict[str, Any]:
    return {
        "record_id": str(rec.record_id),
        "timestamp": rec.timestamp,
        "action": rec.action,
        "from_run_id": str(rec.from_run_id) if rec.from_run_id is not None else None,
        "to_run_id": str(rec.to_run_id) if rec.to_run_id is not None else None,
        "point_count": rec.point_count,
        "manual_preserved_count": rec.manual_preserved_count,
    }


def deserialize_activation_record(data: Any) -> ActivationRecord | None:
    if not isinstance(data, dict):
        return None
    rec_id = _parse_uuid(data.get("record_id"))
    ts = _parse_iso(data.get("timestamp"))
    act = data.get("action")
    from_r = _parse_uuid(data.get("from_run_id"))
    to_r = _parse_uuid(data.get("to_run_id"))
    pt_cnt = data.get("point_count", 0)
    m_cnt = data.get("manual_preserved_count", 0)
    if rec_id is None or act not in {"activate", "replace", "clear"}:
        return None
    try:
        return ActivationRecord(
            record_id=rec_id,
            timestamp=ts,
            action=act,
            from_run_id=from_r,
            to_run_id=to_r,
            point_count=int(pt_cnt),
            manual_preserved_count=int(m_cnt),
        )
    except (ValueError, TypeError):
        return None


def serialize_refinement_state(state: RefinementState) -> dict[str, Any]:
    return {
        "active_infer_run_id": (
            str(state.active_infer_run_id) if state.active_infer_run_id is not None else None
        ),
        "activation_history": [serialize_activation_record(r) for r in state.activation_history],
        "active_validation_series_id": (
            str(state.active_validation_series_id)
            if state.active_validation_series_id is not None
            else None
        ),
        "validation_series": [serialize_validation_series(s) for s in state.validation_series],
    }


def deserialize_refinement_state(data: Any) -> RefinementState:
    if not isinstance(data, dict):
        return RefinementState()
    active_infer = _parse_uuid(data.get("active_infer_run_id"))
    active_val = _parse_uuid(data.get("active_validation_series_id"))

    history: list[ActivationRecord] = []
    raw_hist = data.get("activation_history")
    if isinstance(raw_hist, list):
        for item in raw_hist:
            rec = deserialize_activation_record(item)
            if rec is not None:
                history.append(rec)

    series_list: list[ValidationSeries] = []
    raw_series = data.get("validation_series")
    if isinstance(raw_series, list):
        for item in raw_series:
            ser = deserialize_validation_series(item)
            if ser is not None:
                series_list.append(ser)

    return RefinementState(
        active_infer_run_id=active_infer,
        activation_history=tuple(history),
        active_validation_series_id=active_val,
        validation_series=tuple(series_list),
    )


def attach_refinement_state(track: Track, state: RefinementState) -> Track:
    extras = dict(track.extra_fields)
    extras[REFINEMENT_STATE_KEY] = serialize_refinement_state(state)
    return replace(track, extra_fields=extras)


def extract_refinement_state(track: Track) -> RefinementState:
    raw = track.extra_fields.get(REFINEMENT_STATE_KEY)
    return deserialize_refinement_state(raw)


# --- RefinementIterationInfo ---


def serialize_refinement_iteration(info: RefinementIterationInfo) -> dict[str, Any]:
    return {
        "iteration_index": info.iteration_index,
        "previous_training_run_id": (
            str(info.previous_training_run_id)
            if info.previous_training_run_id is not None
            else None
        ),
        "source_infer_run_id": (
            str(info.source_infer_run_id) if info.source_infer_run_id is not None else None
        ),
        "validation_series_id": (
            str(info.validation_series_id) if info.validation_series_id is not None else None
        ),
        "training_labels": [serialize_validation_snapshot(s) for s in info.training_labels],
        "review_summary": dict(info.review_summary) if info.review_summary is not None else None,
    }


def deserialize_refinement_iteration(data: Any) -> RefinementIterationInfo | None:
    if not isinstance(data, dict):
        return None
    idx = data.get("iteration_index")
    if not isinstance(idx, int) or idx < 0:
        return None
    prev_train = _parse_uuid(data.get("previous_training_run_id"))
    src_infer = _parse_uuid(data.get("source_infer_run_id"))
    val_id = _parse_uuid(data.get("validation_series_id"))

    labels: list[ValidationLabelSnapshot] = []
    raw_labels = data.get("training_labels")
    if isinstance(raw_labels, list):
        for item in raw_labels:
            snap = deserialize_validation_snapshot(item)
            if snap is not None:
                labels.append(snap)

    rev_sum = data.get("review_summary")
    review_summary = dict(rev_sum) if isinstance(rev_sum, dict) else None

    try:
        return RefinementIterationInfo(
            iteration_index=idx,
            previous_training_run_id=prev_train,
            source_infer_run_id=src_infer,
            validation_series_id=val_id,
            training_labels=tuple(labels),
            review_summary=review_summary,
        )
    except (ValueError, TypeError):
        return None


def attach_refinement_iteration(run: TrackingRun, info: RefinementIterationInfo) -> TrackingRun:
    extras = dict(run.extra_fields)
    extras[REFINEMENT_ITERATION_KEY] = serialize_refinement_iteration(info)
    return replace(run, extra_fields=extras)


def extract_refinement_iteration(run: TrackingRun) -> RefinementIterationInfo | None:
    raw = run.extra_fields.get(REFINEMENT_ITERATION_KEY)
    return deserialize_refinement_iteration(raw)


# --- PredictionSummary ---


def serialize_prediction_summary(summary: PredictionSummary) -> dict[str, Any]:
    return {
        "row_count": summary.row_count,
        "eligible_count": summary.eligible_count,
        "missing_count": summary.missing_count,
        "low_confidence_count": summary.low_confidence_count,
        "threshold": summary.threshold,
        "coverage": summary.coverage,
    }


def deserialize_prediction_summary(data: Any) -> PredictionSummary | None:
    if not isinstance(data, dict):
        return None
    try:
        return PredictionSummary(
            row_count=int(data["row_count"]),
            eligible_count=int(data["eligible_count"]),
            missing_count=int(data["missing_count"]),
            low_confidence_count=int(data["low_confidence_count"]),
            threshold=float(data["threshold"]),
            coverage=float(data["coverage"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


def attach_prediction_summary(run: TrackingRun, summary: PredictionSummary) -> TrackingRun:
    extras = dict(run.extra_fields)
    extras[PREDICTION_SUMMARY_KEY] = serialize_prediction_summary(summary)
    return replace(run, extra_fields=extras)


def extract_prediction_summary(run: TrackingRun) -> PredictionSummary | None:
    raw = run.extra_fields.get(PREDICTION_SUMMARY_KEY)
    return deserialize_prediction_summary(raw)
