"""应用层运动学批次：独立快照计算，输入未变化时才允许原子提交。"""

from concurrent.futures import CancelledError
from dataclasses import dataclass
from threading import Event
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.source_recipe import (
    SmoothingParameters, smoothing_derivative_order, smoothing_step,
)
from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import DerivedData, KINEMATICS_KINDS, preserve_derived_extensions
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.video import Video


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
    points = tuple(point for track_id in track_ids for point in session.effective_points(track_id))
    return AnalysisInputs(session.project.project_id, video, timeline,
                          session.active_calibration(video_id), tracks, points,
                          session.measurement_timing_detail(video_id))


@dataclass(frozen=True)
class KinematicsJob:
    """snapshot 在创建后移交 worker 独占，GUI 只读取 inputs/parameters。"""

    snapshot: ProjectSession
    inputs: AnalysisInputs
    parameters: SmoothingParameters
    previous_derived_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class KinematicsResult:
    inputs: AnalysisInputs
    records: tuple[DerivedData, ...]
    parameters: SmoothingParameters = SmoothingParameters()
    previous_derived_ids: tuple[UUID, ...] = ()


def prepare_kinematics_job(session: ProjectSession, video_id: UUID,
                           track_ids: tuple[UUID, ...], parameters: SmoothingParameters) -> KinematicsJob:
    snapshot = session.detached()
    inputs = analysis_inputs(snapshot, video_id, track_ids)
    expected = {(track_id, kind) for track_id in track_ids for kind in KINEMATICS_KINDS}
    return KinematicsJob(snapshot, inputs, parameters, derived_result_ids(snapshot, expected))


def run_kinematics_job(job: KinematicsJob, cancel: Event) -> KinematicsResult:
    """不写活动会话或文件；在各轨迹间检查取消，失败不会产生部分提交。"""

    records: list[DerivedData] = []
    for track in job.inputs.tracks:
        if cancel.is_set():
            raise CancelledError()
        computed = job.snapshot.compute_kinematics(track.track_id,
            window_length=job.parameters.window_length, polyorder=job.parameters.polyorder)
        records.extend(computed)
    if cancel.is_set():
        raise CancelledError()
    return KinematicsResult(job.inputs, tuple(records), job.parameters, job.previous_derived_ids)


def validated_derived(session: ProjectSession, result: KinematicsResult) -> tuple[DerivedData, ...]:
    """重算提交前复核原输入，保留非目标结果及目标记录的未知扩展字段。"""

    track_ids = tuple(track.track_id for track in result.inputs.tracks)
    expected = {(track_id, kind) for track_id in track_ids for kind in KINEMATICS_KINDS}
    if any(record.input.reference_track_id is not None for record in result.records):
        raise ProjectSessionError("Kinematics batch cannot contain reference tracks")
    validate_smoothing_recipe(result.records, result.parameters, result.inputs.timeline.fps_nominal)
    return validated_batch(session, result.inputs, result.records, expected, result.previous_derived_ids)


def validated_batch(
    session: ProjectSession,
    inputs: AnalysisInputs,
    records: tuple[DerivedData, ...],
    expected: set[tuple[UUID, str]],
    previous_derived_ids: tuple[UUID, ...] = (),
) -> tuple[DerivedData, ...]:
    """分析批次的共用提交校验：输入复核、完整性、非目标保留与扩展字段合并。

    kinematics 与 angular 批次共用（ADR-0019）；expected 是本批次应当
    恰好产出的 (track_id, kind) 集合，多出、缺失或重复都拒绝提交。
    """

    track_ids = tuple(track.track_id for track in inputs.tracks)
    if analysis_inputs(session, inputs.video.video_id, track_ids) != inputs:
        raise ProjectSessionError("Analysis inputs changed; results discarded. Recompute again.")
    actual = [(record.track_id, record.kind) for record in records]
    if set(actual) != expected or len(actual) != len(expected):
        raise ProjectSessionError("Incomplete analysis batch; results discarded")
    if derived_result_ids(session, expected) != previous_derived_ids:
        raise ProjectSessionError("Analysis results changed; old batch discarded. Recompute again.")
    calibration_id = inputs.calibration.calibration_id if inputs.calibration else None
    if any(record.status != "valid" or record.calibration_ref != calibration_id for record in records):
        raise ProjectSessionError("Analysis batch has inconsistent status or calibration")
    for record in records:
        steps = [step for step in record.pipeline if isinstance(step, dict)
                 and step.get("step") == "calibration_transform"]
        if calibration_id is None:
            matches = not steps
        else:
            params = steps[0].get("params") if len(steps) == 1 else None
            matches = isinstance(params, dict) and params.get("calibration_id") == str(calibration_id)
        if not matches:
            raise ProjectSessionError("Analysis calibration pipeline does not match its inputs")
    kept = tuple(item for item in session.project.derived if (item.track_id, item.kind) not in expected)
    records_out = []
    for record in records:
        previous = session.derived_data(record.track_id, record.kind)
        records_out.append(preserve_derived_extensions(record, previous))
    return kept + tuple(records_out)


def derived_result_ids(session: ProjectSession, expected: set[tuple[UUID, str]]) -> tuple[UUID, ...]:
    """只捕获将被替换的结果身份；其他轨迹 / 分析族计算不阻止本批次。"""
    return tuple(item.derived_id for item in session.project.derived
                 if (item.track_id, item.kind) in expected)


def validate_smoothing_recipe(records: tuple[DerivedData, ...], parameters: SmoothingParameters,
                              fps_nominal: float) -> None:
    """批次结果须匹配本次请求的 SG 配方，不能把另一窗口的结果登记为当前计算。"""
    for record in records:
        if smoothing_derivative_order(record.kind) is None:
            continue  # 原始位置 / 原始角度不使用 SG，kind 完整性由 validated_batch 检查。
        expected = smoothing_step(record.kind, parameters.window_length,
                                  parameters.polyorder, fps_nominal)["params"]
        steps = [step for step in record.pipeline if isinstance(step, dict)
                 and step.get("step") == "savitzky_golay"]
        params = steps[0].get("params") if len(steps) == 1 else None
        if not isinstance(params, dict) or any(params.get(key) != value for key, value in expected.items()):
            raise ProjectSessionError("Analysis result does not match the requested smoothing recipe")
