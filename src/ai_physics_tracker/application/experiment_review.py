"""四 role 推理筛选与 run 级审核记录(application 层,Qt-free)。"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from pathlib import Path
from uuid import UUID

from ai_physics_tracker.application.difficult_frames import MiningParams, mine_difficult_frames
from ai_physics_tracker.application.suggested_frame_review import ReviewPredictionSnapshot
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumExperiment
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.infrastructure.dlc_predictions import JointRawPredictions, read_joint_raw_predictions
from ai_physics_tracker.infrastructure.hashing import file_sha256

EXPERIMENT_REVIEW_KEY = "experiment_frame_review_v1"


@dataclass(frozen=True)
class ExperimentFrameCandidate:
    frame_index: int
    predictions: dict[str, ReviewPredictionSnapshot | None]
    role_reasons: dict[str, tuple[str, ...]]
    geometry_reasons: tuple[str, ...]
    pivot_offset_px: float | None
    screening_score: float

    def __post_init__(self) -> None:
        if type(self.frame_index) is not int or self.frame_index < 0:
            raise ValueError("joint review frame_index must be non-negative")
        if set(self.predictions) != set(ROLE_ORDER) or set(self.role_reasons) != set(ROLE_ORDER):
            raise ValueError("joint review candidate must contain exactly four roles")
        if any(not isinstance(reasons, tuple) or
               any(not isinstance(reason, str) for reason in reasons)
               for reasons in self.role_reasons.values()):
            raise ValueError("joint review role reasons must be tuples of strings")
        if any(not isinstance(reason, str) for reason in self.geometry_reasons):
            raise ValueError("joint review geometry reasons must be strings")
        if (self.pivot_offset_px is not None and
                (not isfinite(self.pivot_offset_px) or self.pivot_offset_px < 0)):
            raise ValueError("joint review pivot offset must be finite and non-negative")
        if not isfinite(self.screening_score) or self.screening_score < 0:
            raise ValueError("joint review screening score must be finite and non-negative")

    @property
    def complete(self) -> bool:
        return all(self.predictions[role] is not None for role in ROLE_ORDER)

    def to_dict(self) -> dict[str, object]:
        return {
            "frame_index": self.frame_index,
            "predictions": {role: (value.to_dict() if value else None)
                            for role, value in self.predictions.items()},
            "role_reasons": {role: list(reasons) for role, reasons in self.role_reasons.items()},
            "geometry_reasons": list(self.geometry_reasons),
            "pivot_offset_px": self.pivot_offset_px,
            "screening_score": self.screening_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ExperimentFrameCandidate:
        predictions = data["predictions"]
        reasons = data["role_reasons"]
        if not isinstance(predictions, dict) or not isinstance(reasons, dict):
            raise ValueError("joint review candidate must contain per-role predictions and reasons")
        if set(predictions) != set(ROLE_ORDER) or set(reasons) != set(ROLE_ORDER):
            raise ValueError("joint review candidate must contain exactly four roles")
        if any(not isinstance(reasons[role], list)
               or any(not isinstance(reason, str) for reason in reasons[role])
               for role in ROLE_ORDER):
            raise ValueError("joint review role reasons must be lists of strings")
        if (type(data.get("frame_index")) is not int
                or not isinstance(data.get("geometry_reasons"), list)
                or isinstance(data.get("screening_score"), bool)):
            raise ValueError("joint review candidate has malformed frame or diagnostics")
        offset = data["pivot_offset_px"]
        return cls(
            frame_index=int(data["frame_index"]),
            predictions={role: ReviewPredictionSnapshot.from_dict(predictions[role])
                         for role in ROLE_ORDER},
            role_reasons={role: tuple(reasons[role]) for role in ROLE_ORDER},
            geometry_reasons=tuple(data["geometry_reasons"]),
            pivot_offset_px=None if offset is None else float(offset),
            screening_score=float(data["screening_score"]),
        )


def read_experiment_candidate(
    project_root: Path, run: TrackingRun, experiment: PendulumExperiment, frame_count: int,
) -> JointRawPredictions:
    """审核或激活前复核 run 绑定与不可变 raw artifact。"""

    if (run.status != "completed" or run.task_type != "infer"
            or run.config.get("request_kind") != "experiment-joint-inference-v1"
            or run.experiment_id != experiment.experiment_id
            or run.role_bindings != experiment.roles):
        raise ValueError("run is not a completed candidate for the current four-role binding")
    relative = run.extra_fields.get("prediction_path")
    expected_hash = run.extra_fields.get("prediction_sha256")
    mapping = run.config.get("bodypart_mapping")
    scorer = run.extra_fields.get("scorer")
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ValueError("candidate prediction artifact identity is missing")
    if not isinstance(mapping, list) or not isinstance(scorer, str):
        raise ValueError("candidate bodypart mapping or scorer is missing")
    root = project_root.resolve()
    artifact = (root / relative).resolve()
    if not artifact.is_relative_to(root) or not artifact.is_file():
        raise ValueError("candidate prediction artifact is unavailable")
    if file_sha256(artifact) != expected_hash:
        raise ValueError("candidate prediction artifact hash changed")
    return read_joint_raw_predictions(
        artifact, tuple(tuple(pair) for pair in mapping),
        frame_count=frame_count, expected_scorer=scorer,
    )


def frame_diagnostic(
    raw: JointRawPredictions, frame_index: int, *, confidence_threshold: float,
    fixed_pivot_px: tuple[float, float] | None,
    mined_reasons: dict[str, tuple[str, ...]] | None = None,
    screening_score: float = 0.0,
) -> ExperimentFrameCandidate:
    """描述测量完整性;不做科学 mask 或 pivot 截断。"""

    if not 0 <= frame_index < raw.frame_count:
        raise ValueError("review frame is outside candidate")
    if not 0 <= confidence_threshold <= 1:
        raise ValueError("screening confidence threshold must be in [0, 1]")
    predictions = {
        role: ReviewPredictionSnapshot.from_raw_prediction(rows[frame_index])
        for role, rows in raw.by_role
    }
    reasons: dict[str, tuple[str, ...]] = {}
    for role in ROLE_ORDER:
        found = list((mined_reasons or {}).get(role, ()))
        prediction = predictions[role]
        if prediction is None and "missing" not in found:
            found.append("missing")
        elif prediction is not None and prediction.confidence < confidence_threshold:
            if "low_confidence" not in found:
                found.append("low_confidence")
        reasons[role] = tuple(found)
    geometry: list[str] = []
    top, bottom, tip = (predictions[role] for role in ("body_top", "body_bottom", "tip"))
    if (top is None or bottom is None
            or hypot(top.pixel_x - bottom.pixel_x, top.pixel_y - bottom.pixel_y) == 0.0):
        geometry.append("body_axis_unavailable")
    if (tip is None or fixed_pivot_px is None
            or hypot(tip.pixel_x - fixed_pivot_px[0], tip.pixel_y - fixed_pivot_px[1]) == 0.0):
        geometry.append("tip_radius_unavailable")
    tracked_pivot = predictions["pivot"]
    offset = None if tracked_pivot is None or fixed_pivot_px is None else hypot(
        tracked_pivot.pixel_x - fixed_pivot_px[0],
        tracked_pivot.pixel_y - fixed_pivot_px[1],
    )
    return ExperimentFrameCandidate(
        frame_index, predictions, reasons, tuple(geometry), offset, screening_score,
    )


def build_experiment_review_queue(
    raw: JointRawPredictions, *, fps_nominal: float,
    confidence_threshold: float, fixed_pivot_px: tuple[float, float] | None,
    top_n: int = 20,
) -> tuple[ExperimentFrameCandidate, ...]:
    """把既有单 role 筛选信号合并为帧级审核队列。"""

    params = MiningParams(top_n=top_n, confidence_threshold=confidence_threshold)
    signals: dict[int, dict[str, tuple[str, ...]]] = {}
    scores: dict[int, float] = {}
    for role, rows in raw.by_role:
        outcome = mine_difficult_frames(
            rows, zone_start=0, zone_end=raw.frame_count - 1,
            fps_nominal=fps_nominal, params=params,
        )
        for item in outcome.shortlist:
            signals.setdefault(item.frame_index, {})[role] = item.reasons
            scores[item.frame_index] = max(scores.get(item.frame_index, 0.0), item.total_score)
    # 几何退化帧可能不被逐 role 的跳变/置信信号捕获,这里显式补扫
    geometry_extra = 0
    for frame_index in range(raw.frame_count):
        if frame_index in signals:
            continue
        diagnostic = frame_diagnostic(
            raw, frame_index, confidence_threshold=confidence_threshold,
            fixed_pivot_px=fixed_pivot_px,
        )
        if diagnostic.geometry_reasons and geometry_extra < top_n:
            signals[frame_index] = {}
            geometry_extra += 1
    # HR 反馈(2026-09-29):逐 role 各取 top_n 合并可达 4×top_n+几何帧(实测
    # 84 帧),审核量不现实——按帧级 screening score 排序后统一截断 top_n
    ranked = sorted(signals, key=lambda index: (-scores.get(index, 0.0), index))
    return tuple(
        frame_diagnostic(
            raw, frame_index, confidence_threshold=confidence_threshold,
            fixed_pivot_px=fixed_pivot_px, mined_reasons=signals[frame_index],
            screening_score=scores.get(frame_index, 0.0),
        )
        for frame_index in ranked[:top_n]
    )


def review_record_ids(record: dict[str, object]) -> dict[str, UUID]:
    """校验一条持久化的帧审核决定并返回其修正点 ID。"""

    if record.get("disposition") not in {"accepted", "skipped", "corrected"}:
        raise ValueError("invalid experiment review disposition")
    if not isinstance(record.get("reviewed_at"), str):
        raise ValueError("experiment review timestamp is missing")
    raw_ids = record.get("manual_point_ids")
    if not isinstance(raw_ids, dict) or not set(raw_ids) <= set(ROLE_ORDER):
        raise ValueError("experiment review correction roles are invalid")
    ids = {role: UUID(value) for role, value in raw_ids.items()}
    if (record["disposition"] == "corrected") != bool(ids):
        raise ValueError("experiment review correction IDs disagree with disposition")
    return ids
