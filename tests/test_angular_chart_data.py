"""Phase 6.2 S1 — 角运动图表与相空间的数据适配测试（Qt-free）。

覆盖 phase-6.2 计划 AC-2/AC-3/AC-5 的纯数据部分：
- 单列 values 消费、rad/degree 显示转换（不改持久化数据）
- 时间轴绝对源帧时间、缺帧断线、wrapped θ 跨 ±π 断线
- θ–ω / x–vx 按源帧交集配对，配方 / 参考 / 标定 / 时序不一致时拒绝
- mixed valid/stale 整组 stale、参考与近似时序披露
- 旧线性五图遇到单列角量记录不退化
"""

from dataclasses import replace
from datetime import UTC, datetime
from math import pi
from pathlib import PurePosixPath
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.chart_data import (
    ANGLE_UNIT_DEGREE,
    build_chart_data,
)
from ai_physics_tracker.application.chart_recipe import (
    timing_identity,
    timing_summary,
)
from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import Project
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.domain.video import Video

_NOW = datetime(2026, 10, 13, tzinfo=UTC)
FPS = 30.0
PIVOT_PX = (100.0, 1000.0)

_ANGULAR_UNITS = {
    "angular_position": "rad",
    "smoothed_angular_position": "rad",
    "angular_velocity": "rad/s",
    "angular_acceleration": "rad/s²",
}


def _project(
    *,
    fps: float = FPS,
    zone: tuple[int, int] = (0, 99),
    track_names: tuple[str, ...] = ("Bob",),
    calibrated: bool = True,
) -> tuple[Project, UUID, dict[str, Track]]:
    video_id = uuid4()
    tracks = {
        name: Track(uuid4(), video_id, name, "#AABBCC", _NOW)
        for name in track_names
    }
    project = Project(
        project_id=uuid4(),
        name="angular chart test",
        created_at=_NOW,
        modified_at=_NOW,
        videos=(
            Video(
                video_id=video_id,
                file_path=PurePosixPath(f"videos/{video_id}.mp4"),
                display_name="test.mp4",
                width_px=640,
                height_px=480,
                fps_container=FPS,
                frame_count=100,
            ),
        ),
        timelines=(Timeline(video_id, fps, zone),),
        tracks=tuple(tracks.values()),
        derived=(),
    )
    if calibrated:
        calibration = Calibration(
            calibration_id=uuid4(),
            video_id=video_id,
            name="scale",
            scale_end_1_px=(0.0, 0.0),
            scale_end_2_px=(100.0, 0.0),
            known_length=1.0,
            unit="m",
            created_at=_NOW,
        )
        project = replace(
            project,
            calibrations=(calibration,),
            active_calibration_by_video={video_id: calibration.calibration_id},
        )
    return project, video_id, tracks


def _timing(*, fps: float = FPS, zone: tuple[int, int] = (0, 99), approximation=None):
    return {
        "fps_nominal": fps,
        "working_zone": list(zone),
        "approximation": approximation,
    }


def _angular_pipeline(
    calibration_id: UUID,
    *,
    mode: str = "pendulum",
    pivot: tuple[float, float] = PIVOT_PX,
    ref_track_id: UUID | None = None,
    deriv: int | None = None,
    window: int = 7,
    polyorder: int = 2,
    unwrap: bool = True,
    delta: float | None = None,
) -> tuple[dict, ...]:
    steps: list[dict] = [
        {"step": "calibration_transform",
         "params": {"calibration_id": str(calibration_id)}},
    ]
    if mode == "pendulum":
        reference = {"mode": "pendulum", "pivot_px": [pivot[0], pivot[1]]}
    else:
        reference = {"mode": "two_point", "reference_track_id": str(ref_track_id)}
    steps.append({"step": "angular_reference", "params": reference})
    if deriv is not None:
        if unwrap:
            steps.append({"step": "angular_unwrap", "params": {"discont": pi}})
        params: dict = {
            "window_length": window,
            "polyorder": polyorder,
            "deriv": deriv,
            "mode": "interp",
        }
        if deriv > 0:
            params["delta"] = delta if delta is not None else 1.0 / FPS
        steps.append({"step": "savitzky_golay", "params": params})
    return tuple(steps)


def _angular_record(
    track_id: UUID,
    kind: str,
    frames: tuple[int, ...],
    values: tuple[tuple[float, ...], ...],
    *,
    pipeline: tuple[dict, ...],
    calibration_id: UUID | None,
    status: str = "valid",
    reference_track_id: UUID | None = None,
    timing: dict | None = None,
    unit: str | None = None,
) -> DerivedData:
    extra_fields = {"timing_context": timing} if timing is not None else {}
    return DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind=kind,
        input=DerivedInput(track_id, reference_track_id=reference_track_id),
        pipeline=pipeline,
        frames=frames,
        values=values,
        payload_ref=None,
        unit=unit if unit is not None else _ANGULAR_UNITS[kind],
        produced_by="test",
        created_at=_NOW,
        status=status,
        calibration_ref=calibration_id,
        extra_fields=extra_fields,
    )


def _linear_pipeline(calibration_id: UUID | None, *, deriv: int, window: int = 7,
                     delta: float | None = None) -> tuple[dict, ...]:
    steps: list[dict] = []
    if calibration_id is not None:
        steps.append({"step": "calibration_transform",
                      "params": {"calibration_id": str(calibration_id)}})
    params: dict = {"window_length": window, "polyorder": 2,
                    "deriv": deriv, "mode": "interp"}
    if deriv > 0:
        params["delta"] = delta if delta is not None else 1.0 / FPS
    steps.append({"step": "savitzky_golay", "params": params})
    return tuple(steps)


def _linear_record(
    track_id: UUID,
    kind: str,
    frames: tuple[int, ...],
    values: tuple[tuple[float, ...], ...],
    *,
    unit: str,
    pipeline: tuple[dict, ...],
    calibration_id: UUID | None,
    timing: dict | None = None,
) -> DerivedData:
    extra_fields = {"timing_context": timing} if timing is not None else {}
    return DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind=kind,
        input=DerivedInput(track_id),
        pipeline=pipeline,
        frames=frames,
        values=values,
        payload_ref=None,
        unit=unit,
        produced_by="test",
        created_at=_NOW,
        status="valid",
        calibration_ref=calibration_id,
        extra_fields=extra_fields,
    )


def _cal_id(project: Project) -> UUID:
    return project.calibrations[0].calibration_id


def _with_derived(project: Project, *records: DerivedData) -> Project:
    return replace(project, derived=tuple(records))


# ---------------------------------------------------------------------------
# 角运动时间图：单列、单位、绝对时间、wrapped 断线
# ---------------------------------------------------------------------------


def test_angular_time_kinds_consume_single_column_values() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5, 6), ((0.1,), (0.2,)),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing()),
        _angular_record(bob, "angular_velocity", (5, 6), ((1.5,), (-1.5,)),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=_timing()),
        _angular_record(bob, "angular_acceleration", (5, 6), ((0.4,), (0.5,)),
                        pipeline=_angular_pipeline(cal, deriv=2),
                        calibration_id=cal, timing=_timing()),
    )

    theta = build_chart_data(project, video_id, (bob,), "theta_t")
    assert theta.title == "θ(t)"
    assert theta.x_unit == "s"
    assert theta.y_unit == "rad"
    assert theta.pixel_coordinates is False
    assert theta.series[0].component == "theta"
    assert theta.series[0].y_values == (0.1, 0.2)
    assert theta.series[0].x_values == pytest.approx((5 / FPS, 6 / FPS))
    assert theta.series[0].connect == (True, False)

    omega = build_chart_data(project, video_id, (bob,), "omega_t")
    assert omega.title == "ω(t)"
    assert omega.y_unit == "rad/s"
    assert omega.series[0].component == "omega"
    assert omega.series[0].y_values == (1.5, -1.5)

    alpha = build_chart_data(project, video_id, (bob,), "alpha_t")
    assert alpha.title == "α(t)"
    assert alpha.y_unit == "rad/s²"
    assert alpha.series[0].component == "alpha"


def test_theta_t_smoothed_flag_selects_unwrapped_smoothed_record() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5,), ((6.0,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing()),
        _angular_record(bob, "smoothed_angular_position", (5,), ((6.4,),),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, timing=_timing()),
    )

    raw = build_chart_data(project, video_id, (bob,), "theta_t")
    assert raw.series[0].y_values == (6.0,)
    assert raw.series[0].pipeline_summary.startswith("pendulum pivot px")
    assert "Savitzky-Golay" not in raw.series[0].pipeline_summary

    smoothed = build_chart_data(project, video_id, (bob,), "theta_t", smoothed=True)
    assert smoothed.series[0].y_values == (6.4,)
    assert "Savitzky-Golay window=7, polyorder=2" in smoothed.series[0].pipeline_summary
    assert "pendulum pivot px (100, 1000)" in smoothed.series[0].pipeline_summary


def test_time_axis_uses_absolute_source_frame_times_with_gaps() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_velocity", (12, 13, 20, 21),
                        ((0.0,), (0.1,), (0.2,), (0.3,)),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (bob,), "omega_t")
    series = chart.series[0]
    # 非零起点：时间从帧 12 的绝对时间开始，不从 0 重新编号。
    assert series.x_values == pytest.approx(
        (12 / FPS, 13 / FPS, 20 / FPS, 21 / FPS))
    assert series.connect == (True, False, True, False)


def test_raw_wrapped_theta_breaks_at_pi_jump_without_unwrapping() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    wrapped = (3.10, -3.10, -3.05, 0.00)
    project = _with_derived(
        project,
        _angular_record(
            bob, "angular_position", (5, 6, 7, 8),
            tuple((value,) for value in wrapped),
            pipeline=_angular_pipeline(cal), calibration_id=cal, timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (bob,), "theta_t")
    series = chart.series[0]
    # 帧 5→6 相邻但跨 ±π（|Δ| = 6.2 > π）：断线；6→7 与 7→8 连续：连线。
    assert series.connect == (False, True, True, False)
    # 不重新 unwrap、不写回：数值原样。
    assert series.y_values == pytest.approx(wrapped)


def test_degree_display_converts_values_and_units_without_mutating_records() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    records = (
        _angular_record(bob, "angular_position", (5,), ((0.5,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing()),
        _angular_record(bob, "angular_velocity", (5,), ((0.5,),),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=_timing()),
        _angular_record(bob, "angular_acceleration", (5,), ((0.5,),),
                        pipeline=_angular_pipeline(cal, deriv=2),
                        calibration_id=cal, timing=_timing()),
    )
    project = _with_derived(project, *records)

    theta = build_chart_data(project, video_id, (bob,), "theta_t",
                             angle_unit=ANGLE_UNIT_DEGREE)
    assert theta.series[0].y_values == pytest.approx((0.5 * 180.0 / pi,))
    assert theta.series[0].unit == "°"
    assert theta.y_unit == "°"
    omega = build_chart_data(project, video_id, (bob,), "omega_t",
                             angle_unit=ANGLE_UNIT_DEGREE)
    assert omega.y_unit == "°/s"
    assert omega.series[0].unit == "°/s"
    alpha = build_chart_data(project, video_id, (bob,), "alpha_t",
                             angle_unit=ANGLE_UNIT_DEGREE)
    assert alpha.y_unit == "°/s²"

    # 持久化数据不变：仍是 rad 原值。
    assert records[0].values == ((0.5,),)
    assert records[0].unit == "rad"
    radians = build_chart_data(project, video_id, (bob,), "theta_t")
    assert radians.series[0].y_values == (0.5,)


def test_wrong_column_count_or_unit_is_rejected_without_fabrication() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5,), ((1.0, 2.0),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (bob,), "theta_t")
    assert chart.series == ()
    assert any("not one column" in message for message in chart.messages)

    wrong_unit = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5,), ((1.0,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing(), unit="deg"),
    )
    chart = build_chart_data(wrong_unit, video_id, (bob,), "theta_t")
    assert chart.series == ()
    assert any("incompatible" in message for message in chart.messages)


def test_linear_charts_keep_working_when_only_angular_records_exist() -> None:
    """旧五图遇到单列角量记录不得退化（AC-2 回归）。"""
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5,), ((1.0,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (bob,), "x_t")
    assert chart.series == ()
    # 旧图消费 world_position；角量记录存在时明确报告缺失原因，不伪造列数错误。
    assert any("has no world_position derived data" in message
               for message in chart.messages)


def test_theta_t_refuses_mixing_pendulum_and_two_point_definitions() -> None:
    project, video_id, tracks = _project(track_names=("Bob", "Rod", "Ref"))
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    rod = tracks["Rod"].track_id
    ref = tracks["Ref"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5,), ((0.2,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing()),
        _angular_record(rod, "angular_position", (5,), ((0.3,),),
                        pipeline=_angular_pipeline(cal, mode="two_point",
                                                   ref_track_id=ref),
                        calibration_id=cal, reference_track_id=ref,
                        timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (bob, rod), "theta_t")
    assert [series.name for series in chart.series] == ["Bob"]
    assert any("pendulum" in message and "ignored" in message
               for message in chart.messages)


# ---------------------------------------------------------------------------
# 相空间：按源帧交集配对 + 配方 / 时序一致性
# ---------------------------------------------------------------------------


def _pair_project(
    *,
    omega_fn=None,
    omega_timing: dict | None = None,
    omega_status: str = "valid",
):
    """构造一条可配对的 θ–ω 轨迹；omega_fn(cal) 生成破坏一致性的 ω pipeline。"""
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    smooth = _angular_record(
        bob, "smoothed_angular_position", (10, 11, 12, 15),
        ((0.1,), (0.2,), (0.3,), (0.4,)),
        pipeline=_angular_pipeline(cal, deriv=0), calibration_id=cal,
        timing=_timing())
    omega = _angular_record(
        bob, "angular_velocity", (11, 12, 15, 16),
        ((1.1,), (1.2,), (1.5,), (1.6,)),
        pipeline=omega_fn(cal) if omega_fn else _angular_pipeline(cal, deriv=1),
        calibration_id=cal,
        timing=omega_timing if omega_timing is not None else _timing(),
        status=omega_status)
    return _with_derived(project, smooth, omega), video_id, bob


def test_theta_omega_pairs_by_source_frame_intersection() -> None:
    project, video_id, bob = _pair_project()

    chart = build_chart_data(project, video_id, (bob,), "theta_omega")
    assert chart.title == "θ–ω"
    assert chart.x_unit == "rad"
    assert chart.y_unit == "rad/s"
    assert chart.pixel_coordinates is False
    series = chart.series[0]
    # 交集 = (11, 12, 15)：θ 用帧 11/12/15 的值，ω 用同帧值，绝不行号 zip。
    assert series.frames == (11, 12, 15)
    assert series.x_values == pytest.approx((0.2, 0.3, 0.4))
    assert series.y_values == pytest.approx((1.1, 1.2, 1.5))
    assert series.connect == (True, False, False)
    assert series.status == "valid"
    assert "pendulum pivot px (100, 1000)" in series.pipeline_summary
    assert "Savitzky-Golay" in series.pipeline_summary

    degrees = build_chart_data(project, video_id, (bob,), "theta_omega",
                               angle_unit=ANGLE_UNIT_DEGREE)
    assert degrees.x_unit == "°"
    assert degrees.y_unit == "°/s"
    assert degrees.series[0].x_values == pytest.approx(
        tuple(value * 180.0 / pi for value in (0.2, 0.3, 0.4)))
    assert degrees.series[0].y_values == pytest.approx(
        tuple(value * 180.0 / pi for value in (1.1, 1.2, 1.5)))


def test_theta_omega_refuses_recipe_and_timing_mismatches() -> None:
    cases = {
        # SG 窗口不同 → 拒绝
        "window": (lambda cal: _angular_pipeline(cal, deriv=1, window=9),
                   "different Savitzky-Golay settings"),
        # 物理采样步长不符 → 拒绝
        "delta": (lambda cal: _angular_pipeline(cal, deriv=1, delta=1.0 / 25.0),
                  "sampling step"),
        # unwrap 步骤缺失 → 拒绝
        "unwrap": (lambda cal: _angular_pipeline(cal, deriv=1, unwrap=False),
                   "unwrap"),
        # 参考定义不同（支点）→ 拒绝
        "pivot": (lambda cal: _angular_pipeline(cal, deriv=1, pivot=(200.0, 500.0)),
                  "different angle references"),
    }
    for label, (omega_fn, expected) in cases.items():
        project, video_id, bob = _pair_project(omega_fn=omega_fn)
        chart = build_chart_data(project, video_id, (bob,), "theta_omega")
        assert chart.series == (), label
        assert any(expected in message for message in chart.messages), label

    # 缓存 fps 与当前时序不一致 → 拒绝，不猜旧来源
    project, video_id, bob = _pair_project(omega_timing=_timing(fps=25.0))
    chart = build_chart_data(project, video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("25 fps" in message and "refused" in message
               for message in chart.messages)

    # angular 结果缺失 timing_context → 无法确认，拒绝
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "smoothed_angular_position", (10,), ((0.1,),),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, timing=None),
        _angular_record(bob, "angular_velocity", (10,), ((1.1,),),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=_timing()),
    )
    chart = build_chart_data(project, video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("cannot be confirmed" in message for message in chart.messages)

    # 配对双方标定不同 → 拒绝
    project, video_id, tracks = _project()
    calibration = project.calibrations[0]
    other_cal = replace(calibration, calibration_id=uuid4(), name="other")
    cal = calibration.calibration_id
    project = replace(project, calibrations=(calibration, other_cal))
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "smoothed_angular_position", (10,), ((0.1,),),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, timing=_timing()),
        _angular_record(bob, "angular_velocity", (10,), ((1.1,),),
                        pipeline=_angular_pipeline(other_cal.calibration_id, deriv=1),
                        calibration_id=other_cal.calibration_id, timing=_timing()),
    )
    chart = build_chart_data(project, video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("different calibrations" in message for message in chart.messages)


def test_theta_omega_mixed_valid_stale_is_shown_as_stale_group() -> None:
    project, video_id, bob = _pair_project(omega_status="stale")

    chart = build_chart_data(project, video_id, (bob,), "theta_omega")
    assert len(chart.series) == 1
    assert chart.series[0].status == "stale"
    assert any("shown as stale" in message for message in chart.messages)


def test_theta_omega_reports_missing_pair_member_and_empty_intersection() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    only_smooth = _with_derived(
        project,
        _angular_record(bob, "smoothed_angular_position", (10,), ((0.1,),),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, timing=_timing()),
    )
    chart = build_chart_data(only_smooth, video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("has no angular_velocity derived data" in message
               for message in chart.messages)

    disjoint = _with_derived(
        project,
        _angular_record(bob, "smoothed_angular_position", (10, 11), ((0.1,), (0.2,)),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, timing=_timing()),
        _angular_record(bob, "angular_velocity", (20, 21), ((1.0,), (1.1,)),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=_timing()),
    )
    chart = build_chart_data(disjoint, video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("no common source frames" in message for message in chart.messages)


def test_theta_omega_zone_change_from_current_is_displayed_as_stale() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    old_zone = _timing(zone=(10, 50))
    project = _with_derived(
        project,
        _angular_record(bob, "smoothed_angular_position", (12,), ((0.1,),),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, timing=old_zone),
        _angular_record(bob, "angular_velocity", (12,), ((1.0,),),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=old_zone),
    )

    chart = build_chart_data(project, video_id, (bob,), "theta_omega")
    assert len(chart.series) == 1
    assert chart.series[0].status == "stale"
    assert any("working zone" in message for message in chart.messages)


def test_two_point_reference_is_disclosed_in_phase_summary() -> None:
    project, video_id, tracks = _project(track_names=("Rod A", "Rod B"))
    cal = _cal_id(project)
    track_a = tracks["Rod A"].track_id
    track_b = tracks["Rod B"].track_id
    project = _with_derived(
        project,
        _angular_record(track_a, "smoothed_angular_position", (10,), ((0.1,),),
                        pipeline=_angular_pipeline(cal, mode="two_point",
                                                   ref_track_id=track_b, deriv=0),
                        calibration_id=cal, reference_track_id=track_b,
                        timing=_timing()),
        _angular_record(track_a, "angular_velocity", (10,), ((1.0,),),
                        pipeline=_angular_pipeline(cal, mode="two_point",
                                                   ref_track_id=track_b, deriv=1),
                        calibration_id=cal, reference_track_id=track_b,
                        timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (track_a,), "theta_omega")
    assert "two-point A→B (reference: Rod B)" in chart.series[0].pipeline_summary


def test_approximate_timing_is_disclosed() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    approx = _timing(approximation='{"timing_method": "near_cfr_user_accepted_v1"}')
    project = _with_derived(
        project,
        _angular_record(bob, "angular_velocity", (5,), ((1.0,),),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=approx),
    )

    chart = build_chart_data(project, video_id, (bob,), "omega_t")
    assert len(chart.series) == 1
    assert any("approximate timing" in message for message in chart.messages)


# ---------------------------------------------------------------------------
# x–vx：线性相空间（smoothed_position + velocity）
# ---------------------------------------------------------------------------


def test_x_vx_pairs_smoothed_position_with_velocity_by_frames() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _linear_record(bob, "smoothed_position", (3, 4, 6),
                       ((0.10, 0.20), (0.22, 0.20), (0.30, 0.21)),
                       unit="m", pipeline=_linear_pipeline(cal, deriv=0),
                       calibration_id=cal, timing=_timing()),
        _linear_record(bob, "velocity", (4, 5, 6),
                       ((1.0, 0.0), (1.1, 0.0), (1.2, 0.0)),
                       unit="m/s", pipeline=_linear_pipeline(cal, deriv=1),
                       calibration_id=cal, timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (bob,), "x_vx")
    assert chart.title == "x–vx"
    assert chart.x_unit == "m"
    assert chart.y_unit == "m/s"
    series = chart.series[0]
    assert series.frames == (4, 6)
    assert series.x_values == pytest.approx((0.22, 0.30))
    assert series.y_values == pytest.approx((1.0, 1.2))
    assert series.connect == (False, False)
    # degree 显示参数对线性量无效：数值不变。
    degrees = build_chart_data(project, video_id, (bob,), "x_vx",
                               angle_unit=ANGLE_UNIT_DEGREE)
    assert degrees.x_unit == "m"
    assert degrees.series[0].x_values == pytest.approx((0.22, 0.30))


def test_x_vx_refuses_records_without_complete_timing_context() -> None:
    """旧线性记录缺 timing_context 时拒绝配对：导数 delta 不能替代
    fps / 区间 / 授权来源的确认（fail-closed，与 phase-6.2 计划一致）。"""
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id

    def _records(*, timing: dict | None, delta: float | None = None):
        return _with_derived(
            project,
            _linear_record(bob, "smoothed_position", (4,), ((0.2, 0.2),),
                           unit="m", pipeline=_linear_pipeline(cal, deriv=0),
                           calibration_id=cal, timing=timing),
            _linear_record(bob, "velocity", (4,), ((1.0, 0.0),),
                           unit="m/s",
                           pipeline=_linear_pipeline(cal, deriv=1, delta=delta),
                           calibration_id=cal, timing=timing),
        )

    # 完全没有 timing_context：即使 delta 与当前 fps 匹配也拒绝。
    chart = build_chart_data(_records(timing=None), video_id, (bob,), "x_vx")
    assert chart.series == ()
    assert any("cannot be confirmed" in message for message in chart.messages)

    # 只有 fps / approximation、缺 working_zone：同样拒绝并提示重算。
    partial = _records(timing={"fps_nominal": FPS, "approximation": None})
    chart = build_chart_data(partial, video_id, (bob,), "x_vx")
    assert chart.series == ()
    assert any("working zone" in message for message in chart.messages)

    # delta 与当前 fps 不符时同样拒绝（额外栅栏保留）。
    chart = build_chart_data(
        _records(timing=None, delta=1.0 / 25.0), video_id, (bob,), "x_vx"
    )
    assert chart.series == ()
    assert any("cannot be confirmed" in message for message in chart.messages)


# ---------------------------------------------------------------------------
# 定向回归：stale 保留、SG/unwrap 必备、pendulum 单轨迹、时序契约、比较基准
# ---------------------------------------------------------------------------


def test_theta_t_preserves_stale_status_without_context_mismatch() -> None:
    """记录 status='stale' 不因标定 / 区间 / 时序恰好一致而被洗白为 valid。"""
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5,), ((0.1,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing(), status="stale"),
    )

    chart = build_chart_data(project, video_id, (bob,), "theta_t")
    assert len(chart.series) == 1
    assert chart.series[0].status == "stale"
    assert any("stale" in message for message in chart.messages)


def test_smoothed_angular_records_require_smoothing_and_unwrap_steps() -> None:
    """平滑 / 导数角量必须有 SG 步骤与可读 unwrap；缺失即拒绝，不猜测来源。"""
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id

    def _smoothed(pipeline: tuple[dict, ...]) -> Project:
        return _with_derived(
            project,
            _angular_record(bob, "smoothed_angular_position", (5,), ((0.4,),),
                            pipeline=pipeline, calibration_id=cal,
                            timing=_timing()),
        )

    unwrap_only = _angular_pipeline(cal) + (
        {"step": "angular_unwrap", "params": {"discont": pi}},
    )
    chart = build_chart_data(_smoothed(unwrap_only), video_id, (bob,),
                             "theta_t", smoothed=True)
    assert chart.series == ()
    assert any("missing its Savitzky-Golay smoothing step" in message
               for message in chart.messages)

    no_unwrap = _angular_pipeline(cal, deriv=0, unwrap=False)
    chart = build_chart_data(_smoothed(no_unwrap), video_id, (bob,),
                             "theta_t", smoothed=True)
    assert chart.series == ()
    assert any("missing a readable unwrap step" in message
               for message in chart.messages)


def test_theta_omega_refuses_pendulum_pair_with_reference_track_input() -> None:
    """pendulum 定义是单轨迹：input 带参考轨迹即拒绝，不改动实际数据。"""
    project, video_id, tracks = _project(track_names=("Bob", "Pivot B"))
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    pivot = tracks["Pivot B"].track_id
    records = (
        _angular_record(bob, "smoothed_angular_position", (10,), ((0.1,),),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, reference_track_id=pivot,
                        timing=_timing()),
        _angular_record(bob, "angular_velocity", (10,), ((1.0,),),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, reference_track_id=pivot,
                        timing=_timing()),
    )
    project = _with_derived(project, *records)

    chart = build_chart_data(project, video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("pendulum" in message and "reference" in message
               for message in chart.messages)

    time_chart = build_chart_data(project, video_id, (bob,), "omega_t")
    assert time_chart.series == ()
    assert any("pendulum" in message and "reference" in message
               for message in time_chart.messages)
    # 不改实际数据：记录保持原值与原 status。
    assert records[0].values == ((0.1,),)
    assert records[0].status == "valid"


def test_timing_identity_rejects_non_positive_fps_and_malformed_fields() -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id

    def _record(timing: dict) -> DerivedData:
        return _angular_record(bob, "angular_position", (5,), ((0.1,),),
                               pipeline=_angular_pipeline(cal),
                               calibration_id=cal, timing=timing)

    assert timing_identity(_record({"fps_nominal": 0.0,
                                    "working_zone": [0, 99],
                                    "approximation": None})) is None
    assert timing_identity(_record({"fps_nominal": -FPS,
                                    "working_zone": [0, 99],
                                    "approximation": None})) is None
    assert timing_identity(_record({"fps_nominal": FPS,
                                    "working_zone": [0.5, 99],
                                    "approximation": None})) is None
    assert timing_identity(_record({"fps_nominal": FPS,
                                    "working_zone": ["0", 99],
                                    "approximation": None})) is None
    assert timing_identity(_record({"fps_nominal": FPS,
                                    "working_zone": [True, 99],
                                    "approximation": None})) is None
    assert timing_identity(_record({"fps_nominal": FPS,
                                    "working_zone": [99, 0],
                                    "approximation": None})) is None
    assert timing_identity(_record({"fps_nominal": FPS,
                                    "working_zone": [0, 99],
                                    "approximation": ""})) is None
    assert timing_identity(_record({"fps_nominal": FPS,
                                    "working_zone": [0, 99],
                                    "approximation": None})) is not None


@pytest.mark.parametrize(
    ("timing", "expected"),
    [
        ({"fps_nominal": FPS, "working_zone": [0.5, 99], "approximation": None},
         "unreadable recorded working zone"),
        ({"fps_nominal": FPS, "working_zone": ["0", 99], "approximation": None},
         "unreadable recorded working zone"),
        ({"fps_nominal": FPS, "working_zone": [99, 0], "approximation": None},
         "unreadable recorded working zone"),
        ({"fps_nominal": FPS, "working_zone": [0, 99], "approximation": ""},
         "unreadable timing approximation record"),
    ],
)
def test_theta_t_refuses_malformed_timing_context(
    timing: dict, expected: str
) -> None:
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id
    project = _with_derived(
        project,
        _angular_record(bob, "angular_position", (5,), ((0.1,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=timing),
    )

    chart = build_chart_data(project, video_id, (bob,), "theta_t")
    assert chart.series == ()
    assert any(expected in message for message in chart.messages)


def test_timing_summary_distinguishes_approximation_field_states() -> None:
    """缺 approximation 字段不得称为 exact timing；近似须显示实际说明。"""
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id

    def _record(timing: dict) -> DerivedData:
        return _angular_record(bob, "angular_position", (5,), ((0.1,),),
                               pipeline=_angular_pipeline(cal),
                               calibration_id=cal, timing=timing)

    exact = timing_summary(_record({"fps_nominal": FPS,
                                    "working_zone": [0, 99],
                                    "approximation": None}))
    assert "exact timing" in exact

    missing = timing_summary(_record({"fps_nominal": FPS,
                                      "working_zone": [0, 99]}))
    assert "timing source unrecorded" in missing
    assert "exact timing" not in missing

    note = '{"timing_method": "near_cfr_user_accepted_v1"}'
    approx = timing_summary(_record({"fps_nominal": FPS,
                                     "working_zone": [0, 99],
                                     "approximation": note}))
    assert "approximate timing" in approx
    assert note in approx


def test_comparison_basis_follows_first_displayable_series() -> None:
    """首条轨迹区间内无数据时不得绑定比较基准；其后不同 pivot 的正常轨迹应显示。"""
    project, video_id, tracks = _project(track_names=("Empty", "Good"))
    cal = _cal_id(project)
    empty = tracks["Empty"].track_id
    good = tracks["Good"].track_id
    project = _with_derived(
        project,
        # 第一条：pivot 不同（若被当作基准会排斥第二条）且区间内无数据。
        _angular_record(empty, "angular_position", (), (),
                        pipeline=_angular_pipeline(cal, pivot=(200.0, 500.0)),
                        calibration_id=cal, timing=_timing()),
        _angular_record(good, "angular_position", (5,), ((0.2,),),
                        pipeline=_angular_pipeline(cal), calibration_id=cal,
                        timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (empty, good), "theta_t")
    assert [series.name for series in chart.series] == ["Good"]
    assert any("no valid data" in message for message in chart.messages)


def test_phase_basis_follows_first_displayable_pair() -> None:
    """首对轨迹交集为空时不得绑定比较基准；其后不同 pivot 的正常配对应显示。"""
    project, video_id, tracks = _project(track_names=("Empty", "Good"))
    cal = _cal_id(project)
    empty = tracks["Empty"].track_id
    good = tracks["Good"].track_id
    project = _with_derived(
        project,
        # 第一对：pivot 不同且 θ 与 ω 帧不相交（无可展示序列）。
        _angular_record(empty, "smoothed_angular_position", (10, 11),
                        ((0.1,), (0.2,)),
                        pipeline=_angular_pipeline(cal, deriv=0,
                                                   pivot=(200.0, 500.0)),
                        calibration_id=cal, timing=_timing()),
        _angular_record(empty, "angular_velocity", (20, 21),
                        ((1.0,), (1.1,)),
                        pipeline=_angular_pipeline(cal, deriv=1,
                                                   pivot=(200.0, 500.0)),
                        calibration_id=cal, timing=_timing()),
        _angular_record(good, "smoothed_angular_position", (10, 11),
                        ((0.1,), (0.2,)),
                        pipeline=_angular_pipeline(cal, deriv=0),
                        calibration_id=cal, timing=_timing()),
        _angular_record(good, "angular_velocity", (10, 11),
                        ((1.0,), (1.1,)),
                        pipeline=_angular_pipeline(cal, deriv=1),
                        calibration_id=cal, timing=_timing()),
    )

    chart = build_chart_data(project, video_id, (empty, good), "theta_omega")
    assert [series.name for series in chart.series] == ["Good"]
    assert any("no common source frames" in message for message in chart.messages)


def test_rejected_phase_pair_does_not_claim_stale_display() -> None:
    project, video_id, bob = _pair_project(
        omega_fn=lambda cal: _angular_pipeline(cal, deriv=1, window=9)
    )
    records = tuple(replace(record, status="stale", extra_fields={
        "timing_context": _timing(zone=(0, 50))
    }) for record in project.derived)
    chart = build_chart_data(replace(project, derived=records), video_id, (bob,), "theta_omega")

    assert chart.series == ()
    assert any("ignored" in message for message in chart.messages)
    assert not any("shown as stale" in message for message in chart.messages)


def test_equivalent_nested_extension_parameters_do_not_hide_comparable_track() -> None:
    project, video_id, tracks = _project(track_names=("Bob", "Other"))
    cal = _cal_id(project)
    records = []
    for name, params in (("Bob", {"gain": 1.0, "options": {"a": 1, "b": 2}}),
                         ("Other", {"options": {"b": 2, "a": 1}, "gain": 1.0})):
        record = _angular_record(tracks[name].track_id, "angular_position", (5,), ((0.2,),),
                                 pipeline=(*_angular_pipeline(cal),
                                           {"step": "extension", "params": params}),
                                 calibration_id=cal, timing=_timing())
        record = replace(record, input=replace(record.input, extra_fields={"extension": params}))
        records.append(record)
    chart = build_chart_data(_with_derived(project, *records), video_id,
                            tuple(record.track_id for record in records), "theta_t")

    assert [series.name for series in chart.series] == ["Bob", "Other"]


def test_theta_omega_probes_reject_input_recipe_and_approximation_drift() -> None:
    """F1 探针回归：配对任一侧的输入选择 / SG 契约值 / 近似授权漂移，
    都把 1 条可展示序列拒为 0 条；一致配对保持可显示。"""
    project, video_id, tracks = _project()
    cal = _cal_id(project)
    bob = tracks["Bob"].track_id

    def _pair(
        *,
        omega_source_filter: str | None = None,
        omega_sg_mode: str = "interp",
        omega_approximation: object = None,
    ) -> Project:
        smooth = _angular_record(
            bob, "smoothed_angular_position", (10,), ((0.1,),),
            pipeline=_angular_pipeline(cal, deriv=0), calibration_id=cal,
            timing=_timing())
        pipeline = list(_angular_pipeline(cal, deriv=1))
        for step in pipeline:
            if step["step"] == "savitzky_golay":
                step["params"]["mode"] = omega_sg_mode
        omega = _angular_record(
            bob, "angular_velocity", (10,), ((1.0,),),
            pipeline=tuple(pipeline), calibration_id=cal,
            timing=_timing(approximation=omega_approximation))
        if omega_source_filter is not None:
            omega = replace(
                omega,
                input=replace(omega.input, source_filter=omega_source_filter),
            )
        return _with_derived(project, smooth, omega)

    chart = build_chart_data(_pair(), video_id, (bob,), "theta_omega")
    assert len(chart.series) == 1

    chart = build_chart_data(_pair(omega_source_filter="manual"),
                             video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("different input selections" in message
               for message in chart.messages)

    chart = build_chart_data(_pair(omega_sg_mode="nearest"),
                             video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("smoothing recipe" in message for message in chart.messages)

    chart = build_chart_data(
        _pair(omega_approximation='{"timing_method": "near_cfr_user_accepted_v1"}'),
        video_id, (bob,), "theta_omega")
    assert chart.series == ()
    assert any("different timing approximations" in message
               for message in chart.messages)
