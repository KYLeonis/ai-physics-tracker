"""Project aggregate registration and cross-reference validation tests."""

from dataclasses import replace
from pathlib import PurePosixPath
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.project import add_video, create_project
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.video import Video


def _video(*, path: str = "videos/a.mp4", vfr_suspected: bool = False) -> Video:
    return Video(
        video_id=uuid4(),
        file_path=PurePosixPath(path),
        display_name="a.mp4",
        width_px=1920,
        height_px=1080,
        fps_container=30.0,
        frame_count=300,
        vfr_suspected=vfr_suspected,
    )


def test_add_video_registers_exactly_one_matching_timeline() -> None:
    project = create_project("pendulum")
    video = _video()
    timeline = Timeline(video.video_id, 30.0, (0, 299))

    updated = add_video(project, video, timeline)

    assert updated.videos == (video,)
    assert updated.timelines == (timeline,)


def test_add_video_rejects_vfr_and_duplicate_paths() -> None:
    project = create_project("pendulum")
    vfr = _video(vfr_suspected=True)
    with pytest.raises(ValueError, match="VFR"):
        add_video(project, vfr, Timeline(vfr.video_id, 30.0, (0, 299)))

    first = _video()
    project = add_video(project, first, Timeline(first.video_id, 30.0, (0, 299)))
    duplicate = replace(first, video_id=uuid4())
    with pytest.raises(ValueError, match="path is already registered"):
        add_video(project, duplicate, Timeline(duplicate.video_id, 30.0, (0, 299)))


def test_add_video_rejects_working_zone_beyond_frame_count() -> None:
    video = _video()
    with pytest.raises(ValueError, match="frame_count"):
        add_video(
            create_project("pendulum"),
            video,
            Timeline(video.video_id, 30.0, (0, 300)),
        )
