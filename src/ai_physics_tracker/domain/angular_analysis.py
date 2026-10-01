"""领域层：版本化角度导数、信息 extrema 与分段过零周期（无 Qt/I/O）。"""

from dataclasses import dataclass
from math import isfinite, pi
from statistics import mean, median

import numpy as np
import scipy
from scipy.signal import argrelextrema, savgol_filter

from ai_physics_tracker.domain.pendulum_reconstruction import (
    LEGACY_PROFILE_SHA256, STUDENT_PROFILE_SHA256,
)
from ai_physics_tracker.domain.scientific_result import is_sha256_hex
from ai_physics_tracker.domain.types import canonical_json_digest

CORE_VERSION = "angular-analysis-1.1.0"
DIAGNOSTICS_SHA256 = "d58670ec679057cd913407c52341b8aacab141bad162abbd894b0f76c26aae8e"
STUDENT = "student-default-v2"
LEGACY = "legacy-publication-v1"
SG_WINDOW = 9
SG_POLYORDER = 3
UNIFORM_DT_REL_TOL = 1e-6
TAIL_MIN_PERIODS = 10


def analysis_config(profile_id: str, *, sg_window: int = SG_WINDOW,
                    sg_polyorder: int = SG_POLYORDER) -> dict[str, object]:
    """展开本核心实际用到的 profile；历史算法只有显式请求才启用。"""
    if profile_id not in (STUDENT, LEGACY):
        raise ValueError(f"unsupported angular profile: {profile_id}")
    if (type(sg_window) is not int or sg_window < 3 or sg_window % 2 != 1
            or type(sg_polyorder) is not int or not 1 <= sg_polyorder < sg_window):
        raise ValueError("SG window must be an odd integer >= 3; polynomial order must be >= 1 and < window")
    custom = (sg_window, sg_polyorder) != (SG_WINDOW, SG_POLYORDER)
    if profile_id == LEGACY and custom:
        raise ValueError("legacy reproduction does not allow SG overrides")
    return {
        "profile_id": profile_id, "profile_version": "2.0.0" if profile_id == STUDENT else "1.0.0",
        "profile_sha256": STUDENT_PROFILE_SHA256 if profile_id == STUDENT else LEGACY_PROFILE_SHA256,
        "diagnostics_sha256": DIAGNOSTICS_SHA256, "core_version": CORE_VERSION,
        "numpy_version": np.__version__, "scipy_version": scipy.__version__,
        "resolved_overrides": {"sg_window": sg_window, "sg_polyorder": sg_polyorder,
                               "source": "user-settings; ADR-0019"} if custom else {},
        "derivative": {"window_frames": sg_window, "polyorder": sg_polyorder,
                       "deriv": 1, "mode": "interp", "presmoothing": False,
                       "delta": "segment_median_dt" if profile_id == STUDENT else "1/fps_nominal",
                       "minimum_segment_frames": sg_window if profile_id == STUDENT else None,
                       "uniform_dt_relative_tolerance": UNIFORM_DT_REL_TOL if profile_id == STUDENT else None},
        "tail": {"start": "last_third_strict" if profile_id == STUDENT else 70.0,
                 "minimum_periods": TAIL_MIN_PERIODS, "aggregate": "mean_per_period_omega2"},
        "period": {"zero_plateau": "split_raw_or_centered_zero" if profile_id == STUDENT else "legacy_sign_edges",
                   "isolated_zero": "opposite_neighbors" if profile_id == STUDENT else "legacy_sign_edges"},
        "information_extrema": {"order": "max(8,int(fps_nominal/10))", "mode": "clip", "insert_initial": False},
        "provenance": {"derivative": (["policy-student-v1", "metrics", "ADR-0019:user-settings"] if custom
                                      else ["policy-student-v1", "metrics"]) if profile_id == STUDENT else ["metrics"],
                       "period": ["tail", "policy-student-v1"] if profile_id == STUDENT else ["tail"],
                       "information_extrema": ["information"]},
    }


@dataclass(frozen=True)
class AngularSeries:
    """完整源时域角度序列；None 缺测，QC 标志必须是真 bool。"""

    upstream_digest: str
    frame_indices: tuple[int, ...]
    time_release_relative_s: tuple[float, ...]
    theta_rad: tuple[float | None, ...]
    qc_valid: tuple[bool, ...]
    fps_nominal: float

    def __post_init__(self) -> None:
        arrays = (self.frame_indices, self.time_release_relative_s, self.theta_rad, self.qc_valid)
        if not all(isinstance(a, tuple) for a in arrays) or not self.frame_indices:
            raise ValueError("angular arrays must be nonempty immutable tuples")
        if len({len(a) for a in arrays}) != 1:
            raise ValueError("angular arrays must have equal lengths")
        if not is_sha256_hex(self.upstream_digest):
            raise ValueError("angular upstream_digest must be a SHA256 digest")
        if any(type(f) is not int or f < 0 for f in self.frame_indices):
            raise ValueError("angular source frame IDs must be non-negative integers")
        if any(b <= a for a, b in zip(self.frame_indices, self.frame_indices[1:])):
            raise ValueError("angular source frame IDs must be unique and ordered")
        if any(type(t) not in (int, float) or not isfinite(t) for t in self.time_release_relative_s):
            raise ValueError("angular source times must be finite numbers")
        if any(b <= a for a, b in zip(self.time_release_relative_s, self.time_release_relative_s[1:])):
            raise ValueError("angular source times must be strictly increasing")
        if not isfinite(self.time_release_relative_s[-1] - self.time_release_relative_s[0]):
            raise ValueError("angular time span must be finite")
        if any(type(flag) is not bool for flag in self.qc_valid):
            raise ValueError("angular QC mask must contain actual booleans")
        if any(v is not None and (type(v) not in (int, float) or not isfinite(v)) for v in self.theta_rad):
            raise ValueError("angular theta must be finite or null")
        if any(v is not None and abs(v) > pi for v in self.theta_rad):
            raise ValueError("angular theta must be signed radians within [-pi, pi]")
        if any(ok and v is None for ok, v in zip(self.qc_valid, self.theta_rad)):
            raise ValueError("QC-valid theta cannot be missing")
        if type(self.fps_nominal) not in (int, float) or not isfinite(self.fps_nominal) or self.fps_nominal <= 0:
            raise ValueError("angular fps_nominal must be positive and finite")
        object.__setattr__(self, "time_release_relative_s", tuple(float(t) for t in self.time_release_relative_s))
        object.__setattr__(self, "theta_rad", tuple(None if v is None else float(v) for v in self.theta_rad))
        object.__setattr__(self, "fps_nominal", float(self.fps_nominal))


def angular_series_digest(series: AngularSeries) -> str:
    """签名覆盖实际数组，不能仅信任外层给出的 upstream digest。"""
    return canonical_json_digest({"upstream_digest": series.upstream_digest,
        "frames": list(series.frame_indices), "times_s": list(series.time_release_relative_s),
        "theta_rad": list(series.theta_rad), "qc_valid": list(series.qc_valid),
        "fps_nominal": series.fps_nominal})


@dataclass(frozen=True)
class Crossing:
    """由相邻源帧插值得到的过零时间；保留方向与源段，非新观测。"""
    time_s: float
    direction: str
    left_frame_index: int
    right_frame_index: int
    segment_start_frame_index: int
    segment_end_frame_index: int


@dataclass(frozen=True)
class Period:
    start: Crossing
    end: Crossing
    period_s: float
    omega2_s_inv2: float


@dataclass(frozen=True)
class PeriodAnalysis:
    """周期及可用性；periods 可保留不足十周期时的诊断候选。"""
    crossings: tuple[Crossing, ...]
    periods: tuple[Period, ...]
    center_rad: float | None
    omega2_mean_s_inv2: float | None
    status: str
    reason: str | None
    start_s: float
    end_s: float
    amplitude_max_rad: float | None
    source_time_digest: str


@dataclass(frozen=True)
class AngularAnalysis:
    input_digest: str
    profile_id: str
    omega_rad_s: tuple[float | None, ...]
    omega_reasons: tuple[str | None, ...]
    edge_window: tuple[bool, ...]
    information_extrema: tuple[tuple[int, str], ...]
    periods: PeriodAnalysis
    tail: PeriodAnalysis
    source_series_digest: str


def valid_segments(series: AngularSeries, mask: tuple[bool, ...], *, branch_guard: bool = True) -> tuple[tuple[int, int], ...]:
    """连续 QC-valid 源帧半开区间；不重排，不压缩时间，不跨 ±π。"""
    if len(mask) != len(series.frame_indices) or any(type(v) is not bool for v in mask):
        raise ValueError("segment mask must be an aligned boolean tuple")
    segments = []
    start = None
    for i, ok in enumerate(mask):
        ok = ok and series.qc_valid[i]
        adjacent = i > 0 and series.frame_indices[i] == series.frame_indices[i-1] + 1
        branch = (i > 0 and series.theta_rad[i] is not None and series.theta_rad[i-1] is not None
                  and abs(series.theta_rad[i] - series.theta_rad[i-1]) > pi)
        if start is not None and (not ok or not adjacent or (branch_guard and branch)):
            segments.append((start, i))
            start = None
        if ok and series.theta_rad[i] is not None and start is None:
            start = i
    if start is not None:
        segments.append((start, len(mask)))
    return tuple(segments)


def _derivative(series: AngularSeries, mask: tuple[bool, ...], profile_id: str,
                sg_window: int, sg_polyorder: int):
    n = len(mask)
    omega = [None] * n
    reasons = ["outside_interval" if t < 0 else "qc_excluded" for t in series.time_release_relative_s]
    edges = [False] * n
    if profile_id == LEGACY:
        # 明确保留历史整数组语义；不能拿此 fallback 给学生缺口数据补导数。
        if any(v is None for v in series.theta_rad) or n < 2:
            return tuple(omega), tuple("legacy_derivative_unavailable" for _ in mask), tuple(edges)
        window = min(SG_WINDOW, n if n % 2 else n-1)
        values = np.asarray(series.theta_rad, dtype=float)
        result = (np.gradient(values, 1/series.fps_nominal) if window < 5 else
                  savgol_filter(values, window, min(SG_POLYORDER, window-2), deriv=1,
                                delta=1/series.fps_nominal, mode="interp"))
        return tuple(float(v) for v in result), (None,) * n, tuple(i < window//2 or i >= n-window//2 for i in range(n))
    for start, end in valid_segments(series, mask):
        dt = np.diff(series.time_release_relative_s[start:end])
        reason = "short_segment" if end-start < sg_window else None
        delta = float(np.median(dt)) if len(dt) else None
        if reason is None and np.any(np.abs(dt-delta) > UNIFORM_DT_REL_TOL * delta):
            reason = "nonuniform_segment"
        if reason is not None:
            reasons[start:end] = [reason] * (end-start)
            continue
        values = savgol_filter(series.theta_rad[start:end], sg_window, sg_polyorder,
                               deriv=1, delta=delta, mode="interp")
        for i, value in enumerate(values, start):
            omega[i] = float(value) if isfinite(value) else None
            reasons[i] = None if isfinite(value) else "nonfinite_derivative"
            edges[i] = i < start+sg_window//2 or i >= end-sg_window//2
    return tuple(omega), tuple(reasons), tuple(edges)


def period_analysis(series: AngularSeries, mask: tuple[bool, ...], *, start_s: float,
                    end_s: float, profile_id: str = STUDENT, minimum_periods: int = 1) -> PeriodAnalysis:
    """以选定窗口 mean 居中；学生周期只配同段的交替三过零点。"""
    analysis_config(profile_id)
    if (type(start_s) not in (int, float) or type(end_s) not in (int, float)
            or not isfinite(start_s) or not isfinite(end_s) or start_s > end_s
            or type(minimum_periods) is not int or minimum_periods < 1):
        raise ValueError("invalid period window or minimum_periods")
    valid_segments(series, mask)
    mask = tuple(ok and qc and start_s <= t <= end_s
                 for ok, qc, t in zip(mask, series.qc_valid, series.time_release_relative_s))
    valid_values = [v for v, ok in zip(series.theta_rad, mask) if ok and v is not None]
    center = mean(valid_values) if valid_values else None
    amplitude = max(abs(v-center) for v in valid_values) if valid_values else None
    if profile_id == STUDENT and center is not None:
        # 连续零平台没有唯一过零时刻：保守切段，尾窗 mean 偏移也不能
        # 把真实 vertical 的零平台重新变成线性 crossing。
        zero = tuple(ok and (value == 0 or value == center)
                     for value, ok in zip(series.theta_rad, mask))
        plateau = tuple(z and ((i > 0 and zero[i-1]) or
                               (i+1 < len(zero) and zero[i+1]))
                        for i, z in enumerate(zero))
        mask = tuple(ok and not flat for ok, flat in zip(mask, plateau))
    segments = valid_segments(series, mask, branch_guard=profile_id == STUDENT)
    crossings = []
    for start, end in segments:
        for i in range(start, end-1):
            a, b = series.theta_rad[i]-center, series.theta_rad[i+1]-center
            if not ((a <= 0 < b) or (a >= 0 > b)):
                continue
            if profile_id == STUDENT and a == 0:
                # 孤立零点需两侧异号；触零后原路返回和段首零点不计。
                if i == start or (series.theta_rad[i-1]-center) * b >= 0:
                    continue
            fraction = -a / (b-a)
            time_s = series.time_release_relative_s[i] + fraction * (series.time_release_relative_s[i+1]-series.time_release_relative_s[i])
            crossings.append(Crossing(time_s, "upward" if b > a else "downward",
                series.frame_indices[i], series.frame_indices[i+1],
                series.frame_indices[start], series.frame_indices[end-1]))
    periods = []
    frequency_failed = False
    for a, middle, b in zip(crossings, crossings[1:], crossings[2:]):
        if profile_id == STUDENT and (
            a.direction != b.direction or a.direction == middle.direction
            or (a.segment_start_frame_index, a.segment_end_frame_index) != (b.segment_start_frame_index, b.segment_end_frame_index)
        ):
            continue
        period_s = b.time_s-a.time_s
        if period_s > 0:
            frequency = 2*pi/period_s
            omega2 = frequency * frequency
            if not isfinite(omega2):
                frequency_failed = True
                continue
            periods.append(Period(a, b, period_s, omega2))
    available = not frequency_failed and len(periods) >= minimum_periods
    return PeriodAnalysis(tuple(crossings), tuple(periods), center,
        mean(p.omega2_s_inv2 for p in periods) if available else None,
        "failed" if frequency_failed else ("success" if available else "insufficient_data"),
        "nonfinite_period_frequency" if frequency_failed else (None if available else "not_enough_complete_periods"),
        float(start_s), float(end_s), amplitude,
        canonical_json_digest({"frames": list(series.frame_indices),
                               "times_s": list(series.time_release_relative_s)}))


def analyze_angular_series(series: AngularSeries, *, profile_id: str = STUDENT,
                           end_frame_index: int | None = None, tail_start_s: float | None = None,
                           sg_window: int = SG_WINDOW, sg_polyorder: int = SG_POLYORDER) -> AngularAnalysis:
    """一套源帧网格输出 derivative / information / period / tail；无二次平滑。"""
    config = analysis_config(profile_id, sg_window=sg_window, sg_polyorder=sg_polyorder)
    end_frame = series.frame_indices[-1] if end_frame_index is None else end_frame_index
    if type(end_frame) is not int or end_frame not in series.frame_indices:
        raise ValueError("analysis end frame must exist in the source series")
    if profile_id == LEGACY and (end_frame != series.frame_indices[-1]
                                or any(t < 0 for t in series.time_release_relative_s)):
        raise ValueError("legacy reproduction requires the complete post-release series")
    interval = tuple(t >= 0 and f <= end_frame for f, t in zip(series.frame_indices, series.time_release_relative_s))
    selected = [t for t, ok in zip(series.time_release_relative_s, interval) if ok]
    if not selected:
        raise ValueError("analysis interval has no post-release source frames")
    start_s, end_s = selected[0], selected[-1]
    tail_start = (start_s + (end_s-start_s)*2/3 if profile_id == STUDENT else 70.0) if tail_start_s is None else tail_start_s
    if type(tail_start) not in (int, float) or not isfinite(tail_start):
        raise ValueError("tail start must be finite")
    mask = tuple(i and q for i, q in zip(interval, series.qc_valid))
    omega, reasons, edges = _derivative(series, mask, profile_id, sg_window, sg_polyorder)
    reasons = tuple(reason if included else "outside_interval" for reason, included in zip(reasons, interval))
    information = []
    order = max(8, int(series.fps_nominal/10))
    for start, end in valid_segments(series, mask, branch_guard=profile_id == STUDENT):
        values = np.asarray(series.theta_rad[start:end])
        for kind, comparison in (("maximum", np.greater), ("minimum", np.less)):
            information.extend((series.frame_indices[start+i], kind) for i in argrelextrema(values, comparison, order=order, mode="clip")[0])
    tail_mask = tuple(ok and t > tail_start for ok, t in zip(mask, series.time_release_relative_s))
    periods = period_analysis(series, mask, start_s=start_s, end_s=end_s, profile_id=profile_id)
    # 短视频仍记录所选窗口；legacy 70s 可超出末帧，并明确 unavailable。
    tail = period_analysis(series, tail_mask, start_s=float(tail_start), end_s=max(end_s, float(tail_start)),
                           profile_id=profile_id, minimum_periods=TAIL_MIN_PERIODS)
    identity = canonical_json_digest({"series_digest": angular_series_digest(series), "end_frame_index": end_frame,
        "tail_start_s": float(tail_start), "config": config})
    return AngularAnalysis(identity, profile_id, omega, reasons, edges, tuple(sorted(information)), periods, tail, angular_series_digest(series))
