"""领域层：封存确定性fit起点；student seed不跨缺口，不改正式观测时间。"""

from dataclasses import dataclass
from math import pi, radians, sqrt

import numpy as np
from scipy.signal import find_peaks

from ai_physics_tracker.domain.angular_analysis import LEGACY, UNIFORM_DT_REL_TOL, valid_segments
from ai_physics_tracker.domain.pendulum_ode import M0, M1, ObjectiveRequest, fit_valid_indices

Q_MIN_SAMPLES = 20
Q_EARLY_SECONDS = 35.0
ALPHA1_MIN_SAMPLES = 30
START_MARGIN = 1e-10
Q_SEED_FACTORS = (.975, 1.0, 1.025)


@dataclass(frozen=True)
class SeedEstimate:
    """实际支持源帧与估计值；极值仅用于seed，不伪造历史优化日志。"""
    source_frames: tuple[int, ...]
    omega2_estimate_s_inv2: float
    omega2_guess_s_inv2: float
    alpha1_guess_s_inv: float
    frequency_extrema_count: int
    policy: str


def seed_source_indices(request: ObjectiveRequest) -> tuple[int, ...]:
    """student选择最长连续均匀base-QC段，长度相同取最早；legacy保留历史子序列。"""
    valid = fit_valid_indices(request)
    if request.profile_id == LEGACY:
        return valid
    allowed = set(valid)
    mask = tuple(i in allowed for i in range(len(request.series.frame_indices)))
    candidates = []
    for start, end in valid_segments(request.series, mask):
        dt = np.diff(request.series.time_release_relative_s[start:end])
        if len(dt) and np.all(np.abs(dt-np.median(dt)) <= UNIFORM_DT_REL_TOL*np.median(dt)):
            candidates.append((start, end))
    if not candidates:
        return ()
    start, end = max(candidates, key=lambda span: span[1]-span[0])
    return tuple(range(start, end))


def _estimate_omega2(theta, times, expected_omega2):
    # source-fitting::estimate_omega2；没有把这一探峰器复用为周期或诊断算法。
    if len(theta) < Q_MIN_SAMPLES:
        return expected_omega2, 0
    limit = int(np.searchsorted(times, min(float(times[-1]), Q_EARLY_SECONDS), side="right"))
    signal, local_times = theta[:limit], times[:limit]
    if len(signal) < Q_MIN_SAMPLES:
        return expected_omega2, 0
    equilibrium = float(np.median(signal[-max(10, len(signal)//5):]))
    centered = signal-equilibrium
    amplitude = max(abs(float(centered[0])), radians(2))
    period = 2*pi/sqrt(expected_omega2)
    distance = max(2, int(.55*period/float(np.median(np.diff(local_times)))))
    prominence = max(.08*amplitude, radians(.15))
    positive, _ = find_peaks(centered, distance=distance, prominence=prominence)
    negative, _ = find_peaks(-centered, distance=distance, prominence=prominence)
    periods = np.asarray([float(t) for peaks in (positive, negative)
                          for t in np.diff(local_times[peaks])], dtype=float)
    reasonable = periods[(periods > .45*period) & (periods < 1.8*period)]
    count = len(positive)+len(negative)
    return ((2*pi/float(np.median(reasonable)))**2, count) if len(reasonable) else (expected_omega2, count)


def _estimate_alpha1(theta, times, omega2, upper):
    # source-fitting::estimate_alpha1；log-envelope斜率仅给优化起点。
    fallback = min(.02, .25*upper)
    if len(theta) < ALPHA1_MIN_SAMPLES:
        return fallback
    period = 2*pi/sqrt(omega2)
    equilibrium = float(np.median(theta[-max(10, len(theta)//10):]))
    amplitude = np.abs(theta-equilibrium)
    peaks, _ = find_peaks(amplitude, distance=max(2, int(.35*period/float(np.median(np.diff(times))))),
                         prominence=max(radians(.1), abs(theta[0]-equilibrium)*.015))
    peaks = peaks[:30]
    if len(peaks) < 4:
        return fallback
    keep = amplitude[peaks] > radians(.1)
    if np.count_nonzero(keep) < 4:
        return fallback
    slope = float(np.polyfit(times[peaks][keep], np.log(amplitude[peaks][keep]), 1)[0])
    return float(np.clip(-2*slope, .002, .8*upper))


def estimate_fit_seed(request: ObjectiveRequest, omega2_bounds: tuple[float, float],
                      alpha1_upper: float) -> SeedEstimate:
    """已验证fit bounds的消费入口；原始时刻只在student seed内部平移一次。"""
    indices = seed_source_indices(request)
    theta = np.asarray([request.series.theta_rad[i] for i in indices], dtype=float)
    times = np.asarray([request.series.time_release_relative_s[i] for i in indices], dtype=float)
    if request.profile_id != LEGACY and len(times):
        times = times-times[0]
    estimate, count = _estimate_omega2(theta, times, request.g_m_s2/request.effective_length_m)
    low, high = omega2_bounds
    # 窄自定义bounds没有历史1%内区间时，直接按显式bounds投影；不反转np.clip上下界。
    guess_low, guess_high = low*1.01, high*.99
    if guess_low >= guess_high:
        guess_low, guess_high = low+START_MARGIN, high-START_MARGIN
    guess = float(np.clip(estimate, guess_low, guess_high))
    alpha1 = _estimate_alpha1(theta, times, guess, alpha1_upper)
    return SeedEstimate(tuple(request.series.frame_indices[i] for i in indices), float(estimate),
                        guess, alpha1, count, "legacy_valid_subsequence" if request.profile_id == LEGACY
                        else "student_longest_contiguous_uniform")


def deterministic_starts(model: str, seed: SeedEstimate, lower: tuple[float, ...],
                         upper: tuple[float, ...]) -> tuple[tuple[float, ...], ...]:
    """source-M0/M1 bounds_and_starts原公式，最后按实际bounds夹进可行内区间。"""
    qlow, qhigh = lower[-1], upper[-1]
    inner_low, inner_high = qlow*1.001, qhigh*.999
    if inner_low >= inner_high:
        inner_low, inner_high = qlow+START_MARGIN, qhigh-START_MARGIN
    q = np.clip(seed.omega2_guess_s_inv2*np.asarray(Q_SEED_FACTORS), inner_low, inner_high)
    a1 = seed.alpha1_guess_s_inv
    if model == M0:
        starts = ((a1, q[0]), (max(.005, a1), q[1]), (min(.08, .5*upper[0]), q[2]))
    elif model == M1:
        starts = ((a1, .005, q[0]), (max(.005, .6*a1), .03, q[1]),
                  (.005, min(.10, .5*upper[1]), q[2]))
    else:
        raise ValueError(f"unsupported model: {model}")
    return tuple(tuple(map(float, np.clip(start, np.asarray(lower)+START_MARGIN,
                                          np.asarray(upper)-START_MARGIN))) for start in starts)
