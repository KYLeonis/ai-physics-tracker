"""Pendulum experiment 领域值对象；四 role 绑定、几何、物理参数与激活历史。

对应 publication 契约 §2（experiment-run-derived-contracts.md）。本模块只定义
事实与构造期不变量；跨对象引用（video/track/run 存在性）由
`domain.project.validate_project` 在聚合层校验。
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from math import isfinite
from uuid import UUID, uuid4

from ai_physics_tracker.domain.types import (
    JsonObject,
    canonical_json_digest,
    require_aware_datetime,
    utc_now,
)

ROLE_ORDER: tuple[str, ...] = ("tip", "body_top", "body_bottom", "pivot")
PENDULUM_MODE = "pendulum"
EXPERIMENT_CONTRACT_VERSION = 1
ACTIVATION_ACTIONS = frozenset({"activate", "replace", "clear"})


@dataclass(frozen=True)
class PendulumRoles:
    """恰好四个规范 role 到 Track UUID 的绑定；顺序固定为规范 role 顺序。"""

    tip: UUID
    body_top: UUID
    body_bottom: UUID
    pivot: UUID

    def __post_init__(self) -> None:
        if len({self.tip, self.body_top, self.body_bottom, self.pivot}) != len(ROLE_ORDER):
            raise ValueError("pendulum roles must bind four distinct tracks")

    def track_ids(self) -> tuple[UUID, ...]:
        """按规范 role 顺序返回成员 Track UUID。"""

        return (self.tip, self.body_top, self.body_bottom, self.pivot)

    def by_role(self) -> dict[str, UUID]:
        return dict(zip(ROLE_ORDER, self.track_ids(), strict=True))

    def track_id_for(self, role: str) -> UUID:
        roles = self.by_role()
        if role not in roles:
            raise ValueError(f"unknown pendulum role: {role}")
        return roles[role]


def vertical_endpoint_digest(
    top_px: tuple[float, float], bottom_px: tuple[float, float]
) -> str:
    """true vertical 端点的 canonical digest；确认状态与端点绑定的依据。"""

    return canonical_json_digest(
        {"bottom_px": list(bottom_px), "top_px": list(top_px)}
    )


@dataclass(frozen=True)
class TrueVertical:
    """用户按 top→bottom 顺序确认的重力向下方向（契约 §2）。

    `direction_confirmed` 表示用户已显式确认 top→bottom 即向下；确认绑定
    `confirmed_digest`，端点变化后必须重建对象（应用动作负责撤销确认），
    加载时由构造校验 digest 一致性，防篡改。
    """

    top_px: tuple[float, float]
    bottom_px: tuple[float, float]
    direction_confirmed: bool = False
    confirmed_digest: str | None = None

    def __post_init__(self) -> None:
        for name, point in (("top_px", self.top_px), ("bottom_px", self.bottom_px)):
            if len(point) != 2 or not all(isfinite(value) for value in point):
                raise ValueError(f"true vertical {name} must be two finite coordinates")
        if self.top_px == self.bottom_px:
            raise ValueError("true vertical endpoints must not coincide")
        if self.direction_confirmed:
            expected = vertical_endpoint_digest(self.top_px, self.bottom_px)
            if self.confirmed_digest != expected:
                raise ValueError(
                    "confirmed true vertical digest does not match its endpoints"
                )
        elif self.confirmed_digest is not None:
            raise ValueError("unconfirmed true vertical must not carry a digest")

    def confirmed(self) -> "TrueVertical":
        """返回带确认与当前端点 digest 的副本。"""

        return replace(
            self,
            direction_confirmed=True,
            confirmed_digest=vertical_endpoint_digest(self.top_px, self.bottom_px),
        )


@dataclass(frozen=True)
class PendulumGeometry:
    """实验固定几何事实；缺项明确为 None，允许分步保存（契约 §2）。"""

    fixed_pivot_px: tuple[float, float] | None = None
    true_vertical: TrueVertical | None = None
    tip_radius_reference_px: float | None = None

    def __post_init__(self) -> None:
        if self.fixed_pivot_px is not None and (
            len(self.fixed_pivot_px) != 2
            or not all(isfinite(value) for value in self.fixed_pivot_px)
        ):
            raise ValueError("fixed_pivot_px must be two finite coordinates")
        if self.tip_radius_reference_px is not None and (
            not isfinite(self.tip_radius_reference_px)
            or self.tip_radius_reference_px <= 0
        ):
            raise ValueError("tip_radius_reference_px must be a positive finite number")


@dataclass(frozen=True)
class PhysicalParameters:
    """物理参数：effective pivot-to-COM 长度与重力加速度，来源必须显式。"""

    length_m: float
    g_m_s2: float
    length_source: str
    g_source: str

    def __post_init__(self) -> None:
        if not isfinite(self.length_m) or self.length_m <= 0:
            raise ValueError("physical length_m must be a positive finite number")
        if not isfinite(self.g_m_s2) or self.g_m_s2 <= 0:
            raise ValueError("physical g_m_s2 must be a positive finite number")
        if not self.length_source.strip():
            raise ValueError("physical length_source provenance must not be blank")
        if not self.g_source.strip():
            raise ValueError("physical g_source provenance must not be blank")


@dataclass(frozen=True)
class ExperimentFrameSet:
    """experiment 级共享代表帧集（契约 §3：帧号与 selection provenance 只存一次）。

    frames 必须升序且唯一；帧界由聚合校验对照 video.frame_count。
    `source_video_sha256` 冻结选帧时的视频身份，内容变化即作废重选依据。
    """

    frames: tuple[int, ...]
    algorithm: str
    created_at: datetime
    seed: int | None = None
    working_zone: tuple[int, int] | None = None
    source_video_sha256: str | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("experiment frame set must not be empty")
        if any(frame < 0 for frame in self.frames):
            raise ValueError("frame indices must be non-negative")
        if len(set(self.frames)) != len(self.frames):
            raise ValueError("experiment frame set must not contain duplicates")
        if list(self.frames) != sorted(self.frames):
            raise ValueError("experiment frame set must be ordered by frame index")
        if not self.algorithm.strip():
            raise ValueError("frame set algorithm provenance must not be blank")
        require_aware_datetime(self.created_at, "created_at")
        if self.working_zone is not None:
            if len(self.working_zone) != 2:
                raise ValueError("working_zone must contain two frame indices")
            # 对齐 Timeline 先例:拒绝负起点与逆序区间
            if self.working_zone[0] < 0 or self.working_zone[1] < self.working_zone[0]:
                raise ValueError(
                    "working_zone must be a non-empty ascending frame range"
                )


@dataclass(frozen=True)
class ExperimentFixedCheck:
    """experiment 级固定检查帧集（契约 §3：四 role 共同进 test/共同排除）。

    `label_digest` 冻结 freeze 时的 canonical 标签 digest（S2）；任一 role
    的点改动都会使当前 digest 偏离 → invalid，需 renew（重新冻结）。
    """

    frames: tuple[int, ...]
    label_digest: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("fixed check set must not be empty")
        if len(set(self.frames)) != len(self.frames):
            raise ValueError("fixed check frames must be unique")
        if list(self.frames) != sorted(self.frames):
            raise ValueError("fixed check frames must be ordered by frame index")
        if len(self.label_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.label_digest
        ):
            raise ValueError("fixed check label_digest must be a sha256 hex digest")
        require_aware_datetime(self.created_at, "created_at")


@dataclass(frozen=True)
class RoleBindingEditRecord:
    """一次 role 绑定编辑的不可变历史：完整 old/new 快照与编辑后 revision。

    创建 experiment 是首条记录（old_roles 为 None）。revision 记录编辑后的
    measurement_revision，供 result provenance 引用（契约 §2）。
    """

    record_id: UUID
    timestamp: datetime
    old_roles: PendulumRoles | None
    new_roles: PendulumRoles
    revision: int

    def __post_init__(self) -> None:
        require_aware_datetime(self.timestamp, "timestamp")
        if self.revision < 0:
            raise ValueError("binding edit revision must be non-negative")


@dataclass(frozen=True)
class RoleAdoptionCount:
    """activation 历史中单个 role 的采用/保留 manual 计数。"""

    role: str
    adopted_count: int
    manual_preserved_count: int

    def __post_init__(self) -> None:
        if self.role not in ROLE_ORDER:
            raise ValueError(f"unknown pendulum role: {self.role}")
        if self.adopted_count < 0 or self.manual_preserved_count < 0:
            raise ValueError("role adoption counts must be non-negative")


@dataclass(frozen=True)
class ExperimentActivationRecord:
    """一次四轨 Activate/Replace/Clear 事务的不可变记录（契约 §2/§5）。

    P1.1 只定义 schema 与不变量；记录由 P1.4 的 activation 事务产生。
    """

    record_id: UUID
    timestamp: datetime
    action: str
    from_run_id: UUID | None
    to_run_id: UUID | None
    role_counts: tuple[RoleAdoptionCount, ...]
    input_digest: str

    def __post_init__(self) -> None:
        require_aware_datetime(self.timestamp, "timestamp")
        if self.action not in ACTIVATION_ACTIONS:
            raise ValueError(f"unknown activation action: {self.action}")
        if self.action == "clear" and self.to_run_id is not None:
            raise ValueError("clear activation must not set a to_run_id")
        if self.action in {"activate", "replace"} and self.to_run_id is None:
            raise ValueError(f"{self.action} activation requires a to_run_id")
        if len({count.role for count in self.role_counts}) != len(self.role_counts):
            raise ValueError("activation role counts must not repeat a role")
        if len(self.input_digest) != 64:
            raise ValueError("activation input_digest must be a sha256 hex digest")


@dataclass(frozen=True)
class PendulumExperiment:
    """单摆实验聚合事实：role 身份、几何、物理参数、release 与激活状态。

    scale 不在本对象上：来源是 `Project.active_calibration_by_video`，运行时
    解析快照（契约 §2 scale_binding）。`measurement_revision` 单调递增，由
    应用层事务维护；创建即提交首条绑定历史，revision 从 1 开始。
    """

    experiment_id: UUID
    video_id: UUID
    roles: PendulumRoles
    created_at: datetime
    measurement_revision: int = 1
    geometry: PendulumGeometry = field(default_factory=PendulumGeometry)
    physical: PhysicalParameters | None = None
    release_frame_index: int | None = None
    frame_set: ExperimentFrameSet | None = None
    fixed_check: ExperimentFixedCheck | None = None
    active_infer_run_id: UUID | None = None
    activation_history: tuple[RoleBindingEditRecord | ExperimentActivationRecord, ...] = ()
    mode: str = PENDULUM_MODE
    contract_version: int = EXPERIMENT_CONTRACT_VERSION
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.mode != PENDULUM_MODE:
            raise ValueError(f"unsupported experiment mode: {self.mode}")
        if self.contract_version != EXPERIMENT_CONTRACT_VERSION:
            raise ValueError(
                f"unsupported experiment contract_version: {self.contract_version}"
            )
        require_aware_datetime(self.created_at, "created_at")
        if self.measurement_revision < 0:
            raise ValueError("measurement_revision must be non-negative")
        if self.release_frame_index is not None and self.release_frame_index < 0:
            raise ValueError("release_frame_index must be non-negative")
        record_ids = [record.record_id for record in self.activation_history]
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("activation history record ids must be unique")

    def binding_history(self) -> tuple[RoleBindingEditRecord, ...]:
        return tuple(
            record
            for record in self.activation_history
            if isinstance(record, RoleBindingEditRecord)
        )


def create_pendulum_experiment(
    experiment_id: UUID,
    video_id: UUID,
    roles: PendulumRoles,
) -> PendulumExperiment:
    """创建初始 experiment：首条绑定历史 + revision 1。"""

    now = utc_now()
    return PendulumExperiment(
        experiment_id=experiment_id,
        video_id=video_id,
        roles=roles,
        created_at=now,
        measurement_revision=1,
        activation_history=(
            RoleBindingEditRecord(
                record_id=uuid4(),
                timestamp=now,
                old_roles=None,
                new_roles=roles,
                revision=1,
            ),
        ),
    )
