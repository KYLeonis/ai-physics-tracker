"""领域层：单摆 raw 参数等价族与条件 objective valley；无 Qt/IO。"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from math import isclose, isfinite, log10, sin
from typing import Callable, Literal

import numpy as np
from scipy.integrate import solve_ivp

from ai_physics_tracker.domain.pendulum_ode import (
    M1,
    ForwardResult,
    InitialCondition,
    IntegrationSettings,
    ObjectiveRequest,
    PendulumParameters,
    evaluate_objective,
    fit_sample_indices,
    objective_request_digest,
    simulate_pendulum,
)

FROZEN_CURVE_COUNT = 222
FROZEN_SURFACE_ALPHA_A = (0.0, 0.12)
FROZEN_SURFACE_ALPHA_A_COUNT = 101
FROZEN_SURFACE_OMEGA2_FACTORS = (0.94, 1.16)
FROZEN_SURFACE_OMEGA2_COUNT = 91


def _finite_number(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value)


@dataclass(frozen=True)
class RawParameters:
    """raw 模型参数：惯性增量与阻尼、频率平方；总惯性须为正。"""

    alpha_a: float
    alpha1_s_inv: float
    alpha2_rad_inv: float
    omega0_sq_s_inv2: float

    def __post_init__(self) -> None:
        for name in ("alpha_a", "alpha1_s_inv", "alpha2_rad_inv", "omega0_sq_s_inv2"):
            value = getattr(self, name)
            if not _finite_number(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, float(value))
        if 1 + self.alpha_a <= 0:
            raise ValueError("raw total inertia 1 + alpha_a must be positive")
        if self.alpha1_s_inv < 0 or self.alpha2_rad_inv < 0 or self.omega0_sq_s_inv2 <= 0:
            raise ValueError("raw damping must be non-negative and omega0 squared must be positive")


@dataclass(frozen=True)
class RawParameterBounds:
    """四个 raw 参数的闭区间约束；所有界都必须显式提供。"""

    alpha_a: tuple[float, float]
    alpha1_s_inv: tuple[float, float]
    alpha2_rad_inv: tuple[float, float]
    omega0_sq_s_inv2: tuple[float, float]

    def __post_init__(self) -> None:
        for name in ("alpha_a", "alpha1_s_inv", "alpha2_rad_inv", "omega0_sq_s_inv2"):
            bounds = getattr(self, name)
            if (not isinstance(bounds, tuple) or len(bounds) != 2
                    or any(not _finite_number(value) for value in bounds)
                    or bounds[0] > bounds[1]):
                raise ValueError(f"{name} bounds must be a finite ordered pair")
            object.__setattr__(self, name, tuple(map(float, bounds)))
        if (self.alpha1_s_inv[0] < 0 or self.alpha2_rad_inv[0] < 0
                or self.omega0_sq_s_inv2[0] < 0):
            raise ValueError("raw damping and frequency bounds cannot be negative")


@dataclass(frozen=True)
class LambdaRange:
    """等价缩放的可行区间；只有总惯性约束不提供正下界时，下界才开。"""

    min_lambda: float
    max_lambda: float
    min_inclusive: bool

    def __post_init__(self) -> None:
        if (not _finite_number(self.min_lambda) or not _finite_number(self.max_lambda)
                or self.min_lambda < 0 or self.max_lambda <= 0
                or self.min_lambda > self.max_lambda
                or (self.min_lambda == self.max_lambda and not self.min_inclusive)):
            raise ValueError("lambda range must be nonempty and finite")

    def contains(self, value: float) -> bool:
        if not _finite_number(value):
            return False
        lower_ok = value >= self.min_lambda if self.min_inclusive else value > self.min_lambda
        return lower_ok and value <= self.max_lambda


def lump_parameters(parameters: RawParameters) -> PendulumParameters:
    """映射 raw 参数到三项可辨识的集总参数。"""
    if not isinstance(parameters, RawParameters):
        raise ValueError("lumping requires validated raw parameters")
    scale = 1 + parameters.alpha_a
    return PendulumParameters(parameters.alpha1_s_inv / scale,
                              parameters.omega0_sq_s_inv2 / scale,
                              parameters.alpha2_rad_inv / scale)


def feasible_lambda_range(parameters: RawParameters, bounds: RawParameterBounds) -> LambdaRange:
    """对全部 raw bounds 求缩放交集，不逐项 clip 参数。"""
    if not isinstance(parameters, RawParameters) or not isinstance(bounds, RawParameterBounds):
        raise ValueError("lambda range requires raw parameters and declared bounds")
    scale = 1 + parameters.alpha_a
    lows = [(bounds.alpha_a[0] + 1) / scale]
    highs = [(bounds.alpha_a[1] + 1) / scale]
    for value, (low, high) in (
        (parameters.alpha1_s_inv, bounds.alpha1_s_inv),
        (parameters.alpha2_rad_inv, bounds.alpha2_rad_inv),
        (parameters.omega0_sq_s_inv2, bounds.omega0_sq_s_inv2),
    ):
        if value == 0:
            if not low <= 0 <= high:
                raise ValueError("raw bounds have no feasible equivalent scale")
            continue
        lows.append(low / value)
        highs.append(high / value)
    raw_min = max(lows)
    min_lambda = max(0.0, raw_min)
    max_lambda = min(highs)
    min_inclusive = raw_min > 0
    if (not isfinite(min_lambda) or not isfinite(max_lambda) or max_lambda <= 0
            or min_lambda > max_lambda or (min_lambda == max_lambda and not min_inclusive)):
        raise ValueError("raw parameter bounds have no representable feasible lambda")
    return LambdaRange(float(min_lambda), float(max_lambda), min_inclusive)


def transform_raw_parameters(
    parameters: RawParameters, lambda_scale: float, bounds: RawParameterBounds | None = None,
) -> RawParameters:
    """沿等价族变换 raw 参数；提供 bounds 时越界直接拒绝。"""
    if not isinstance(parameters, RawParameters) or not _finite_number(lambda_scale) or lambda_scale <= 0:
        raise ValueError("equivalent transform requires raw parameters and positive finite lambda")
    lambda_scale = float(lambda_scale)
    if bounds is not None and not feasible_lambda_range(parameters, bounds).contains(lambda_scale):
        raise ValueError("lambda lies outside the complete raw-parameter feasible range")
    scale = 1 + parameters.alpha_a
    transformed = RawParameters(lambda_scale * scale - 1,
                                lambda_scale * parameters.alpha1_s_inv,
                                lambda_scale * parameters.alpha2_rad_inv,
                                lambda_scale * parameters.omega0_sq_s_inv2)
    if bounds is not None:
        for name in ("alpha_a", "alpha1_s_inv", "alpha2_rad_inv", "omega0_sq_s_inv2"):
            value = getattr(transformed, name)
            low, high = getattr(bounds, name)
            if ((value < low and not isclose(value, low, rel_tol=1e-12, abs_tol=1e-12))
                    or (value > high and not isclose(value, high, rel_tol=1e-12, abs_tol=1e-12))):
                raise ValueError(f"transformed {name} lies outside its declared raw bounds")
    return transformed


def illustrative_raw_reference(
    parameters: PendulumParameters, alpha_a: float = 0.0,
) -> RawParameters:
    """从拟合的 starred 值构造教学用 raw 参考；alpha_a 是任意示例值。"""
    if not isinstance(parameters, PendulumParameters) or not _finite_number(alpha_a) or 1 + alpha_a <= 0:
        raise ValueError("illustrative raw reference requires valid lumped parameters and alpha_a > -1")
    scale = 1 + float(alpha_a)
    return RawParameters(float(alpha_a), scale * parameters.alpha1_s_inv,
                         scale * parameters.alpha2_rad_inv,
                         scale * parameters.omega2_s_inv2)


@dataclass(frozen=True)
class IdentifiabilityState:
    """不可变教学状态；reference 永远标作 illustrative，不是测得 raw 参数。"""

    reference_raw: RawParameters
    lambda_scale: float
    bounds: RawParameterBounds | None = None
    illustrative: Literal[True] = field(default=True, init=False)
    _transformed_raw: RawParameters = field(init=False, repr=False)

    def __post_init__(self) -> None:
        transformed = transform_raw_parameters(self.reference_raw, self.lambda_scale, self.bounds)
        object.__setattr__(self, "lambda_scale", float(self.lambda_scale))
        object.__setattr__(self, "_transformed_raw", transformed)

    @property
    def transformed_raw(self) -> RawParameters:
        return self._transformed_raw

    @property
    def reference_lumped(self) -> PendulumParameters:
        return lump_parameters(self.reference_raw)

    @property
    def transformed_lumped(self) -> PendulumParameters:
        return lump_parameters(self.transformed_raw)


def raw_pendulum_rhs(state: tuple[float, float], parameters: RawParameters) -> tuple[float, float]:
    """raw ODE 独立右端项；与集总 RHS 分别计算，不复用其预测数组。"""
    if (not isinstance(parameters, RawParameters) or not isinstance(state, (tuple, list, np.ndarray))
            or len(state) != 2
            or any(not _finite_number(value) for value in state)):
        raise ValueError("raw RHS requires a two-value state and validated raw parameters")
    theta, omega = state
    acceleration = -(parameters.omega0_sq_s_inv2 * sin(theta)
                     + parameters.alpha1_s_inv * omega
                     + parameters.alpha2_rad_inv * omega * abs(omega)) / (1 + parameters.alpha_a)
    return omega, acceleration


def simulate_raw_pendulum(
    parameters: RawParameters,
    initial_condition: InitialCondition,
    time_s: tuple[float, ...],
    settings: IntegrationSettings = IntegrationSettings(),
    *,
    check_cancel: Callable[[], None] | None = None,
) -> ForwardResult:
    """独立用 raw RHS 与指定积分容差求解实际请求时刻。"""
    if (not isinstance(parameters, RawParameters) or not isinstance(initial_condition, InitialCondition)
            or not isinstance(settings, IntegrationSettings)):
        raise ValueError("raw forward requires validated parameters, IC and integration settings")
    if (not isinstance(time_s, tuple) or any(not _finite_number(t) or t < 0 for t in time_s)
            or any(b <= a for a, b in zip(time_s, time_s[1:]))):
        raise ValueError("forward times must be ordered non-negative finite seconds")
    if not time_s:
        return ForwardResult("empty", None, (), (), 0)
    if check_cancel is not None:
        check_cancel()
    if time_s[-1] <= 0:
        return ForwardResult("success", None, (initial_condition.theta0_rad,),
                             (initial_condition.omega0_rad_s,), 0)
    if settings.first_step_s is not None and settings.first_step_s > time_s[-1]:
        raise ValueError("first_step exceeds integration span")

    cancellation_error: Exception | None = None

    def rhs(_time: float, state: np.ndarray) -> tuple[float, float]:
        nonlocal cancellation_error
        if check_cancel is not None:
            try:
                check_cancel()
            except Exception as exc:
                cancellation_error = exc
                raise
        return raw_pendulum_rhs((float(state[0]), float(state[1])), parameters)

    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            solution = solve_ivp(
                rhs, (0.0, time_s[-1]),
                (initial_condition.theta0_rad, initial_condition.omega0_rad_s),
                method="DOP853", t_eval=np.asarray(time_s, dtype=float), rtol=settings.rtol,
                atol=settings.atol, max_step=np.inf if settings.max_step_s is None else settings.max_step_s,
                first_step=settings.first_step_s, vectorized=False, dense_output=False, events=None,
            )
    except (FloatingPointError, OverflowError, ValueError, RuntimeError) as exc:
        if cancellation_error is not None:
            raise cancellation_error
        return ForwardResult("failed", f"integration_failed: {exc}", (), (), 0)
    if check_cancel is not None:
        check_cancel()
    if not solution.success or np.shape(solution.y) != (2, len(time_s)):
        return ForwardResult("failed", f"integration_failed: {solution.message}", (), (), int(solution.nfev))
    if not np.all(np.isfinite(solution.y)):
        return ForwardResult("failed", "nonfinite_prediction", (), (), int(solution.nfev))
    return ForwardResult("success", None, tuple(map(float, solution.y[0])),
                         tuple(map(float, solution.y[1])), int(solution.nfev))


@dataclass(frozen=True)
class ForwardEquivalence:
    """raw reference、变换 raw 与 starred RHS 的独立轨迹及差值。"""

    time_s: tuple[float, ...]
    raw_reference: ForwardResult
    raw_transformed: ForwardResult
    lumped_reference: ForwardResult
    raw_overlap_max_abs_difference_rad: float | None
    raw_lumped_max_abs_difference_rad: float | None
    tolerance_rad: float
    status: str
    reason: str | None

    @property
    def within_tolerance(self) -> bool | None:
        if (self.status != "success" or self.raw_overlap_max_abs_difference_rad is None
                or self.raw_lumped_max_abs_difference_rad is None):
            return None
        return (self.raw_overlap_max_abs_difference_rad <= self.tolerance_rad
                and self.raw_lumped_max_abs_difference_rad <= self.tolerance_rad)


def compare_equivalent_forwards(
    parameters: RawParameters,
    lambda_scale: float,
    initial_condition: InitialCondition,
    time_s: tuple[float, ...],
    settings: IntegrationSettings = IntegrationSettings(),
    *,
    tolerance_rad: float = 1e-7,
    bounds: RawParameterBounds | None = None,
    check_cancel: Callable[[], None] | None = None,
) -> ForwardEquivalence:
    """独立积分 raw A、raw B 与集总 RHS，并比较同一 IC 和实际时刻。"""
    if not _finite_number(tolerance_rad) or tolerance_rad <= 0:
        raise ValueError("trajectory tolerance must be positive and finite")
    transformed = transform_raw_parameters(parameters, lambda_scale, bounds)
    raw_reference = simulate_raw_pendulum(parameters, initial_condition, time_s, settings,
                                          check_cancel=check_cancel)
    raw_transformed = simulate_raw_pendulum(transformed, initial_condition, time_s, settings,
                                           check_cancel=check_cancel)
    if check_cancel is not None:
        check_cancel()
    lumped = lump_parameters(parameters)
    lumped_result = simulate_pendulum(M1, lumped, initial_condition, time_s, settings)
    results = (raw_reference, raw_transformed, lumped_result)
    failed = next((result for result in results if result.status not in ("success", "empty")), None)
    if failed is not None or any(result.status == "empty" for result in results):
        reason = failed.reason if failed is not None else "empty_time_grid"
        return ForwardEquivalence(time_s, raw_reference, raw_transformed, lumped_result,
                                  None, None, float(tolerance_rad), "failed", reason)
    if check_cancel is not None:
        check_cancel()
    errors = (
        max(abs(a - b) for a, b in zip(raw_reference.theta_rad, raw_transformed.theta_rad)),
        max(abs(a - b) for a, b in zip(raw_reference.theta_rad, lumped_result.theta_rad)),
    )
    return ForwardEquivalence(time_s, raw_reference, raw_transformed, lumped_result,
                              float(errors[0]), float(errors[1]), float(tolerance_rad), "success", None)


@dataclass(frozen=True)
class IdentifiabilityObjectiveNode:
    """一个直接计算或一维插值得到的 objective 点；分母为零时 ratio 不可用。"""

    omega2_s_inv2: float
    mean_objective_rad2: float | None
    objective_ratio: float | None
    log10_objective_ratio: float | None
    status: str
    reason: str | None
    evaluation: Literal["direct", "interpolated"]
    alpha_a: float | None = None
    omega0_sq_s_inv2: float | None = None


@dataclass(frozen=True)
class IdentifiabilityCurve:
    """222 点 q 条件扫描；实际样本、权重、loss、IC 和积分设置来自 request。"""

    omega2_s_inv2: tuple[float, ...]
    mean_objective_rad2: tuple[float | None, ...]
    objective_ratio: tuple[float | None, ...]
    log10_objective_ratio: tuple[float | None, ...]
    fitted_omega2_s_inv2: float
    fitted_mean_objective_rad2: float
    sample_count: int
    alpha1_star_s_inv: float
    alpha2_star_rad_inv: float
    request_digest: str


def _mean_objective(request: ObjectiveRequest, parameters: PendulumParameters) -> float | None:
    evaluated = evaluate_objective(request, M1, parameters)
    if evaluated.status != "success" or evaluated.cost_rad2 is None or not evaluated.residual_rad:
        return None
    return 2 * evaluated.cost_rad2 / len(evaluated.residual_rad)


def _ratio_values(mean_objective: float | None, fitted_mean: float) -> tuple[float | None, float | None]:
    if mean_objective is None or fitted_mean <= 0:
        return None, None
    ratio = mean_objective / fitted_mean
    return ratio, log10(max(ratio, 1e-12))


def evaluate_objective_at_q(
    request: ObjectiveRequest,
    fitted_parameters: PendulumParameters,
    omega2_s_inv2: float,
    *,
    curve: IdentifiabilityCurve | None = None,
    alpha_a: float | None = None,
    omega0_sq_s_inv2: float | None = None,
    check_cancel: Callable[[], None] | None = None,
) -> IdentifiabilityObjectiveNode:
    """用实际 ObjectiveRequest 直接求一个 q 点，不做插值或重新拟合阻尼。"""
    if (not isinstance(request, ObjectiveRequest) or not isinstance(fitted_parameters, PendulumParameters)
            or not _finite_number(omega2_s_inv2) or omega2_s_inv2 <= 0
            or (curve is not None and not isinstance(curve, IdentifiabilityCurve))
            or (alpha_a is not None and not _finite_number(alpha_a))
            or (omega0_sq_s_inv2 is not None and (not _finite_number(omega0_sq_s_inv2)
                                                  or omega0_sq_s_inv2 <= 0))):
        raise ValueError("objective node requires validated input, fitted damping and positive q")
    if curve is not None:
        _validate_curve_identity(request, fitted_parameters, curve)
    if check_cancel is not None:
        check_cancel()
    parameters = PendulumParameters(fitted_parameters.alpha1_s_inv, float(omega2_s_inv2),
                                    fitted_parameters.alpha2_rad_inv)
    mean_objective = _mean_objective(request, parameters)
    if check_cancel is not None:
        check_cancel()
    if curve is not None:
        fitted_mean = curve.fitted_mean_objective_rad2
    else:
        fitted_mean = _mean_objective(request, fitted_parameters)
    if fitted_mean is None or fitted_mean < 0:
        return IdentifiabilityObjectiveNode(float(omega2_s_inv2), mean_objective, None, None,
                                            "unavailable", "fitted_objective_unavailable", "direct",
                                            alpha_a, omega0_sq_s_inv2)
    if mean_objective is None:
        return IdentifiabilityObjectiveNode(float(omega2_s_inv2), None, None, None,
                                            "unavailable", "objective_evaluation_failed", "direct",
                                            alpha_a, omega0_sq_s_inv2)
    if fitted_mean == 0:
        return IdentifiabilityObjectiveNode(float(omega2_s_inv2), mean_objective, None, None,
                                            "unavailable", "zero_fitted_objective", "direct",
                                            alpha_a, omega0_sq_s_inv2)
    ratio, log_ratio = _ratio_values(mean_objective, fitted_mean)
    return IdentifiabilityObjectiveNode(float(omega2_s_inv2), mean_objective, ratio, log_ratio,
                                        "success", None, "direct", alpha_a, omega0_sq_s_inv2)


def _validate_curve_identity(
    request: ObjectiveRequest,
    fitted_parameters: PendulumParameters,
    curve: IdentifiabilityCurve,
) -> None:
    """拒绝把其他 request 或 fitted-star 参数的归一化分母接到当前节点。"""
    if (curve.request_digest != objective_request_digest(request)
            or curve.fitted_omega2_s_inv2 != fitted_parameters.omega2_s_inv2
            or curve.alpha1_star_s_inv != fitted_parameters.alpha1_s_inv
            or curve.alpha2_star_rad_inv != fitted_parameters.alpha2_rad_inv):
        raise ValueError("identifiability curve does not match the objective request and fitted parameters")


def build_identifiability_curve(
    request: ObjectiveRequest,
    fitted_parameters: PendulumParameters,
    *,
    check_cancel: Callable[[], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> IdentifiabilityCurve:
    """固定 starred damping 扫描 222 个 q；取消透传，不返回部分曲线。"""
    if not isinstance(request, ObjectiveRequest) or not isinstance(fitted_parameters, PendulumParameters):
        raise ValueError("curve requires a validated objective request and fitted M1 parameters")
    q_fit = fitted_parameters.omega2_s_inv2
    grid = np.unique(np.append(np.linspace(0.94 * q_fit / 1.12, 1.16 * q_fit, FROZEN_CURVE_COUNT - 1), q_fit))
    if len(grid) != FROZEN_CURVE_COUNT:
        raise ValueError("frozen q grid must contain 222 unique points")
    means: list[float | None] = []
    for index, q_value in enumerate(grid):
        if check_cancel is not None:
            check_cancel()
        means.append(_mean_objective(request, PendulumParameters(
            fitted_parameters.alpha1_s_inv, float(q_value), fitted_parameters.alpha2_rad_inv)))
        if progress is not None:
            progress(index + 1, len(grid))
    if check_cancel is not None:
        check_cancel()
    fit_index = int(np.flatnonzero(grid == q_fit)[0])
    fitted_mean = means[fit_index]
    if fitted_mean is None:
        raise ValueError("fitted q objective could not be evaluated")
    ratios: list[float | None] = []
    logs: list[float | None] = []
    for mean_objective in means:
        ratio, log_ratio = _ratio_values(mean_objective, fitted_mean)
        ratios.append(ratio)
        logs.append(log_ratio)
    sample_count = len(fit_sample_indices(request))
    return IdentifiabilityCurve(tuple(map(float, grid)), tuple(means), tuple(ratios), tuple(logs),
                                q_fit, float(fitted_mean), sample_count,
                                fitted_parameters.alpha1_s_inv, fitted_parameters.alpha2_rad_inv,
                                objective_request_digest(request))


def interpolate_objective_at_q(curve: IdentifiabilityCurve, omega2_s_inv2: float) -> IdentifiabilityObjectiveNode:
    """按 profile 在 objective ratio 上作 q 线性插值，不外推。"""
    if (not isinstance(curve, IdentifiabilityCurve) or not _finite_number(omega2_s_inv2)
            or omega2_s_inv2 < curve.omega2_s_inv2[0] or omega2_s_inv2 > curve.omega2_s_inv2[-1]):
        raise ValueError("interpolation requires q within the completed curve")
    q_values = curve.omega2_s_inv2
    index = bisect_left(q_values, float(omega2_s_inv2))
    if index < len(q_values) and q_values[index] == omega2_s_inv2:
        mean_objective = curve.mean_objective_rad2[index]
        ratio = curve.objective_ratio[index]
        log_ratio = curve.log10_objective_ratio[index]
    else:
        mean_objective = float(np.interp(omega2_s_inv2, q_values,
                                         [np.nan if value is None else value
                                          for value in curve.mean_objective_rad2]))
        ratio = float(np.interp(omega2_s_inv2, q_values,
                                [np.nan if value is None else value for value in curve.objective_ratio]))
        log_ratio = None if not isfinite(ratio) else log10(max(ratio, 1e-12))
        if not isfinite(mean_objective):
            mean_objective = None
        if not isfinite(ratio):
            ratio = None
    unavailable = mean_objective is None or ratio is None
    return IdentifiabilityObjectiveNode(float(omega2_s_inv2), mean_objective, ratio, log_ratio,
                                        "unavailable" if unavailable else "success",
                                        "objective_curve_unavailable" if unavailable else None,
                                        "interpolated")


@dataclass(frozen=True)
class IdentifiabilitySurface:
    """101×91 raw 坐标投影；q、ratio、log10 均为 alpha_a 行、omega0² 列。"""

    alpha_a_values: tuple[float, ...]
    omega0_sq_s_inv2_values: tuple[float, ...]
    omega2_s_inv2_grid: tuple[tuple[float, ...], ...]
    objective_ratio_grid: tuple[tuple[float | None, ...], ...]
    log10_objective_ratio_grid: tuple[tuple[float | None, ...], ...]
    fitted_mean_objective_rad2: float


def build_identifiability_surface(curve: IdentifiabilityCurve) -> IdentifiabilitySurface:
    """把已算 q curve 投影到固定 raw αa/ω₀² 网格，不运行额外 ODE。"""
    if not isinstance(curve, IdentifiabilityCurve):
        raise ValueError("surface requires a completed identifiability curve")
    alpha_values = np.linspace(*FROZEN_SURFACE_ALPHA_A, FROZEN_SURFACE_ALPHA_A_COUNT)
    omega_values = np.linspace(curve.fitted_omega2_s_inv2 * FROZEN_SURFACE_OMEGA2_FACTORS[0],
                               curve.fitted_omega2_s_inv2 * FROZEN_SURFACE_OMEGA2_FACTORS[1],
                               FROZEN_SURFACE_OMEGA2_COUNT)
    q_grid: list[tuple[float, ...]] = []
    ratio_grid: list[tuple[float | None, ...]] = []
    log_grid: list[tuple[float | None, ...]] = []
    for alpha_a in alpha_values:
        q_row = tuple(float(omega / (1 + alpha_a)) for omega in omega_values)
        points = tuple(interpolate_objective_at_q(curve, q_value) for q_value in q_row)
        q_grid.append(q_row)
        ratio_grid.append(tuple(point.objective_ratio for point in points))
        log_grid.append(tuple(point.log10_objective_ratio for point in points))
    return IdentifiabilitySurface(tuple(map(float, alpha_values)), tuple(map(float, omega_values)),
                                  tuple(q_grid), tuple(ratio_grid), tuple(log_grid),
                                  curve.fitted_mean_objective_rad2)


def evaluate_surface_node_direct(
    request: ObjectiveRequest,
    fitted_parameters: PendulumParameters,
    curve: IdentifiabilityCurve,
    alpha_a: float,
    omega0_sq_s_inv2: float,
    *,
    check_cancel: Callable[[], None] | None = None,
) -> IdentifiabilityObjectiveNode:
    """用实际 ODE 直接复核选定(raw αa,ω₀²)节点，保留条件曲面的 starred damping。"""
    if (not isinstance(curve, IdentifiabilityCurve) or not _finite_number(alpha_a) or alpha_a < 0
            or not _finite_number(omega0_sq_s_inv2) or omega0_sq_s_inv2 <= 0):
        raise ValueError("direct surface node requires non-negative alpha_a and positive omega0 squared")
    q_value = float(omega0_sq_s_inv2 / (1 + alpha_a))
    return evaluate_objective_at_q(request, fitted_parameters, q_value,
                                   curve=curve,
                                   alpha_a=float(alpha_a), omega0_sq_s_inv2=float(omega0_sq_s_inv2),
                                   check_cancel=check_cancel)
