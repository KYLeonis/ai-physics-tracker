"""应用层：在 adopted snapshot 消费入口复核身份，再交给 Qt-free 数值核心。"""

from concurrent.futures import CancelledError
from dataclasses import asdict, dataclass
from threading import Event
from typing import cast
from uuid import UUID, uuid4

from ai_physics_tracker.application.adopted_measurement import (
    AdoptedMeasurementSnapshot, assert_adopted_measurement_current, build_adopted_measurement,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.angular_analysis import (
    AngularSeries, STUDENT, analysis_config, analyze_angular_series,
)
from ai_physics_tracker.domain.pendulum import QCExclusion, ROLE_ORDER
from ai_physics_tracker.domain.pendulum_energy import energy_config, reference_energy
from ai_physics_tracker.domain.pendulum_reconstruction import (
    AdoptedLandmark, MeasurementFrame, ReconstructionInput, PendulumReconstruction,
    reconstruction_config, reconstruct_pendulum,
)
from ai_physics_tracker.domain.scientific_result import ResultColumn, ScientificResult
from ai_physics_tracker.domain.types import canonical_json_digest, utc_now
from ai_physics_tracker.infrastructure.publication_serializer import geometry_from_payload
from ai_physics_tracker.infrastructure.scientific_payload import write_scientific_payload, read_scientific_payload


def prepare_pendulum_reconstruction(
    session: ProjectSession, snapshot: AdoptedMeasurementSnapshot,
) -> ReconstructionInput:
    """每次分析消费调用一次 current 检查；不逐帧哈希视频。"""
    assert_adopted_measurement_current(session, snapshot)
    payload = snapshot.payload
    if payload["calibration"] is None:
        raise ProjectSessionError("pendulum analysis requires scale calibration")
    if payload["physical"] is None:
        raise ProjectSessionError("pendulum analysis requires physical length and gravity")
    frames = []
    for row in cast(list[dict[str, object]], payload["frames"]):
        points = cast(dict[str, dict[str, object] | None], row["points_by_role"])
        adopted = []
        for role in ROLE_ORDER:
            point = points[role]
            adopted.append(None if point is None else AdoptedLandmark(
                cast(float, point["pixel_x"]), cast(float, point["pixel_y"]),
                cast(str, point["source"]), cast(float | None, point["confidence"]),
            ))
        frames.append(MeasurementFrame(cast(int, row["frame_index"]),
                                       cast(float, row["time_absolute_s"]), tuple(adopted)))
    try:
        return ReconstructionInput(
            snapshot.digest, tuple(frames),
            geometry_from_payload(cast(dict[str, object], payload["geometry"])),
            cast(int, payload["release_frame_index"]),
            tuple(QCExclusion(cast(int, item["frame_index"]), cast(str, item["reason"]))
                  for item in cast(list[dict[str, object]], payload["qc_overrides"])),
        )
    except ValueError as error:
        raise ProjectSessionError(str(error)) from error


def angular_series_from_reconstruction(
    reconstruction: PendulumReconstruction, fps_nominal: float,
) -> AngularSeries:
    """沿用 P2.1 全部源帧；不筛成稀疏 valid 列表，不压缩时间。"""
    rows = reconstruction.frames
    return AngularSeries(
        reconstruction.input_digest, tuple(row.frame_index for row in rows),
        tuple(row.time_release_relative_s for row in rows),
        tuple(row.theta_rad for row in rows), tuple(row.is_qc_valid for row in rows), fps_nominal,
    )


ANALYSIS_KIND = "pendulum-core-analysis-v1"
CORE_VERSION = "pendulum-core-analysis-2.0.0"
COLUMNS = tuple(ResultColumn(name, dtype, unit) for name, dtype, unit in (
    ("frame_index", "int64", None), ("time_absolute_s", "float64", "s"),
    ("time_release_relative_s", "float64", "s"), ("theta_rad", "float64?", "rad"),
    ("phi_rad", "float64?", "rad"), ("omega_rad_s", "float64?", "rad/s"),
    ("is_qc_valid", "bool", None), ("qc_reasons", "string[]", None),
    ("auxiliary_qc_reasons", "string[]", None),
    ("radius_px", "float64?", "px"), ("body_length_px", "float64?", "px"),
    ("pivot_displacement_px", "float64?", "px"),
    ("relative_weight", "float64?", None), ("edge_window", "bool", None),
    ("omega_reason", "string?", None), ("potential_s_inv2", "float64?", "s^-2"),
    ("kinetic_s_inv2", "float64?", "s^-2"), ("energy_s_inv2", "float64?", "s^-2"),
    ("energy_reason", "string?", None), ("points_by_role", "object", None),
))


def analysis_input_state(session: ProjectSession, experiment_id: UUID) -> tuple:
    """内存捕获的数值事实；GUI 状态与别的视频改动不拒绝后台结果。"""
    project = session.project
    experiment = session.pendulum_experiment(experiment_id)
    return (project.project_id, session.project_root, experiment,
            next(v for v in project.videos if v.video_id == experiment.video_id),
            next(t for t in project.timelines if t.video_id == experiment.video_id),
            session.active_calibration(experiment.video_id),
            tuple(p for p in project.observations if p.track_id in experiment.roles.track_ids()),
            next((r for r in project.tracking_runs if r.run_id == experiment.active_infer_run_id), None))


def analysis_video_stamp(session: ProjectSession, experiment_id: UUID) -> tuple:
    """SHA已在worker验证；主线程用stat代际拒绝验证后发生的文件变更。"""
    experiment = session.pendulum_experiment(experiment_id)
    video = next(v for v in session.project.videos if v.video_id == experiment.video_id)
    path = session.video_path(video)
    if path is None:
        raise ProjectSessionError("analysis video is unavailable")
    stat = path.stat()
    return (str(path.resolve()), stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def analysis_signature(snapshot: AdoptedMeasurementSnapshot, end_frame_index: int) -> str:
    return canonical_json_digest({"measurement_digest": snapshot.digest,
        "end_frame_index": end_frame_index, "core_version": CORE_VERSION,
        "reconstruction": reconstruction_config(), "angular": analysis_config(STUDENT),
        "energy": energy_config()})


@dataclass(frozen=True)
class PendulumAnalysisJob:
    session: ProjectSession
    experiment_id: UUID
    end_frame_index: int
    captured_state: tuple


@dataclass(frozen=True)
class PendulumAnalysisResult:
    record: ScientificResult
    payload: dict
    captured_state: tuple
    verified_video_stamp: tuple


def prepare_analysis_job(session: ProjectSession, experiment_id: UUID,
                         end_frame_index: int) -> PendulumAnalysisJob:
    if session.project_root is None:
        raise ProjectSessionError("save the publication project before analysis")
    experiment = session.pendulum_experiment(experiment_id)
    video = next(v for v in session.project.videos if v.video_id == experiment.video_id)
    if type(end_frame_index) is not int or not 0 <= end_frame_index < video.frame_count:
        raise ProjectSessionError("analysis end frame must be in the video")
    if experiment.release_frame_index is None or end_frame_index < experiment.release_frame_index:
        raise ProjectSessionError("analysis end frame must be at or after release")
    if not session.can_measure(video.video_id):
        raise ProjectSessionError("video timing must be authorized before analysis")
    return PendulumAnalysisJob(session.detached(), experiment_id, end_frame_index,
                               analysis_input_state(session, experiment_id))


def _check_cancel(cancel: Event) -> None:
    if cancel.is_set():
        raise CancelledError()


def run_analysis_job(job: PendulumAnalysisJob, cancel: Event) -> PendulumAnalysisResult:
    """worker 拥有 detached session；文件完整发布后才返回待提交 record。"""
    _check_cancel(cancel)
    snapshot = build_adopted_measurement(job.session, job.experiment_id)
    reconstruction = reconstruct_pendulum(prepare_pendulum_reconstruction(job.session, snapshot))
    series = angular_series_from_reconstruction(reconstruction, snapshot.payload["video"]["fps_nominal"])
    angular = analyze_angular_series(series, end_frame_index=job.end_frame_index)
    physical = snapshot.payload["physical"]
    energy = reference_energy(series, angular, physical["length_m"], physical["g_m_s2"])
    _check_cancel(cancel)
    rows = []
    for i, row in enumerate(reconstruction.frames):
        rows.append({**asdict(row), "points_by_role": snapshot.payload["frames"][i]["points_by_role"],
            "omega_rad_s": angular.omega_rad_s[i], "omega_reason": angular.omega_reasons[i],
            "edge_window": angular.edge_window[i], "potential_s_inv2": energy.potential_s_inv2[i],
            "kinetic_s_inv2": energy.kinetic_s_inv2[i], "energy_s_inv2": energy.total_s_inv2[i],
            "energy_reason": energy.reasons[i]})
    digest = analysis_signature(snapshot, job.end_frame_index)
    payload = {"contract": ANALYSIS_KIND, "input_digest": digest, "measurement": snapshot.payload,
        "config": {"reconstruction": reconstruction_config(), "angular": analysis_config(STUDENT),
                   "energy": energy_config(), "end_frame_index": job.end_frame_index},
        "reconstruction_digest": reconstruction.input_digest, "angular_digest": angular.input_digest,
        "energy_digest": energy.input_digest, "q_reference_s_inv2": energy.q_s_inv2,
        "body_reference_px": reconstruction.body_reference_px,
        "body_reference_frames": list(reconstruction.body_reference_frames),
        "body_reference_digest": reconstruction.body_reference_digest,
        "periods": asdict(angular.periods), "tail": asdict(angular.tail),
        "information_extrema": list(angular.information_extrema), "rows": rows}
    # 此处复核外部 video 内容；主线程再比较捕获的全部内存事实，避免 GUI 哈希大视频。
    video_stamp = analysis_video_stamp(job.session, job.experiment_id)
    assert_adopted_measurement_current(job.session, snapshot)
    if analysis_video_stamp(job.session, job.experiment_id) != video_stamp:
        raise ProjectSessionError("video changed during analysis verification")
    _check_cancel(cancel)
    result_id = uuid4()
    reference = write_scientific_payload(job.session.project_root, result_id, payload, COLUMNS)
    record = ScientificResult(result_id, job.experiment_id, ANALYSIS_KIND, utc_now(),
        digest, CORE_VERSION, "success" if any(v is not None for v in energy.total_s_inv2) else "insufficient_data",
        payload=reference, extra_fields={"measurement_digest": snapshot.digest,
            "end_frame_index": job.end_frame_index, "config": payload["config"],
            "active_run_id": str(snapshot.active_run_id)})
    if cancel.is_set():
        (job.session.project_root / reference.path).unlink(missing_ok=True)
        raise CancelledError()
    return PendulumAnalysisResult(record, payload, job.captured_state, video_stamp)


def load_analysis_result(session: ProjectSession, record: ScientificResult) -> tuple[dict, bool, str | None]:
    """后台校验文件和内容签名；漏置 stale 布尔也不能显示 valid。"""
    if record.kind != ANALYSIS_KIND or record.payload is None or session.project_root is None:
        raise ProjectSessionError("pendulum result has no readable payload")
    payload = read_scientific_payload(session.project_root, record.payload)
    if payload.get("contract") != ANALYSIS_KIND or payload.get("input_digest") != record.input_digest:
        raise ProjectSessionError("pendulum payload identity does not match record")
    try:
        snapshot = build_adopted_measurement(session, record.experiment_id)
        current = analysis_signature(snapshot, record.extra_fields["end_frame_index"])
    except (ProjectSessionError, ValueError, KeyError) as error:
        return payload, False, str(error)
    valid = current == record.input_digest and record.core_version == CORE_VERSION and record.freshness == "valid"
    return payload, valid, None if valid else "analysis inputs changed — recompute"
