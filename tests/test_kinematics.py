"""领域层运动学计算纯函数测试：坐标转换、SG 平滑、一阶/二阶数值微分与 NaN 隔离。

对应 Phase 3 验收标准：
- AC-3: 标定后坐标转换误差满足设计精度（误差 < 1e-9）
- AC-4: 匀速合成数据验证速度计算正确（偏差 < 0.01 m/s）
- AC-5: 匀加速合成数据验证加速度计算正确（偏差 < 0.05 m/s²）
- AC-6: NaN 处理正确（缺测帧不造值、不跨段平滑、短段自适应缩窗）
"""

from datetime import datetime, timezone
from uuid import uuid4
import numpy as np
import pytest

from ai_physics_tracker.domain.calibration import Calibration, CalibrationTransform
from ai_physics_tracker.domain.kinematics import (
    batch_pixel_to_world,
    dense_to_sparse_records,
    differentiate_savgol,
    derive_unit,
    expand_to_dense_grid,
    segment_by_nan,
    smooth_savgol,
)
from ai_physics_tracker.domain.track import TrackPoint


def _make_track_point(
    track_id: uuid4,
    frame_index: int,
    pixel_x: float,
    pixel_y: float,
    time_s: float | None = None,
) -> TrackPoint:
    now = datetime.now(timezone.utc)
    return TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=frame_index,
        time_s=time_s if time_s is not None else frame_index / 30.0,
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        source="manual",
        visibility="visible",
        status="active",
        created_at=now,
        modified_at=now,
    )


def test_expand_to_dense_grid_sparse_and_empty() -> None:
    track_id = uuid4()
    points = [
        _make_track_point(track_id, 2, 10.0, 20.0),
        _make_track_point(track_id, 5, 13.0, 23.0),
        _make_track_point(track_id, 8, 16.0, 26.0),
    ]

    # 不指定 frame_range：以 min/max 帧展开
    frames, px_x, px_y = expand_to_dense_grid(points)
    assert np.array_equal(frames, np.arange(2, 9))
    assert px_x[0] == 10.0 and px_y[0] == 20.0
    assert np.isnan(px_x[1]) and np.isnan(px_y[1])
    assert px_x[3] == 13.0 and px_y[3] == 23.0
    assert px_x[6] == 16.0 and px_y[6] == 26.0

    # 指定 frame_range=(0, 10)
    frames_full, px_x_full, px_y_full = expand_to_dense_grid(points, frame_range=(0, 10))
    assert np.array_equal(frames_full, np.arange(0, 11))
    assert np.isnan(px_x_full[0])
    assert px_x_full[2] == 10.0
    assert px_x_full[5] == 13.0
    assert px_x_full[8] == 16.0
    assert np.isnan(px_x_full[10])

    # 空点序列
    empty_frames, empty_x, empty_y = expand_to_dense_grid([])
    assert len(empty_frames) == 0
    assert len(empty_x) == 0
    assert len(empty_y) == 0

    # 非法 frame_range
    with pytest.raises(ValueError, match="frame_range"):
        expand_to_dense_grid(points, frame_range=(5, 3))


def test_batch_pixel_to_world_ac3() -> None:
    """AC-3: 标定后坐标转换误差满足设计精度（误差 < 1e-9）。"""
    video_id = uuid4()
    now = datetime.now(timezone.utc)
    # 标定：端点 (0,0)-(100,0), L = 50 mm -> s = 2 px/mm. 原点 (10, 20), 旋转 0 度
    cal = Calibration(
        calibration_id=uuid4(),
        video_id=video_id,
        name="Scale 50mm",
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=50.0,
        unit="mm",
        created_at=now,
        origin_px=(10.0, 20.0),
        rotation_deg=0.0,
    )
    transform = CalibrationTransform(calibration=cal, height_px=1080)

    # 构造像素坐标序列，含 NaN
    px_x = np.array([10.0, 10.0, np.nan, 20.0, 0.0], dtype=float)
    px_y = np.array([30.0, 10.0, np.nan, 20.0, 20.0], dtype=float)

    world_x, world_y = batch_pixel_to_world(px_x, px_y, transform)

    # 逐点与单个 transform.pixel_to_world 以及解析解比对
    # (10, 30) -> 原点下方 10px -> y = -5 mm, x = 0 mm
    assert np.isclose(world_x[0], 0.0, atol=1e-12)
    assert np.isclose(world_y[0], -5.0, atol=1e-12)

    # (10, 10) -> 原点上方 10px -> y = +5 mm, x = 0 mm
    assert np.isclose(world_x[1], 0.0, atol=1e-12)
    assert np.isclose(world_y[1], 5.0, atol=1e-12)

    # NaN 保持 NaN
    assert np.isnan(world_x[2]) and np.isnan(world_y[2])

    # 检查所有非 NaN 点与 transform.pixel_to_world 的一致性（误差 < 1e-9）
    for i in (0, 1, 3, 4):
        exp_x, exp_y = transform.pixel_to_world((float(px_x[i]), float(px_y[i])))
        assert abs(world_x[i] - exp_x) < 1e-9
        assert abs(world_y[i] - exp_y) < 1e-9


def test_segment_by_nan() -> None:
    # 纯非空无 NaN
    data = np.array([1.0, 2.0, 3.0, 4.0])
    assert segment_by_nan(data) == [(0, 4)]

    # 全 NaN
    data_all_nan = np.array([np.nan, np.nan, np.nan])
    assert segment_by_nan(data_all_nan) == []

    # 首尾与中间均有 NaN
    data_mixed = np.array([np.nan, 1.0, 2.0, np.nan, np.nan, 3.0, 4.0, 5.0, np.nan])
    assert segment_by_nan(data_mixed) == [(1, 3), (5, 8)]

    # 空数组
    assert segment_by_nan(np.empty((0,), dtype=float)) == []

    # 非 1D 抛错
    with pytest.raises(ValueError, match="1D array"):
        segment_by_nan(np.zeros((2, 2)))


def test_smooth_uniform_velocity_ac4() -> None:
    """AC-4: 匀速合成数据验证 v 计算正确（偏差 < 0.01 m/s）。"""
    fps = 30.0
    dt = 1.0 / fps
    n_frames = 100
    t = np.arange(n_frames) * dt

    vx_true = 2.0  # m/s
    vy_true = -1.2  # m/s
    x0 = 0.5
    y0 = 3.0

    x = x0 + vx_true * t
    y = y0 + vy_true * t

    # 1. 检验 SG 平滑保形
    smooth_x = smooth_savgol(x, window_length=7, polyorder=2)
    smooth_y = smooth_savgol(y, window_length=7, polyorder=2)
    assert np.allclose(smooth_x, x, atol=1e-10)
    assert np.allclose(smooth_y, y, atol=1e-10)

    # 2. 检验一阶数值微分（速度）
    vx_calc = differentiate_savgol(x, window_length=7, polyorder=2, deriv=1, delta=dt)
    vy_calc = differentiate_savgol(y, window_length=7, polyorder=2, deriv=1, delta=dt)

    # 扣除首尾 3 帧边界效应
    interior = slice(3, n_frames - 3)
    max_vx_err = np.max(np.abs(vx_calc[interior] - vx_true))
    max_vy_err = np.max(np.abs(vy_calc[interior] - vy_true))

    assert max_vx_err < 0.01, f"vx error {max_vx_err} exceeded tolerance 0.01 m/s"
    assert max_vy_err < 0.01, f"vy error {max_vy_err} exceeded tolerance 0.01 m/s"


def test_smooth_uniform_acceleration_ac5() -> None:
    """AC-5: 匀加速合成数据验证 a 计算正确（偏差 < 0.05 m/s²）。"""
    fps = 30.0
    dt = 1.0 / fps
    n_frames = 100
    t = np.arange(n_frames) * dt

    ax_true = 1.0  # m/s²
    ay_true = -9.8  # m/s²
    vx0 = 0.5
    vy0 = 5.0
    x0 = 0.0
    y0 = 10.0

    x = x0 + vx0 * t + 0.5 * ax_true * (t**2)
    y = y0 + vy0 * t + 0.5 * ay_true * (t**2)

    # 1. 速度微分验证 (vx = vx0 + ax * t, vy = vy0 + ay * t)
    vx_calc = differentiate_savgol(x, window_length=7, polyorder=2, deriv=1, delta=dt)
    vy_calc = differentiate_savgol(y, window_length=7, polyorder=2, deriv=1, delta=dt)
    interior = slice(3, n_frames - 3)
    assert np.allclose(vx_calc[interior], vx0 + ax_true * t[interior], atol=0.01)
    assert np.allclose(vy_calc[interior], vy0 + ay_true * t[interior], atol=0.01)

    # 2. 二阶微分（加速度）验证
    ax_calc = differentiate_savgol(x, window_length=7, polyorder=2, deriv=2, delta=dt)
    ay_calc = differentiate_savgol(y, window_length=7, polyorder=2, deriv=2, delta=dt)

    max_ax_err = np.max(np.abs(ax_calc[interior] - ax_true))
    max_ay_err = np.max(np.abs(ay_calc[interior] - ay_true))

    assert max_ax_err < 0.05, f"ax error {max_ax_err} exceeded tolerance 0.05 m/s²"
    assert max_ay_err < 0.05, f"ay error {max_ay_err} exceeded tolerance 0.05 m/s²"


def test_nan_gap_no_bridging_ac6() -> None:
    """AC-6: 缺测帧不造值、不跨越缺测段平滑。"""
    fps = 30.0
    dt = 1.0 / fps
    n_frames = 100
    t = np.arange(n_frames) * dt
    x = 2.0 * t

    # 在帧 40-60 设置 NaN 缺测区间
    x_gapped = x.copy()
    x_gapped[40:61] = np.nan

    smooth_x = smooth_savgol(x_gapped, window_length=7, polyorder=2)
    vx = differentiate_savgol(x_gapped, window_length=7, polyorder=2, deriv=1, delta=dt)

    # 缺测段必须完全为 NaN
    assert np.all(np.isnan(smooth_x[40:61]))
    assert np.all(np.isnan(vx[40:61]))

    # 有效段（0..39 和 61..99）内部不受缺测影响，结果与真值一致
    seg1_interior = slice(3, 37)
    seg2_interior = slice(64, 96)

    assert np.allclose(smooth_x[seg1_interior], x[seg1_interior], atol=1e-10)
    assert np.allclose(smooth_x[seg2_interior], x[seg2_interior], atol=1e-10)
    assert np.allclose(vx[seg1_interior], 2.0, atol=0.01)
    assert np.allclose(vx[seg2_interior], 2.0, atol=0.01)


def test_short_segment_window_shrink_ac6() -> None:
    """AC-6: 段长度 < window_length 时的自适应缩窗与超短段跳过。"""
    fps = 30.0
    dt = 1.0 / fps
    # 构造数据：
    # 段 1: 长度 5 (< window_length 7，但 >= polyorder+1=3) -> 自动缩窗至 5 滤波
    # 段 2: 长度 2 (< polyorder+1=3) -> 跳过，保持 NaN
    data = np.full(20, np.nan)
    data[2:7] = np.array([1.0, 2.0, 3.0, 4.0, 5.0])  # len 5
    data[12:14] = np.array([10.0, 20.0])  # len 2

    smooth = smooth_savgol(data, window_length=7, polyorder=2)
    vx = differentiate_savgol(data, window_length=7, polyorder=2, deriv=1, delta=dt)

    # 段 1 (2..6) 成功滤波
    assert not np.any(np.isnan(smooth[2:7]))
    assert not np.any(np.isnan(vx[2:7]))
    assert np.allclose(smooth[2:7], data[2:7], atol=1e-10)
    assert np.allclose(vx[2:7], 1.0 * fps, atol=1e-10)

    # 段 2 (12..13) 因数据过短无法拟合 2 阶多项式，保持 NaN
    assert np.all(np.isnan(smooth[12:14]))
    assert np.all(np.isnan(vx[12:14]))


def test_derive_unit() -> None:
    assert derive_unit("m", 0) == "m"
    assert derive_unit("m", 1) == "m/s"
    assert derive_unit("m", 2) == "m/s²"
    assert derive_unit("px", 0) == "px"
    assert derive_unit("px", 1) == "px/s"
    assert derive_unit("px", 2) == "px/s²"
    assert derive_unit("cm", 1) == "cm/s"
    assert derive_unit("mm", 2) == "mm/s²"

    with pytest.raises(ValueError, match="non-negative"):
        derive_unit("m", -1)


def test_pendulum_small_angle_synthetic() -> None:
    """单摆小角度合成数据 x(t) = A*sin(w*t) 验证 v 与 a 恢复精度。"""
    fps = 60.0
    dt = 1.0 / fps
    n_frames = 120
    t = np.arange(n_frames) * dt

    amplitude = 0.2  # 0.2 m
    length = 1.0  # 1.0 m
    g = 9.8
    omega = np.sqrt(g / length)  # ~3.13 rad/s

    x_true = amplitude * np.sin(omega * t)
    v_true = amplitude * omega * np.cos(omega * t)
    a_true = -amplitude * (omega**2) * np.sin(omega * t)

    v_calc = differentiate_savgol(x_true, window_length=7, polyorder=2, deriv=1, delta=dt)
    a_calc = differentiate_savgol(x_true, window_length=7, polyorder=2, deriv=2, delta=dt)

    interior = slice(5, n_frames - 5)
    # 单摆在 60fps、窗口 7 下的一阶与二阶微分精度
    assert np.allclose(v_calc[interior], v_true[interior], atol=0.01)
    assert np.allclose(a_calc[interior], a_true[interior], atol=0.1)


def test_dense_to_sparse_records() -> None:
    frames = np.array([0, 1, 2, 3, 4])
    x = np.array([10.0, np.nan, 20.0, np.nan, 30.0])
    y = np.array([15.0, 25.0, 35.0, np.nan, 45.0])

    sparse_frames, sparse_values = dense_to_sparse_records(frames, x, y)
    # 帧 0, 2, 4 两坐标均非 NaN
    assert sparse_frames == (0, 2, 4)
    assert sparse_values == ((10.0, 15.0), (20.0, 35.0), (30.0, 45.0))


def test_invalid_parameters_raise_value_error() -> None:
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    # 偶数窗口
    with pytest.raises(ValueError, match="positive odd integer"):
        smooth_savgol(data, window_length=4)
    # polyorder >= window_length
    with pytest.raises(ValueError, match="polyorder"):
        smooth_savgol(data, window_length=5, polyorder=5)
    # deriv > polyorder
    with pytest.raises(ValueError, match="polyorder"):
        differentiate_savgol(data, window_length=5, polyorder=1, deriv=2)
    # delta <= 0
    with pytest.raises(ValueError, match="delta"):
        differentiate_savgol(data, window_length=5, polyorder=2, deriv=1, delta=0.0)
