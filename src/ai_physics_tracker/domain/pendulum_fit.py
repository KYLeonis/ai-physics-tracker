"""领域层：bounded deterministic multistart与共同输入的M0/M1比较，无Qt/IO。"""

from dataclasses import asdict, dataclass
from math import degrees, isfinite
from typing import Callable

import numpy as np
from scipy.optimize import least_squares

from ai_physics_tracker.domain.angular_analysis import LEGACY
from ai_physics_tracker.domain.pendulum_fit_seed import (
    START_MARGIN, SeedEstimate, deterministic_starts, estimate_fit_seed,
)
from ai_physics_tracker.domain.pendulum_ode import (
    M0, M1, ObjectiveRequest, PendulumParameters, TrajectoryEvaluation,
    evaluate_objective, evaluate_trajectory, fit_eligibility, fit_sample_indices,
    fit_valid_indices, objective_config, objective_request_digest,
)
from ai_physics_tracker.domain.types import canonical_json_digest

CORE_VERSION = "pendulum-fit-1.1.0"
BOUND_RELATIVE_TOLERANCE = 1e-4
JACOBIAN_CONDITION_WARNING = 1e8


def _bounds(value: tuple[float, float], name: str, *, positive: bool = False) -> tuple[float, float]:
    if (not isinstance(value, tuple) or len(value) != 2
            or any(type(v) not in (int, float) or not isfinite(v) for v in value)
            or value[0] < 0 or (positive and value[0] <= 0)
            or value[1]-value[0] <= 2*START_MARGIN):
        raise ValueError(f"{name} requires finite ordered bounds and a nonempty interior")
    return tuple(map(float, value))


@dataclass(frozen=True)
class FitSettings:
    """明确可改的实际bounds/优化设置；None q bounds解析为[.20,1.60]g/L。"""
    alpha1_bounds: tuple[float, float] = (0., .5)
    alpha2_bounds: tuple[float, float] = (0., .5)
    omega2_bounds: tuple[float, float] | None = None
    max_nfev: int = 180
    ftol: float = 1e-8
    xtol: float = 1e-8
    gtol: float = 1e-8
    starts: tuple[tuple[float, ...], ...] | None = None

    def __post_init__(self) -> None:
        for name in ("alpha1_bounds", "alpha2_bounds"):
            object.__setattr__(self, name, _bounds(getattr(self, name), name))
        if self.omega2_bounds is not None:
            object.__setattr__(self, "omega2_bounds", _bounds(self.omega2_bounds, "omega2_bounds", positive=True))
        if type(self.max_nfev) is not int or self.max_nfev < 1:
            raise ValueError("max_nfev must be a positive integer")
        for name in ("ftol", "xtol", "gtol"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value <= np.finfo(float).eps:
                raise ValueError(f"{name} must exceed machine epsilon and be finite")
            object.__setattr__(self, name, float(value))
        if self.starts is not None:
            if (not isinstance(self.starts, tuple) or not self.starts
                    or any(not isinstance(s, tuple) or not s or
                           any(type(v) not in (int, float) or not isfinite(v) for v in s) for s in self.starts)):
                raise ValueError("custom starts must be nonempty immutable finite vectors")
            object.__setattr__(self, "starts", tuple(tuple(map(float, s)) for s in self.starts))


def fit_bounds(request: ObjectiveRequest, model: str, settings: FitSettings) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """依模型确定参数顺序；拒绝未知模型而非按维数猜测。"""
    if not isinstance(request, ObjectiveRequest) or not isinstance(settings, FitSettings):
        raise ValueError("fit requires validated objective and settings")
    q = request.g_m_s2/request.effective_length_m
    qbounds = settings.omega2_bounds or _bounds((.20*q, 1.60*q), "resolved omega2_bounds", positive=True)
    if model not in (M0, M1):
        raise ValueError(f"unsupported model: {model}")
    pairs = (settings.alpha1_bounds, qbounds) if model == M0 else (
        settings.alpha1_bounds, settings.alpha2_bounds, qbounds)
    return tuple(v[0] for v in pairs), tuple(v[1] for v in pairs)


def _parameters(model: str, values: tuple[float, ...]) -> PendulumParameters:
    return PendulumParameters(values[0], values[-1], values[1] if model == M1 else 0.)


@dataclass(frozen=True)
class StartDiagnostic:
    start: tuple[float, ...]
    parameters: tuple[float, ...] | None
    status: str
    optimizer_success: bool
    cost_rad2: float | None
    nfev: int
    message: str
    failed_evaluations: int
    at_bound: tuple[bool, ...]
    jacobian_rank: int | None
    jacobian_condition: float | None


@dataclass(frozen=True)
class PendulumFit:
    """完整fit事实；failed/insufficient_data不携带冒充成功的参数或trajectory。"""
    model: str
    status: str
    reason: str | None
    parameters: PendulumParameters | None
    selected_start_index: int | None
    starts: tuple[StartDiagnostic, ...]
    seed: SeedEstimate
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    sample_frames: tuple[int, ...]
    sample_time_s: tuple[float, ...]
    trajectory: TrajectoryEvaluation | None
    warnings: tuple[str, ...]
    input_digest: str
    comparability_digest: str
    config: dict[str, object]


def fit_config(request: ObjectiveRequest, settings: FitSettings) -> dict[str, object]:
    """Normal/Advanced共享同一展开值；自定义设置有明确override provenance。"""
    resolved = asdict(settings)
    defaults = asdict(FitSettings())
    overrides = {key: value for key, value in resolved.items() if value != defaults[key]}
    return {"core_version": CORE_VERSION, "objective": objective_config(request),
        "settings": resolved, "resolved_overrides": {"source": "user-settings", "values": overrides} if overrides else {},
        "optimizer": {"method": "trf", "jac": "2-point", "x_scale": "jac", "loss": request.loss,
            "f_scale_rad": request.f_scale_rad, "max_nfev": settings.max_nfev,
            "ftol": settings.ftol, "xtol": settings.xtol, "gtol": settings.gtol,
            "diff_step": None, "tr_solver": "exact", "tr_options": {}, "jac_sparsity": None},
        "sources": ["source-fitting", "source-m0_linear", "source-m1_linear_quadratic",
                    "policy-student-v1"] if request.profile_id != LEGACY else ["source-fitting"]}


def _comparison_digest(request: ObjectiveRequest, settings: FitSettings) -> str:
    # starts是模型求解策略，不改变观测/目标；不阻止M1较M0多一个默认起点。
    common = asdict(settings); common.pop("starts")
    return canonical_json_digest({"objective": objective_request_digest(request), "settings": common})


def _resolve_starts(request, model, settings, seed, lower, upper, warm_start):
    if settings.starts is not None:
        if any(len(s) != len(lower) or any(v < lo or v > hi for v, lo, hi in zip(s, lower, upper))
               for s in settings.starts):
            raise ValueError("custom start shape/values must match the model bounds")
        return tuple(tuple(map(float, np.clip(s, np.asarray(lower)+START_MARGIN,
                                             np.asarray(upper)-START_MARGIN))) for s in settings.starts)
    starts = deterministic_starts(model, seed, lower, upper)
    if warm_start is not None:
        if (model != M1 or not isinstance(warm_start, PendulumFit) or warm_start.model != M0
                or warm_start.comparability_digest != _comparison_digest(request, settings)):
            raise ValueError("M1 warm start must be a comparable M0 result")
        allowed = warm_start.status == "success" or (request.profile_id == LEGACY and warm_start.status == "nonconverged")
        if allowed and warm_start.parameters is not None:
            p = warm_start.parameters
            warm = tuple(map(float, np.clip((p.alpha1_s_inv, 1e-8, p.omega2_s_inv2),
                                            np.asarray(lower)+START_MARGIN, np.asarray(upper)-START_MARGIN)))
            starts = (warm,)+starts
    return starts


def _run_start(request, model, settings, start, lower, upper, check_cancel):
    failures = 0
    def residuals(values):
        nonlocal failures
        if check_cancel is not None:
            check_cancel()
        evaluated = evaluate_objective(request, model, _parameters(model, tuple(map(float, values))))
        if evaluated.status != "success":
            failures += 1
        return np.asarray(evaluated.residual_rad, dtype=float)

    try:
        result = least_squares(residuals, x0=start, bounds=(lower, upper),
            method="trf", jac="2-point", ftol=settings.ftol, xtol=settings.xtol, gtol=settings.gtol,
            x_scale="jac", loss=request.loss, f_scale=request.f_scale_rad, max_nfev=settings.max_nfev,
            diff_step=None, tr_solver="exact", tr_options={}, jac_sparsity=None, verbose=0)
    except (ValueError, RuntimeError, FloatingPointError, OverflowError) as error:
        return StartDiagnostic(start, None, "failed", False, None, 0, str(error), failures, (), None, None)
    if not np.all(np.isfinite(result.x)) or not isfinite(float(result.cost)):
        return StartDiagnostic(start, None, "failed", False, None, int(result.nfev),
                               "nonfinite optimizer candidate", failures, (), None, None)
    values = tuple(map(float, result.x))
    try:
        if not np.all(np.isfinite(result.jac)):
            raise ValueError("nonfinite optimizer Jacobian")
        singular = np.linalg.svd(result.jac, compute_uv=False)
    except (ValueError, RuntimeError, FloatingPointError, OverflowError) as error:
        return StartDiagnostic(start, None, "failed", False, None, int(result.nfev),
                               f"Jacobian diagnostic failed: {error}", failures, (), None, None)
    tolerance = np.finfo(float).eps*max(result.jac.shape)*singular[0] if len(singular) else 0.
    rank = int(np.count_nonzero(singular > tolerance))
    condition = float(singular[0]/singular[-1]) if len(singular) and singular[-1] > 0 else None
    if condition is not None and not isfinite(condition):
        condition = None
    flags = tuple(bool(v) for v in (np.minimum(result.x-np.asarray(lower), np.asarray(upper)-result.x)
                                   <= BOUND_RELATIVE_TOLERANCE*np.maximum(np.asarray(upper)-lower, 1.)))
    return StartDiagnostic(start, values, "success" if result.success else "nonconverged", bool(result.success),
                           float(result.cost), int(result.nfev), str(result.message), failures, flags, rank, condition)


def _fit_identity(request, model, settings, warm_start):
    lower, upper = fit_bounds(request, model, settings)
    seed = estimate_fit_seed(request, (lower[-1], upper[-1]), upper[0])
    starts = _resolve_starts(request, model, settings, seed, lower, upper, warm_start)
    config = fit_config(request, settings)
    sample = fit_sample_indices(request)
    frames = tuple(request.series.frame_indices[i] for i in sample)
    times = tuple(request.series.time_release_relative_s[i] for i in sample)
    comparison = _comparison_digest(request, settings)
    digest = canonical_json_digest({"request": objective_request_digest(request), "model": model,
        "config": config, "lower": list(lower), "upper": list(upper), "starts": starts, "seed": asdict(seed)})
    return lower, upper, seed, starts, config, frames, times, comparison, digest


def _fit_warnings(request, best, diagnostics, lower):
    warnings = []
    if not best.optimizer_success:
        warnings.append("optimizer_not_converged")
    if any(best.at_bound):
        warnings.append("parameter_at_bound")
    if best.jacobian_rank < len(lower):
        warnings.append("rank_deficient_local_jacobian")
    if best.jacobian_condition is None or best.jacobian_condition > JACOBIAN_CONDITION_WARNING:
        warnings.append("ill_conditioned_local_jacobian")
    if any(d.failed_evaluations for d in diagnostics):
        warnings.append("integration_failures_during_optimization")
    if any(d.status == "failed" for d in diagnostics):
        warnings.append("some_starts_failed")
    valid = fit_valid_indices(request)
    end_s = request.series.time_release_relative_s[request.series.frame_indices.index(request.end_frame_index)]
    late = [request.series.theta_rad[i] for i in valid if request.series.time_release_relative_s[i] >= end_s-5]
    if late and abs(degrees(float(np.median(late)))) > 1:
        warnings.append("late_equilibrium_offset_over_1deg")
    return tuple(warnings)


def fit_pendulum(request: ObjectiveRequest, model: str, settings: FitSettings = FitSettings(), *,
                 warm_start: PendulumFit | None = None, check_cancel: Callable[[], None] | None = None,
                 progress: Callable[[int, int], None] | None = None) -> PendulumFit:
    """数值候选取最小finite cost，单独复核最终forward；取消异常透传给任务所有者。"""
    lower, upper, seed, starts, config, frames, times, comparison, digest = _fit_identity(
        request, model, settings, warm_start)
    def output(status, reason=None, parameters=None, selected=None, diagnostics=(), trajectory=None, warnings=()):
        return PendulumFit(model, status, reason, parameters, selected, diagnostics, seed,
                           lower, upper, frames, times, trajectory, warnings, digest, comparison, config)
    eligibility = fit_eligibility(request)
    if eligibility.status != "ready":
        return output("insufficient_data", ";".join(eligibility.reasons))
    diagnostics = []
    for index, start in enumerate(starts):
        if check_cancel is not None:
            check_cancel()
        diagnostics.append(_run_start(request, model, settings, start, lower, upper, check_cancel))
        if progress is not None:
            progress(index+1, len(starts))
    diagnostics = tuple(diagnostics)
    candidates = [i for i, d in enumerate(diagnostics) if d.parameters is not None and d.cost_rad2 is not None]
    if not candidates:
        return output("failed", "all_starts_failed", diagnostics=diagnostics)
    selected = min(candidates, key=lambda i: diagnostics[i].cost_rad2)
    best = diagnostics[selected]
    parameters = _parameters(model, best.parameters)
    if check_cancel is not None:
        check_cancel()
    final_objective = evaluate_objective(request, model, parameters)
    trajectory = evaluate_trajectory(request, model, parameters)
    if final_objective.status != "success" or trajectory.status != "success":
        return output("failed", final_objective.reason or trajectory.reason,
                      selected=selected, diagnostics=diagnostics)
    warnings = _fit_warnings(request, best, diagnostics, lower)
    return output(best.status, parameters=parameters, selected=selected,
                  diagnostics=diagnostics, trajectory=trajectory, warnings=tuple(warnings))


@dataclass(frozen=True)
class FitComparison:
    status: str
    reason: str | None
    rmse_improvement_percent: float | None


def compare_fits(m0: PendulumFit, m1: PendulumFit) -> FitComparison:
    """较低RMSE仅是同一输入上的拟合比较，不证明二次阻尼或参数独立可辨识。"""
    if m0.model != M0 or m1.model != M1:
        raise ValueError("comparison requires ordered M0 and M1 fits")
    if m0.comparability_digest != m1.comparability_digest:
        return FitComparison("not_comparable", "inputs_or_configuration_differ", None)
    if m0.status != "success" or m1.status != "success":
        return FitComparison("unavailable", "fit_not_converged_or_failed", None)
    denominator = m0.trajectory.rmse_rad
    if denominator <= 0:
        return FitComparison("unavailable", "zero_m0_rmse", None)
    return FitComparison("comparable", None, 100*(denominator-m1.trajectory.rmse_rad)/denominator)


def validate_saved_fit(request: ObjectiveRequest, model: str, settings: FitSettings,
                       saved: dict, *, warm_start: PendulumFit | None = None) -> PendulumFit:
    """读回时复核同core身份、typed诊断和final forward；不重做优化。"""
    from dataclasses import fields
    if not isinstance(saved, dict) or set(saved) != {f.name for f in fields(PendulumFit)}:
        raise ValueError("saved fit structure changed")
    lower, upper, seed, starts, config, frames, times, comparison, digest = _fit_identity(request, model, settings, warm_start)
    expected = {"model": model, "lower": lower, "upper": upper, "seed": asdict(seed), "config": config,
                "sample_frames": frames, "sample_time_s": times, "comparability_digest": comparison, "input_digest": digest}
    if canonical_json_digest(expected) != canonical_json_digest({k: saved[k] for k in expected}):
        raise ValueError("saved fit input/configuration identity changed")
    if fit_eligibility(request).status != "ready":
        result = fit_pendulum(request, model, settings, warm_start=warm_start)
        if canonical_json_digest(asdict(result)) != canonical_json_digest(saved):
            raise ValueError("saved insufficient-data fit changed")
        return result
    if not isinstance(saved["starts"], list) or len(saved["starts"]) != len(starts):
        raise ValueError("saved start diagnostics incomplete")
    diagnostics = []
    for expected_start, raw in zip(starts, saved["starts"]):
        if not isinstance(raw, dict) or set(raw) != {f.name for f in fields(StartDiagnostic)}:
            raise ValueError("saved start diagnostic structure changed")
        data = dict(raw)
        for key in ("start", "parameters", "at_bound"):
            data[key] = None if data[key] is None else tuple(data[key])
        diagnostic = StartDiagnostic(**data)
        if (diagnostic.start != expected_start or diagnostic.status not in ("success", "nonconverged", "failed")
                or type(diagnostic.optimizer_success) is not bool
                or diagnostic.optimizer_success != (diagnostic.status == "success")
                or type(diagnostic.nfev) is not int or not 0 <= diagnostic.nfev <= settings.max_nfev
                or type(diagnostic.failed_evaluations) is not int or diagnostic.failed_evaluations < 0
                or not isinstance(diagnostic.message, str)):
            raise ValueError("saved start diagnostic values changed")
        if diagnostic.parameters is not None:
            if (len(diagnostic.parameters) != len(lower) or any(type(v) not in (int, float) or not isfinite(v)
                    or not lo <= v <= hi for v, lo, hi in zip(diagnostic.parameters, lower, upper))
                    or type(diagnostic.cost_rad2) not in (int, float) or not isfinite(diagnostic.cost_rad2) or diagnostic.cost_rad2 < 0
                    or len(diagnostic.at_bound) != len(lower) or any(type(v) is not bool for v in diagnostic.at_bound)
                    or type(diagnostic.jacobian_rank) is not int or not 0 <= diagnostic.jacobian_rank <= len(lower)
                    or diagnostic.jacobian_condition is not None and (type(diagnostic.jacobian_condition) not in (int, float)
                        or not isfinite(diagnostic.jacobian_condition) or diagnostic.jacobian_condition < 1)):
                raise ValueError("saved candidate diagnostic is invalid")
            flags = tuple(bool(v) for v in (np.minimum(np.asarray(diagnostic.parameters)-lower,
                np.asarray(upper)-diagnostic.parameters) <= BOUND_RELATIVE_TOLERANCE*np.maximum(np.asarray(upper)-lower, 1.)))
            if diagnostic.at_bound != flags:
                raise ValueError("saved candidate bound flags changed")
        elif (diagnostic.status != "failed" or diagnostic.cost_rad2 is not None or diagnostic.at_bound
                or diagnostic.jacobian_rank is not None or diagnostic.jacobian_condition is not None):
            raise ValueError("saved failed candidate has parameters/cost")
        diagnostics.append(diagnostic)
    diagnostics = tuple(diagnostics)
    candidates = [i for i, d in enumerate(diagnostics) if d.parameters is not None and d.cost_rad2 is not None]
    selected = min(candidates, key=lambda i: diagnostics[i].cost_rad2) if candidates else None
    if saved["selected_start_index"] != selected:
        raise ValueError("saved selected start changed")
    parameters = _parameters(model, diagnostics[selected].parameters) if selected is not None else None
    evaluated = evaluate_objective(request, model, parameters) if parameters is not None else None
    reason = "all_starts_failed" if selected is None else None
    trajectory = evaluate_trajectory(request, model, parameters) if parameters is not None else None
    if trajectory is not None and (trajectory.status != "success" or evaluated.status != "success"):
        reason = evaluated.reason or trajectory.reason
        trajectory = None; parameters = None
    if (canonical_json_digest(saved["parameters"]) != canonical_json_digest(None if parameters is None else asdict(parameters))
            or canonical_json_digest(saved["trajectory"]) != canonical_json_digest(None if trajectory is None else asdict(trajectory))):
        raise ValueError("saved fit parameters/prediction/residual changed")
    if trajectory is not None:
        if evaluated.status != "success" or not np.isclose(evaluated.cost_rad2,
                diagnostics[selected].cost_rad2, atol=1e-12, rtol=1e-8):
            raise ValueError("saved selected objective cost changed")
    status = diagnostics[selected].status if trajectory is not None else "failed"
    warnings = _fit_warnings(request, diagnostics[selected], diagnostics, lower) if trajectory is not None else ()
    if saved["status"] != status or saved["warnings"] != list(warnings) or saved["reason"] != reason:
        raise ValueError("saved fit status/warnings changed")
    if saved["reason"] is not None and not isinstance(saved["reason"], str):
        raise ValueError("saved fit reason changed")
    return PendulumFit(model, status, saved["reason"], parameters, selected, diagnostics, seed,
        lower, upper, frames, times, trajectory, warnings, digest, comparison, config)
