"""与 Qt 无关的 ProjectSession 标注会话测试。

验证 phase2-requirements.md §2 R5：manual TrackPoint 写入语义
（time_s 冻结、manual last-wins、superseded 遮蔽）与 dirty 生命周期。
"""

from pathlib import Path

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _info(fps: float = 10.0, frame_count: int = 5) -> VideoStreamInfo:
    return VideoStreamInfo(64, 48, fps, frame_count, "fake", "cfr")


def _session_with_video(tmp_path: Path) -> ProjectSession:
    session = ProjectSession.start(ProjectRepository())
    session.register_external_video(tmp_path / "clip.mp4", _info())
    return session


def test_register_external_video_adds_video_and_timeline(tmp_path: Path) -> None:
    session = ProjectSession.start(ProjectRepository())

    video, timeline = session.register_external_video(
        tmp_path / "clip.mp4", _info(fps=24.0, frame_count=30)
    )

    assert session.project.videos == (video,)
    assert session.project.timelines == (timeline,)
    assert video.original_path == str(tmp_path / "clip.mp4")
    assert video.file_path is None
    assert timeline.fps_nominal == pytest.approx(24.0)
    assert session.is_dirty


def test_add_track_auto_names_and_rotates_palette(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    first = session.add_track(video.video_id)
    second = session.add_track(video.video_id)

    assert first.name == "Track 1"
    assert second.name == "Track 2"
    assert first.color != second.color
    assert session.tracks == (first, second)
    assert session.project.tracks == (first, second)


def test_add_track_respects_explicit_unique_name(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    session.add_track(video.video_id)

    named = session.add_track(video.video_id, name=" Pendulum bob ")

    assert named.name == "Pendulum bob"


def test_mark_point_freezes_time_via_timeline_and_manual_semantics(
    tmp_path: Path,
) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    point = session.mark_point(track.track_id, 2, 31.5, 24.0)

    assert point.source == "manual"
    assert point.confidence is None
    assert point.status == "active"
    assert point.time_s == pytest.approx(0.2, abs=1e-12)  # 2 / 10 fps
    assert session.project.observations == (point,)


def test_mark_point_same_frame_last_wins_deletes_old_manual(
    tmp_path: Path,
) -> None:
    # data-model.md §4.2：旧 manual 点硬删除；引擎点保留为 superseded
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    first = session.mark_point(track.track_id, 1, 10.0, 10.0)
    second = session.mark_point(track.track_id, 1, 42.0, 21.0)

    stored = session.project.observations
    assert len(stored) == 1
    assert stored[0].point_id == second.point_id
    assert first.point_id != second.point_id
    assert session.effective_point(track.track_id, 1) == second
    assert session.manual_points(track.track_id) == (second,)


def test_remove_track_cascades_observations(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)

    session.remove_track(track.track_id)

    assert session.tracks == ()
    assert session.project.observations == ()
    with pytest.raises(ProjectSessionError):
        session.mark_point(track.track_id, 0, 2.0, 2.0)


def test_dirty_lifecycle_across_save_roundtrip(tmp_path: Path) -> None:
    repository = ProjectRepository()
    root = tmp_path / "proj"
    root.mkdir()
    session = ProjectSession.start(repository, name="Pendulum run 1")
    video, _timeline = session.register_external_video(
        tmp_path / "clip.mp4", _info()
    )
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 5.0, 6.0)
    assert session.is_dirty

    with pytest.raises(ProjectSessionError):
        ProjectSession.start(repository).save()  # 无根目录不能保存

    session._project_root = root  # 测试直接注入根目录；2.4 提供 Save As UI
    saved = session.save()

    assert not session.is_dirty
    assert saved.tracks == session.tracks

    reloaded = repository.load(root)
    assert reloaded.tracks == session.tracks
    assert reloaded.observations == session.project.observations
    assert reloaded.observations[0].pixel_x == pytest.approx(5.0)


def test_mark_point_unknown_track_reports_error(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    from uuid import uuid4

    with pytest.raises(ProjectSessionError):
        session.mark_point(uuid4(), 0, 1.0, 1.0)
