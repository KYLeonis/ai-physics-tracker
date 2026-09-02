"""应用层困难帧挖掘策略：纯函数、Qt-free，不持有会话或引擎对象（Phase 5.2）。

输入为全帧原始预测（含低置信度与缺测，NaN 语义见 data-model.md §3.5）；
输出为带分量分数与触发原因的候选排名。pipeline 顺序固定为
candidate pool → normalization + weighted rank → temporal de-duplication →
(视觉多样性, 由 job 层复用 5.1 K-means) → Top N（spec R2.5）。

已有 active manual 标注的帧不进入候选池：它们已有 ground truth，
再审阅它们不产生新训练数据（与 R1 排除 manual 帧同语义）。
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

import numpy as np

from ai_physics_tracker.domain.kinematics import smooth_savgol
from ai_physics_tracker.infrastructure.dlc_predictions import RawPrediction

# MAD → 标准差的一致性常数 1/Φ⁻¹(0.75)，正态假设下 robust z-score 用
_MAD_TO_SIGMA = 1.4826

# 残差/距离低于该值（px）视为数值零：完美合成轨迹上 savgol 残差只有浮点噪声，
# 不归零会在 MAD=0 分支把噪声判成伪异常
_SIGNAL_FLOOR_PX = 1e-6

COMPONENT_UNCERTAINTY = "uncertainty"
COMPONENT_JUMP = "jump"
COMPONENT_RESIDUAL = "residual"
COMPONENT_PRIOR = "prior_correction"

REASON_MISSING = "missing"
REASON_LOW_CONFIDENCE = "low_confidence"
REASON_JUMP_OUTLIER = "jump_outlier"
REASON_RESIDUAL_OUTLIER = "residual_outlier"
REASON_PRIOR_NEIGHBORHOOD = "prior_correction_neighborhood"


@dataclass(frozen=True)
class MiningParams:
    """困难帧挖掘参数值对象；全部字段进入结果参数快照以保证可复现。

    分数语义：component 经候选池内 percentile rank 归一化后加权求和，
    是筛查排名，不是概率（spec R2.4 / 硬性不变式 5）。
    """

    top_n: int = 10
    confidence_threshold: float = 0.6
    # robust z-score 阈值；MAD 为零时仅把严格大于 median 的值视为异常（plan 默认）
    jump_z_threshold: float = 3.5
    residual_z_threshold: float = 3.5
    # residual 平滑复用 domain.kinematics.smooth_savgol，NaN 分段语义沿用 ADR-0008
    smooth_window_length: int = 7
    smooth_polyorder: int = 2
    # 时间去重最小间隔（秒）；候选不足 top_n 时逐级减半放宽至 1 帧
    min_gap_s: float = 0.25
    diversity_shortlist_factor: int = 4  # 视觉多样性 shortlist 上限 = factor * top_n
    prior_radius_frames: int = 2
    weight_uncertainty: float = 0.40
    weight_jump: float = 0.25
    weight_residual: float = 0.25
    weight_prior: float = 0.10
    seed: int = 0  # 仅供视觉多样性 K-means 使用；策略本身确定性无随机

    def __post_init__(self) -> None:
        if type(self.top_n) is not int or self.top_n <= 0:
            raise ValueError("top_n must be a positive integer")
        threshold = self._finite_number(self.confidence_threshold, "confidence_threshold")
        if not 0 <= threshold <= 1:
            raise ValueError("confidence_threshold must be finite and in [0, 1]")
        for label, value in (("jump_z_threshold", self.jump_z_threshold),
                             ("residual_z_threshold", self.residual_z_threshold)):
            if self._finite_number(value, label) < 0:
                raise ValueError(f"{label} must be finite and non-negative")
        if (type(self.smooth_window_length) is not int or self.smooth_window_length <= 0
                or self.smooth_window_length % 2 == 0):
            raise ValueError("smooth_window_length must be a positive odd integer")
        if type(self.smooth_polyorder) is not int or not 0 <= self.smooth_polyorder < self.smooth_window_length:
            raise ValueError("smooth_polyorder must be in [0, smooth_window_length)")
        if self._finite_number(self.min_gap_s, "min_gap_s") <= 0:
            raise ValueError("min_gap_s must be finite and positive")
        if type(self.diversity_shortlist_factor) is not int or self.diversity_shortlist_factor < 1:
            raise ValueError("diversity_shortlist_factor must be a positive integer")
        if type(self.prior_radius_frames) is not int or self.prior_radius_frames < 0:
            raise ValueError("prior_radius_frames must be a non-negative integer")
        weights = (("weight_uncertainty", self.weight_uncertainty),
                   ("weight_jump", self.weight_jump),
                   ("weight_residual", self.weight_residual),
                   ("weight_prior", self.weight_prior))
        for label, value in weights:
            if self._finite_number(value, label) < 0:
                raise ValueError(f"{label} must be finite and non-negative")
        if sum(value for _, value in weights) <= 0:
            raise ValueError("at least one weight must be positive")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")

    @staticmethod
    def _finite_number(value: object, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be a finite number")
        try:
            number = float(value)
        except OverflowError as error:  # 超大整数转 float 溢出，统一 ValueError 语义
            raise ValueError(f"{label} must be a finite number") from error
        if not isfinite(number):
            raise ValueError(f"{label} must be a finite number")
        return number

    def to_snapshot(self) -> dict[str, float | int]:
        """导出可序列化参数快照（写入结果文件与 TrackingRun.extra_fields）。"""
        return {
            "top_n": self.top_n,
            "confidence_threshold": self.confidence_threshold,
            "jump_z_threshold": self.jump_z_threshold,
            "residual_z_threshold": self.residual_z_threshold,
            "smooth_window_length": self.smooth_window_length,
            "smooth_polyorder": self.smooth_polyorder,
            "min_gap_s": self.min_gap_s,
            "diversity_shortlist_factor": self.diversity_shortlist_factor,
            "prior_radius_frames": self.prior_radius_frames,
            "weight_uncertainty": self.weight_uncertainty,
            "weight_jump": self.weight_jump,
            "weight_residual": self.weight_residual,
            "weight_prior": self.weight_prior,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class FrameCandidate:
    """单个困难帧候选：分量分数、原始信号值、触发原因与总分（AC-4）。

    components 为候选池内 percentile rank 归一化后的分量（[0, 1]），
    是筛查排名信号，不是概率；raw_components 保留物理可解释的原始值
    （uncertainty=1-confidence、jump/residual=robust z-score、prior=0/1）。
    """

    frame_index: int
    components: dict[str, float]
    raw_components: dict[str, float]
    reasons: tuple[str, ...]
    total_score: float

    def __post_init__(self) -> None:
        if type(self.frame_index) is not int or self.frame_index < 0:
            raise ValueError("frame_index must be a non-negative integer")
        for mapping in (self.components, self.raw_components):
            for label, value in mapping.items():
                if isinstance(value, bool) or not isinstance(value, float) or not isfinite(value):
                    raise ValueError(f"{label} must be a finite float")
        if (isinstance(self.total_score, bool) or not isinstance(self.total_score, float)
                or not isfinite(self.total_score)):
            raise ValueError("total_score must be a finite float")


@dataclass(frozen=True)
class MiningOutcome:
    """纯策略层挖掘结果：时间去重后的排名 shortlist 与诊断信息。

    shortlist 已按总分降序、满足最小帧间隔，长度 ≤ diversity_shortlist_factor
    × top_n；视觉多样性选择与 Top N 截断由 job 层完成（Slice 3）。
    """

    shortlist: tuple[FrameCandidate, ...]
    pool_size: int
    min_gap_frames: int
    actual_min_gap_frames: int | None
    gap_relaxed: bool
    params_snapshot: dict[str, Any] = field(default_factory=dict)


def mine_difficult_frames(
    predictions: Sequence[RawPrediction],
    *,
    zone_start: int,
    zone_end: int,
    fps_nominal: float,
    params: MiningParams,
    prior_correct_frames: frozenset[int] = frozenset(),
    manual_frames: frozenset[int] = frozenset(),
) -> MiningOutcome:
    """确定性挖掘管线（R2.3–R2.6）：池 → 归一化加权 → 时间去重 → shortlist。

    predictions 必须是覆盖 [0, len) 的连续全帧序列（read_raw_predictions 产物）；
    本函数无随机性，同输入/参数结果相同（AC-4）；NaN 只表示缺测。
    """
    for position, row in enumerate(predictions):
        if row.frame_index != position:
            raise ValueError("predictions must be a contiguous full-frame sequence from 0")
    if not 0 <= zone_start <= zone_end < len(predictions):
        raise ValueError(f"working zone [{zone_start}, {zone_end}] exceeds predictions")
    if not isfinite(fps_nominal) or fps_nominal <= 0:
        raise ValueError("fps_nominal must be finite and positive")

    zone = predictions[zone_start:zone_end + 1]
    frame_count = len(zone)

    def zone_frame(position: int) -> int:
        return zone_start + position

    raw, flags = _component_signals(zone, params, prior_correct_frames)

    pool_positions: list[int] = []
    reasons_by_position: list[tuple[str, ...]] = []
    for position in range(frame_count):
        frame = zone_frame(position)
        if frame in manual_frames:
            continue  # 已有 ground truth，不再建议
        reasons = _reasons_for(flags, position)
        if reasons:
            pool_positions.append(position)
            reasons_by_position.append(reasons)

    min_gap_frames = max(1, round(params.min_gap_s * fps_nominal))
    if not pool_positions:
        return MiningOutcome((), 0, min_gap_frames, None, False,
                             _snapshot(params, 0, min_gap_frames, None, False,
                                       zone_start, zone_end, fps_nominal))

    components = _normalized_components(raw, pool_positions)
    weights = {
        COMPONENT_UNCERTAINTY: params.weight_uncertainty,
        COMPONENT_JUMP: params.weight_jump,
        COMPONENT_RESIDUAL: params.weight_residual,
        COMPONENT_PRIOR: params.weight_prior,
    }
    totals = [
        sum(weights[name] * components[name][pool_index] for name in weights)
        for pool_index in range(len(pool_positions))
    ]

    ordered = sorted(range(len(pool_positions)),
                     key=lambda pool_index: (-totals[pool_index], pool_positions[pool_index]))
    gap, relaxed = min_gap_frames, False
    kept = _greedy_temporal_dedup(ordered, pool_positions, gap)
    while len(kept) < params.top_n and gap > 1:
        gap = max(1, gap // 2)
        relaxed = True
        kept = _greedy_temporal_dedup(ordered, pool_positions, gap)

    shortlist = tuple(
        FrameCandidate(
            frame_index=zone_frame(pool_positions[pool_index]),
            components={name: float(components[name][pool_index]) for name in weights},
            raw_components={name: float(raw[name][pool_positions[pool_index]]) for name in weights},
            reasons=reasons_by_position[pool_index],
            total_score=float(totals[pool_index]),
        )
        for pool_index in kept[: params.diversity_shortlist_factor * params.top_n]
    )

    actual_min_gap = _min_pairwise_gap([candidate.frame_index for candidate in shortlist])
    return MiningOutcome(
        shortlist=shortlist,
        pool_size=len(pool_positions),
        min_gap_frames=min_gap_frames,
        actual_min_gap_frames=actual_min_gap,
        gap_relaxed=relaxed,
        params_snapshot=_snapshot(params, len(pool_positions), min_gap_frames,
                                  actual_min_gap, relaxed, zone_start, zone_end, fps_nominal),
    )


def _component_signals(
    zone: Sequence[RawPrediction],
    params: MiningParams,
    prior_correct_frames: frozenset[int],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """计算 working zone 内四类原始信号与触发标志；NaN 只出现在缺测帧。"""
    frame_count = len(zone)
    x = np.array([row.pixel_x for row in zone], dtype=np.float64)
    y = np.array([row.pixel_y for row in zone], dtype=np.float64)
    confidence = np.array([row.confidence for row in zone], dtype=np.float64)
    valid = np.isfinite(x) & np.isfinite(y)

    # uncertainty：缺测或来源未给 confidence 记 1.0，否则 1 - confidence
    uncertainty = np.where(np.isfinite(confidence), 1.0 - confidence, 1.0)
    uncertainty[~valid] = 1.0

    jump_raw, jump_flag = _jump_signals(x, y, valid, params.jump_z_threshold)
    residual_raw, residual_flag = _residual_signals(
        x, y, valid, params.smooth_window_length, params.smooth_polyorder,
        params.residual_z_threshold,
    )

    zone_offset = zone[0].frame_index if zone else 0
    radius = params.prior_radius_frames
    prior_raw = np.zeros(frame_count)
    for corrected in prior_correct_frames:
        low = max(0, corrected - radius - zone_offset)
        high = min(frame_count - 1, corrected + radius - zone_offset)
        if low <= high:
            prior_raw[low:high + 1] = 1.0
    prior_flag = prior_raw > 0.0

    raw = {COMPONENT_UNCERTAINTY: uncertainty, COMPONENT_JUMP: jump_raw,
           COMPONENT_RESIDUAL: residual_raw, COMPONENT_PRIOR: prior_raw}
    flags = {REASON_MISSING: ~valid,
             REASON_LOW_CONFIDENCE: valid & (~np.isfinite(confidence)
                                             | (confidence < params.confidence_threshold)),
             REASON_JUMP_OUTLIER: jump_flag,
             REASON_RESIDUAL_OUTLIER: residual_flag,
             REASON_PRIOR_NEIGHBORHOOD: prior_flag}
    return raw, flags


def _robust_scores(values: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """对一维非负值计算 robust z-score 与异常标志。

    低于 _SIGNAL_FLOOR_PX 的值先归零；MAD 为零时 z-score 无定义，
    按 plan 默认只把严格大于 median 的值判为异常，分数退化为
    1.0/0.0 二值以保持排名可分。
    """
    values = np.where(values <= _SIGNAL_FLOOR_PX, 0.0, values)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scores = np.zeros(len(values))
    anomalies = np.zeros(len(values), dtype=bool)
    if mad > 0.0:
        z = (values - median) / (_MAD_TO_SIGMA * mad)
        scores = np.maximum(z, 0.0)
        anomalies = z >= threshold
    else:
        anomalies = values > median
        scores = np.where(anomalies, 1.0, 0.0)
    return scores, anomalies


def _jump_signals(
    x: np.ndarray, y: np.ndarray, valid: np.ndarray, threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """相邻有效帧像素距离的 robust z-score；帧取其两侧 link 的最大值。"""
    frame_count = len(x)
    dist_to_prev = np.full(frame_count, np.nan)
    if frame_count > 1:
        both = valid[1:] & valid[:-1]
        distances = np.hypot(x[1:] - x[:-1], y[1:] - y[:-1])
        dist_to_prev[1:][both] = distances[both]
    # link_at[i] = 帧 i 与 i-1 之间 link 在压缩数组中的下标（-1 = 无 link）
    link_at = np.full(frame_count, -1, dtype=int)
    link_values: list[float] = []
    for position in range(1, frame_count):
        if np.isfinite(dist_to_prev[position]):
            link_at[position] = len(link_values)
            link_values.append(float(dist_to_prev[position]))
    raw = np.zeros(frame_count)
    flags = np.zeros(frame_count, dtype=bool)
    if not link_values:
        return raw, flags
    link_scores, link_anomalies = _robust_scores(np.array(link_values), threshold)
    for position in range(frame_count):
        member_links = [link_at[position]]
        if position + 1 < frame_count:
            member_links.append(link_at[position + 1])
        member_links = [index for index in member_links if index >= 0]
        if member_links:
            raw[position] = max(link_scores[index] for index in member_links)
            flags[position] = any(link_anomalies[index] for index in member_links)
    return raw, flags


def _residual_signals(
    x: np.ndarray, y: np.ndarray, valid: np.ndarray,
    window_length: int, polyorder: int, threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """raw 相对 Savitzky-Golay 平滑轨迹的残差 robust z-score（ADR-0008 分段语义）。"""
    smoothed_x = smooth_savgol(x, window_length=window_length, polyorder=polyorder)
    smoothed_y = smooth_savgol(y, window_length=window_length, polyorder=polyorder)
    residual_px = np.hypot(x - smoothed_x, y - smoothed_y)  # NaN 段保持 NaN
    finite = np.isfinite(residual_px)
    raw = np.zeros(len(x))
    flags = np.zeros(len(x), dtype=bool)
    if not finite.any():
        return raw, flags
    scores, anomalies = _robust_scores(residual_px[finite], threshold)
    raw[finite] = scores
    flags[finite] = anomalies
    return raw, flags


def _reasons_for(flags: dict[str, np.ndarray], position: int) -> tuple[str, ...]:
    return tuple(name for name, mask in flags.items() if bool(mask[position]))


def _normalized_components(
    raw: dict[str, np.ndarray], pool_positions: list[int],
) -> dict[str, np.ndarray]:
    """候选池内 percentile rank 归一化（确定性，并列取平均名次）。

    池大小为 1 时归一化为 0.0；全并列时为 0.5——分数只用于池内排名，
    不跨池比较，也不解释为概率（R2.4）。
    """
    normalized: dict[str, np.ndarray] = {}
    for name, values in raw.items():
        normalized[name] = _percentile_ranks(values[pool_positions])
    return normalized


def _percentile_ranks(values: np.ndarray) -> np.ndarray:
    count = len(values)
    if count <= 1:
        return np.zeros(count)
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    ranks = np.empty(count, dtype=np.float64)
    start = 0
    while start < count:
        end = start
        while end + 1 < count and sorted_values[end + 1] == sorted_values[start]:
            end += 1
        ranks[start:end + 1] = (start + end) / 2 + 1  # 1-based 平均名次
        start = end + 1
    result = np.empty(count, dtype=np.float64)
    result[order] = ranks
    return (result - 1) / (count - 1)


def _greedy_temporal_dedup(
    ordered_pool_indices: list[int], pool_positions: list[int], gap: int,
) -> list[int]:
    """按分数顺序贪心选择，与已选帧间隔 >= gap 才保留（连续段不垄断）。"""
    kept: list[int] = []
    kept_frames: list[int] = []
    for pool_index in ordered_pool_indices:
        frame = pool_positions[pool_index]
        if all(abs(frame - kept_frame) >= gap for kept_frame in kept_frames):
            kept.append(pool_index)
            kept_frames.append(frame)
    return kept


def _min_pairwise_gap(frames: list[int]) -> int | None:
    if len(frames) < 2:
        return None
    ordered = sorted(frames)
    return min(b - a for a, b in zip(ordered, ordered[1:]))


def _snapshot(
    params: MiningParams, pool_size: int, min_gap_frames: int,
    actual_min_gap_frames: int | None, gap_relaxed: bool,
    zone_start: int, zone_end: int, fps_nominal: float,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = dict(params.to_snapshot())
    snapshot.update({
        "pool_size": pool_size,
        "min_gap_frames": min_gap_frames,
        "actual_min_gap_frames": actual_min_gap_frames,
        "gap_relaxed": gap_relaxed,
        "zone_start": zone_start,
        "zone_end": zone_end,
        "fps_nominal": fps_nominal,
    })
    return snapshot
