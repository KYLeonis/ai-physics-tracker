"""领域层：诊断独立的 extrema 准备与同源过零匹配，不计算拟合耗散。"""

from dataclasses import dataclass
from math import isclose, isfinite, pi, radians, sqrt

import numpy as np
import scipy
from scipy.signal import argrelextrema, find_peaks

from ai_physics_tracker.domain.angular_analysis import (
    AngularSeries, Crossing, PeriodAnalysis, valid_segments, angular_series_digest, DIAGNOSTICS_SHA256,
)
from ai_physics_tracker.domain.timeline import TIME_COMPARISON_TOLERANCE_S
from ai_physics_tracker.domain.types import canonical_json_digest

PHASE_PROFILE = "phase-halfcycle-v1"
ENERGY_PROFILE = "energy-envelope-v1"
PHASE_SKIP = 2
ENERGY_SKIP = 5
AMPLITUDE_CUTOFF_RAD = radians(0.4)
RELATIVE_AMPLITUDE_CUTOFF = 0.015
FREQUENCY_FLOOR = 1e-12
PHASE_DISTANCE_FRACTION = 0.30
PROMINENCE_RAD = radians(0.08)
RELATIVE_PROMINENCE = 0.01
ENERGY_ORDER_FRACTION = 0.22
INITIAL_AMPLITUDE_FRAMES = 10
PHASE_TAIL_MIN_FRAMES = 30


def extrema_config(diagnostic_id: str) -> dict[str, object]:
    """诊断独立 profile 与实际 resolved 常数；无拟合 q 的隐式替代值。"""
    if diagnostic_id not in (PHASE_PROFILE, ENERGY_PROFILE):
        raise ValueError(f"unsupported extrema diagnostic: {diagnostic_id}")
    phase = diagnostic_id == PHASE_PROFILE
    return {"profile_id": diagnostic_id, "profile_sha256": DIAGNOSTICS_SHA256,
        "core_version": "diagnostic-extrema-1.0.0", "insert_initial": True,
        "numpy_version": np.__version__, "scipy_version": scipy.__version__,
        "skip_initial_extrema": PHASE_SKIP if phase else ENERGY_SKIP,
        "minimum_retained": 10 if phase else 8,
        "minimum_amplitude_rad": AMPLITUDE_CUTOFF_RAD, "relative_amplitude_cutoff": RELATIVE_AMPLITUDE_CUTOFF,
        "frequency_floor_s_inv2": FREQUENCY_FLOOR,
        "algorithm": "abs_find_peaks" if phase else "signed_argrelextrema",
        "distance_fraction_period": PHASE_DISTANCE_FRACTION if phase else None,
        "minimum_prominence_rad": PROMINENCE_RAD if phase else None,
        "relative_prominence": RELATIVE_PROMINENCE if phase else None,
        "order_fraction_halfperiod": None if phase else ENERGY_ORDER_FRACTION,
        "initial_amplitude_frames": INITIAL_AMPLITUDE_FRAMES if phase else None,
        "center_tail_minimum_frames": PHASE_TAIL_MIN_FRAMES if phase else None,
        "sources": ["phase" if phase else "energy", "policy-student-v1"]}


@dataclass(frozen=True)
class DiagnosticExtrema:
    """仅观测 extrema 准备；候选与 skip 后帧分开，不冒称包络拟合成功。"""
    profile_id: str
    candidate_frames: tuple[int, ...]
    retained_frames: tuple[int, ...]
    center_rad: float | None
    status: str
    reason: str | None
    skip_initial_extrema: int
    input_digest: str
    omega2_s_inv2: float


def prepare_diagnostic_extrema(series: AngularSeries, diagnostic_id: str,
                               omega2_s_inv2: float, *, end_frame_index: int | None = None) -> DiagnosticExtrema:
    """scientific-profiles §5：phase 用 abs/find_peaks，EDP 用带符号 argrelextrema。"""
    config = extrema_config(diagnostic_id)
    if type(omega2_s_inv2) not in (int, float) or not isfinite(omega2_s_inv2) or omega2_s_inv2 <= 0:
        raise ValueError("diagnostic requires explicitly supplied positive fitted omega2")
    end_frame = series.frame_indices[-1] if end_frame_index is None else end_frame_index
    if type(end_frame) is not int or end_frame not in series.frame_indices:
        raise ValueError("diagnostic end frame must exist in source series")
    indices = tuple(i for i, (f, t) in enumerate(zip(series.frame_indices, series.time_release_relative_s)) if t >= 0 and f <= end_frame)
    skip = PHASE_SKIP if diagnostic_id == PHASE_PROFILE else ENERGY_SKIP
    digest = canonical_json_digest({"series_digest": angular_series_digest(series),
        "config": config, "omega2_s_inv2": float(omega2_s_inv2), "end_frame_index": end_frame})
    def unavailable(reason, candidates=(), center=None):
        return DiagnosticExtrema(diagnostic_id, candidates, (), center, "insufficient_data", reason, skip, digest, float(omega2_s_inv2))
    if len(indices) < 2:
        return unavailable("short_interval")
    mask = tuple(i in range(indices[0], indices[-1]+1) and series.qc_valid[i] for i in range(len(series.frame_indices)))
    segments = valid_segments(series, mask)
    if segments != ((indices[0], indices[-1]+1),):
        return unavailable("interrupted_interval")
    values = np.asarray(series.theta_rad[indices[0]:indices[-1]+1], dtype=float)
    times = series.time_release_relative_s[indices[0]:indices[-1]+1]
    delta = float(np.median(np.diff(times)))
    frequency = sqrt(max(float(omega2_s_inv2), FREQUENCY_FLOOR))
    center = None
    if diagnostic_id == PHASE_PROFILE:
        center = float(np.median(values[-max(PHASE_TAIL_MIN_FRAMES, len(values)//10):]))
        amplitude = np.abs(values-center)
        initial_amplitude = float(np.max(np.abs(values[:INITIAL_AMPLITUDE_FRAMES])))
        distance = max(2, round(PHASE_DISTANCE_FRACTION * (2*pi/frequency) / delta))
        peaks, _ = find_peaks(amplitude, distance=distance,
                            prominence=max(PROMINENCE_RAD, RELATIVE_PROMINENCE * initial_amplitude))
        peaks = np.unique(np.concatenate(([0], peaks)))
        peaks = peaks[amplitude[peaks] >= max(AMPLITUDE_CUTOFF_RAD, RELATIVE_AMPLITUDE_CUTOFF * initial_amplitude)]
        minimum_retained = 10
    else:
        order = max(3, round(ENERGY_ORDER_FRACTION * pi/frequency / delta))
        peaks = np.sort(np.concatenate((argrelextrema(values, np.greater, order=order)[0],
                                        argrelextrema(values, np.less, order=order)[0])))
        peaks = np.unique(np.concatenate(([0], peaks)))
        amplitude = np.abs(values[peaks])
        peaks = peaks[amplitude >= max(AMPLITUDE_CUTOFF_RAD, RELATIVE_AMPLITUDE_CUTOFF * float(np.max(amplitude)))]
        minimum_retained = 8
    candidates = tuple(series.frame_indices[indices[0]+int(i)] for i in peaks)
    if len(candidates)-skip < minimum_retained:
        return unavailable("not_enough_extrema_after_skip", candidates, center)
    return DiagnosticExtrema(diagnostic_id, candidates, candidates[skip:], center, "success", None, skip, digest, float(omega2_s_inv2))


@dataclass(frozen=True)
class CrossingMatch:
    """源时间段/方向序列不同则 unmatched，不输出漂移总结。"""
    status: str
    reason: str | None
    matched: tuple[tuple[Crossing, Crossing], ...]
    final_drift_s: float | None


def match_phase_crossings(observed: PeriodAnalysis, predicted: PeriodAnalysis) -> CrossingMatch:
    """scientific-profiles §3：在对应 source-time 段按方向及序号匹配。"""
    if observed.source_time_digest != predicted.source_time_digest:
        return CrossingMatch("unmatched", "different_source_time_grid", (), None)
    if not (isclose(observed.start_s, predicted.start_s, rel_tol=0, abs_tol=TIME_COMPARISON_TOLERANCE_S)
            and isclose(observed.end_s, predicted.end_s, rel_tol=0, abs_tol=TIME_COMPARISON_TOLERANCE_S)):
        return CrossingMatch("unmatched", "different_analysis_windows", (), None)
    a, b = observed.crossings, predicted.crossings
    if not a or len(a) != len(b):
        return CrossingMatch("unmatched", "different_crossing_counts", (), None)
    for left, right in zip(a, b):
        if (left.direction, left.segment_start_frame_index, left.segment_end_frame_index) != (
            right.direction, right.segment_start_frame_index, right.segment_end_frame_index
        ):
            return CrossingMatch("unmatched", "different_source_segments_or_directions", (), None)
    return CrossingMatch("matched", None, tuple(zip(a, b)), b[-1].time_s-a[-1].time_s)
