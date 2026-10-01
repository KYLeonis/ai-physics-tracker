"""应用层：已验证fit的只读诊断与教学快照，不创建或修改科学结果。"""

from concurrent.futures import CancelledError
from dataclasses import dataclass, replace
from threading import Event
from uuid import UUID

import numpy as np

from ai_physics_tracker.application.pendulum_fit import load_fit_result, validated_fit_inputs
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.angular_analysis import analyze_angular_series
from ai_physics_tracker.domain.pendulum_criticism import PendulumCriticism, criticize_pendulum_fits
from ai_physics_tracker.domain.pendulum_identifiability import (
    IdentifiabilityCurve, IdentifiabilityObjectiveNode, IdentifiabilityState,
    ForwardEquivalence, RawParameterBounds, RawParameters, compare_equivalent_forwards,
    evaluate_objective_at_q, illustrative_raw_reference, lump_parameters, simulate_raw_pendulum,
)
from ai_physics_tracker.domain.pendulum_ode import M0, M1, IntegrationSettings, ObjectiveRequest, PendulumParameters
from ai_physics_tracker.domain.scientific_result import ScientificResult

OVERLAP_SETTINGS = IntegrationSettings(1e-10, 1e-12)


def check_exploration_cancel(cancel: Event) -> None:
    if cancel.is_set():
        raise CancelledError()


@dataclass(frozen=True)
class FitExploration:
    """绑定一个保存fit的Qt-free教学状态；只读，不冒充新的fit。"""
    result_id: UUID
    request: ObjectiveRequest
    criticism: PendulumCriticism
    model: str | None
    parameters: PendulumParameters | None


def read_fit_exploration(session: ProjectSession, record: ScientificResult, cancel: Event) -> FitExploration:
    check_exploration_cancel(cancel)
    payload, current, reason = load_fit_result(session, record)
    if not current:
        raise ProjectSessionError(reason or "fit is stale — recompute")
    request, fits = validated_fit_inputs(payload, record)
    check_exploration_cancel(cancel)
    angular = analyze_angular_series(request.series, profile_id=request.profile_id,
                                     end_frame_index=request.end_frame_index)
    criticism = criticize_pendulum_fits(request, fits.get(M0), fits.get(M1), angular)
    selected = next((fits[m] for m in (M1, M0) if m in fits and fits[m].status == "success"), None)
    check_exploration_cancel(cancel)
    return FitExploration(record.result_id, request, criticism,
                          None if selected is None else selected.model,
                          None if selected is None else selected.parameters)


def teaching_bounds(parameters: PendulumParameters) -> RawParameterBounds:
    """采用冻结曲面的教学范围；它不是实验测得的raw范围。"""
    return RawParameterBounds((0., .12), (0., max(.6, 1.12*parameters.alpha1_s_inv)),
        (0., max(.6, 1.12*parameters.alpha2_rad_inv)), (.01, 1.5*parameters.omega2_s_inv2))


@dataclass(frozen=True)
class TeachingPreview:
    state: IdentifiabilityState
    displayed_raw: RawParameters
    displayed_lumped: PendulumParameters
    forwards: ForwardEquivalence
    node: IdentifiabilityObjectiveNode
    non_equivalent_control: bool


def preview_equivalence(source: FitExploration, lambda_scale: float, non_equivalent: bool,
                        curve: IdentifiabilityCurve | None, cancel: Event) -> TeachingPreview:
    if source.parameters is None:
        raise ProjectSessionError("parameter exploration needs a converged fit")
    check = lambda: check_exploration_cancel(cancel)
    check()
    reference = illustrative_raw_reference(source.parameters)
    bounds = teaching_bounds(source.parameters)
    state = IdentifiabilityState(reference, lambda_scale, bounds)
    # 教学forward从release IC开始；展示最长25s，不用压缩的有效帧序号生成时间。
    end_s = min(25., max(t for f, t in zip(source.request.series.frame_indices,
        source.request.series.time_release_relative_s) if f <= source.request.end_frame_index))
    times = tuple(map(float, np.linspace(0., end_s, 501)))
    forwards = compare_equivalent_forwards(reference, lambda_scale, source.request.initial_condition,
        times, OVERLAP_SETTINGS, bounds=bounds, check_cancel=check)
    raw = state.transformed_raw
    if non_equivalent:
        raw = replace(raw, omega0_sq_s_inv2=raw.omega0_sq_s_inv2*1.05)
        other = simulate_raw_pendulum(raw, source.request.initial_condition, times,
                                     OVERLAP_SETTINGS, check_cancel=check)
        difference = None if other.status != "success" or forwards.raw_reference.status != "success" else float(
            np.max(np.abs(np.asarray(other.theta_rad)-np.asarray(forwards.raw_reference.theta_rad))))
        forwards = replace(forwards, raw_transformed=other,
            raw_overlap_max_abs_difference_rad=difference, status="non_equivalent_control",
            reason="q increased by 5%; no equivalence claim")
    lumped = lump_parameters(raw)
    node = evaluate_objective_at_q(source.request, source.parameters, lumped.omega2_s_inv2,
        curve=curve, alpha_a=raw.alpha_a, omega0_sq_s_inv2=raw.omega0_sq_s_inv2, check_cancel=check)
    check()
    return TeachingPreview(state, raw, lumped, forwards, node, non_equivalent)
