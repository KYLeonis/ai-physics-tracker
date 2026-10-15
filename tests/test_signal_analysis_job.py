"""P6.3源 / 目标双版本、持久化与历史事务回归。"""

from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.signal_analysis_job import (
    SignalSelection, prepare_signal_analysis, run_signal_analysis,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.angular import TwoPointReference
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec
from ai_physics_tracker.domain.recurrence import RecurrenceSpec
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


@pytest.fixture
def signal_session(tmp_path):
    repository = ProjectRepository()
    session = ProjectSession.start(repository)
    video, _ = session.register_external_video(tmp_path/'test.avi', VideoStreamInfo(640, 480, 10, 100, 'synthetic', 'cfr'))
    track = session.add_track(video.video_id, 'Measured')
    for frame in range(20, 71):
        if frame != 40:
            session.mark_point(track.track_id, frame, pixel_x=3+.2*(frame-20), pixel_y=20)
    session.compute_kinematics(track.track_id)
    return session, video.video_id, track.track_id


def _job(session, track_id, spec=None, formulas=()):
    return prepare_signal_analysis(session, SignalSelection(track_id, 'x', 20, 70),
                                   spec or FitSpec('a*t+b', (FitParameter('a'), FitParameter('b'))), formulas)


def test_nonzero_origin_and_gap_keep_actual_frames_times_and_roundtrip(signal_session, tmp_path):
    session, _, track_id = signal_session
    job = _job(session, track_id, formulas=(('inverse_slope', '1/a'), ('invalid', 't')))
    assert job.samples[0] == (20, 2., 0., 3., 0)
    after_gap = next(row for row in job.samples if row[0] == 41)
    assert after_gap[2] == pytest.approx(2.1, abs=1e-12) and after_gap[4] == 1
    before = session.project
    result = run_signal_analysis(job, Event())
    assert session.project == before
    session.apply_analysis_result(result)
    record = session.derived_data(track_id, 'function_fit_x')
    metadata = record.extra_fields['analysis']
    assert len(record.frames) == 50 and 40 not in record.frames
    assert dict(result.fit_outcome.parameter_values) == pytest.approx({'a': 2, 'b': 3}, abs=1e-7)
    converted = metadata['summary']['result_formulas']
    assert converted[0]['value'] == pytest.approx(.5, abs=1e-7)
    assert converted[1]['value'] is None and converted[1]['error']
    root = tmp_path/'saved'
    ProjectRepository().create_from_project(root, session.project)
    assert ProjectRepository().load(root).derived == session.project.derived
    assert session.undo() and session.project.derived == before.derived
    assert session.redo() and session.derived_data(track_id, 'function_fit_x') == record


def test_fit_and_recurrence_replace_independent_slots_and_unknown_extensions(signal_session):
    session, _, track = signal_session
    first = run_signal_analysis(_job(session, track), Event())
    first = replace(first, record=replace(first.record, extra_fields=first.record.extra_fields | {'future': 7}))
    session.apply_analysis_result(first)
    recurrence = run_signal_analysis(_job(session, track, RecurrenceSpec(5)), Event())
    session.apply_analysis_result(recurrence)
    assert session.derived_data(track, 'signal_recurrence_x').extra_fields['analysis']['summary']['measurement_status'] == 'insufficient_events'
    newer = run_signal_analysis(_job(session, track), Event())
    session.apply_analysis_result(newer)
    assert session.derived_data(track, 'function_fit_x').extra_fields['future'] == 7
    assert session.derived_data(track, 'signal_recurrence_x') == recurrence.record
    assert len(session.project.derived) == 6


@pytest.mark.parametrize('change', ['source_recompute', 'raw', 'target_recompute'])
def test_late_result_cannot_overwrite_changed_source_or_target(signal_session, change):
    session, _, track = signal_session
    result = run_signal_analysis(_job(session, track), Event())
    if change == 'source_recompute':
        session.compute_kinematics(track)
    elif change == 'raw':
        session.mark_point(track, 22, pixel_x=99, pixel_y=20)
    else:
        session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    before = session.project
    with pytest.raises(ProjectSessionError):
        session.apply_analysis_result(result)
    assert session.project == before


def test_source_replacement_stales_result_and_undo_restores_both(signal_session):
    session, _, track = signal_session
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    before = session.project.derived
    session.compute_kinematics(track)
    assert session.derived_data(track, 'function_fit_x').status == 'stale'
    assert session.undo() and session.project.derived == before
    session.clear_derived(track)
    assert session.project.derived == ()


def test_deleted_angular_reference_retains_stale_historical_result(signal_session):
    session, video_id, track = signal_session
    other = session.add_track(video_id, 'Reference')
    session.add_calibration(video_id, (0, 0), (100, 0), 1, unit='m')
    for frame in range(20, 71):
        session.mark_point(other.track_id, frame, pixel_x=30, pixel_y=10)
    session.compute_angular(track, reference=TwoPointReference(other.track_id))
    selection = SignalSelection(track, 'theta', 20, 70)
    spec = FitSpec('c', (FitParameter('c'),))
    session.apply_analysis_result(run_signal_analysis(prepare_signal_analysis(session, selection, spec), Event()))
    session.remove_track(other.track_id)
    record = session.derived_data(track, 'function_fit_theta')
    assert record is not None and record.status == 'stale'
    assert record.input.reference_track_id is None
    assert record.extra_fields['analysis']['source_snapshot']['input']['reference_track_id'] == str(other.track_id)


def test_future_version_is_preserved_and_not_overwritten(signal_session):
    session, _, track = signal_session
    result = run_signal_analysis(_job(session, track), Event())
    metadata = result.record.extra_fields['analysis'] | {'version': 2, 'future': {'a': 4}}
    future = replace(result.record, extra_fields={'analysis': metadata})
    session._project = replace(session.project, derived=session.project.derived+(future,))
    with pytest.raises(ProjectSessionError, match='unsupported version'):
        _job(session, track)
    assert session.derived_data(track, 'function_fit_x') == future


def test_tampered_sample_snapshot_is_rejected_atomically(signal_session):
    session, _, track = signal_session
    result = run_signal_analysis(_job(session, track), Event())
    metadata = result.record.extra_fields['analysis'] | {'samples': []}
    tampered = replace(result, record=replace(result.record, extra_fields={'analysis': metadata}))
    before = session.project
    with pytest.raises(ProjectSessionError, match='sample snapshot'):
        session.apply_analysis_result(tampered)
    assert session.project == before


def test_reopen_checks_source_freshness_from_older_writers(signal_session, tmp_path):
    session, _, track = signal_session
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    saved = session.project
    source = session.derived_data(track, 'world_position')
    from uuid import uuid4
    changed = replace(saved, derived=tuple(replace(item, derived_id=uuid4()) if item == source else item for item in saved.derived))
    repository = ProjectRepository()
    root = tmp_path / 'older-writer'
    repository.create_from_project(root, changed)
    reopened = ProjectSession.load(repository, root)
    assert reopened.derived_data(track, 'function_fit_x').status == 'stale'


def test_nested_summary_and_input_extensions_survive_replacement(signal_session):
    session, _, track = signal_session
    result = run_signal_analysis(_job(session, track), Event())
    metadata = result.record.extra_fields['analysis']
    metadata = metadata | {'summary': metadata['summary'] | {'future_metric': {'score': 8}}}
    record = replace(result.record, extra_fields={'analysis': metadata})
    session.apply_analysis_result(replace(result, record=record))
    old = session.derived_data(track, 'function_fit_x')
    old = replace(old, input=replace(old.input, extra_fields={'future_selector': 3}))
    session._project = replace(session.project, derived=tuple(old if item.kind == old.kind else item for item in session.project.derived))
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    current = session.derived_data(track, 'function_fit_x')
    assert current.extra_fields['analysis']['summary']['future_metric'] == {'score': 8}
    assert current.input.extra_fields['future_selector'] == 3


@pytest.mark.parametrize('corruption', ['unit', 'raw_with_smoothing', 'derivative_delta'])
def test_rejects_inconsistent_source_recipe_even_if_marked_valid(signal_session, corruption):
    session, _, track = signal_session
    quantity = 'vx' if corruption == 'derivative_delta' else 'x'
    source = session.derived_data(track, 'velocity' if quantity == 'vx' else 'world_position')
    if corruption == 'unit':
        changed = replace(source, unit='m')
    elif corruption == 'raw_with_smoothing':
        changed = replace(source, pipeline=session.derived_data(track, 'smoothed_position').pipeline)
    else:
        changed = replace(source, pipeline=tuple(step | {'params': step['params'] | {'delta': 1.0}}
                                                 if step['step'] == 'savitzky_golay' else step for step in source.pipeline))
    session._project = replace(session.project, derived=tuple(changed if item == source else item for item in session.project.derived))
    with pytest.raises(ProjectSessionError):
        prepare_signal_analysis(session, SignalSelection(track, quantity, 20, 70), FitSpec('c', (FitParameter('c'),)))


def test_analysis_history_never_crosses_a_raw_edit(signal_session):
    session, _, track = signal_session
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    before = session.project.observations
    assert session.can_undo_analysis and session.undo_analysis()
    assert session.derived_data(track, 'function_fit_x') is None
    assert session.can_redo_analysis and session.redo_analysis()
    assert session.project.observations == before
    session.mark_point(track, 22, pixel_x=99, pixel_y=20)
    raw = session.project
    assert not session.can_undo_analysis and not session.undo_analysis()
    assert session.project == raw and not session.can_redo_analysis


def test_result_history_does_not_undo_upstream_recomputation(signal_session):
    session, _, track = signal_session
    session.apply_analysis_result(run_signal_analysis(_job(session, track), Event()))
    session.compute_kinematics(track)
    before = session.project
    assert not session.can_undo_analysis and not session.undo_analysis()
    assert session.project == before
