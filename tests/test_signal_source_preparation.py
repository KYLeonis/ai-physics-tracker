"""自动源准备只选择所需轨迹并沿用既有原子批次契约。"""

from dataclasses import replace
from threading import Event

import pytest

from tests.test_signal_analysis_job import signal_session
from ai_physics_tracker.application.kinematics_job import SmoothingParameters, run_kinematics_job
from ai_physics_tracker.application.angular_job import run_angular_job
from ai_physics_tracker.application.project_session import ProjectSessionError
from ai_physics_tracker.application.signal_analysis_job import SignalSelection, prepare_signal_source
from ai_physics_tracker.domain.angular import PendulumReference, TwoPointReference


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


@pytest.mark.parametrize("two_point", [False, True])
def test_stale_unselected_track_uses_its_own_recorded_reference_and_smoothing(signal_session, two_point):
    session, video, track = signal_session
    session.add_calibration(video, scale_end_1_px=(0., 0.), scale_end_2_px=(10., 0.), known_length=1., unit="m")
    reference = PendulumReference((50., 0.))
    if two_point:
        other = session.add_track(video, "Reference")
        for frame in range(20, 71):
            session.mark_point(other.track_id, frame, pixel_x=20., pixel_y=10.)
        reference = TwoPointReference(other.track_id)
    session.compute_angular(track, reference=reference, window_length=9, polyorder=3)
    session.mark_point(track, 22, pixel_x=8., pixel_y=20.)
    selection = SignalSelection(track, "omega", 20, 70)
    job = prepare_signal_source(session, selection, None)
    assert job.parameters == SmoothingParameters(9, 3)
    assert job.specs[0].reference == reference
    assert len(job.inputs.tracks) == (2 if two_point else 1)
    session.apply_angular_result(run_angular_job(job, Event()))
    assert prepare_signal_source(session, selection, None) is None


@pytest.mark.parametrize("corruption", ["known_extra_step", "unit", "selection", "smoothing", "width", "frames"])
def test_stale_but_structurally_invalid_sources_are_never_overwritten(signal_session, corruption):
    session, _, track = signal_session
    source = session.derived_data(track, "velocity" if corruption == "smoothing" else "world_position")
    if corruption == "known_extra_step":
        altered = replace(source, pipeline=source.pipeline + ({"step": "angular_reference", "params": {}},))
    elif corruption == "unit":
        altered = replace(source, unit="unknown-unit")
    elif corruption == "selection":
        altered = replace(source, input=replace(source.input, extra_fields={"observation_selection": "unknown"}))
    elif corruption == "width":
        altered = replace(source, values=tuple(row + (1.,) for row in source.values))
    elif corruption == "frames":
        altered = replace(source, frames=source.frames[::-1])
    else:
        altered = replace(source, pipeline=tuple({**step, "params": {**step["params"], "delta": -1}}
                                               if step["step"] == "savitzky_golay" else step for step in source.pipeline))
    altered = replace(altered, status="stale")
    session._project = replace(session.project, derived=tuple(altered if item.derived_id == altered.derived_id else item for item in session.project.derived))
    before = session.project
    selection = SignalSelection(track, "vx" if corruption == "smoothing" else "x", 20, 70)
    with pytest.raises(ProjectSessionError, match="Source"):
        prepare_signal_source(session, selection, SmoothingParameters())
    assert session.project == before


@pytest.mark.parametrize("conflict", ["smoothing", "reference", "calibration"])
def test_conflicting_group_recipes_are_preserved_for_explicit_confirmation(signal_session, conflict):
    session, video, track = signal_session
    if conflict == "reference":
        session.add_calibration(video, scale_end_1_px=(0., 0.), scale_end_2_px=(10., 0.), known_length=1., unit="m")
        session.compute_angular(track, reference=PendulumReference((10., 0.)))
        source = session.derived_data(track, "angular_velocity")
        altered = replace(source, pipeline=tuple({**step, "params": {**step["params"], "pivot_px": [20., 0.]}}
                          if step["step"] == "angular_reference" else step for step in source.pipeline))
        quantity = "omega"
    elif conflict == "calibration":
        session.add_calibration(video, scale_end_1_px=(0., 0.), scale_end_2_px=(10., 0.), known_length=1., unit="m")
        calibrated = session.compute_kinematics(track)
        altered = next(item for item in calibrated if item.kind == "velocity")
        session.clear_derived(track)
        session._project = replace(session.project, active_calibration_by_video={})
        session.compute_kinematics(track)
        quantity = "vx"
    else:
        source = session.derived_data(track, "velocity")
        altered = replace(source, pipeline=tuple({**step, "params": {**step["params"], "window_length": 9, "polyorder": 3}}
                          if step["step"] == "savitzky_golay" else step for step in source.pipeline))
        quantity = "vx"
    session._project = replace(session.project, derived=tuple(
        replace(altered if item.kind == altered.kind else item, status="stale") for item in session.project.derived))
    before = session.project
    for parameters in (None, SmoothingParameters()):
        with pytest.raises(ProjectSessionError, match="conflicting"):
            prepare_signal_source(session, SignalSelection(track, quantity, 20, 70), parameters,
                                  PendulumReference((10., 0.)) if conflict == "reference" else None)
    assert session.project == before
