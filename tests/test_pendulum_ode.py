"""P3.1：解析/耗散identity、真实时间与初态、冻结E2，不重建expected。"""

import csv
from dataclasses import replace
import gzip
import json
from math import cos, degrees, pi, radians, sin, sqrt
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.integrate import simpson

from ai_physics_tracker.domain.angular_analysis import AngularSeries, LEGACY
from ai_physics_tracker.domain.pendulum_ode import (
    M0, M1, InitialCondition, IntegrationSettings, ObjectiveRequest,
    PendulumParameters, evaluate_objective, evaluate_trajectory, fit_eligibility, fit_sample_indices,
    objective_request_digest, pendulum_rhs, resolve_student_initial_condition,
    simulate_pendulum, soft_l1_cost,
)

GOLDEN = Path(__file__).resolve().parents[1] / "publication/evidence/golden"


def _request(count=101, dt=.1, *, release=0):
    series = AngularSeries("a" * 64, tuple(range(count)),
        tuple((i-release)*dt for i in range(count)), (.2,)*count, (True,)*count, 1/dt)
    return ObjectiveRequest(series, (1.,)*count, InitialCondition(.2, 0., "explicit"),
                            release, count-1, .25)


def test_fixed_ic_linear_limit_nonuniform_times_and_first_observation_after_zero():
    times = (0., .003, .07, .2, 1., 2., 4.1)
    ic = InitialCondition(.65, -.3, "explicit")
    parameters = PendulumParameters(.03, 40.)
    m0 = simulate_pendulum(M0, parameters, ic, times)
    m1 = simulate_pendulum(M1, parameters, ic, times)
    assert m0.status == m1.status == "success"
    np.testing.assert_allclose(m0.theta_rad, m1.theta_rad, atol=1e-12, rtol=1e-12)
    assert m0.theta_rad[0] == pytest.approx(ic.theta0_rad, abs=1e-14)
    assert m0.omega_rad_s[0] == pytest.approx(ic.omega0_rad_s, abs=1e-14)
    after = simulate_pendulum(M0, parameters, ic, times[2:])
    np.testing.assert_allclose(after.theta_rad, m0.theta_rad[2:], atol=1e-12, rtol=1e-12)
    assert abs(after.theta_rad[0]-ic.theta0_rad) > .01


def test_small_angle_known_analytic_limit_with_nonzero_omega():
    theta0, omega0, q = 1e-5, -2e-5, 40.
    times = tuple(map(float, np.linspace(0., 3., 151)))
    result = simulate_pendulum(M0, PendulumParameters(0., q),
        InitialCondition(theta0, omega0, "explicit"), times, IntegrationSettings(1e-11, 1e-14))
    expected = [theta0*cos(sqrt(q)*t)+omega0/sqrt(q)*sin(sqrt(q)*t) for t in times]
    np.testing.assert_allclose(result.theta_rad, expected, atol=1e-12, rtol=1e-8)


@pytest.mark.parametrize("alpha1,alpha2", [(0., 0.), (.03, 0.), (.03, .02)])
def test_energy_balance_matches_integrated_dissipation(alpha1, alpha2):
    times = tuple(float(t) for t in np.linspace(0., 10., 6001))
    q = 40.
    result = simulate_pendulum(M1, PendulumParameters(alpha1, q, alpha2),
        InitialCondition(.8, .2, "explicit"), times, IntegrationSettings(2e-10, 2e-12))
    theta, omega = np.asarray(result.theta_rad), np.asarray(result.omega_rad_s)
    energy = omega**2/2+q*(1-np.cos(theta))
    power = alpha1*omega**2+alpha2*np.abs(omega)**3
    assert energy[-1]-energy[0]+simpson(power, x=times) == pytest.approx(0., abs=2e-7)
    if alpha1 == alpha2 == 0:
        np.testing.assert_allclose(energy, energy[0], atol=2e-7, rtol=0)
    else:
        assert energy[-1] < energy[0]


def test_rest_initial_condition_is_circular_median_of_exact_pre_release_qc_frames():
    request = _request(release=7)
    angles = list(request.series.theta_rad)
    angles[2:7] = [3.12, -3.13, 3.13, -3.14, 3.14]
    series = replace(request.series, theta_rad=tuple(angles))
    ic = resolve_student_initial_condition(series, 7, rest_confirmed=True)
    assert ic.source == "pre_release_rest" and ic.support_frames == (2, 3, 4, 5, 6)
    assert ic.theta0_rad == pytest.approx(3.14, abs=1e-12)
    assert ic.omega0_rad_s == pytest.approx(0., abs=1e-14)
    assert replace(request, series=series, initial_condition=ic).initial_condition is ic
    assert resolve_student_initial_condition(series, 7, rest_confirmed=False) is None
    qc = list(series.qc_valid); qc[4] = False
    assert resolve_student_initial_condition(replace(series, qc_valid=tuple(qc)), 7, rest_confirmed=True) is None
    with pytest.raises(ValueError, match="current pre-release"):
        replace(request, series=replace(series, qc_valid=tuple(qc)), initial_condition=ic)
    with pytest.raises(ValueError, match="precedes|precede"):
        replace(request, initial_condition=ic, release_frame_index=8,
                series=replace(request.series, time_release_relative_s=tuple(t-.1 for t in request.series.time_release_relative_s)))


def test_missing_pre_release_or_moving_release_needs_explicit_ic_and_explicit_wins():
    series = _request().series
    assert resolve_student_initial_condition(series, 0, rest_confirmed=True) is None
    explicit = InitialCondition(-.7, 1.2, "explicit")
    assert resolve_student_initial_condition(series, 0, rest_confirmed=False, explicit=explicit) is explicit
    with pytest.raises(ValueError, match="boolean"):
        resolve_student_initial_condition(series, 0, rest_confirmed="False")


def test_eligibility_counts_missing_frames_with_ceil_and_physical_span():
    request = _request()
    qc = (True,)*50+(False,)*51
    insufficient = fit_eligibility(replace(request, series=replace(request.series, qc_valid=qc)))
    assert insufficient.valid_count == 50 and insufficient.required_count == 51
    assert insufficient.reasons == ("insufficient_valid_frames",)
    qc = (True,)*51+(False,)*50
    assert fit_eligibility(replace(request, series=replace(request.series, qc_valid=qc))).status == "ready"
    assert fit_eligibility(_request(49)).required_count == 50
    assert fit_eligibility(_request(50)).status == "ready"
    assert "insufficient_valid_time_span" in fit_eligibility(_request(101, .001)).reasons
    q = request.g_m_s2 / request.effective_length_m
    boundary = _request(51, 3*2*pi/sqrt(q)/50)
    assert fit_eligibility(boundary).status == "ready"
    assert fit_eligibility(replace(boundary, effective_length_m=.250001)).status == "insufficient_data"
    legacy = replace(request, profile_id=LEGACY,
        series=replace(request.series, qc_valid=(True,)*50+(False,)*51),
        initial_condition=InitialCondition(.2, 0., "archived_toml"))
    assert fit_eligibility(legacy).status == "ready"


def test_sampling_ties_to_even_preserves_source_frames_and_original_times():
    request = replace(_request(7), maximum_samples=5)
    assert fit_sample_indices(request) == (0, 2, 3, 4, 6)
    request = _request(1101)
    assert len(fit_sample_indices(request)) == 500
    assert fit_sample_indices(request)[0] == 0 and fit_sample_indices(request)[-1] == 1100
    sparse = replace(request.series,
        frame_indices=tuple(i if i < 500 else i+100 for i in range(1101)),
        time_release_relative_s=tuple(i*.1 if i < 500 else (i+100)*.1 for i in range(1101)))
    request = replace(request, series=sparse, end_frame_index=1200)
    indices = fit_sample_indices(request)
    assert any(request.series.frame_indices[i] > i for i in indices)
    assert request.series.time_release_relative_s[-1] == pytest.approx(120., abs=1e-12)


def test_objective_uses_weighted_radians_across_gap_without_restarting_ic():
    request = replace(_request(), maximum_samples=7)
    qc = list(request.series.qc_valid); qc[40:60] = [False]*20
    weights = tuple(None if not ok else (.25 if i % 2 else 1.) for i, ok in enumerate(qc))
    request = replace(request, series=replace(request.series, qc_valid=tuple(qc)), relative_weights=weights)
    parameters = PendulumParameters(.02, 40.)
    evaluation = evaluate_objective(request, M0, parameters)
    full = simulate_pendulum(M0, parameters, request.initial_condition, request.series.time_release_relative_s)
    indices = fit_sample_indices(request)
    assert not any(40 <= i < 60 for i in indices)
    np.testing.assert_allclose(evaluation.prediction.theta_rad, [full.theta_rad[i] for i in indices], atol=1e-12, rtol=1e-12)
    expected = [sqrt(weights[i])*(full.theta_rad[i]-.2) for i in indices]
    np.testing.assert_allclose(evaluation.residual_rad, expected, atol=1e-12, rtol=1e-12)
    expected_cost = sum(request.f_scale_rad**2*(sqrt(1+(r/request.f_scale_rad)**2)-1) for r in expected)
    assert evaluation.cost_rad2 == pytest.approx(expected_cost, rel=1e-12, abs=1e-15)
    assert soft_l1_cost((1e-12,)) == pytest.approx(.5e-24, rel=1e-12, abs=1e-35)


def test_request_digest_covers_actual_mask_weights_ic_and_sampling():
    request = _request()
    digest = objective_request_digest(request)
    assert digest == objective_request_digest(replace(request, effective_length_m=.25))
    for changed in (replace(request, maximum_samples=50), replace(request, f_scale_rad=.01),
                    replace(request, initial_condition=InitialCondition(.3, 0., "explicit")),
                    replace(request, relative_weights=(.25,)+(1.,)*100),
                    replace(request, series=replace(request.series, qc_valid=(False,)+(True,)*100))):
        assert objective_request_digest(changed) != digest


@pytest.mark.parametrize("changes", [
    {"effective_length_m": 0}, {"g_m_s2": True}, {"maximum_samples": True},
    {"relative_weights": (None,)*101}, {"relative_weights": (.01,)*101},
    {"f_scale_rad": float("nan")}, {"end_frame_index": 999}, {"profile_id": "unknown"},
])
def test_invalid_request_is_rejected_at_construction(changes):
    with pytest.raises(ValueError):
        replace(_request(), **changes)


@pytest.mark.parametrize("times", [(-.01, .1), (.1, .1), (.2, .1), (float("nan"),)])
def test_invalid_forward_time_is_rejected_without_sorting_or_compressing(times):
    with pytest.raises(ValueError, match="forward times"):
        simulate_pendulum(M0, PendulumParameters(.02, 40.), InitialCondition(.2, 0., "explicit"), times)


def test_solver_failure_and_nonfinite_predictions_are_not_successful_objectives(monkeypatch):
    import ai_physics_tracker.domain.pendulum_ode as core
    request = _request()
    parameters = PendulumParameters(.02, 40.)
    monkeypatch.setattr(core, "solve_ivp", lambda *a, **kw: SimpleNamespace(
        success=False, y=np.empty((2, 0)), nfev=4, message="step failure"))
    result = evaluate_objective(request, M0, parameters)
    assert result.status == "failed" and result.cost_rad2 is None
    assert result.residual_rad == (1000.,)*101 and result.prediction.theta_rad == ()
    monkeypatch.setattr(core, "solve_ivp", lambda *a, **kw: SimpleNamespace(
        success=True, y=np.full((2, 101), np.nan), nfev=4, message="claimed success"))
    assert evaluate_objective(request, M0, parameters).reason == "nonfinite_prediction"


@pytest.mark.parametrize("video_id", ["P011", "P014"])
@pytest.mark.parametrize("model", [M0, M1])
def test_frozen_e2_forward_and_all_valid_rmse(video_id, model):
    with gzip.open(GOLDEN/f"{video_id}-effective.csv.gz", "rt", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    with (GOLDEN/"formal-fit48.csv").open(encoding="utf-8-sig", newline="") as f:
        fit = next(r for r in csv.DictReader(f) if r["video_id"] == video_id and r["model"] == model)
    item = next(r for r in json.loads((GOLDEN/"inputs24.json").read_text()) if r["video_id"] == video_id)
    parameters = PendulumParameters(float(fit["alpha1_s_inv"]), float(fit["omega2_s_inv2"]), float(fit["alpha2_rad_inv"]))
    times = tuple(float(r["time_s"]) for r in rows)
    result = simulate_pendulum(model, parameters,
        InitialCondition(item["theta0_rad"], item["omega0_rad_s"], "archived_toml"), times)
    assert result.status == "success"
    expected_key = f"theta_predicted_deg__{model}"
    assert expected_key in rows[0], tuple(rows[0])
    expected = np.radians([float(r[expected_key]) for r in rows])
    assert np.max(np.abs(np.asarray(result.theta_rad)-expected)) <= 1e-5
    valid = np.asarray([r["geometry_valid"] == "True" for r in rows])
    observed = np.radians([float(r["theta_observed_deg"]) for r in rows])
    rmse_deg = degrees(sqrt(float(np.mean((np.asarray(result.theta_rad)[valid]-observed[valid])**2))))
    assert rmse_deg == pytest.approx(float(fit["rmse_deg"]), abs=1e-4)


def test_full_metrics_use_all_valid_observations_and_do_not_normalize_by_sum_weights():
    request = replace(_request(), maximum_samples=3, relative_weights=(.25,)*101)
    parameters = PendulumParameters(.02, 40.)
    full = evaluate_trajectory(request, M0, parameters)
    assert full.status == "success" and len(full.residual_rad) == 101
    expected = sqrt(float(np.mean(np.square(full.residual_rad))))
    assert full.rmse_rad == pytest.approx(expected, rel=1e-12)
    assert full.weighted_rmse_rad == pytest.approx(.5*expected, rel=1e-12)
    sample = evaluate_objective(request, M0, parameters)
    assert len(sample.residual_rad) == 3
    assert sqrt(float(np.mean(np.square(sample.residual_rad)))) != pytest.approx(full.rmse_rad, rel=1e-3)
    theta = list(request.series.theta_rad); theta[50] = None
    qc = list(request.series.qc_valid); qc[50] = False
    weights = list(request.relative_weights); weights[50] = None
    changed = replace(request, series=replace(request.series, theta_rad=tuple(theta), qc_valid=tuple(qc)),
                      relative_weights=tuple(weights))
    result = evaluate_trajectory(changed, M0, parameters)
    assert result.residual_rad[50] is None and len(result.prediction.theta_rad) == 101


def test_empty_zero_time_and_invalid_parameters_or_tolerances():
    parameters = PendulumParameters(.02, 40.)
    ic = InitialCondition(.2, -.3, "explicit")
    assert simulate_pendulum(M0, parameters, ic, ()).status == "empty"
    assert simulate_pendulum(M0, parameters, ic, (0.,)).omega_rad_s == (-.3,)
    with pytest.raises(ValueError, match="M0"):
        simulate_pendulum(M0, replace(parameters, alpha2_rad_inv=.01), ic, (0., .1))
    with pytest.raises(ValueError, match="precision"):
        IntegrationSettings(rtol=1e-20)
    with pytest.raises(ValueError):
        InitialCondition(float("nan"), 0., "explicit")
    with pytest.raises(ValueError):
        PendulumParameters(-.1, 40.)
    with pytest.raises(ValueError, match="first_step"):
        simulate_pendulum(M0, parameters, ic, (.1,), IntegrationSettings(first_step_s=.2))


def test_missing_release_source_frame_is_rejected_but_missing_release_observation_is_allowed():
    request = _request(release=50)
    indices = tuple(i for i in range(101) if i != 50)
    series = replace(request.series,
        frame_indices=tuple(request.series.frame_indices[i] for i in indices),
        time_release_relative_s=tuple(request.series.time_release_relative_s[i] for i in indices),
        theta_rad=tuple(request.series.theta_rad[i] for i in indices), qc_valid=(True,)*100)
    with pytest.raises(ValueError, match="release"):
        replace(request, series=series, relative_weights=(1.,)*100)
    theta = list(request.series.theta_rad); theta[50] = None
    qc = list(request.series.qc_valid); qc[50] = False
    weights = list(request.relative_weights); weights[50] = None
    request = replace(request, series=replace(request.series, theta_rad=tuple(theta), qc_valid=tuple(qc)),
                      relative_weights=tuple(weights))
    evaluation = evaluate_objective(request, M0, PendulumParameters(.02, 40.))
    assert evaluation.status == "success"
    assert evaluation.prediction.theta_rad[0] != pytest.approx(request.initial_condition.theta0_rad, abs=1e-3)


@pytest.mark.parametrize("changes", [{"initial_condition": None}, {"series": None}, {"integration": {}}])
def test_invalid_collaborator_types_are_value_errors(changes):
    with pytest.raises(ValueError, match="validated"):
        replace(_request(), **changes)
    with pytest.raises(ValueError, match="validated"):
        simulate_pendulum(M0, PendulumParameters(.02, 40.), None, (.1,))


def test_solver_runtime_error_is_structured_for_objective_and_full_trajectory(monkeypatch):
    import ai_physics_tracker.domain.pendulum_ode as core
    def failing_solver(*args, **kwargs):
        raise RuntimeError("synthetic solver crash")
    monkeypatch.setattr(core, "solve_ivp", failing_solver)
    request, parameters = _request(), PendulumParameters(.02, 40.)
    objective = evaluate_objective(request, M0, parameters)
    full = evaluate_trajectory(request, M0, parameters)
    assert objective.status == full.status == "failed"
    assert "synthetic solver crash" in objective.reason
    assert objective.cost_rad2 is None and full.rmse_rad is None
    assert objective.prediction.theta_rad == full.prediction.theta_rad == ()
