"""应用层建议帧审核值对象与契约：纯函数、Qt-free（Phase 5.3 ADR-0013）。

负责困难帧挖掘结果与人工审核记录在 TrackingRun.extra_fields["suggested_frame_review_v1"]
中的持久化契约、数据校验、统计与同 run 抑制过滤。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from math import isfinite, isnan
from typing import Any
from uuid import UUID

from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.infrastructure.dlc_predictions import RawPrediction

logger = logging.getLogger(__name__)

SUGGESTED_FRAME_REVIEW_KEY = "suggested_frame_review_v1"

DISPOSITION_ACCEPTED = "accepted"
DISPOSITION_CORRECTED = "corrected"
DISPOSITION_SKIPPED = "skipped"
VALID_DISPOSITIONS = frozenset(
    {DISPOSITION_ACCEPTED, DISPOSITION_CORRECTED, DISPOSITION_SKIPPED}
)


@dataclass(frozen=True)
class ReviewPredictionSnapshot:
    """审核时绑定的单帧预测快照（ADR-0013）。

    所有分量必须为有限浮点数；缺测在上一层直接以 None 表达（写入 JSON null），
    绝不存 NaN（data-model.md §3.5）。
    """

    pixel_x: float
    pixel_y: float
    confidence: float

    def __post_init__(self) -> None:
        for label, val in (
            ("pixel_x", self.pixel_x),
            ("pixel_y", self.pixel_y),
            ("confidence", self.confidence),
        ):
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(f"{label} must be a finite float")
            f_val = float(val)
            if not isfinite(f_val):
                raise ValueError(f"{label} must be a finite float")
            object.__setattr__(self, label, f_val)

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in range [0.0, 1.0]")

    def to_dict(self) -> dict[str, float]:
        return {
            "pixel_x": self.pixel_x,
            "pixel_y": self.pixel_y,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Any) -> ReviewPredictionSnapshot | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError("prediction snapshot must be a dict or null")
        try:
            return cls(
                pixel_x=data["pixel_x"],
                pixel_y=data["pixel_y"],
                confidence=data["confidence"],
            )
        except (KeyError, TypeError) as err:
            raise ValueError(f"malformed prediction snapshot: {err}") from err

    @classmethod
    def from_raw_prediction(cls, raw: RawPrediction | None) -> ReviewPredictionSnapshot | None:
        """从基础设施 RawPrediction 转换；若缺测或含 NaN 则返回 None。"""
        if raw is None:
            return None
        if isnan(raw.pixel_x) or isnan(raw.pixel_y) or isnan(raw.confidence):
            return None
        if not (isfinite(raw.pixel_x) and isfinite(raw.pixel_y) and isfinite(raw.confidence)):
            return None
        return cls(
            pixel_x=float(raw.pixel_x),
            pixel_y=float(raw.pixel_y),
            confidence=float(raw.confidence),
        )


@dataclass(frozen=True)
class ReviewCandidate:
    """当前批次中的单个候选帧。"""

    frame_index: int
    prediction: ReviewPredictionSnapshot | None
    components: dict[str, float]
    raw_components: dict[str, float]
    reasons: tuple[str, ...]
    total_score: float

    def __post_init__(self) -> None:
        if isinstance(self.frame_index, bool) or not isinstance(self.frame_index, int):
            raise ValueError("frame_index must be an integer")
        if self.frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        for mapping_name, mapping in (
            ("components", self.components),
            ("raw_components", self.raw_components),
        ):
            if not isinstance(mapping, dict):
                raise ValueError(f"{mapping_name} must be a dict")
            for k, v in mapping.items():
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(float(v)):
                    raise ValueError(f"{mapping_name} value for {k} must be a finite float")
        if not isinstance(self.reasons, (tuple, list)):
            raise ValueError("reasons must be a tuple or list of strings")
        object.__setattr__(self, "reasons", tuple(str(r) for r in self.reasons))
        if isinstance(self.total_score, bool) or not isinstance(self.total_score, (int, float)):
            raise ValueError("total_score must be a finite float")
        f_score = float(self.total_score)
        if not isfinite(f_score):
            raise ValueError("total_score must be a finite float")
        object.__setattr__(self, "total_score", f_score)


@dataclass(frozen=True)
class ReviewRecord:
    """单帧的人工审核提交记录（ADR-0013）。

    disposition 为 accepted/corrected/skipped。
    corrected 必须附带 manual_point_id；accepted/skipped 必须为 None。
    """

    disposition: str
    reviewed_at: str
    request_id: UUID
    prediction: ReviewPredictionSnapshot | None
    manual_point_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.disposition not in VALID_DISPOSITIONS:
            raise ValueError(
                f"invalid disposition: {self.disposition!r}; expected one of {VALID_DISPOSITIONS}"
            )
        if not isinstance(self.reviewed_at, str) or not self.reviewed_at.strip():
            raise ValueError("reviewed_at must be a non-empty ISO timestamp string")
        if not isinstance(self.request_id, UUID):
            raise ValueError("request_id must be a UUID")
        if self.disposition == DISPOSITION_CORRECTED:
            if not isinstance(self.manual_point_id, UUID):
                raise ValueError("corrected disposition requires a valid UUID manual_point_id")
        else:
            if self.manual_point_id is not None:
                raise ValueError(
                    f"{self.disposition} disposition must not have a manual_point_id"
                )


@dataclass(frozen=True)
class ActiveReviewBatch:
    """当前活动的困难帧挖掘批次。"""

    request_id: UUID
    params_snapshot: dict[str, Any]
    candidates: tuple[ReviewCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, UUID):
            raise ValueError("request_id must be a UUID")
        if not isinstance(self.params_snapshot, dict):
            raise ValueError("params_snapshot must be a dict")
        if not isinstance(self.candidates, (tuple, list)):
            raise ValueError("candidates must be a tuple or list of ReviewCandidate")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        seen_frames: set[int] = set()
        for cand in self.candidates:
            if not isinstance(cand, ReviewCandidate):
                raise ValueError("all candidates must be ReviewCandidate instances")
            if cand.frame_index in seen_frames:
                raise ValueError(f"duplicate frame_index in batch: {cand.frame_index}")
            seen_frames.add(cand.frame_index)


@dataclass(frozen=True)
class SuggestedFrameReviewState:
    """绑定于单个 completed infer run 的审核状态容器（ADR-0013）。"""

    active_batch: ActiveReviewBatch | None
    reviewed_frames: dict[int, ReviewRecord]

    def __post_init__(self) -> None:
        if self.active_batch is not None and not isinstance(self.active_batch, ActiveReviewBatch):
            raise ValueError("active_batch must be ActiveReviewBatch or None")
        if not isinstance(self.reviewed_frames, dict):
            raise ValueError("reviewed_frames must be a dict mapping int frame_index to ReviewRecord")
        for f_idx, record in self.reviewed_frames.items():
            if isinstance(f_idx, bool) or not isinstance(f_idx, int) or f_idx < 0:
                raise ValueError(f"invalid frame index in reviewed_frames: {f_idx}")
            if not isinstance(record, ReviewRecord):
                raise ValueError(f"invalid ReviewRecord for frame {f_idx}")


@dataclass(frozen=True)
class ReviewBatchSummary:
    """当前批次的统计概要（供 UI 与后续 5.5 Advisor 消费）。"""

    total_candidates: int
    pending_count: int
    accepted_count: int
    corrected_count: int
    skipped_count: int
    total_reviewed: int


def compute_batch_summary(state: SuggestedFrameReviewState | None) -> ReviewBatchSummary:
    """根据当前审核状态计算当前批次的统计概要。"""
    if state is None or state.active_batch is None:
        return ReviewBatchSummary(
            total_candidates=0,
            pending_count=0,
            accepted_count=0,
            corrected_count=0,
            skipped_count=0,
            total_reviewed=0,
        )

    candidates = state.active_batch.candidates
    total_candidates = len(candidates)
    accepted = 0
    corrected = 0
    skipped = 0
    pending = 0

    for cand in candidates:
        record = state.reviewed_frames.get(cand.frame_index)
        if record is None:
            pending += 1
        elif record.disposition == DISPOSITION_ACCEPTED:
            accepted += 1
        elif record.disposition == DISPOSITION_CORRECTED:
            corrected += 1
        elif record.disposition == DISPOSITION_SKIPPED:
            skipped += 1
        else:
            pending += 1

    return ReviewBatchSummary(
        total_candidates=total_candidates,
        pending_count=pending,
        accepted_count=accepted,
        corrected_count=corrected,
        skipped_count=skipped,
        total_reviewed=accepted + corrected + skipped,
    )


def get_candidate_disposition(
    state: SuggestedFrameReviewState | None, frame_index: int
) -> str:
    """返回指定帧在当前状态下的审核状态（pending / accepted / corrected / skipped）。"""
    if state is None:
        return "pending"
    record = state.reviewed_frames.get(frame_index)
    if record is None:
        return "pending"
    return record.disposition


def get_excluded_frames_for_run(state: SuggestedFrameReviewState | None) -> frozenset[int]:
    """返回同一 infer run 后续 mining 需排除的帧（已 Accept / Skip 的帧，R2.8）。"""
    if state is None:
        return frozenset()
    return frozenset(
        frame_idx
        for frame_idx, record in state.reviewed_frames.items()
        if record.disposition in {DISPOSITION_ACCEPTED, DISPOSITION_SKIPPED}
    )


def get_prior_correct_frames_for_run(state: SuggestedFrameReviewState | None) -> frozenset[int]:
    """返回同一 infer run 中已被 Correct 标记的帧集合。"""
    if state is None:
        return frozenset()
    return frozenset(
        frame_idx
        for frame_idx, record in state.reviewed_frames.items()
        if record.disposition == DISPOSITION_CORRECTED
    )


def serialize_review_state(state: SuggestedFrameReviewState) -> dict[str, Any]:
    """将审核状态序列化为 project.json schema v1 兼容的 dict（ADR-0013）。"""
    payload: dict[str, Any] = {
        "active_batch": None,
        "reviewed_frames": {},
    }

    if state.active_batch is not None:
        batch = state.active_batch
        payload["active_batch"] = {
            "request_id": str(batch.request_id),
            "params_snapshot": dict(batch.params_snapshot),
            "candidates": [
                {
                    "frame_index": c.frame_index,
                    "prediction": c.prediction.to_dict() if c.prediction is not None else None,
                    "components": dict(c.components),
                    "raw_components": dict(c.raw_components),
                    "reasons": list(c.reasons),
                    "total_score": c.total_score,
                }
                for c in batch.candidates
            ],
        }

    reviewed_frames_dict: dict[str, Any] = {}
    for frame_idx, record in sorted(state.reviewed_frames.items()):
        reviewed_frames_dict[str(frame_idx)] = {
            "disposition": record.disposition,
            "reviewed_at": record.reviewed_at,
            "request_id": str(record.request_id),
            "prediction": record.prediction.to_dict() if record.prediction is not None else None,
            "manual_point_id": str(record.manual_point_id) if record.manual_point_id is not None else None,
        }
    payload["reviewed_frames"] = reviewed_frames_dict
    return payload


def extract_review_state(run: TrackingRun) -> SuggestedFrameReviewState | None:
    """从 TrackingRun 中提取审核状态；若未记录或为旧项目返回 None。

    若内容损坏抛出 ValueError。
    """
    raw_val = run.extra_fields.get(SUGGESTED_FRAME_REVIEW_KEY)
    if raw_val is None:
        return None
    if not isinstance(raw_val, dict):
        raise ValueError(
            f"corrupted {SUGGESTED_FRAME_REVIEW_KEY} in run {run.run_id}: expected dict, got {type(raw_val).__name__}"
        )

    # 1. 解析 active_batch
    raw_batch = raw_val.get("active_batch")
    active_batch: ActiveReviewBatch | None = None
    if raw_batch is not None:
        if not isinstance(raw_batch, dict):
            raise ValueError("active_batch must be a dict or null")
        try:
            batch_req_id = UUID(raw_batch["request_id"])
            params_snapshot = dict(raw_batch.get("params_snapshot", {}))
            raw_candidates = raw_batch.get("candidates", [])
            candidates: list[ReviewCandidate] = []
            for cand in raw_candidates:
                candidates.append(
                    ReviewCandidate(
                        frame_index=int(cand["frame_index"]),
                        prediction=ReviewPredictionSnapshot.from_dict(cand.get("prediction")),
                        components={str(k): float(v) for k, v in cand.get("components", {}).items()},
                        raw_components={str(k): float(v) for k, v in cand.get("raw_components", {}).items()},
                        reasons=tuple(str(r) for r in cand.get("reasons", ())),
                        total_score=float(cand["total_score"]),
                    )
                )
            active_batch = ActiveReviewBatch(
                request_id=batch_req_id,
                params_snapshot=params_snapshot,
                candidates=tuple(candidates),
            )
        except (KeyError, ValueError, TypeError) as err:
            raise ValueError(f"malformed active_batch in run {run.run_id}: {err}") from err

    # 2. 解析 reviewed_frames
    raw_reviewed = raw_val.get("reviewed_frames", {})
    if not isinstance(raw_reviewed, dict):
        raise ValueError("reviewed_frames must be a dict")
    reviewed_frames: dict[int, ReviewRecord] = {}
    for key_str, record_dict in raw_reviewed.items():
        try:
            frame_idx = int(key_str)
            if not isinstance(record_dict, dict):
                raise ValueError(f"record for frame {key_str} must be a dict")
            disposition = str(record_dict["disposition"])
            reviewed_at = str(record_dict["reviewed_at"])
            req_id = UUID(record_dict["request_id"])
            prediction = ReviewPredictionSnapshot.from_dict(record_dict.get("prediction"))
            raw_point_id = record_dict.get("manual_point_id")
            manual_point_id = UUID(raw_point_id) if raw_point_id is not None else None
            reviewed_frames[frame_idx] = ReviewRecord(
                disposition=disposition,
                reviewed_at=reviewed_at,
                request_id=req_id,
                prediction=prediction,
                manual_point_id=manual_point_id,
            )
        except (KeyError, ValueError, TypeError) as err:
            raise ValueError(
                f"malformed review record for frame {key_str} in run {run.run_id}: {err}"
            ) from err

    return SuggestedFrameReviewState(
        active_batch=active_batch,
        reviewed_frames=reviewed_frames,
    )


def attach_review_state(
    run: TrackingRun, state: SuggestedFrameReviewState | None
) -> TrackingRun:
    """返回更新了审核状态的 TrackingRun 快照，保留同级其他 extra_fields。"""
    extras: JsonObject = dict(run.extra_fields)
    if state is None:
        extras.pop(SUGGESTED_FRAME_REVIEW_KEY, None)
    else:
        extras[SUGGESTED_FRAME_REVIEW_KEY] = serialize_review_state(state)
    return replace(run, extra_fields=extras)
