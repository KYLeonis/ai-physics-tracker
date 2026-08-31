"""应用层训练编排服务 TrainingCoordinator 单元与集成测试。"""

from pathlib import Path
import time
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.training_job import (
    MIN_MANUAL_POINTS_FOR_TRAINING,
    TrainingCoordinator,
)
from ai_physics_tracker.application.video import DecodedFrame, VideoStreamInfo
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


class DummyRepository:
    def save(self, project_root, project):
        return project

    def load(self, project_root):
        raise NotImplementedError

    def create_from_project(self, project_root, project):
        return project

    def save_as(self, source_root, destination_root, project):
        return project

    def resolve_video_path(self, project_root, video):
        return Path(video.original_path) if video.original_path else None


def _setup_session_with_track(tmp_path: Path, point_count: int = 5) -> tuple[ProjectSession, OpenCVVideoReader, Path]:
    video_file = tmp_path / "sample_video.mp4"
    video_file.touch()

    repo = DummyRepository()
    session = ProjectSession.start(repo, "Train Test")

    info = VideoStreamInfo(
        width_px=1920,
        height_px=1080,
        fps_container=30.0,
        frame_count=300,
        container_format="mp4",
        timing_status="cfr",
    )
    video, timeline = session.register_external_video(video_file, info)
    track = session.add_track(video.video_id, "Bob")

    for i in range(point_count):
        session.mark_point(track.track_id, frame_index=i * 10, pixel_x=100.0 + i, pixel_y=200.0 + i)

    mock_reader = MagicMock(spec=OpenCVVideoReader)
    mock_reader.is_open = True
    mock_reader.read_frame.return_value = DecodedFrame(
        frame_index=0,
        pixels_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
    )

    return session, mock_reader, video_file


def test_prepare_training_insufficient_points(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=2)
    coordinator = TrainingCoordinator()
    track_id = session.tracks[0].track_id

    with pytest.raises(ProjectSessionError, match=f"At least {MIN_MANUAL_POINTS_FOR_TRAINING} active manual points"):
        coordinator.prepare_training(session, track_id, reader, working_dir=tmp_path)


def test_prepare_training_success_and_directory_reuse(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=4)
    coordinator = TrainingCoordinator()
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=25, batch_size=4)
    run, cfg_path = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )

    # 验证返回值与 session 中的 TrackingRun
    assert run.status == "pending"
    assert run.track_id == track.track_id
    assert run.config["epochs"] == 25
    assert cfg_path.is_file()
    assert len(session.tracking_runs(track.track_id)) == 1

    # 验证相同 Track 二次调用复用相同目录
    run2, cfg_path2 = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )
    assert cfg_path2 == cfg_path
    assert len(session.tracking_runs(track.track_id)) == 2

    # 验证不同 Track 使用不同目录
    track2 = session.add_track(track.video_id, "Pivot")
    for i in range(3):
        session.mark_point(track2.track_id, frame_index=i * 5, pixel_x=50.0, pixel_y=50.0)

    run3, cfg_path3 = coordinator.prepare_training(
        session,
        track2.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )
    assert cfg_path3 != cfg_path
    assert cfg_path3.parent != cfg_path.parent


def test_start_training_and_poll_completion(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=4)
    coordinator = TrainingCoordinator()
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=5, extra_params={"simulate_delay": 0.01})
    run, cfg_path = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )

    handle = coordinator.start_training(session, run.run_id, cfg_path, MockEngineAdapter)
    assert coordinator.is_running(run.run_id)

    # 校验状态变更为 running
    running_run = next(r for r in session.tracking_runs() if r.run_id == run.run_id)
    assert running_run.status == "running"

    # 轮询直至完成
    all_msgs = []
    start = time.time()
    while coordinator.is_running(run.run_id) or (time.time() - start < 3.0):
        msgs = coordinator.poll_messages(session, run.run_id)
        all_msgs.extend(msgs)
        if not coordinator.is_running(run.run_id):
            break
        time.sleep(0.02)

    handle.join(timeout_s=1.0)
    all_msgs.extend(coordinator.poll_messages(session, run.run_id))

    # 校验状态已更新为 completed 且带 snapshot 路径
    completed_run = next(r for r in session.tracking_runs() if r.run_id == run.run_id)
    assert completed_run.status == "completed"
    assert completed_run.model_snapshot is not None
    assert Path(completed_run.model_snapshot).is_file()
    assert completed_run.completed_at is not None


def test_cancel_training(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=4)
    coordinator = TrainingCoordinator()
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=100, extra_params={"simulate_delay": 0.05})
    run, cfg_path = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )

    coordinator.start_training(session, run.run_id, cfg_path, MockEngineAdapter)
    time.sleep(0.05)
    assert coordinator.is_running(run.run_id)

    # 取消训练
    coordinator.cancel_training(session, run.run_id, timeout_s=1.0)
    assert not coordinator.is_running(run.run_id)

    cancelled_run = next(r for r in session.tracking_runs() if r.run_id == run.run_id)
    assert cancelled_run.status == "cancelled"
    assert cancelled_run.completed_at is not None


def test_cancel_all_for_session_close(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=4)
    coordinator = TrainingCoordinator()
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=100, extra_params={"simulate_delay": 0.05})
    run, cfg_path = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )

    coordinator.start_training(session, run.run_id, cfg_path, MockEngineAdapter)
    assert coordinator.is_running(run.run_id)

    # 模拟 session 关闭触发 cancel_all
    coordinator.cancel_all(session)
    assert not coordinator.is_running(run.run_id)

    cancelled_run = next(r for r in session.tracking_runs() if r.run_id == run.run_id)
    assert cancelled_run.status == "cancelled"


def test_training_failure_handling(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=4)
    coordinator = TrainingCoordinator()
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=5, extra_params={"simulate_failure": "CUDA Driver Error"})
    run, cfg_path = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )

    handle = coordinator.start_training(session, run.run_id, cfg_path, MockEngineAdapter)

    start = time.time()
    while coordinator.is_running(run.run_id) or (time.time() - start < 2.0):
        coordinator.poll_messages(session, run.run_id)
        if not coordinator.is_running(run.run_id):
            break
        time.sleep(0.02)

    handle.join(timeout_s=1.0)
    coordinator.poll_messages(session, run.run_id)

    failed_run = next(r for r in session.tracking_runs() if r.run_id == run.run_id)
    assert failed_run.status == "failed"
    assert "CUDA Driver Error" in str(failed_run.error_message)
