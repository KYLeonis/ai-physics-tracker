"""面向 P2 科学核心的只读四点测量交付(application 层,Qt-free)。"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.calibration import CalibrationTransform
from ai_physics_tracker.domain.timeline import TIME_COMPARISON_TOLERANCE_S, frame_to_time
from ai_physics_tracker.domain.types import canonical_json_digest
from ai_physics_tracker.infrastructure.hashing import file_sha256


def _coordinates(point: tuple[float, float]) -> list[float]:
    # JSON reader 将数值解析为 float；写入边界也统一，防止 1 与 1.0 导致重开失效。
    return [float(value) for value in point]


@dataclass(frozen=True)
class AdoptedMeasurementSnapshot:
    """payload 保留全部源帧;空点带显式缺测原因。"""

    experiment_id: UUID
    active_run_id: UUID
    payload: dict[str, object]
    digest: str


def build_adopted_measurement(
    session: ProjectSession, experiment_id: UUID,
) -> AdoptedMeasurementSnapshot:
    experiment = session.pendulum_experiment(experiment_id)
    active_id = experiment.active_infer_run_id
    run = next((item for item in session.tracking_runs() if item.run_id == active_id), None)
    if (active_id is None or run is None or run.status != "completed"
            or run.task_type != "infer"
            or run.config.get("request_kind") != "experiment-joint-inference-v1"
            or run.experiment_id != experiment_id
            or run.role_bindings != experiment.roles
            or run.member_track_ids != experiment.roles.track_ids()):
        raise ProjectSessionError("adopted measurement requires the current joint active run")
    if (not isinstance(run.extra_fields.get("input_digest"), str)
            or not isinstance(run.extra_fields.get("prediction_sha256"), str)):
        raise ProjectSessionError("adopted measurement active run has no verified input/artifact identity")
    video = next((item for item in session.project.videos
                  if item.video_id == experiment.video_id), None)
    timeline = next((item for item in session.project.timelines
                     if item.video_id == experiment.video_id), None)
    if video is None or timeline is None:
        raise ProjectSessionError("adopted measurement video or timeline is missing")
    video_path = session.video_path(video)
    if video_path is None or not video_path.is_file():
        raise ProjectSessionError("adopted measurement video file is unavailable")
    video_sha256 = file_sha256(video_path)
    if video_sha256 != run.extra_fields.get("video_sha256"):
        raise ProjectSessionError("adopted measurement video changed after inference")
    for point in session.project.observations:
        if point.track_id not in experiment.roles.track_ids() or point.source == "manual":
            continue
        if point.source != run.engine or point.source_detail != run.source_detail:
            raise ProjectSessionError(
                "adopted measurement contains AI observations not from the current active run"
            )

    calibration = session.active_calibration(video.video_id)
    calibration_fact = None
    if calibration is not None:
        transform = CalibrationTransform(calibration, video.height_px)
        calibration_fact = {
            "calibration_id": str(calibration.calibration_id),
            "scale_end_1_px": _coordinates(calibration.scale_end_1_px),
            "scale_end_2_px": _coordinates(calibration.scale_end_2_px),
            "known_length": float(calibration.known_length),
            "unit": calibration.unit,
            "pixels_per_unit": transform.pixels_per_unit,
            "origin_px": _coordinates(transform.origin_px),
            "rotation_deg": float(calibration.rotation_deg),
            "height_px": video.height_px,
        }
    vertical = experiment.geometry.true_vertical
    geometry_fact = {
        "fixed_pivot_px": _coordinates(experiment.geometry.fixed_pivot_px)
        if experiment.geometry.fixed_pivot_px is not None else None,
        "tip_radius_reference_px": float(experiment.geometry.tip_radius_reference_px)
        if experiment.geometry.tip_radius_reference_px is not None else None,
        "true_vertical": None if vertical is None else {
            "top_px": _coordinates(vertical.top_px),
            "bottom_px": _coordinates(vertical.bottom_px),
            "direction_confirmed": vertical.direction_confirmed,
            "confirmed_digest": vertical.confirmed_digest,
        },
    }
    physical = experiment.physical
    physical_fact = None if physical is None else {
        "length_m": float(physical.length_m), "length_source": physical.length_source,
        "g_m_s2": float(physical.g_m_s2), "g_source": physical.g_source,
    }
    release = experiment.release_frame_index
    release_time = frame_to_time(release, timeline) if release is not None else None
    effective_by_role = {
        role: {point.frame_index: point for point in session.effective_points(track_id)}
        for role, track_id in experiment.roles.by_role().items()
    }
    rows: list[dict[str, object]] = []
    for frame_index in range(video.frame_count):
        absolute = frame_to_time(frame_index, timeline)
        points: dict[str, dict[str, object] | None] = {}
        reasons: dict[str, str | None] = {}
        for role in effective_by_role:
            point = effective_by_role[role].get(frame_index)
            if point is None:
                points[role] = None
                reasons[role] = "no_adopted_point"
                continue
            if (point.frame_index != frame_index or point.status != "active"
                    or abs(point.time_s - absolute) >= TIME_COMPARISON_TOLERANCE_S
                    or not all(isfinite(value) for value in
                               (point.pixel_x, point.pixel_y))):
                raise ProjectSessionError("adopted point does not match source frame/time")
            points[role] = {
                "point_id": str(point.point_id),
                "pixel_x": float(point.pixel_x), "pixel_y": float(point.pixel_y),
                "source": point.source, "source_detail": point.source_detail,
                "confidence": float(point.confidence) if point.confidence is not None else None,
                "visibility": point.visibility,
                "quality_flags": list(point.quality_flags),
            }
            reasons[role] = None
        rows.append({
            "frame_index": frame_index,
            "time_absolute_s": absolute,
            "time_release_relative_s": absolute - release_time
            if release_time is not None else None,
            "points_by_role": points,
            "missing_reasons_by_role": reasons,
        })
    payload: dict[str, object] = {
        "contract": "adopted-four-landmark-v1",
        "experiment_id": str(experiment_id),
        "active_run_id": str(active_id),
        "candidate_input_digest": run.extra_fields.get("input_digest"),
        "prediction_sha256": run.extra_fields.get("prediction_sha256"),
        "measurement_revision": experiment.measurement_revision,
        "role_bindings": {role: str(track_id)
                          for role, track_id in experiment.roles.by_role().items()},
        "video": {
            "video_id": str(video.video_id), "sha256": video_sha256,
            "frame_count": video.frame_count, "width_px": video.width_px,
            "height_px": video.height_px, "fps_nominal": float(timeline.fps_nominal),
            "frame_indexing": timeline.frame_indexing,
            "working_zone": list(timeline.working_zone),
        },
        "geometry": geometry_fact,
        "calibration": calibration_fact,
        "release_frame_index": release,
        "release_time_absolute_s": release_time,
        "physical": physical_fact,
        "qc_overrides": [
            {"frame_index": item.frame_index, "reason": item.reason}
            for item in experiment.qc_overrides
        ],
        "frames": rows,
    }
    return AdoptedMeasurementSnapshot(
        experiment_id, active_id, payload, canonical_json_digest(payload),
    )


def assert_adopted_measurement_current(
    session: ProjectSession, snapshot: AdoptedMeasurementSnapshot,
) -> None:
    """任一依赖变化即 fail-closed;构建期错误也统一按 stale 报告。"""

    try:
        current = build_adopted_measurement(session, snapshot.experiment_id)
    except ProjectSessionError as error:
        raise ProjectSessionError(
            f"adopted measurement snapshot is stale: {error}"
        ) from error
    if (canonical_json_digest(snapshot.payload) != snapshot.digest
            or current.digest != snapshot.digest
            or current.active_run_id != snapshot.active_run_id):
        raise ProjectSessionError("adopted measurement snapshot is stale")
