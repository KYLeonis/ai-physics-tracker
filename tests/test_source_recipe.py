"""源配方跨同步生成、后台计算、旧读取入口的等价契约。"""

from copy import deepcopy
from dataclasses import replace
from threading import Event

import pytest

from tests.test_signal_analysis_job import signal_session
from ai_physics_tracker.application import chart_recipe, source_recipe
from ai_physics_tracker.application.angular_job import AngularSpec, prepare_angular_job, run_angular_job
from ai_physics_tracker.application.kinematics_job import prepare_kinematics_job, run_kinematics_job
from ai_physics_tracker.domain.angular import PendulumReference, TwoPointReference


@pytest.mark.parametrize("mode", ["linear", "pendulum", "two_point"])
def test_synchronous_and_background_records_keep_identical_values_and_recipes(signal_session, mode):
    session, video, track = signal_session
    parameters = source_recipe.SmoothingParameters(9, 3)
    if mode == "linear":
        job = prepare_kinematics_job(session, video, (track,), parameters)
        expected = session.compute_kinematics(track, window_length=9, polyorder=3)
        actual = run_kinematics_job(job, Event()).records
    else:
        session.add_calibration(video, scale_end_1_px=(0., 0.), scale_end_2_px=(10., 0.), known_length=1., unit="m")
        reference = PendulumReference((10., 0.))
        if mode == "two_point":
            other = session.add_track(video, "Reference")
            for frame in range(20, 71):
                session.mark_point(other.track_id, frame, pixel_x=40., pixel_y=10.)
            reference = TwoPointReference(other.track_id)
        job = prepare_angular_job(session, video, (AngularSpec(track, reference),), parameters)
        expected = session.compute_angular(track, reference=reference, window_length=9, polyorder=3)
        actual = run_angular_job(job, Event()).records
    for sync, background in zip(expected, actual, strict=True):
        assert background.pipeline == sync.pipeline
        assert background.frames == sync.frames
        assert background.values == sync.values
        assert background.input == sync.input
        assert background.unit == sync.unit
        assert background.calibration_ref == sync.calibration_ref
        assert background.extra_fields == sync.extra_fields
        timing = source_recipe.timing_identity(sync)
        assert timing.fps_nominal == 10. and timing.working_zone == (0, 99)
        recipe = source_recipe.smoothing_recipe(sync)
        if recipe:
            assert recipe["window_length"] == 9 and recipe["polyorder"] == 3
            orders = {"smoothed_position": 0, "velocity": 1, "acceleration": 2,
                      "smoothed_angular_position": 0, "angular_velocity": 1, "angular_acceleration": 2}
            assert recipe["deriv"] == orders[sync.kind]
            assert recipe["delta"] == (None if orders[sync.kind] == 0 else .1)
        else:
            assert sync.kind in ("world_position", "angular_position")
        if mode != "linear":
            assert source_recipe.recorded_reference(source_recipe.reference_recipe(sync)) == reference


def test_shared_readers_keep_legacy_imports_and_unknown_json_untouched(signal_session):
    session, _, track = signal_session
    record = session.derived_data(track, "velocity")
    record = replace(record, pipeline=record.pipeline + ({"step": "future", "params": {"nested": [1, {"x": 2}]}},),
                     extra_fields=record.extra_fields | {"future": {"version": 9}})
    before = deepcopy(record)
    for name in ("smoothing_recipe", "reference_recipe", "timing_identity", "calibration_recipe_reject_reason"):
        old_reader, reader = getattr(chart_recipe, name), getattr(source_recipe, name)
        assert old_reader is reader
        assert old_reader(record) == reader(record)
    assert record == before
