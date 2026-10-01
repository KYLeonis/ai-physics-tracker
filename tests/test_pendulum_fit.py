"""P3.2：参数恢复、起点支持集、失败/非收敛与共同输入比较。"""

from concurrent.futures import CancelledError
from dataclasses import replace
from math import cos, pi, sqrt
from types import SimpleNamespace
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from ai_physics_tracker.domain.angular_analysis import AngularSeries, LEGACY
from ai_physics_tracker.domain.pendulum_ode import (
    M0, M1, InitialCondition, IntegrationSettings, ObjectiveRequest, PendulumParameters, simulate_pendulum,
)
from ai_physics_tracker.domain.pendulum_fit_seed import (
    deterministic_starts, estimate_fit_seed, seed_source_indices,
)
from ai_physics_tracker.domain.pendulum_fit import (
    FitSettings, compare_fits, fit_bounds, fit_pendulum,
)


def _request(model=M1, *, theta0=.7, omega0=-.4, q=40., count=241, integration=IntegrationSettings()):
    times = tuple(i*.05 for i in range(count))
    params = PendulumParameters(.03, q, .02 if model == M1 else 0.)
    ic = InitialCondition(theta0, omega0, "explicit")
    prediction = simulate_pendulum(model, params, ic, times, integration)
    series = AngularSeries("a"*64, tuple(range(count)), times, prediction.theta_rad, (True,)*count, 20.)
    return ObjectiveRequest(series, (1.,)*count, ic, 0, count-1, .25, integration=integration), params


@pytest.mark.parametrize("model,theta0,omega0", [(M0, .7, 0.), (M1, -.8, .4)])
def test_noiseless_physical_parameters_are_recovered_on_full_grid(model, theta0, omega0):
    # 参数恢复用显式高精度控制积分噪声；profile默认容差另由E2/E3历史回归检查，不改冻结值。
    request, truth = _request(model, theta0=theta0, omega0=omega0, integration=IntegrationSettings(2e-10, 2e-12))
    result = fit_pendulum(request, model)
    assert result.status == "success"
    assert len(result.starts) == 3 and result.selected_start_index in range(3)
    assert len(result.trajectory.prediction.theta_rad) == len(request.series.frame_indices)
    assert result.parameters.alpha1_s_inv == pytest.approx(truth.alpha1_s_inv, abs=2e-5)
    assert result.parameters.alpha2_rad_inv == pytest.approx(truth.alpha2_rad_inv, abs=2e-5)
    assert result.parameters.omega2_s_inv2 == pytest.approx(truth.omega2_s_inv2, abs=2e-5)
    assert result.trajectory.rmse_rad < 1e-6
    assert all(s.start and s.parameters is not None and s.nfev > 0 for s in result.starts)
    assert result.config["optimizer"]["f_scale_rad"] == pytest.approx(pi/360, abs=1e-15)


@pytest.mark.xfail(strict=True, reason="P3.2 review F2 Accepted Limitation: frozen tolerance can give false M1 recovery")
def test_frozen_default_m1_parameter_recovery_gate():
    request, truth = _request(M1)
    result = fit_pendulum(request, M1)
    assert result.status == "success"
    assert result.parameters.alpha1_s_inv == pytest.approx(truth.alpha1_s_inv, abs=2e-5)
    assert result.parameters.alpha2_rad_inv == pytest.approx(truth.alpha2_rad_inv, abs=2e-5)
    assert result.parameters.omega2_s_inv2 == pytest.approx(truth.omega2_s_inv2, abs=2e-5)


def test_m0_warm_start_and_comparison_of_nested_model_on_same_observations():
    request, _ = _request(M0)
    m0 = fit_pendulum(request, M0)
    m1 = fit_pendulum(request, M1, warm_start=m0)
    assert m0.status == m1.status == "success"
    assert len(m1.starts) == 4
    assert m1.starts[0].start[0] == pytest.approx(m0.parameters.alpha1_s_inv, abs=1e-12)
    assert m1.starts[0].start[1] == pytest.approx(1e-8, abs=1e-12)
    assert compare_fits(m0, m1).status == "comparable"
    changed = replace(m1, comparability_digest="b"*64)
    assert compare_fits(m0, changed).status == "not_comparable"
    assert compare_fits(replace(m0, status="nonconverged"), m1).status == "unavailable"
    zero = replace(m0, trajectory=replace(m0.trajectory, rmse_rad=0.))
    assert compare_fits(zero, m1).reason == "zero_m0_rmse"


def test_student_longest_uniform_seed_tie_earliest_and_fallback_do_not_change_source_time():
    request, _ = _request()
    qc = tuple(20 <= i < 60 or 100 <= i < 140 for i in range(241))
    series = replace(request.series, qc_valid=qc)
    request = replace(request, series=series)
    assert seed_source_indices(request) == tuple(range(20, 60))
    times = list(series.time_release_relative_s); times[30] += .001
    request = replace(request, series=replace(series, time_release_relative_s=tuple(times)))
    assert seed_source_indices(request) == tuple(range(100, 140))
    assert request.series.time_release_relative_s[100] == pytest.approx(5., abs=1e-12)
    one = replace(request, series=replace(request.series, qc_valid=tuple(i % 3 == 0 for i in range(241))))
    assert seed_source_indices(one) == ()
    seed = estimate_fit_seed(one, (8., 64.), .5)
    assert seed.alpha1_guess_s_inv == pytest.approx(.02, abs=1e-14)
    assert seed.omega2_estimate_s_inv2 == pytest.approx(one.g_m_s2/one.effective_length_m, abs=1e-12)
    legacy = replace(one, profile_id=LEGACY, initial_condition=InitialCondition(.7, -.4, "archived_toml"))
    assert seed_source_indices(legacy) == tuple(range(0, 241, 3))


def test_deterministic_starts_match_sealed_m0_m1_formula_and_custom_narrow_bounds():
    request, _ = _request()
    settings = FitSettings()
    lower, upper = fit_bounds(request, M0, settings)
    seed = estimate_fit_seed(request, (lower[-1], upper[-1]), upper[0])
    starts = deterministic_starts(M0, seed, lower, upper)
    assert len(starts) == 3
    assert starts[0][0] == pytest.approx(seed.alpha1_guess_s_inv, abs=1e-12)
    assert starts[1][0] == pytest.approx(max(.005, seed.alpha1_guess_s_inv), abs=1e-12)
    assert starts[2][0] == pytest.approx(.08, abs=1e-12)
    narrow = FitSettings(alpha1_bounds=(.04, .041), alpha2_bounds=(.05, .051), omega2_bounds=(39.99, 40.01))
    lower, upper = fit_bounds(request, M1, narrow)
    seed = estimate_fit_seed(request, (lower[-1], upper[-1]), upper[0])
    for start in deterministic_starts(M1, seed, lower, upper):
        assert all(lo < value < hi for value, lo, hi in zip(start, lower, upper))


def _optimizer_result(x, cost, *, success=True):
    x = np.asarray(x, dtype=float)
    return SimpleNamespace(x=x, cost=cost, success=success, nfev=1, message="synthetic optimizer result",
                           jac=np.eye(len(x)))


def test_lowest_finite_cost_candidate_may_be_nonconverged_and_is_not_ranked(monkeypatch):
    import ai_physics_tracker.domain.pendulum_fit as core
    request, _ = _request(M0)
    calls = iter([_optimizer_result((.03, 40.), .1, success=False),
                  _optimizer_result((.04, 40.), .2), _optimizer_result((.05, 40.), .3)])
    monkeypatch.setattr(core, "least_squares", lambda *a, **kw: next(calls))
    result = fit_pendulum(request, M0)
    assert result.status == "nonconverged" and result.selected_start_index == 0
    assert result.starts[0].cost_rad2 == pytest.approx(.1, abs=1e-14)
    assert "optimizer_not_converged" in result.warnings
    # student不接受nonconverged warm；legacy显式保留封存行为。
    calls = iter([_optimizer_result((.03, .02, 40.), .1)]*3)
    m1 = fit_pendulum(request, M1, warm_start=result)
    assert len(m1.starts) == 3


def test_optimizer_failure_is_recorded_per_start_and_does_not_hide_valid_candidates(monkeypatch):
    import ai_physics_tracker.domain.pendulum_fit as core
    request, _ = _request(M0)
    count = 0
    def optimizer(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("one start failed")
        return _optimizer_result((.03, 40.), .1)
    monkeypatch.setattr(core, "least_squares", optimizer)
    result = fit_pendulum(request, M0)
    assert result.status == "success" and result.starts[0].status == "failed"
    assert result.selected_start_index == 1
    assert "some_starts_failed" in result.warnings
    monkeypatch.setattr(core, "least_squares", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("all failed")))
    result = fit_pendulum(request, M0)
    assert result.status == "failed" and result.parameters is None and result.trajectory is None
    assert len(result.starts) == 3 and result.reason == "all_starts_failed"


def test_nonfinite_jacobian_is_a_failed_start_not_an_uncaught_numerical_error(monkeypatch):
    import ai_physics_tracker.domain.pendulum_fit as core
    request, _ = _request(M0)
    bad = _optimizer_result((.03, 40.), .01)
    bad.jac[:] = float("nan")
    calls = iter([bad, _optimizer_result((.03, 40.), .1), _optimizer_result((.03, 40.), .2)])
    monkeypatch.setattr(core, "least_squares", lambda *a, **kw: next(calls))
    result = fit_pendulum(request, M0)
    assert result.status == "success" and result.selected_start_index == 1
    assert result.starts[0].status == "failed" and "Jacobian" in result.starts[0].message


def test_penalty_only_optimizer_success_cannot_become_successful_fit(monkeypatch):
    import ai_physics_tracker.domain.pendulum_fit as core
    import ai_physics_tracker.domain.pendulum_ode as ode
    request, _ = _request(M0)
    def failing_solver(*args, **kwargs):
        raise RuntimeError("integration failure")
    monkeypatch.setattr(ode, "solve_ivp", failing_solver)
    monkeypatch.setattr(core, "least_squares", lambda *a, **kw: _optimizer_result((.03, 40.), 123.))
    result = fit_pendulum(request, M0)
    assert result.status == "failed" and result.parameters is None and result.trajectory is None
    assert "integration failure" in result.reason


def test_insufficient_data_and_explicit_cancellation_skip_optimizer(monkeypatch):
    import ai_physics_tracker.domain.pendulum_fit as core
    request, _ = _request(count=49)
    monkeypatch.setattr(core, "least_squares", lambda *a, **kw: pytest.fail("optimizer must not run"))
    assert fit_pendulum(request, M0).status == "insufficient_data"
    request, _ = _request(M0)
    def cancel():
        raise CancelledError()
    with pytest.raises(CancelledError):
        fit_pendulum(request, M0, check_cancel=cancel)


@pytest.mark.parametrize("changes", [
    {"alpha1_bounds": (1., 0.)}, {"alpha2_bounds": (0., float("inf"))},
    {"omega2_bounds": (0., 40.)}, {"max_nfev": True}, {"xtol": 1e-20}, {"starts": ()},
])
def test_invalid_fit_settings_are_rejected_at_construction(changes):
    with pytest.raises(ValueError):
        FitSettings(**changes)


def test_custom_start_shape_and_outside_bounds_are_rejected():
    request, _ = _request()
    with pytest.raises(ValueError, match="custom start"):
        fit_pendulum(request, M0, FitSettings(starts=((.02, .03, 40.),)))
    with pytest.raises(ValueError, match="custom start"):
        fit_pendulum(request, M1, FitSettings(starts=((-1., .03, 40.),)))


def test_archived_regression_parser_preserves_units_mask_and_rejects_changed_input(tmp_path):
    import json
    from math import radians
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("fit_regression", root/"scripts/publication_fit_regression.py")
    regression = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regression)
    request, digest = regression.read_request("P011", None)
    item = next(row for row in json.loads((root/"publication/evidence/golden/inputs24.json").read_text(encoding="utf-8"))
                if row["video_id"] == "P011")
    assert request.profile_id == LEGACY and request.initial_condition.source == "archived_toml"
    assert request.initial_condition.theta0_rad == item["theta0_rad"]
    assert request.series.frame_indices[0] == item["release_frame"]
    assert request.series.time_release_relative_s[0] == 0.
    assert request.series.theta_rad[0] == pytest.approx(radians(-69.87425787288859), abs=1e-12)
    assert request.series.qc_valid[0] and request.relative_weights[0] == 1.
    assert request.series.upstream_digest == digest
    source = next(row for row in json.loads((root/"publication/evidence/source-map.json").read_text(encoding="utf-8"))["sources"]
                  if row["id"] == "trajectory-P011")
    changed = tmp_path/source["path"]
    changed.parent.mkdir(parents=True)
    changed.write_bytes(b"changed research asset")
    with pytest.raises(ValueError, match="hash mismatch"):
        regression.read_request("P011", tmp_path)


def test_regression_cli_refuses_frozen_source_map_output(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("fit_regression", root/"scripts/publication_fit_regression.py")
    regression = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regression)
    monkeypatch.setattr("sys.argv", ["regression", "--output", str(root/"publication/evidence/source-map.json")])
    with pytest.raises(SystemExit) as error:
        regression.main()
    assert error.value.code == 2
