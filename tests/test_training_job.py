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
from ai_physics_tracker.application.refinement_history import extract_refinement_iteration
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


def test_prepare_training_with_active_validation_series_fixed_split(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=5)  # frames 0, 10, 20, 30, 40
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    # 1. Without active validation series: train/test indices should be None
    run1, _ = prepare_training(session, track.track_id, reader, adapter=adapter, working_dir=tmp_path)
    iter_info1 = extract_refinement_iteration(run1)
    assert iter_info1 is not None
    assert iter_info1.iteration_index == 0
    assert iter_info1.validation_series_id is None
    assert len(iter_info1.training_labels) == 5
    assert adapter.created_dataset_splits[-1] == (None, None)

    # 2. Create and activate validation series on frames 10 and 30
    val_series = session.create_validation_series(track.track_id, "Fixed Val 1", [10, 30])
    assert val_series.frame_indices == (10, 30)

    # Prepare training with active validation series
    run2, _ = prepare_training(session, track.track_id, reader, adapter=adapter, working_dir=tmp_path)
    iter_info2 = extract_refinement_iteration(run2)
    assert iter_info2 is not None
    assert iter_info2.validation_series_id == val_series.series_id
    # Training labels should only contain frames 0, 20, 40
    assert tuple(s.frame_index for s in iter_info2.training_labels) == (0, 20, 40)

    # Verify adapter received explicit train and test indices
    train_inds, test_inds = adapter.created_dataset_splits[-1]
    assert train_inds == [0, 2, 4]
    assert test_inds == [1, 3]
    # Verify zero data leakage: disjoint sets and full coverage
    assert set(train_inds) & set(test_inds) == set()
    assert set(train_inds) | set(test_inds) == {0, 1, 2, 3, 4}


def test_prepare_training_rejects_invalid_or_all_consuming_validation_series(tmp_path: Path) -> None:
    session, reader, _ = _setup_session_with_track(tmp_path, point_count=3)  # frames 0, 10, 20
    track = session.tracks[0]
    adapter = MockEngineAdapter()

    # A: Validation series takes all points (0, 10, 20) -> no points left for training
    session.create_validation_series(track.track_id, "All Points Val", [0, 10, 20])
    with pytest.raises(ProjectSessionError, match="At least one manual point must be available"):
        prepare_training(session, track.track_id, reader, adapter=adapter, working_dir=tmp_path)

    # B: Validation series on frame 0, but user moves/modifies point 0
    session.create_validation_series(track.track_id, "Val Frame 0", [0])
    # Modify coordinates on frame 0
    session.mark_point(track.track_id, 0, 999.0, 999.0)
    with pytest.raises(ProjectSessionError, match="Active validation series 'Val Frame 0' is invalid"):
        prepare_training(session, track.track_id, reader, adapter=adapter, working_dir=tmp_path)

