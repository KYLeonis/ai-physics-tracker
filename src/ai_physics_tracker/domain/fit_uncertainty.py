"""领域层：局部Jacobian条件性SE、95%局部t区间及摘要边界（ADR-0028/0029）。"""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
import math
import json
from collections.abc import Mapping

import numpy as np
from scipy.stats import t as student_t

if TYPE_CHECKING:
    from ai_physics_tracker.domain.function_fit import FitParameter

CONDITION_RTOL = 1e-5
BOUNDARY_RTOL = 1e-7
METHOD = "local_jacobian_svd"
CONFIDENCE_LEVEL = 0.95
INTERVAL_METHOD = "local_student_t"
SUPPORTED_SOURCE_KINDS = ("world_position", "angular_position")
REASONS = {
    "fixed": "Fixed / not estimated",
    "unsupported_source": "Unsupported source: smoothing / numerical derivatives can correlate residuals",
    "insufficient_dof": "Not estimable: more samples than free parameters are required",
    "rank_deficient": "Not estimable: rank-deficient local Jacobian",
    "ill_conditioned": "Not estimable: ill-conditioned local Jacobian",
    "boundary_limited": "Not estimable: a free parameter is at or near a bound",
    "nonfinite": "Not estimable: non-finite or unrepresentable numerical estimate",
}


@dataclass(frozen=True)
class ParameterError:
    """单个参数的SE及独立的区间可估计状态。"""

    name: str
    status: str
    standard_error: float | None
    reason: str
    confidence_interval: tuple[float, float] | None = None
    interval_reason: str = "Not recorded"


@dataclass(frozen=True)
class ParameterUncertainty:
    """直接拟合参数的条件性SE与可选局部区间；不含传播或系统误差。"""

    version: int
    method: str
    sample_count: int
    free_parameter_count: int
    degrees_of_freedom: int
    parameters: tuple[ParameterError, ...]
    confidence_level: float | None = None
    interval_method: str | None = None


def estimate_parameter_uncertainty(
    parameters: tuple["FitParameter", ...], jacobian: np.ndarray, residual: np.ndarray,
    parameter_scales: np.ndarray, boundary_limited: bool = False,
) -> ParameterUncertainty:
    """输入为求解器缩放坐标；SVD与对数恢复原参数尺度，不改变拟合结果。"""
    free = [parameter for parameter in parameters if not parameter.fixed]
    n, p = len(residual), len(free)
    errors = None
    status = "estimated"
    if p:
        try:
            jacobian = np.asarray(jacobian, dtype=float)
            scales = np.asarray(parameter_scales, dtype=float)
            if (jacobian.shape != (n, p) or scales.shape != (p,)
                    or not np.all(np.isfinite(jacobian)) or not np.all(np.isfinite(residual))
                    or not np.all(np.isfinite(scales)) or np.any(scales <= 0)):
                status = "nonfinite"
            elif n <= p:
                status = "insufficient_dof"
            elif boundary_limited:
                status = "boundary_limited"
            else:
                maxima = np.max(np.abs(jacobian), axis=0)
                if np.any(maxima == 0):
                    status = "rank_deficient"
                else:
                    normalized = jacobian / maxima
                    norms = np.linalg.norm(normalized, axis=0)
                    _, singular, vt = np.linalg.svd(normalized / norms, full_matrices=False)
                    ratio = singular[-1] / singular[0]
                    if ratio <= np.finfo(float).eps * max(n, p):
                        status = "rank_deficient"
                    elif ratio <= CONDITION_RTOL:
                        status = "ill_conditioned"
                    else:
                        # SSE/(n-p)与逆Jacobian的行范数相乘；不平方极端尺度。
                        peak = float(np.max(np.abs(residual)))
                        noise = math.sqrt(float(np.sum((residual / peak) ** 2)) / (n-p)) if peak else 0.0
                        inverse_norms = np.linalg.norm(vt.T / singular, axis=1)
                        errors = [math.exp(math.log(scale) + math.log(peak) + math.log(noise)
                                           + math.log(inverse) - math.log(maximum) - math.log(norm))
                                  if peak else 0.0
                                  for scale, inverse, maximum, norm in zip(scales, inverse_norms, maxima, norms)]
                        if any(not math.isfinite(value) or (peak and value == 0) for value in errors):
                            status = "nonfinite"
        except (ValueError, OverflowError, FloatingPointError, np.linalg.LinAlgError):
            status = "nonfinite"
    index = 0
    entries = []
    for parameter in parameters:
        current = "fixed" if parameter.fixed else status
        error = errors[index] if current == "estimated" else None
        entries.append(ParameterError(parameter.name, current, error, "" if current == "estimated" else REASONS[current]))
        if not parameter.fixed:
            index += 1
    return ParameterUncertainty(1, METHOD, n, p, n-p, tuple(entries))


def add_parameter_intervals(
    uncertainty: ParameterUncertainty, parameters: tuple["FitParameter", ...],
    parameter_values: Mapping[str, float],
) -> ParameterUncertainty:
    """只在本次正式计算中追加95%局部t区间；历史读取不调用此生成入口。"""
    entries = []
    for entry, parameter in zip(uncertainty.parameters, parameters):
        bounds, reason = (_parameter_interval(parameter_values[entry.name], entry.standard_error,
                                             uncertainty.degrees_of_freedom, parameter)
                          if entry.status == "estimated" else (None, entry.reason))
        entries.append(replace(entry, confidence_interval=bounds, interval_reason=reason))
    return replace(uncertainty, version=2, parameters=tuple(entries),
                   confidence_level=CONFIDENCE_LEVEL, interval_method=INTERVAL_METHOD)


def _parameter_interval(value: float, error: float, dof: int, parameter: "FitParameter") -> tuple[tuple[float, float] | None, str]:
    # ADR-0029：不裁剪到约束边界；区间失败不能删除已成功的SE。
    try:
        margin = float(student_t.ppf((1 + CONFIDENCE_LEVEL) / 2, dof)) * error
        lower, upper = value - margin, value + margin
        if not all(math.isfinite(number) for number in (margin, lower, upper)):
            return None, "Not estimable: confidence interval is outside the finite numerical range"
        if error > 0 and not lower < value < upper:
            return None, "Not estimable: confidence interval is below floating-point resolution"
        if ((parameter.lower is not None and lower <= parameter.lower)
                or (parameter.upper is not None and upper >= parameter.upper)):
            return None, "Not estimable: local confidence interval reaches a parameter bound"
        return (lower, upper), ""
    except (ValueError, OverflowError, FloatingPointError):
        return None, "Not estimable: confidence interval is outside the finite numerical range"


def read_parameter_uncertainty(
    value: object, parameters: tuple["FitParameter", ...], sample_count: int, source_kind: str,
    parameter_values: Mapping[str, float] | None = None,
) -> tuple[ParameterError, ...]:
    """严格读取v1 / v2；旧v1不补区间，未知 / 损坏摘要不显示统计数值。"""
    if not isinstance(value, Mapping) or type(value.get("version")) is not int or value["version"] not in (1, 2):
        raise ValueError("Unsupported parameter uncertainty version (read-only)")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Parameter uncertainty is not finite JSON (read-only)") from error
    if type(sample_count) is not int or sample_count < 0:
        raise ValueError("Unreadable parameter uncertainty sample count")
    p = sum(not parameter.fixed for parameter in parameters)
    expected = {"sample_count": sample_count, "free_parameter_count": p, "degrees_of_freedom": sample_count-p}
    if value.get("method") != METHOD or any(type(value.get(key)) is not int or value[key] != count for key, count in expected.items()):
        raise ValueError("Unreadable parameter uncertainty method / sample counts")
    if value["version"] == 2:
        level = value.get("confidence_level")
        if (type(level) not in (float, int) or not _finite_number(level)
                or not math.isclose(level, CONFIDENCE_LEVEL, rel_tol=0, abs_tol=1e-15)
                or value.get("interval_method") != INTERVAL_METHOD or not isinstance(parameter_values, Mapping)):
            raise ValueError("Unreadable confidence interval method / level / estimates")
    rows = value.get("parameters")
    if not isinstance(rows, (tuple, list)) or len(rows) != len(parameters):
        raise ValueError("Parameter uncertainty does not match the recorded parameters")
    entries = []
    for row, parameter in zip(rows, parameters):
        if not isinstance(row, Mapping):
            raise ValueError("Unreadable parameter uncertainty row")
        status, error, reason = row.get("status"), row.get("standard_error"), row.get("reason")
        if (row.get("name") != parameter.name or status not in ("estimated", *REASONS)
                or (status == "fixed") != parameter.fixed or not isinstance(reason, str)
                or (status != "estimated" and (error is not None or not reason.strip()))
                or (status == "estimated" and (sample_count <= p or type(error) not in (int, float)
                                               or not _finite_error(error)))):
            raise ValueError("Unreadable parameter uncertainty value / status")
        if not parameter.fixed and ((source_kind in SUPPORTED_SOURCE_KINDS and status == "unsupported_source")
                                    or (source_kind not in SUPPORTED_SOURCE_KINDS and status != "unsupported_source")):
            raise ValueError("Parameter uncertainty conflicts with recorded source processing (read-only)")
        entry = ParameterError(parameter.name, status, error, reason)
        if value["version"] == 2:
            estimate = parameter_values.get(parameter.name)
            if type(estimate) not in (float, int) or not _finite_number(estimate):
                raise ValueError("Unreadable recorded parameter estimate")
            expected, unavailable = (_parameter_interval(estimate, error, sample_count-p, parameter)
                                     if status == "estimated" else (None, reason))
            bounds, interval_reason = row.get("confidence_interval"), row.get("interval_reason")
            if not isinstance(interval_reason, str) or interval_reason != unavailable:
                raise ValueError("Confidence interval reason does not match the recorded estimate / constraints")
            if expected is None:
                if "confidence_interval" not in row or bounds is not None:
                    raise ValueError("Unavailable confidence interval must be null")
            else:
                if (not isinstance(bounds, (tuple, list)) or len(bounds) != 2
                        or any(type(number) not in (int, float) or not _finite_number(number) for number in bounds)
                        or bounds[0] > bounds[1]
                        or (error > 0 and not bounds[0] < estimate < bounds[1])):
                    raise ValueError("Unreadable confidence interval bounds")
                tolerance = 4 * max(math.ulp(estimate), *(math.ulp(number) for number in expected))
                if any(not math.isclose(number, target, rel_tol=0, abs_tol=tolerance)
                       for number, target in zip(bounds, expected)):
                    raise ValueError("Confidence interval does not match its estimate / SE / degrees of freedom")
            entry = replace(entry, confidence_interval=tuple(bounds) if bounds is not None else None,
                            interval_reason=interval_reason)
        entries.append(entry)
    return tuple(entries)


def _finite_error(value: float) -> bool:
    return _finite_number(value) and value >= 0


def _finite_number(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
