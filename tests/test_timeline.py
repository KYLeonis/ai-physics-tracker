"""Timeline 契约测试（phase1-requirements AC-4）。"""

from uuid import uuid4

import pytest

from ai_physics_tracker.domain.timeline import (
    Timeline,
    clamp_to_working_zone,
    frame_to_time,
    has_time_mismatch,
    step_frame,
    time_to_frame,
)


def test_frame_time_conversion_is_zero_based_and_direct_at_29_97_fps() -> None:
    timeline = Timeline(uuid4(), 29.97, (0, 19_999))

    assert frame_to_time(0, timeline) == 0.0
    assert frame_to_time(10_000, timeline) == pytest.approx(
        10_000 / 29.97, abs=1e-6
    )


def test_time_to_frame_uses_half_up_rounding_and_video_clamp() -> None:
    timeline = Timeline(uuid4(), 30.0, (10, 90))

    assert time_to_frame(0.5 / 30.0, timeline, 100) == 1
    assert time_to_frame(-5.0, timeline, 100) == 0
    assert time_to_frame(99.0, timeline, 100) == 99


def test_working_zone_filters_steps_without_resetting_absolute_time() -> None:
    timeline = Timeline(uuid4(), 25.0, (100, 500))

    assert frame_to_time(100, timeline) == pytest.approx(4.0, abs=1e-12)
    assert clamp_to_working_zone(0, timeline) == 100
    assert step_frame(500, 1, timeline) == 500
    assert step_frame(100, -1, timeline) == 100


def test_time_mismatch_uses_half_frame_loading_tolerance() -> None:
    timeline = Timeline(uuid4(), 60.0, (0, 99))
    expected = frame_to_time(30, timeline)

    assert not has_time_mismatch(30, expected + 0.5 / 60.0, timeline)
    assert has_time_mismatch(30, expected + 0.6 / 60.0, timeline)


@pytest.mark.parametrize("fps_nominal", [0.0, -1.0, float("inf")])
def test_timeline_rejects_invalid_fps(fps_nominal: float) -> None:
    with pytest.raises(ValueError, match="fps_nominal"):
        Timeline(uuid4(), fps_nominal, (0, 10))
