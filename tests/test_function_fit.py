"""S1解析回归：先冻结容差，再验证参数、预测和失败语义。"""

import numpy as np
import pytest

from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec, fit_function

# 无噪声、良好初值的多项式参数绝对容差1e-7；阻尼余弦1e-6，预测RMSE<1e-8。
@pytest.mark.parametrize("formula,truth,initial", [
    ("a*t+b", {"a": 2.3, "b": -4}, {"a": 1, "b": 0}),
    ("a*t^2+b*t+c", {"a": .4, "b": -2, "c": 1}, {"a": 1, "b": 0, "c": 0}),
    ("c+A*exp(-beta*t)*cos(Omega*t+phi)",
     {"c": .2, "A": 1.3, "beta": .12, "Omega": 4.2, "phi": .3},
     {"c": .1, "A": 1, "beta": .1, "Omega": 4, "phi": .2}),
])
def test_recovers_identifiable_user_functions(formula, truth, initial):
    time_s = np.linspace(0, 4, 161)
    measured = parse_expression(formula).evaluate(time_s, truth)
    spec = FitSpec(formula, tuple(FitParameter(name, value) for name, value in initial.items()))

    outcome = fit_function(time_s, measured, spec)

    assert outcome.status == "success", outcome.message
    assert outcome.rmse < 1e-8
    for name, value in outcome.parameter_values:
        tolerance = 1e-6 if "cos" in formula else 1e-7
        assert value == pytest.approx(truth[name], rel=0, abs=tolerance)
    np.testing.assert_allclose(outcome.residual, measured - outcome.prediction, atol=1e-12)


def test_bounds_and_fixed_parameters_are_respected():
    time_s = np.linspace(0, 2, 30)
    spec = FitSpec("a*t+b", (FitParameter("a", 1, 0, 2), FitParameter("b", 3, fixed=True)))
    outcome = fit_function(time_s, 4*time_s+3, spec)
    assert outcome.status == "success"
    assert dict(outcome.parameter_values) == pytest.approx({"a": 2, "b": 3}, abs=1e-7)


def test_constant_fit_is_valid_and_all_fixed_is_distinct():
    time_s = np.arange(8, dtype=float)
    outcome = fit_function(time_s, np.full(8, 5), FitSpec("c", (FitParameter("c", 1),)))
    assert outcome.status == "success"
    assert dict(outcome.parameter_values)["c"] == pytest.approx(5, abs=1e-9)
    fixed = fit_function(time_s, np.full(8, 5), FitSpec("c", (FitParameter("c", 4, fixed=True),)))
    assert fixed.status == "given_parameters"
    assert fixed.rmse == pytest.approx(1, abs=1e-12)


@pytest.mark.parametrize("formula,params", [
    ("a+b+t", (FitParameter("a"), FitParameter("b"))),
    ("a*0+t", (FitParameter("a"),)),
])
def test_unidentifiable_parameters_are_not_publishable(formula, params):
    outcome = fit_function(np.arange(10.), np.arange(10.)+2, FitSpec(formula, params))
    assert outcome.status == "unidentifiable"
    assert not outcome.is_publishable and not outcome.prediction


def test_domain_budget_cancel_and_insufficient_samples_never_publish():
    time_s = np.arange(10.)
    domain = fit_function(time_s, time_s, FitSpec("sqrt(a-t)", (FitParameter("a", 1),)))
    assert domain.status == "domain_error"
    spec = FitSpec("a*t", (FitParameter("a", 1),), max_evaluations=1)
    assert fit_function(time_s, time_s*2, spec).status == "evaluation_limit"
    assert fit_function(time_s, time_s, spec, lambda: True).status == "cancelled"
    assert fit_function(time_s[:1], time_s[:1], spec).status == "insufficient_samples"


def test_constraints_are_validated_before_solving():
    with pytest.raises(ValueError):
        FitParameter("a", 4, upper=2)
    with pytest.raises(ValueError):
        FitSpec("a*t", (FitParameter("b"),))


@pytest.mark.parametrize('scale',[1e17,1e-200])
def test_identifiable_constant_does_not_depend_on_signal_units(scale):
    outcome = fit_function(np.arange(20.),np.full(20,scale),FitSpec('c',(FitParameter('c',scale),)))
    assert outcome.is_publishable,outcome
    assert dict(outcome.parameter_values)['c'] == pytest.approx(scale,rel=1e-10,abs=0)
