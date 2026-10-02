"""论文线三工作区的事实投影；不读payload、不保存第二套工作流状态。"""

from dataclasses import replace

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.annotation_join import canonical_label_digest, join_complete_frames
from ai_physics_tracker.domain.pendulum import PendulumExperiment
from ai_physics_tracker.application.pendulum_setup import pendulum_setup_status
from ai_physics_tracker.application.workflow_projection import (
    ActionSpec, AnalysisFacts, TaskCard, WorkflowState, select_task_card,
)

INITIAL_LANDMARK_FRAME_COUNT = 20


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
               and r.execution_status in ("success", "insufficient_data", "nonconverged") and r.payload is not None]
    if any(r.execution_status == "insufficient_data" for r in current):
        limits.append("Saved kinematics is partial — some derivatives or energy are unavailable")
    for record in latest_by_kind.values():
        if record.execution_status in ("nonconverged", "failed", "cancelled"):
            limits.append(f"Latest saved {record.kind}: {record.execution_status}; inspect its diagnostics before interpreting")
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
            if gaps == ("tip_radius_reference",):
                if not session.effective_points(experiment.roles.tip):
                    return TaskCard("setup", "Next: acquire a reliable tip point",
                                    ("Label a tip in Acquire, or infer and adopt a teacher-model candidate; then return to Setup to set the radius reference.",),
                                    ActionSpec("view_acquire", "Acquire tip observations"))
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
                        (ActionSpec("export_scientific", "Export scientific results…"),
                         ActionSpec("view_acquire", "Correct tip observations")))
    # 六个既有按钮承载恒定循环；步骤由标签digest/run身份派生，不另存流程状态。
    joined = join_complete_frames(session.project, experiment)
    attempts = sorted((r for r in session.tracking_runs() if r.experiment_id == experiment.experiment_id),
                      key=lambda r: r.created_at)
    train = next((r for r in reversed(attempts) if r.task_type == "train" and r.status == "completed"), None)
    infer = next((r for r in reversed(attempts) if r.task_type == "infer" and r.status == "completed"), None)
    models = [m for m in session.project.model_references if m.compatibility_state in ("compatible", "unverified")]
    blocked = "Save the project first" if session.project_root is None else (
        "Authorize video timing in Setup first" if not session.can_measure(experiment.video_id) else None)
    has_frames = bool(experiment.frame_set and experiment.frame_set.frames)
    train_reason = blocked or ("Label at least two complete four-point frames first" if len(joined.complete) < 2 else None)
    steps = (
        ActionSpec("pick_landmark_frames", f"1 · Recommend {INITIAL_LANDMARK_FRAME_COUNT} frames", not blocked, blocked),
        ActionSpec("guided_marking", "2 · Label recommended frames", has_frames and not blocked,
                   blocked or (None if has_frames else "Recommend frames first")),
        ActionSpec("train_current_labels", "3 · Train / retrain with current labels", not train_reason, train_reason),
        ActionSpec("run_joint_inference", "4 · Verify & run inference", bool(models) and not blocked,
                   blocked or (None if models else "Train or import a teacher model first")),
        ActionSpec("review_joint_candidate", "5 · Mine difficult frames / choose a batch", infer is not None and not blocked,
                   blocked or (None if infer else "Run inference first")),
    )
    changed = train is not None and train.config.get("label_digest") != canonical_label_digest(joined)
    trained_models = {str(m.model_id) for m in models if train is not None and m.source_train_run_id == train.run_id}
    needs_inference = train is not None and (infer is None or infer.config.get("model_id") not in trained_models)
    if changed:
        index = 2 if len(joined.complete) >= 2 else 1
    elif needs_inference:
        index = 3
    elif infer is not None:
        index = 4
    elif has_frames:
        index = 1 if state.frame_set and state.frame_set.next_frame is not None else 2
    elif models and not joined.complete:
        index = 3
    else:
        index = 0
    primary = steps[index]
    last = attempts[-1] if attempts else None
    if last is not None and last.status in ("failed", "cancelled"):
        index = 2 if last.task_type == "train" else 3
        primary = replace(steps[index], label=f"Retry {last.task_type} · {steps[index].label}")
        extra = ActionSpec("view_history", "Results & history")
    elif state.joint and state.joint.candidate_run_id:
        extra = ActionSpec("replace_experiment" if state.joint.active_run_id else "activate_experiment",
                           "Use candidate for analysis")
    elif experiment.active_infer_run_id:
        extra = ActionSpec("view_analysis", "View current analysis")
    else:
        extra = ActionSpec("import_teacher", "Import teacher model…")
    progress = state.frame_set
    explanation = (
        "Recommend → label four points per frame → train → infer → choose a small difficult-frame batch → relabel → retrain.",
        f"Complete four-point labels: {len(joined.complete)}. " +
        (f"Recommended set: {progress.done}/{progress.total} complete. " if progress else "No recommended frame set yet. ") +
        ("Labels changed since training; retrain to use them." if changed else "Choose how many frames to relabel each round."),
        train_reason or "Training confirms the fixed-check split when needed, then continues. Imported teachers can also run directly at step 4.",
    )
    if last is not None and last.status in ("failed", "cancelled"):
        explanation += (f"Last {last.task_type}: {last.status}. Adopted measurements stay; see Results & history for details.",)
    return TaskCard("setup", f"Next: {primary.label}", explanation, primary,
                    tuple(step for step in steps if step.action_id != primary.action_id) + (extra,), base.evidence)
