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
from ai_physics_tracker.domain.pendulum import PendulumExperiment
from ai_physics_tracker.domain.scientific_result import ScientificResult, is_sha256_hex
from ai_physics_tracker.domain.timeline import (
    Timeline,
    frame_to_time,
    has_time_mismatch,
)
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.domain.types import JsonObject, require_aware_datetime, utc_now
from ai_physics_tracker.domain.video import Video

# publication 契约 §1：v2 顶层 required_capabilities 固定包含这两项；读者必须
# 理解全部 required 项才能写入，未知项在 load/save 两侧均拒绝。
PUBLICATION_REQUIRED_CAPABILITIES: tuple[str, ...] = (
    "pendulum-four-role-v1",
    "scientific-results-v1",
)
KNOWN_REQUIRED_CAPABILITIES = frozenset(PUBLICATION_REQUIRED_CAPABILITIES)


@dataclass(frozen=True)
class MigrationRecord:
    """v1→v2 显式 Save As 迁移的来源事实（契约 §1）。

    只记录 provenance；v1 原件保持不变，不提供 v2→v1 降级。
    """

    source_schema_version: int
    source_manifest_sha256: str

    def __post_init__(self) -> None:
        if self.source_schema_version < 1:
            raise ValueError("migration source_schema_version must be positive")
        if not is_sha256_hex(self.source_manifest_sha256):
            raise ValueError("migration source_manifest_sha256 must be a 64-hex digest")


@dataclass(frozen=True)
class Registries:
    """随项目一起持久化的开放字符串注册表。"""

    sources: tuple[str, ...] = ("manual", "template", "dlc")
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
    tracking_runs: tuple[TrackingRun, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    migration: MigrationRecord | None = None
    experiments: tuple[PendulumExperiment, ...] = ()
    scientific_results: tuple[ScientificResult, ...] = ()
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
    """将确认删除的 Track 级联到观测、派生数据与引擎运行记录。

    TrackingRun 以成员 Track 为主体（§7.6），run 不能脱离其成员存活；
    保留会在下一次 replace 的聚合校验中被拒绝。撤销恢复 track/观测/派生时，
    该 track 的 run 由会话历史快照一并恢复（P6R-01；Phase 5.4 起 Track 的
    refinement state 含 active run pointer，"恢复 track 不恢复 run"必然产生
    悬空引用）。

    experiment-bound Track 拒绝删除（契约 §5）：必须先显式删除或改绑
    experiment，不允许留下断引用的 roles/results。同理，被 experiment
    joint run 引用（即便已因 rebind 解除 role 绑定）的 Track 也拒绝——
    级联删除会整条抹掉共享测量历史，契约要求显式删除计划（不自动断引用）。
    """

    if not any(track.track_id == track_id for track in project.tracks):
        raise ValueError(f"unknown track_id: {track_id}")
    for experiment in project.experiments:
        if track_id in experiment.roles.track_ids():
            raise ValueError(
                f"track is bound to pendulum experiment {experiment.experiment_id}; "
                "rebind or delete the experiment before deleting the track"
            )
    for run in project.tracking_runs:
        if run.experiment_id is not None and track_id in run.member_track_ids:
            raise ValueError(
                f"track is a member of experiment joint run {run.run_id}; "
                "delete the referencing experiment runs before deleting the track"
            )
    return replace(
        project,
        tracks=tuple(track for track in project.tracks if track.track_id != track_id),
        observations=tuple(
            point for point in project.observations if point.track_id != track_id
        ),
        derived=tuple(item for item in project.derived if item.track_id != track_id),
        tracking_runs=tuple(
            run for run in project.tracking_runs
            if track_id not in run.member_track_ids
        ),
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
    run_ids = [run.run_id for run in project.tracking_runs]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("tracking run run_id values must be unique")
    for run in project.tracking_runs:
        if run.video_id not in videos_by_id:
            raise ValueError("every tracking run must reference a registered video")
        if any(member not in track_id_set for member in run.member_track_ids):
            raise ValueError("every tracking run member must reference a registered track")
        for member in run.member_track_ids:
            if tracks_by_id[member].video_id != run.video_id:
                raise ValueError("every tracking run member must belong to the run's video")
    _validate_format_mode(project, videos_by_id, tracks_by_id)


def _validate_format_mode(
    project: Project,
    videos_by_id: dict[UUID, Video],
    tracks_by_id: dict[UUID, Track],
) -> None:
    """区分 v1 generic 与 v2 publication 项目：不允许格式语义混装。

    capabilities 为空 = v1 语义，不得携带任何 publication 事实（契约 §1）；
    capabilities 非空 = v2 语义，必须恰好是已知的 publication 集合。
    """

    declared = set(project.required_capabilities)
    if not declared:
        if project.migration is not None:
            raise ValueError("v1 project must not carry a migration record")
        if project.experiments or project.scientific_results:
            raise ValueError("v1 project must not carry publication collections")
        for run in project.tracking_runs:
            if len(run.member_track_ids) != 1 or run.experiment_id is not None:
                raise ValueError(
                    "v1 project tracking runs must be single-member without experiment bindings"
                )
        return
    unknown = declared - KNOWN_REQUIRED_CAPABILITIES
    if unknown:
        raise ValueError(f"unknown required capabilities: {sorted(unknown)}")
    missing = set(PUBLICATION_REQUIRED_CAPABILITIES) - declared
    if missing:
        raise ValueError(f"publication project missing required capabilities: {sorted(missing)}")
    _validate_publication_collections(project, videos_by_id, tracks_by_id)


def _validate_publication_collections(
    project: Project,
    videos_by_id: dict[UUID, Video],
    tracks_by_id: dict[UUID, Track],
) -> None:
    """v2 publication 集合的跨对象不变量（契约 §2/§3）。

    单对象结构校验（四 role distinct、geometry/physical 有限性、digest
    一致性）已在值对象构造期完成；这里负责引用存在性、同 video 约束、
    唯一性与 active run 结构一致性。
    """

    experiment_ids = [item.experiment_id for item in project.experiments]
    if len(set(experiment_ids)) != len(experiment_ids):
        raise ValueError("experiment_id values must be unique")
    experiments_by_video: dict[UUID, PendulumExperiment] = {}
    bound_track_owner: dict[UUID, UUID] = {}
    experiments_by_id: dict[UUID, PendulumExperiment] = {}
    for experiment in project.experiments:
        video = videos_by_id.get(experiment.video_id)
        if video is None:
            raise ValueError("every experiment must reference a registered video")
        if experiment.video_id in experiments_by_video:
            raise ValueError("a video must have at most one pendulum experiment")
        experiments_by_video[experiment.video_id] = experiment
        experiments_by_id[experiment.experiment_id] = experiment
        for role, member in experiment.roles.by_role().items():
            if member not in tracks_by_id:
                raise ValueError(f"experiment role '{role}' must reference a registered track")
            if tracks_by_id[member].video_id != experiment.video_id:
                raise ValueError("experiment roles must reference tracks of the same video")
            owner = bound_track_owner.get(member)
            if owner is not None and owner != experiment.experiment_id:
                raise ValueError("a track cannot bind to two pendulum experiments")
            bound_track_owner[member] = experiment.experiment_id
        if experiment.release_frame_index is not None and (
            experiment.release_frame_index >= video.frame_count
        ):
            raise ValueError("experiment release_frame_index exceeds its video frame_count")
        if experiment.frame_set is not None and any(
            frame >= video.frame_count for frame in experiment.frame_set.frames
        ):
            raise ValueError("experiment frame set exceeds its video frame_count")
        if experiment.fixed_check is not None and any(
            frame >= video.frame_count for frame in experiment.fixed_check.frames
        ):
            raise ValueError(
                "experiment fixed check exceeds its video frame_count"
            )
    result_ids = [item.result_id for item in project.scientific_results]
    if len(set(result_ids)) != len(result_ids):
        raise ValueError("result_id values must be unique")
    for result in project.scientific_results:
        if result.experiment_id not in experiments_by_id:
            raise ValueError("every scientific result must reference a registered experiment")
    runs_by_id = {run.run_id: run for run in project.tracking_runs}
    for experiment in project.experiments:
        active_id = experiment.active_infer_run_id
        if active_id is None:
            continue
        run = runs_by_id.get(active_id)
        if run is None:
            raise ValueError("experiment active_infer_run_id must reference a registered run")
        if (
            run.experiment_id != experiment.experiment_id
            or run.task_type != "infer"
            or run.status != "completed"
        ):
            raise ValueError(
                "experiment active run must be a completed joint inference of this experiment"
            )
        if set(run.member_track_ids) != set(experiment.roles.track_ids()):
            raise ValueError(
                "experiment active run members must match the current role bindings"
            )
        if run.role_bindings != experiment.roles:
            raise ValueError(
                "experiment active run role_bindings must equal the current roles"
            )
    for run in project.tracking_runs:
        if run.experiment_id is None:
            if len(run.member_track_ids) != 1:
                raise ValueError("generic tracking runs must have exactly one member")
            # 迁移携带的 legacy generic run 允许引用 bound track（历史记录）；
            # 新的 generic run 注册在 session 层被拒绝（_require_unbound_track）。
            continue
        experiment = experiments_by_id.get(run.experiment_id)
        if experiment is None:
            raise ValueError("experiment-bound runs must reference a registered experiment")
        if experiment.video_id != run.video_id:
            raise ValueError("experiment-bound runs must belong to the experiment's video")
        # 角色快照是历史解释（契约 §3）：rebind 后旧 run 保留原快照，
        # 只有 experiment.active_infer_run_id 指向的 run 必须匹配当前 roles
        # （该检查在上方 active 指针校验中完成）。
        bindings = run.role_bindings
        if bindings is None:
            raise ValueError("experiment-bound run requires a role_bindings snapshot")
        if run.member_track_ids != bindings.track_ids():
            raise ValueError(
                "experiment-bound run members must follow the canonical role order"
            )


def _video_reference_key(video: Video) -> tuple[str, str]:
    if video.file_path is not None:
        return "project", video.file_path.as_posix().casefold()
    if video.original_path is None:
        raise ValueError("video must define a managed or external locator")
    return "external", video.original_path.replace("\\", "/").casefold()
