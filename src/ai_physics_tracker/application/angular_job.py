"""应用层角运动批次：独立快照计算，输入（含参考轨迹）未变化时才允许原子提交。

事务骨架复用 kinematics_job 的 AnalysisInputs / detached 快照 / validated_batch
（ADR-0019 第 5 节）；批次期望集为 ANGULAR_KINDS × 目标轨迹。
"""

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import dataclass, replace
from threading import Event
from uuid import UUID

from ai_physics_tracker.application.kinematics_job import (
    AnalysisInputs,
    SmoothingParameters,
    analysis_inputs,
    validated_batch,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.angular import AngularReference, TwoPointReference
from ai_physics_tracker.domain.derived import ANGULAR_KINDS, DerivedData


@dataclass(frozen=True)
class AngularSpec:
    """一条角运动计算规格：目标轨迹（单摆摆球 / 两点方向 A）+ 角度参考。"""

    track_id: UUID
    reference: AngularReference


@dataclass(frozen=True)
class AngularJob:
    """snapshot 在创建后移交 worker 独占，GUI 只读取 inputs/parameters/specs。"""

    snapshot: ProjectSession
    inputs: AnalysisInputs
    parameters: SmoothingParameters
    specs: tuple[AngularSpec, ...]


@dataclass(frozen=True)
class AngularResult:
    inputs: AnalysisInputs
    specs: tuple[AngularSpec, ...]
    records: tuple[DerivedData, ...]


def _reference_track_id(reference: AngularReference) -> UUID | None:
    return (
        reference.reference_track_id
        if isinstance(reference, TwoPointReference)
        else None
    )


def _job_track_ids(specs: tuple[AngularSpec, ...]) -> tuple[UUID, ...]:
    """目标轨迹在前、其参考轨迹紧随其后；去重保序，作为输入快照的确定性顺序。"""

    ordered: list[UUID] = []
    for spec in specs:
        for track_id in (spec.track_id, _reference_track_id(spec.reference)):
            if track_id is not None and track_id not in ordered:
                ordered.append(track_id)
    return tuple(ordered)


def prepare_angular_job(
    session: ProjectSession,
    video_id: UUID,
    specs: tuple[AngularSpec, ...],
    parameters: SmoothingParameters,
) -> AngularJob:
    """构造角运动批次快照；校验时序授权、同视频与目标轨迹不重复。"""

    if not specs:
        raise ProjectSessionError("Select at least one angular spec")
    target_ids = [spec.track_id for spec in specs]
    if len(set(target_ids)) != len(target_ids):
        raise ProjectSessionError("Angular specs must target distinct tracks")
    for spec in specs:
        if _reference_track_id(spec.reference) == spec.track_id:
            raise ProjectSessionError(
                "angular two-point reference must differ from the target track"
            )
    snapshot = session.detached()
    # R1 首版要求有效标定；在 prepare 阶段 fail fast，避免多规格批次
    # 在 worker 内逐规格计算后才失败。
    video_ids = {spec_track.video_id for spec_track in snapshot.tracks
                 if spec_track.track_id in _job_track_ids(specs)}
    if any(snapshot.active_calibration(video_id) is None for video_id in video_ids):
        raise ProjectSessionError(
            "angular analysis requires an active calibration (phase6 R1)"
        )
    return AngularJob(
        snapshot,
        analysis_inputs(snapshot, video_id, _job_track_ids(specs)),
        parameters,
        tuple(specs),
    )


def run_angular_job(job: AngularJob, cancel: Event) -> AngularResult:
    """不写活动会话或文件；在各规格间检查取消，失败不会产生部分提交。"""

    records: list[DerivedData] = []
    for spec in job.specs:
        if cancel.is_set():
            raise CancelledError()
        computed = job.snapshot.compute_angular(
            spec.track_id,
            reference=spec.reference,
            window_length=job.parameters.window_length,
            polyorder=job.parameters.polyorder,
        )
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
    return AngularResult(job.inputs, job.specs, tuple(records))


def validated_angular(
    session: ProjectSession, result: AngularResult
) -> tuple[DerivedData, ...]:
    """重算提交前复核原输入（含参考轨迹），保留非目标结果及未知扩展字段。"""

    expected = {
        (spec.track_id, kind) for spec in result.specs for kind in ANGULAR_KINDS
    }
    return validated_batch(session, result.inputs, result.records, expected)
