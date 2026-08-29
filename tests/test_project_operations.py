"""Cross-object project operations not owned by TrackStore."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import (
    Project,
    delete_track,
    update_timeline,
)
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.video import Video

_NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _project_with_observation() -> tuple[Project, TrackPoint]:
    video_id = uuid4()
    track_id = uuid4()
    point = TrackPoint(
        uuid4(), track_id, 30, 1.0, 10.0, 20.0, "manual", "visible", "active", _NOW, _NOW
    )
    derived = DerivedData(
        uuid4(),
        track_id,
        "velocity",
        DerivedInput(track_id),
        (),
        (30,),
        ((1.0, 2.0),),
        None,
        "m/s",
        "test",
        _NOW,
        "valid",
    )
    project = Project(
        uuid4(),
        "test",
        _NOW,
        _NOW,
        videos=(
            Video(
                video_id,
                PurePosixPath("videos/a.mp4"),
                "a",
                100,
                100,
                30.0,
                300,
            ),
        ),
        timelines=(Timeline(video_id, 30.0, (0, 299)),),
        tracks=(Track(track_id, video_id, "bob", "#AABBCC", _NOW),),
        observations=(point,),
        derived=(derived,),
    )
    return project, point


def test_fps_change_preserves_frozen_time_and_marks_mismatch_until_recalculated() -> None:
    project, point = _project_with_observation()
    video_id = project.videos[0].video_id
    changed = update_timeline(project, Timeline(video_id, 60.0, (0, 299)))

    assert changed.observations[0].time_s == point.time_s
    assert "time_mismatch" in changed.observations[0].quality_flags
    assert changed.derived[0].status == "stale"

    recalculated = update_timeline(
        project,
        Timeline(video_id, 60.0, (0, 299)),
        recalculate_times=True,
    )

    assert recalculated.observations[0].time_s == pytest.approx(0.5, abs=1e-12)
    assert "time_mismatch" not in recalculated.observations[0].quality_flags


def test_delete_track_cascades_observations_and_derived_data() -> None:
    project, _ = _project_with_observation()

    deleted = delete_track(project, project.tracks[0].track_id)

    assert deleted.tracks == ()
    assert deleted.observations == ()
    assert deleted.derived == ()
