"""应用层：冻结分析输入及无会话写入的运动学计算 / 候选记录构造。"""

from copy import deepcopy
from dataclasses import dataclass, replace
from math import pi
from uuid import UUID, uuid4

from ai_physics_tracker.application.source_recipe import (
    SmoothingParameters, smoothing_step, reference_parameters, timing_parameters,
)
from ai_physics_tracker.domain.angular import (
    AngularReference, PendulumReference, TwoPointReference, dense_to_sparse_scalar_records,
    direction_theta_world, pendulum_theta_world, unwrap_per_segment,
)
from ai_physics_tracker.domain.calibration import Calibration, CalibrationTransform
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.kinematics import (
    batch_pixel_to_world, dense_to_sparse_records, derive_unit, differentiate_savgol,
    expand_to_dense_grid, smooth_savgol,
)
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.types import JsonObject, utc_now
from ai_physics_tracker.domain.video import Video


@dataclass(frozen=True)
class AnalysisInputs:
    """本次必要输入；不包含会话、历史栈、视图或文件写入能力。"""

    project_id: UUID
    video: Video
    timeline: Timeline
    calibration: Calibration | None
    tracks: tuple[Track, ...]
    points: tuple[TrackPoint, ...]
    timing_detail: str | None


def compute_kinematics_records(inputs: AnalysisInputs, track_id: UUID,
                               parameters: SmoothingParameters) -> tuple[DerivedData, ...]:
    """只使用冻结值生成候选记录，不改工程、Undo或文件。"""
    track = next((item for item in inputs.tracks if item.track_id == track_id), None)
    if track is None:
        raise ValueError(f"unknown track_id: {track_id}")
    timeline, video = inputs.timeline, inputs.video
    window_length, polyorder = parameters.window_length, parameters.polyorder
    delta = 1.0 / timeline.fps_nominal
    points = tuple(point for point in inputs.points if point.track_id == track_id)

    frames, px_x, px_y = expand_to_dense_grid(
        points, frame_range=timeline.working_zone
    )

    active_cal = inputs.calibration
    if active_cal is not None:
        transform = CalibrationTransform(
            calibration=active_cal, height_px=video.height_px
        )
        pos_x, pos_y = batch_pixel_to_world(px_x, px_y, transform)
        pos_unit = active_cal.unit
        cal_ref = active_cal.calibration_id
        cal_step = [
            {
                "step": "calibration_transform",
                "params": {"calibration_id": str(active_cal.calibration_id)},
            }
        ]
    else:
        pos_x, pos_y = px_x.copy(), px_y.copy()
        pos_unit = "px"
        cal_ref = None
        cal_step = []

    smooth_x = smooth_savgol(
        pos_x, window_length=window_length, polyorder=polyorder
    )
    smooth_y = smooth_savgol(
        pos_y, window_length=window_length, polyorder=polyorder
    )
    vx = differentiate_savgol(
        pos_x,
        window_length=window_length,
        polyorder=polyorder,
        deriv=1,
        delta=delta,
    )
    vy = differentiate_savgol(
        pos_y,
        window_length=window_length,
        polyorder=polyorder,
        deriv=1,
        delta=delta,
    )
    ax = differentiate_savgol(
        pos_x,
        window_length=window_length,
        polyorder=polyorder,
        deriv=2,
        delta=delta,
    )
    ay = differentiate_savgol(
        pos_y,
        window_length=window_length,
        polyorder=polyorder,
        deriv=2,
        delta=delta,
    )

    now = utc_now()
    derived_input = DerivedInput(
        track_id=track_id,
        source_filter=None,
        include_superseded=False,
        extra_fields={"observation_selection": "effective"},
    )
    produced_by = "ai_physics_tracker.kinematics.v1"

    pos_frames, pos_values = dense_to_sparse_records(frames, pos_x, pos_y)
    smooth_frames, smooth_values = dense_to_sparse_records(frames, smooth_x, smooth_y)
    vel_frames, vel_values = dense_to_sparse_records(frames, vx, vy)
    acc_frames, acc_values = dense_to_sparse_records(frames, ax, ay)

    d_pos = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="world_position",
        input=derived_input,
        pipeline=tuple(cal_step),
        frames=pos_frames,
        values=pos_values,
        payload_ref=None,
        unit=pos_unit,
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    d_smooth = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="smoothed_position",
        input=derived_input,
        pipeline=(*cal_step,
                  smoothing_step("smoothed_position", window_length, polyorder, timeline.fps_nominal)),
        frames=smooth_frames,
        values=smooth_values,
        payload_ref=None,
        unit=pos_unit,
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    d_vel = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="velocity",
        input=derived_input,
        pipeline=(*cal_step,
                  smoothing_step("velocity", window_length, polyorder, timeline.fps_nominal)),
        frames=vel_frames,
        values=vel_values,
        payload_ref=None,
        unit=derive_unit(pos_unit, 1),
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    d_acc = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="acceleration",
        input=derived_input,
        pipeline=(*cal_step,
                  smoothing_step("acceleration", window_length, polyorder, timeline.fps_nominal)),
        frames=acc_frames,
        values=acc_values,
        payload_ref=None,
        unit=derive_unit(pos_unit, 2),
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    new_items = (d_pos, d_smooth, d_vel, d_acc)
    # 线性批次与角运动批次共用时序来源口径（ADR-0020）：fps / 区间 /
    # 近似授权记入既有可扩展字段，不改 schema；相空间配对依赖完整来源。
    timing_context = timing_parameters(timeline, inputs.timing_detail)
    return tuple(replace(item, extra_fields={"timing_context": deepcopy(timing_context)})
                 for item in new_items)


def compute_angular_records(inputs: AnalysisInputs, track_id: UUID, reference: AngularReference,
                            parameters: SmoothingParameters) -> tuple[DerivedData, ...]:
    """只使用冻结值生成候选记录，不改工程、Undo或文件。"""
    track = next((item for item in inputs.tracks if item.track_id == track_id), None)
    if track is None:
        raise ValueError(f"unknown track_id: {track_id}")
    timeline, video = inputs.timeline, inputs.video
    window_length, polyorder = parameters.window_length, parameters.polyorder
    active_cal = inputs.calibration
    if active_cal is None:
        raise ValueError("angular analysis requires an active calibration (phase6 R1)")
    delta = 1.0 / timeline.fps_nominal
    transform = CalibrationTransform(calibration=active_cal, height_px=video.height_px)
    points_a = tuple(point for point in inputs.points if point.track_id == track_id)

    frames, px_ax, px_ay = expand_to_dense_grid(
        points_a, frame_range=timeline.working_zone
    )
    world_ax, world_ay = batch_pixel_to_world(px_ax, px_ay, transform)

    if isinstance(reference, PendulumReference):
        reference_track_id: UUID | None = None
        pivot_wx, pivot_wy = transform.pixel_to_world(reference.pivot_px)
        theta = pendulum_theta_world(world_ax, world_ay, pivot_wx, pivot_wy)
        angle_params: JsonObject = reference_parameters(reference)
    elif isinstance(reference, TwoPointReference):
        if reference.reference_track_id == track_id:
            raise ValueError(
                "angular two-point reference must differ from the target track"
            )
        ref_track = next(
            (t for t in inputs.tracks
             if t.track_id == reference.reference_track_id),
            None,
        )
        if ref_track is None:
            raise ValueError(
                f"unknown reference track_id: {reference.reference_track_id}"
            )
        if ref_track.video_id != track.video_id:
            raise ValueError(
                "angular reference track must belong to the same video"
            )
        reference_track_id = reference.reference_track_id
        points_b = tuple(point for point in inputs.points if point.track_id == reference.reference_track_id)
        _, px_bx, px_by = expand_to_dense_grid(
            points_b, frame_range=timeline.working_zone
        )
        world_bx, world_by = batch_pixel_to_world(px_bx, px_by, transform)
        theta = direction_theta_world(world_ax, world_ay, world_bx, world_by)
        angle_params = reference_parameters(reference)
    else:
        raise ValueError(
            f"unsupported angular reference: {type(reference).__name__}"
        )

    unwrapped = unwrap_per_segment(theta)
    smooth_theta = smooth_savgol(
        unwrapped, window_length=window_length, polyorder=polyorder
    )
    omega = differentiate_savgol(
        unwrapped,
        window_length=window_length,
        polyorder=polyorder,
        deriv=1,
        delta=delta,
    )
    alpha = differentiate_savgol(
        unwrapped,
        window_length=window_length,
        polyorder=polyorder,
        deriv=2,
        delta=delta,
    )

    now = utc_now()
    derived_input = DerivedInput(
        track_id=track_id,
        source_filter=None,
        include_superseded=False,
        reference_track_id=reference_track_id,
        extra_fields={"observation_selection": "effective"},
    )
    produced_by = "ai_physics_tracker.angular.v1"
    cal_step = {
        "step": "calibration_transform",
        "params": {"calibration_id": str(active_cal.calibration_id)},
    }
    angle_step = {"step": "angular_reference", "params": angle_params}
    unwrap_step = {"step": "angular_unwrap", "params": {"discont": pi}}
    cal_ref = active_cal.calibration_id

    theta_frames, theta_values = dense_to_sparse_scalar_records(frames, theta)
    smooth_frames, smooth_values = dense_to_sparse_scalar_records(frames, smooth_theta)
    omega_frames, omega_values = dense_to_sparse_scalar_records(frames, omega)
    alpha_frames, alpha_values = dense_to_sparse_scalar_records(frames, alpha)

    common_pipeline = (cal_step, angle_step)

    d_theta = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="angular_position",
        input=derived_input,
        pipeline=common_pipeline,
        frames=theta_frames,
        values=theta_values,
        payload_ref=None,
        unit="rad",
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    d_smooth = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="smoothed_angular_position",
        input=derived_input,
        pipeline=(*common_pipeline, unwrap_step,
                  smoothing_step("smoothed_angular_position", window_length, polyorder, timeline.fps_nominal)),
        frames=smooth_frames,
        values=smooth_values,
        payload_ref=None,
        unit="rad",
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    d_omega = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="angular_velocity",
        input=derived_input,
        pipeline=(*common_pipeline, unwrap_step,
                  smoothing_step("angular_velocity", window_length, polyorder, timeline.fps_nominal)),
        frames=omega_frames,
        values=omega_values,
        payload_ref=None,
        unit=derive_unit("rad", 1),
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    d_alpha = DerivedData(
        derived_id=uuid4(),
        track_id=track_id,
        kind="angular_acceleration",
        input=derived_input,
        pipeline=(*common_pipeline, unwrap_step,
                  smoothing_step("angular_acceleration", window_length, polyorder, timeline.fps_nominal)),
        frames=alpha_frames,
        values=alpha_values,
        payload_ref=None,
        unit=derive_unit("rad", 2),
        produced_by=produced_by,
        created_at=now,
        status="valid",
        calibration_ref=cal_ref,
    )

    new_items = (d_theta, d_smooth, d_omega, d_alpha)
    timing_context = timing_parameters(timeline, inputs.timing_detail)
    return tuple(replace(item, extra_fields={"timing_context": deepcopy(timing_context)})
                 for item in new_items)
