"""历史拟合尝试只读重建的应用层回归。"""

from dataclasses import asdict
import json
from pathlib import Path
from threading import Event

import pytest

from ai_physics_tracker.application.fit_attempt_view import rebuild_fit_attempt_view
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.signal_analysis_job import (
    SignalSelection,
    prepare_signal_analysis,
    run_signal_analysis,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.analysis import source_fingerprint
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


@pytest.fixture
def signal_session(tmp_path: Path):
    """沿用 test_signal_analysis_job 的 10 fps、带一帧缺测合成轨迹。"""

    session = ProjectSession.start(ProjectRepository())
    video, _ = session.register_external_video(
        tmp_path / "test.avi",
        VideoStreamInfo(640, 480, 10, 100, "synthetic", "cfr"),
    )
    track = session.add_track(video.video_id, "Measured")
    for frame in range(20, 71):
        if frame != 40:
            session.mark_point(track.track_id, frame, pixel_x=3 + .2 * (frame - 20), pixel_y=20)
    session.compute_kinematics(track.track_id)
    return session, track.track_id


def _successful_attempt(session: ProjectSession, track_id, spec=None):
    spec = spec or FitSpec("a*t+b", (FitParameter("a"), FitParameter("b")))
    selection = SignalSelection(track_id, "x", 20, 70)
    job = prepare_signal_analysis(session, selection, spec)
    result = run_signal_analysis(job, Event())
    summary = json.loads(json.dumps(asdict(result.fit_outcome), allow_nan=False))
    return (
        {
            "id": "attempt-1",
            "status": "completed",
            "track_id": str(track_id),
            "quantity": "x",
            "interval": [20, 70],
            "smoothed": False,
            "formula": spec.expression,
            "source_id": str(job.source.derived_id),
            "source_fingerprint": source_fingerprint(job.source),
            "sample_count": len(job.samples),
            "unit": job.source.unit,
            "spec": json.loads(json.dumps(asdict(spec))),
            "summary": summary,
        },
        job,
        result,
    )


def test_given_parameters_are_a_publishable_readonly_curve(signal_session):
    session, track = signal_session
    attempt, _, result = _successful_attempt(session, track, FitSpec('c', (FitParameter('c', 4, fixed=True),)))
    assert attempt['summary']['status'] == 'given_parameters'
    before = session.project

    view = rebuild_fit_attempt_view(session, attempt)

    assert view.is_available, view.reason
    assert view.prediction == pytest.approx(tuple(result.fit_outcome.prediction), rel=1e-12, abs=1e-12)
    assert session.project is before


def test_rebuilds_successful_attempt_against_current_source_without_session_changes(signal_session):
    session, track_id = signal_session
    attempt, job, result = _successful_attempt(session, track_id)
    before_project, before_dirty, before_undo = session.project, session.is_dirty, session.can_undo

    view = rebuild_fit_attempt_view(session, attempt)

    assert view.is_available
    assert view.spec == job.spec
    assert view.selection == job.selection
    assert view.samples == job.samples
    assert view.prediction == tuple(result.fit_outcome.prediction)
    assert view.residual == tuple(result.fit_outcome.residual)
    assert view.metadata["source_snapshot"]
    assert view.metadata["selection"]["track_id"] == str(track_id)
    assert view.metadata["interval"] == [20, 70]
    assert len(view.metadata["samples"]) == len(job.samples)
    assert view.metadata["spec"]["expression"] == "a*t+b"
    assert view.metadata["summary"]["prediction"] == list(view.prediction)
    assert view.metadata["summary"]["residual"] == list(view.residual)
    assert "current matching source" in view.reason
    assert (session.project, session.is_dirty, session.can_undo) == (
        before_project,
        before_dirty,
        before_undo,
    )


@pytest.mark.parametrize(
    "status,summary_status",
    [("failed", "success"), ("cancelled", "success"), ("rejected", "domain_error"), ("completed", "not_converged")],
)
def test_non_successful_attempt_never_produces_a_curve(signal_session, status, summary_status):
    session, track_id = signal_session
    attempt, _, _ = _successful_attempt(session, track_id)
    attempt["status"] = status
    attempt["summary"]["status"] = summary_status

    view = rebuild_fit_attempt_view(session, attempt)

    assert not view.is_available
    assert not view.prediction
    assert view.reason


@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("source_id", "other", "source ID"),
        ("source_fingerprint", "other", "fingerprint"),
        ("sample_count", 1, "sample count"),
        ("unit", "m", "unit"),
    ],
)
def test_source_identity_must_match_current_source(signal_session, field, value, fragment):
    session, track_id = signal_session
    attempt, _, _ = _successful_attempt(session, track_id)
    attempt[field] = value

    view = rebuild_fit_attempt_view(session, attempt)

    assert not view.is_available
    assert fragment in view.reason


@pytest.mark.parametrize(
    "parameter_values,fragment",
    [
        ([['a', 2.0]], "parameter names exactly"),
        ([['a', 2.0], ['b', float('nan')]], "finite"),
        ([['a', 2.0], ['b', 3.0], ['extra', 1.0]], "parameter names exactly"),
    ],
)
def test_bad_recorded_parameters_do_not_get_reinterpreted(signal_session, parameter_values, fragment):
    session, track_id = signal_session
    attempt, _, _ = _successful_attempt(session, track_id)
    attempt["summary"]["parameter_values"] = parameter_values

    view = rebuild_fit_attempt_view(session, attempt)

    assert not view.is_available
    assert fragment in view.reason


def test_timing_authorization_is_a_reconstruction_guard(signal_session):
    session, track_id = signal_session
    attempt, _, _ = _successful_attempt(session, track_id)
    video_id = session.tracks[0].video_id
    session._verified_videos.clear()
    before = session.project

    view = rebuild_fit_attempt_view(session, attempt)

    assert not view.is_available
    assert "timing" in view.reason.lower()
    assert session.project == before


def test_missing_spec_is_explicitly_unavailable(signal_session):
    session, track_id = signal_session
    attempt, _, _ = _successful_attempt(session, track_id)
    del attempt["spec"]

    view = rebuild_fit_attempt_view(session, attempt)

    assert view.spec is None
    assert not view.is_available
    assert "FitSpec" in view.reason


def test_parameter_errors_are_copied_only_if_recorded_without_fitting(signal_session, monkeypatch):
    from copy import deepcopy
    import ai_physics_tracker.domain.function_fit as fitting
    session, track = signal_session
    attempt, _, _ = _successful_attempt(session, track)
    expected = deepcopy(attempt['summary']['parameter_uncertainty'])
    def unexpected_fit(*_args, **_kwargs):
        pytest.fail('History must not refit to compute parameter errors')
    monkeypatch.setattr(fitting, 'fit_function', unexpected_fit)
    before = session.project
    view = rebuild_fit_attempt_view(session, attempt)
    assert view.is_available
    assert view.metadata['summary']['parameter_uncertainty'] == expected
    del attempt['summary']['parameter_uncertainty']
    legacy = rebuild_fit_attempt_view(session, attempt)
    assert legacy.is_available
    assert 'parameter_uncertainty' not in legacy.metadata['summary']
    assert session.project is before
