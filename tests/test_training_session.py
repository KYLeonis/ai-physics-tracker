"""统一训练任务与 ProjectSession 持久化边界测试。"""

from pathlib import Path
import time

import pytest

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.tracking_job import (
    TrackingJobRunner,
    cancel_tracking_job,
    prepare_tracking_candidate,
    prepare_tracking_request,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.tracking_run import mark_run_cancelled, mark_run_running
from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskResult


def _create_session(tmp_path: Path, video_path: Path) -> tuple[ProjectSession, object]:
    session = ProjectSession.start(ProjectRepository(), "Tracking session test")
    info = VideoStreamInfo(
        width_px=64,
        height_px=48,
        fps_container=10.0,
        frame_count=5,
        container_format="avi",
        timing_status="cfr",
    )
    video, _timeline = session.register_external_video(video_path, info)
    track = session.add_track(video.video_id, "Target")
    for frame_index in (0, 1, 2, 3):
        session.mark_point(track.track_id, frame_index, 10.0 + frame_index, 20.0)
    session.save_as(tmp_path / "project")
    return session, track


def _wait_for_result(handle, root: Path) -> Path:
    messages = []
    deadline = time.monotonic() + 20.0
    while handle.is_alive() and time.monotonic() < deadline:
        messages.extend(handle.poll_messages(limit=200))
        handle.join(timeout_s=0.02)
    messages.extend(handle.poll_messages(limit=200))
    if handle.is_alive():
        handle.cancel(timeout_s=1.0)
        pytest.fail("tracking worker did not terminate")
    results = [
        message
        for message in messages
        if isinstance(message, TaskResult)
        and message.success
        and message.payload
        and message.payload.get("result_path")
    ]
    assert len(results) == 1
    return root / results[0].payload["result_path"]


def test_tracking_run_persistence_roundtrip_through_unified_runner(
    tmp_path: Path,
    synthetic_video_path: Path,
) -> None:
    session, track = _create_session(tmp_path, synthetic_video_path)
    request = prepare_tracking_request(
        session,
        track.track_id,
        TrainingParams(epochs=4, extra_params={"simulate_delay": 0.0}),
    )
    session.record_tracking_run(request.run)
    session.update_tracking_run(mark_run_running(request.run))

    handle = TrackingJobRunner(adapter=MockEngineAdapter()).start(request)
    result_path = _wait_for_result(handle, request.project_root)
    candidate = prepare_tracking_candidate(session.project, request, result_path)
    assert session.apply_tracking_candidate(candidate)
    session.save()

    reloaded = ProjectRepository().load(session.project_root)
    completed = reloaded.tracking_runs[-1]
    assert completed.status == "completed"
    assert completed.model_snapshot is not None
    assert completed.completed_at is not None
    assert completed.config["epochs"] == 4


def test_session_close_cancels_unified_runner_and_persists_status(
    tmp_path: Path,
    synthetic_video_path: Path,
) -> None:
    session, track = _create_session(tmp_path, synthetic_video_path)
    request = prepare_tracking_request(
        session,
        track.track_id,
        TrainingParams(epochs=50, extra_params={"simulate_delay": 0.05}),
    )
    session.record_tracking_run(request.run)
    running = mark_run_running(request.run)
    session.update_tracking_run(running)
    handle = TrackingJobRunner(adapter=MockEngineAdapter()).start(request)

    cancel_tracking_job(handle, request)
    assert not handle.is_alive()
    session.update_tracking_run(mark_run_cancelled(running))
    session.save()

    loaded = ProjectRepository().load(session.project_root)
    assert loaded.tracking_runs[-1].status == "cancelled"
