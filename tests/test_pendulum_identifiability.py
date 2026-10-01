"""P4.2：raw 等价族、独立 forward 与条件 objective valley。"""

import csv
from concurrent.futures import CancelledError
from dataclasses import replace
import gzip
import json
from math import radians
from pathlib import Path

import numpy as np
import pytest

from ai_physics_tracker.domain.angular_analysis import AngularSeries, LEGACY, STUDENT
from ai_physics_tracker.domain.pendulum_identifiability import (
    IdentifiabilityState,
    RawParameterBounds,
    RawParameters,
    build_identifiability_curve,
    build_identifiability_surface,
    compare_equivalent_forwards,
    evaluate_objective_at_q,
    evaluate_surface_node_direct,
    feasible_lambda_range,
    illustrative_raw_reference,
    lump_parameters,
    interpolate_objective_at_q,
    simulate_raw_pendulum,
    transform_raw_parameters,
)
from ai_physics_tracker.domain.pendulum_ode import (
    M1,
    InitialCondition,
    IntegrationSettings,
    ObjectiveRequest,
    PendulumParameters,
    evaluate_objective,
    simulate_pendulum,
)

ROOT = Path(__file__).resolve().parents[1] / "publication" / "evidence" / "golden"


def _raw_values(parameters: RawParameters) -> tuple[float, ...]:
    return (parameters.alpha_a, parameters.alpha1_s_inv,
            parameters.alpha2_rad_inv, parameters.omega0_sq_s_inv2)


def _starred_values(parameters: PendulumParameters) -> tuple[float, ...]:
    return (parameters.alpha1_s_inv, parameters.alpha2_rad_inv, parameters.omega2_s_inv2)


def _request(*, noisy: bool = True, count: int = 151):
    times = tuple(index * 0.05 for index in range(count))
    ic = InitialCondition(0.7, -0.4, "explicit")
    truth = PendulumParameters(0.02, 40.0, 0.03)
    prediction = simulate_pendulum(M1, truth, ic, times, IntegrationSettings(2e-10, 2e-12))
    theta = tuple(float(value + (0.002 * np.sin(index * 0.13) if noisy else 0.0))
                  for index, value in enumerate(prediction.theta_rad))
    series = AngularSeries("a" * 64, tuple(range(count)), times, theta, (True,) * count, 20.0)
    weights = tuple(0.55 + 0.45 * (index % 7) / 6 for index in range(count))
    return ObjectiveRequest(series, weights, ic, 0, count - 1, 0.25, profile_id=STUDENT,
                           maximum_samples=93, integration=IntegrationSettings(2e-10, 2e-12)), truth


def _p011_request_and_parameters():
    with gzip.open(ROOT / "P011-effective.csv.gz", "rt", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    with (ROOT / "formal-fit48.csv").open(encoding="utf-8-sig", newline="") as source:
        fit_rows = list(csv.DictReader(source))
    fit = next(row for row in fit_rows if row["video_id"] == "P011" and row["model"] == M1)
    with (ROOT / "inputs24.json").open(encoding="utf-8") as source:
        input_row = next(row for row in json.load(source) if row["video_id"] == "P011")
    series = AngularSeries(
        "b" * 64,
        tuple(int(row["frame_index_0based"]) for row in rows),
        tuple(float(row["time_s"]) for row in rows),
        tuple(radians(float(row["theta_observed_deg"])) for row in rows),
        tuple(row["geometry_valid"] == "True" for row in rows),
        input_row["fps"],
    )
    weights = tuple(max(0.05, min(1.0, float(row["marker_likelihood"]))) if valid else None
                    for row, valid in zip(rows, series.qc_valid))
    # E4 frozen legacy valley explicitly round-trips theta0_deg from the formal fit row.
    ic = InitialCondition(radians(float(fit["theta0_deg_signed"])), input_row["omega0_rad_s"], "archived_toml")
    request = ObjectiveRequest(series, weights, ic, input_row["release_frame"], series.frame_indices[-1],
                               input_row["length_m"], profile_id=LEGACY)
    parameters = PendulumParameters(float(fit["alpha1_s_inv"]), float(fit["omega2_s_inv2"]),
                                    float(fit["alpha2_rad_inv"]))
    return request, parameters, rows, fit


def _close(actual: float, expected: float, atol: float, rtol: float) -> bool:
    return abs(actual - expected) <= atol + rtol * abs(expected)


def test_raw_lumping_transform_composition_inverse_and_full_bounds_intersection():
    raw_fixture = RawParameters(0.2, 0.024, 0.036, 48.0)
    starred = lump_parameters(raw_fixture)
    assert _starred_values(starred) == pytest.approx((0.02, 0.03, 40.0))
    assert _raw_values(transform_raw_parameters(raw_fixture, 2.0)) == pytest.approx(
        (1.4, 0.048, 0.072, 96.0))
    assert _starred_values(lump_parameters(transform_raw_parameters(raw_fixture, 2.0))) == pytest.approx(
        _starred_values(starred))

    raw = RawParameters(0.0, 0.024, 0.036, 48.0)

    bounds = RawParameterBounds((0.0, 0.12), (0.0, 0.5), (0.0, 0.5), (0.0, 100.0))
    allowed = feasible_lambda_range(raw, bounds)
    assert allowed.min_lambda == pytest.approx(1.0)
    assert allowed.max_lambda == pytest.approx(1.12)
    assert allowed.min_inclusive and allowed.contains(1.0) and allowed.contains(1.12)
    assert not allowed.contains(0.99) and not allowed.contains(1.12001)
    tight_q_bounds = RawParameterBounds((0.0, 0.12), (0.0, 0.5), (0.0, 0.5), (0.0, 52.0))
    tight_range = feasible_lambda_range(raw, tight_q_bounds)
    assert tight_range.max_lambda == pytest.approx(52 / 48)
    assert not tight_range.contains(1.12)

    transformed = transform_raw_parameters(raw, 1.12, bounds)
    assert _raw_values(transformed) == pytest.approx((0.12, 0.02688, 0.04032, 53.76))
    assert _starred_values(lump_parameters(transformed)) == pytest.approx(_starred_values(lump_parameters(raw)))
    composed = transform_raw_parameters(transform_raw_parameters(raw, 1.12), 0.75)
    assert _raw_values(composed) == pytest.approx(_raw_values(transform_raw_parameters(raw, 1.12 * 0.75)))
    assert _raw_values(transform_raw_parameters(transformed, 1 / 1.12)) == pytest.approx(_raw_values(raw))
    state = IdentifiabilityState(raw, 1.12, bounds)
    assert state.illustrative is True
    assert state.transformed_raw == transformed
    assert _starred_values(state.reference_lumped) == pytest.approx(_starred_values(state.transformed_lumped))
    with pytest.raises((AttributeError, TypeError)):
        state.lambda_scale = 1.0
    with pytest.raises(ValueError):
        transform_raw_parameters(raw, 1.13, bounds)
    with pytest.raises(ValueError):
        transform_raw_parameters(raw, 0.0)
    with pytest.raises(ValueError):
        RawParameters(-1.0, 0.02, 0.03, 40.0)


def test_raw_rhs_is_independently_integrated_and_non_equivalent_raw_changes_curve():
    raw = RawParameters(0.0, 0.024, 0.036, 48.0)
    ic = InitialCondition(0.6, -0.3, "explicit")
    times = tuple(index * 0.02 for index in range(501))
    comparison = compare_equivalent_forwards(raw, 1.12, ic, times,
                                              IntegrationSettings(1e-10, 1e-12), tolerance_rad=1e-7)
    assert comparison.status == "success"
    assert comparison.raw_overlap_max_abs_difference_rad <= 1e-7
    assert comparison.raw_lumped_max_abs_difference_rad <= 1e-7
    assert comparison.within_tolerance is True
    assert comparison.raw_reference.theta_rad is not comparison.raw_transformed.theta_rad

    changed = RawParameters(0.0, 0.024, 0.036, 49.0)
    changed_result = simulate_raw_pendulum(changed, ic, times, IntegrationSettings(1e-10, 1e-12))
    assert max(abs(a - b) for a, b in zip(comparison.raw_reference.theta_rad,
                                         changed_result.theta_rad)) > 1e-3


def test_actual_objective_is_invariant_on_equivalent_starred_parameters_and_curve_surface_are_typed():
    request, fitted = _request()
    raw = illustrative_raw_reference(fitted, alpha_a=0.0)
    transformed = transform_raw_parameters(raw, 1.12)
    actual = evaluate_objective(request, M1, lump_parameters(raw))
    equivalent = evaluate_objective(request, M1, lump_parameters(transformed))
    assert actual.status == equivalent.status == "success"
    # evidence/README E4：实际请求按已声明的轨迹及mean objective误差预算核对。
    assert actual.prediction.theta_rad == pytest.approx(equivalent.prediction.theta_rad, abs=1e-7, rel=0)
    actual_mean_cost = 2 * actual.cost_rad2 / len(actual.residual_rad)
    equivalent_mean_cost = 2 * equivalent.cost_rad2 / len(equivalent.residual_rad)
    assert actual_mean_cost == pytest.approx(equivalent_mean_cost, abs=1e-9, rel=1e-4)
    # 变换回集总参数会有ULP舍入，改变自适应步长；等价性证明使用更高积分精度，保留原断言容差。
    proof_request = replace(request, integration=IntegrationSettings(1e-12, 1e-14))
    first = evaluate_objective(proof_request, M1, lump_parameters(raw))
    second = evaluate_objective(proof_request, M1, lump_parameters(transformed))
    assert first.status == second.status == "success"
    assert first.cost_rad2 == pytest.approx(second.cost_rad2, abs=1e-11, rel=1e-8)

    progress = []
    curve = build_identifiability_curve(request, fitted, progress=lambda done, total: progress.append((done, total)))
    assert len(curve.omega2_s_inv2) == 222
    assert progress[-1] == (222, 222)
    assert curve.sample_count == 93
    assert curve.alpha1_star_s_inv == fitted.alpha1_s_inv
    assert curve.alpha2_star_rad_inv == fitted.alpha2_rad_inv
    assert curve.fitted_mean_objective_rad2 == pytest.approx(actual_mean_cost, abs=1e-15, rel=1e-12)
    assert curve.omega2_s_inv2[0] == pytest.approx(0.94 * fitted.omega2_s_inv2 / 1.12)
    assert curve.omega2_s_inv2[-1] == pytest.approx(1.16 * fitted.omega2_s_inv2)

    surface = build_identifiability_surface(curve)
    assert len(surface.alpha_a_values) == 101 and len(surface.omega0_sq_s_inv2_values) == 91
    assert len(surface.objective_ratio_grid) == 101
    assert all(len(row) == 91 for row in surface.objective_ratio_grid)
    interpolated = surface.objective_ratio_grid[0][-1]
    direct = evaluate_surface_node_direct(request, fitted, curve, 0.0,
                                          surface.omega0_sq_s_inv2_values[-1])
    assert direct.evaluation == "direct" and direct.omega2_s_inv2 == pytest.approx(curve.omega2_s_inv2[-1])
    assert direct.objective_ratio == pytest.approx(interpolated, abs=1e-12, rel=1e-10)
    assert direct.mean_objective_rad2 != pytest.approx(curve.fitted_mean_objective_rad2)

    row, column = 50, 74
    alpha_a = surface.alpha_a_values[row]
    omega0_sq = surface.omega0_sq_s_inv2_values[column]
    q_off_grid = surface.omega2_s_inv2_grid[row][column]
    assert 0 < row < 100 and 0 < column < 90
    assert q_off_grid not in curve.omega2_s_inv2
    interpolated_off_grid = interpolate_objective_at_q(curve, q_off_grid)
    direct_off_grid = evaluate_surface_node_direct(request, fitted, curve, alpha_a, omega0_sq)
    assert direct_off_grid.status == interpolated_off_grid.status == "success"
    assert surface.objective_ratio_grid[row][column] == pytest.approx(
        interpolated_off_grid.objective_ratio, abs=1e-12, rel=1e-10)
    assert abs(direct_off_grid.objective_ratio - interpolated_off_grid.objective_ratio) \
        / interpolated_off_grid.objective_ratio <= 1e-4

    changed_weights = replace(request, relative_weights=(0.7,) + request.relative_weights[1:])
    changed_ic = replace(request, initial_condition=InitialCondition(0.71, -0.4, "explicit"))
    changed_fit = PendulumParameters(fitted.alpha1_s_inv + 1e-4, fitted.omega2_s_inv2,
                                     fitted.alpha2_rad_inv)
    for mismatched_request, mismatched_fit in (
        (changed_weights, fitted), (changed_ic, fitted), (request, changed_fit),
    ):
        with pytest.raises(ValueError, match="does not match"):
            evaluate_surface_node_direct(mismatched_request, mismatched_fit, curve, alpha_a, omega0_sq)


def test_zero_reference_objective_has_unavailable_ratio_and_scan_cancellation_propagates():
    request, fitted = _request(noisy=False)
    node = evaluate_objective_at_q(request, fitted, fitted.omega2_s_inv2)
    assert node.status == "unavailable" and node.reason == "zero_fitted_objective"
    assert node.objective_ratio is None and node.log10_objective_ratio is None

    calls = 0

    def cancel_after_two_nodes():
        nonlocal calls
        calls += 1
        if calls > 4:
            raise CancelledError("cancelled")

    with pytest.raises(CancelledError):
        build_identifiability_curve(request, fitted, check_cancel=cancel_after_two_nodes)


def test_frozen_p011_e4_curve_surface_and_raw_overlap_remain_within_declared_tolerances():
    request, fitted, rows, fit = _p011_request_and_parameters()
    assert request.profile_id == LEGACY
    assert request.initial_condition.theta0_rad == pytest.approx(radians(float(fit["theta0_deg_signed"])), abs=0)

    curve = build_identifiability_curve(request, fitted)
    with gzip.open(ROOT / "report_identifiability_objective_curve.json.gz", "rt") as source:
        expected_curve = json.load(source)
    assert len(expected_curve) == 222
    for index, expected in enumerate(expected_curve):
        assert _close(curve.omega2_s_inv2[index], expected["omega2_observed_s_inv2"], 1e-12, 1e-12)
        assert curve.mean_objective_rad2[index] is not None
        assert _close(curve.mean_objective_rad2[index], expected["robust_objective"], 1e-9, 1e-4)
        assert _close(curve.objective_ratio[index], expected["objective_over_fitted"], 1e-5, 1e-4)

    surface = build_identifiability_surface(curve)
    with gzip.open(ROOT / "fig04_objective_surface.csv.gz", "rt", newline="") as source:
        expected_surface = list(csv.DictReader(source))
    assert len(expected_surface) == 101 * 91
    alpha_index = {round(value, 12): index for index, value in enumerate(surface.alpha_a_values)}
    omega_index = {round(value, 12): index for index, value in enumerate(surface.omega0_sq_s_inv2_values)}
    for row in expected_surface:
        i = alpha_index[round(float(row["alpha_a"]), 12)]
        j = omega_index[round(float(row["omega0_sq_s_inv2"]), 12)]
        assert _close(surface.omega2_s_inv2_grid[i][j], float(row["omega2_observed_s_inv2"]), 1e-12, 1e-12)
        assert _close(surface.objective_ratio_grid[i][j], float(row["objective_over_fitted"]), 1e-5, 1e-4)
        assert _close(surface.log10_objective_ratio_grid[i][j], float(row["log10_objective_over_fitted"]),
                      1e-5, 1e-4)

    with gzip.open(ROOT / "fig04_complete_raw_parameter_sets.csv.gz", "rt", newline="") as source:
        raw_rows = {row["set"]: row for row in csv.DictReader(source)}
    raw_a = RawParameters(float(raw_rows["A"]["alpha_a"]), float(raw_rows["A"]["alpha1_s_inv"]),
                          float(raw_rows["A"]["alpha2_rad_inv"]), float(raw_rows["A"]["omega0_sq_s_inv2"]))
    raw_b = RawParameters(float(raw_rows["B"]["alpha_a"]), float(raw_rows["B"]["alpha1_s_inv"]),
                          float(raw_rows["B"]["alpha2_rad_inv"]), float(raw_rows["B"]["omega0_sq_s_inv2"]))
    assert _raw_values(transform_raw_parameters(raw_a, 1.12)) == pytest.approx(
        _raw_values(raw_b), abs=1e-12, rel=1e-12)
    with gzip.open(ROOT / "fig04_raw_set_trajectory_overlap.csv.gz", "rt", newline="") as source:
        overlap_rows = list(csv.DictReader(source))
    overlap_times = tuple(float(row["time_s"]) for row in overlap_rows)
    overlap_ic = InitialCondition(request.initial_condition.theta0_rad,
                                  request.initial_condition.omega0_rad_s, "archived_toml")
    settings = IntegrationSettings(1e-10, 1e-12)
    pred_a = simulate_raw_pendulum(raw_a, overlap_ic, overlap_times, settings)
    pred_b = simulate_raw_pendulum(raw_b, overlap_ic, overlap_times, settings)
    assert pred_a.status == pred_b.status == "success"
    assert max(abs(a - b) for a, b in zip(pred_a.theta_rad, pred_b.theta_rad)) <= 1e-7
    for index, expected in enumerate(overlap_rows):
        assert abs(pred_a.theta_rad[index] - radians(float(expected["theta_A_deg"]))) <= 1e-7
        assert abs(pred_b.theta_rad[index] - radians(float(expected["theta_B_deg"]))) <= 1e-7
