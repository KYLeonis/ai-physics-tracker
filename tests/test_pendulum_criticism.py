"""P4.1：共同拟合输入上的模型批判证据与来源边界。"""

from dataclasses import replace

import pytest

from ai_physics_tracker.domain.angular_analysis import (
    AngularAnalysis,
    AngularSeries,
    LEGACY,
    analyze_angular_series,
    angular_series_digest,
)
from ai_physics_tracker.domain.pendulum_criticism import criticize_pendulum_fits
from ai_physics_tracker.domain.pendulum_fit import FitSettings, fit_pendulum
from ai_physics_tracker.domain.pendulum_ode import (
    M0,
    M1,
    InitialCondition,
    IntegrationSettings,
    ObjectiveRequest,
    PendulumParameters,
    evaluate_trajectory,
    simulate_pendulum,
)


@pytest.fixture(scope="module")
def m1_case():
    truth = PendulumParameters(.015, 40., .02)
    ic = InitialCondition(.55, -.12, "explicit")
    integration = IntegrationSettings(2e-10, 2e-12)
    count, dt = 801, .05
    time_s = tuple(i*dt for i in range(count))
    forward = simulate_pendulum(M1, truth, ic, time_s, integration)
    frames = tuple(i if i < 350 else i+5 for i in range(count))
    series = AngularSeries("a"*64, frames, time_s, forward.theta_rad, (True,)*count, 1/dt)
    request = ObjectiveRequest(series, (1.,)*count, ic, frames[0], frames[-1], .25,
        integration=integration, maximum_samples=500, fit_start_frame_index=frames[40])
    m0 = fit_pendulum(request, M0, FitSettings(starts=((truth.alpha1_s_inv, truth.omega2_s_inv2),)))
    m1 = fit_pendulum(request, M1, FitSettings(starts=((truth.alpha1_s_inv,
        truth.alpha2_rad_inv, truth.omega2_s_inv2),)))
    assert m0.status == m1.status == "success"
    angular = analyze_angular_series(series)
    return request, m0, m1, angular


def test_same_input_reports_rmse_strata_phase_tail_and_distinct_energy_meanings(m1_case):
    request, m0, m1, angular = m1_case
    result = criticize_pendulum_fits(request, m0, m1, angular)

    assert result.comparison.status == "comparable"
    assert result.comparison.rmse_improvement_percent.value > 0
    assert result.objective_digest
    m1_evidence = next(model for model in result.models if model.model == M1)
    assert m1_evidence.residuals.rmse_rad.unit == "rad"
    assert m1_evidence.residuals.valid_count == 761
    assert len(m1_evidence.residuals.points) == 761
    assert m1_evidence.residuals.speed.valid_speed_count > 700
    assert {item.name for item in m1_evidence.residuals.speed.strata} == {"low", "middle", "high"}

    assert m1_evidence.phase.observed_crossing_count > 10
    assert m1_evidence.phase.matched
    assert all(item.segment_end_frame_index <= 349 or item.segment_start_frame_index >= 355
               for item in m1_evidence.phase.matched)
    assert all(item.direction in ("upward", "downward") for item in m1_evidence.phase.matched)
    assert m1_evidence.phase.median_delta_s.unit == "s"

    expected_tail_start = request.series.time_release_relative_s[40] + (
        request.series.time_release_relative_s[-1]-request.series.time_release_relative_s[40])*2/3
    assert m1_evidence.tail.start_s == pytest.approx(expected_tail_start, abs=1e-12)
    assert m1_evidence.tail.period_count >= 10
    assert m1_evidence.tail.q_tail_s_inv2.status == "available"
    assert m1_evidence.tail.source_series_digest == angular_series_digest(request.series)
    assert m1_evidence.length_consistency.fit_q_s_inv2 == pytest.approx(m1.parameters.omega2_s_inv2)
    assert "表观动力学长度" in m1_evidence.length_consistency.interpretation
    assert m1_evidence.length_consistency.apparent_dynamical_length_m.unit == "m"

    assert m1_evidence.energy_dissipation.fit_q_s_inv2 == pytest.approx(m1.parameters.omega2_s_inv2)
    assert "不是对观测能量的吻合度" in m1_evidence.energy_dissipation.interpretation
    assert m1_evidence.energy_dissipation.energy_balance_rmse_s_inv2.value < 3e-4
    assert result.reference_energy_proxy.q_proxy_s_inv2 == pytest.approx(
        request.g_m_s2/request.effective_length_m, abs=1e-12)
    assert "q=g/L" in result.reference_energy_proxy.interpretation
    assert result.reference_energy_proxy.total_energy_count > 700


def test_replaced_fit_outputs_are_rejected_and_single_model_keeps_raw_residuals(m1_case):
    request, m0, m1, _ = m1_case
    poor_parameters = PendulumParameters(m1.parameters.alpha1_s_inv,
                                         m1.parameters.omega2_s_inv2, .35)
    poor_trajectory = evaluate_trajectory(request, M1, poor_parameters)
    forged_fits = (
        replace(m1, parameters=poor_parameters),
        replace(m1, trajectory=poor_trajectory),
        replace(m1, parameters=poor_parameters, trajectory=poor_trajectory),
        replace(m1, selected_start_index=None),
    )
    for forged in forged_fits:
        result = criticize_pendulum_fits(request, m0, forged)
        evidence = next(model for model in result.models if model.model == M1)
        assert evidence.fit_identity_status == "invalid"
        assert evidence.fit_identity_reason == "fit_output_validation_failed"
        assert evidence.residuals.rmse_rad.status == "unavailable"
        assert evidence.phase.status == "unavailable"
        assert evidence.length_consistency.status == "unavailable"
        assert evidence.energy_dissipation.status == "unavailable"
        assert evidence.tail.tail_to_fit_q_difference_percent.status == "unavailable"
        assert result.comparison.status == "not_comparable"

    single = criticize_pendulum_fits(request, m1=m1)
    assert single.comparison.status == "unavailable"
    assert single.comparison.reason == "both_models_required"
    assert single.models[0].residuals.rmse_rad.status == "available"
    assert single.models[0].residuals.speed.reason == "angular_analysis_missing"
    assert single.reference_energy_proxy.reason == "angular_analysis_missing"


def test_fit_readback_validation_does_not_run_optimizer(m1_case, monkeypatch):
    request, m0, m1, _ = m1_case

    def optimizer_must_not_run(*args, **kwargs):
        raise AssertionError("model criticism must not optimize")

    monkeypatch.setattr("ai_physics_tracker.domain.pendulum_fit.least_squares", optimizer_must_not_run)
    result = criticize_pendulum_fits(request, m0, m1)
    assert all(model.fit_identity_status == "valid" for model in result.models)


def test_source_mismatch_and_missing_sg_do_not_hide_raw_residuals(m1_case):
    request, m0, m1, angular = m1_case
    missing_sg = analyze_angular_series(request.series, sg_window=1001)
    result = criticize_pendulum_fits(request, m0, m1, missing_sg, sg_window=1001)
    assert result.models[0].residuals.rmse_rad.status == "available"
    assert result.models[0].residuals.speed.reason == "no_valid_observed_speeds"
    assert result.reference_energy_proxy.reason == "no_total_energy_samples_in_fit_interval"

    wrong_source = replace(angular, source_series_digest="b"*64)
    result = criticize_pendulum_fits(request, m0, m1, wrong_source)
    assert result.models[1].residuals.rmse_rad.status == "available"
    assert result.models[1].residuals.speed.reason == "angular_analysis_source_mismatch"
    assert result.reference_energy_proxy.reason == "angular_analysis_source_mismatch"

    assert any(segment.segment_start_frame_index == 40 and segment.segment_end_frame_index == 349
               for segment in result.models[1].phase.segments)
    assert any(segment.segment_start_frame_index == 355 and segment.segment_end_frame_index == 805
               for segment in result.models[1].phase.segments)


def test_angular_outputs_are_recomputed_with_explicit_sg_settings(m1_case):
    request, m0, _, angular = m1_case
    forged = replace(angular, omega_rad_s=tuple(
        None if value is None else 0. for value in angular.omega_rad_s))
    result = criticize_pendulum_fits(request, m0=m0, angular=forged)
    assert result.reference_energy_proxy.reason == "angular_analysis_output_mismatch"
    assert result.models[0].residuals.speed.reason == "angular_analysis_output_mismatch"
    assert result.models[0].residuals.rmse_rad.status == "available"
    custom = analyze_angular_series(request.series, sg_window=5, sg_polyorder=2)
    checked = criticize_pendulum_fits(request, m0=m0, angular=custom, sg_window=5, sg_polyorder=2)
    assert checked.reference_energy_proxy.status == "available"
    assert checked.models[0].residuals.speed.status == "available"
    mismatch = criticize_pendulum_fits(request, m0=m0, angular=custom)
    assert mismatch.reference_energy_proxy.reason == "angular_analysis_configuration_mismatch"


def test_unsupported_auxiliary_interval_keeps_raw_diagnostics(m1_case):
    request, _, _, _ = m1_case
    legacy_request = replace(request, profile_id=LEGACY, end_frame_index=request.series.frame_indices[400],
        initial_condition=InitialCondition(request.initial_condition.theta0_rad,
                                           request.initial_condition.omega0_rad_s, "archived_toml"))
    fit = fit_pendulum(legacy_request, M0, FitSettings(starts=((.02, 40.),)))
    angular = analyze_angular_series(request.series, profile_id=LEGACY)
    result = criticize_pendulum_fits(legacy_request, m0=fit, angular=angular)
    assert result.reference_energy_proxy.reason == "angular_analysis_configuration_mismatch"
    assert result.models[0].residuals.rmse_rad.status == "available"


def test_different_request_or_nonconverged_fit_cannot_be_ranked(m1_case):
    request, m0, m1, _ = m1_case
    changed_mask = list(request.series.qc_valid)
    changed_mask[100] = False
    changed_time = list(request.series.time_release_relative_s)
    changed_time[100] += 1e-5
    changed_requests = (
        replace(request, relative_weights=(.8,)*len(request.relative_weights)),
        replace(request, series=replace(request.series, qc_valid=tuple(changed_mask))),
        replace(request, initial_condition=InitialCondition(.6, -.12, "explicit")),
        replace(request, series=replace(request.series, time_release_relative_s=tuple(changed_time))),
    )
    for changed in changed_requests:
        result = criticize_pendulum_fits(changed, m0, m1)
        assert result.comparison.status == "not_comparable"
        assert result.comparison.reason == "inputs_or_configuration_differ"
        assert result.models[0].residuals.rmse_rad.status == "unavailable"

    slow_m0 = fit_pendulum(request, M0, FitSettings(max_nfev=1, starts=((.1, 60.),)))
    slow_m1 = fit_pendulum(request, M1,
        FitSettings(max_nfev=1, starts=((.1, .1, 60.),)))
    assert slow_m0.status == slow_m1.status == "nonconverged"
    result = criticize_pendulum_fits(request, slow_m0, slow_m1)
    assert result.comparison.status == "unavailable"
    assert result.comparison.reason == "fit_not_converged_or_failed"
    assert all(model.fit_identity_status == "valid" for model in result.models)
    assert result.models[0].residuals.rmse_rad.status == "available"


def test_request_and_angular_inputs_are_typed():
    with pytest.raises(ValueError, match="ObjectiveRequest"):
        criticize_pendulum_fits(None, m0=object())
    with pytest.raises(ValueError, match="at least one typed PendulumFit"):
        series = AngularSeries("a"*64, (0, 1), (0., 1.), (.1, .1), (True, True), 1.)
        request = ObjectiveRequest(series, (1., 1.), InitialCondition(.1, 0., "explicit"),
            0, 1, .25)
        criticize_pendulum_fits(request, m0=object())
