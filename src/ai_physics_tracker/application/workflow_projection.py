"""Phase 5.7 — 工作流状态投影：把既有项目事实派生为 UI 状态（Qt-free）。

设计（docs/design/phase-5.7-interaction-redesign.md §9/§10/§11）：
- 不持久化第二套 workflow 状态；本模块全部输出都是对 Project / TrackingRun /
  review state / active result / DerivedData 的**可重建投影**。
- 三个正交维度：执行（谁在工作）、轨迹（当前输入与候选）、分析（可计算性）。
- 任务卡按固定优先级选择主动作；分析可用性独立计算，不被较新的候选/失败覆盖。

GUI 侧的瞬时事实（哪个任务在跑、取消中）由调用方作为显式输入传入；
本模块不接触 Qt、不修改会话、不读文件。
"""

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.domain.tracking_run import TrackingRun

# --- 执行维度（GUI 瞬时事实，由调用方声明）---

EXEC_IDLE = "idle"
EXEC_FRAME_SELECTION = "frame_selection"
EXEC_TRAINING = "training"
EXEC_INFERRING = "inferring"
EXEC_MINING = "mining"
EXEC_CANCELLING = "cancelling"

# --- 任务卡 mode（呈现层枚举，不持久化）---

MODE_SETUP = "setup"
MODE_ANNOTATE = "annotate"
MODE_LEARNING = "learning"
MODE_LEARN_READY = "learn_ready"
MODE_GENERATING = "generating"
MODE_GENERATE_READY = "generate_ready"
MODE_INSPECT = "inspect"
MODE_REVIEWING = "reviewing"
MODE_ADOPT = "adopt"
MODE_OPTIMIZE = "optimize"
MODE_ANALYZE = "analyze"
MODE_BLOCKED = "blocked"

# --- 主动作 id（GUI 据此路由到既有执行入口）---

ACTION_ADD_VIDEO = "add_video"
ACTION_CREATE_TRACK = "create_track"
ACTION_SAVE_PROJECT = "save_project"
ACTION_PICK_FRAMES = "pick_frames"            # 挑选代表画面（显式启动选帧）
ACTION_LABEL_FRAME = "label_frame"            # 跳到待标/待审画面
ACTION_START_LEARNING = "start_learning"      # 开始学习（C2 显式执行推荐计划）
ACTION_GENERATE_TRAJECTORY = "generate_trajectory"
ACTION_INSPECT_TRAJECTORY = "inspect_trajectory"
ACTION_ADOPT_TRAJECTORY = "adopt_trajectory"
ACTION_CONTINUE_OPTIMIZING = "continue_optimizing"
ACTION_VIEW_ANALYSIS = "view_analysis"
ACTION_UPDATE_CHARTS = "update_charts"
ACTION_CANCEL_TASK = "cancel_task"
ACTION_RETRY_LEARNING = "retry_learning"

# --- 分析可用性四态（设计 §11.1）---

ANALYSIS_NOT_COMPUTABLE = "not_computable"
ANALYSIS_PARTIAL = "partial"
ANALYSIS_NEEDS_UPDATE = "needs_update"
ANALYSIS_LATEST = "latest"

_MIN_LABELS_FOR_TRAINING = 3


@dataclass(frozen=True)
class ExecutionInput:
    """GUI 声明的瞬时执行事实；默认一切空闲。"""

    kind: str = EXEC_IDLE
    frame_selection: bool = False
    mining: bool = False
    cancelling: bool = False

    @property
    def busy(self) -> bool:
        return self.kind != EXEC_IDLE


@dataclass(frozen=True)
class CandidateFacts:
    """一条尚未采用的 completed 推理候选（普通模式只关注最新一条）。"""

    run_id: UUID
    version: int                          # 完成顺序的稳定版本号（第 N 版）
    pending_review: int = 0
    has_review_batch: bool = False
    reviewed_count: int = 0
    corrected_count: int = 0
    skipped_count: int = 0
    accepted_count: int = 0

    @property
    def label(self) -> str:
        return f"version {self.version}"


@dataclass(frozen=True)
class TrajectoryFacts:
    """当前输入与候选的分离事实（设计 §9 轨迹维度）。"""

    manual_count: int = 0
    active_status: str = "none"           # session.get_track_activation_status 的状态
    active_run_id: UUID | None = None
    active_version: int | None = None     # 第 N 版；manual-only/none 为 None
    active_pending_review: int = 0
    candidate: CandidateFacts | None = None

    @property
    def has_active_result(self) -> bool:
        return self.active_status in ("active", "legacy_inferred", "legacy_mixed")

    @property
    def has_effective_input(self) -> bool:
        return self.manual_count > 0 or self.has_active_result

    @property
    def active_label(self) -> str | None:
        return f"version {self.active_version}" if self.active_version else None


@dataclass(frozen=True)
class AnalysisFacts:
    """分析可用性（设计 §11）；限制（缺测/待审）在任何状态都保留。"""

    state: str
    reason: str | None = None
    limitations: tuple[str, ...] = ()
    effective_frames: int = 0
    zone_frames: int = 0


@dataclass(frozen=True)
class WorkflowState:
    """三维修量投影 + 组装卡片/状态头所需的全部摘要。"""

    execution: ExecutionInput
    trajectory: TrajectoryFacts
    analysis: AnalysisFacts
    prerequisites: tuple[str, ...] = ()   # 阻塞 AI 流程的缺失前置
    fixed_check_frames: int = 0           # 当前活动检查帧数（0 = 无活动集合）
    fixed_check_valid: bool = False
    failed_run_id: UUID | None = None     # 最近一次相关训练失败（恢复卡用）
    completed_train_count: int = 0
    completed_infer_count: int = 0
    learned_not_generated: bool = False   # 最新完成训练晚于最新完成推理
    new_labels_since_last_train: int = 0
    candidate_comparison: "ComparisonFacts | None" = None


@dataclass(frozen=True)
class ActionSpec:
    """卡片动作：id + 用户语言标签 + 禁用原因（禁用必须邻接显示原因）。"""

    action_id: str
    label: str
    enabled: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class TaskCard:
    """上下文任务卡的全部内容；由 select_task_card 从 WorkflowState 派生。"""

    mode: str
    title: str                                   # “当前：检查轨迹”
    explanation: tuple[str, ...] = ()
    primary: ActionSpec | None = None
    secondary: tuple[ActionSpec, ...] = ()
    evidence: tuple[str, ...] = ()               # “依据与本次设置”内容


# ---------------------------------------------------------------------------
# 事实采集（纯读取）
# ---------------------------------------------------------------------------


def _review_summary(session: ProjectSession, run_id: UUID):
    """run 的审核批次摘要；无批次时返回零计数摘要（不抛错）。"""
    return session.get_review_summary(run_id)


def _active_pending_review(session: ProjectSession, track_id: UUID) -> int:
    """当前采用结果对应审核队列的未审数（不混入候选队列）。"""
    try:
        _status, active_run_id, _ = session.get_track_activation_status(track_id)
    except Exception:
        return 0
    if active_run_id is None:
        return 0
    return _review_summary(session, active_run_id).pending_count


def _completed_of(
    runs: Sequence[TrackingRun], track_id: UUID, task_type: str
) -> list[TrackingRun]:
    """按完成顺序（created_at 稳定排序）返回某 track 的 completed run。"""
    return sorted(
        (r for r in runs
         if r.track_id == track_id and r.task_type == task_type
         and r.status == "completed"),
        key=lambda r: (r.created_at, r.run_id),
    )


def trajectory_facts(
    session: ProjectSession,
    track_id: UUID | None,
    runs: Sequence[TrackingRun],
) -> TrajectoryFacts:
    """从 manual 点、active pointer 与最新候选派生轨迹事实。"""
    if track_id is None:
        return TrajectoryFacts()
    manual_count = len(session.manual_points(track_id))
    try:
        status, active_run_id, _ = session.get_track_activation_status(track_id)
    except Exception:
        status, active_run_id = "none", None

    active_pending = 0
    active_version = None
    if active_run_id is not None:
        completed_infer = _completed_of(runs, track_id, "infer")
        for index, run in enumerate(completed_infer, start=1):
            if run.run_id == active_run_id:
                active_version = index
                break
        active_pending = _review_summary(session, active_run_id).pending_count

    candidate = None
    completed_infer = _completed_of(runs, track_id, "infer")
    if completed_infer:
        latest = completed_infer[-1]
        if active_run_id is None or latest.run_id != active_run_id:
            summary = _review_summary(session, latest.run_id)
            candidate = CandidateFacts(
                run_id=latest.run_id,
                version=len(completed_infer),
                pending_review=summary.pending_count,
                has_review_batch=summary.total_candidates > 0,
                reviewed_count=summary.total_reviewed,
                corrected_count=summary.corrected_count,
                skipped_count=summary.skipped_count,
                accepted_count=summary.accepted_count,
            )
    return TrajectoryFacts(
        manual_count=manual_count,
        active_status=status,
        active_run_id=active_run_id,
        active_version=active_version,
        active_pending_review=active_pending,
        candidate=candidate,
    )


def analysis_facts(session: ProjectSession, track_id: UUID | None) -> AnalysisFacts:
    """四态分析可用性；限制（缺测/待审）在任何状态都保留。

    状态优先级：无有效点 → not_computable；derived 缺失/过期 → needs_update；
    derived 有效但存在缺测或当前结果待审 → partial；否则 latest。
    """
    if track_id is None:
        return AnalysisFacts(state=ANALYSIS_NOT_COMPUTABLE, reason="no track selected")
    track = next((t for t in session.tracks if t.track_id == track_id), None)
    if track is None:
        return AnalysisFacts(state=ANALYSIS_NOT_COMPUTABLE, reason="no track selected")
    timeline = next(
        (t for t in session.project.timelines if t.video_id == track.video_id), None)
    if timeline is None:
        return AnalysisFacts(state=ANALYSIS_NOT_COMPUTABLE, reason="no timeline")

    points = session.effective_points(track_id)
    if not points:
        return AnalysisFacts(
            state=ANALYSIS_NOT_COMPUTABLE,
            reason="no effective observations on this track")

    zone_start, zone_end = timeline.working_zone
    zone_frames = zone_end - zone_start + 1
    effective = len({p.frame_index for p in points})
    limitations: list[str] = []
    if effective < zone_frames:
        limitations.append(
            f"{zone_frames - effective} of {zone_frames} frames in the working zone "
            "have no effective observation")
    pending = _active_pending_review(session, track_id)
    if pending:
        limitations.append(
            f"{pending} suggested frame(s) of the current result await review")

    derived_valid = any(
        d.track_id == track_id and d.status == "valid"
        for d in session.project.derived
    )
    derived_present = any(d.track_id == track_id for d in session.project.derived)
    if not derived_valid:
        state = ANALYSIS_NEEDS_UPDATE
        reason = None if derived_present else "charts have not been computed yet"
    elif limitations:
        state, reason = ANALYSIS_PARTIAL, None
    else:
        state, reason = ANALYSIS_LATEST, None
    return AnalysisFacts(
        state=state,
        reason=reason,
        limitations=tuple(limitations),
        effective_frames=effective,
        zone_frames=zone_frames,
    )


def project_workflow_state(
    session: ProjectSession,
    track_id: UUID | None,
    runs: Sequence[TrackingRun],
    execution: ExecutionInput | None = None,
) -> WorkflowState:
    """三维修量 + 前置缺失 + 学习/生成推进度的一次性投影（纯读取）。"""
    execution = execution or ExecutionInput()
    prerequisites: list[str] = []
    if not session.project.videos:
        prerequisites.append("add an experiment video")
    if track_id is None:
        prerequisites.append("select or create a track")
    if session.project_root is None:
        prerequisites.append("save the project before AI tasks")

    trajectory = trajectory_facts(session, track_id, runs)
    analysis = analysis_facts(session, track_id)

    fixed_frames = 0
    fixed_valid = False
    completed_train = completed_infer = 0
    learned_not_generated = False
    failed_run_id = None
    new_labels = 0
    if track_id is not None:
        state = session.get_refinement_state(track_id)
        series = state.active_series
        if series is not None:
            fixed_frames = len(series.label_snapshots)
            fixed_valid, _reason = session.validate_active_validation_series(track_id)

        completed_train_runs = _completed_of(runs, track_id, "train")
        completed_infer_runs = _completed_of(runs, track_id, "infer")
        completed_train = len(completed_train_runs)
        completed_infer = len(completed_infer_runs)
        if completed_train_runs:
            latest_train = completed_train_runs[-1]
            latest_infer = completed_infer_runs[-1] if completed_infer_runs else None
            learned_not_generated = latest_infer is None or (
                latest_train.created_at > latest_infer.created_at)

        # 最近一次相关训练尝试失败且其后无成功 → 恢复卡
        relevant = [
            r for r in runs
            if r.track_id == track_id and r.task_type == "train"
            and r.status in {"completed", "failed"}]
        latest_attempt = None
        for run in relevant:
            if latest_attempt is None or run.created_at >= latest_attempt.created_at:
                latest_attempt = run
        if latest_attempt is not None and latest_attempt.status == "failed":
            failed_run_id = latest_attempt.run_id
        elif completed_train_runs:
            last = completed_train_runs[-1]
            if last.completed_at is not None:
                new_labels = sum(
                    1 for p in session.manual_points(track_id)
                    if p.modified_at > last.completed_at)

    comparison = None
    if track_id is not None and trajectory.candidate is not None:
        try:
            comparison = candidate_comparison(session, track_id, runs)
        except Exception:  # 比较是辅助证据；失败不阻塞卡片
            comparison = ComparisonFacts(
                conclusion=COMPARISON_INCOMPARABLE,
                detail="Comparison evidence could not be read.",
                limitation="Cannot judge which version is more accurate.")

    return WorkflowState(
        execution=execution,
        trajectory=trajectory,
        analysis=analysis,
        prerequisites=tuple(prerequisites),
        fixed_check_frames=fixed_frames,
        fixed_check_valid=fixed_valid,
        failed_run_id=failed_run_id,
        completed_train_count=completed_train,
        completed_infer_count=completed_infer,
        learned_not_generated=learned_not_generated,
        new_labels_since_last_train=new_labels,
        candidate_comparison=comparison,
    )


# ---------------------------------------------------------------------------
# C1 — 固定检查帧预选（确定性规则，用户确认后才 freeze）
# ---------------------------------------------------------------------------


def preselect_fixed_check_frames(frames: Sequence[int]) -> tuple[int, ...]:
    """按设计 §6.3 预选检查帧。

    n≥4 时取 ``min(n−3, max(1, n // 5))`` 个，在按帧号排序的人工帧上取等间隔
    内部位置（索引 ``floor(i * (n-1) / (k+1))``，i=1..k；floor 保证平局取较早
    帧）；去重保持帧号序。n≤3 返回空——标签不足时推荐补标而非建立检查集。
    """
    ordered = sorted(set(frames))
    n = len(ordered)
    if n < 4:
        return ()
    count = min(n - 3, max(1, n // 5))
    picked: list[int] = []
    for i in range(1, count + 1):
        index = int(i * (n - 1) / (count + 1))  # floor：平局取较早帧
        frame = ordered[index]
        if frame not in picked:
            picked.append(frame)
    return tuple(picked)


# ---------------------------------------------------------------------------
# 任务卡选择（优先级见设计 §9：前置缺失 → 执行中/取消 → 失败恢复 →
# 候选待审 → 候选采用结论 → 已学习未生成 → 初始标注/学习 → 优化/分析）
# ---------------------------------------------------------------------------


def select_task_card(state: WorkflowState) -> TaskCard:
    """按固定优先级返回当前上下文任务卡；纯函数、同状态同卡。"""
    traj = state.trajectory

    # 1. 必要前置缺失（无视频/无目标/未保存）
    if state.prerequisites:
        first = state.prerequisites[0]
        primary = {
            "add an experiment video": ActionSpec(ACTION_ADD_VIDEO, "Add experiment video"),
            "select or create a track": ActionSpec(ACTION_CREATE_TRACK, "Create a track"),
            "save the project before AI tasks": ActionSpec(ACTION_SAVE_PROJECT, "Save the project"),
        }.get(first, ActionSpec(ACTION_CREATE_TRACK, "Create a track"))
        return TaskCard(
            mode=MODE_SETUP,
            title="Current: experiment setup",
            explanation=(
                "Define what you are measuring before acquiring trajectories.",
                f"Next: {first}."),
            primary=primary,
            evidence=(f"Missing: {', '.join(state.prerequisites)}.",),
        )

    # 2. 取消中 / 执行中
    if state.execution.cancelling:
        return TaskCard(
            mode=MODE_BLOCKED,
            title="Current: stopping task",
            explanation=("The running task is stopping. Existing data is kept.",),
            primary=None,
        )
    if state.execution.busy:
        return _running_card(state)

    # 3. 最近一次相关训练失败（其后无成功）→ 恢复卡
    if state.failed_run_id is not None:
        return TaskCard(
            mode=MODE_BLOCKED,
            title="Current: learning did not finish",
            explanation=(
                "The last learning attempt failed. Manual points and any adopted "
                "trajectory are unchanged.",
                "Open “Results & history” for the error details and log."),
            primary=ActionSpec(ACTION_RETRY_LEARNING, "Retry learning"),
            secondary=(
                ActionSpec(ACTION_VIEW_ANALYSIS, "View current analysis",
                           enabled=traj.has_effective_input),
            ),
        )

    # 4. 最新候选有待审核帧
    if traj.candidate is not None and traj.candidate.pending_review > 0:
        cand = traj.candidate
        return TaskCard(
            mode=MODE_REVIEWING,
            title="Current: review trajectory",
            explanation=(
                f"{cand.pending_review} suggested frame(s) of the new trajectory "
                f"({cand.label}, not adopted) still need your judgement.",
                "Accept = position is fine · Correct = place the manual position · "
                "Skip = leave undecided."),
            primary=ActionSpec(ACTION_LABEL_FRAME, "Review next frame"),
            evidence=(
                f"Candidate {cand.label}: {cand.reviewed_count} reviewed "
                f"({cand.accepted_count} accepted · {cand.corrected_count} corrected · "
                f"{cand.skipped_count} skipped).",
            ),
        )

    # 5. 候选已就绪（已检查或未筛查）→ 采用结论卡
    if traj.candidate is not None:
        return _candidate_decision_card(state)

    # 6. 已学习未生成
    if state.learned_not_generated:
        return TaskCard(
            mode=MODE_GENERATE_READY,
            title="Current: generate trajectory",
            explanation=(
                "Learning finished. Apply the learned positions to the whole video "
                "next; nothing changes until you adopt the result.",),
            primary=ActionSpec(ACTION_GENERATE_TRAJECTORY, "Generate trajectory"),
            evidence=("Learning and tracking stay two explicit steps.",),
        )

    # 7. 标注不足 / 首次学习就绪
    if traj.manual_count < _MIN_LABELS_FOR_TRAINING:
        needed = _MIN_LABELS_FOR_TRAINING - traj.manual_count
        return TaskCard(
            mode=MODE_ANNOTATE,
            title="Current: mark example positions",
            explanation=(
                f"{traj.manual_count} frame(s) marked; at least {needed} more "
                "needed before learning can start.",
                "Mark the object in a few well-spread frames."),
            primary=(
                ActionSpec(ACTION_PICK_FRAMES, "Pick representative frames")
                if traj.manual_count == 0 else
                ActionSpec(ACTION_LABEL_FRAME, "Mark next suggested frame")
            ),
            evidence=("Manual positions are the only ground truth; suggestions "
                      "create no labels.",),
        )
    if state.completed_train_count == 0:
        return TaskCard(
            mode=MODE_LEARN_READY,
            title="Current: ready to start learning",
            explanation=(
                f"{traj.manual_count} manual example(s) ready. The system prepares "
                "the plan (fixed-check frames, epochs, batch, device); you start it.",),
            primary=ActionSpec(ACTION_START_LEARNING, "Start learning"),
            evidence=_learning_evidence(state),
        )

    # 8. 优化 / 分析出口
    if state.new_labels_since_last_train > 0:
        return TaskCard(
            mode=MODE_OPTIMIZE,
            title="Current: corrections applied",
            explanation=(
                f"{state.new_labels_since_last_train} new manual position(s) already "
                "improve the current trajectory for analysis.",
                "Continue optimizing only to improve the remaining frames."),
            primary=ActionSpec(ACTION_CONTINUE_OPTIMIZING, "Continue optimizing"),
            secondary=(
                ActionSpec(ACTION_VIEW_ANALYSIS, "View current analysis",
                           enabled=traj.has_effective_input),
            ),
        )
    if traj.has_effective_input and state.analysis.state == ANALYSIS_NEEDS_UPDATE:
        return TaskCard(
            mode=MODE_ANALYZE,
            title="Current: trajectory ready · charts need update",
            explanation=(
                "The current trajectory can be analyzed; charts are not up to "
                "date with it yet.",),
            primary=ActionSpec(ACTION_UPDATE_CHARTS, "Update charts"),
        )
    return TaskCard(
        mode=MODE_ANALYZE,
        title="Current: ready for analysis",
        explanation=("Charts are up to date with the current trajectory.",),
        primary=ActionSpec(
            ACTION_VIEW_ANALYSIS, "View charts", enabled=traj.has_effective_input,
            reason=None if traj.has_effective_input else "no effective observations"),
    )


def _running_card(state: WorkflowState) -> TaskCard:
    kind = state.execution.kind
    titles = {
        EXEC_FRAME_SELECTION: "picking representative frames",
        EXEC_TRAINING: "learning example positions",
        EXEC_INFERRING: "generating trajectory",
        EXEC_MINING: "finding frames to check",
    }
    modes = {
        EXEC_FRAME_SELECTION: MODE_ANNOTATE,
        EXEC_TRAINING: MODE_LEARNING,
        EXEC_INFERRING: MODE_GENERATING,
        EXEC_MINING: MODE_INSPECT,
    }
    return TaskCard(
        mode=modes.get(kind, MODE_BLOCKED),
        title=f"Current: {titles.get(kind, kind)}",
        explanation=(
            "The software is working; your data is safe.",
            "Epochs are learning steps, not remaining minutes."),
        primary=ActionSpec(ACTION_CANCEL_TASK, "Cancel"),
    )


def _candidate_decision_card(state: WorkflowState) -> TaskCard:
    traj = state.trajectory
    cand = traj.candidate
    comparison = state.candidate_comparison
    evidence = [
        f"Candidate {cand.label}: {cand.reviewed_count} reviewed "
        f"({cand.corrected_count} corrected · {cand.skipped_count} skipped).",
    ]
    if traj.active_label:
        evidence.append(
            f"Current adopted: {traj.active_label} + "
            f"{traj.manual_count} manual position(s).")
    if comparison is not None:
        evidence.append(comparison.detail)
        if comparison.limitation:
            evidence.append(comparison.limitation)
    if not traj.has_active_result:
        return TaskCard(
            mode=MODE_ADOPT,
            title="Current: first AI trajectory ready",
            explanation=(
                f"A first AI trajectory ({cand.label}) is ready and not used "
                "for analysis yet.",
                "Check its evidence, then adopt it explicitly.",),
            primary=ActionSpec(ACTION_INSPECT_TRAJECTORY, "Check this trajectory"),
            secondary=(ActionSpec(ACTION_ADOPT_TRAJECTORY, "Adopt this trajectory"),),
            evidence=tuple(evidence),
        )
    conclusion = comparison.conclusion if comparison else COMPARISON_INCOMPARABLE
    if conclusion == COMPARISON_BETTER:
        title = "Current: new trajectory looks better on fixed-check frames"
        explanation = (
            comparison.detail if comparison else "New trajectory is ready.",
            "Adopting replaces the current result; manual positions stay.",
        )
        primary = ActionSpec(ACTION_ADOPT_TRAJECTORY, "Adopt this trajectory")
        secondary = (ActionSpec(ACTION_VIEW_ANALYSIS, "View current analysis"),)
    elif conclusion in (COMPARISON_FLAT, COMPARISON_WORSE):
        head = ("No clear improvement" if conclusion == COMPARISON_FLAT
                else "Fixed-check error increased")
        title = f"Current: {head} — keep the current trajectory"
        explanation = (
            (comparison.detail if comparison else "No comparable evidence."),
            "The current adopted result stays; the candidate remains in history.",
        )
        primary = ActionSpec(ACTION_VIEW_ANALYSIS, "View current analysis")
        secondary = (
            ActionSpec(ACTION_ADOPT_TRAJECTORY,
                       "Adopt this trajectory anyway"),
        )
    else:  # incomparable
        title = "Current: new trajectory ready — cannot compare"
        explanation = (
            (comparison.detail if comparison
             else "There is no qualified fixed-check comparison."),
            "Charts keep using the current adopted trajectory.",
        )
        primary = ActionSpec(ACTION_INSPECT_TRAJECTORY, "Check this trajectory")
        secondary = (
            ActionSpec(ACTION_ADOPT_TRAJECTORY, "Adopt this trajectory"),
            ActionSpec(ACTION_VIEW_ANALYSIS, "View current analysis"),
        )
    return TaskCard(
        mode=MODE_ADOPT,
        title=title,
        explanation=explanation,
        primary=primary,
        secondary=secondary,
        evidence=tuple(evidence),
    )


def _learning_evidence(state: WorkflowState) -> tuple[str, ...]:
    n = state.trajectory.manual_count
    if state.fixed_check_valid and state.fixed_check_frames:
        train_n = n - state.fixed_check_frames
        return (
            f"{n} manual example(s): {train_n} for learning, "
            f"{state.fixed_check_frames} held out as fixed-check frames.",
            "Fixed-check frames are compared with the same ruler across runs.",
        )
    return (
        f"{n} manual example(s) will be used for learning.",
        "Before learning starts you can confirm a suggested set of fixed-check "
        "frames for fair comparison.",
    )


# ---------------------------------------------------------------------------
# C2 — 推荐 → 执行计划（与 Advanced 同一执行入口；Advisor Apply 语义不变）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LearningPlan:
    """一次学习的系统计划；执行仍由用户显式启动。"""

    training_mode: str                  # "restart" | "resume"
    epochs: int
    batch_size: int
    resume_from_run_id: "UUID | None" = None
    basis: str = ""                     # 计划依据（卡片“依据”行）

    def summary_line(self) -> str:
        parts = [f"{self.epochs} epochs", f"batch {self.batch_size}"]
        if self.training_mode == "resume":
            parts.insert(0, "continue from the last learning")
        else:
            parts.insert(0, "learn from scratch")
        return f"{self.training_mode}: " + " · ".join(parts)


def recommended_learning_plan(
    recommendation,
    *,
    first_training: bool,
    resume_source_run_id: UUID | None,
    default_epochs: int = 50,
    default_batch: int = 8,
) -> LearningPlan:
    """把 Advisor 建议（或首轮默认）转换为可执行学习计划。

    recommendation 为 None（无 Advisor 输入）且非首轮时保守 restart。
    resume 仅在存在可用源时生效；入口（prepare_tracking_request）会再校验。
    """
    if first_training:
        return LearningPlan(
            training_mode="restart",
            epochs=default_epochs,
            batch_size=default_batch,
            basis="first learning run with current system defaults",
        )
    mode, epochs, batch = "restart", default_epochs, default_batch
    basis = "no comparable evidence; conservative fresh learning"
    if recommendation is not None:
        if recommendation.epochs is not None:
            epochs = recommendation.epochs
        if recommendation.batch_size is not None:
            batch = recommendation.batch_size
        if recommendation.training_mode == "resume" and resume_source_run_id is not None:
            mode = "resume"
            basis = "; ".join(recommendation.evidence[:2]) or "advisor recommendation"
        elif recommendation.training_mode == "resume":
            # 建议继续但没有合格源（资格/快照缺失）：诚实降级并说明原因
            basis = ("; ".join(recommendation.evidence[:2]) or "advisor recommendation"
                     ) + "; no eligible resume source, falling back to restart"
        elif recommendation.training_mode == "restart":
            basis = "; ".join(recommendation.evidence[:2]) or "advisor recommendation"
    if mode == "resume" and resume_source_run_id is None:
        mode = "restart"
        basis = (basis + "; no eligible resume source, falling back to restart").strip("; ")
    return LearningPlan(
        training_mode=mode,
        epochs=epochs,
        batch_size=batch,
        resume_from_run_id=resume_source_run_id if mode == "resume" else None,
        basis=basis,
    )


def default_resume_source(
    session: ProjectSession,
    track_id: UUID,
    runs: Sequence[TrackingRun],
) -> UUID | None:
    """系统默认 resume 源：最新 completed train run（有 snapshot）且对当前
    活动验证集 clean（P6R-02 资格；无活动验证集时不设限）。"""
    from ai_physics_tracker.application.refinement_history import (
        validation_training_exposure,
    )
    active_series = session.get_refinement_state(track_id).active_series
    for run in reversed(_completed_of(runs, track_id, "train")):
        if not run.model_snapshot:
            continue
        if active_series is not None:
            exposure = validation_training_exposure(
                runs, run.run_id, active_series.frame_indices)
            if exposure.qualification != "clean":
                continue
        return run.run_id
    return None


# ---------------------------------------------------------------------------
# 候选 vs 当前采用结果的比较结论（设计 §12.1）
# ---------------------------------------------------------------------------

COMPARISON_BETTER = "better"
COMPARISON_FLAT = "flat"
COMPARISON_WORSE = "worse"
COMPARISON_INCOMPARABLE = "incomparable"

# 与 Advisor 一致的趋势档位（设计 §12.1-5：非显著性检验）
RMSE_TREND_THRESHOLD = 0.05


@dataclass(frozen=True)
class ComparisonFacts:
    """候选相对当前采用结果的固定检查比较结论。"""

    conclusion: str                    # better | flat | worse | incomparable
    detail: str                        # 人话结论 + 数字（含限制）
    limitation: str | None = None      # 永远附带的边界说明


def _infer_source_train_run(runs: Sequence[TrackingRun], infer_run: TrackingRun) -> TrackingRun | None:
    source_id = infer_run.config.get("training_run_id")
    if source_id is None:
        return None
    try:
        from uuid import UUID as _UUID
        source_uuid = _UUID(str(source_id))
    except (ValueError, TypeError):
        return None
    return next((r for r in runs if r.run_id == source_uuid), None)


def _train_evaluation(run: TrackingRun | None):
    """取 train run 的 (train_rmse, val_rmse, metric, unit)；无评价返回 None。"""
    if run is None:
        return None
    evaluation = run.extra_fields.get("evaluation")
    if not isinstance(evaluation, dict):
        return None
    from ai_physics_tracker.application.advisor_collection import _evaluation_rmse
    return _evaluation_rmse(evaluation)


def candidate_comparison(
    session: ProjectSession,
    track_id: UUID,
    runs: Sequence[TrackingRun],
) -> ComparisonFacts | None:
    """候选（其来源学习）vs 当前采用结果（其来源学习）的固定检查比较。

    资格要求（设计 §12.1-3）：同一有效 series、同名同单位指标、两者比较
    资格均 clean（P6R-02 lineage 暴露）；任一不满足 → incomparable，并说明
    缺什么。结论只描述固定检查帧上的趋势，不声称整段轨迹精度。
    """
    from ai_physics_tracker.application.refinement_history import (
        VALIDATION_COMPARISON_CLEAN,
        extract_refinement_iteration,
        validation_comparison_exposure,
    )

    facts = trajectory_facts(session, track_id, runs)
    if facts.candidate is None:
        return None
    candidate_run = next(
        (r for r in runs if r.run_id == facts.candidate.run_id), None)
    if candidate_run is None:
        return None
    if not facts.has_active_result or facts.active_run_id is None:
        return ComparisonFacts(
            conclusion=COMPARISON_INCOMPARABLE,
            detail="No adopted trajectory to compare with yet — this would be "
                   "the first AI result.",
            limitation="Adopting is allowed without comparison evidence.")

    ref_state = session.get_refinement_state(track_id)
    candidate_source = _infer_source_train_run(runs, candidate_run)
    active_run = next((r for r in runs if r.run_id == facts.active_run_id), None)
    active_source = _infer_source_train_run(runs, active_run) if active_run else None
    if candidate_source is None or active_source is None:
        return ComparisonFacts(
            conclusion=COMPARISON_INCOMPARABLE,
            detail="The two versions do not both record which learning run "
                   "produced them.",
            limitation="Cannot judge which version is more accurate.")

    candidate_eval = _train_evaluation(candidate_source)
    active_eval = _train_evaluation(active_source)
    if candidate_eval is None or active_eval is None:
        return ComparisonFacts(
            conclusion=COMPARISON_INCOMPARABLE,
            detail="A fixed-check evaluation is missing for at least one version.",
            limitation="Cannot judge which version is more accurate.")

    candidate_iter = extract_refinement_iteration(candidate_source)
    active_iter = extract_refinement_iteration(active_source)
    series_ids = [it.validation_series_id if it else None
                  for it in (candidate_iter, active_iter)]
    if series_ids[0] is None or series_ids[0] != series_ids[1]:
        return ComparisonFacts(
            conclusion=COMPARISON_INCOMPARABLE,
            detail="The two versions were not checked against the same "
                   "fixed-check frames.",
            limitation="Same-series comparison only; cannot judge accuracy.")

    for source in (candidate_source, active_source):
        exposure = validation_comparison_exposure(runs, source, ref_state)
        if exposure.qualification != VALIDATION_COMPARISON_CLEAN:
            reason = ("training lineage saw validation frames "
                      f"{list(exposure.exposed_frames)}" if exposure.exposed_frames
                      else "; ".join(exposure.reasons))
            return ComparisonFacts(
                conclusion=COMPARISON_INCOMPARABLE,
                detail=f"Comparison not qualified: {reason}.",
                limitation="Historical RMSE values are unchanged; the numbers "
                          "are not an independent holdout comparison.")

    _c_train, c_val, metric, unit = candidate_eval
    _a_train, a_val, metric2, unit2 = active_eval
    if metric != metric2 or unit != unit2:
        return ComparisonFacts(
            conclusion=COMPARISON_INCOMPARABLE,
            detail="The two evaluations use different metrics or units.",
            limitation="Cannot judge which version is more accurate.")
    if a_val <= 0:
        return ComparisonFacts(
            conclusion=COMPARISON_INCOMPARABLE,
            detail=f"Baseline {metric} is {a_val}; no trend is computed.",
            limitation="Raw values only; no automatic verdict.")

    delta = (c_val - a_val) / a_val
    limitation = ("This is a trend on the fixed-check frames, not the error of "
                  "the whole trajectory.")
    if delta <= -RMSE_TREND_THRESHOLD:
        return ComparisonFacts(
            conclusion=COMPARISON_BETTER,
            detail=(f"Fixed-check {metric} improved {abs(delta):.1%} "
                    f"({a_val:.4g} → {c_val:.4g} {unit})."),
            limitation=limitation)
    if delta >= RMSE_TREND_THRESHOLD:
        return ComparisonFacts(
            conclusion=COMPARISON_WORSE,
            detail=(f"Fixed-check {metric} increased {delta:.1%} "
                    f"({a_val:.4g} → {c_val:.4g} {unit})."),
            limitation=limitation)
    return ComparisonFacts(
        conclusion=COMPARISON_FLAT,
        detail=(f"Fixed-check {metric} changed {delta:+.1%} "
                f"({a_val:.4g} → {c_val:.4g} {unit}); below the ±5% trend band."),
        limitation=limitation)
