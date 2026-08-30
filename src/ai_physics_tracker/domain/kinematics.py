"""运动学计算纯函数：密集网格展开、批量标定变换、NaN 分段与 Savitzky-Golay 平滑/微分。

领域层模块：无 Qt 依赖、不持有状态。
遵循 ADR-0008 与 phase3-requirements.md R4/R5。
"""

from math import radians
from typing import Sequence
import numpy as np
from scipy.signal import savgol_filter

from ai_physics_tracker.domain.calibration import CalibrationTransform
from ai_physics_tracker.domain.track import TrackPoint


def expand_to_dense_grid(
    points: Sequence[TrackPoint],
    frame_range: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """将稀疏的 TrackPoint 序列展开为连续帧索引的密集 NumPy 数组。

    缺测帧位置填充 NaN。

    Args:
        points: TrackPoint 观测点序列。
        frame_range: 可选的 (start_frame, end_frame) 闭区间。若为 None，
            在 points 非空时使用 [min(frame), max(frame)]，为空时返回空数组。

    Returns:
        (frames, px_x, px_y) 三元组，均为一维 NumPy 数组。
    """
    if frame_range is not None:
        start, end = frame_range
        if start < 0 or start > end:
            raise ValueError("frame_range must satisfy 0 <= start <= end")
        frames = np.arange(start, end + 1, dtype=int)
    else:
        if not points:
            return (
                np.empty((0,), dtype=int),
                np.empty((0,), dtype=float),
                np.empty((0,), dtype=float),
            )
        start = min(p.frame_index for p in points)
        end = max(p.frame_index for p in points)
        frames = np.arange(start, end + 1, dtype=int)

    px_x = np.full(len(frames), np.nan, dtype=float)
    px_y = np.full(len(frames), np.nan, dtype=float)

    for point in points:
        if start <= point.frame_index <= end:
            idx = point.frame_index - start
            px_x[idx] = point.pixel_x
            px_y[idx] = point.pixel_y

    return frames, px_x, px_y


def batch_pixel_to_world(
    px_x: np.ndarray,
    px_y: np.ndarray,
    transform: CalibrationTransform,
) -> tuple[np.ndarray, np.ndarray]:
    """对密集像素坐标数组批量执行标定变换（pixel -> world）。

    依据 data-model.md §6.2 / ADR-0008，NaN 处保持 NaN。

    Args:
        px_x: 像素 x 坐标一维数组。
        px_y: 像素 y 坐标一维数组。
        transform: 标定变换对象。

    Returns:
        (world_x, world_y) 物理世界坐标数组（标定声明单位）。
    """
    if px_x.ndim != 1 or px_y.ndim != 1:
        raise ValueError("px_x and px_y must be 1D arrays")
    if len(px_x) != len(px_y):
        raise ValueError("px_x and px_y must have equal lengths")
    if len(px_x) == 0:
        return np.empty((0,), dtype=float), np.empty((0,), dtype=float)

    origin_x, origin_y = transform.origin_px
    scale = transform.pixels_per_unit
    unrotated_x = (px_x - origin_x) / scale
    unrotated_y = -(px_y - origin_y) / scale
    angle = radians(transform.calibration.rotation_deg)

    world_x = np.cos(angle) * unrotated_x - np.sin(angle) * unrotated_y
    world_y = np.sin(angle) * unrotated_x + np.cos(angle) * unrotated_y

    return world_x, world_y


def segment_by_nan(data: np.ndarray) -> list[tuple[int, int]]:
    """将一维数组按 NaN 边界分割为连续有效段的 [start, end) 半开索引区间列表。

    依据 ADR-0008 D4 (contiguous segment slicing)。

    Args:
        data: 一维 NumPy 数组。

    Returns:
        连续非 NaN 区间索引 [(start, end), ...]，满足切片 data[start:end]。
    """
    if data.ndim != 1:
        raise ValueError("data must be a 1D array")
    if len(data) == 0:
        return []

    valid = ~np.isnan(data)
    segments: list[tuple[int, int]] = []
    in_segment = False
    start = 0

    for idx, is_valid in enumerate(valid):
        if is_valid and not in_segment:
            start = idx
            in_segment = True
        elif not is_valid and in_segment:
            segments.append((start, idx))
            in_segment = False

    if in_segment:
        segments.append((start, len(data)))

    return segments


def _savgol_filter_segmented(
    data: np.ndarray,
    window_length: int,
    polyorder: int,
    deriv: int,
    delta: float,
    mode: str,
) -> np.ndarray:
    """按连续有效段独立施加 Savitzky-Golay 平滑/微分滤波。

    ADR-0008 D4 规则：
    - 段长度 >= window_length：正常滤波。
    - 段长度 < window_length 且 >= polyorder + 1：缩短窗口至最近奇数。
    - 段长度 < polyorder + 1 或缩短后窗口 <= polyorder：跳过（保持 NaN）。
    - NaN 区域保持 NaN。
    """
    if data.ndim != 1:
        raise ValueError("data must be a 1D array")
    if window_length <= 0 or window_length % 2 == 0:
        raise ValueError("window_length must be a positive odd integer")
    if polyorder < 0 or polyorder >= window_length:
        raise ValueError("polyorder must be non-negative and less than window_length")
    if deriv < 0:
        raise ValueError("deriv must be non-negative")
    if deriv > polyorder:
        raise ValueError("polyorder must be greater than or equal to deriv")
    if delta <= 0:
        raise ValueError("delta must be positive")

    output = np.full(data.shape, np.nan, dtype=float)
    if len(data) == 0:
        return output

    segments = segment_by_nan(data)
    for start, end in segments:
        seg_len = end - start
        if seg_len >= window_length:
            eff_window = window_length
        else:
            cand = seg_len if seg_len % 2 == 1 else seg_len - 1
            if cand > polyorder:
                eff_window = cand
            else:
                continue

        filtered = savgol_filter(
            data[start:end],
            window_length=eff_window,
            polyorder=polyorder,
            deriv=deriv,
            delta=delta,
            mode=mode,
        )
        output[start:end] = filtered

    return output


def smooth_savgol(
    data: np.ndarray,
    window_length: int = 7,
    polyorder: int = 2,
    mode: str = "interp",
) -> np.ndarray:
    """对一维数组执行 Savitzky-Golay 平滑（deriv=0）。

    Args:
        data: 一维 NumPy 数组（可含 NaN）。
        window_length: 滤波窗口长度（必须为正奇数，默认 7）。
        polyorder: 多项式拟合阶数（默认 2）。
        mode: 边界处理模式（默认 'interp'）。

    Returns:
        平滑后的一维数组。
    """
    return _savgol_filter_segmented(
        data=data,
        window_length=window_length,
        polyorder=polyorder,
        deriv=0,
        delta=1.0,
        mode=mode,
    )


def differentiate_savgol(
    data: np.ndarray,
    window_length: int = 7,
    polyorder: int = 2,
    deriv: int = 1,
    delta: float = 1.0,
    mode: str = "interp",
) -> np.ndarray:
    """对一维数组执行 Savitzky-Golay 微分（deriv=1 或 deriv=2）。

    注意：delta 必须传入物理时间步长（1/fps_nominal），确保导数具有正确的物理单位。

    Args:
        data: 一维 NumPy 数组（可含 NaN）。
        window_length: 滤波窗口长度（必须为正奇数，默认 7）。
        polyorder: 多项式拟合阶数（默认 2）。
        deriv: 导数阶数（1 表示一阶导/速度，2 表示二阶导/加速度）。
        delta: 采样时间步长（秒，默认 1.0）。
        mode: 边界处理模式（默认 'interp'）。

    Returns:
        微分后的一维数组。
    """
    return _savgol_filter_segmented(
        data=data,
        window_length=window_length,
        polyorder=polyorder,
        deriv=deriv,
        delta=delta,
        mode=mode,
    )


def derive_unit(base_unit: str, deriv_order: int) -> str:
    """依据基础长度单位和微分阶数推导物理单位。

    Examples:
        ("m", 0) -> "m"
        ("m", 1) -> "m/s"
        ("m", 2) -> "m/s²"
        ("px", 1) -> "px/s"
    """
    if deriv_order < 0:
        raise ValueError("deriv_order must be non-negative")
    if deriv_order == 0:
        return base_unit
    if deriv_order == 1:
        return f"{base_unit}/s"
    if deriv_order == 2:
        return f"{base_unit}/s²"
    return f"{base_unit}/s^{deriv_order}"


def dense_to_sparse_records(
    frames: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
) -> tuple[tuple[int, ...], tuple[tuple[float, ...], ...]]:
    """将包含 NaN 的密集数组提取为无 NaN 的稀疏 (frames, values) 元组。

    用于构造持久化与跨层传输的 DerivedData 对象。
    """
    if len(frames) != len(x) or len(frames) != len(y):
        raise ValueError("frames, x, and y must have equal lengths")
    if len(frames) == 0:
        return (), ()

    valid_mask = ~(np.isnan(x) | np.isnan(y))
    sparse_frames = tuple(int(f) for f in frames[valid_mask])
    sparse_values = tuple(
        (float(xi), float(yi)) for xi, yi in zip(x[valid_mask], y[valid_mask])
    )
    return sparse_frames, sparse_values
