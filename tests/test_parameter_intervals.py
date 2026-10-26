"""ADR-0029：95%局部t区间的解析 / 拒绝 / 兼容与历史契约。"""

from copy import deepcopy
from dataclasses import asdict, replace
from threading import Event
import json

import numpy as np
import pytest

from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec, fit_function
from ai_physics_tracker.domain.fit_uncertainty import (
    ParameterError, ParameterUncertainty, METHOD, add_parameter_intervals, read_parameter_uncertainty,
)
from tests.test_signal_analysis_job import signal_session, _job
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.application.signal_analysis_job import recorded_parameter_errors, run_signal_analysis
from ai_physics_tracker.application.fit_attempt_view import rebuild_fit_attempt_view
from tests.test_fit_attempt_view import _successful_attempt


@pytest.mark.parametrize('scale', [1e-150, 1., 1e150])
def test_small_sample_interval_uses_t_with_actual_residual_dof(scale):
    time = np.arange(4.)
    noise = np.array([.1, -.1, -.1, .1])
    spec = FitSpec('a*t+b', (FitParameter('a', scale), FitParameter('b', scale)))
    outcome = fit_function(time, (2*time+3+noise)*scale, spec)
    assert outcome.is_publishable
    stats = outcome.parameter_uncertainty
    assert stats.version == 2 and stats.degrees_of_freedom == 2
    assert stats.confidence_level == pytest.approx(.95, abs=1e-15)
    # df=2的独立表值；不能用大样本1.96替代。
    expected_se = {'a': np.sqrt(.02/5), 'b': np.sqrt(.02*(.25+1.5**2/5))}
    estimates = dict(outcome.parameter_values)
    for entry in stats.parameters:
        expected_half = 4.302652729749464 * expected_se[entry.name]
        lower, upper = entry.confidence_interval
        assert (upper-lower)/(2*scale) == pytest.approx(expected_half, rel=2e-5, abs=0)
        assert (lower+upper)/(2*scale) == pytest.approx(estimates[entry.name]/scale, rel=1e-12, abs=1e-12)
        assert not entry.interval_reason
    raw = json.loads(json.dumps(asdict(stats), allow_nan=False))
    assert read_parameter_uncertainty(raw, spec.parameters, 4, 'world_position', estimates) == stats.parameters


def test_intervals_restore_original_parameter_coordinates_in_existing_fixture():
    time = np.linspace(0, 4, 41)
    noise = np.random.default_rng(6428).normal(0, .04, len(time))
    spec = FitSpec('a*t+b', (FitParameter('a', .2), FitParameter('b', -10)))
    result = fit_function(time, 2.5*time-.7+noise, spec)
    for entry in result.parameter_uncertainty.parameters:
        lower, upper = entry.confidence_interval
        assert (upper-lower)/2 == pytest.approx(2.022690920036761*entry.standard_error, rel=2e-5, abs=1e-15)


@pytest.mark.parametrize('value,error,lower,upper,reason', [
    (1., .1, .9, None, 'bound'), (1., .1, None, 1.1, 'bound'),
    (1e308, 1e308, None, None, 'finite numerical range'),
    (1., 1e-100, None, None, 'floating-point resolution'),
])
def test_unavailable_interval_preserves_finite_se(value, error, lower, upper, reason):
    parameter = FitParameter('a', value, lower=lower, upper=upper)
    original = ParameterUncertainty(1, METHOD, 20, 1, 19, (ParameterError('a', 'estimated', error, ''),))
    result = add_parameter_intervals(original, (parameter,), {'a': value})
    entry = result.parameters[0]
    assert entry.standard_error == error
    assert entry.status == 'estimated' and entry.confidence_interval is None
    assert reason in entry.interval_reason
    json.dumps(asdict(result), allow_nan=False)


def test_exact_zero_se_can_record_a_degenerate_interval():
    parameter = FitParameter('a', 1.)
    original = ParameterUncertainty(1, METHOD, 20, 1, 19, (ParameterError('a', 'estimated', 0., ''),))
    result = add_parameter_intervals(original, (parameter,), {'a': 1.})
    assert result.parameters[0].confidence_interval == (1., 1.)


@pytest.mark.parametrize('mutation', ['level_bool', 'level_99', 'method', 'inverted', 'shifted', 'nan', 'missing', 'false_reason'])
def test_v2_reader_rejects_confidence_metadata_or_bounds_that_disagree(mutation):
    spec = FitSpec('a*t+b', (FitParameter('a'), FitParameter('b')))
    result = fit_function(np.arange(4.), np.array([3.1, 4.9, 6.9, 9.1]), spec)
    raw = json.loads(json.dumps(asdict(result.parameter_uncertainty)))
    row = raw['parameters'][0]
    if mutation.startswith('level'):
        raw['confidence_level'] = True if mutation == 'level_bool' else .99
    elif mutation == 'method':
        raw['interval_method'] = 'normal_1.96'
    elif mutation == 'inverted':
        row['confidence_interval'].reverse()
    elif mutation == 'shifted':
        row['confidence_interval'][1] += 1
    elif mutation == 'nan':
        row['confidence_interval'][0] = float('nan')
    elif mutation == 'missing':
        del row['confidence_interval']
    else:
        row['interval_reason'] = 'not actually missing'
    with pytest.raises(ValueError):
        read_parameter_uncertainty(raw, spec.parameters, 4, 'world_position', dict(result.parameter_values))


def test_v1_se_only_is_not_backfilled_and_unknown_extensions_survive_upgrade(signal_session):
    session, _, track = signal_session
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    record = session.derived_data(track, 'function_fit_x')
    extras = deepcopy(record.extra_fields)
    stats = extras['analysis']['summary']['parameter_uncertainty']
    stats['version'] = 1
    del stats['confidence_level'], stats['interval_method']
    stats['future_root'] = 'keep'
    for row in stats['parameters']:
        del row['confidence_interval'], row['interval_reason']
        row['future_row'] = 'keep'
    legacy = replace(record, extra_fields=extras)
    session._project = replace(session.project, derived=tuple(legacy if item.derived_id == record.derived_id else item for item in session.project.derived))
    assert all(entry.confidence_interval is None and entry.interval_reason == 'Not recorded'
               for entry in recorded_parameter_errors(extras['analysis']))
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    new = session.derived_data(track, 'function_fit_x').extra_fields['analysis']['summary']['parameter_uncertainty']
    assert new['version'] == 2 and new['future_root'] == 'keep'
    assert all(row['future_row'] == 'keep' and 'confidence_interval' in row for row in new['parameters'])


def test_new_intervals_roundtrip_undo_and_history_copy_without_backfill(signal_session, tmp_path, monkeypatch):
    session, _, track = signal_session
    # 复用已有解析轨迹，追加确定性误差使区间宽度清晰可见。
    for frame in range(20, 71):
        if frame != 40:
            session.mark_point(track, frame, pixel_x=3+.2*(frame-20)+.04*np.sin(frame), pixel_y=20)
    session.compute_kinematics(track)
    attempt, _, result = _successful_attempt(session, track)
    session.apply_analysis_result(result)
    record = session.derived_data(track, 'function_fit_x')
    statistics = deepcopy(record.extra_fields['analysis']['summary']['parameter_uncertainty'])
    assert all(row['confidence_interval'] is not None for row in statistics['parameters'])
    assert session.undo_analysis() and session.redo_analysis()
    assert session.derived_data(track, 'function_fit_x').extra_fields['analysis']['summary']['parameter_uncertainty'] == statistics
    root = tmp_path/'saved'
    ProjectRepository().create_from_project(root, session.project)
    assert next(item for item in ProjectRepository().load(root).derived if item.kind == 'function_fit_x').extra_fields['analysis']['summary']['parameter_uncertainty'] == statistics
    import ai_physics_tracker.domain.function_fit as fitting
    monkeypatch.setattr(fitting, 'fit_function', lambda *_args, **_kwargs: pytest.fail('History must not refit'))
    before = session.project
    view = rebuild_fit_attempt_view(session, attempt)
    assert view.is_available
    assert view.metadata['summary']['parameter_uncertainty'] == statistics
    legacy_attempt = deepcopy(attempt)
    legacy_stats = legacy_attempt['summary']['parameter_uncertainty']
    legacy_stats['version'] = 1
    del legacy_stats['confidence_level'], legacy_stats['interval_method']
    for row in legacy_stats['parameters']:
        del row['confidence_interval'], row['interval_reason']
    view = rebuild_fit_attempt_view(session, legacy_attempt)
    assert view.is_available
    assert all(entry.interval_reason == 'Not recorded' for entry in recorded_parameter_errors(view.metadata))
    assert session.project is before
