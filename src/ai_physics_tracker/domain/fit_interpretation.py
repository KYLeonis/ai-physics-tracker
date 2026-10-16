"""领域层：拟合解读——把拟合 RMSE 与同样本"常数均值"基线对比，产出面向 UI 的英文结论。

只做误差量级的数值对比，不声明求解器收敛、模型正确性或参数不确定度。
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

# 基线可分辨下限的相对系数（spec 口径）：baseline_rmse <= 64*eps*max|measured| 视为不可分辨。
# 64 是对中心化相消误差的余量；刻意不设绝对下限（如 1.0），1e-12 量级的微小信号同样有效。
_BASELINE_RESOLUTION_FACTOR = 64.0 * np.finfo(float).eps

# reason 为 UI 直接展示的英文一句话结论，按改善符号三分类；基线不可分辨时单独说明。
_UNRESOLVABLE_BASELINE_REASON = (
    "The measured signal has no variation resolvable above floating-point precision, "
    "so improvement over a constant prediction is undefined."
)
_BETTER_THAN_BASELINE_REASON = "Fit error is lower than predicting the constant sample mean."
_WORSE_THAN_BASELINE_REASON = "Fit error is higher than predicting the constant sample mean."
_EQUAL_TO_BASELINE_REASON = "Fit error matches predicting the constant sample mean."


@dataclass(frozen=True)
class FitInterpretation:
    """拟合误差相对"恒预测样本均值"基线的解读结果。

    rmse 与 baseline_rmse 恒为有限值；improvement_percent = 100*(1 - rmse/baseline_rmse)，
    负值表示拟合比常数基线更差。None 表示基线在数值上不可分辨（常数或近常数信号），
    语义是"无法量化"，不是零改善。reason 不包含模型正确性或不确定度声明。
    """

    rmse: float
    baseline_rmse: float
    improvement_percent: float | None
    reason: str


def _scaled_rmse(errors: np.ndarray) -> float:
    """缩放均方根：先按最大绝对值归一再平方，有限大输入不会在平方步骤溢出。"""
    scale = float(np.max(np.abs(errors)))
    if scale == 0.0:
        return 0.0
    return scale * math.sqrt(float(np.mean((errors / scale) ** 2)))


def interpret_fit(measured: npt.ArrayLike, predicted: npt.ArrayLike) -> FitInterpretation:
    """对比 predicted 与 measured 的 RMSE 及同样本"常数均值"基线，产出可展示的拟合解读。

    输入必须为等长、非空、有限的一维数值序列，否则抛 ValueError；
    计算溢出或得到非有限指标时同样拒绝，绝不产出 NaN/inf 结果。
    """
    measured_arr, predicted_arr = np.asarray(measured, dtype=float), np.asarray(predicted, dtype=float)
    if measured_arr.ndim != 1 or predicted_arr.ndim != 1 or measured_arr.shape != predicted_arr.shape:
        raise ValueError("Measured and predicted must be paired one-dimensional arrays")
    if not measured_arr.size:
        raise ValueError("Measured and predicted must be non-empty")
    if not (np.all(np.isfinite(measured_arr)) and np.all(np.isfinite(predicted_arr))):
        raise ValueError("Measured and predicted values must be finite")
    try:
        # 缩放后求平方均值，与 function_fit 的 RMSE 口径一致。
        with np.errstate(over="raise", invalid="raise"):
            rmse = _scaled_rmse(predicted_arr - measured_arr)
            baseline_rmse = _scaled_rmse(measured_arr - float(np.mean(measured_arr)))
    except FloatingPointError as exc:
        raise ValueError("Fit error or baseline computation overflows the finite real domain") from exc
    if not (math.isfinite(rmse) and math.isfinite(baseline_rmse)):
        raise ValueError("Fit metrics are outside the finite real domain")
    resolvable_limit = _BASELINE_RESOLUTION_FACTOR * float(np.max(np.abs(measured_arr)))
    if baseline_rmse <= resolvable_limit:
        return FitInterpretation(rmse, baseline_rmse, None, _UNRESOLVABLE_BASELINE_REASON)
    try:
        with np.errstate(over="raise", invalid="raise"):
            improvement = 100.0 * (1.0 - rmse / baseline_rmse)
    except FloatingPointError as exc:
        raise ValueError("Improvement computation overflows the finite real domain") from exc
    if not math.isfinite(improvement):
        raise ValueError("Improvement is outside the finite real domain")
    if improvement > 0.0:
        reason = _BETTER_THAN_BASELINE_REASON
    elif improvement < 0.0:
        reason = _WORSE_THAN_BASELINE_REASON
    else:
        reason = _EQUAL_TO_BASELINE_REASON
    return FitInterpretation(rmse, baseline_rmse, improvement, reason)
