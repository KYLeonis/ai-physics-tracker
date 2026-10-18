"""R04完整分析链路：无会话计算、同一发布校验、输入隔离和资格事实。"""

import ast
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
from threading import Event

import pytest

from tests.test_signal_analysis_job import signal_session
from ai_physics_tracker.application.analysis_readiness import assess_signal_source
from ai_physics_tracker.application.angular_job import AngularSpec, prepare_angular_job, run_angular_job
from ai_physics_tracker.application.kinematics_job import SmoothingParameters, prepare_kinematics_job, run_kinematics_job
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.signal_analysis_job import SignalSelection, prepare_signal_source
from ai_physics_tracker.domain.angular import PendulumReference


def _prepare(session, video_id, track_id, family):
    if family == 'angular':
        session.add_calibration(video_id, (0, 0), (10, 0), 1, 'm')
        reference = PendulumReference((0., 0.))
        return prepare_angular_job(session, video_id, (AngularSpec(track_id, reference),), SmoothingParameters()), run_angular_job
    return prepare_kinematics_job(session, video_id, (track_id,), SmoothingParameters()), run_kinematics_job


@pytest.mark.parametrize('family', ['linear', 'angular'])
def test_all_source_entry_points_compute_without_detached_sessions_or_writes(signal_session, monkeypatch, family):
    session, video, track = signal_session

    def forbidden(*args, **kwargs):
        raise AssertionError('Computation must not create a temporary session')

    monkeypatch.setattr(ProjectSession, 'detached', forbidden)
    job, run = _prepare(session, video, track, family)
    assert 'snapshot' not in {field.name for field in fields(job)}
    before, undo, redo = session.project, tuple(session._undo_stack), tuple(session._redo_stack)
    result = run(job, Event())
    assert session.project == before
    assert tuple(session._undo_stack) == undo and tuple(session._redo_stack) == redo
    if family == 'angular':
        session.apply_angular_result(result)
        expected = session.compute_angular(track, reference=job.specs[0].reference)
    else:
        session.apply_kinematics_result(result)
        expected = session.compute_kinematics(track)
    for item, current in zip(result.records, expected, strict=True):
        assert item.values == current.values and item.pipeline == current.pipeline
        assert item.frames == current.frames and item.unit == current.unit
    selection = SignalSelection(track, 'theta' if family == 'angular' else 'x', 20, 70)
    assert prepare_signal_source(session, selection, None) is None


@pytest.mark.parametrize('family', ['linear', 'angular'])
def test_synchronous_compute_rejects_incomplete_candidate_atomically(signal_session, monkeypatch, family):
    session, video, track = signal_session
    job, _ = _prepare(session, video, track, family)
    if family == 'angular':
        import ai_physics_tracker.application.angular_job as jobs
        name = 'compute_angular_records'
        compute = lambda: session.compute_angular(track, reference=job.specs[0].reference)
    else:
        import ai_physics_tracker.application.kinematics_job as jobs
        name = 'compute_kinematics_records'
        compute = lambda: session.compute_kinematics(track)
    original = getattr(jobs, name)
    monkeypatch.setattr(jobs, name, lambda *args: original(*args)[:3])
    before, undo, redo = session.project, tuple(session._undo_stack), tuple(session._redo_stack)
    with pytest.raises(ProjectSessionError, match='Incomplete analysis batch'):
        compute()
    assert session.project == before
    assert tuple(session._undo_stack) == undo and tuple(session._redo_stack) == redo


@pytest.mark.parametrize('family', ['linear', 'angular'])
def test_job_input_metadata_does_not_share_mutable_fields_with_active_session(signal_session, family):
    session, video, track = signal_session
    job, _ = _prepare(session, video, track, family)
    before = deepcopy(session.project)
    values = (job.inputs.video, job.inputs.timeline, *job.inputs.tracks, *job.inputs.points)
    if job.inputs.calibration is not None:
        values += (job.inputs.calibration,)
    for value in values:
        value.extra_fields['future'] = {'nested': [1, 2]}
    assert session.project == before


def test_source_assessment_separates_ready_preparable_and_blocked_without_writing(signal_session):
    session, video, track = signal_session
    selection = SignalSelection(track, 'x', 20, 70)
    before, undo = session.project, tuple(session._undo_stack)
    ready = assess_signal_source(session, video, selection, None)
    assert ready.ready and ready.preparation is None and not ready.reason
    assert session.project == before and tuple(session._undo_stack) == undo
    session.clear_derived(track)
    before = session.project
    prepare = assess_signal_source(session, video, selection, None)
    assert not prepare.ready and prepare.preparation is not None
    assert not prepare.source_issue and not prepare.availability_issue
    assert 'updating' in prepare.reason
    assert session.project == before
    angular = assess_signal_source(session, video, replace(selection, quantity='theta'), SmoothingParameters())
    assert not angular.ready and angular.source_issue and angular.preparation is None
    assert 'calibration' in angular.reason


def test_source_assessment_does_not_allow_unknown_cached_recipe(signal_session):
    session, video, track = signal_session
    source = session.derived_data(track, 'world_position')
    changed = replace(source, pipeline=source.pipeline+({'step':'future', 'params':{}},))
    session._project = replace(session.project, derived=tuple(changed if item == source else item for item in session.project.derived))
    before = session.project
    state = assess_signal_source(session, video, SignalSelection(track, 'x', 20, 70), None)
    assert not state.ready and state.source_issue and state.preparation is None
    assert 'unsupported recipe' in state.reason
    assert session.project == before


def test_motion_computation_has_no_session_gui_or_file_dependencies():
    path = Path(__file__).parents[1]/'src/ai_physics_tracker/application/motion_computation.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert all(not any(part in name for part in ('project_session', 'gui', 'infrastructure')) for name in imports)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names.intersection({'ProjectSession', 'open', 'TrackStore'})
