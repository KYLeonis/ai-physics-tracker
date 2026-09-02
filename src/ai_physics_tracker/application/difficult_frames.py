"""应用层困难帧挖掘策略：纯函数、Qt-free，不持有会话或引擎对象（Phase 5.2）。

输入为全帧原始预测（含低置信度与缺测，NaN 语义见 data-model.md §3.5）；
输出为带分量分数与触发原因的候选排名。pipeline 顺序固定为
candidate pool → normalization + weighted rank → temporal de-duplication →
(视觉多样性, 由 job 层复用 5.1 K-means) → Top N（spec R2.5）。
"""

from dataclasses import dataclass
from math import isfinite


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
        weights = (self.weight_uncertainty, self.weight_jump, self.weight_residual, self.weight_prior)
        if any(self._finite_number(w, "weight") < 0 for w in weights):
            raise ValueError("weights must be finite and non-negative")
        if sum(weights) <= 0:
            raise ValueError("at least one weight must be positive")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")

    @staticmethod
    def _finite_number(value: object, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be a finite number")
        number = float(value)
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
