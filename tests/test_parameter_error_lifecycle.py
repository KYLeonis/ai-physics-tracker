"""P6.4：统计的保存 / Undo / 旧记录与未来扩展保护，不重拟合历史。"""

from copy import deepcopy
from dataclasses import replace
from threading import Event

import pytest

from tests.test_signal_analysis_job import signal_session, _job
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.signal_analysis_job import SignalSelection, prepare_signal_analysis, run_signal_analysis
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def test_errors_roundtrip_and_result_undo_preserve_exact_statistics(signal_session, tmp_path):
    session, _, track = signal_session
    result = run_signal_analysis(_job(session, track), Event())
    session.apply_analysis_result(result)
    recorded = session.derived_data(track, 'function_fit_x')
    statistics = recorded.extra_fields['analysis']['summary']['parameter_uncertainty']
    assert statistics['sample_count'] == 50
    assert statistics['free_parameter_count'] == 2
    assert all(row['status'] == 'estimated' for row in statistics['parameters'])
    session.undo_analysis()
    assert session.derived_data(track, 'function_fit_x') is None
    session.redo_analysis()
    assert session.derived_data(track, 'function_fit_x') == recorded
    root = tmp_path/'saved'
    ProjectRepository().create_from_project(root, session.project)
    reopened = ProjectRepository().load(root)
    assert next(item for item in reopened.derived if item.kind == 'function_fit_x').extra_fields['analysis']['summary']['parameter_uncertainty'] == statistics


def test_processed_source_keeps_fit_and_fixed_but_does_not_publish_free_se(signal_session):
    session, _, track = signal_session
    spec = FitSpec('a*t+b', (FitParameter('a'), FitParameter('b', 3, fixed=True)))
    job = prepare_signal_analysis(session, SignalSelection(track, 'x', 20, 70, True), spec)
    result = run_signal_analysis(job, Event())
    session.apply_analysis_result(result)
    assert result.fit_outcome.is_publishable
    rows = result.record.extra_fields['analysis']['summary']['parameter_uncertainty']['parameters']
    assert [row['status'] for row in rows] == ['unsupported_source', 'fixed']
    assert all(row['standard_error'] is None for row in rows)


@pytest.mark.parametrize('mutation', ['future', 'boolean', 'bad_se', 'source_conflict', 'selection_conflict', 'legacy', 'extensions'])
def test_target_compatibility_and_unknown_extensions(signal_session, mutation):
    session, _, track = signal_session
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    record = session.derived_data(track, 'function_fit_x')
    extras = deepcopy(record.extra_fields)
    summary = extras['analysis']['summary']
    statistics = summary['parameter_uncertainty']
    if mutation == 'future':
        statistics['version'] = 99
    elif mutation == 'boolean':
        statistics['version'] = True
    elif mutation == 'bad_se':
        statistics['parameters'][0]['standard_error'] = float('nan')
    elif mutation == 'source_conflict':
        extras['analysis']['source_snapshot']['kind'] = 'smoothed_position'
    elif mutation == 'selection_conflict':
        extras['analysis']['selection']['smoothed'] = True
    elif mutation == 'legacy':
        del summary['parameter_uncertainty']
    else:
        summary['future_summary'] = {'value': 9}
        statistics['future_statistics'] = [7]
        statistics['parameters'][0]['future_parameter'] = {'value': 8}
    replaced = replace(record, extra_fields=extras)
    session._project = replace(session.project, derived=tuple(replaced if item.derived_id == record.derived_id else item for item in session.project.derived))
    before = session.project
    if mutation in ('future', 'boolean', 'bad_se', 'source_conflict', 'selection_conflict'):
        with pytest.raises(ProjectSessionError, match='read-only'):
            _job(session, track)
        assert session.project is before
    else:
        session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
        new = session.derived_data(track, 'function_fit_x').extra_fields['analysis']['summary']
        assert new['parameter_uncertainty']['version'] == 2
        if mutation == 'extensions':
            assert new['future_summary'] == {'value': 9}
            assert new['parameter_uncertainty']['future_statistics'] == [7]
            assert new['parameter_uncertainty']['parameters'][0]['future_parameter'] == {'value': 8}


def test_malformed_published_statistics_reject_atomically(signal_session):
    session, _, track = signal_session
    result = run_signal_analysis(_job(session, track), Event())
    extras = deepcopy(result.record.extra_fields)
    extras['analysis']['summary']['parameter_uncertainty']['sample_count'] = True
    result = replace(result, record=replace(result.record, extra_fields=extras))
    before = session.project
    with pytest.raises(ProjectSessionError):
        session.apply_analysis_result(result)
    assert session.project is before


@pytest.mark.parametrize('quantity,smoothed,supported', [('theta', False, True), ('theta', True, False), ('omega', False, False), ('vx', False, False)])
def test_source_support_uses_actual_kind_and_keeps_angular_or_derivative_fit(signal_session, quantity, smoothed, supported):
    from ai_physics_tracker.domain.angular import TwoPointReference
    session, video_id, track = signal_session
    session.add_calibration(video_id, (0, 0), (100, 0), 1, unit='m')
    other = session.add_track(video_id, 'Reference')
    for frame in range(20, 71):
        session.mark_point(other.track_id, frame, pixel_x=30, pixel_y=10)
    session.compute_kinematics(track)
    session.compute_angular(track, reference=TwoPointReference(other.track_id))
    result = run_signal_analysis(prepare_signal_analysis(
        session, SignalSelection(track, quantity, 20, 70, smoothed), FitSpec('c', (FitParameter('c'),))), Event())
    session.apply_analysis_result(result)
    entry = result.record.extra_fields['analysis']['summary']['parameter_uncertainty']['parameters'][0]
    assert entry['status'] == ('estimated' if supported else 'unsupported_source')


@pytest.mark.parametrize('location', ['summary', 'statistics', 'parameter', 'analysis', 'record', 'input'])
def test_nonfinite_unknown_extensions_cannot_create_unsavable_analysis(signal_session, location):
    session, _, track = signal_session
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    record = session.derived_data(track, 'function_fit_x')
    extras = deepcopy(record.extra_fields)
    input_extras = deepcopy(record.input.extra_fields)
    summary = extras['analysis']['summary']
    targets = {'summary': summary, 'statistics': summary['parameter_uncertainty'],
               'parameter': summary['parameter_uncertainty']['parameters'][0],
               'analysis': extras['analysis'], 'record': extras, 'input': input_extras}
    targets[location]['future_extension'] = {'bad': float('nan')}
    corrupted = replace(record, extra_fields=extras, input=replace(record.input, extra_fields=input_extras))
    session._project = replace(session.project, derived=tuple(corrupted if item.derived_id == record.derived_id else item for item in session.project.derived))
    before, undo = session.project, session.can_undo_analysis
    with pytest.raises(ProjectSessionError, match='finite JSON'):
        result = run_signal_analysis(_job(session, track), Event())
        session.apply_analysis_result(result)
    assert session.project is before and session.can_undo_analysis == undo
