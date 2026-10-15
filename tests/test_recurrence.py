"""S2：通用参考线测量、缺测与不适用语义。"""

import numpy as np
import pytest

from ai_physics_tracker.domain.recurrence import RecurrenceSpec, measure_recurrence


@pytest.mark.parametrize("direction", ["rising", "falling"])
def test_biased_nonpendulum_periodic_signal_within_one_percent(direction):
    time_s = np.linspace(3, 15, 1201)
    signal = 7 + 2*np.sin(2*np.pi*time_s/1.3)
    result = measure_recurrence(np.arange(300, 1501), time_s, signal,
                                RecurrenceSpec(7, direction, .1, .2))
    assert len(result.intervals_s) >= 5
    assert abs(result.mean_interval_s/1.3 - 1) <= .01
    assert result.sample_std_s < 1e-4
    assert all(event.lower_frame_index >= 300 for event in result.events)


@pytest.mark.parametrize("signal", [np.ones(100), np.arange(100.), np.exp(-np.arange(100.)/10)])
def test_constant_and_nonperiodic_signals_have_no_period(signal):
    result = measure_recurrence(np.arange(100), np.arange(100.)*.1, signal, RecurrenceSpec(.5))
    assert result.measurement_status == "insufficient_events"
    assert result.mean_interval_s is None and result.sample_std_s is None


def test_single_interval_has_no_estimable_sample_std_and_exact_zero_is_an_event():
    result = measure_recurrence(np.arange(7), np.arange(7.), np.array([-1, 0, 1, -1, 0, 1, 2]), RecurrenceSpec())
    assert len(result.events) == 2
    assert result.events[0].time_s == pytest.approx(1, abs=1e-12)
    assert result.mean_interval_s == pytest.approx(3, abs=1e-12)
    assert result.sample_std_s is None


@pytest.mark.parametrize("gap", ["frame", "nan", "plateau", "wrapped"])
def test_no_pairing_across_missing_or_ambiguous_segments(gap):
    frames, time_s = np.arange(8), np.arange(8.)
    signal = np.array([-1., 1, 2, -1, 1, 2, 3, 4])
    spec = RecurrenceSpec()
    if gap == "frame":
        frames[3:] += 2
    elif gap == "nan":
        signal[2] = np.nan
    elif gap == "plateau":
        signal[2:4] = 0
        signal[4:] = [-1, 1, 2, 3]
    else:
        signal = np.array([-1., 1, 3, -3, -1, 1, 2, 3])
        spec = RecurrenceSpec(wrapped_angle=True)
    result = measure_recurrence(frames, time_s, signal, spec)
    assert len(result.events) == 2
    assert result.intervals_s == ()


def test_hysteresis_confirms_zero_crossing_instead_of_band_crossing():
    signal = np.array([-2., -.1, .1, -.1, .1, .2, 2, -2, -.1, .1, 2])
    result = measure_recurrence(np.arange(len(signal)), np.arange(len(signal), dtype=float),
                                signal, RecurrenceSpec(hysteresis=.5))
    assert len(result.events) == 2
    assert result.events[0].time_s == pytest.approx(3.5, abs=1e-12)
    assert result.events[0].upper_frame_index == 4


def test_reference_outside_signal_has_no_events():
    result = measure_recurrence(np.arange(20), np.arange(20.), np.sin(np.arange(20.)), RecurrenceSpec(4))
    assert result.events == ()


def test_multipeak_and_drifting_signal_reports_intervals_not_a_unique_period():
    time_s = np.linspace(0, 20, 2001)
    signal = np.sin(time_s**1.3) + .8*np.sin(3*time_s**1.3)
    result = measure_recurrence(np.arange(len(time_s)), time_s, signal, RecurrenceSpec())
    assert len(result.intervals_s) > 5 and result.sample_std_s > .1
    assert "fundamental period is not inferred" in result.message
