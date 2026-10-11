"""角运动计算纯函数：单摆/两点方向角度、段内 unwrap 与标量稀疏记录。

领域层模块：无 Qt 依赖、不持有状态。
角度定义依据 phase6-requirements.md R1 与 ADR-0019；世界系一律 y 向上。
"""

import math
from dataclasses import dataclass
from uuid import UUID

import numpy as np

from ai_physics_tracker.domain.kinematics import segment_by_nan


@dataclass(frozen=True)
class PendulumReference:
    """单摆角度参考：固定支点（像素坐标），与摆球使用同一标定变换。"""

    pivot_px: tuple[float, float]

    def __post_init__(self) -> None:
        if len(self.pivot_px) != 2:
            raise ValueError("pivot_px must contain exactly two coordinates")
        if not all(math.isfinite(value) for value in self.pivot_px):
            raise ValueError("pivot_px must be finite")


@dataclass(frozen=True)
class TwoPointReference:
    """刚体方向参考：同视频有序两轨迹 A→B 中的第二轨迹 B。"""

    reference_track_id: UUID


AngularReference = PendulumReference | TwoPointReference


def pendulum_theta_world(
    world_x: np.ndarray,
    world_y: np.ndarray,
    pivot_world_x: float,
    pivot_world_y: float,
) -> np.ndarray:
    """单摆摆角（phase6-requirements.md R1）：

    theta = atan2(world_x - pivot_x, -(world_y - pivot_y))

    竖直向下为零，向右摆动为正，范围 [-pi, pi]。NaN 观测保持 NaN；
    摆球与支点严格重合的帧无定义（NaN，不造 0）。
    """

    dx = np.asarray(world_x, dtype=float) - pivot_world_x
    dy = np.asarray(world_y, dtype=float) - pivot_world_y
    # -dy 在 dy == +0.0 时产生 -0.0，会使 atan2 把正右方解析成 π；
    # 加 +0.0 把 -0.0 规整回 +0.0，其余数值不受影响（IEEE 754）。
    theta = np.arctan2(dx, -dy + 0.0)
    coincident = (dx == 0.0) & (dy == 0.0)
    theta = np.where(coincident, np.nan, theta)
    return theta


def direction_theta_world(
    world_x_a: np.ndarray,
    world_y_a: np.ndarray,
    world_x_b: np.ndarray,
    world_y_b: np.ndarray,
) -> np.ndarray:
    """刚体平面方向角（phase6-requirements.md R1）：

    theta = atan2(world_y_B - world_y_A, world_x_B - world_x_A)

    +x 为零，逆时针为正，范围 [-pi, pi]。任一输入 NaN 的帧保持 NaN
    （同帧有效交集语义）；两点严格重合的帧无定义（NaN，不造 0）。
    """

    dx = np.asarray(world_x_b, dtype=float) - np.asarray(world_x_a, dtype=float)
    dy = np.asarray(world_y_b, dtype=float) - np.asarray(world_y_a, dtype=float)
    theta = np.arctan2(dy, dx)
    coincident = (dx == 0.0) & (dy == 0.0)
    theta = np.where(coincident, np.nan, theta)
    return theta


def unwrap_per_segment(theta: np.ndarray, discont: float = math.pi) -> np.ndarray:
    """在各连续有效段内独立 unwrap；不跨缺测段拼接整周偏移。

    段内使用 np.unwrap 语义（相邻差绝对值超过 discont 时补偿 ±2π）。
    NaN 位置保持 NaN；跨段的整周偏移无法从观测确定，不做任何恢复。
    """

    theta = np.asarray(theta, dtype=float)
    if theta.ndim != 1:
        raise ValueError("theta must be a 1D array")
    output = theta.copy()
    for start, end in segment_by_nan(theta):
        output[start:end] = np.unwrap(theta[start:end], discont=discont)
    return output


def dense_to_sparse_scalar_records(
    frames: np.ndarray, values: np.ndarray
) -> tuple[tuple[int, ...], tuple[tuple[float, ...], ...]]:
    """将含 NaN 的标量密集数组提取为无 NaN 的单列稀疏 (frames, values)。

    用于构造角运动 DerivedData 的单列 values 行。
    """

    if len(frames) != len(values):
        raise ValueError("frames and values must have equal lengths")
    if len(frames) == 0:
        return (), ()
    valid_mask = ~np.isnan(values)
    sparse_frames = tuple(int(f) for f in frames[valid_mask])
    sparse_values = tuple((float(v),) for v in values[valid_mask])
    return sparse_frames, sparse_values
