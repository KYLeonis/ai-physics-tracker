"""TrackingRun 领域模型、状态转换与 JSON 序列化测试。"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
import pytest

from ai_physics_tracker.domain.project import (
    Project,
    Registries,
    add_video,
    create_project,
    validate_project,
)
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_cancelled,
    mark_run_completed,
    mark_run_failed,
    mark_run_running,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.project_serializer import (
    project_from_payload,
    project_to_payload,
)


def _sample_video_and_track(project: Project) -> tuple[Project, Video, Track]:
    vid = uuid4()
    video = Video(
        video_id=vid,
        file_path=None,
        original_path="/dummy/test.mp4",
        display_name="test.mp4",
        width_px=1920,
        height_px=1080,
        fps_container=30.0,
        frame_count=300,
        vfr_suspected=False,
    )
    timeline = Timeline(video_id=vid, fps_nominal=30.0, working_zone=(0, 299))
    project = add_video(project, video, timeline)
    track_id = uuid4()
    track = Track(
        track_id=track_id,
        video_id=vid,
        name="Ball",
        color="#FF0000",
        created_at=utc_now(),
    )
    project = Project(
        project_id=project.project_id,
        name=project.name,
        created_at=project.created_at,
        modified_at=project.modified_at,
        videos=project.videos,
        timelines=project.timelines,
        tracks=(track,),
    )
    return project, video, track


def test_tracking_run_creation_and_defaults() -> None:
    vid = uuid4()
    tid = uuid4()
    run = create_tracking_run(
        video_id=vid,
        track_id=tid,
        task_type="train",
        config={"epochs": 50, "shuffle": 1},
    )

    assert run.video_id == vid
    assert run.track_id == tid
    assert run.engine == "dlc"
    assert run.engine_version == "3.0.1"
    assert run.task_type == "train"
    assert run.status == "pending"
    assert run.config == {"epochs": 50, "shuffle": 1}
    assert run.model_snapshot is None
    assert run.completed_at is None
    assert run.error_message is None
    assert run.source_detail.startswith("dlc:train:")


def test_tracking_run_state_transitions() -> None:
    run = create_tracking_run(video_id=uuid4(), track_id=uuid4(), task_type="train")
    assert run.status == "pending"

    # Start running
    run_running = mark_run_running(run)
    assert run_running.status == "running"

    # Cannot start again if already running
    with pytest.raises(ValueError, match="cannot start run in 'running' status"):
        mark_run_running(run_running)

    # Complete run
    run_completed = mark_run_completed(run_running, model_snapshot="/path/snapshot-50.pt")
    assert run_completed.status == "completed"
    assert run_completed.model_snapshot == "/path/snapshot-50.pt"
    assert run_completed.completed_at is not None

    # Cannot cancel or fail completed run
    with pytest.raises(ValueError, match="cannot cancel run already in 'completed' status"):
        mark_run_cancelled(run_completed)
    with pytest.raises(ValueError, match="cannot fail run already in 'completed' status"):
        mark_run_failed(run_completed, "some error")


def test_tracking_run_fail_and_cancel() -> None:
    run = create_tracking_run(video_id=uuid4(), track_id=uuid4(), task_type="infer")
    failed = mark_run_failed(run, "CUDA OOM error")
    assert failed.status == "failed"
    assert failed.error_message == "CUDA OOM error"
    assert failed.completed_at is not None

    run2 = create_tracking_run(video_id=uuid4(), track_id=uuid4(), task_type="infer")
    cancelled = mark_run_cancelled(run2)
    assert cancelled.status == "cancelled"
    assert cancelled.completed_at is not None


def test_tracking_run_validation() -> None:
    vid = uuid4()
    tid = uuid4()
    now = utc_now()

    with pytest.raises(ValueError, match="engine must not be blank"):
        TrackingRun(
            run_id=uuid4(),
            video_id=vid,
            track_id=tid,
            engine="",
            engine_version="3.0",
            task_type="train",
            config={},
            source_detail="dlc:1",
            created_at=now,
        )

    with pytest.raises(ValueError, match="task_type must be one of"):
        TrackingRun(
            run_id=uuid4(),
            video_id=vid,
            track_id=tid,
            engine="dlc",
            engine_version="3.0",
            task_type="invalid_type",
            config={},
            source_detail="dlc:1",
            created_at=now,
        )

    with pytest.raises(ValueError, match="status must be one of"):
        TrackingRun(
            run_id=uuid4(),
            video_id=vid,
            track_id=tid,
            engine="dlc",
            engine_version="3.0",
            task_type="train",
            config={},
            source_detail="dlc:1",
            created_at=now,
            status="unknown_status",
        )

    # completed_at < created_at
    past = datetime(2020, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="completed_at cannot be earlier than created_at"):
        TrackingRun(
            run_id=uuid4(),
            video_id=vid,
            track_id=tid,
            engine="dlc",
            engine_version="3.0",
            task_type="train",
            config={},
            source_detail="dlc:1",
            created_at=now,
            completed_at=past,
        )


def test_project_validation_with_tracking_runs() -> None:
    base = create_project("Test Project")
    project, video, track = _sample_video_and_track(base)

    run = create_tracking_run(video_id=video.video_id, track_id=track.track_id, task_type="train")
    project_with_run = Project(
        project_id=project.project_id,
        name=project.name,
        created_at=project.created_at,
        modified_at=project.modified_at,
        videos=project.videos,
        timelines=project.timelines,
        tracks=project.tracks,
        tracking_runs=(run,),
    )
    validate_project(project_with_run)

    # Bad video_id
    bad_vid_run = create_tracking_run(video_id=uuid4(), track_id=track.track_id, task_type="train")
    with pytest.raises(ValueError, match="every tracking run must reference a registered video"):
        Project(
            project_id=project.project_id,
            name=project.name,
            created_at=project.created_at,
            modified_at=project.modified_at,
            videos=project.videos,
            timelines=project.timelines,
            tracks=project.tracks,
            tracking_runs=(bad_vid_run,),
        )

    # Bad track_id
    bad_track_run = create_tracking_run(video_id=video.video_id, track_id=uuid4(), task_type="train")
    with pytest.raises(ValueError, match="every tracking run must reference a registered track"):
        Project(
            project_id=project.project_id,
            name=project.name,
            created_at=project.created_at,
            modified_at=project.modified_at,
            videos=project.videos,
            timelines=project.timelines,
            tracks=project.tracks,
            tracking_runs=(bad_track_run,),
        )


def test_dlc_source_in_registries_and_track_point() -> None:
    project = create_project("P")
    assert "dlc" in project.registries.sources

    project, video, track = _sample_video_and_track(project)
    point = TrackPoint(
        point_id=uuid4(),
        track_id=track.track_id,
        frame_index=10,
        time_s=10 / 30.0,
        pixel_x=123.4,
        pixel_y=567.8,
        source="dlc",
        source_detail="dlc:infer:run1",
        confidence=0.95,
        visibility="visible",
        status="active",
        created_at=utc_now(),
        modified_at=utc_now(),
    )
    project_with_point = Project(
        project_id=project.project_id,
        name=project.name,
        created_at=project.created_at,
        modified_at=project.modified_at,
        videos=project.videos,
        timelines=project.timelines,
        tracks=project.tracks,
        observations=(point,),
    )
    validate_project(project_with_point)


def test_tracking_run_serialization_roundtrip(tmp_path: Path) -> None:
    base = create_project("Serialized Project")
    project, video, track = _sample_video_and_track(base)

    run = create_tracking_run(
        video_id=video.video_id,
        track_id=track.track_id,
        task_type="train",
        config={"iterations": 1000},
        model_snapshot="dlc-models/snapshot-1000.pt",
    )
    completed_run = mark_run_completed(mark_run_running(run))

    project = Project(
        project_id=project.project_id,
        name=project.name,
        created_at=project.created_at,
        modified_at=project.modified_at,
        videos=project.videos,
        timelines=project.timelines,
        tracks=project.tracks,
        tracking_runs=(completed_run,),
    )

    payload = project_to_payload(project)
    assert "tracking_runs" in payload
    assert len(payload["tracking_runs"]) == 1

    restored = project_from_payload(payload)
    assert len(restored.tracking_runs) == 1
    r = restored.tracking_runs[0]
    assert r.run_id == completed_run.run_id
    assert r.video_id == video.video_id
    assert r.track_id == track.track_id
    assert r.engine == "dlc"
    assert r.task_type == "train"
    assert r.status == "completed"
    assert r.model_snapshot == "dlc-models/snapshot-1000.pt"
    assert r.completed_at == completed_run.completed_at
    assert r.config == {"iterations": 1000}

    # Test full repository save and load
    repo = ProjectRepository()
    proj_dir = tmp_path / "project_dir"
    saved = repo.create_from_project(proj_dir, project)
    loaded = repo.load(proj_dir)
    assert len(loaded.tracking_runs) == 1
    assert loaded.tracking_runs[0].run_id == completed_run.run_id
