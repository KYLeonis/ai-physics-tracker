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
from ai_physics_tracker.domain.tracking_run import create_tracking_run
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
    assert point.visibility == "visible"  # data-model.md §3.5 manual 缺省
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


def test_remove_track_with_runs_succeeds_and_undo_keeps_runs_deleted(
    tmp_path: Path,
) -> None:
    # review F1 回归：带 TrackingRun 的 track 删除不再被聚合校验拒绝；
    # undo 恢复 track/观测（数据层），run 注册表是审计日志、不进撤销快照。
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)
    session.record_tracking_run(
        create_tracking_run(
            video.video_id, track.track_id, "train", engine_version="3.0.1-mock"
        )
    )

    session.remove_track(track.track_id)

    assert session.tracks == ()
    assert session.project.observations == ()
    assert session.project.tracking_runs == ()

    assert session.undo()

    assert session.tracks == (track,)
    assert len(session.project.observations) == 1
    assert session.project.tracking_runs == ()


def test_detached_snapshot_is_isolated_from_subsequent_writes(
    tmp_path: Path,
) -> None:
    # review F5：detached 去除 deepcopy 后，隔离性由"frozen + replace()"契约
    # 保证；本测试固定该契约——任何一侧的原地修改都会在这里暴露。
    from copy import deepcopy

    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)
    snapshot = session.detached()
    reference = deepcopy(snapshot.project)

    session.mark_point(track.track_id, 1, 2.0, 3.0)
    session.add_calibration(
        video_id=video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(10.0, 0.0),
        known_length=1.0,
    )
    session.record_tracking_run(
        create_tracking_run(
            video.video_id, track.track_id, "train", engine_version="3.0.1-mock"
        )
    )
    session.update_view_state({"frame_index": 7})

    assert snapshot.project == reference

    snapshot.update_view_state({"frame_index": 9})
    workflow = session.project.ui_state.get("workflow", {})
    assert workflow.get("frame_index") == 7


def test_detached_shares_frozen_project_without_copying(tmp_path: Path) -> None:
    # review F5 实现契约：detached 必须共享不可变结构（O(1)）。
    # 退化回 deepcopy 会让 GUI 线程上的成本随观测数线性增长。
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)

    snapshot = session.detached()

    assert snapshot._project is session._project
    assert snapshot._saved_project is session._saved_project


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


def test_undo_restores_point_replaced_by_last_wins(tmp_path: Path) -> None:
    # last-wins 硬删旧 manual 点；undo 必须能恢复被替换的旧点
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    session.mark_point(track.track_id, 1, 10.0, 10.0)
    session.mark_point(track.track_id, 1, 42.0, 21.0)
    assert len(session.project.observations) == 1

    assert session.undo()

    points = session.manual_points(track.track_id)
    assert len(points) == 1
    assert (points[0].pixel_x, points[0].pixel_y) == (10.0, 10.0)

    assert session.redo()

    points = session.manual_points(track.track_id)
    assert (points[0].pixel_x, points[0].pixel_y) == (42.0, 21.0)


def test_undo_add_track_and_delete_track(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    assert session.undo()
    assert session.tracks == ()

    assert session.redo()
    assert session.tracks == (track,)

    session.mark_point(track.track_id, 0, 5.0, 5.0)
    session.remove_track(track.track_id)
    assert session.tracks == ()

    assert session.undo()  # 恢复删除
    assert session.tracks == (track,)
    assert len(session.project.observations) == 1


def test_undo_stack_is_limited_and_save_clears_it(tmp_path: Path) -> None:
    from ai_physics_tracker.application.project_session import UNDO_STACK_LIMIT

    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    for step in range(UNDO_STACK_LIMIT + 5):
        session.mark_point(track.track_id, step % 5, 1.0, 1.0)  # 合成视频 5 帧

    # 栈深限制：最早的 mark（add_track 之后）已不可撤销
    for _ in range(UNDO_STACK_LIMIT):
        assert session.undo()
    assert not session.can_undo

    session._project_root = tmp_path  # 测试注入根
    session.save()
    assert not session.can_undo and not session.can_redo


def test_new_write_clears_redo_stack(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    session.mark_point(track.track_id, 0, 1.0, 1.0)
    assert session.undo()
    assert session.can_redo

    session.mark_point(track.track_id, 1, 2.0, 2.0)  # 分支：旧 redo 作废

    assert not session.can_redo


def test_add_calibration_creates_and_activates_calibration(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(10.0, 20.0),
        scale_end_2_px=(110.0, 20.0),
        known_length=1.0,
        unit="m",
    )

    assert cal.name == "Calibration 1"
    assert cal.known_length == 1.0
    assert cal.unit == "m"
    assert session.calibrations == (cal,)
    assert session.active_calibration(video.video_id) == cal
    assert session.project.active_calibration_by_video == {video.video_id: cal.calibration_id}
    assert session.is_dirty


def test_add_calibration_auto_names_and_custom_name(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal1 = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(50.0, 0.0),
        known_length=0.5,
        unit="m",
    )
    cal2 = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=100.0,
        unit="cm",
        name="Ruler 1m",
    )

    assert cal1.name == "Calibration 1"
    assert cal2.name == "Ruler 1m"
    assert session.active_calibration(video.video_id) == cal2


def test_add_calibration_invalid_params_raises(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    with pytest.raises(ProjectSessionError):
        session.add_calibration(
            video.video_id,
            scale_end_1_px=(10.0, 10.0),
            scale_end_2_px=(10.0, 10.0),  # 重合点
            known_length=1.0,
        )

    with pytest.raises(ProjectSessionError):
        session.add_calibration(
            video.video_id,
            scale_end_1_px=(0.0, 0.0),
            scale_end_2_px=(10.0, 10.0),
            known_length=-5.0,  # 负长度
        )


def test_remove_calibration_and_set_active(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
    )
    assert session.active_calibration(video.video_id) == cal

    session.set_active_calibration(video.video_id, None)
    assert session.active_calibration(video.video_id) is None

    session.set_active_calibration(video.video_id, cal.calibration_id)
    assert session.active_calibration(video.video_id) == cal

    session.remove_calibration(cal.calibration_id)
    assert session.calibrations == ()
    assert session.active_calibration(video.video_id) is None


def test_update_calibration_modifies_origin_and_rotation(tmp_path: Path) -> None:
    from dataclasses import replace

    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
    )

    updated_cal = replace(cal, origin_px=(10.0, 40.0), rotation_deg=45.0)
    session.update_calibration(updated_cal)

    active = session.active_calibration(video.video_id)
    assert active is not None
    assert active.origin_px == (10.0, 40.0)
    assert active.rotation_deg == 45.0


def test_undo_redo_calibration_operations(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
    )

    assert session.undo()
    assert session.calibrations == ()
    assert session.active_calibration(video.video_id) is None

    assert session.redo()
    assert session.calibrations == (cal,)
    assert session.active_calibration(video.video_id) == cal

    session.remove_calibration(cal.calibration_id)
    assert session.calibrations == ()

    assert session.undo()
    assert session.calibrations == (cal,)
    assert session.active_calibration(video.video_id) == cal

