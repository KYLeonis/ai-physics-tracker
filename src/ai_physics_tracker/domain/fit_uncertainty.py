"""领域层：局部Jacobian条件性参数标准误差及有版本摘要边界（ADR-0028）。"""

from dataclasses import dataclass
from typing import TYPE_CHECKING
import math
import json
from collections.abc import Mapping

import numpy as np

if TYPE_CHECKING:
    from ai_physics_tracker.domain.function_fit import FitParameter

CONDITION_RTOL = 1e-5
BOUNDARY_RTOL = 1e-7
METHOD = "local_jacobian_svd"
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
    name: str
    status: str
    standard_error: float | None
    reason: str


@dataclass(frozen=True)
class ParameterUncertainty:
    """SE只属于直接拟合参数；没有协方差 / 传播 / 置信区间承诺。"""

    version: int
    method: str
    sample_count: int
    free_parameter_count: int
    degrees_of_freedom: int
    parameters: tuple[ParameterError, ...]


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


def read_parameter_uncertainty(
    value: object, parameters: tuple["FitParameter", ...], sample_count: int, source_kind: str,
) -> tuple[ParameterError, ...]:
    """严格读取v1；旧 / 未来 / 损坏摘要由调用方只读披露，绝不猜测SE。"""
    if not isinstance(value, Mapping) or type(value.get("version")) is not int or value["version"] != 1:
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
        entries.append(ParameterError(parameter.name, status, error, reason))
    return tuple(entries)


def _finite_error(value: float) -> bool:
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False
