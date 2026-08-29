"""Project aggregate, creation helpers, and cross-object validation."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from math import isclose
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import (
    DerivedData,
    mark_calibrations_stale,
    mark_tracks_stale,
)
from ai_physics_tracker.domain.timeline import (
    Timeline,
    frame_to_time,
    has_time_mismatch,
)
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.types import JsonObject, require_aware_datetime, utc_now
from ai_physics_tracker.domain.video import Video


@dataclass(frozen=True)
class Registries:
    """Open string registries persisted with each project."""

    sources: tuple[str, ...] = ("manual", "template")
    units: tuple[str, ...] = ("m", "cm", "mm", "px")
    quality_flags: tuple[str, ...] = (
        "interpolated",
        "extrapolated",
        "outlier",
        "low_confidence",
        "user_locked",
        "repaired",
        "time_mismatch",
    )
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for field_name, values in (
            ("sources", self.sources),
            ("units", self.units),
            ("quality_flags", self.quality_flags),
        ):
            if len(set(values)) != len(values) or any(not value for value in values):
                raise ValueError(f"{field_name} entries must be unique and non-blank")
        if "manual" not in self.sources or "template" not in self.sources:
            raise ValueError("Phase 1 source registry must include manual and template")


@dataclass(frozen=True)
class Project:
    """Persistent aggregate root for one experiment analysis session."""

    project_id: UUID
    name: str
    created_at: datetime
    modified_at: datetime
    description: str | None = None
    videos: tuple[Video, ...] = ()
    timelines: tuple[Timeline, ...] = ()
    tracks: tuple[Track, ...] = ()
    observations: tuple[TrackPoint, ...] = ()
    calibrations: tuple[Calibration, ...] = ()
    active_calibration_by_video: dict[UUID, UUID] = field(default_factory=dict)
    derived: tuple[DerivedData, ...] = ()
    registries: Registries = field(default_factory=Registries)
    ui_state: JsonObject = field(default_factory=dict)
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name must not be blank")
        require_aware_datetime(self.created_at, "created_at")
        require_aware_datetime(self.modified_at, "modified_at")
        validate_project(self)


def create_project(name: str, description: str | None = None) -> Project:
    """Create an empty valid project with generated identity and UTC timestamps."""

    now = utc_now()
    return Project(
        project_id=uuid4(),
        name=name,
        description=description,
        created_at=now,
        modified_at=now,
    )


def add_video(project: Project, video: Video, timeline: Timeline) -> Project:
    """Register CFR video metadata and its Timeline as one atomic domain update."""

    if video.vfr_suspected:
        raise ValueError("VFR video is not supported; transcode it to CFR before analysis")
    if timeline.video_id != video.video_id:
        raise ValueError("timeline.video_id must match video.video_id")
    if any(item.video_id == video.video_id for item in project.videos):
        raise ValueError(f"video_id is already registered: {video.video_id}")
    if any(item.file_path == video.file_path for item in project.videos):
        raise ValueError(f"video path is already registered: {video.file_path}")
    if timeline.working_zone[1] >= video.frame_count:
        raise ValueError("timeline working_zone exceeds video frame_count")
    return replace(
        project,
        videos=(*project.videos, video),
        timelines=(*project.timelines, timeline),
    )


def relink_video(project: Project, video_id: UUID, file_path: PurePosixPath) -> Project:
    """Update only a video's portable path; observations remain untouched."""

    if file_path.is_absolute():
        raise ValueError("relinked file_path must remain project-relative")
    found = False
    videos: list[Video] = []
    for video in project.videos:
        if video.video_id == video_id:
            videos.append(replace(video, file_path=file_path))
            found = True
        else:
            videos.append(video)
    if not found:
        raise ValueError(f"unknown video_id: {video_id}")
    return replace(project, videos=tuple(videos))


def update_timeline(
    project: Project, timeline: Timeline, *, recalculate_times: bool = False
) -> Project:
    """Update timing and either flag or explicitly recalculate frozen times."""

    existing = next(
        (item for item in project.timelines if item.video_id == timeline.video_id), None
    )
    if existing is None:
        raise ValueError(f"unknown video_id: {timeline.video_id}")
    video = next(item for item in project.videos if item.video_id == timeline.video_id)
    if timeline.working_zone[1] >= video.frame_count:
        raise ValueError("timeline working_zone exceeds video frame_count")
    timelines = tuple(
        timeline if item.video_id == timeline.video_id else item
        for item in project.timelines
    )
    fps_changed = not isclose(
        timeline.fps_nominal,
        existing.fps_nominal,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    if not fps_changed and not recalculate_times:
        return replace(project, timelines=timelines)

    affected_track_ids = {
        track.track_id for track in project.tracks if track.video_id == timeline.video_id
    }
    now = utc_now()
    observations: list[TrackPoint] = []
    for point in project.observations:
        if point.track_id not in affected_track_ids:
            observations.append(point)
            continue
        flags = tuple(flag for flag in point.quality_flags if flag != "time_mismatch")
        if recalculate_times:
            observations.append(
                replace(
                    point,
                    time_s=frame_to_time(point.frame_index, timeline),
                    quality_flags=flags,
                    modified_at=now,
                )
            )
        elif has_time_mismatch(point.frame_index, point.time_s, timeline):
            observations.append(
                replace(
                    point,
                    quality_flags=(*flags, "time_mismatch"),
                    modified_at=now,
                )
            )
        else:
            observations.append(
                replace(point, quality_flags=flags, modified_at=now)
                if flags != point.quality_flags
                else point
            )
    return replace(
        project,
        timelines=timelines,
        observations=tuple(observations),
        derived=mark_tracks_stale(project.derived, affected_track_ids),
    )


def set_active_calibration(
    project: Project, video_id: UUID, calibration_id: UUID | None
) -> Project:
    """Set or clear one video's active calibration and invalidate prior interpretation."""

    video_ids = {video.video_id for video in project.videos}
    if video_id not in video_ids:
        raise ValueError(f"unknown video_id: {video_id}")
    previous = project.active_calibration_by_video.get(video_id)
    if previous == calibration_id:
        return project
    active = dict(project.active_calibration_by_video)
    if calibration_id is None:
        active.pop(video_id, None)
    else:
        calibration = next(
            (item for item in project.calibrations if item.calibration_id == calibration_id),
            None,
        )
        if calibration is None or calibration.video_id != video_id:
            raise ValueError("active calibration must exist and belong to the video")
        active[video_id] = calibration_id
    # Switching interpretation invalidates data produced with the previous
    # calibration. Data already produced with the newly selected calibration
    # remains valid (data-model.md §6.3).
    changed_ids = {previous} if previous is not None else set()
    return replace(
        project,
        active_calibration_by_video=active,
        derived=mark_calibrations_stale(project.derived, changed_ids),
    )


def add_calibration(project: Project, calibration: Calibration) -> Project:
    """Add a uniquely identified Calibration for a registered video."""

    if calibration.video_id not in {video.video_id for video in project.videos}:
        raise ValueError("calibration must reference a registered video")
    if any(
        item.calibration_id == calibration.calibration_id
        for item in project.calibrations
    ):
        raise ValueError(f"calibration_id already exists: {calibration.calibration_id}")
    return replace(project, calibrations=(*project.calibrations, calibration))


def replace_calibration(project: Project, calibration: Calibration) -> Project:
    """Replace calibration parameters without mutating raw observations."""

    found = False
    calibrations: list[Calibration] = []
    for existing in project.calibrations:
        if existing.calibration_id == calibration.calibration_id:
            if existing.video_id != calibration.video_id:
                raise ValueError("calibration video_id cannot change")
            calibrations.append(calibration)
            found = True
        else:
            calibrations.append(existing)
    if not found:
        raise ValueError(f"unknown calibration_id: {calibration.calibration_id}")
    return replace(
        project,
        calibrations=tuple(calibrations),
        derived=mark_calibrations_stale(project.derived, {calibration.calibration_id}),
    )


def delete_track(project: Project, track_id: UUID) -> Project:
    """Cascade a confirmed Track deletion to observations and derived data."""

    if not any(track.track_id == track_id for track in project.tracks):
        raise ValueError(f"unknown track_id: {track_id}")
    return replace(
        project,
        tracks=tuple(track for track in project.tracks if track.track_id != track_id),
        observations=tuple(
            point for point in project.observations if point.track_id != track_id
        ),
        derived=tuple(item for item in project.derived if item.track_id != track_id),
    )


def delete_calibration(project: Project, calibration_id: UUID) -> Project:
    """Delete a calibration; clearing an active one invalidates its derived data."""

    calibration = next(
        (item for item in project.calibrations if item.calibration_id == calibration_id),
        None,
    )
    if calibration is None:
        raise ValueError(f"unknown calibration_id: {calibration_id}")
    active = dict(project.active_calibration_by_video)
    if active.get(calibration.video_id) == calibration_id:
        active.pop(calibration.video_id)
    return replace(
        project,
        calibrations=tuple(
            item
            for item in project.calibrations
            if item.calibration_id != calibration_id
        ),
        active_calibration_by_video=active,
        derived=mark_calibrations_stale(project.derived, {calibration_id}),
    )


def validate_project(project: Project) -> None:
    """Validate aggregate references and project-wide uniqueness invariants."""

    video_ids = [video.video_id for video in project.videos]
    if len(set(video_ids)) != len(video_ids):
        raise ValueError("video_id values must be unique")
    if len({video.file_path for video in project.videos}) != len(project.videos):
        raise ValueError("video file_path values must be unique")
    timelines = {timeline.video_id: timeline for timeline in project.timelines}
    if len(timelines) != len(project.timelines) or set(timelines) != set(video_ids):
        raise ValueError("each video must have exactly one Timeline")
    videos_by_id = {video.video_id: video for video in project.videos}
    for video_id, timeline in timelines.items():
        if timeline.working_zone[1] >= videos_by_id[video_id].frame_count:
            raise ValueError("timeline working_zone exceeds video frame_count")
    track_ids = [track.track_id for track in project.tracks]
    if len(set(track_ids)) != len(track_ids):
        raise ValueError("track_id values must be unique")
    if len({track.name for track in project.tracks}) != len(project.tracks):
        raise ValueError("track names must be project-unique")
    if any(track.video_id not in videos_by_id for track in project.tracks):
        raise ValueError("every track must reference a registered video")
    tracks_by_id = {track.track_id: track for track in project.tracks}
    track_id_set = set(track_ids)
    point_ids = [point.point_id for point in project.observations]
    if len(set(point_ids)) != len(point_ids):
        raise ValueError("point_id values must be unique")
    if any(point.track_id not in track_id_set for point in project.observations):
        raise ValueError("every observation must reference a registered track")
    if any(point.source not in project.registries.sources for point in project.observations):
        raise ValueError("every observation source must be registered")
    registered_flags = set(project.registries.quality_flags)
    if any(
        any(flag not in registered_flags for flag in point.quality_flags)
        for point in project.observations
    ):
        raise ValueError("every observation quality flag must be registered")
    for point in project.observations:
        track = tracks_by_id[point.track_id]
        video = videos_by_id[track.video_id]
        if point.frame_index >= video.frame_count:
            raise ValueError("observation frame_index exceeds its video frame_count")
    points_by_id = {point.point_id: point for point in project.observations}
    for point in project.observations:
        if point.superseded_by is None:
            continue
        replacement = points_by_id.get(point.superseded_by)
        if replacement is None:
            raise ValueError("superseded_by must reference an existing observation")
        if (
            replacement.track_id != point.track_id
            or replacement.frame_index != point.frame_index
        ):
            raise ValueError("superseded_by must stay within the same track and frame")
    calibration_by_id = {item.calibration_id: item for item in project.calibrations}
    if len(calibration_by_id) != len(project.calibrations):
        raise ValueError("calibration_id values must be unique")
    if any(item.video_id not in videos_by_id for item in project.calibrations):
        raise ValueError("every calibration must reference a registered video")
    for video_id, calibration_id in project.active_calibration_by_video.items():
        calibration = calibration_by_id.get(calibration_id)
        if video_id not in videos_by_id or calibration is None:
            raise ValueError("active calibration references must exist")
        if calibration.video_id != video_id:
            raise ValueError("active calibration must belong to its mapped video")
    if any(item.track_id not in track_id_set for item in project.derived):
        raise ValueError("every DerivedData item must reference a registered track")
