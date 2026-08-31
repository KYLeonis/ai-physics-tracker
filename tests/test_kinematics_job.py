"""运动学后台批次的快照、校验与原子提交回归。"""

from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.kinematics_job import (
    SmoothingParameters,
    prepare_kinematics_job,
    run_kinematics_job,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.project_media import ProjectMediaService
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _info(*, fps: float = 10.0, frame_count: int = 12) -> VideoStreamInfo:
    return VideoStreamInfo(64, 48, fps, frame_count, "synthetic", "cfr")


def _session_with_tracks(
    tmp_path: Path,
    *,
    track_count: int = 2,
    frames: range = range(9),
) -> tuple[ProjectSession, UUID, tuple[Track, ...]]:
    session = ProjectSession.start(ProjectRepository())
    video, _timeline = session.register_external_video(tmp_path / "clip.avi", _info())
    tracks = tuple(session.add_track(video.video_id) for _ in range(track_count))
    for track_offset, track in enumerate(tracks):
        for frame_index in frames:
            session.mark_point(
                track.track_id,
                frame_index,
                pixel_x=10.0 + frame_index + track_offset,
                pixel_y=20.0 + 2.0 * frame_index,
            )
    return session, video.video_id, tracks


def test_batch_computes_four_kinds_per_track_and_is_one_undo(
    tmp_path: Path,
) -> None:
    session, video_id, tracks = _session_with_tracks(tmp_path)
    track_ids = tuple(track.track_id for track in tracks)
    job = prepare_kinematics_job(
        session,
        video_id,
        track_ids,
        SmoothingParameters(),
    )

    result = run_kinematics_job(job, Event())

    # worker 只写 detached snapshot，活动会话在提交前不应出现部分结果。
    assert session.project.derived == ()
    assert len(result.records) == 8
    assert {
        (record.track_id, record.kind) for record in result.records
    } == {
        (track_id, kind)
        for track_id in track_ids
        for kind in ("world_position", "smoothed_position", "velocity", "acceleration")
    }

    session.apply_kinematics_result(result)
    assert len(session.project.derived) == 8
    assert session.undo()
    assert session.project.derived == ()
    assert session.project.observations
    assert session.redo()
    assert len(session.project.derived) == 8


def test_failed_batch_never_commits_partial_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, video_id, tracks = _session_with_tracks(tmp_path)
    job = prepare_kinematics_job(
        session,
        video_id,
        tuple(track.track_id for track in tracks),
        SmoothingParameters(),
    )
    original_compute = job.snapshot.compute_kinematics

    def fail_on_second_track(track_id: UUID, *, window_length: int, polyorder: int):
        if track_id == tracks[1].track_id:
            raise RuntimeError("synthetic second-track failure")
        return original_compute(
            track_id,
            window_length=window_length,
            polyorder=polyorder,
        )

    monkeypatch.setattr(job.snapshot, "compute_kinematics", fail_on_second_track)

    with pytest.raises(RuntimeError, match="second-track"):
        run_kinematics_job(job, Event())

    assert session.project.derived == ()


def test_cancelling_between_tracks_discards_first_track_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, video_id, tracks = _session_with_tracks(tmp_path)
    job = prepare_kinematics_job(
        session,
        video_id,
        tuple(track.track_id for track in tracks),
        SmoothingParameters(),
    )
    original_compute = job.snapshot.compute_kinematics
    cancel = Event()
    calls = 0

    def cancel_after_first(track_id: UUID, *, window_length: int, polyorder: int):
        nonlocal calls
        calls += 1
        result = original_compute(
            track_id,
            window_length=window_length,
            polyorder=polyorder,
        )
        cancel.set()
        return result

    monkeypatch.setattr(job.snapshot, "compute_kinematics", cancel_after_first)

    with pytest.raises(CancelledError):
        run_kinematics_job(job, cancel)

    assert calls == 1
    assert session.project.derived == ()


def test_input_change_rejects_late_result_without_touching_current_project(
    tmp_path: Path,
) -> None:
    session, video_id, tracks = _session_with_tracks(tmp_path, track_count=1)
    track_id = tracks[0].track_id
    job = prepare_kinematics_job(session, video_id, (track_id,), SmoothingParameters())
    result = run_kinematics_job(job, Event())

    session.mark_point(track_id, 9, pixel_x=99.0, pixel_y=88.0)
    before = session.project

    with pytest.raises(ProjectSessionError, match="inputs changed"):
        session.apply_kinematics_result(result)

    assert session.project == before
    assert session.project.derived == ()
    assert session.manual_points(track_id)[-1].frame_index == 9


def test_saving_detached_copy_does_not_lose_raw_points_before_result_commit(
    tmp_path: Path,
) -> None:
    session, video_id, tracks = _session_with_tracks(tmp_path, track_count=1)
    track_id = tracks[0].track_id
    job = prepare_kinematics_job(session, video_id, (track_id,), SmoothingParameters())
    result = run_kinematics_job(job, Event())

    saved_copy = session.detached()
    saved_copy.save_as(tmp_path / "saved-copy")
    session.apply_kinematics_result(result)

    loaded = ProjectSession.load(ProjectRepository(), tmp_path / "saved-copy")
    assert loaded.project.observations == session.project.observations
    assert loaded.project.observations == saved_copy.project.observations
    assert loaded.project.derived == ()
    assert len(session.project.derived) == 4


def test_unknown_derived_kind_and_existing_extra_fields_survive_batch_replace(
    tmp_path: Path,
) -> None:
    session, video_id, tracks = _session_with_tracks(tmp_path, track_count=1)
    track_id = tracks[0].track_id
    session.compute_kinematics(track_id)
    existing = tuple(
        replace(
            item,
            extra_fields={"plugin_record": {"keep": True}},
            input=replace(item.input, extra_fields={"plugin_input": "keep"}),
        )
        for item in session.project.derived
    )
    custom = replace(
        existing[0],
        derived_id=uuid4(),
        kind="custom",
        extra_fields={"custom_field": [1, "keep"]},
        input=replace(existing[0].input, extra_fields={"custom_input": 42}),
    )
    session._project = replace(session.project, derived=(*existing, custom))

    job = prepare_kinematics_job(session, video_id, (track_id,), SmoothingParameters())
    result = run_kinematics_job(job, Event())
    session.apply_kinematics_result(result)

    custom_after = next(item for item in session.project.derived if item.kind == "custom")
    velocity = session.derived_data(track_id, "velocity")
    assert custom_after == custom
    assert velocity is not None
    assert velocity.extra_fields["plugin_record"] == {"keep": True}
    assert velocity.input.extra_fields["plugin_input"] == "keep"

    session.save_as(tmp_path / "with-custom")
    loaded = ProjectSession.load(ProjectRepository(), tmp_path / "with-custom")
    loaded_custom = next(item for item in loaded.project.derived if item.kind == "custom")
    loaded_velocity = loaded.derived_data(track_id, "velocity")
    assert loaded_custom.extra_fields == custom.extra_fields
    assert loaded_custom.input.extra_fields == custom.input.extra_fields
    assert loaded_velocity is not None
    assert loaded_velocity.extra_fields["plugin_record"] == {"keep": True}
    assert loaded_velocity.input.extra_fields["plugin_input"] == "keep"


def test_first_active_calibration_marks_existing_pixel_results_stale(
    tmp_path: Path,
) -> None:
    session, video_id, tracks = _session_with_tracks(tmp_path, track_count=1)
    track_id = tracks[0].track_id
    session.compute_kinematics(track_id)
    assert all(item.status == "valid" and item.calibration_ref is None for item in session.project.derived)

    session.add_calibration(
        video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
    )

    assert all(item.status == "stale" for item in session.project.derived)
    assert all(item.unit in {"px", "px/s", "px/s²"} for item in session.project.derived)
    assert all(item.calibration_ref is None for item in session.project.derived)


def test_smoothing_parameters_reject_invalid_window_or_order() -> None:
    for window_length, polyorder in ((8, 2), (7, 1), (7, 7), (3, 3)):
        with pytest.raises(ValueError):
            SmoothingParameters(window_length, polyorder)
    assert SmoothingParameters(7, 2) == SmoothingParameters()


def test_missing_video_revokes_detached_timing_authorization_before_batch_prepare(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    session = ProjectSession.start(repository)
    video, _timeline = session.register_external_video(
        tmp_path / "not-present.avi", _info()
    )
    track = session.add_track(video.video_id)
    candidate = session.detached()
    service = ProjectMediaService(repository, lambda: None, object())

    prepared = service.select_video(candidate, video.video_id, Event())

    assert prepared.snapshot is None
    assert prepared.decoder is None
    assert not candidate.can_measure(video.video_id)
    with pytest.raises(ProjectSessionError, match="timing is not authorized"):
        prepare_kinematics_job(
            candidate,
            video.video_id,
            (track.track_id,),
            SmoothingParameters(),
        )
