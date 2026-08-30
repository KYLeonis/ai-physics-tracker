"""应用层运动学批次：独立快照计算，输入未变化时才允许原子提交。"""

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import dataclass, replace
from threading import Event
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import DerivedData, KINEMATICS_KINDS
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.video import Video


@dataclass(frozen=True)
class SmoothingParameters:
    """二阶 SG 管线参数；与 ADR-0008 保持相同默认值。"""

    window_length: int = 7
    polyorder: int = 2

    def __post_init__(self) -> None:
        if (type(self.window_length) is not int or type(self.polyorder) is not int
                or self.window_length % 2 != 1 or not 2 <= self.polyorder < self.window_length):
            raise ValueError("SG window must be odd and satisfy 2 <= polynomial order < window")


@dataclass(frozen=True)
class AnalysisInputs:
    """只包含会影响目标计算的输入，不包含视图、保存时间或其他轨迹的数据。"""

    project_id: UUID
    video: Video
    timeline: Timeline
    calibration: Calibration | None
    tracks: tuple[Track, ...]
    points: tuple[TrackPoint, ...]
    timing_detail: str | None


def analysis_inputs(session: ProjectSession, video_id: UUID,
                    track_ids: tuple[UUID, ...]) -> AnalysisInputs:
    """校验同视频轨迹与当前时序授权，取得可比较的输入快照。"""

    if not track_ids or len(set(track_ids)) != len(track_ids):
        raise ProjectSessionError("Select at least one distinct track")
    if not session.can_measure(video_id):
        raise ProjectSessionError("Video timing is not authorized; cached results are read-only")
    tracks = tuple(next((track for track in session.tracks if track.track_id == track_id), None)
                   for track_id in track_ids)
    if any(track is None or track.video_id != video_id for track in tracks):
        raise ProjectSessionError("All selected tracks must belong to the current video")
    video = next(item for item in session.project.videos if item.video_id == video_id)
    timeline = next(item for item in session.project.timelines if item.video_id == video_id)
    points = tuple(point for track_id in track_ids for point in session.manual_points(track_id))
    return AnalysisInputs(session.project.project_id, video, timeline,
                          session.active_calibration(video_id), tracks, points,
                          session.measurement_timing_detail(video_id))


@dataclass(frozen=True)
class KinematicsJob:
    """snapshot 在创建后移交 worker 独占，GUI 只读取 inputs/parameters。"""

    snapshot: ProjectSession
    inputs: AnalysisInputs
    parameters: SmoothingParameters


@dataclass(frozen=True)
class KinematicsResult:
    inputs: AnalysisInputs
    records: tuple[DerivedData, ...]


def prepare_kinematics_job(session: ProjectSession, video_id: UUID,
                           track_ids: tuple[UUID, ...], parameters: SmoothingParameters) -> KinematicsJob:
    snapshot = session.detached()
    return KinematicsJob(snapshot, analysis_inputs(snapshot, video_id, track_ids), parameters)


def run_kinematics_job(job: KinematicsJob, cancel: Event) -> KinematicsResult:
    """不写活动会话或文件；在各轨迹间检查取消，失败不会产生部分提交。"""

    records: list[DerivedData] = []
    for track in job.inputs.tracks:
        if cancel.is_set():
            raise CancelledError()
        computed = job.snapshot.compute_kinematics(track.track_id,
            window_length=job.parameters.window_length, polyorder=job.parameters.polyorder)
        for item in computed:
            extra_fields = deepcopy(item.extra_fields)
            # 时序上下文不是滤波步骤，使用既有可扩展字段记录，不改 schema。
            extra_fields["timing_context"] = {
                "fps_nominal": job.inputs.timeline.fps_nominal,
                "approximation": job.inputs.timing_detail,
            }
            records.append(replace(item, extra_fields=extra_fields))
    if cancel.is_set():
        raise CancelledError()
    return KinematicsResult(job.inputs, tuple(records))


def validated_derived(session: ProjectSession, result: KinematicsResult) -> tuple[DerivedData, ...]:
    """重算提交前复核原输入，保留非目标结果及目标记录的未知扩展字段。"""

    track_ids = tuple(track.track_id for track in result.inputs.tracks)
    if analysis_inputs(session, result.inputs.video.video_id, track_ids) != result.inputs:
        raise ProjectSessionError("Analysis inputs changed; results discarded. Recompute again.")
    expected = {(track_id, kind) for track_id in track_ids for kind in KINEMATICS_KINDS}
    actual = [(record.track_id, record.kind) for record in result.records]
    if set(actual) != expected or len(actual) != len(expected):
        raise ProjectSessionError("Incomplete kinematics batch; results discarded")
    kept = tuple(item for item in session.project.derived if (item.track_id, item.kind) not in expected)
    records = []
    for record in result.records:
        previous = session.derived_data(record.track_id, record.kind)
        extras = deepcopy(previous.extra_fields) if previous else {}
        extras.update(record.extra_fields)
        input_extras = deepcopy(previous.input.extra_fields) if previous else {}
        input_extras.update(record.input.extra_fields)
        records.append(replace(record, extra_fields=extras,
                               input=replace(record.input, extra_fields=input_extras)))
    return kept + tuple(records)
