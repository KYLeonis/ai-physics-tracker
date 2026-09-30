"""P2.2：解析信号、源缺口和冻结 E1；expected 不从 core 重新生成。"""

import csv
from dataclasses import replace
import gzip
from hashlib import sha256
import json
from math import cos, pi, radians, sin
from pathlib import Path

import numpy as np
import pytest

from ai_physics_tracker.domain.angular_analysis import (
    AngularSeries, LEGACY, STUDENT, analyze_angular_series, analysis_config, valid_segments,
)
from ai_physics_tracker.domain.pendulum_diagnostics import (
    ENERGY_PROFILE, PHASE_PROFILE, match_phase_crossings, prepare_diagnostic_extrema,
)

ROOT = Path(__file__).resolve().parents[1] / 'publication' / 'evidence' / 'golden'


def _series(theta, dt=.01, start=0):
    return AngularSeries('a'*64, tuple(range(len(theta))),
        tuple(start+i*dt for i in range(len(theta))), tuple(theta), (True,)*len(theta), 1/dt)


def _frozen(video_id):
    with gzip.open(ROOT / f'{video_id}-effective.csv.gz', 'rt', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    inputs = json.loads((ROOT / 'inputs24.json').read_text(encoding='utf-8'))
    item = next(x for x in inputs if x['video_id'] == video_id)
    return AngularSeries('b'*64, tuple(int(r['frame_index_0based']) for r in rows),
        tuple(float(r['time_s']) for r in rows), tuple(radians(float(r['theta_observed_deg'])) for r in rows),
        tuple(r['geometry_valid'] == 'True' for r in rows), item['fps']), rows


def test_direct_cubic_sg_derivative_and_edge_flags():
    series = _series(tuple((i*.01)**3 for i in range(101)))
    result = analyze_angular_series(series)
    np.testing.assert_allclose(result.omega_rad_s, 3*np.square(series.time_release_relative_s), atol=1e-11, rtol=1e-11)
    assert result.edge_window == (True,)*4 + (False,)*93 + (True,)*4
    assert not any(result.omega_reasons)


@pytest.mark.parametrize('count', [1, 8, 9])
def test_short_series_has_explicit_unavailable(count):
    result = analyze_angular_series(_series((.1,)*count))
    if count < 9:
        assert result.omega_rad_s == (None,)*count
        assert result.omega_reasons == ('short_segment',)*count
    else:
        np.testing.assert_allclose(result.omega_rad_s, 0, atol=1e-12, rtol=0)
    assert result.tail.status == 'insufficient_data'


def test_qc_gap_and_source_id_gap_never_bridge_derivatives_or_periods():
    series = _series(tuple(sin(2*pi*i*.01) for i in range(1001)))
    qc = list(series.qc_valid); qc[500] = False
    split = replace(series, qc_valid=tuple(qc))
    result = analyze_angular_series(split)
    assert result.omega_rad_s[500] is None and result.omega_reasons[500] == 'qc_excluded'
    assert all(p.start.segment_start_frame_index == p.end.segment_start_frame_index for p in result.periods.periods)
    assert all(not (p.start.time_s < 5 < p.end.time_s) for p in result.periods.periods)
    sparse = replace(series, frame_indices=tuple(i if i < 500 else i+1 for i in range(1001)))
    assert valid_segments(sparse, sparse.qc_valid) == ((0, 500), (500, 1001))
    result = analyze_angular_series(sparse)
    assert result.edge_window[499] and result.edge_window[500]


def test_nonuniform_time_branch_jump_and_interval_do_not_get_fallback():
    series = _series((.1,)*20)
    times = list(series.time_release_relative_s); times[10] += .001
    result = analyze_angular_series(replace(series, time_release_relative_s=tuple(times)))
    assert result.omega_rad_s == (None,)*20
    assert set(result.omega_reasons) == {'nonuniform_segment'}
    branch = replace(series, theta_rad=(3.,)*10+(-3.,)*10)
    result = analyze_angular_series(branch)
    np.testing.assert_allclose(result.omega_rad_s, 0, atol=1e-11, rtol=0)
    assert result.edge_window[9] and result.edge_window[10]
    result = analyze_angular_series(series, end_frame_index=8)
    assert result.omega_reasons[9:] == ('outside_interval',)*11
    assert result.omega_rad_s[9:] == (None,)*11


def test_negative_pre_release_time_is_preserved_but_outside_interval():
    series = _series((.1,)*20, start=-.05)
    result = analyze_angular_series(series)
    assert result.omega_rad_s[:5] == (None,)*5
    assert result.omega_reasons[:5] == ('outside_interval',)*5
    assert result.periods.start_s == pytest.approx(0, abs=1e-12)


def test_sine_period_and_tail_window_count_gate():
    series = _series(tuple(sin(2*pi*i*.01) for i in range(3001)))
    result = analyze_angular_series(series)
    np.testing.assert_allclose([p.period_s for p in result.periods.periods], 1, atol=1e-10, rtol=0)
    assert result.tail.start_s == pytest.approx(20, abs=1e-12)
    assert all(c.left_frame_index > 2000 for c in result.tail.crossings)
    assert result.tail.status == 'success'
    assert result.tail.omega2_mean_s_inv2 == pytest.approx((2*pi)**2, abs=1e-9, rel=1e-9)
    short = analyze_angular_series(series, tail_start_s=29)
    assert short.tail.status == 'insufficient_data' and short.tail.omega2_mean_s_inv2 is None
    assert short.tail.start_s == pytest.approx(29, abs=1e-12)
    assert analyze_angular_series(_series((0.,)*100)).periods.periods == ()


def test_phase_matching_requires_same_source_grid_segments_and_directions():
    series = _series(tuple(sin(2*pi*i*.01) for i in range(1001)))
    observed = analyze_angular_series(series).periods
    match = match_phase_crossings(observed, observed)
    assert match.status == 'matched' and match.final_drift_s == pytest.approx(0, abs=1e-12)
    changed = replace(observed, crossings=observed.crossings[:-1])
    assert match_phase_crossings(observed, changed).final_drift_s is None
    changed = replace(observed, crossings=(replace(observed.crossings[0], direction='wrong'), *observed.crossings[1:]))
    assert match_phase_crossings(observed, changed).status == 'unmatched'
    times = list(series.time_release_relative_s); times[500] += .001
    changed = analyze_angular_series(replace(series, time_release_relative_s=tuple(times))).periods
    assert match_phase_crossings(observed, changed).reason == 'different_source_time_grid'


@pytest.mark.parametrize('diagnostic,skip', [(PHASE_PROFILE,2), (ENERGY_PROFILE,5)])
def test_independent_diagnostic_peak_preparation_has_skip_and_gap_gate(diagnostic, skip):
    series = _series(tuple(.5*cos(2*pi*i*.01) for i in range(3001)))
    result = prepare_diagnostic_extrema(series, diagnostic, (2*pi)**2)
    assert result.status == 'success'
    assert result.retained_frames == result.candidate_frames[skip:]
    assert result.candidate_frames[0] == 0
    qc = list(series.qc_valid); qc[100] = False
    result = prepare_diagnostic_extrema(replace(series, qc_valid=tuple(qc)), diagnostic, (2*pi)**2)
    assert result.reason == 'interrupted_interval' and result.retained_frames == ()
    result = prepare_diagnostic_extrema(_series((.1,)*20), diagnostic, (2*pi)**2)
    assert result.reason == 'not_enough_extrema_after_skip'
    with pytest.raises(ValueError):
        prepare_diagnostic_extrema(series, diagnostic, None)


@pytest.mark.parametrize('video_id', ['P011','P014'])
@pytest.mark.parametrize('profile_id', [LEGACY,STUDENT])
def test_frozen_sg9_derivative_matches_archived_values(video_id, profile_id):
    series, rows = _frozen(video_id)
    result = analyze_angular_series(series, profile_id=profile_id)
    np.testing.assert_allclose(result.omega_rad_s, [float(r['omega_savgol9_rad_s']) for r in rows], atol=1e-8, rtol=1e-8)


def test_frozen_information_extrema_full_identity_and_tail_periods():
    series, _ = _frozen('P011')
    result = analyze_angular_series(series, profile_id=LEGACY)
    with (ROOT / 'P011-information-extrema.csv').open(encoding='utf-8',newline='') as f:
        extrema = list(csv.DictReader(f))
    assert len(extrema) == 213
    assert result.information_extrema == tuple((int(r['frame_index_0based']), r['extremum_type']) for r in extrema)
    with gzip.open(ROOT / 'm1_tail_frequency_periods.json.gz','rt',encoding='utf-8') as f:
        archived = sorted((r for r in json.load(f) if r['video_id']=='P011' and r['tail_start_s']==70), key=lambda r:r['period_index_0based'])
    assert len(result.tail.periods) == len(archived)
    for actual, expected in zip(result.tail.periods, archived):
        assert actual.start.direction == expected['crossing_direction']
        assert actual.start.time_s == pytest.approx(expected['start_crossing_time_s'], abs=1e-8,rel=1e-8)
        assert actual.end.time_s == pytest.approx(expected['end_crossing_time_s'], abs=1e-8,rel=1e-8)
        assert actual.period_s == pytest.approx(expected['period_s'], abs=1e-8,rel=1e-8)
        assert actual.omega2_s_inv2 == pytest.approx(expected['omega2_tail_period_s_inv2'], abs=1e-7,rel=1e-7)


def test_policy_identity_invalid_input_and_float64_semantics():
    series = _series((0.,)*20, dt=1)
    ints = replace(series, time_release_relative_s=tuple(range(20)), theta_rad=(0,)*20, fps_nominal=1)
    assert analyze_angular_series(series) == analyze_angular_series(ints)
    assert analyze_angular_series(series).input_digest != analyze_angular_series(series, tail_start_s=5).input_digest
    for changes in [
        {'qc_valid': ('False',)*20}, {'theta_rad': (None,)*20},
        {'frame_indices': tuple(range(19))}, {'fps_nominal':0},
        {'time_release_relative_s': (0.,)*20}, {'frame_indices':(0,)*20},
        {'theta_rad':(float('nan'),)*20}, {'frame_indices':tuple(float(i) for i in range(20))},
    ]:
        with pytest.raises(ValueError): replace(series, **changes)
    with pytest.raises(ValueError): analyze_angular_series(series, profile_id='unknown')
    with pytest.raises(ValueError): analyze_angular_series(series, tail_start_s=float('nan'))
    with pytest.raises(ValueError): analyze_angular_series(series, end_frame_index=True)
    profiles=ROOT.parents[1]/'profiles'
    config=analysis_config(STUDENT)
    assert config['profile_sha256']==sha256((profiles/'student-default-v2.json').read_bytes()).hexdigest()
    assert config['diagnostics_sha256']==sha256((profiles/'diagnostics-v1.json').read_bytes()).hexdigest()


def test_period_frequency_uses_mean_of_per_period_q_and_never_nonfinite_values():
    series, _ = _frozen('P011')
    result = analyze_angular_series(series, profile_id=LEGACY)
    qs = [p.omega2_s_inv2 for p in result.tail.periods]
    assert result.tail.omega2_mean_s_inv2 == pytest.approx(np.mean(qs), abs=1e-12, rel=1e-12)
    incorrect = (2*pi/np.mean([p.period_s for p in result.tail.periods]))**2
    assert abs(result.tail.omega2_mean_s_inv2-incorrect) > 1e-9
    # finite 时间输入可能仍无法表示平方频率，必须明确失败，不能输出 Infinity。
    from ai_physics_tracker.domain.angular_analysis import period_analysis
    tiny = _series(tuple(.1*sin(i*pi/4) for i in range(33)), dt=1e-200)
    result = period_analysis(tiny, tiny.qc_valid, start_s=0, end_s=tiny.time_release_relative_s[-1])
    assert result.status == 'failed' and result.reason == 'nonfinite_period_frequency'
    assert result.omega2_mean_s_inv2 is None


def test_public_period_mask_cannot_override_base_qc_and_legacy_fallback_is_explicit():
    from ai_physics_tracker.domain.angular_analysis import period_analysis
    series = _series((0., .1, -.1, .1, -.1))
    blocked = replace(series, qc_valid=(False,)*5)
    result = period_analysis(blocked, (True,)*5, start_s=0, end_s=.04)
    assert result.center_rad is None and result.crossings == ()
    short = _series((0., 1., 0., 1.), dt=1)
    legacy = analyze_angular_series(short, profile_id=LEGACY)
    np.testing.assert_allclose(legacy.omega_rad_s, [1., 0., 0., 1.], atol=1e-12, rtol=0)
    assert analyze_angular_series(short).omega_rad_s == (None,)*4
    with pytest.raises(ValueError, match='signed radians'):
        replace(short, theta_rad=(0.,45.,0.,1.))


def test_zero_plateau_and_touch_zero_do_not_manufacture_cycles():
    series = _series(tuple([-1., -1., 0., 0., 1., 1., 0., 0.] * 40), dt=.1)
    result = analyze_angular_series(series)
    assert result.periods.periods == ()
    assert result.tail.periods == ()
    assert result.tail.status == 'insufficient_data'
    assert result.tail.omega2_mean_s_inv2 is None
    # 单点触零后返回同侧不计；只有孤立零点两侧异号才是 crossing。
    series = _series((1., 0., 1., -1., 0., -1.), dt=.1)
    result = analyze_angular_series(series)
    assert len(result.periods.crossings) == 1
    assert result.periods.periods == ()
    assert analysis_config(STUDENT)['provenance']['derivative'] == ['policy-student-v1', 'metrics']
