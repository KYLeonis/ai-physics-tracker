"""自动源准备只选择所需轨迹并沿用既有原子批次契约。"""

from dataclasses import replace
from threading import Event

import pytest

from tests.test_signal_analysis_job import signal_session
from ai_physics_tracker.application.kinematics_job import SmoothingParameters, run_kinematics_job
from ai_physics_tracker.application.angular_job import run_angular_job
from ai_physics_tracker.application.project_session import ProjectSessionError
from ai_physics_tracker.application.signal_analysis_job import SignalSelection, prepare_signal_source
from ai_physics_tracker.domain.angular import PendulumReference


def test_fresh_source_is_reused_without_writing(signal_session):
    session, _, track = signal_session
    before = session.project
    assert prepare_signal_source(session, SignalSelection(track, "x", 20, 70), SmoothingParameters()) is None
    assert session.project == before


def test_missing_source_is_detached_and_late_batch_cannot_overwrite_new_result(signal_session):
    session, _, track = signal_session
    session.clear_derived(track)
    before = session.project
    job = prepare_signal_source(session, SignalSelection(track, "x", 20, 70), SmoothingParameters())
    result = run_kinematics_job(job, Event())
    assert session.project == before
    session.compute_kinematics(track)
    with pytest.raises(ProjectSessionError, match="results changed"):
        session.apply_kinematics_result(result)
    assert all(item.derived_id not in {record.derived_id for record in result.records} for item in session.project.derived)


def test_requested_sg_settings_only_recompute_sources_that_use_smoothing(signal_session):
    session, _, track = signal_session
    changed = SmoothingParameters(9, 3)
    assert prepare_signal_source(session, SignalSelection(track, "x", 20, 70), changed) is None
    job = prepare_signal_source(session, SignalSelection(track, "vx", 20, 70), changed)
    assert job.parameters == changed
    session.apply_kinematics_result(run_kinematics_job(job, Event()))
    assert prepare_signal_source(session, SignalSelection(track, "vx", 20, 70), changed) is None


def test_unknown_sibling_recipe_is_preserved_when_selected_source_is_missing(signal_session):
    session, _, track = signal_session
    unknown = replace(session.derived_data(track, "velocity"), pipeline=({"step": "future_method", "params": {}},))
    session._project = replace(session.project, derived=(unknown,))
    before = session.project
    with pytest.raises(ProjectSessionError, match="unsupported recipes"):
        prepare_signal_source(session, SignalSelection(track, "x", 20, 70), SmoothingParameters())
    assert session.project == before


def test_angular_source_uses_only_confirmed_reference_and_can_be_reused(signal_session):
    session, video, track = signal_session
    selection = SignalSelection(track, "theta", 20, 70)
    with pytest.raises(ProjectSessionError, match="applied reference"):
        prepare_signal_source(session, selection, SmoothingParameters())
    reference = PendulumReference((0., 0.))
    with pytest.raises(ProjectSessionError, match="calibration"):
        prepare_signal_source(session, selection, SmoothingParameters(), reference)
    session.add_calibration(video, scale_end_1_px=(0., 0.), scale_end_2_px=(10., 0.), known_length=1., unit="m")
    job = prepare_signal_source(session, selection, SmoothingParameters(), reference)
    session.apply_angular_result(run_angular_job(job, Event()))
    assert prepare_signal_source(session, selection, SmoothingParameters(), reference) is None
    changed = PendulumReference((10., 0.))
    assert prepare_signal_source(session, selection, SmoothingParameters(), changed).specs[0].reference == changed


def test_interval_and_timing_are_checked_before_any_source_computation(signal_session):
    session, video, track = signal_session
    before = session.project
    with pytest.raises(ProjectSessionError, match="working zone"):
        prepare_signal_source(session, SignalSelection(track, "x", 0, 1000), SmoothingParameters())
    session._verified_videos.clear()
    with pytest.raises(ProjectSessionError, match="timing"):
        prepare_signal_source(session, SignalSelection(track, "x", 20, 70), SmoothingParameters())
    assert session.project == before
