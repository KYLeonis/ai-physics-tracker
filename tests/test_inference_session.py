"""推理观测批量导入、融合解析与运动学输入衔接测试。"""

from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.kinematics_job import (
    SmoothingParameters,
    analysis_inputs,
    prepare_kinematics_job,
    run_kinematics_job,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_completed,
    mark_run_running,
)
from ai_physics_tracker.domain.track_store import BatchWriteResult
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _session_with_track(tmp_path: Path) -> tuple[ProjectSession, UUID, UUID, Timeline]:
    session = ProjectSession.start(ProjectRepository())
    video, timeline = session.register_external_video(
        tmp_path / "clip.mp4",
        VideoStreamInfo(64, 48, 10.0, 8, "synthetic", "cfr"),
    )
    track = session.add_track(video.video_id, "Target")
    return session, video.video_id, track.track_id, timeline


def _running_infer_run(
    session: ProjectSession,
    video_id: UUID,
    track_id: UUID,
    *,
    source_detail: str | None = None,
) -> TrackingRun:
    run = create_tracking_run(
        video_id=video_id,
        track_id=track_id,
        task_type="infer",
        source_detail=source_detail,
        config={"frame_range": [0, 7], "min_confidence": 0.5},
    )
    session.record_tracking_run(run)
    running = mark_run_running(run)
    session.update_tracking_run(running)
    return running


def _engine_point(
    run: TrackingRun,
    timeline: Timeline,
    frame_index: int,
    *,
    pixel_x: float = 10.0,
    pixel_y: float = 20.0,
    time_s: float | None = None,
) -> TrackPoint:
    now = utc_now()
    return TrackPoint(
        point_id=uuid4(),
        track_id=run.track_id,
        frame_index=frame_index,
        time_s=(frame_to_time(frame_index, timeline) if time_s is None else time_s),
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        source=run.engine,
        source_detail=run.source_detail,
        confidence=0.9,
        visibility="unknown",
        status="active",
        created_at=now,
        modified_at=now,
    )


def test_import_preserves_manual_points_and_records_summary(
    tmp_path: Path,
) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    manual = session.mark_point(track_id, 0, 100.0, 200.0)
    run = _running_infer_run(session, video_id, track_id, source_detail="dlc:infer:one")
    completed = replace(
        mark_run_completed(run),
        extra_fields={"import_summary": {"parsed": 3}, "output_path": "raw.h5"},
    )

    result = session.import_engine_points(
        tuple(_engine_point(run, timeline, frame, pixel_x=frame) for frame in (0, 1, 2)),
        completed,
    )

    assert (result.inserted, result.skipped) == (2, 1)
    assert session.effective_points(track_id)[0] == manual
    assert [point.frame_index for point in session.effective_points(track_id)] == [0, 1, 2]
    stored_engine = [
        point for point in session.project.observations if point.source == "dlc"
    ]
    assert [point.frame_index for point in stored_engine] == [1, 2]
    stored_run = session.tracking_runs()[0]
    assert stored_run.status == "completed"
    assert stored_run.extra_fields["output_path"] == "raw.h5"
    assert stored_run.extra_fields["import_summary"] == {
        "parsed": 3,
        "inserted": 2,
        "skipped": 1,
    }


def test_import_first_wins_old_ai_and_manual_correction_chain(
    tmp_path: Path,
) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    first = _running_infer_run(session, video_id, track_id, source_detail="dlc:infer:first")
    first_done = mark_run_completed(first)
    first_point = _engine_point(first, timeline, 2, pixel_x=12.0)
    session.import_engine_points((first_point,), first_done)

    second = _running_infer_run(session, video_id, track_id, source_detail="dlc:infer:second")
    second_done = mark_run_completed(second)
    second_point = _engine_point(second, timeline, 2, pixel_x=99.0)
    new_point = _engine_point(second, timeline, 3, pixel_x=13.0)
    result = session.import_engine_points((second_point, new_point), second_done)

    assert (result.inserted, result.skipped) == (1, 1)
    assert session.effective_point(track_id, 2) == first_point

    manual = session.mark_point(track_id, 2, 77.0, 88.0)
    assert session.effective_point(track_id, 2) == manual
    preserved = next(
        point for point in session.project.observations
        if point.point_id == first_point.point_id
    )
    assert preserved.status == "superseded"
    assert preserved.superseded_by == manual.point_id


def test_invalid_engine_batch_is_atomic_and_requires_matching_running_run(
    tmp_path: Path,
) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    run = _running_infer_run(session, video_id, track_id)
    completed = mark_run_completed(run)
    valid = _engine_point(run, timeline, 1)
    invalid = _engine_point(run, timeline, 2, time_s=123.0)
    before_project = session.project
    before_undo = len(session._undo_stack)
    before_redo = len(session._redo_stack)

    with pytest.raises(ProjectSessionError, match="time"):
        session.import_engine_points((valid, invalid), completed)

    assert session.project == before_project
    assert session.project.observations == ()
    assert len(session._undo_stack) == before_undo
    assert len(session._redo_stack) == before_redo

    with pytest.raises(ProjectSessionError, match="configuration"):
        session.import_engine_points(
            (valid,),
            replace(completed, config={"different": True}),
        )
    assert session.tracking_runs()[0].status == "running"


def test_all_skipped_or_empty_import_only_updates_run(
    tmp_path: Path,
) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    first = _running_infer_run(session, video_id, track_id, source_detail="dlc:infer:first")
    session.import_engine_points(
        (_engine_point(first, timeline, 1),),
        mark_run_completed(first),
    )
    before_undo = len(session._undo_stack)
    before_redo = len(session._redo_stack)
    before_derived = session.project.derived

    skipped_run = _running_infer_run(session, video_id, track_id, source_detail="dlc:infer:skip")
    skipped = session.import_engine_points(
        (_engine_point(skipped_run, timeline, 1),),
        mark_run_completed(skipped_run),
    )
    empty_run = _running_infer_run(session, video_id, track_id, source_detail="dlc:infer:empty")
    empty = session.import_engine_points((), mark_run_completed(empty_run))

    assert skipped == BatchWriteResult(inserted=0, skipped=1)
    assert empty == BatchWriteResult(inserted=0, skipped=0)
    assert len(session._undo_stack) == before_undo
    assert len(session._redo_stack) == before_redo
    assert session.project.derived == before_derived
    assert all(run.status == "completed" for run in session.tracking_runs())


def test_import_is_one_undo_and_tracking_run_history_survives_undo_redo(
    tmp_path: Path,
) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    run = _running_infer_run(session, video_id, track_id)
    completed = mark_run_completed(run)
    point = _engine_point(run, timeline, 1)
    session.import_engine_points((point,), completed)

    assert session.undo()
    assert session.project.observations == ()
    assert session.tracking_runs()[0].status == "completed"
    assert session.tracking_runs()[0].extra_fields["import_summary"]["inserted"] == 1

    assert session.redo()
    assert session.project.observations == (point,)
    assert session.tracking_runs()[0].status == "completed"


def test_import_persists_points_confidence_and_run_summary(tmp_path: Path) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    run = _running_infer_run(session, video_id, track_id)
    session.import_engine_points(
        (_engine_point(run, timeline, 4, pixel_x=44.0),),
        replace(mark_run_completed(run), extra_fields={"import_summary": {"parsed": 1}}),
    )

    project_dir = tmp_path / "project"
    session.save_as(project_dir)
    loaded = ProjectSession.load(ProjectRepository(), project_dir)

    assert loaded.project.observations[0].confidence == pytest.approx(0.9)
    assert loaded.project.observations[0].source == "dlc"
    loaded_run = loaded.tracking_runs()[0]
    assert loaded_run.status == "completed"
    assert loaded_run.extra_fields["import_summary"] == {
        "parsed": 1,
        "inserted": 1,
        "skipped": 0,
    }


def test_mixed_effective_points_drive_kinematics_and_analysis_inputs(
    tmp_path: Path,
) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    manual = session.mark_point(track_id, 0, 10.0, 20.0)
    run = _running_infer_run(session, video_id, track_id)
    ai_points = tuple(_engine_point(run, timeline, frame, pixel_x=10.0 + frame)
                      for frame in (1, 2))
    session.import_engine_points(ai_points, mark_run_completed(run))

    effective = session.effective_points(track_id)
    assert effective[0] == manual
    assert [point.source for point in effective] == ["manual", "dlc", "dlc"]
    assert [point.frame_index for point in effective] == [0, 1, 2]

    derived = session.compute_kinematics(track_id)
    assert derived[0].frames == (0, 1, 2)
    assert all(item.input.source_filter is None for item in derived)
    assert all(
        item.input.extra_fields["observation_selection"] == "effective"
        for item in derived
    )
    inputs = analysis_inputs(session, video_id, (track_id,))
    assert inputs.points == effective


def test_ai_import_invalidates_old_kinematics_job_inputs(tmp_path: Path) -> None:
    session, video_id, track_id, timeline = _session_with_track(tmp_path)
    session.mark_point(track_id, 0, 10.0, 20.0)
    job = prepare_kinematics_job(
        session,
        video_id,
        (track_id,),
        SmoothingParameters(),
    )
    result = run_kinematics_job(job, Event())

    run = _running_infer_run(session, video_id, track_id)
    session.import_engine_points(
        (_engine_point(run, timeline, 1),),
        mark_run_completed(run),
    )

    with pytest.raises(ProjectSessionError, match="inputs changed"):
        session.apply_kinematics_result(result)
