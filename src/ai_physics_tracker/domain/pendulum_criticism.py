"""领域层：按同一拟合输入汇总残差、相位与物理一致性证据；无 Qt/I/O。"""

from dataclasses import asdict, dataclass
import json
from math import cos, isfinite, sqrt

import numpy as np

from ai_physics_tracker.domain.angular_analysis import (
    AngularAnalysis,
    AngularSeries,
    Crossing,
    PeriodAnalysis,
    TAIL_MIN_PERIODS,
    SG_WINDOW,
    SG_POLYORDER,
    analyze_angular_series,
    angular_series_digest,
    period_analysis,
)
from ai_physics_tracker.domain.pendulum_energy import reference_energy
from ai_physics_tracker.domain.pendulum_fit import (
    FitSettings,
    PendulumFit,
    compare_fits,
    validate_saved_fit,
)
from ai_physics_tracker.domain.pendulum_ode import (
    M0,
    M1,
    ObjectiveRequest,
    objective_config,
    objective_request_digest,
)
from ai_physics_tracker.domain.types import canonical_json_digest


@dataclass(frozen=True)
class MetricEvidence:
    """一个带单位的数值证据；缺值必须附具体原因。"""

    status: str
    reason: str | None
    value: float | None
    unit: str
    count: int


@dataclass(frozen=True)
class ResidualPoint:
    frame_index: int
    time_s: float
    residual_rad: float


@dataclass(frozen=True)
class SpeedStratum:
    name: str
    count: int
    rmse_rad: MetricEvidence


@dataclass(frozen=True)
class SpeedEvidence:
    status: str
    reason: str | None
    valid_speed_count: int
    quantiles_rad_s: tuple[float, float] | None
    strata: tuple[SpeedStratum, ...]


@dataclass(frozen=True)
class ResidualEvidence:
    status: str
    reason: str | None
    valid_count: int
    rmse_rad: MetricEvidence
    early_rmse_rad: MetricEvidence
    late_rmse_rad: MetricEvidence
    points: tuple[ResidualPoint, ...]
    speed: SpeedEvidence


@dataclass(frozen=True)
class PhaseCrossingDelta:
    segment_start_frame_index: int
    segment_end_frame_index: int
    direction: str
    ordinal: int
    observed_time_s: float
    predicted_time_s: float
    delta_s: float


@dataclass(frozen=True)
class PhaseSegmentEvidence:
    segment_start_frame_index: int
    segment_end_frame_index: int
    direction: str
    observed_count: int
    predicted_count: int
    matched_count: int
    status: str
    reason: str | None


@dataclass(frozen=True)
class PhaseEvidence:
    status: str
    reason: str | None
    observed_crossing_count: int
    predicted_crossing_count: int
    segments: tuple[PhaseSegmentEvidence, ...]
    matched: tuple[PhaseCrossingDelta, ...]
    median_delta_s: MetricEvidence
    maximum_absolute_delta_s: MetricEvidence


@dataclass(frozen=True)
class LengthConsistencyEvidence:
    status: str
    reason: str | None
    fit_q_s_inv2: float | None
    physical_q_s_inv2: float | None
    fit_to_g_over_l_ratio: MetricEvidence
    apparent_dynamical_length_m: MetricEvidence
    apparent_length_difference_percent: MetricEvidence
    interpretation: str


@dataclass(frozen=True)
class TailEvidence:
    start_s: float
    end_s: float
    period_count: int
    q_tail_s_inv2: MetricEvidence
    tail_to_fit_q_difference_percent: MetricEvidence
    apparent_dynamical_length_m: MetricEvidence
    source_time_digest: str
    source_series_digest: str


@dataclass(frozen=True)
class EnergyDissipationEvidence:
    """拟合q下的e*=ω²/2+q(1-cosθ)、dE/dt=−a₁ω²−a₂|ω|³；不表示与观测能量吻合。"""

    status: str
    reason: str | None
    fit_q_s_inv2: float | None
    state_count: int
    energy_min_s_inv2: MetricEvidence
    energy_max_s_inv2: MetricEvidence
    maximum_energy_increase_s_inv2: MetricEvidence
    energy_balance_rmse_s_inv2: MetricEvidence
    maximum_dissipation_rate_s_inv3: MetricEvidence
    interpretation: str = "使用本模型拟合q与ODE预测状态；这是能量耗散恒等式诊断，不是对观测能量的吻合度。"


@dataclass(frozen=True)
class ReferenceEnergyEvidence:
    status: str
    reason: str | None
    profile_id: str | None
    angular_input_digest: str | None
    q_proxy_s_inv2: float | None
    total_energy_count: int
    total_energy_min_s_inv2: MetricEvidence
    total_energy_max_s_inv2: MetricEvidence
    interpretation: str = "参考能量使用物理q=g/L；与模型拟合q下的specific-energy证据分开。"


@dataclass(frozen=True)
class ModelCriticism:
    model: str
    fit_status: str
    fit_identity_status: str
    fit_identity_reason: str | None
    residuals: ResidualEvidence
    phase: PhaseEvidence
    length_consistency: LengthConsistencyEvidence
    tail: TailEvidence
    energy_dissipation: EnergyDissipationEvidence


@dataclass(frozen=True)
class FitComparisonEvidence:
    status: str
    reason: str | None
    common_digest: str | None
    rmse_improvement_percent: MetricEvidence


@dataclass(frozen=True)
class PendulumCriticism:
    objective_digest: str
    comparison: FitComparisonEvidence
    reference_energy_proxy: ReferenceEnergyEvidence
    models: tuple[ModelCriticism, ...]


def _metric(value: float, unit: str, count: int) -> MetricEvidence:
    return MetricEvidence("available", None, float(value), unit, count)


def _unavailable(reason: str, unit: str, count: int = 0) -> MetricEvidence:
    return MetricEvidence("unavailable", reason, None, unit, count)


def _request_fit_problem(request: ObjectiveRequest, fit: PendulumFit) -> str | None:
    """复核typed fit仍引用给定request和它保存的比较配置。"""
    if not isinstance(fit.config, dict) or fit.config.get("objective") != objective_config(request):
        return "different_objective_request"
    settings = fit.config.get("settings")
    if not isinstance(settings, dict) or "starts" not in settings:
        return "invalid_fit_configuration"
    try:
        expected_comparability = canonical_json_digest({
            "objective": objective_request_digest(request),
            "settings": {key: value for key, value in settings.items() if key != "starts"},
        })
    except (TypeError, ValueError):
        return "invalid_fit_configuration"
    if fit.comparability_digest != expected_comparability:
        return "inputs_or_configuration_differ"
    if fit.status == "insufficient_data":
        # 没有运行起点诊断，无法从结果重建digest中的resolved starts；该状态也不能参与排名。
        return None
    try:
        starts = tuple(diagnostic.start for diagnostic in fit.starts)
        expected_input = canonical_json_digest({
            "request": objective_request_digest(request),
            "model": fit.model,
            "config": fit.config,
            "lower": list(fit.lower),
            "upper": list(fit.upper),
            "starts": starts,
            "seed": asdict(fit.seed),
        })
    except (AttributeError, TypeError, ValueError):
        return "invalid_fit_identity"
    return None if fit.input_digest == expected_input else "fit_input_identity_mismatch"


def _fit_settings(fit: PendulumFit) -> FitSettings:
    """Rebuild the saved optimizer settings, including JSON list representations."""
    if not isinstance(fit.config, dict) or not isinstance(fit.config.get("settings"), dict):
        raise ValueError("invalid_fit_configuration")
    values = dict(fit.config["settings"])
    for name in ("alpha1_bounds", "alpha2_bounds", "omega2_bounds"):
        if values.get(name) is not None:
            values[name] = tuple(values[name])
    if values.get("starts") is not None:
        values["starts"] = tuple(tuple(start) for start in values["starts"])
    return FitSettings(**values)


def _validated_fit(request: ObjectiveRequest, fit: PendulumFit,
                   warm_start: PendulumFit | None) -> tuple[PendulumFit, str | None]:
    """Readback-validate parameters, selected start, objective and trajectory without optimizing."""
    try:
        settings = _fit_settings(fit)
        saved = json.loads(json.dumps(asdict(fit), allow_nan=False))
        checked = validate_saved_fit(request, fit.model, settings, saved, warm_start=warm_start)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        return fit, "fit_output_validation_failed"
    return checked, None


def _trajectory_problem(request: ObjectiveRequest, fit: PendulumFit) -> str | None:
    trajectory = fit.trajectory
    if trajectory is None or trajectory.status != "success":
        return "fit_trajectory_unavailable"
    if fit.status == "success" and fit.parameters is None:
        return "fit_parameters_unavailable"
    expected_indices = tuple(
        i for i, frame in enumerate(request.series.frame_indices)
        if request.start_frame_index <= frame <= request.end_frame_index
    )
    prediction = trajectory.prediction
    if (trajectory.source_indices != expected_indices or prediction.status != "success"
            or len(prediction.theta_rad) != len(expected_indices)
            or len(prediction.omega_rad_s) != len(expected_indices)
            or len(trajectory.residual_rad) != len(expected_indices)
            or any(not isfinite(value) for value in prediction.theta_rad+prediction.omega_rad_s)):
        return "fit_trajectory_grid_mismatch"
    for position, index in enumerate(expected_indices):
        observed = request.series.theta_rad[index]
        residual = trajectory.residual_rad[position]
        predicted = prediction.theta_rad[position]
        if observed is None:
            if residual is not None:
                return "fit_residual_observation_mismatch"
        elif (residual is None or not isfinite(residual)
              or not np.isclose(residual, predicted-observed, rtol=1e-10, atol=1e-12)):
            return "fit_residual_observation_mismatch"
    if fit.status == "success":
        valid_residuals = [trajectory.residual_rad[position]
            for position, index in enumerate(expected_indices) if request.series.qc_valid[index]]
        if not valid_residuals or trajectory.rmse_rad is None or not np.isclose(
                trajectory.rmse_rad, sqrt(float(np.mean(np.square(valid_residuals)))),
                rtol=1e-10, atol=1e-12):
            return "fit_residual_metrics_mismatch"
    return None


def _speed_evidence(
    request: ObjectiveRequest,
    indices: tuple[int, ...],
    residual_by_index: dict[int, float],
    angular: AngularAnalysis | None,
    angular_problem: str | None,
) -> SpeedEvidence:
    unavailable_strata = tuple(SpeedStratum(
        name, 0, _unavailable(angular_problem or "angular_analysis_missing", "rad", 0)
    ) for name in ("low", "middle", "high"))
    if angular is None or angular_problem is not None:
        reason = angular_problem or "angular_analysis_missing"
        return SpeedEvidence("unavailable", reason, 0, None, unavailable_strata)

    valid = [i for i in indices if request.series.qc_valid[i]
             and angular.omega_reasons[i] is None and angular.omega_rad_s[i] is not None]
    if not valid:
        return SpeedEvidence("unavailable", "no_valid_observed_speeds", 0, None,
                             tuple(SpeedStratum(name, 0, _unavailable("empty_speed_stratum", "rad", 0))
                                   for name in ("low", "middle", "high")))
    speeds = np.asarray([abs(angular.omega_rad_s[i]) for i in valid], dtype=float)
    lower, upper = map(float, np.quantile(speeds, (1/3, 2/3), method="linear"))
    buckets: dict[str, list[float]] = {"low": [], "middle": [], "high": []}
    for index, speed in zip(valid, speeds):
        if speed >= upper:
            buckets["high"].append(residual_by_index[index])
        elif speed <= lower:
            buckets["low"].append(residual_by_index[index])
        else:
            buckets["middle"].append(residual_by_index[index])
    strata = tuple(SpeedStratum(name, len(values),
        _metric(sqrt(float(np.mean(np.square(values)))), "rad", len(values))
        if values else _unavailable("empty_speed_stratum", "rad"))
        for name, values in buckets.items())
    return SpeedEvidence("available", None, len(valid), (lower, upper), strata)


def _residual_evidence(
    request: ObjectiveRequest,
    fit: PendulumFit,
    angular: AngularAnalysis | None,
    angular_problem: str | None,
) -> ResidualEvidence:
    unit = "rad"
    unavailable_speed = _speed_evidence(request, (), {}, angular, angular_problem)
    problem = _trajectory_problem(request, fit)
    if problem is not None:
        return ResidualEvidence("unavailable", problem, 0,
            _unavailable(problem, unit), _unavailable(problem, unit),
            _unavailable(problem, unit), (), unavailable_speed)

    indices = fit.trajectory.source_indices
    valid_indices = tuple(i for i in indices if request.series.qc_valid[i])
    residuals = {i: float(fit.trajectory.residual_rad[position])
                 for position, i in enumerate(indices)
                 if request.series.qc_valid[i]}
    points = tuple(ResidualPoint(request.series.frame_indices[i],
                                 request.series.time_release_relative_s[i], residuals[i])
                   for i in valid_indices)
    values = [residuals[i] for i in valid_indices]
    if not values:
        missing = _unavailable("no_valid_observations", unit)
        return ResidualEvidence("unavailable", "no_valid_observations", 0,
                                missing, missing, missing, (), unavailable_speed)
    third = max(1, len(values)//3)
    all_rmse = sqrt(float(np.mean(np.square(values))))
    early_rmse = sqrt(float(np.mean(np.square(values[:third]))))
    late_rmse = sqrt(float(np.mean(np.square(values[-third:]))))
    return ResidualEvidence("available", None, len(values),
        _metric(all_rmse, unit, len(values)), _metric(early_rmse, unit, third),
        _metric(late_rmse, unit, third), points,
        _speed_evidence(request, indices, residuals, angular, angular_problem))


def _phase_evidence(request: ObjectiveRequest, fit: PendulumFit) -> PhaseEvidence:
    problem = _trajectory_problem(request, fit)
    if problem is not None:
        missing = _unavailable(problem, "s")
        return PhaseEvidence("unavailable", problem, 0, 0, (), (), missing, missing)
    indices = fit.trajectory.source_indices
    source = request.series
    frame_indices = tuple(source.frame_indices[i] for i in indices)
    times = tuple(source.time_release_relative_s[i] for i in indices)
    mask = tuple(source.qc_valid[i] for i in indices)
    if any(abs(value) > np.pi for value in fit.trajectory.prediction.theta_rad):
        reason = "predicted_angle_outside_nonrotational_phase_domain"
        missing = _unavailable(reason, "s")
        return PhaseEvidence("unavailable", reason, 0, 0, (), (), missing, missing)
    observed_series = AngularSeries(source.upstream_digest, frame_indices, times,
        tuple(source.theta_rad[i] for i in indices), mask, source.fps_nominal)
    predicted_series = AngularSeries(source.upstream_digest, frame_indices, times,
        fit.trajectory.prediction.theta_rad, mask, source.fps_nominal)
    start_s, end_s = times[0], times[-1]
    observed = period_analysis(observed_series, mask, start_s=start_s, end_s=end_s,
                               profile_id=request.profile_id)
    predicted = period_analysis(predicted_series, mask, start_s=start_s, end_s=end_s,
                                profile_id=request.profile_id)

    def grouped(periods: PeriodAnalysis) -> dict[tuple[int, int, str], list[Crossing]]:
        result: dict[tuple[int, int, str], list[Crossing]] = {}
        for crossing in periods.crossings:
            key = (crossing.segment_start_frame_index, crossing.segment_end_frame_index,
                   crossing.direction)
            result.setdefault(key, []).append(crossing)
        return result

    observed_groups = grouped(observed)
    predicted_groups = grouped(predicted)
    segment_rows = []
    matched = []
    for key in sorted(set(observed_groups) | set(predicted_groups)):
        left = observed_groups.get(key, [])
        right = predicted_groups.get(key, [])
        count = min(len(left), len(right))
        if len(left) == len(right):
            status, reason = "matched", None
        elif count:
            status, reason = "partial", "crossing_count_mismatch"
        else:
            status, reason = "unmatched", "missing_observed_or_predicted_crossings"
        segment_rows.append(PhaseSegmentEvidence(*key, len(left), len(right), count, status, reason))
        matched.extend(PhaseCrossingDelta(*key, ordinal, observed_crossing.time_s,
            predicted_crossing.time_s, predicted_crossing.time_s-observed_crossing.time_s)
            for ordinal, (observed_crossing, predicted_crossing) in enumerate(zip(left, right)))
    matched.sort(key=lambda item: (item.observed_time_s, item.direction))
    observed_count = len(observed.crossings)
    predicted_count = len(predicted.crossings)
    if not segment_rows:
        status, reason = "unavailable", "no_zero_crossings_in_fit_interval"
    elif any(segment.status == "partial" or segment.status == "unmatched" for segment in segment_rows):
        status, reason = ("partial", "some_source_segments_or_directions_unmatched") if matched else (
            "unmatched", "no_matching_source_segment_and_direction")
    else:
        status, reason = "matched", None
    deltas = [item.delta_s for item in matched]
    median_delta = _metric(float(np.median(deltas)), "s", len(deltas)) if deltas else _unavailable(
        "no_matched_zero_crossings", "s")
    maximum_delta = _metric(max(map(abs, deltas)), "s", len(deltas)) if deltas else _unavailable(
        "no_matched_zero_crossings", "s")
    return PhaseEvidence(status, reason, observed_count, predicted_count, tuple(segment_rows),
                         tuple(matched), median_delta, maximum_delta)


def _length_consistency(request: ObjectiveRequest, fit: PendulumFit,
                        fit_problem: str | None = None) -> LengthConsistencyEvidence:
    q_fit = None if fit.parameters is None else fit.parameters.omega2_s_inv2
    physical_q = request.g_m_s2/request.effective_length_m
    explanation = "q 是集总惯性参数；g/q 仅为表观动力学长度，不是测得的质心长度"
    if fit_problem is not None or q_fit is None or not isfinite(q_fit) or q_fit <= 0:
        reason = fit_problem or "fit_parameters_unavailable"
        q_fit = None if fit_problem is not None else q_fit
        return LengthConsistencyEvidence("unavailable", reason, q_fit, physical_q,
            _unavailable(reason, "ratio"), _unavailable(reason, "m"), _unavailable(reason, "%"), explanation)
    apparent_length = request.g_m_s2/q_fit
    return LengthConsistencyEvidence("available", None, q_fit, physical_q,
        _metric(q_fit/physical_q, "ratio", 1), _metric(apparent_length, "m", 1),
        _metric(100*(apparent_length/request.effective_length_m-1), "%", 1), explanation)


def _tail_analysis(request: ObjectiveRequest) -> tuple[float, float, PeriodAnalysis]:
    series = request.series
    indices = tuple(i for i, frame in enumerate(series.frame_indices)
                    if request.start_frame_index <= frame <= request.end_frame_index)
    first_time = series.time_release_relative_s[indices[0]]
    last_time = series.time_release_relative_s[indices[-1]]
    tail_start = first_time + (last_time-first_time)*2/3
    mask = tuple(request.start_frame_index <= frame <= request.end_frame_index
                 and series.qc_valid[i] and series.time_release_relative_s[i] > tail_start
                 for i, frame in enumerate(series.frame_indices))
    analysis = period_analysis(series, mask, start_s=tail_start, end_s=last_time,
        profile_id=request.profile_id, minimum_periods=TAIL_MIN_PERIODS)
    return tail_start, last_time, analysis


def _tail_evidence(request: ObjectiveRequest, fit: PendulumFit,
                   tail_start: float, tail_end: float, analysis: PeriodAnalysis,
                   fit_problem: str | None = None) -> TailEvidence:
    count = len(analysis.periods)
    reason = analysis.reason or "tail_fit_q_unavailable"
    q_tail = (_metric(analysis.omega2_mean_s_inv2, "s^-2", count)
              if analysis.omega2_mean_s_inv2 is not None else _unavailable(reason, "s^-2", count))
    q_fit = None if fit_problem is not None or fit.parameters is None else fit.parameters.omega2_s_inv2
    if q_tail.value is None:
        difference = _unavailable(reason, "%", count)
        apparent = _unavailable(reason, "m", count)
    elif q_fit is None or q_fit <= 0:
        difference = _unavailable(fit_problem or "fit_parameters_unavailable", "%", count)
        apparent = _metric(request.g_m_s2/q_tail.value, "m", count)
    else:
        difference = _metric(100*(q_tail.value/q_fit-1), "%", count)
        apparent = _metric(request.g_m_s2/q_tail.value, "m", count)
    return TailEvidence(tail_start, tail_end, count, q_tail, difference, apparent,
        analysis.source_time_digest, angular_series_digest(request.series))


def _energy_dissipation(request: ObjectiveRequest, fit: PendulumFit,
                        fit_problem: str | None = None) -> EnergyDissipationEvidence:
    problem = _trajectory_problem(request, fit)
    problem = fit_problem or problem
    if problem is not None or fit.parameters is None:
        reason = problem or "fit_parameters_unavailable"
        return EnergyDissipationEvidence("unavailable", reason,
            None if problem is not None or fit.parameters is None else fit.parameters.omega2_s_inv2, 0,
            *(_unavailable(reason, unit) for unit in ("s^-2", "s^-2", "s^-2", "s^-2", "s^-3")))
    theta = fit.trajectory.prediction.theta_rad
    omega = fit.trajectory.prediction.omega_rad_s
    q = fit.parameters.omega2_s_inv2
    energy = tuple(.5*w*w + q*(1-cos(value)) for value, w in zip(theta, omega))
    power = tuple(fit.parameters.alpha1_s_inv*w*w
                  + fit.parameters.alpha2_rad_inv*abs(w)**3 for w in omega)
    times = tuple(request.series.time_release_relative_s[i] for i in fit.trajectory.source_indices)
    balances = tuple((energy[i+1]-energy[i])
                     + (times[i+1]-times[i])*(power[i+1]+power[i])/2
                     for i in range(len(energy)-1))
    increases = tuple(max(0., energy[i+1]-energy[i]) for i in range(len(energy)-1))
    return EnergyDissipationEvidence("available", None, q, len(energy),
        _metric(min(energy), "s^-2", len(energy)), _metric(max(energy), "s^-2", len(energy)),
        _metric(max(increases, default=0.), "s^-2", len(increases)),
        _metric(sqrt(float(np.mean(np.square(balances)))) if balances else 0., "s^-2", len(balances)),
        _metric(max(power, default=0.), "s^-3", len(power)))


def _angular_problem(request: ObjectiveRequest, angular: AngularAnalysis | None,
                     sg_window: int, sg_polyorder: int) -> str | None:
    if angular is None:
        return "angular_analysis_missing"
    if angular.source_series_digest != angular_series_digest(request.series):
        return "angular_analysis_source_mismatch"
    n = len(request.series.frame_indices)
    if any(len(values) != n for values in (angular.omega_rad_s, angular.omega_reasons, angular.edge_window)):
        return "angular_analysis_length_mismatch"
    if any(value is not None and (type(value) not in (int, float) or not isfinite(value))
           for value in angular.omega_rad_s):
        return "angular_analysis_has_nonfinite_speed"
    if any(reason is not None and not isinstance(reason, str) for reason in angular.omega_reasons):
        return "angular_analysis_has_invalid_speed_reason"
    if any(type(flag) is not bool for flag in angular.edge_window):
        return "angular_analysis_has_invalid_edge_flags"
    # 摘要标识输入，不证明输出；按显式SG配置重算廉价辅助量，不运行拟合。
    try:
        expected = analyze_angular_series(request.series, profile_id=request.profile_id,
            end_frame_index=request.end_frame_index, sg_window=sg_window, sg_polyorder=sg_polyorder)
    except ValueError:
        return "angular_analysis_configuration_mismatch"
    if angular.input_digest != expected.input_digest:
        return "angular_analysis_configuration_mismatch"
    if angular != expected:
        return "angular_analysis_output_mismatch"
    return None


def _reference_energy_evidence(request: ObjectiveRequest, angular: AngularAnalysis | None,
                               angular_problem: str | None) -> ReferenceEnergyEvidence:
    if angular is None or angular_problem is not None:
        reason = angular_problem or "angular_analysis_missing"
        missing = _unavailable(reason, "s^-2")
        return ReferenceEnergyEvidence("unavailable", reason, None, None, None, 0, missing, missing)
    energy = reference_energy(request.series, angular, request.effective_length_m, request.g_m_s2)
    selected = tuple(i for i, frame in enumerate(request.series.frame_indices)
                     if request.start_frame_index <= frame <= request.end_frame_index)
    values = tuple(energy.total_s_inv2[i] for i in selected if energy.total_s_inv2[i] is not None)
    if values:
        minimum = _metric(min(values), "s^-2", len(values))
        maximum = _metric(max(values), "s^-2", len(values))
        status, reason = "available", None
    else:
        reason = "no_total_energy_samples_in_fit_interval"
        minimum = _unavailable(reason, "s^-2")
        maximum = _unavailable(reason, "s^-2")
        status = "unavailable"
    return ReferenceEnergyEvidence(status, reason, angular.profile_id, angular.input_digest,
        energy.q_s_inv2, len(values), minimum, maximum)


def _comparison(request: ObjectiveRequest, fits: dict[str, PendulumFit],
                residuals: dict[str, ResidualEvidence], problems: dict[str, str | None]) -> FitComparisonEvidence:
    missing = _unavailable("both_models_required", "%")
    if M0 not in fits or M1 not in fits:
        return FitComparisonEvidence("unavailable", "both_models_required", None, missing)
    m0, m1 = fits[M0], fits[M1]
    if problems[M0] is not None or problems[M1] is not None:
        reason = problems[M0] or problems[M1] or "fit_input_mismatch"
        return FitComparisonEvidence("not_comparable", reason, None, _unavailable(reason, "%"))
    if m0.comparability_digest != m1.comparability_digest:
        reason = "inputs_or_configuration_differ"
        return FitComparisonEvidence("not_comparable", reason, None, _unavailable(reason, "%"))
    common_digest = m0.comparability_digest
    if m0.status != "success" or m1.status != "success":
        reason = "fit_not_converged_or_failed"
        return FitComparisonEvidence("unavailable", reason, common_digest,
                                     _unavailable(reason, "%"))
    if (m0.trajectory is None or m1.trajectory is None
            or residuals[M0].rmse_rad.value is None or residuals[M1].rmse_rad.value is None):
        reason = "fit_trajectory_unavailable"
        return FitComparisonEvidence("unavailable", reason, common_digest,
                                     _unavailable(reason, "%"))
    # 保持P3公开比较语义，包括零RMSE分母与相同comparability digest守卫。
    existing = compare_fits(m0, m1)
    if existing.status != "comparable":
        reason = existing.reason or "fit_comparison_unavailable"
        return FitComparisonEvidence("unavailable", reason, common_digest,
                                     _unavailable(reason, "%"))
    value = 100*(residuals[M0].rmse_rad.value-residuals[M1].rmse_rad.value)/residuals[M0].rmse_rad.value
    return FitComparisonEvidence("comparable", None, common_digest,
                                 _metric(value, "%", min(residuals[M0].valid_count,
                                                          residuals[M1].valid_count)))


def criticize_pendulum_fits(
    request: ObjectiveRequest,
    m0: PendulumFit | None = None,
    m1: PendulumFit | None = None,
    angular: AngularAnalysis | None = None,
    *,
    sg_window: int = SG_WINDOW,
    sg_polyorder: int = SG_POLYORDER,
) -> PendulumCriticism:
    """汇总只读批判证据；不重新优化，也不把较低RMSE解释为模型胜出。"""
    if not isinstance(request, ObjectiveRequest):
        raise ValueError("criticism requires a validated ObjectiveRequest")
    supplied = tuple(fit for fit in (m0, m1) if fit is not None)
    if not supplied or any(not isinstance(fit, PendulumFit) for fit in supplied):
        raise ValueError("criticism requires at least one typed PendulumFit")
    input_fits = {}
    for expected_model, fit in ((M0, m0), (M1, m1)):
        if fit is None:
            continue
        if fit.model != expected_model:
            raise ValueError(f"{expected_model} slot requires a {expected_model} fit")
        input_fits[expected_model] = fit
    if angular is not None and not isinstance(angular, AngularAnalysis):
        raise ValueError("angular evidence must be a typed AngularAnalysis")

    angular_problem = _angular_problem(request, angular, sg_window, sg_polyorder)
    tail_start, tail_end, tail_analysis = _tail_analysis(request)
    fits = {}
    problems = {}
    for model in (M0, M1):
        fit = input_fits.get(model)
        if fit is None:
            continue
        problem = _request_fit_problem(request, fit)
        warm_start = None
        if problem is None:
            try:
                settings = _fit_settings(fit)
            except (AttributeError, KeyError, TypeError, ValueError):
                problem = "invalid_fit_configuration"
            else:
                source_m0 = input_fits.get(M0)
                if (model == M1 and settings.starts is None and source_m0 is not None
                        and fit.comparability_digest == source_m0.comparability_digest):
                    if problems.get(M0) is not None:
                        problem = "warm_start_fit_unavailable"
                    else:
                        warm_start = fits[M0]
        if problem is None:
            fit, problem = _validated_fit(request, fit, warm_start)
        fits[model] = fit
        problems[model] = problem
    models = []
    residual_by_model = {}
    for model in (M0, M1):
        fit = fits.get(model)
        if fit is None:
            continue
        problem = problems[model]
        if problem is not None:
            residual = ResidualEvidence("unavailable", problem, 0,
                _unavailable(problem, "rad"), _unavailable(problem, "rad"),
                _unavailable(problem, "rad"), (),
                _speed_evidence(request, (), {}, angular, angular_problem))
            phase = PhaseEvidence("unavailable", problem, 0, 0, (), (),
                _unavailable(problem, "s"), _unavailable(problem, "s"))
        else:
            residual = _residual_evidence(request, fit, angular, angular_problem)
            phase = _phase_evidence(request, fit)
        residual_by_model[model] = residual
        tail = _tail_evidence(request, fit, tail_start, tail_end, tail_analysis, problem)
        models.append(ModelCriticism(model, fit.status,
            "valid" if problem is None else "invalid", problem, residual, phase,
            _length_consistency(request, fit, problem), tail,
            _energy_dissipation(request, fit, problem)))
    return PendulumCriticism(objective_request_digest(request),
        _comparison(request, fits, residual_by_model, problems),
        _reference_energy_evidence(request, angular, angular_problem), tuple(models))
