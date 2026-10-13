"""角运动领域纯函数测试：角度定义、段内 unwrap、SG 导数解析精度。

覆盖 phase6-requirements.md AC-1/AC-2（ADR-0019 契约）：
- 单摆/两点方向的基准方向、符号、±π 跨界
- 恒角速/恒角加速的精确恢复（SG 对多项式精确）
- 解析正弦信号的 ω/α 归一化 RMSE 门槛与端点单独报告
- 缺测、重合点、短段语义
"""

from math import cos, pi, sin

import numpy as np
import pytest

from ai_physics_tracker.domain.angular import (
    PendulumReference,
    dense_to_sparse_scalar_records,
    direction_theta_world,
    pendulum_theta_world,
    unwrap_per_segment,
)
from ai_physics_tracker.domain.kinematics import differentiate_savgol, smooth_savgol

THETA_ATOL = 1e-10  # AC-1：解析原始角度绝对误差门槛（rad）


# ---------------------------------------------------------------------------
# AC-1：单摆角度定义（基准方向 / 符号 / 重合）
# ---------------------------------------------------------------------------


def test_pendulum_reference_directions_and_signs() -> None:
    """竖直向下为零、向右为正、上方为 ±π、向左为负。"""

    pivot_x, pivot_y = 1.2, -0.7
    length = 0.5
    # 世界系 y 向上；bob 位置 = pivot + L(sin θ, -cos θ)（θ=0 竖直向下）
    thetas = np.array([0.0, pi / 2, pi / 3, -pi / 6, 2.8, -2.8])
    world_x = pivot_x + length * np.sin(thetas)
    world_y = pivot_y - length * np.cos(thetas)

    recovered = pendulum_theta_world(world_x, world_y, pivot_x, pivot_y)

    np.testing.assert_allclose(recovered, thetas, atol=THETA_ATOL)


def test_pendulum_axis_directions_exact() -> None:
    """四个轴向基准：下 0、右 +π/2、上 π、左 -π/2。"""

    theta = pendulum_theta_world(
        np.array([0.0, 1.0, 0.0, -1.0]), np.array([-1.0, 0.0, 1.0, 0.0]), 0.0, 0.0
    )
    np.testing.assert_allclose(theta, [0.0, pi / 2, pi, -pi / 2], atol=THETA_ATOL)


def test_pendulum_coincident_with_pivot_is_undefined() -> None:
    """摆球与支点严格重合的帧无定义（NaN，不造 0）。"""

    theta = pendulum_theta_world(np.array([0.0, 0.4]), np.array([0.0, 0.0]), 0.0, 0.0)
    assert np.isnan(theta[0])
    assert theta[1] == pytest.approx(pi / 2, abs=THETA_ATOL)


def test_pendulum_nan_observation_stays_nan() -> None:
    theta = pendulum_theta_world(
        np.array([np.nan, 0.3, 0.4]), np.array([-0.5, np.nan, 0.0]), 0.0, 0.0
    )
    assert np.isnan(theta[0]) and np.isnan(theta[1])
    assert theta[2] == pytest.approx(pi / 2, abs=THETA_ATOL)


# ---------------------------------------------------------------------------
# AC-1：两点方向定义
# ---------------------------------------------------------------------------


def test_direction_reference_directions_and_sign() -> None:
    """+x 为零、逆时针为正（y 向上）。"""

    origin = np.zeros(4)
    dx = np.array([1.0, 0.0, -1.0, 0.0])
    dy = np.array([0.0, 1.0, 0.0, -1.0])
    theta = direction_theta_world(origin, origin, dx, dy)
    np.testing.assert_allclose(theta, [0.0, pi / 2, pi, -pi / 2], atol=THETA_ATOL)


def test_direction_theta_matches_atan2_definition() -> None:
    rng = np.random.default_rng(20261011)
    ax = rng.uniform(-2.0, 2.0, 64)
    ay = rng.uniform(-2.0, 2.0, 64)
    bx = rng.uniform(-2.0, 2.0, 64)
    by = rng.uniform(-2.0, 2.0, 64)
    # 排除随机重合（概率极低，稳妥起见显式分开一点）
    bx += np.where((bx == ax) & (by == ay), 0.5, 0.0)

    theta = direction_theta_world(ax, ay, bx, by)
    expected = np.arctan2(by - ay, bx - ax)
    np.testing.assert_allclose(theta, expected, atol=THETA_ATOL)


def test_direction_coincident_points_are_undefined() -> None:
    theta = direction_theta_world(
        np.array([1.0, 1.0]), np.array([2.0, 2.0]), np.array([1.0, 3.0]), np.array([2.0, 0.0])
    )
    assert np.isnan(theta[0])
    assert theta[1] == pytest.approx(-pi / 4, abs=THETA_ATOL)


def test_direction_intersection_missing_frames_are_nan() -> None:
    """任一轨迹缺测的帧不产生方向角（同帧有效交集语义）。"""

    theta = direction_theta_world(
        np.array([0.0, np.nan, 0.0]), np.array([0.0, 0.0, np.nan]),
        np.array([1.0, 1.0, 1.0]), np.array([1.0, 1.0, 1.0]),
    )
    assert theta[0] == pytest.approx(pi / 4, abs=THETA_ATOL)
    assert np.isnan(theta[1]) and np.isnan(theta[2])


# ---------------------------------------------------------------------------
# unwrap：段内独立、不跨段拼接、±π 跨界恢复
# ---------------------------------------------------------------------------


def test_unwrap_recovers_continuous_rotation_within_segment() -> None:
    """跨 ±π 的连续旋转在段内被 unwrap 还原为线性角度。"""

    t = np.linspace(0.0, 4.0, 81)
    true_theta = 0.9 * t - 1.2  # 线性增长，跨越 ±π
    wrapped = (true_theta + pi) % (2 * pi) - pi

    unwrapped = unwrap_per_segment(wrapped)

    # unwrap 只保证与真值相差 2π 的整数倍；线性信号应完全恢复
    np.testing.assert_allclose(unwrapped, true_theta, atol=1e-12)


def test_unwrap_does_not_stitch_across_nan_segments() -> None:
    """缺测两侧的整周偏移不做任何恢复（段独立 unwrap）。"""

    seg1 = np.array([2.9, 3.05, 3.2])          # 逼近 +π
    seg2 = np.array([-3.1, -2.95])             # 缺测后从 -π 附近重新开始
    theta = np.array([*seg1, np.nan, np.nan, *seg2])

    unwrapped = unwrap_per_segment(theta)

    np.testing.assert_allclose(unwrapped[:3], seg1, atol=1e-12)
    np.testing.assert_allclose(unwrapped[5:], seg2, atol=1e-12)
    assert np.isnan(unwrapped[3]) and np.isnan(unwrapped[4])


def test_unwrap_single_value_segment_unchanged() -> None:
    out = unwrap_per_segment(np.array([np.nan, 1.3, np.nan]))
    assert out[1] == pytest.approx(1.3, abs=1e-15)


# ---------------------------------------------------------------------------
# AC-1：恒角速 / 恒角加速 + 短段语义
# ---------------------------------------------------------------------------


def test_constant_angular_velocity_recovered_exactly() -> None:
    """θ(t) = ω t（段内 unwrap 后线性）：SG(deriv=1) 对多项式精确。"""

    fps = 30.0
    frames = np.arange(0, 90)
    t = frames / fps
    omega_true = 0.8
    theta = omega_true * t

    omega = differentiate_savgol(theta, deriv=1, delta=1.0 / fps)

    np.testing.assert_allclose(omega, omega_true, atol=1e-12)


def test_constant_angular_acceleration_recovered_exactly() -> None:
    """θ(t) = α t²/2：SG(polyorder=2, deriv=2) 对二次多项式精确。"""

    fps = 30.0
    frames = np.arange(0, 90)
    t = frames / fps
    alpha_true = 0.25
    theta = 0.5 * alpha_true * t**2

    alpha = differentiate_savgol(theta, deriv=2, delta=1.0 / fps)

    np.testing.assert_allclose(alpha, alpha_true, atol=1e-10)


def test_short_segment_keeps_raw_theta_without_derivatives() -> None:
    """R1：短段（< polyorder+1）保留可定义的原始角度，不造 ω/α。"""

    theta = np.array([0.1, 0.2, np.nan, np.nan, np.nan, 0.15, 0.25, 0.35, np.nan, 0.3])
    smoothed = smooth_savgol(theta, window_length=7, polyorder=2)
    omega = differentiate_savgol(theta, window_length=7, polyorder=2, deriv=1, delta=1.0)

    # 长度 2 的段不满足短段缩窗规则 → 平滑与导数保持 NaN
    assert np.isnan(smoothed[0]) and np.isnan(omega[0])
    # 长度 3 的段可缩窗到 3 → 有输出；长度 1 的段无导数
    assert not np.isnan(smoothed[5]) and not np.isnan(omega[5])
    assert np.isnan(smoothed[9]) and np.isnan(omega[9])


# ---------------------------------------------------------------------------
# AC-2：解析正弦信号精度（60 fps / 20 s / SG 7-2，段内去两端半窗口）
# ---------------------------------------------------------------------------


def test_sine_signal_omega_alpha_normalized_rmse_ac2() -> None:
    """θ = 0.2 sin(πt)：内域 ω/α 归一化 RMSE ≤ 2% / 5%，端点误差单独报告。"""

    fps = 60.0
    window_length, polyorder = 7, 2
    frames = np.arange(0, 1201)  # 20 s
    t = frames / fps
    amplitude, omega_sig = 0.2, pi

    theta = amplitude * np.sin(omega_sig * t)
    omega_true = amplitude * omega_sig * np.cos(omega_sig * t)
    alpha_true = -amplitude * omega_sig**2 * np.sin(omega_sig * t)

    unwrapped = unwrap_per_segment(theta)  # |θ| ≤ 0.2 < π，unwrap 恒等
    omega = differentiate_savgol(
        unwrapped, window_length=window_length, polyorder=polyorder,
        deriv=1, delta=1.0 / fps,
    )
    alpha = differentiate_savgol(
        unwrapped, window_length=window_length, polyorder=polyorder,
        deriv=2, delta=1.0 / fps,
    )

    half = window_length // 2
    interior = slice(half, len(t) - half)
    omega_rmse = float(np.sqrt(np.mean((omega[interior] - omega_true[interior]) ** 2)))
    alpha_rmse = float(np.sqrt(np.mean((alpha[interior] - alpha_true[interior]) ** 2)))
    omega_rel = omega_rmse / np.max(np.abs(omega_true))
    alpha_rel = alpha_rmse / np.max(np.abs(alpha_true))

    # 端点误差另行报告：只随断言消息披露，不设门槛（AC-2）。
    edge = np.concatenate([np.arange(0, half), np.arange(len(t) - half, len(t))])
    omega_edge_rmse = float(np.sqrt(np.mean((omega[edge] - omega_true[edge]) ** 2)))
    alpha_edge_rmse = float(np.sqrt(np.mean((alpha[edge] - alpha_true[edge]) ** 2)))

    assert omega_rel <= 0.02, (
        f"omega normalized RMSE {omega_rel:.4%} > 2%; "
        f"endpoint omega RMSE {omega_edge_rmse:.3e} rad/s (reported separately)"
    )
    assert alpha_rel <= 0.05, (
        f"alpha normalized RMSE {alpha_rel:.4%} > 5%; "
        f"endpoint alpha RMSE {alpha_edge_rmse:.3e} rad/s² (reported separately)"
    )


def test_sine_with_gap_segments_trim_half_window_per_segment() -> None:
    """含缺测段的正弦：每段各自去两端半窗口后仍满足门槛。"""

    fps = 60.0
    window_length, polyorder = 7, 2
    frames = np.arange(0, 1201)
    t = frames / fps
    theta = 0.2 * np.sin(pi * t)
    omega_true = 0.2 * pi * np.cos(pi * t)

    theta = theta.astype(float)
    theta[400:520] = np.nan  # 中段缺测 ~2 s

    unwrapped = unwrap_per_segment(theta)
    omega = differentiate_savgol(
        unwrapped, window_length=window_length, polyorder=polyorder,
        deriv=1, delta=1.0 / fps,
    )

    half = window_length // 2
    valid = ~np.isnan(omega)
    interior_mask = np.zeros_like(valid)
    seg_start = None
    for idx in range(len(valid) + 1):
        in_seg = idx < len(valid) and valid[idx]
        if in_seg and seg_start is None:
            seg_start = idx
        elif not in_seg and seg_start is not None:
            interior_mask[seg_start + half: idx - half] = True
            seg_start = None

    errors = omega[interior_mask] - omega_true[interior_mask]
    rel = float(np.sqrt(np.mean(errors**2))) / np.max(np.abs(omega_true))
    assert rel <= 0.02
    # 缺测区间及各段端点未被计入，也不应被静默填补
    assert np.isnan(omega[400:520]).all()


# ---------------------------------------------------------------------------
# 标量稀疏记录
# ---------------------------------------------------------------------------


def test_dense_to_sparse_scalar_records_drops_nan_and_wraps_single_column() -> None:
    frames = np.array([3, 4, 5, 6])
    values = np.array([0.1, np.nan, -0.2, 0.3])
    sparse_frames, sparse_values = dense_to_sparse_scalar_records(frames, values)
    assert sparse_frames == (3, 5, 6)
    assert sparse_values == ((0.1,), (-0.2,), (0.3,))
    assert all(len(row) == 1 for row in sparse_values)


def test_dense_to_sparse_scalar_records_empty_and_mismatch() -> None:
    assert dense_to_sparse_scalar_records(np.array([], dtype=int), np.array([])) == ((), ())
    with pytest.raises(ValueError, match="equal lengths"):
        dense_to_sparse_scalar_records(np.array([0, 1]), np.array([0.0]))


# ---------------------------------------------------------------------------
# 参考值对象校验
# ---------------------------------------------------------------------------


def test_pendulum_reference_rejects_non_finite_pivot() -> None:
    with pytest.raises(ValueError, match="finite"):
        PendulumReference(pivot_px=(float("nan"), 0.0))
    with pytest.raises(ValueError, match="exactly two"):
        PendulumReference(pivot_px=(1.0,))
    assert PendulumReference(pivot_px=(1.0, 2.0)).pivot_px == (1.0, 2.0)
