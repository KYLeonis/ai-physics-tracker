"""应用层 ProjectSession 运动学计算管线集成测试。

覆盖功能：
- compute_kinematics 生产 4 条 DerivedData（world_position, smoothed_position, velocity, acceleration）
- 无标定时生成像素单位（px, px/s, px/s²）的派生数据
- 重复计算时替换同 Track、同 kind 的旧数据（不重复堆叠）
- 标注点变更时自动使下游 DerivedData 变为 stale
- 标定变更时自动使引用该标定的 DerivedData 变为 stale（AC-10）
- undo / redo 对 DerivedData 的快照管理
- clear_derived 清除指定 Track 的派生数据
- AC-9: DerivedData pipeline 参数在 project.json 持久化中完整往返一致
"""

from pathlib import Path
from uuid import uuid4
import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _info(fps: float = 30.0, frame_count: int = 60) -> VideoStreamInfo:
    return VideoStreamInfo(1920, 1080, fps, frame_count, "fake", "cfr")


def _session_with_calibrated_track(tmp_path: Path) -> tuple[ProjectSession, uuid4, uuid4]:
    session = ProjectSession.start(ProjectRepository())
    video, timeline = session.register_external_video(tmp_path / "pendulum.mp4", _info())
    track = session.add_track(video.video_id, "Pendulum Bob")

    # 添加标定：100px 对应 1.0m，原点 (100, 1000)
    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
        origin_px=(100.0, 1000.0),
        rotation_deg=0.0,
        set_active=True,
    )

    # 标注若干帧
    for f in range(20):
        session.mark_point(track.track_id, f, pixel_x=100.0 + f * 5.0, pixel_y=900.0 - f * 2.0)

    return session, video.video_id, track.track_id


def test_compute_kinematics_produces_derived_data(tmp_path: Path) -> None:
    session, video_id, track_id = _session_with_calibrated_track(tmp_path)

    derived = session.compute_kinematics(track_id, window_length=7, polyorder=2)
    assert len(derived) == 4

    pos, smooth, vel, acc = derived

    # 校验 kind
    assert pos.kind == "world_position"
    assert smooth.kind == "smoothed_position"
    assert vel.kind == "velocity"
    assert acc.kind == "acceleration"

    # 校验单位
    assert pos.unit == "m"
    assert smooth.unit == "m"
    assert vel.unit == "m/s"
    assert acc.unit == "m/s²"

    # 校验 status 与 produced_by
    for item in derived:
        assert item.status == "valid"
        assert item.produced_by == "ai_physics_tracker.kinematics.v1"
        assert item.track_id == track_id
        assert item.calibration_ref == session.active_calibration(video_id).calibration_id
        assert len(item.frames) == 20
        assert len(item.values) == 20

    # 校验 pipeline 参数记录完整性
    assert pos.pipeline == (
        {
            "step": "calibration_transform",
            "params": {"calibration_id": str(session.active_calibration(video_id).calibration_id)},
        },
    )
    assert len(vel.pipeline) == 2
    assert vel.pipeline[1]["step"] == "savitzky_golay"
    assert vel.pipeline[1]["params"]["deriv"] == 1
    assert vel.pipeline[1]["params"]["window_length"] == 7
    assert vel.pipeline[1]["params"]["polyorder"] == 2
    assert vel.pipeline[1]["params"]["delta"] == pytest.approx(1.0 / 30.0)


def test_compute_kinematics_without_calibration(tmp_path: Path) -> None:
    session = ProjectSession.start(ProjectRepository())
    video, timeline = session.register_external_video(tmp_path / "clip.mp4", _info())
    track = session.add_track(video.video_id, "Track Uncalibrated")

    for f in range(15):
        session.mark_point(track.track_id, f, pixel_x=10.0 + f * 2.0, pixel_y=20.0 + f * 3.0)

    derived = session.compute_kinematics(track.track_id, window_length=5, polyorder=2)
    assert len(derived) == 4

    pos, smooth, vel, acc = derived
    assert pos.unit == "px"
    assert smooth.unit == "px"
    assert vel.unit == "px/s"
    assert acc.unit == "px/s²"

    assert pos.calibration_ref is None
    assert smooth.calibration_ref is None
    assert vel.calibration_ref is None
    assert acc.calibration_ref is None

    assert pos.pipeline == ()
    assert len(vel.pipeline) == 1
    assert vel.pipeline[0]["step"] == "savitzky_golay"


def test_compute_replaces_existing_and_stale(tmp_path: Path) -> None:
    session, video_id, track_id = _session_with_calibrated_track(tmp_path)

    # 第一次计算
    first_run = session.compute_kinematics(track_id)
    assert len(session.project.derived) == 4

    # 再次调用重算
    second_run = session.recompute_kinematics(track_id)
    assert len(session.project.derived) == 4
    # derived_id 重新生成，替换旧记录
    assert {d.derived_id for d in second_run} != {d.derived_id for d in first_run}
    assert all(d.status == "valid" for d in session.project.derived)


def test_stale_on_annotation_change(tmp_path: Path) -> None:
    session, video_id, track_id = _session_with_calibrated_track(tmp_path)
    session.compute_kinematics(track_id)
    assert all(d.status == "valid" for d in session.project.derived)

    # 新增标注点，触发下游 DerivedData 自动置 stale
    session.mark_point(track_id, 20, pixel_x=200.0, pixel_y=800.0)
    assert all(d.status == "stale" for d in session.project.derived)

    # 重新计算后恢复 valid，且包含新的第 20 帧
    recomputed = session.compute_kinematics(track_id)
    assert all(d.status == "valid" for d in recomputed)
    assert len(recomputed[0].frames) == 21


def test_stale_on_calibration_change_ac10(tmp_path: Path) -> None:
    """AC-10: 标定变更后 DerivedData 自动置 stale，重算后恢复 valid。"""
    session, video_id, track_id = _session_with_calibrated_track(tmp_path)
    old_cal_id = session.active_calibration(video_id).calibration_id
    session.compute_kinematics(track_id)
    assert all(d.status == "valid" for d in session.project.derived)

    # 创建新的标定并切换为 active
    new_cal = session.add_calibration(
        video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(200.0, 0.0),
        known_length=2.0,
        unit="m",
        name="Scale 2m",
        set_active=True,
    )

    # 关联旧标定的派生数据应变为 stale
    assert all(
        d.status == "stale"
        for d in session.project.derived
        if d.calibration_ref == old_cal_id
    )

    # 重新计算，生成指向新标定的 valid 数据
    new_derived = session.compute_kinematics(track_id)
    assert all(d.status == "valid" for d in new_derived)
    assert all(d.calibration_ref == new_cal.calibration_id for d in new_derived)


def test_undo_redo_preserves_derived(tmp_path: Path) -> None:
    session, video_id, track_id = _session_with_calibrated_track(tmp_path)
    assert len(session.project.derived) == 0

    session.compute_kinematics(track_id)
    assert len(session.project.derived) == 4

    # 撤销计算
    assert session.can_undo
    session.undo()
    assert len(session.project.derived) == 0

    # 重做计算
    assert session.can_redo
    session.redo()
    assert len(session.project.derived) == 4
    assert all(d.status == "valid" for d in session.project.derived)


def test_clear_derived_and_derived_data_query(tmp_path: Path) -> None:
    session, video_id, track_id = _session_with_calibrated_track(tmp_path)
    session.compute_kinematics(track_id)

    vel = session.derived_data(track_id, "velocity")
    assert vel is not None
    assert vel.kind == "velocity"

    none_res = session.derived_data(track_id, "non_existent_kind")
    assert none_res is None

    session.clear_derived(track_id)
    assert len(session.project.derived) == 0
    assert session.derived_data(track_id, "velocity") is None


def test_pipeline_serialization_roundtrip_ac9(tmp_path: Path) -> None:
    """AC-9: DerivedData pipeline 参数完整记录在 project.json 中。"""
    session, video_id, track_id = _session_with_calibrated_track(tmp_path)
    session.compute_kinematics(track_id, window_length=7, polyorder=2)

    project_dir = tmp_path / "project_with_derived"
    session.save_as(project_dir)

    # 重新加载项目并校验 pipeline 参数
    loaded_session = ProjectSession.load(ProjectRepository(), project_dir)
    assert len(loaded_session.project.derived) == 4

    vel = loaded_session.derived_data(track_id, "velocity")
    assert vel is not None
    assert vel.unit == "m/s"
    assert vel.status == "valid"
    assert len(vel.pipeline) == 2
    assert vel.pipeline[0]["step"] == "calibration_transform"
    assert vel.pipeline[1]["step"] == "savitzky_golay"
    assert vel.pipeline[1]["params"]["window_length"] == 7
    assert vel.pipeline[1]["params"]["polyorder"] == 2
    assert vel.pipeline[1]["params"]["deriv"] == 1
    assert vel.pipeline[1]["params"]["delta"] == pytest.approx(1.0 / 30.0)


def test_compute_kinematics_unknown_track_raises(tmp_path: Path) -> None:
    session = ProjectSession.start(ProjectRepository())
    with pytest.raises(ProjectSessionError, match="unknown track_id"):
        session.compute_kinematics(uuid4())
