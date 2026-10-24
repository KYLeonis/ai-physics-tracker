"""P6.4：解析直线SE、尺度恢复及不可估计摘要边界。"""

from dataclasses import asdict
import json

import numpy as np
import pytest

from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec, fit_function
from ai_physics_tracker.domain.fit_uncertainty import estimate_parameter_uncertainty, read_parameter_uncertainty


@pytest.mark.parametrize('scale', [1e-150, 1., 1e150])
@pytest.mark.parametrize('initial_scale', [.1, 10.])
def test_line_se_matches_independent_closed_form_at_original_scale(scale, initial_scale):
    time = np.linspace(0, 4, 41)
    values = (2.5*time-.7 + np.random.default_rng(6428).normal(0, .04, len(time))) * scale
    spec = FitSpec('a*t+b', (FitParameter('a', 2*scale*initial_scale), FitParameter('b', -scale)))
    outcome = fit_function(time, values, spec)
    assert outcome.is_publishable, outcome
    errors = {row.name: row.standard_error for row in outcome.parameter_uncertainty.parameters}
    # 独立闭式直线解：避免以实现自己的SVD来证明实现。
    centered = time-time.mean()
    slope = np.sum(centered*(values/scale))/np.sum(centered**2)
    intercept = np.mean(values/scale)-slope*time.mean()
    sigma = np.sqrt(np.sum((values/scale-slope*time-intercept)**2)/(len(time)-2))
    expected = {'a': sigma/np.sqrt(np.sum(centered**2)),
                'b': sigma*np.sqrt(1/len(time)+time.mean()**2/np.sum(centered**2))}
    for name in expected:
        assert errors[name]/scale == pytest.approx(expected[name], rel=2e-5, abs=0)
    assert outcome.rmse/scale < .05
    json.dumps(asdict(outcome), allow_nan=False)
    read_parameter_uncertainty(asdict(outcome.parameter_uncertainty), spec.parameters, len(time), "world_position")


def test_fixed_parameters_are_not_zero_errors_and_bounds_do_not_remove_valid_fit():
    time = np.arange(20.)
    spec = FitSpec('a*t+b', (FitParameter('a', 1, upper=2), FitParameter('b', 3, fixed=True)))
    outcome = fit_function(time, time*4+3, spec)
    assert outcome.is_publishable
    assert [row.status for row in outcome.parameter_uncertainty.parameters] == ['boundary_limited', 'fixed']
    assert all(row.standard_error is None for row in outcome.parameter_uncertainty.parameters)
    fixed = fit_function(time, time*4+3, FitSpec('c', (FitParameter('c', 3, fixed=True),)))
    assert fixed.is_publishable
    assert fixed.parameter_uncertainty.parameters[0].status == 'fixed'


@pytest.mark.parametrize('case,status', [
    ('dof', 'insufficient_dof'), ('zero', 'rank_deficient'), ('rank', 'rank_deficient'),
    ('condition', 'ill_conditioned'), ('nan', 'nonfinite'), ('overflow', 'nonfinite'),
])
def test_statistics_failure_is_explicit_and_json_finite(case, status):
    parameters = (FitParameter('a'), FitParameter('b'))
    jacobian = np.column_stack([np.ones(10), np.linspace(0, 1, 10)])
    residual = np.ones(10)
    scales = np.ones(2)
    if case == 'dof':
        jacobian, residual = jacobian[:2], residual[:2]
    elif case == 'zero':
        jacobian[:, 0] = 0
    elif case == 'rank':
        jacobian[:, 1] = 1
    elif case == 'condition':
        jacobian[:, 1] = 1 + np.linspace(0, 1e-6, 10)
    elif case == 'nan':
        jacobian[0, 0] = np.nan
    else:
        jacobian *= 1e-200
        scales *= 1e200
    result = estimate_parameter_uncertainty(parameters, jacobian, residual, scales)
    assert all(row.status == status and row.standard_error is None and row.reason for row in result.parameters)
    json.dumps(asdict(result), allow_nan=False)


@pytest.mark.parametrize('mutate', ['version_bool', 'version_future', 'count_bool', 'nan', 'zero_fixed', 'wrong_name', 'unknown_status'])
def test_summary_boundary_rejects_unreadable_statistics(mutate):
    parameters = (FitParameter('a'),)
    result = estimate_parameter_uncertainty(parameters, np.ones((4, 1)), np.arange(4.), np.ones(1))
    raw = asdict(result)
    row = raw['parameters'][0]
    if mutate.startswith('version'):
        raw['version'] = True if mutate == 'version_bool' else 2
    elif mutate == 'count_bool':
        raw['free_parameter_count'] = True
    elif mutate == 'nan':
        row['standard_error'] = float('nan')
    elif mutate == 'zero_fixed':
        row.update(status='fixed', standard_error=0.)
    elif mutate == 'wrong_name':
        row['name'] = 'b'
    else:
        row['status'] = 'magic'
    with pytest.raises(ValueError):
        read_parameter_uncertainty(raw, parameters, 4, "world_position")


def test_interior_bound_and_nonlinear_model_have_local_estimates():
    time = np.linspace(0, 4, 100)
    values = 3*np.exp(-.7*time) + np.random.default_rng(64).normal(0, .01, len(time))
    outcome = fit_function(time, values, FitSpec('a*exp(-b*t)', (
        FitParameter('a', 2, lower=.1, upper=10), FitParameter('b', .5, lower=.1, upper=2))))
    assert outcome.is_publishable
    assert all(row.status == 'estimated' and row.standard_error > 0 for row in outcome.parameter_uncertainty.parameters)


def test_huge_json_integer_cannot_be_mistaken_for_finite_error():
    parameters = (FitParameter('a'),)
    raw = asdict(estimate_parameter_uncertainty(parameters, np.ones((4, 1)), np.arange(4.), np.ones(1)))
    raw['parameters'][0]['standard_error'] = 10**1000
    with pytest.raises(ValueError):
        read_parameter_uncertainty(raw, parameters, 4, "world_position")
