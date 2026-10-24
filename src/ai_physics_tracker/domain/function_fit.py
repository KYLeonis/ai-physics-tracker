"""领域层：单初值、等权、有界的显式函数最小二乘拟合。"""

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import least_squares

from ai_physics_tracker.domain.expression import ExpressionError, parse_expression
from ai_physics_tracker.domain.fit_uncertainty import (
    BOUNDARY_RTOL, ParameterUncertainty, estimate_parameter_uncertainty, add_parameter_intervals,
)

MAX_FIT_EVALUATIONS = 10000
IDENTIFIABILITY_RTOL = 1e-7


@dataclass(frozen=True)
class FitParameter:
    """用户声明的初值和边界；None表示无相应边界。"""

    name: str
    initial: float = 1.0
    lower: float | None = None
    upper: float | None = None
    fixed: bool = False

    def __post_init__(self) -> None:
        if not self.name or not math.isfinite(self.initial):
            raise ValueError("Parameter name and finite initial value are required")
        if any(value is not None and not math.isfinite(value) for value in (self.lower, self.upper)):
            raise ValueError("Parameter bounds must be finite or omitted")
        if self.lower is not None and self.initial < self.lower:
            raise ValueError(f"Initial {self.name} is below its lower bound")
        if self.upper is not None and self.initial > self.upper:
            raise ValueError(f"Initial {self.name} is above its upper bound")
        if self.lower is not None and self.upper is not None and self.lower >= self.upper:
            raise ValueError("Bounds must be strictly ordered; use Fixed for a constant parameter")


@dataclass(frozen=True)
class FitSpec:
    """完整求解规格；单次所有模型调用都计入评估预算。"""

    expression: str
    parameters: tuple[FitParameter, ...]
    max_evaluations: int = 1000

    def __post_init__(self) -> None:
        expression = parse_expression(self.expression)
        names = [parameter.name for parameter in self.parameters]
        if len(set(names)) != len(names) or set(names) != set(expression.parameter_names):
            raise ValueError("Parameters must match the expression exactly")
        if type(self.max_evaluations) is not int or not 1 <= self.max_evaluations <= MAX_FIT_EVALUATIONS:
            raise ValueError(f"Evaluation budget must be in [1, {MAX_FIT_EVALUATIONS}]")


@dataclass(frozen=True)
class FitOutcome:
    """失败状态不含可发布预测；全固定计算与拟合成功分别标识。"""

    status: str
    message: str
    parameter_values: tuple[tuple[str, float], ...] = ()
    prediction: tuple[float, ...] = ()
    residual: tuple[float, ...] = ()
    rmse: float | None = None
    evaluations: int = 0
    solver_status: int | None = None
    residual_scale: float = 1.0
    parameter_scales: tuple[tuple[str, float], ...] = ()
    parameter_uncertainty: ParameterUncertainty | None = None

    @property
    def is_publishable(self) -> bool:
        return self.status in ("success", "given_parameters")


class _FitStopped(Exception):
    def __init__(self, status: str, message: str) -> None:
        self.status, self.message = status, message


def fit_function(
    time_s: np.ndarray, measured: np.ndarray, spec: FitSpec,
    is_cancelled: Callable[[], bool] = lambda: False,
) -> FitOutcome:
    """拟合真实有效样本；时间由调用方从源帧映射，不按行重新编号。"""
    time, values = np.asarray(time_s, dtype=float), np.asarray(measured, dtype=float)
    if (time.ndim != 1 or values.shape != time.shape or not len(time)
            or not np.all(np.isfinite(time)) or not np.all(np.isfinite(values))
            or np.any(np.diff(time) <= 0)):
        raise ValueError("Fit samples must be finite, paired and strictly increasing in time")
    expression = parse_expression(spec.expression)
    free = tuple(parameter for parameter in spec.parameters if not parameter.fixed)
    if free and len(time) <= len(free):
        return FitOutcome("insufficient_samples", "More samples than free parameters are required")
    fixed = {parameter.name: parameter.initial for parameter in spec.parameters if parameter.fixed}
    # 在无量纲参数坐标求解，避免巨大初值触发xtol假收敛或微小参数差分下溢。
    parameter_scales = np.array([abs(parameter.initial) or 1.0 for parameter in free])
    evaluations = 0
    # 同一常数缩放保留等权最小二乘目标，避免小单位信号过早满足绝对gtol。
    residual_scale = float(np.max(np.abs(values))) or 1.0

    def parameter_values(vector: np.ndarray) -> dict[str, float]:
        return fixed | {parameter.name: float(value) for parameter, value in zip(free, vector * parameter_scales)}

    def model(parameters: dict[str, float]) -> np.ndarray:
        nonlocal evaluations
        if is_cancelled():
            raise _FitStopped("cancelled", "Fit was cancelled")
        if evaluations >= spec.max_evaluations:
            raise _FitStopped("evaluation_limit", "Model evaluation budget was reached")
        evaluations += 1
        return expression.evaluate(time, parameters)

    def residual(vector: np.ndarray) -> np.ndarray:
        predicted = model(parameter_values(vector))
        with np.errstate(over="raise", invalid="raise"):
            return (predicted - values) / residual_scale

    try:
        if any(parameter.initial == 0 for parameter in free):
            # 零初值没有自身尺度：在用户边界内用一次有限探针估算响应尺度。
            # 探针只作坐标预处理，不改变可见初值/边界；同样消耗模型评估预算。
            base_parameters = fixed | {parameter.name: parameter.initial for parameter in free}
            base = model(base_parameters)
            for index, parameter in enumerate(free):
                if parameter.initial != 0:
                    continue
                probe = min(1.0, parameter.upper) if parameter.upper is not None else 1.0
                if probe <= 0:
                    probe = max(-1.0, parameter.lower) if parameter.lower is not None else -1.0
                try:
                    probed = model(base_parameters | {parameter.name: probe})
                    with np.errstate(over="raise", invalid="raise"):
                        response = float(np.max(np.abs(probed-base)))
                    if response > 0:
                        scale = math.exp(math.log(abs(probe))+math.log(residual_scale)-math.log(response))
                        if not math.isfinite(scale) or scale <= 0:
                            raise _FitStopped("unidentifiable", "Parameter scale is outside the finite numerical range")
                        parameter_scales[index] = scale
                except (ExpressionError, FloatingPointError, OverflowError):
                    # 合法初值的探针可越出公式定义域；不因此修改初值或拒绝原模型。
                    parameter_scales[index] = 1.0
        initial = np.array([parameter.initial for parameter in free], dtype=float) / parameter_scales
        if not free:
            errors = residual(initial)
            solution, status, message = initial, None, "Computed with given fixed parameters"
        else:
            lower = [parameter.lower if parameter.lower is not None else -np.inf for parameter in free]
            upper = [parameter.upper if parameter.upper is not None else np.inf for parameter in free]
            with np.errstate(over="ignore"):
                lower = np.asarray(lower) / parameter_scales
                upper = np.asarray(upper) / parameter_scales
            result = least_squares(residual, initial, bounds=(lower, upper), max_nfev=spec.max_evaluations,
                                   x_scale="jac", ftol=1e-10, xtol=1e-10, gtol=1e-10)
            if not result.success:
                return FitOutcome("not_converged", result.message, evaluations=evaluations,
                                  solver_status=int(result.status))
            # 列归一化避免仅因参数单位不同误判；此处只检查拟合可辨识性，统计另行估计。
            maxima = np.max(np.abs(result.jac), axis=0)
            if np.any(maxima == 0) or not np.all(np.isfinite(maxima)):
                return FitOutcome("unidentifiable", "Model is insensitive to a free parameter",
                                  evaluations=evaluations)
            normalized = result.jac / maxima
            norms = np.linalg.norm(normalized, axis=0)
            singular = np.linalg.svd(normalized / norms, compute_uv=False)
            if singular[-1] <= IDENTIFIABILITY_RTOL * singular[0]:
                return FitOutcome("unidentifiable", "Free parameters have a rank-deficient local Jacobian",
                                  evaluations=evaluations)
            solution, errors = result.x, result.fun
            status, message = int(result.status), str(result.message)
        if is_cancelled():
            return FitOutcome("cancelled", "Fit was cancelled", evaluations=evaluations)
        errors = errors * residual_scale
        # 缩放后求平方均值，避免有限大残差在平方步骤溢出。
        scale = float(np.max(np.abs(errors)))
        rmse = scale * math.sqrt(float(np.mean((errors / scale) ** 2))) if scale else 0.0
        predicted = values + errors
        if not math.isfinite(rmse) or not np.all(np.isfinite(predicted)):
            raise ExpressionError("Fit summary is outside the finite real domain")
        boundary_limited = bool(free) and (np.any(result.active_mask != 0) or np.any(
            np.minimum(solution-lower, upper-solution) <= BOUNDARY_RTOL * np.maximum(1, np.abs(solution))))
        uncertainty = estimate_parameter_uncertainty(
            spec.parameters, result.jac if free else np.empty((len(time), 0)),
            result.fun if free else errors / residual_scale, parameter_scales, boundary_limited)
        ordered = parameter_values(solution)
        uncertainty = add_parameter_intervals(uncertainty, spec.parameters, ordered)
        return FitOutcome("success" if free else "given_parameters", message,
                          tuple((parameter.name, ordered[parameter.name]) for parameter in spec.parameters),
                          tuple(map(float, predicted)), tuple(map(float, -errors)), rmse, evaluations, status, residual_scale,
                          tuple((parameter.name, float(scale)) for parameter, scale in zip(free, parameter_scales)), uncertainty)
    except _FitStopped as exc:
        return FitOutcome(exc.status, exc.message, evaluations=evaluations)
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
        return FitOutcome("domain_error", str(exc), evaluations=evaluations)
