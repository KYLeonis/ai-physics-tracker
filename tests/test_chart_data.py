"""Qt-free 图表数据适配器测试。"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.chart_data import build_chart_data
from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import Project, create_project
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.domain.video import Video

_NOW = datetime(2026, 8, 30, tzinfo=UTC)


def _video(video_id: UUID, *, frame_count: int = 100) -> Video:
    return Video(
        video_id=video_id,
        file_path=PurePosixPath(f"videos/{video_id}.mp4"),
        display_name="test.mp4",
        width_px=640,
        height_px=480,
        fps_container=29.97,
        frame_count=frame_count,
    )


def _track(track_id: UUID, video_id: UUID, name: str = "Bob") -> Track:
    return Track(track_id, video_id, name, "#AABBCC", _NOW)


def _derived(
    track_id: UUID,
    kind: str,
    frames: tuple[int, ...],
    values: tuple[tuple[float, ...], ...] | None,
    *,
    unit: str = "m",
    status: str = "valid",
    payload_ref: str | None = None,
    pipeline: tuple[dict[str, object], ...] = (),
) -> DerivedData:
    return DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind=kind,
        input=DerivedInput(track_id),
        pipeline=pipeline,
        frames=frames,
        values=values,
        payload_ref=payload_ref,
        unit=unit,
        produced_by="test",
        created_at=_NOW,
        status=status,
    )


def _project(
    *,
    video_id: UUID | None = None,
    track_id: UUID | None = None,
    fps: float = 29.97,
    working_zone: tuple[int, int] = (0, 99),
    derived: tuple[DerivedData, ...] = (),
    calibrated: bool = True,
    calibration_unit: str = "m",
) -> tuple[Project, UUID, UUID]:
    video_id = video_id or uuid4()
    track_id = track_id or uuid4()
    video = _video(video_id)
    timeline = Timeline(video_id, fps, working_zone)
    track = _track(track_id, video_id)
    project = Project(
        project_id=uuid4(),
        name="chart test",
        created_at=_NOW,
        modified_at=_NOW,
        videos=(video,),
        timelines=(timeline,),
        tracks=(track,),
        derived=derived,
    )
    if calibrated:
        calibration = Calibration(
            calibration_id=uuid4(),
            video_id=video_id,
            name="scale",
            scale_end_1_px=(0.0, 0.0),
            scale_end_2_px=(100.0, 0.0),
            known_length=1.0,
            unit=calibration_unit,
            created_at=_NOW,
        )
        project = replace(
            project,
            calibrations=(calibration,),
            active_calibration_by_video={video_id: calibration.calibration_id},
        )
    return project, video_id, track_id


def test_all_chart_kinds_map_columns_and_units() -> None:
    track_id = uuid4()
    project, video_id, _ = _project(
        track_id=track_id,
        derived=(
            _derived(track_id, "world_position", (0, 1, 3), ((1, 2), (3, 4), (5, 6))),
            _derived(
                track_id,
                "smoothed_position",
                (0, 1, 3),
                ((11, 12), (13, 14), (15, 16)),
                pipeline=(
                    {
                        "step": "savitzky_golay",
                        "params": {"window_length": 9, "polyorder": 3, "deriv": 0},
                    },
                ),
            ),
            _derived(
                track_id,
                "velocity",
                (0, 1, 3),
                ((21, 22), (23, 24), (25, 26)),
                unit="m/s",
                pipeline=(
                    {
                        "step": "savitzky_golay",
                        "params": {"window_length": 9, "polyorder": 3, "deriv": 1},
                    },
                ),
            ),
            _derived(
                track_id,
                "acceleration",
                (0, 1, 3),
                ((31, 32), (33, 34), (35, 36)),
                unit="m/s²",
                pipeline=(
                    {
                        "step": "savitzky_golay",
                        "params": {"window_length": 9, "polyorder": 3, "deriv": 2},
                    },
                ),
            ),
        )
    )

    x_chart = build_chart_data(project, video_id, (track_id,), "x_t")
    assert x_chart.title == "x(t)"
    assert x_chart.x_unit == "s"
    assert x_chart.y_unit == "m"
    assert x_chart.series[0].component == "x"
    assert x_chart.series[0].y_values == (1.0, 3.0, 5.0)

    y_chart = build_chart_data(project, video_id, (track_id,), "y_t", smoothed=True)
    assert y_chart.series[0].component == "y"
    assert y_chart.series[0].y_values == (12.0, 14.0, 16.0)
    assert "window=9" in y_chart.series[0].pipeline_summary
    assert "polyorder=3" in y_chart.series[0].pipeline_summary

    velocity = build_chart_data(project, video_id, (track_id,), "v_t")
    assert [item.component for item in velocity.series] == ["vx", "vy"]
    assert [item.y_values for item in velocity.series] == [
        (21.0, 23.0, 25.0),
        (22.0, 24.0, 26.0),
    ]
    assert velocity.y_unit == "m/s"

    acceleration = build_chart_data(project, video_id, (track_id,), "a_t")
    assert [item.component for item in acceleration.series] == ["ax", "ay"]
    assert acceleration.y_unit == "m/s²"

    xy_chart = build_chart_data(project, video_id, (track_id,), "xy")
    assert xy_chart.x_unit == "m"
    assert xy_chart.y_unit == "m"
    assert xy_chart.series[0].component == "xy"
    assert xy_chart.series[0].x_values == (1.0, 3.0, 5.0)
    assert xy_chart.series[0].y_values == (2.0, 4.0, 6.0)


def test_time_uses_source_frames_and_working_zone_without_reset() -> None:
    track_id = uuid4()
    project, video_id, _ = _project(
        track_id=track_id,
        fps=29.97,
        working_zone=(10, 13),
        derived=(
            _derived(
                track_id,
                "world_position",
                (9, 10, 12, 14),
                ((1, 1), (2, 2), (3, 3), (4, 4)),
            ),
        ),
    )

    chart = build_chart_data(project, video_id, (track_id,), "x_t")
    series = chart.series[0]
    assert series.frames == (10, 12)
    assert series.x_values == pytest.approx((10 / 29.97, 12 / 29.97))
    assert series.y_values == (2.0, 3.0)
    assert series.connect == (False, False)


def test_connect_flags_keep_single_and_isolated_points_for_scatter() -> None:
    track_id = uuid4()
    project, video_id, _ = _project(
        track_id=track_id,
        derived=(
            _derived(track_id, "world_position", (2, 4, 5), ((1, 2), (3, 4), (5, 6))),
        ),
    )
    chart = build_chart_data(project, video_id, (track_id,), "xy")
    assert chart.series[0].connect == (False, True, False)

    one_point = replace(
        project,
        derived=(_derived(track_id, "world_position", (4,), ((9, 10),)),),
    )
    chart = build_chart_data(one_point, video_id, (track_id,), "xy")
    assert chart.series[0].frames == (4,)
    assert chart.series[0].connect == (False,)


def test_stale_and_mixed_units_are_reported_without_unit_conversion() -> None:
    track_one = uuid4()
    track_two = uuid4()
    video_id = uuid4()
    project, video_id, _ = _project(
        video_id=video_id,
        track_id=track_one,
        derived=(_derived(track_one, "world_position", (1,), ((1, 2),), status="stale"),),
    )
    second = _track(track_two, video_id, "Other")
    project = replace(
        project,
        tracks=(*project.tracks, second),
        derived=(*project.derived, _derived(track_two, "world_position", (1,), ((3, 4),), unit="cm")),
    )

    chart = build_chart_data(project, video_id, (track_one, track_two), "x_t")
    assert len(chart.series) == 1
    assert chart.series[0].status == "stale"
    assert any("stale" in message for message in chart.messages)
    assert any("incompatible" in message for message in chart.messages)
    assert chart.y_unit == "m"


def test_uncalibrated_position_uses_pixels_and_marks_y_direction() -> None:
    track_id = uuid4()
    project, video_id, _ = _project(
        track_id=track_id,
        calibrated=False,
        derived=(_derived(track_id, "world_position", (2,), ((8, 9),), unit="px"),),
    )

    chart = build_chart_data(project, video_id, (track_id,), "xy")
    assert chart.pixel_coordinates is True
    assert chart.x_unit == "px"
    assert chart.y_unit == "px"
    assert any("not calibrated" in message for message in chart.messages)


def test_valid_cache_from_another_calibration_is_displayed_as_stale_without_mutation() -> None:
    track_id = uuid4()
    project, video_id, _ = _project(track_id=track_id,
        derived=(_derived(track_id, "world_position", (2,), ((8, 9),)),))
    active = project.calibrations[0]
    other = replace(active, calibration_id=uuid4(), name="other", origin_px=(30, 0))
    old_result = replace(project.derived[0], calibration_ref=other.calibration_id)
    project = replace(project, calibrations=(active, other), derived=(old_result,))
    chart = build_chart_data(project, video_id, (track_id,), "x_t")
    assert chart.series[0].status == "stale"
    assert any("different calibration" in message for message in chart.messages)
    assert project.derived[0].status == "valid"
    current = replace(project, derived=(replace(old_result, calibration_ref=active.calibration_id),))
    assert build_chart_data(current, video_id, (track_id,), "x_t").series[0].status == "valid"


@pytest.mark.parametrize(
    ("values", "frames", "expected_message"),
    [
        (None, (1,), "values are None"),
        (((1.0,),), (1,), "not two columns"),
        (((float("nan"), 1.0),), (1,), "non-finite"),
        (((1.0, 2.0), (3.0, 4.0)), (2, 1), "frame order"),
    ],
)
def test_malformed_derived_data_returns_message_without_crashing(
    values: tuple[tuple[float, ...], ...] | None,
    frames: tuple[int, ...],
    expected_message: str,
) -> None:
    track_id = uuid4()
    derived = _derived(track_id, "world_position", frames, values)
    project, video_id, _ = _project(track_id=track_id, derived=(derived,))

    chart = build_chart_data(project, video_id, (track_id,), "x_t")
    assert chart.series == ()
    assert any(expected_message in message for message in chart.messages)


def test_external_payload_is_not_loaded_or_guessed() -> None:
    track_id = uuid4()
    derived = _derived(
        track_id,
        "world_position",
        (1,),
        None,
        payload_ref="data/derived/points.npy",
    )
    project, video_id, _ = _project(track_id=track_id, derived=(derived,))

    chart = build_chart_data(project, video_id, (track_id,), "x_t")
    assert chart.series == ()
    assert any("payload_ref" in message for message in chart.messages)


def test_missing_short_and_cross_video_tracks_are_isolated() -> None:
    video_one = uuid4()
    video_two = uuid4()
    track_one = uuid4()
    track_two = uuid4()
    project, _, _ = _project(
        video_id=video_one,
        track_id=track_one,
        derived=(_derived(track_one, "velocity", (), (), unit="m/s"),),
    )
    other_video = _video(video_two)
    other_track = _track(track_two, video_two, "Other video")
    project = replace(
        project,
        videos=(*project.videos, other_video),
        timelines=(*project.timelines, Timeline(video_two, 29.97, (0, 99))),
        tracks=(*project.tracks, other_track),
        derived=(*project.derived, _derived(track_two, "velocity", (1,), ((1, 2),), unit="m/s")),
    )

    chart = build_chart_data(project, video_one, (track_one, track_two), "v_t")
    assert chart.series == ()
    assert any("too few continuous" in message for message in chart.messages)
    assert any("does not belong to the current video" in message for message in chart.messages)
