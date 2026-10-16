"""ADR-0022实现前冻结样本：建议须支持后续真实单次求解。"""
import numpy as np
import pytest
from ai_physics_tracker.domain.fit_initial import estimate_initial, adopt_estimate
from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec, fit_function


def _fit(time, values, formula):
    expression = parse_expression(formula)
    spec = FitSpec(formula, tuple(FitParameter(name, 1.) for name in expression.parameter_names))
    estimate = estimate_initial(time, values, formula)
    assert estimate.values, estimate.reason
    outcome = fit_function(time, values, adopt_estimate(spec, estimate))
    assert outcome.is_publishable, outcome
    return estimate, outcome


@pytest.mark.parametrize('formula,expected', [('a*t+b', {'a':3.,'b':-2.}),
    ('c + t*b + t^2*a', {'a':.7,'b':-2.,'c':5.}), ('theta', {'theta':2.})])
def test_polynomial_estimates_reproduce_frozen_curves(formula, expected):
    time = np.linspace(0,8,241)
    values = parse_expression(formula).evaluate(time, expected)
    estimate, outcome = _fit(time, values, formula)
    assert outcome.rmse < 1e-8
    assert dict(outcome.parameter_values) == pytest.approx(expected, abs=1e-7)


@pytest.mark.parametrize('damped', [False, True])
@pytest.mark.parametrize('scale,phase', [(1.,.3),(1e-6,-1.2),(1e6,-1.2)])
def test_oscillation_estimates_seed_one_fit(damped,scale,phase):
    time = np.linspace(0,12,601)
    formula = 'c+A*exp(-beta*t)*cos(Omega*t+phi)' if damped else 'c+A*cos(Omega*t+phi)'
    expected = {'c':.4*scale,'A':2*scale,'Omega':2*np.pi*.8,'phi':phase}
    if damped: expected['beta'] = .08
    values = parse_expression(formula).evaluate(time,expected)
    estimate, outcome = _fit(time,values,formula)
    assert dict(estimate.values)['Omega'] == pytest.approx(expected['Omega'],rel=.1)
    assert outcome.rmse/scale < 1e-8
    assert dict(outcome.parameter_values) == pytest.approx(expected, rel=1e-6, abs=1e-10)


def test_noisy_frozen_oscillation():
    time = np.linspace(0,12,601)
    formula = 'A*exp(-gamma*t)*cos(omega*t+phi)+y0'
    values = .4+2*np.exp(-.08*time)*np.cos(2*np.pi*.8*time+.3)
    values += np.random.default_rng(631).normal(0,.03,len(time))
    estimate, outcome = _fit(time,values,formula)
    assert dict(estimate.values)['omega'] == pytest.approx(2*np.pi*.8,rel=.05)
    assert outcome.rmse < .04


@pytest.mark.parametrize('kind', ['short','constant','nearconstant','few_cycles','segments','wrapped','custom'])
def test_estimator_refuses_unreliable_or_custom_sources(kind):
    time = np.linspace(0,12,601)
    values = np.cos(2*np.pi*.8*time)
    formula = 'c+A*cos(w*t+p)'
    options = {}
    if kind == 'short': time,values=time[:15],values[:15]
    if kind == 'constant': values[:]=4
    if kind == 'nearconstant': values=4+values*1e-15
    if kind == 'few_cycles': values=np.cos(2*np.pi*.05*time)
    if kind == 'segments': options['segment_indices']=[0]*300+[1]*301
    if kind == 'wrapped': values=(time+np.pi)%(2*np.pi)-np.pi;options['wrapped']=True
    if kind == 'custom': formula='sin(t*t)'
    estimate = estimate_initial(time,values,formula,**options)
    assert not estimate.values
    assert 'manually' in estimate.reason


def test_adopting_preserves_fixed_and_rejects_out_of_bounds_as_a_batch():
    estimate = estimate_initial([0,1,2],[2,5,8],'a*t+b')
    spec = FitSpec('a*t+b',(FitParameter('a',1,0,2),FitParameter('b',7,fixed=True)))
    with pytest.raises(ValueError): adopt_estimate(spec,estimate)
    spec = FitSpec('a*t+b',(FitParameter('a',1,0,4),FitParameter('b',7,fixed=True)))
    adopted = adopt_estimate(spec,estimate)
    assert adopted.parameters[0].initial == pytest.approx(3.)
    assert adopted.parameters[0].lower == 0
    assert adopted.parameters[1] == spec.parameters[1]
