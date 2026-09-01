"""GUI 跟踪任务的请求快照、spawn worker 与候选合并边界测试。"""

from dataclasses import replace
import time
from pathlib import Path

import pytest

from ai_physics_tracker.application import tracking_job
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.tracking_run import (
    create_tracking_run,
    mark_run_completed,
    mark_run_running,
)
from ai_physics_tracker.infrastructure.engine_adapter import InferenceParams, TrainingParams
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import BackgroundTaskRunner, TaskResult


def _make_session(
    tmp_path: Path,
    video_path: Path,
    *,
    point_frames: tuple[int, ...] = (0, 1, 2),
) -> tuple[ProjectSession, object, object]:
    session = ProjectSession.start(ProjectRepository(), "Tracking job test")
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
    for frame_index in point_frames:
        session.mark_point(track.track_id, frame_index, 10.0 + frame_index, 20.0)
    session.save_as(tmp_path / "project")
    return session, video, track


def _wait_worker(handle, timeout_s: float = 20.0):
    messages = []
    deadline = time.monotonic() + timeout_s
    while handle.is_alive() and time.monotonic() < deadline:
        messages.extend(handle.poll_messages(limit=200))
        handle.join(timeout_s=0.02)
    messages.extend(handle.poll_messages(limit=200))
    if handle.is_alive():
        handle.cancel(timeout_s=1.0)
        pytest.fail("tracking worker did not terminate")
    messages.extend(handle.poll_messages(limit=200))
    return messages


def _result_path(messages, root: Path) -> Path:
    results = [
        message
        for message in messages
        if isinstance(message, TaskResult)
        and message.success
        and isinstance(message.payload, dict)
        and message.payload.get("result_path")
    ]
    assert len(results) == 1
    return root / results[0].payload["result_path"]


def _register_running(session: ProjectSession, request) -> None:
    session.record_tracking_run(request.run)
    session.update_tracking_run(mark_run_running(request.run))


def test_prepare_request_captures_lightweight_snapshot_without_engine_setup(
    tmp_path: Path, synthetic_video_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _video, track = _make_session(tmp_path, synthetic_video_path)
    calls = []

    class UnexpectedReader:
        def __init__(self):
            calls.append("reader")
            raise AssertionError("prepare must not create a video reader")

    class UnexpectedCoordinator:
        def __init__(self):
            calls.append("coordinator")
            raise AssertionError("prepare must not prepare a DLC project")

    monkeypatch.setattr(tracking_job, "OpenCVVideoReader", UnexpectedReader)
    monkeypatch.setattr(tracking_job, "TrainingCoordinator", UnexpectedCoordinator)

    request = tracking_job.prepare_tracking_request(
        session, track.track_id, TrainingParams()
    )

    assert request.run.task_type == "train"
    assert request.video_path == synthetic_video_path.resolve()
    assert request.video_file_info is not None
    assert calls == []


def test_spawn_mock_training_result_is_importable_as_candidate(
    tmp_path: Path, synthetic_video_path: Path
) -> None:
    session, _video, track = _make_session(tmp_path, synthetic_video_path)
    request = tracking_job.prepare_tracking_request(
        session,
        track.track_id,
        TrainingParams(epochs=2, extra_params={"simulate_delay": 0.0}),
    )
    _register_running(session, request)

    runner = BackgroundTaskRunner()
    handle = runner.start_task(
        request.run.run_id,
        tracking_job.run_tracking_worker,
        request,
        MockEngineAdapter(),
    )
    messages = _wait_worker(handle)
    result_path = _result_path(messages, request.project_root)

    candidate = tracking_job.prepare_tracking_candidate(
        session.project, request, result_path
    )

    assert session.apply_tracking_candidate(candidate)
    completed = next(run for run in session.tracking_runs() if run.run_id == request.run.run_id)
    assert completed.status == "completed"
    assert completed.model_snapshot is not None
    assert (request.project_root / completed.model_snapshot).is_file()


def _session_with_model(
    tmp_path: Path, synthetic_video_path: Path
) -> tuple[ProjectSession, object, object, object]:
    session, video, track = _make_session(
        tmp_path, synthetic_video_path, point_frames=(0, 1, 2)
    )
    models = session.project_root / "models"
    models.mkdir(exist_ok=True)
    (models / "config.yaml").write_text("bodyparts: [target]\n", encoding="utf-8")
    (models / "snapshot.pt").write_bytes(b"mock weights")
    trained = mark_run_completed(
        create_tracking_run(
            video.video_id,
            track.track_id,
            "train",
            config={"shuffle": 1, "trainingsetindex": 0},
            model_snapshot="models/snapshot.pt",
        )
    )
    trained = replace(trained, extra_fields={"config_path": "models/config.yaml"})
    session.record_tracking_run(trained)
    return session, video, track, trained


def test_spawn_mock_inference_without_hash_imports_and_keeps_manual_edits(
    tmp_path: Path, synthetic_video_path: Path
) -> None:
    session, _video, track, trained = _session_with_model(tmp_path, synthetic_video_path)
    assert "model_sha256" not in trained.extra_fields

    request = tracking_job.prepare_tracking_request(
        session,
        track.track_id,
        InferenceParams(min_confidence=0.6, device="cpu", batch_size=8),
        training_run_id=trained.run_id,
    )
    _register_running(session, request)

    runner = BackgroundTaskRunner()
    handle = runner.start_task(
        request.run.run_id,
        tracking_job.run_tracking_worker,
        request,
        MockEngineAdapter(),
    )
    messages = _wait_worker(handle)
    result_path = _result_path(messages, request.project_root)

    model_path = session.project_root / "models/snapshot.pt"
    config_path = session.project_root / "models/config.yaml"
    model_content, config_content = model_path.read_bytes(), config_path.read_bytes()
    model_stat, config_stat = model_path.stat(), config_path.stat()
    model_path.write_bytes(b"changed model")
    config_path.write_text("changed config", encoding="utf-8")
    with pytest.raises(ProjectSessionError, match="file changed"):
        tracking_job.prepare_tracking_candidate(session.project, request, result_path)
    model_path.write_bytes(model_content)
    config_path.write_bytes(config_content)
    import os
    os.utime(model_path, ns=(model_stat.st_atime_ns, model_stat.st_mtime_ns))
    os.utime(config_path, ns=(config_stat.st_atime_ns, config_stat.st_mtime_ns))

    base_project = session.project
    first_candidate = tracking_job.prepare_tracking_candidate(
        base_project, request, result_path
    )
    manual = session.mark_point(track.track_id, 4, 99.0, 88.0)
    assert not session.apply_tracking_candidate(first_candidate)

    second_candidate = tracking_job.prepare_tracking_candidate(
        session.project, request, result_path
    )
    assert session.apply_tracking_candidate(second_candidate)
    assert session.effective_point(track.track_id, 4) == manual
    assert len(session.effective_points(track.track_id)) == 5
    completed = next(run for run in session.tracking_runs() if run.run_id == request.run.run_id)
    assert completed.status == "completed"


def test_reopened_unfinished_run_is_marked_failed_in_memory_until_saved(tmp_path, synthetic_video_path):
    session, video, track = _make_session(tmp_path, synthetic_video_path)
    run = create_tracking_run(video.video_id, track.track_id, "train")
    session.record_tracking_run(mark_run_running(run))
    session.save()

    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    recovered = reopened.tracking_runs()[-1]
    assert recovered.status == "failed"
    assert "interrupted" in recovered.error_message.lower()
    assert reopened.is_dirty

    reopened.save()
    persisted = ProjectRepository().load(reopened.project_root).tracking_runs[-1]
    assert persisted == recovered
