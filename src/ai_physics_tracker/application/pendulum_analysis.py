"""应用层：在 adopted snapshot 消费入口复核身份，再交给 Qt-free 数值核心。"""

from typing import cast

from ai_physics_tracker.application.adopted_measurement import (
    AdoptedMeasurementSnapshot, assert_adopted_measurement_current,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.pendulum import QCExclusion, ROLE_ORDER
from ai_physics_tracker.domain.pendulum_reconstruction import (
    AdoptedLandmark, MeasurementFrame, ReconstructionInput, PendulumReconstruction,
)
from ai_physics_tracker.domain.angular_analysis import AngularSeries
from ai_physics_tracker.infrastructure.publication_serializer import geometry_from_payload


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
