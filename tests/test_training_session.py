"""训练生命周期与项目持久化 (project.json) 及会话级联测试。"""

from pathlib import Path
import time
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.training_job import TrainingCoordinator
from ai_physics_tracker.application.video import DecodedFrame, VideoStreamInfo
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _create_session_with_data(tmp_path: Path) -> tuple[ProjectSession, OpenCVVideoReader, Path, Path]:
    proj_dir = tmp_path / "my_project"
    video_file = tmp_path / "video.mp4"
    video_file.touch()

    repo = ProjectRepository()
    proj = create_project("Cascading Project")
    session = ProjectSession(repo, proj, project_root=proj_dir)

    info = VideoStreamInfo(
        width_px=1920,
        height_px=1080,
        fps_container=30.0,
        frame_count=200,
        container_format="mp4",
        timing_status="cfr",
    )
    video, timeline = session.register_external_video(video_file, info)
    track = session.add_track(video.video_id, "TrackA")

    for i in range(4):
        session.mark_point(track.track_id, frame_index=i * 5, pixel_x=10.0 + i, pixel_y=20.0 + i)

    # 保存初始项目到目录
    repo.create_from_project(proj_dir, session.project)

    mock_reader = MagicMock(spec=OpenCVVideoReader)
    mock_reader.is_open = True
    mock_reader.read_frame.return_value = DecodedFrame(
        frame_index=0,
        pixels_rgb=np.zeros((100, 100, 3), dtype=np.uint8),
    )

    return session, mock_reader, proj_dir, video_file


def test_tracking_run_persistence_roundtrip_through_session(tmp_path: Path) -> None:
    session, reader, proj_dir, _ = _create_session_with_data(tmp_path)
    coordinator = TrainingCoordinator()
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=4, extra_params={"simulate_delay": 0.01})
    run, cfg_path = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
    )

    # 1. 验证 pending 状态持久化
    repo = ProjectRepository()
    saved_proj = repo.save(proj_dir, session.project)
    loaded_proj = repo.load(proj_dir)
    assert len(loaded_proj.tracking_runs) == 1
    assert loaded_proj.tracking_runs[0].status == "pending"

    # 2. 启动训练并运行至完成
    coordinator.start_training(session, run.run_id, cfg_path, MockEngineAdapter)
    start = time.time()
    while coordinator.is_running(run.run_id) or (time.time() - start < 2.0):
        coordinator.poll_messages(session, run.run_id)
        if not coordinator.is_running(run.run_id):
            break
        time.sleep(0.02)

    coordinator.poll_messages(session, run.run_id)
    completed_run = next(r for r in session.tracking_runs() if r.run_id == run.run_id)
    assert completed_run.status == "completed"

    # 3. 验证 completed 状态与 snapshot 路径持久化
    repo.save(proj_dir, session.project)
    reloaded_proj = repo.load(proj_dir)
    assert len(reloaded_proj.tracking_runs) == 1
    reloaded_run = reloaded_proj.tracking_runs[0]
    assert reloaded_run.status == "completed"
    assert reloaded_run.model_snapshot is not None
    assert reloaded_run.completed_at is not None
    assert reloaded_run.config["epochs"] == 4


def test_session_close_cancels_running_tasks(tmp_path: Path) -> None:
    session, reader, proj_dir, _ = _create_session_with_data(tmp_path)
    coordinator = TrainingCoordinator()
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=50, extra_params={"simulate_delay": 0.05})
    run, cfg_path = coordinator.prepare_training(
        session,
        track.track_id,
        reader,
        params=params,
        adapter=adapter,
    )

    coordinator.start_training(session, run.run_id, cfg_path, MockEngineAdapter)
    assert coordinator.is_running(run.run_id)

    # 模拟会话关闭前调用 cancel_all
    coordinator.cancel_all(session)
    assert not coordinator.is_running(run.run_id)

    # 保存后重新加载
    repo = ProjectRepository()
    repo.save(proj_dir, session.project)
    loaded = repo.load(proj_dir)
    assert len(loaded.tracking_runs) == 1
    assert loaded.tracking_runs[0].status == "cancelled"
