"""应用层训练准备边界测试。"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.training_job import (
    MIN_MANUAL_POINTS_FOR_TRAINING,
    prepare_training,
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
    track_id = session.tracks[0].track_id

    with pytest.raises(ProjectSessionError, match=f"At least {MIN_MANUAL_POINTS_FOR_TRAINING} active manual points"):
        prepare_training(session, track_id, reader, working_dir=tmp_path)


def test_prepare_training_success_and_directory_reuse(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=4)
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    params = TrainingParams(epochs=25, batch_size=4)
    run, cfg_path = prepare_training(
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
    run2, cfg_path2 = prepare_training(
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

    run3, cfg_path3 = prepare_training(
        session,
        track2.track_id,
        reader,
        params=params,
        adapter=adapter,
        working_dir=tmp_path,
    )
    assert cfg_path3 != cfg_path
    assert cfg_path3.parent != cfg_path.parent
