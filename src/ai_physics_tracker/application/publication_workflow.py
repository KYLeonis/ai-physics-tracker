"""论文线三工作区的事实投影；不读payload、不保存第二套工作流状态。"""

from dataclasses import replace

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.domain.pendulum import PendulumExperiment
from ai_physics_tracker.application.pendulum_setup import pendulum_setup_status
from ai_physics_tracker.application.workflow_projection import (
    ActionSpec, AnalysisFacts, TaskCard, WorkflowState, select_task_card,
)


def publication_analysis_facts(session: ProjectSession, experiment: PendulumExperiment) -> AnalysisFacts:
    """以实验tip与科学结果元数据判断；文件完整性仍由各结果读取器复核。"""
    setup = pendulum_setup_status(session.project, experiment)
    limits = []
    if setup.missing_for_analysis:
        limits.append("Setup missing: " + ", ".join(setup.missing_for_analysis))
    if not session.can_measure(experiment.video_id):
        limits.append("Timing not authorized — use the timing controls in Setup")
    if experiment.active_infer_run_id is None:
        limits.append("No adopted measurement — activate a reviewed candidate in Acquire")
    timeline = next(t for t in session.project.timelines if t.video_id == experiment.video_id)
    first, last = timeline.working_zone
    points = session.effective_points(experiment.roles.tip)
    count = sum(first <= p.frame_index <= last for p in points)
    total = last - first + 1
    if limits or not count:
        if not count:
            limits.append("No effective tip observations")
        return AnalysisFacts("not_computable", "Complete the prerequisites", tuple(limits), count, total)
    if count < total:
        limits.append(f"Tip observations: {count}/{total}; gaps remain missing")
    records = [r for r in session.project.scientific_results
               if r.experiment_id == experiment.experiment_id
               and r.kind in ("pendulum-core-analysis-v1", "pendulum-ode-fit-v1")]
    latest_by_kind = {}
    for record in sorted(records, key=lambda r: r.created_at):
        latest_by_kind[record.kind] = record
    current = [r for r in latest_by_kind.values() if r.freshness == "valid"
               and r.execution_status in ("success", "insufficient_data") and r.payload is not None]
    if any(r.execution_status == "insufficient_data" for r in current):
        limits.append("Saved kinematics is partial — some derivatives or energy are unavailable")
    if any(r.freshness == "stale" for r in latest_by_kind.values()):
        limits.append("Some saved results are stale — recompute their page before exporting")
    state = "latest" if current else "needs_update"
    if current and limits:
        state = "partial"
    return AnalysisFacts(state, "Saved scientific results; files verified when opened", tuple(limits), count, total)


def publication_task_card(session: ProjectSession, experiment: PendulumExperiment,
                          state: WorkflowState, workspace: str, *, activity: str = "") -> TaskCard:
    """现有执行入口的下一步提示；教师模型不经过训练前置。"""
    if activity:
        return TaskCard("blocked", "Current: task running", (activity, "Cancel preserves adopted observations and saved results."),
                        ActionSpec("cancel_task", "Cancel task"),
                        (ActionSpec("view_history", "Results & history"),))
    base = select_task_card(state)
    if workspace == "setup":
        gaps = pendulum_setup_status(session.project, experiment).missing_for_analysis
        if gaps:
            if gaps[0] == "tip_radius_reference":
                return TaskCard("setup", "Next: set the tip radius reference",
                                ("Select a reliable tip frame, then use 'Use current tip as radius reference' in Setup.",),
                                ActionSpec("view_setup", "Go to Setup"))
            return select_task_card(replace(state, joint=None))
        if not session.can_measure(experiment.video_id):
            return TaskCard("setup", "Next: authorize video timing",
                            ("Review the timing result in Setup. Near-CFR requires your explicit approval of average-FPS approximation.",),
                            ActionSpec("view_setup", "Review timing in Setup"))
        return TaskCard("setup", "Current: experiment setup complete",
                        ("Next: acquire a tip trajectory using your own training or an imported teacher model.",),
                        ActionSpec("view_acquire", "Acquire trajectory"))
    if workspace == "analysis":
        if state.analysis.state == "not_computable":
            return TaskCard("setup", "Next: complete analysis prerequisites", state.analysis.limitations,
                            ActionSpec("view_setup" if pendulum_setup_status(session.project, experiment).missing_for_analysis
                                       or not session.can_measure(experiment.video_id) else "view_acquire", "Complete prerequisites"))
        return TaskCard("analyze", "Current: tip + fixed-pivot analysis",
                        ("Kinematics computes θ / ω / phase / reference energy; ODE fitting uses raw θ. Auxiliary landmarks do not gate either.",
                         "Saved results retain their own settings; recompute the relevant page after changing inputs."),
                        ActionSpec("compute_pendulum", "Compute / update kinematics"),
                        (ActionSpec("view_acquire", "Correct tip observations"),))
    attempts = [r for r in session.tracking_runs()
                if r.config.get("experiment_id") == str(experiment.experiment_id)]
    last_attempt = max(attempts, key=lambda r: r.created_at, default=None)
    if last_attempt is not None and last_attempt.status in ("failed", "cancelled"):
        return TaskCard("blocked", f"Current: last {last_attempt.task_type} {last_attempt.status}",
                        ("Adopted observations and manual corrections are preserved. Open history for the error/log, then retry.",),
                        ActionSpec("run_joint_training" if last_attempt.task_type == "train" else "run_joint_inference", "Retry task"),
                        (ActionSpec("view_history", "Results & history"), ActionSpec("view_analysis", "View saved analysis")))
    if state.joint and (state.joint.candidate_run_id or state.joint.active_run_id or state.joint.pending_run_id):
        return replace(base, secondary=base.secondary + (ActionSpec("import_teacher", "Import teacher model…"),))
    models = [m for m in session.project.model_references if m.compatibility_state in ("compatible", "unverified")]
    secondary = tuple(a for a in base.secondary if a.action_id != "run_joint_inference")
    if models:
        primary = ActionSpec("run_joint_inference", "Choose model · verify & run inference")
        secondary = (ActionSpec("guided_marking", "Label frames for my own training"), *secondary)
    else:
        primary = base.primary
    return replace(base, primary=primary, secondary=(ActionSpec("import_teacher", "Import teacher model…"), *secondary)[:5],
                   explanation=("Two paths: label representative frames and train your own model, or import a teacher model and verify it before inference.",
                                *base.explanation))
