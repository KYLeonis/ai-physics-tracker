"""Pendulum setup 完整性投影与依赖 digest（P1.1-S3，Qt-free）。

状态是从 Project/Experiment 事实重建的投影，不落库、不形成第二套
workflow 真值（契约 §2/§6）。digest 覆盖解析后的 scale calibration
全部值、几何、物理、release 与 role 绑定；显示类变化不进入 digest。
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.pendulum import PendulumExperiment
from ai_physics_tracker.domain.project import Project
from ai_physics_tracker.domain.types import canonical_json_digest


@dataclass(frozen=True)
class PendulumSetupStatus:
    """setup 完整性投影：每项缺口显式呈现，不用 0 冒充缺失。"""

    experiment_id: UUID
    video_id: UUID
    scale_calibration_id: UUID | None
    fixed_pivot_set: bool
    true_vertical_present: bool
    true_vertical_confirmed: bool
    physical_set: bool
    release_set: bool

    @property
    def geometry_complete(self) -> bool:
        """分析所需几何：固定 pivot + 已确认的 true vertical。"""

        return self.fixed_pivot_set and self.true_vertical_confirmed

    @property
    def can_annotate(self) -> bool:
        """P1.2 标注门槛：experiment 存在即成立（frames gate 属 P1.2）。"""

        return True

    @property
    def can_analyze(self) -> bool:
        """P2 分析门槛：几何 + 标定 + 物理 + release 全部就绪。"""

        return (
            self.geometry_complete
            and self.scale_calibration_id is not None
            and self.physical_set
            and self.release_set
        )

    @property
    def missing_for_analysis(self) -> tuple[str, ...]:
        """按固定顺序列出阻塞 P2 分析的缺口（任务卡/清单复用）。"""

        gaps: list[str] = []
        if not self.fixed_pivot_set:
            gaps.append("fixed_pivot")
        if not self.true_vertical_present:
            gaps.append("true_vertical")
        elif not self.true_vertical_confirmed:
            gaps.append("true_vertical_confirmation")
        if self.scale_calibration_id is None:
            gaps.append("active_calibration")
        if not self.physical_set:
            gaps.append("physical_parameters")
        if not self.release_set:
            gaps.append("release_frame")
        return tuple(gaps)


def resolve_scale_calibration(
    project: Project, experiment: PendulumExperiment
) -> Calibration | None:
    """解析 experiment 的 scale 来源：既有 active_calibration_by_video。

    删除 active calibration 解析为 None（契约 §2），绝不静默选择另一个。
    """

    calibration_id = project.active_calibration_by_video.get(experiment.video_id)
    if calibration_id is None:
        return None
    return next(
        (
            item
            for item in project.calibrations
            if item.calibration_id == calibration_id
        ),
        None,
    )


def pendulum_setup_status(
    project: Project, experiment: PendulumExperiment
) -> PendulumSetupStatus:
    """从当前事实重建 setup 状态；缺测显式为 False/None。"""

    calibration = resolve_scale_calibration(project, experiment)
    vertical = experiment.geometry.true_vertical
    return PendulumSetupStatus(
        experiment_id=experiment.experiment_id,
        video_id=experiment.video_id,
        scale_calibration_id=calibration.calibration_id if calibration else None,
        fixed_pivot_set=experiment.geometry.fixed_pivot_px is not None,
        true_vertical_present=vertical is not None,
        true_vertical_confirmed=vertical is not None and vertical.direction_confirmed,
        physical_set=experiment.physical is not None,
        release_set=experiment.release_frame_index is not None,
    )


def _calibration_digest_payload(calibration: Calibration | None) -> dict[str, Any]:
    if calibration is None:
        return {"calibration": None}
    return {
        "calibration": {
            "calibration_id": str(calibration.calibration_id),
            "scale_end_1_px": list(calibration.scale_end_1_px),
            "scale_end_2_px": list(calibration.scale_end_2_px),
            "known_length": calibration.known_length,
            "unit": calibration.unit,
            "origin_px": list(calibration.origin_px)
            if calibration.origin_px is not None
            else None,
            "rotation_deg": calibration.rotation_deg,
        }
    }


def experiment_dependency_digest(
    project: Project, experiment: PendulumExperiment
) -> str:
    """experiment 输入的 canonical 依赖 digest（契约 §6 首版保守集合）。

    包含：video 帧数/时间基准、四 role 绑定、解析后的 active calibration
    全量值、几何、物理、release 与 measurement_revision。显示类状态
    （颜色/缩放/单位换算偏好）不进入 digest。
    """

    video = next(
        (item for item in project.videos if item.video_id == experiment.video_id),
        None,
    )
    timeline = next(
        (item for item in project.timelines if item.video_id == experiment.video_id),
        None,
    )
    vertical = experiment.geometry.true_vertical
    payload: dict[str, Any] = {
        "video": {
            "video_id": str(experiment.video_id),
            "frame_count": video.frame_count if video else None,
            "height_px": video.height_px if video else None,
            "fps_nominal": timeline.fps_nominal if timeline else None,
        },
        "roles": {
            role: str(member)
            for role, member in experiment.roles.by_role().items()
        },
        "geometry": {
            "fixed_pivot_px": list(experiment.geometry.fixed_pivot_px)
            if experiment.geometry.fixed_pivot_px is not None
            else None,
            "true_vertical": None
            if vertical is None
            else {
                "top_px": list(vertical.top_px),
                "bottom_px": list(vertical.bottom_px),
                "direction_confirmed": vertical.direction_confirmed,
            },
            "tip_radius_reference_px": experiment.geometry.tip_radius_reference_px,
        },
        "physical": None
        if experiment.physical is None
        else {
            "length_m": experiment.physical.length_m,
            "g_m_s2": experiment.physical.g_m_s2,
            "length_source": experiment.physical.length_source,
            "g_source": experiment.physical.g_source,
        },
        "release_frame_index": experiment.release_frame_index,
        "measurement_revision": experiment.measurement_revision,
    }
    payload.update(_calibration_digest_payload(resolve_scale_calibration(project, experiment)))
    return canonical_json_digest(payload)
