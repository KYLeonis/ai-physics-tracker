"""领域层：固定初态的单摆ODE与原始θ目标函数，无Qt/文件/观测补值。"""

from dataclasses import asdict, dataclass
from math import atan2, ceil, isclose, isfinite, pi, sin, sqrt

import numpy as np
import scipy
from scipy.integrate import solve_ivp

from ai_physics_tracker.domain.angular_analysis import (
    AngularSeries, LEGACY, STUDENT, angular_series_digest,
)
from ai_physics_tracker.domain.pendulum_reconstruction import (
    LEGACY_PROFILE_SHA256, STUDENT_PROFILE_SHA256,
)
from ai_physics_tracker.domain.timeline import TIME_COMPARISON_TOLERANCE_S
from ai_physics_tracker.domain.types import canonical_json_digest

M0 = "M0_linear"
M1 = "M1_linear_quadratic"
CORE_VERSION = "pendulum-ode-1.1.0"
INTEGRATION_FAILURE_RESIDUAL_RAD = 1000.0
DEFAULT_F_SCALE_RAD = pi / 360
DEFAULT_MAXIMUM_SAMPLES = 500
MINIMUM_VALID_FRAMES = 50
MINIMUM_REFERENCE_PERIODS = 3
PRE_RELEASE_FRAMES = 5


def _finite_number(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value)


@dataclass(frozen=True)
class InitialCondition:
    """在release t=0固定的IC；来源独立于第一个拟合观测。"""

    theta0_rad: float
    omega0_rad_s: float
    source: str
    support_frames: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if (not _finite_number(self.theta0_rad) or abs(self.theta0_rad) > pi
                or not _finite_number(self.omega0_rad_s)):
            raise ValueError("fixed IC requires finite signed theta0 radians and omega0 rad/s")
        if self.source not in ("explicit", "pre_release_rest", "archived_toml"):
            raise ValueError("unsupported initial condition source")
        frames = self.support_frames
        if (not isinstance(frames, tuple) or any(type(f) is not int or f < 0 for f in frames)
                or any(b != a + 1 for a, b in zip(frames, frames[1:]))):
            raise ValueError("IC support frames must be ordered consecutive source IDs")
        if self.source == "pre_release_rest":
            if len(frames) != PRE_RELEASE_FRAMES or abs(self.omega0_rad_s) > 0:
                raise ValueError("rest IC requires five support frames and fixed zero angular velocity")
        elif frames:
            raise ValueError("explicit/archived IC cannot claim estimated support frames")
        object.__setattr__(self, "theta0_rad", float(self.theta0_rad))
        object.__setattr__(self, "omega0_rad_s", float(self.omega0_rad_s))


def resolve_student_initial_condition(
    series: AngularSeries, release_frame_index: int, *, rest_confirmed: bool,
    explicit: InitialCondition | None = None,
) -> InitialCondition | None:
    """scientific-profiles §3/§8；None明确表示needs_explicit_IC，不取首观测。"""
    if not isinstance(series, AngularSeries):
        raise ValueError("IC requires a validated AngularSeries")
    if type(rest_confirmed) is not bool or type(release_frame_index) is not int or release_frame_index < 0:
        raise ValueError("IC requires an explicit rest boolean and a non-negative release frame")
    if explicit is not None:
        if not isinstance(explicit, InitialCondition) or explicit.source != "explicit":
            raise ValueError("student explicit IC must have explicit provenance")
        return explicit
    if not rest_confirmed or release_frame_index < PRE_RELEASE_FRAMES:
        return None
    supports = tuple(range(release_frame_index - PRE_RELEASE_FRAMES, release_frame_index))
    rows = {f: i for i, f in enumerate(series.frame_indices)}
    if any(f not in rows or not series.qc_valid[rows[f]]
           or series.time_release_relative_s[rows[f]] >= 0 for f in supports):
        return None
    angles = np.asarray([series.theta_rad[rows[f]] for f in supports], dtype=float)
    # source-data_io/initial：先对circular mean展开，再取median并包回[-π,π)。
    reference = atan2(float(np.mean(np.sin(angles))), float(np.mean(np.cos(angles))))
    unwrapped = reference + (angles - reference + pi) % (2 * pi) - pi
    theta0 = float((np.median(unwrapped) + pi) % (2 * pi) - pi)
    return InitialCondition(theta0, 0.0, "pre_release_rest", supports)


@dataclass(frozen=True)
class IntegrationSettings:
    """profile的DOP853显式参数；None max_step表示无穷，便于严格JSON保存。"""

    rtol: float = 2e-7
    atol: float = 2e-9
    max_step_s: float | None = None
    first_step_s: float | None = None

    def __post_init__(self) -> None:
        for name in ("rtol", "atol", "max_step_s", "first_step_s"):
            value = getattr(self, name)
            if value is None and name in ("max_step_s", "first_step_s"):
                continue
            if not _finite_number(value) or value <= 0:
                raise ValueError(f"integrator {name} must be positive and finite")
            object.__setattr__(self, name, float(value))
        if self.rtol < 100 * np.finfo(float).eps:
            raise ValueError("rtol is below SciPy's supported precision; no implicit clipping")


@dataclass(frozen=True)
class PendulumParameters:
    """集总参数；αa等raw参数不是可独立辨识的fit输出。"""

    alpha1_s_inv: float
    omega2_s_inv2: float
    alpha2_rad_inv: float = 0.0

    def __post_init__(self) -> None:
        for name in ("alpha1_s_inv", "alpha2_rad_inv", "omega2_s_inv2"):
            value = getattr(self, name)
            if not _finite_number(value) or value < 0 or (name == "omega2_s_inv2" and value <= 0):
                raise ValueError(f"invalid pendulum parameter: {name}")
            object.__setattr__(self, name, float(value))


def _validate_model(model: str, parameters: PendulumParameters) -> None:
    if model not in (M0, M1):
        raise ValueError(f"unsupported pendulum model: {model}")
    if model == M0 and parameters.alpha2_rad_inv > 0:
        raise ValueError("M0 cannot silently discard nonzero quadratic damping")


def pendulum_rhs(state: tuple[float, float], parameters: PendulumParameters) -> tuple[float, float]:
    """platform-requirements §7：完整sinθ；α2=0即M0，状态单位rad/rad/s。"""
    theta, omega = state
    acceleration = (-parameters.omega2_s_inv2 * sin(theta) - parameters.alpha1_s_inv * omega
                    - parameters.alpha2_rad_inv * omega * abs(omega))
    return omega, acceleration


@dataclass(frozen=True)
class ForwardResult:
    """失败时不返回部分轨迹；empty仅表示请求无求值时刻。"""

    status: str
    reason: str | None
    theta_rad: tuple[float, ...]
    omega_rad_s: tuple[float, ...]
    nfev: int


def simulate_pendulum(
    model: str, parameters: PendulumParameters, initial_condition: InitialCondition,
    time_s: tuple[float, ...], settings: IntegrationSettings = IntegrationSettings(),
) -> ForwardResult:
    """从0持续积分到最后真实观测时间；gap既不重启IC，也不补成观测。"""
    if (not isinstance(parameters, PendulumParameters) or not isinstance(initial_condition, InitialCondition)
            or not isinstance(settings, IntegrationSettings)):
        raise ValueError("forward requires validated parameters, initial_condition and integration settings")
    _validate_model(model, parameters)
    if (not isinstance(time_s, tuple) or any(not _finite_number(t) or t < 0 for t in time_s)
            or any(b <= a for a, b in zip(time_s, time_s[1:]))):
        raise ValueError("forward times must be an ordered immutable tuple of non-negative finite seconds")
    if not time_s:
        return ForwardResult("empty", None, (), (), 0)
    if time_s[-1] <= 0:
        return ForwardResult("success", None, (initial_condition.theta0_rad,), (initial_condition.omega0_rad_s,), 0)
    if settings.first_step_s is not None and settings.first_step_s > time_s[-1]:
        raise ValueError("first_step exceeds integration span")

    def rhs(_time, state):
        return pendulum_rhs(state, parameters)

    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            solution = solve_ivp(rhs, (0.0, time_s[-1]),
                (initial_condition.theta0_rad, initial_condition.omega0_rad_s), method="DOP853",
                t_eval=np.asarray(time_s, dtype=float), rtol=settings.rtol, atol=settings.atol,
                max_step=np.inf if settings.max_step_s is None else settings.max_step_s,
                first_step=settings.first_step_s, vectorized=False, dense_output=False, events=None)
    except (FloatingPointError, OverflowError, ValueError, RuntimeError) as exc:
        # 已校验请求；这里只把求解器的数值失败转成可诊断结果，不吞编程错误。
        return ForwardResult("failed", f"integration_failed: {exc}", (), (), 0)
    if not solution.success or np.shape(solution.y) != (2, len(time_s)):
        return ForwardResult("failed", f"integration_failed: {solution.message}", (), (), int(solution.nfev))
    if not np.all(np.isfinite(solution.y)):
        return ForwardResult("failed", "nonfinite_prediction", (), (), int(solution.nfev))
    return ForwardResult("success", None, tuple(map(float, solution.y[0])),
                         tuple(map(float, solution.y[1])), int(solution.nfev))


@dataclass(frozen=True)
class ObjectiveRequest:
    """P3共享数值输入；relative_weights已由adopted source解析，None表示缺测。"""

    series: AngularSeries
    relative_weights: tuple[float | None, ...]
    initial_condition: InitialCondition
    release_frame_index: int
    end_frame_index: int
    effective_length_m: float
    g_m_s2: float = 9.80665
    profile_id: str = STUDENT
    maximum_samples: int = DEFAULT_MAXIMUM_SAMPLES
    f_scale_rad: float = DEFAULT_F_SCALE_RAD
    integration: IntegrationSettings = IntegrationSettings()
    loss: str = "soft_l1"
    fit_start_frame_index: int | None = None

    def __post_init__(self) -> None:
        if (not isinstance(self.series, AngularSeries) or not isinstance(self.initial_condition, InitialCondition)
                or not isinstance(self.integration, IntegrationSettings)):
            raise ValueError("objective requires validated series, initial_condition and integration settings")
        if self.profile_id not in (STUDENT, LEGACY):
            raise ValueError("unsupported ODE profile")
        if self.loss not in ("soft_l1", "linear"):
            raise ValueError("fit loss must be soft_l1 or linear")
        if (type(self.release_frame_index) is not int or self.release_frame_index < 0
                or self.release_frame_index not in self.series.frame_indices
                or type(self.end_frame_index) is not int or self.end_frame_index < self.release_frame_index
                or self.end_frame_index not in self.series.frame_indices):
            raise ValueError("fit interval requires valid release and observed source end frame")
        start = self.release_frame_index if self.fit_start_frame_index is None else self.fit_start_frame_index
        if (type(start) is not int or not self.release_frame_index <= start <= self.end_frame_index
                or start not in self.series.frame_indices):
            raise ValueError("fit start must be a source frame between release and end")
        for f, t in zip(self.series.frame_indices, self.series.time_release_relative_s):
            if ((f < self.release_frame_index and t >= 0) or (f > self.release_frame_index and t <= 0)
                    or (f == self.release_frame_index and (t < 0 or abs(t) > TIME_COMPARISON_TOLERANCE_S))):
                raise ValueError("frame/time release identity is inconsistent")
        if not isinstance(self.relative_weights, tuple) or len(self.relative_weights) != len(self.series.frame_indices):
            raise ValueError("relative weights must be an immutable source-aligned tuple")
        if any((w is not None and (not _finite_number(w) or not 0.05 <= w <= 1))
               or (ok and w is None) for w, ok in zip(self.relative_weights, self.series.qc_valid)):
            raise ValueError("QC-valid frames require finite relative weights within [0.05, 1]")
        if self.profile_id == STUDENT and self.initial_condition.source == "archived_toml":
            raise ValueError("student fit cannot silently use archived IC")
        if self.profile_id == LEGACY and self.initial_condition.source != "archived_toml":
            raise ValueError("legacy fit requires explicit archived TOML IC provenance")
        if self.initial_condition.source == "pre_release_rest":
            expected = tuple(range(self.release_frame_index - PRE_RELEASE_FRAMES, self.release_frame_index))
            if self.initial_condition.support_frames != expected:
                raise ValueError("rest IC support does not precede this release")
            resolved = resolve_student_initial_condition(self.series, self.release_frame_index, rest_confirmed=True)
            if (resolved is None or not isclose(resolved.theta0_rad, self.initial_condition.theta0_rad,
                                                rel_tol=0, abs_tol=1e-12)):
                raise ValueError("rest IC does not match the current pre-release base QC")
        for name in ("effective_length_m", "g_m_s2", "f_scale_rad"):
            value = getattr(self, name)
            if not _finite_number(value) or value <= 0:
                raise ValueError(f"fit {name} must be positive and finite")
            object.__setattr__(self, name, float(value))
        if not isfinite(self.g_m_s2 / self.effective_length_m) or self.g_m_s2 / self.effective_length_m <= 0:
            raise ValueError("g/L must be positive and finite")
        if type(self.maximum_samples) is not int or self.maximum_samples < 1:
            raise ValueError("maximum_samples must be a positive integer")
        object.__setattr__(self, "relative_weights", tuple(None if w is None else float(w) for w in self.relative_weights))

    @property
    def start_frame_index(self) -> int:
        return self.release_frame_index if self.fit_start_frame_index is None else self.fit_start_frame_index


def objective_config(request: ObjectiveRequest) -> dict[str, object]:
    """配置展开记录实际库版本；只实现本轮已使用的政策，无公式字符串eval。"""
    student = request.profile_id == STUDENT
    return {
        "profile_id": request.profile_id, "profile_version": "2.0.0" if student else "1.0.0",
        "profile_sha256": STUDENT_PROFILE_SHA256 if student else LEGACY_PROFILE_SHA256,
        "formula_profile_sha256": LEGACY_PROFILE_SHA256, "core_version": CORE_VERSION,
        "numpy_version": np.__version__, "scipy_version": scipy.__version__,
        "integration": {"method": "DOP853", **asdict(request.integration),
                        "vectorized": False, "dense_output": False, "events": None},
        "interval": {"start_frame_index": request.start_frame_index, "end_frame_index": request.end_frame_index,
                     "ic_release_frame_index": request.release_frame_index},
        "sampling": {"maximum": request.maximum_samples, "rounding": "nearest_ties_to_even",
                     "algorithm": "valid_index_linspace_rint_unique"},
        "objective": {"loss": request.loss, "f_scale_rad": request.f_scale_rad,
                      "residual": "sqrt(relative_weight)*(predicted_rad-observed_rad)",
                      "integration_failure_residual_rad": INTEGRATION_FAILURE_RESIDUAL_RAD},
        "eligibility": {"minimum_valid_frames": MINIMUM_VALID_FRAMES,
                        "fraction": 0.5, "rounding": "ceil" if student else "floor",
                        "minimum_span_reference_periods": MINIMUM_REFERENCE_PERIODS if student else None},
        "sources": ["source-fitting", "source-m0_linear", "source-m1_linear_quadratic",
                    "policy-student-v1", "policy-student-v2"] if student else ["source-fitting"],
    }


def objective_request_digest(request: ObjectiveRequest) -> str:
    """比较身份不含模型或候选参数，覆盖两模型必须共享的实际输入与配置。"""
    return canonical_json_digest({"series_digest": angular_series_digest(request.series),
        "weights": list(request.relative_weights), "ic": asdict(request.initial_condition),
        "release_frame_index": request.release_frame_index, "end_frame_index": request.end_frame_index,
        "effective_length_m": request.effective_length_m, "g_m_s2": request.g_m_s2,
        "config": objective_config(request)})


def fit_valid_indices(request: ObjectiveRequest) -> tuple[int, ...]:
    """源帧筛选；不受SG是否有导数或辅助role是否完整影响。"""
    return tuple(i for i, (f, ok) in enumerate(zip(request.series.frame_indices, request.series.qc_valid))
                 if request.start_frame_index <= f <= request.end_frame_index and ok)


@dataclass(frozen=True)
class FitEligibility:
    status: str
    reasons: tuple[str, ...]
    valid_count: int
    required_count: int
    valid_span_s: float
    required_span_s: float


def fit_eligibility(request: ObjectiveRequest) -> FitEligibility:
    """student计算门槛，不是信息充分/科学认证；历史仅保留floor计数门槛。"""
    indices = fit_valid_indices(request)
    total = request.end_frame_index - request.start_frame_index + 1
    required = max(MINIMUM_VALID_FRAMES, ceil(total / 2) if request.profile_id == STUDENT else total // 2)
    times = request.series.time_release_relative_s
    span = times[indices[-1]] - times[indices[0]] if len(indices) > 1 else 0.0
    required_span = MINIMUM_REFERENCE_PERIODS * 2 * pi * sqrt(request.effective_length_m / request.g_m_s2) if request.profile_id == STUDENT else 0.0
    reasons = []
    if len(indices) < required:
        reasons.append("insufficient_valid_frames")
    if span < required_span and not isclose(span, required_span, rel_tol=0, abs_tol=TIME_COMPARISON_TOLERANCE_S):
        reasons.append("insufficient_valid_time_span")
    return FitEligibility("ready" if not reasons else "insufficient_data", tuple(reasons),
                          len(indices), required, span, required_span)


def fit_sample_indices(request: ObjectiveRequest) -> tuple[int, ...]:
    """source-fitting选样：valid序号抽样，但保留实际观测时刻与源帧身份。"""
    indices = fit_valid_indices(request)
    if len(indices) <= request.maximum_samples:
        return indices
    positions = np.rint(np.linspace(0, len(indices) - 1, request.maximum_samples)).astype(int)
    return tuple(indices[int(i)] for i in np.unique(positions))


def soft_l1_cost(residual_rad: tuple[float, ...], f_scale_rad: float = DEFAULT_F_SCALE_RAD) -> float:
    """scientific-profiles §4：与SciPy optimiser.cost同尺度，单位rad²。"""
    if not _finite_number(f_scale_rad) or f_scale_rad <= 0 or any(not _finite_number(v) for v in residual_rad):
        raise ValueError("robust cost requires finite residual radians and positive scale")
    residual = np.asarray(residual_rad, dtype=float)
    # hypot避免平方溢出；分母有理化避免小残差的sqrt(1+x)-1消减。
    radius = np.hypot(float(f_scale_rad), residual)
    return float(np.sum((float(f_scale_rad) * residual) * (residual / (radius + f_scale_rad))))


@dataclass(frozen=True)
class ObjectiveEvaluation:
    """failure residual仅供优化器数值接口，status必须随每次求值保存。"""
    status: str
    reason: str | None
    residual_rad: tuple[float, ...]
    cost_rad2: float | None
    prediction: ForwardResult


def evaluate_objective(request: ObjectiveRequest, model: str,
                       parameters: PendulumParameters) -> ObjectiveEvaluation:
    """仅样本点的加权objective；full RMSE必须另用全部共同有效帧。"""
    indices = fit_sample_indices(request)
    times = tuple(request.series.time_release_relative_s[i] for i in indices)
    prediction = simulate_pendulum(model, parameters, request.initial_condition, times, request.integration)
    if prediction.status != "success":
        residual = (INTEGRATION_FAILURE_RESIDUAL_RAD,) * len(indices)
        return ObjectiveEvaluation("failed", prediction.reason or "no_valid_samples", residual, None, prediction)
    residual = tuple(sqrt(request.relative_weights[i]) * (pred - request.series.theta_rad[i])
                     for i, pred in zip(indices, prediction.theta_rad))
    cost = soft_l1_cost(residual, request.f_scale_rad) if request.loss == "soft_l1" else .5*float(np.dot(residual, residual))
    return ObjectiveEvaluation("success", None, residual, cost, prediction)


@dataclass(frozen=True)
class TrajectoryEvaluation:
    """全源区间预测与原始残差；metrics只使用共同QC-valid观测，不使用抽样分母。"""
    status: str
    reason: str | None
    source_indices: tuple[int, ...]
    prediction: ForwardResult
    residual_rad: tuple[float | None, ...]
    rmse_rad: float | None
    weighted_rmse_rad: float | None
    early_rmse_rad: float | None
    late_rmse_rad: float | None


def evaluate_trajectory(request: ObjectiveRequest, model: str,
                        parameters: PendulumParameters) -> TrajectoryEvaluation:
    """缺测位置有模型预测但没有新观测；非有限forward不会缩小评价mask。"""
    indices = tuple(i for i, f in enumerate(request.series.frame_indices)
                    if request.start_frame_index <= f <= request.end_frame_index)
    times = tuple(request.series.time_release_relative_s[i] for i in indices)
    prediction = simulate_pendulum(model, parameters, request.initial_condition, times, request.integration)
    if prediction.status != "success":
        return TrajectoryEvaluation("failed", prediction.reason or "empty_interval", indices,
                                    prediction, (), None, None, None, None)
    residual = tuple(None if request.series.theta_rad[i] is None else pred - request.series.theta_rad[i]
                     for i, pred in zip(indices, prediction.theta_rad))
    valid_positions = tuple(j for j, i in enumerate(indices) if request.series.qc_valid[i])
    if not valid_positions:
        return TrajectoryEvaluation("insufficient_data", "no_valid_observations", indices,
                                    prediction, residual, None, None, None, None)
    valid_residual = np.asarray([residual[j] for j in valid_positions], dtype=float)
    weights = np.asarray([request.relative_weights[indices[j]] for j in valid_positions], dtype=float)
    third = max(1, len(valid_positions) // 3)
    rmse = sqrt(float(np.mean(valid_residual**2)))
    weighted_rmse = sqrt(float(np.mean(weights * valid_residual**2)))
    early = sqrt(float(np.mean(valid_residual[:third]**2)))
    late = sqrt(float(np.mean(valid_residual[-third:]**2)))
    return TrajectoryEvaluation("success", None, indices, prediction, residual,
                                rmse, weighted_rmse, early, late)
