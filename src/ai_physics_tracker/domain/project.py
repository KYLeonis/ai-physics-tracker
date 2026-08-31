"""Project 聚合根、创建辅助函数与跨对象校验。"""

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
    """随项目一起持久化的开放字符串注册表。"""

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
    """单次实验分析会话的持久化聚合根。"""

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
    """创建一个有效空项目，自动生成标识与 UTC 时间戳。"""

    now = utc_now()
    return Project(
        project_id=uuid4(),
        name=name,
        description=description,
        created_at=now,
        modified_at=now,
    )


def add_video(project: Project, video: Video, timeline: Timeline) -> Project:
    """将 CFR 视频元数据与其 Timeline 作为一次原子领域更新注册。"""

    if video.vfr_suspected:
        raise ValueError("VFR video is not supported; transcode it to CFR before analysis")
    return register_video_reference(project, video, timeline)


def register_video_reference(project: Project, video: Video, timeline: Timeline) -> Project:
    """只登记媒体引用；分析能力由应用会话的本次时序验证授权。"""

    if timeline.video_id != video.video_id:
        raise ValueError("timeline.video_id must match video.video_id")
    if any(item.video_id == video.video_id for item in project.videos):
        raise ValueError(f"video_id is already registered: {video.video_id}")
    if any(
        _video_reference_key(item) == _video_reference_key(video)
        for item in project.videos
    ):
        raise ValueError("video locator is already registered")
    if timeline.working_zone[1] >= video.frame_count:
        raise ValueError("timeline working_zone exceeds video frame_count")
    return replace(
        project,
        videos=(*project.videos, video),
        timelines=(*project.timelines, timeline),
    )


def relink_video(
    project: Project,
    video_id: UUID,
    *,
    file_path: PurePosixPath | None,
    original_path: str | None,
) -> Project:
    """更新一个视频的定位器，不触碰任何观测数据。"""

    found = False
    videos: list[Video] = []
    for video in project.videos:
        if video.video_id == video_id:
            videos.append(
                replace(
                    video,
                    file_path=file_path,
                    original_path=original_path,
                )
            )
            found = True
        else:
            videos.append(video)
    if not found:
        raise ValueError(f"unknown video_id: {video_id}")
    return replace(project, videos=tuple(videos))


def update_timeline(
    project: Project, timeline: Timeline, *, recalculate_times: bool = False
) -> Project:
    """更新时间参数，并按选择标记 time_mismatch 或显式重算冻结时间。"""

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
    """设置或清除一个视频的 active 标定，并使先前的解释结果失效。"""

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
    # 切换解释基准会使旧标定产出的数据失效；用新选标定已经产出的数据
    # 仍然有效（data-model.md §6.3）。
    changed_ids = {previous} if previous is not None else set()
    derived = mark_calibrations_stale(project.derived, changed_ids)
    if previous is None:
        # 首次标定同样改变像素结果的解释基准，只影响该视频的基础运动学记录。
        from ai_physics_tracker.domain.derived import KINEMATICS_KINDS
        track_ids = {track.track_id for track in project.tracks if track.video_id == video_id}
        derived = tuple(replace(item, status="stale")
                        if item.track_id in track_ids and item.calibration_ref is None
                        and item.kind in KINEMATICS_KINDS else item for item in derived)
    return replace(
        project,
        active_calibration_by_video=active,
        derived=derived,
    )


def add_calibration(project: Project, calibration: Calibration) -> Project:
    """为已注册视频添加 calibration_id 唯一的 Calibration。"""

    if calibration.video_id not in {video.video_id for video in project.videos}:
        raise ValueError("calibration must reference a registered video")
    if any(
        item.calibration_id == calibration.calibration_id
        for item in project.calibrations
    ):
        raise ValueError(f"calibration_id already exists: {calibration.calibration_id}")
    return replace(project, calibrations=(*project.calibrations, calibration))


def replace_calibration(project: Project, calibration: Calibration) -> Project:
    """替换标定参数，不改动任何原始观测。"""

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
    """将确认删除的 Track 级联到观测与派生数据。"""

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
    """删除标定；若删除的是 active 标定则使其派生数据失效。"""

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
    """校验聚合引用与项目级唯一性不变量。"""

    video_ids = [video.video_id for video in project.videos]
    if len(set(video_ids)) != len(video_ids):
        raise ValueError("video_id values must be unique")
    if len({_video_reference_key(video) for video in project.videos}) != len(
        project.videos
    ):
        raise ValueError("video locators must be unique")
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


def _video_reference_key(video: Video) -> tuple[str, str]:
    if video.file_path is not None:
        return "project", video.file_path.as_posix().casefold()
    if video.original_path is None:
        raise ValueError("video must define a managed or external locator")
    return "external", video.original_path.replace("\\", "/").casefold()
