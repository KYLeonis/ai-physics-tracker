"""角运动后台批次的快照、取消、迟到拒绝与原子提交回归（phase-6.1 AC-5）。"""

from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import UUID

import pytest

from ai_physics_tracker.application.angular_job import (
    AngularSpec,
    prepare_angular_job,
    run_angular_job,
)
from ai_physics_tracker.application.kinematics_job import (
    SmoothingParameters,
    prepare_kinematics_job,
    run_kinematics_job,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.angular import PendulumReference, TwoPointReference
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

FPS = 10.0


def _info() -> VideoStreamInfo:
    return VideoStreamInfo(640, 480, FPS, 60, "synthetic", "cfr")


def _calibrated_session_with_two_tracks(tmp_path: Path):
    session = ProjectSession.start(ProjectRepository())
    video, _timeline = session.register_external_video(tmp_path / "clip.avi", _info())
    track_a = session.add_track(video.video_id, "Rod A")
    track_b = session.add_track(video.video_id, "Rod B")
    session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
        origin_px=(100.0, 1000.0),
        set_active=True,
    )
    for f in range(12):
        session.mark_point(track_a.track_id, f, pixel_x=100.0 + 3.0 * f, pixel_y=1000.0)
        session.mark_point(track_b.track_id, f, pixel_x=200.0 + 3.0 * f, pixel_y=900.0 - 2.0 * f)
    return session, video.video_id, track_a.track_id, track_b.track_id


ANGULAR_KINDS = (
    "angular_position",
    "smoothed_angular_position",
    "angular_velocity",
    "angular_acceleration",
)


def test_angular_batch_computes_four_kinds_and_is_one_undo(tmp_path: Path) -> None:
    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    job = prepare_angular_job(
        session,
        video_id,
        (AngularSpec(track_a, TwoPointReference(reference_track_id=track_b)),),
        SmoothingParameters(),
    )

    result = run_angular_job(job, Event())

    # worker不持有Session；活动会话提交前无部分结果
    assert session.project.derived == ()
    assert {(r.track_id, r.kind) for r in result.records} == {
        (track_a, kind) for kind in ANGULAR_KINDS
    }
    assert all(r.extra_fields["timing_context"]["fps_nominal"] == FPS for r in result.records)

    session.apply_angular_result(result)
    assert len(session.project.derived) == 4
    assert session.undo()
    assert session.project.derived == ()
    assert session.project.observations
    assert session.redo()
    assert len(session.project.derived) == 4


def test_angular_batch_keeps_existing_kinematics_records(tmp_path: Path) -> None:
    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    session.compute_kinematics(track_a)

    job = prepare_angular_job(
        session,
        video_id,
        (AngularSpec(track_a, TwoPointReference(reference_track_id=track_b)),),
        SmoothingParameters(),
    )
    session.apply_angular_result(run_angular_job(job, Event()))

    kinds = {(r.track_id, r.kind) for r in session.project.derived}
    assert kinds == {(track_a, kind) for kind in ANGULAR_KINDS} | {
        (track_a, kind)
        for kind in ("world_position", "smoothed_position", "velocity", "acceleration")
    }


def test_incomplete_angular_batch_rejected_without_partial_commit(tmp_path: Path) -> None:
    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    job = prepare_angular_job(
        session,
        video_id,
        (AngularSpec(track_a, TwoPointReference(reference_track_id=track_b)),),
        SmoothingParameters(),
    )
    result = run_angular_job(job, Event())
    tampered = replace(result, records=result.records[:3])

    with pytest.raises(ProjectSessionError, match="Incomplete analysis batch"):
        session.apply_angular_result(tampered)
    assert session.project.derived == ()


def test_reference_track_change_rejects_late_result(tmp_path: Path) -> None:
    """计算期间参考轨迹的观测被编辑 → 迟到结果整体拒绝。"""

    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    job = prepare_angular_job(
        session,
        video_id,
        (AngularSpec(track_a, TwoPointReference(reference_track_id=track_b)),),
        SmoothingParameters(),
    )
    result = run_angular_job(job, Event())

    session.mark_point(track_b, 30, pixel_x=11.0, pixel_y=22.0)
    before = session.project

    with pytest.raises(ProjectSessionError, match="inputs changed"):
        session.apply_angular_result(result)
    assert session.project == before
    assert session.project.derived == ()
    assert session.manual_points(track_b)[-1].frame_index == 30


def test_cancelling_between_specs_discards_partial_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    specs = (
        AngularSpec(track_a, TwoPointReference(reference_track_id=track_b)),
        AngularSpec(track_b, PendulumReference(pivot_px=(100.0, 1000.0))),
    )
    job = prepare_angular_job(session, video_id, specs, SmoothingParameters())
    import ai_physics_tracker.application.angular_job as jobs
    original_compute = jobs.compute_angular_records
    cancel = Event()
    calls: list[UUID] = []

    def cancel_after_first(inputs, track_id: UUID, reference, parameters):
        calls.append(track_id)
        result = original_compute(inputs, track_id, reference, parameters)
        cancel.set()
        return result

    monkeypatch.setattr(jobs, "compute_angular_records", cancel_after_first)

    with pytest.raises(CancelledError):
        run_angular_job(job, cancel)

    assert calls == [track_a]
    assert session.project.derived == ()


def test_prepare_rejects_duplicate_targets_and_self_reference(tmp_path: Path) -> None:
    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    with pytest.raises(ProjectSessionError, match="distinct tracks"):
        prepare_angular_job(
            session,
            video_id,
            (
                AngularSpec(track_a, PendulumReference(pivot_px=(1.0, 1.0))),
                AngularSpec(track_a, PendulumReference(pivot_px=(2.0, 2.0))),
            ),
            SmoothingParameters(),
        )
    with pytest.raises(ProjectSessionError, match="differ from the target track"):
        prepare_angular_job(
            session,
            video_id,
            (AngularSpec(track_a, TwoPointReference(reference_track_id=track_a)),),
            SmoothingParameters(),
        )
    with pytest.raises(ProjectSessionError, match="at least one angular spec"):
        prepare_angular_job(session, video_id, (), SmoothingParameters())


def test_prepare_fails_fast_without_active_calibration(tmp_path: Path) -> None:
    """R1 首版要求有效标定：prepare 阶段拒绝，而非 worker 内逐规格失败。"""

    session = ProjectSession.start(ProjectRepository())
    video, _timeline = session.register_external_video(tmp_path / "clip.avi", _info())
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, pixel_x=100.0, pixel_y=1000.0)

    with pytest.raises(ProjectSessionError, match="active calibration"):
        prepare_angular_job(
            session,
            video.video_id,
            (AngularSpec(track.track_id, PendulumReference(pivot_px=(1.0, 1.0))),),
            SmoothingParameters(),
        )


def test_extra_fields_survive_angular_batch_replace_and_roundtrip(
    tmp_path: Path,
) -> None:
    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    session.compute_angular(
        track_a, reference=TwoPointReference(reference_track_id=track_b)
    )
    session._project = replace(
        session.project,
        derived=tuple(
            replace(
                item,
                extra_fields={"plugin_record": {"keep": True}},
                input=replace(item.input, extra_fields={"plugin_input": "keep"}),
            )
            for item in session.project.derived
        ),
    )

    job = prepare_angular_job(
        session,
        video_id,
        (AngularSpec(track_a, TwoPointReference(reference_track_id=track_b)),),
        SmoothingParameters(),
    )
    session.apply_angular_result(run_angular_job(job, Event()))

    omega = session.derived_data(track_a, "angular_velocity")
    assert omega is not None
    assert omega.extra_fields["plugin_record"] == {"keep": True}
    assert omega.input.extra_fields["plugin_input"] == "keep"
    assert omega.input.reference_track_id == track_b

    session.save_as(tmp_path / "angular-extras")
    loaded = ProjectSession.load(ProjectRepository(), tmp_path / "angular-extras")
    loaded_omega = loaded.derived_data(track_a, "angular_velocity")
    assert loaded_omega is not None
    assert loaded_omega.extra_fields["plugin_record"] == {"keep": True}
    assert loaded_omega.input.extra_fields["plugin_input"] == "keep"
    assert loaded_omega.input.reference_track_id == track_b


def test_detached_snapshot_saving_keeps_raw_points_before_commit(tmp_path: Path) -> None:
    session, video_id, track_a, track_b = _calibrated_session_with_two_tracks(tmp_path)
    job = prepare_angular_job(
        session,
        video_id,
        (AngularSpec(track_a, TwoPointReference(reference_track_id=track_b)),),
        SmoothingParameters(),
    )
    result = run_angular_job(job, Event())

    saved_copy = session.detached()
    saved_copy.save_as(tmp_path / "saved-copy")
    session.apply_angular_result(result)

    loaded = ProjectSession.load(ProjectRepository(), tmp_path / "saved-copy")
    assert loaded.project.observations == session.project.observations
    assert loaded.project.derived == ()
    assert len(session.project.derived) == 4


def test_old_angular_batch_cannot_replace_new_reference_result(tmp_path: Path) -> None:
    session, video_id, a, b = _calibrated_session_with_two_tracks(tmp_path)
    job = prepare_angular_job(session, video_id,
        (AngularSpec(a, PendulumReference((100, 1000))),), SmoothingParameters())
    old = run_angular_job(job, Event())
    session.compute_angular(a, reference=PendulumReference((100, 999)))
    before = session.project
    with pytest.raises(ProjectSessionError, match="results changed"):
        session.apply_angular_result(old)
    assert session.project == before


def test_unrelated_analysis_family_and_reference_result_do_not_block_batch(tmp_path: Path) -> None:
    session, video_id, a, b = _calibrated_session_with_two_tracks(tmp_path)
    job = prepare_angular_job(session, video_id,
        (AngularSpec(a, TwoPointReference(b)),), SmoothingParameters())
    result = run_angular_job(job, Event())
    session.compute_kinematics(a)
    reference_records = session.compute_angular(b, reference=PendulumReference((100, 1000)))
    session.apply_angular_result(result)
    assert all(item in session.project.derived for item in reference_records)
    assert len(session.project.derived) == 12


@pytest.mark.parametrize("changed", ["reference", "inputs", "specs", "pivot", "smoothing"])
def test_mismatched_angular_result_is_rejected_atomically(tmp_path: Path, changed: str) -> None:
    from ai_physics_tracker.application.kinematics_job import analysis_inputs
    session, video_id, a, b = _calibrated_session_with_two_tracks(tmp_path)
    c = session.add_track(video_id, "Unrelated C").track_id
    job = prepare_angular_job(session, video_id,
        (AngularSpec(a, TwoPointReference(b)),), SmoothingParameters())
    result = run_angular_job(job, Event())
    if changed == "reference":
        result = replace(result, records=tuple(replace(item,
            input=replace(item.input, reference_track_id=c)) for item in result.records))
    elif changed == "inputs":
        result = replace(result, inputs=analysis_inputs(session, video_id, (c,)))
    elif changed == "specs":
        result = replace(result, specs=())
    elif changed == "pivot":
        result = replace(result, specs=(AngularSpec(a, PendulumReference((100, 999))),))
    else:
        result = replace(result, parameters=SmoothingParameters(5, 2))
    before = session.project
    with pytest.raises(ProjectSessionError):
        session.apply_angular_result(result)
    assert session.project == before


@pytest.mark.parametrize("change", ["wrong_id", "duplicate", "missing"])
def test_angular_batch_rejects_wrong_calibration_recipe(tmp_path: Path, change: str) -> None:
    session, video_id, a, b = _calibrated_session_with_two_tracks(tmp_path)
    job = prepare_angular_job(session, video_id, (AngularSpec(a, TwoPointReference(b)),), SmoothingParameters())
    result = run_angular_job(job, Event())
    bad = {"step": "calibration_transform", "params": {"calibration_id": "00000000-0000-0000-0000-000000000000"}}
    def pipeline(item):
        if change == "duplicate": return (item.pipeline[0], *item.pipeline)
        if change == "missing": return item.pipeline[1:]
        return (bad, *item.pipeline[1:])
    result = replace(result, records=tuple(replace(item, pipeline=pipeline(item)) for item in result.records))
    before = session.project
    with pytest.raises(ProjectSessionError, match="calibration pipeline"):
        session.apply_angular_result(result)
    assert session.project == before
