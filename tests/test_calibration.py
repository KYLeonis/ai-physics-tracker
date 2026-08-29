"""Calibration transform and invalidation tests for AC-6/AC-7."""

from dataclasses import replace
from datetime import UTC, datetime
import random
from pathlib import PurePosixPath
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.calibration import Calibration, CalibrationTransform
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import (
    Project,
    Registries,
    replace_calibration,
    set_active_calibration,
)
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.video import Video

_NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _calibration(*, unit: str = "mm", rotation_deg: float = 0.0) -> Calibration:
    return Calibration(
        calibration_id=uuid4(),
        video_id=uuid4(),
        name="ruler",
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=50.0,
        unit=unit,
        origin_px=(10.0, 20.0),
        rotation_deg=rotation_deg,
        created_at=_NOW,
    )


def test_scale_and_y_flip_match_corrected_spec() -> None:
    transform = CalibrationTransform(_calibration(), height_px=100)

    assert transform.pixels_per_unit == pytest.approx(2.0, abs=1e-12)
    assert transform.pixel_to_world((10.0, 30.0)) == pytest.approx(
        (0.0, -5.0), abs=1e-12
    )
    assert transform.pixel_to_world((10.0, 10.0)) == pytest.approx(
        (0.0, 5.0), abs=1e-12
    )


def test_positive_90_degree_rotation_maps_pixel_right_to_world_positive_y() -> None:
    transform = CalibrationTransform(
        _calibration(rotation_deg=90.0), height_px=100
    )

    assert transform.pixel_to_world((12.0, 20.0)) == pytest.approx(
        (0.0, 1.0), abs=1e-12
    )


def test_transform_round_trip_is_invariant_for_fixed_random_samples() -> None:
    generator = random.Random(20260829)
    for _ in range(50):
        calibration = Calibration(
            calibration_id=uuid4(),
            video_id=uuid4(),
            name="random",
            scale_end_1_px=(0.0, 0.0),
            scale_end_2_px=(generator.uniform(1.0, 500.0), generator.uniform(1.0, 500.0)),
            known_length=generator.uniform(0.1, 100.0),
            unit="cm",
            origin_px=(generator.uniform(-50, 50), generator.uniform(-50, 50)),
            rotation_deg=generator.uniform(-180, 180),
            created_at=_NOW,
        )
        transform = CalibrationTransform(calibration, height_px=1080)
        point = (generator.uniform(-100, 2000), generator.uniform(-100, 1200))

        assert transform.world_to_pixel(transform.pixel_to_world(point)) == pytest.approx(
            point, rel=1e-9, abs=1e-9
        )


@pytest.mark.parametrize(
    ("unit", "expected"),
    [("m", (2.0, -3.0)), ("cm", (0.02, -0.03)), ("mm", (0.002, -0.003))],
)
def test_world_unit_conversion_to_si(
    unit: str, expected: tuple[float, float]
) -> None:
    transform = CalibrationTransform(_calibration(unit=unit), height_px=100)

    assert transform.world_to_si((2.0, -3.0)) == pytest.approx(expected, abs=1e-12)


def test_calibration_rejects_degenerate_scale() -> None:
    calibration = _calibration()

    with pytest.raises(ValueError, match="must not coincide"):
        replace(calibration, scale_end_2_px=calibration.scale_end_1_px)
    with pytest.raises(ValueError, match="known_length"):
        replace(calibration, known_length=0.0)


def test_editing_active_calibration_stales_derived_without_touching_raw() -> None:
    video_id = uuid4()
    track_id = uuid4()
    calibration = replace(_calibration(), video_id=video_id)
    point = TrackPoint(
        uuid4(), track_id, 1, 1 / 30, 10.0, 20.0, "manual", "visible", "active", _NOW, _NOW
    )
    derived = DerivedData(
        uuid4(),
        track_id,
        "world_position",
        DerivedInput(track_id),
        (),
        (1,),
        ((0.0, 0.0),),
        None,
        "mm",
        "test",
        _NOW,
        "valid",
        calibration.calibration_id,
    )
    project = Project(
        uuid4(),
        "test",
        _NOW,
        _NOW,
        videos=(Video(video_id, PurePosixPath("videos/a.mp4"), "a", 10, 10, 30.0, 10),),
        timelines=(Timeline(video_id, 30.0, (0, 9)),),
        tracks=(Track(track_id, video_id, "bob", "#AABBCC", _NOW),),
        observations=(point,),
        calibrations=(calibration,),
        active_calibration_by_video={video_id: calibration.calibration_id},
        derived=(derived,),
        registries=Registries(),
    )

    edited = replace_calibration(project, replace(calibration, known_length=75.0))

    assert edited.observations == project.observations
    assert edited.derived[0].status == "stale"


def test_switching_active_calibration_keeps_data_from_new_choice_valid() -> None:
    video_id = uuid4()
    track_id = uuid4()
    old = replace(_calibration(), video_id=video_id)
    new = replace(_calibration(), calibration_id=uuid4(), video_id=video_id)
    derived_new = DerivedData(
        uuid4(), track_id, "world_position", DerivedInput(track_id), (), (), (), None,
        "mm", "test", _NOW, "valid", new.calibration_id
    )
    project = Project(
        uuid4(), "test", _NOW, _NOW,
        videos=(Video(video_id, PurePosixPath("videos/a.mp4"), "a", 10, 10, 30.0, 10),),
        timelines=(Timeline(video_id, 30.0, (0, 9)),),
        tracks=(Track(track_id, video_id, "bob", "#AABBCC", _NOW),),
        calibrations=(old, new),
        active_calibration_by_video={video_id: old.calibration_id},
        derived=(derived_new,),
    )

    switched = set_active_calibration(project, video_id, new.calibration_id)

    assert switched.derived[0].status == "valid"
