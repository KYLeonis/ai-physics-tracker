"""应用层 ProjectSession 角运动计算、多输入依赖失效与持久化测试。

覆盖 phase-6.1 AC-3/AC-4（ADR-0019 契约）：
- 单摆/两点方向四种 kind、单位、pipeline 与单列 values
- 主轨迹与参考轨迹编辑均使结果 stale；参考轨迹删除级联、Undo 恢复
- 标定变更/首次标定、Undo/Redo、保存重开 round-trip 与未知字段保留
"""

from dataclasses import replace
from math import cos, isclose, pi, sin
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.angular import PendulumReference, TwoPointReference
from ai_physics_tracker.domain.derived import ANGULAR_KINDS, DerivedData, DerivedInput
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

# 标定：100 px = 1 m，原点 (100, 1000)，无旋转。
# world_x = (px - 100) / 100, world_y = -(py - 1000) / 100。
PIVOT_PX = (100.0, 1000.0)
PENDULUM_LENGTH_M = 0.5
FPS = 30.0
FRAME_COUNT = 60


def _info() -> VideoStreamInfo:
    return VideoStreamInfo(640, 480, FPS, FRAME_COUNT, "synthetic", "cfr")


def _bob_pixel(theta: float) -> tuple[float, float]:
    """摆角 θ 对应的摆球像素位置（world: pivot + L(sinθ, -cosθ)）。"""

    world_x = PENDULUM_LENGTH_M * sin(theta)
    world_y = -PENDULUM_LENGTH_M * cos(theta)
    return 100.0 + 100.0 * world_x, 1000.0 - 100.0 * world_y


def _session_with_calibration(
    tmp_path: Path, *, track_names: tuple[str, ...] = ("Pendulum Bob",)
):
    session = ProjectSession.start(ProjectRepository())
    video, _timeline = session.register_external_video(tmp_path / "clip.avi", _info())
    tracks = tuple(session.add_track(video.video_id, name) for name in track_names)
    session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
        origin_px=PIVOT_PX,
        rotation_deg=0.0,
        set_active=True,
    )
    return session, video.video_id, tracks


def _mark_pendulum_swing(session: ProjectSession, track_id, frames: range) -> None:
    for f in frames:
        theta = 0.3 * sin(2.0 * pi * (f / FPS) / 3.0)
        pixel_x, pixel_y = _bob_pixel(theta)
        session.mark_point(track_id, f, pixel_x=pixel_x, pixel_y=pixel_y)


def _angular_records(session: ProjectSession, track_id) -> tuple[DerivedData, ...]:
    return tuple(
        record
        for record in session.project.derived
        if record.track_id == track_id and record.kind in ANGULAR_KINDS
    )


# ---------------------------------------------------------------------------
# 计算结构与数值正确性
# ---------------------------------------------------------------------------


def test_compute_angular_pendulum_structure_and_value(tmp_path: Path) -> None:
    session, video_id, (bob,) = _session_with_calibration(tmp_path)
    _mark_pendulum_swing(session, bob.track_id, range(30))
    cal_id = session.active_calibration(video_id).calibration_id

    derived = session.compute_angular(
        bob.track_id, reference=PendulumReference(pivot_px=PIVOT_PX)
    )

    assert tuple(item.kind for item in derived) == ANGULAR_KINDS
    assert tuple(item.unit for item in derived) == ("rad", "rad", "rad/s", "rad/s²")
    for item in derived:
        assert item.status == "valid"
        assert item.produced_by == "ai_physics_tracker.angular.v1"
        assert item.calibration_ref == cal_id
        assert item.input.reference_track_id is None
        assert all(len(row) == 1 for row in item.values)

    theta_record, smooth, omega, alpha = derived
    # 原始角度解析值：首帧 θ(0) = 0
    assert theta_record.values[0][0] == pytest.approx(0.0, abs=1e-12)
    peak_frame = max(
        range(30), key=lambda f: abs(0.3 * sin(2.0 * pi * (f / FPS) / 3.0))
    )
    expected_peak = 0.3 * sin(2.0 * pi * (peak_frame / FPS) / 3.0)
    assert theta_record.values[peak_frame][0] == pytest.approx(expected_peak, abs=1e-9)

    # pipeline：原始 = 标定 + 角度定义；导数各多 unwrap + savgol
    assert theta_record.pipeline == (
        {"step": "calibration_transform", "params": {"calibration_id": str(cal_id)}},
        {"step": "angular_reference",
         "params": {"mode": "pendulum", "pivot_px": [100.0, 1000.0]}},
    )
    for item, deriv in ((smooth, 0), (omega, 1), (alpha, 2)):
        steps = [step["step"] for step in item.pipeline]
        assert steps == [
            "calibration_transform", "angular_reference", "angular_unwrap", "savitzky_golay",
        ]
        sg_params = item.pipeline[-1]["params"]
        assert sg_params["deriv"] == deriv
        if deriv > 0:
            assert sg_params["delta"] == pytest.approx(1.0 / FPS)
        else:
            assert "delta" not in sg_params
    assert omega.pipeline[2]["params"]["discont"] == pytest.approx(pi)


def test_compute_angular_requires_active_calibration(tmp_path: Path) -> None:
    session = ProjectSession.start(ProjectRepository())
    video, _timeline = session.register_external_video(tmp_path / "clip.avi", _info())
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, pixel_x=100.0, pixel_y=900.0)

    with pytest.raises(ProjectSessionError, match="active calibration"):
        session.compute_angular(
            track.track_id, reference=PendulumReference(pivot_px=PIVOT_PX)
        )


def test_compute_angular_two_point_reference_and_intersection(tmp_path: Path) -> None:
    session, video_id, (track_a, track_b) = _session_with_calibration(
        tmp_path, track_names=("Rod A", "Rod B")
    )
    # A 固定在原点；B 绕 A 匀速转 0..14 帧（两点方向 = 方向角）
    for f in range(15):
        angle = 0.05 * f
        session.mark_point(track_a.track_id, f, pixel_x=100.0, pixel_y=1000.0)
        session.mark_point(
            track_b.track_id, f,
            pixel_x=100.0 + 100.0 * cos(angle),
            pixel_y=1000.0 - 100.0 * sin(angle),
        )
    # B 独占帧：只对两轨迹交集之外 → 不应出现在角度结果中
    session.mark_point(track_b.track_id, 20, pixel_x=200.0, pixel_y=1000.0)

    derived = session.compute_angular(
        track_a.track_id, reference=TwoPointReference(reference_track_id=track_b.track_id)
    )

    assert all(record.track_id == track_a.track_id for record in derived)
    assert all(record.input.reference_track_id == track_b.track_id for record in derived)
    theta = derived[0]
    assert theta.frames == tuple(range(15))
    assert theta.values[0][0] == pytest.approx(0.0, abs=1e-12)
    assert theta.values[7][0] == pytest.approx(0.35, abs=1e-9)
    assert theta.pipeline[1] == {
        "step": "angular_reference",
        "params": {"mode": "two_point", "reference_track_id": str(track_b.track_id)},
    }
    # A 自身无观测依赖问题：方向角对 B 的独占帧不造值
    assert all(frame != 20 for frame in theta.frames)


def test_two_point_reference_validation(tmp_path: Path) -> None:
    session, video_id, (track_a,) = _session_with_calibration(tmp_path)
    session.mark_point(track_a.track_id, 0, pixel_x=100.0, pixel_y=1000.0)

    with pytest.raises(ProjectSessionError, match="differ from the target track"):
        session.compute_angular(
            track_a.track_id,
            reference=TwoPointReference(reference_track_id=track_a.track_id),
        )
    with pytest.raises(ProjectSessionError, match="unknown reference track_id"):
        session.compute_angular(
            track_a.track_id, reference=TwoPointReference(reference_track_id=uuid4())
        )

    other_video, _ = session.register_external_video(tmp_path / "other.avi", _info())
    other_track = session.add_track(other_video.video_id, "Other Video Track")
    session.mark_point(other_track.track_id, 0, pixel_x=100.0, pixel_y=1000.0)
    with pytest.raises(ProjectSessionError, match="same video"):
        session.compute_angular(
            track_a.track_id,
            reference=TwoPointReference(reference_track_id=other_track.track_id),
        )


def test_compute_angular_replaces_existing_series(tmp_path: Path) -> None:
    session, video_id, (bob,) = _session_with_calibration(tmp_path)
    _mark_pendulum_swing(session, bob.track_id, range(30))

    first = session.compute_angular(
        bob.track_id, reference=PendulumReference(pivot_px=PIVOT_PX)
    )
    second = session.compute_angular(
        bob.track_id, reference=PendulumReference(pivot_px=(100.0, 999.0))
    )

    assert len(session.project.derived) == 4
    assert {d.derived_id for d in first}.isdisjoint({d.derived_id for d in second})
    assert all(d.status == "valid" for d in session.project.derived)
    # 换支点后的 pipeline 记录新支点
    theta = session.derived_data(bob.track_id, "angular_position")
    assert theta.pipeline[1]["params"]["pivot_px"] == [100.0, 999.0]


# ---------------------------------------------------------------------------
# AC-3：多输入依赖失效与 Undo/Redo
# ---------------------------------------------------------------------------


def test_stale_on_main_track_edit(tmp_path: Path) -> None:
    session, video_id, (bob,) = _session_with_calibration(tmp_path)
    _mark_pendulum_swing(session, bob.track_id, range(30))
    session.compute_angular(bob.track_id, reference=PendulumReference(pivot_px=PIVOT_PX))
    assert all(d.status == "valid" for d in _angular_records(session, bob.track_id))

    session.mark_point(bob.track_id, 30, pixel_x=120.0, pixel_y=1010.0)
    assert all(d.status == "stale" for d in _angular_records(session, bob.track_id))


def test_stale_on_reference_track_edit(tmp_path: Path) -> None:
    """参考轨迹的观测编辑同样是完整计算依赖（ADR-0019 第 2 节）。"""

    session, video_id, (track_a, track_b) = _session_with_calibration(
        tmp_path, track_names=("Rod A", "Rod B")
    )
    for f in range(15):
        session.mark_point(track_a.track_id, f, pixel_x=100.0 + f, pixel_y=1000.0)
        session.mark_point(track_b.track_id, f, pixel_x=200.0 + f, pixel_y=900.0 - f)
    session.compute_angular(
        track_a.track_id, reference=TwoPointReference(reference_track_id=track_b.track_id)
    )
    assert all(d.status == "valid" for d in _angular_records(session, track_a.track_id))

    # 只动参考轨迹 B：A 的角运动结果也必须 stale
    session.mark_point(track_b.track_id, 15, pixel_x=10.0, pixel_y=10.0)
    assert all(d.status == "stale" for d in _angular_records(session, track_a.track_id))


def test_reference_track_delete_cascades_and_undo_restores(tmp_path: Path) -> None:
    session, video_id, (track_a, track_b, track_c) = _session_with_calibration(
        tmp_path, track_names=("Rod A", "Rod B", "Bystander")
    )
    for f in range(15):
        session.mark_point(track_a.track_id, f, pixel_x=100.0 + f, pixel_y=1000.0)
        session.mark_point(track_b.track_id, f, pixel_x=200.0 + f, pixel_y=900.0 - f)
        session.mark_point(track_c.track_id, f, pixel_x=50.0, pixel_y=950.0)
    session.compute_angular(
        track_a.track_id, reference=TwoPointReference(reference_track_id=track_b.track_id)
    )
    session.compute_kinematics(track_c.track_id)
    assert len(_angular_records(session, track_a.track_id)) == 4

    session.remove_track(track_b.track_id)

    # 引用 B 的角运动结果级联删除；无关轨迹的运动学结果保留
    assert _angular_records(session, track_a.track_id) == ()
    assert len(_angular_records(session, track_c.track_id)) == 0
    assert len(tuple(d for d in session.project.derived if d.track_id == track_c.track_id)) == 4

    assert session.undo()
    assert len(_angular_records(session, track_a.track_id)) == 4
    assert all(d.status == "valid" for d in _angular_records(session, track_a.track_id))


def test_stale_on_calibration_switch_and_timeline_change(tmp_path: Path) -> None:
    session, video_id, (bob,) = _session_with_calibration(tmp_path)
    _mark_pendulum_swing(session, bob.track_id, range(30))
    session.compute_angular(bob.track_id, reference=PendulumReference(pivot_px=PIVOT_PX))

    session.add_calibration(
        video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(200.0, 0.0),
        known_length=2.0,
        unit="m",
        name="Scale 2m",
        set_active=True,
    )
    records = _angular_records(session, bob.track_id)
    assert all(d.status == "stale" for d in records)
    # 角度结果恒带 calibration_ref：首次标定规则（calibration_ref is None 过滤）不涉及


def test_undo_redo_compute_angular(tmp_path: Path) -> None:
    session, video_id, (bob,) = _session_with_calibration(tmp_path)
    _mark_pendulum_swing(session, bob.track_id, range(30))

    session.compute_angular(bob.track_id, reference=PendulumReference(pivot_px=PIVOT_PX))
    assert len(session.project.derived) == 4

    assert session.undo()
    assert session.project.derived == ()
    assert session.redo()
    assert len(session.project.derived) == 4
    assert all(d.status == "valid" for d in session.project.derived)


# ---------------------------------------------------------------------------
# AC-4：保存重开、未知字段保留与聚合校验
# ---------------------------------------------------------------------------


def test_angular_serialization_roundtrip_preserves_reference_and_pipeline(
    tmp_path: Path,
) -> None:
    session, video_id, (track_a, track_b) = _session_with_calibration(
        tmp_path, track_names=("Rod A", "Rod B")
    )
    for f in range(15):
        session.mark_point(track_a.track_id, f, pixel_x=100.0 + f, pixel_y=1000.0)
        session.mark_point(track_b.track_id, f, pixel_x=200.0 + f, pixel_y=900.0 - f)
    session.compute_angular(
        track_a.track_id, reference=TwoPointReference(reference_track_id=track_b.track_id)
    )
    session.compute_angular(
        track_a.track_id, reference=PendulumReference(pivot_px=PIVOT_PX)
    )
    # 注入未知扩展字段，验证 round-trip 保留
    session._project = replace(
        session.project,
        derived=tuple(
            replace(item, extra_fields={"future_angular_key": {"keep": True}})
            for item in session.project.derived
        ),
    )

    project_dir = tmp_path / "angular-project"
    session.save_as(project_dir)
    loaded = ProjectSession.load(ProjectRepository(), project_dir)

    assert len(loaded.project.derived) == 4
    for item in loaded.project.derived:
        assert item.input.reference_track_id is None  # 最终一次为单摆参考
        assert item.extra_fields["future_angular_key"] == {"keep": True}
        assert all(len(row) == 1 for row in item.values)
    omega = loaded.derived_data(track_a.track_id, "angular_velocity")
    assert omega is not None
    assert omega.unit == "rad/s"
    assert omega.pipeline[1]["params"]["mode"] == "pendulum"
    assert omega.pipeline[1]["params"]["pivot_px"] == [100.0, 1000.0]

    # 再算一次两点方向并保存重开：reference_track_id 往返保留
    loaded.compute_angular(
        track_a.track_id,
        reference=TwoPointReference(reference_track_id=track_b.track_id),
    )
    loaded.save_as(tmp_path / "angular-project-two-point")
    reloaded = ProjectSession.load(
        ProjectRepository(), tmp_path / "angular-project-two-point"
    )
    theta = reloaded.derived_data(track_a.track_id, "angular_position")
    assert theta is not None
    assert theta.input.reference_track_id == track_b.track_id
    assert theta.pipeline[1]["params"]["reference_track_id"] == str(track_b.track_id)


def test_derived_input_rejects_self_reference() -> None:
    track_id = uuid4()
    with pytest.raises(ValueError, match="cannot reference its own track"):
        DerivedInput(track_id=track_id, reference_track_id=track_id)


def test_validate_project_rejects_dangling_reference_track(tmp_path: Path) -> None:
    session, video_id, (track_a, track_b) = _session_with_calibration(
        tmp_path, track_names=("Rod A", "Rod B")
    )
    for f in range(5):
        session.mark_point(track_a.track_id, f, pixel_x=100.0 + f, pixel_y=1000.0)
        session.mark_point(track_b.track_id, f, pixel_x=200.0 + f, pixel_y=900.0 - f)
    session.compute_angular(
        track_a.track_id, reference=TwoPointReference(reference_track_id=track_b.track_id)
    )
    records = session.project.derived

    dangling = tuple(
        replace(
            record,
            input=replace(
                record.input, reference_track_id=uuid4(), track_id=record.track_id
            ),
        )
        for record in records
    )
    with pytest.raises(ValueError, match="reference track must be registered"):
        replace(session.project, derived=dangling)


def test_first_calibration_leaves_angular_unaffected_scenario_guard(
    tmp_path: Path,
) -> None:
    """角运动结果恒带 calibration_ref；首版无像素角度结果可被首次标定规则触及。"""

    session, video_id, (bob,) = _session_with_calibration(tmp_path)
    _mark_pendulum_swing(session, bob.track_id, range(30))
    session.compute_angular(bob.track_id, reference=PendulumReference(pivot_px=PIVOT_PX))
    # 清除 active 标定 → 角度结果 stale（解释基准消失）
    session.set_active_calibration(video_id, None)
    assert all(d.status == "stale" for d in _angular_records(session, bob.track_id))
