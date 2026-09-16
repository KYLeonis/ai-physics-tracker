"""Phase 5.7 — 工作流状态投影测试（Qt-free）。

覆盖设计 §9–§11 的核心语义：三维修量派生、任务卡优先级、C1 预选规则、
分析可用性四态、candidate/active 分离。
"""

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    ReviewCandidate,
    SuggestedFrameReviewState,
    attach_review_state,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.workflow_projection import (
    ACTION_ADOPT_TRAJECTORY,
    ACTION_CANCEL_TASK,
    ACTION_CONTINUE_OPTIMIZING,
    ACTION_GENERATE_TRAJECTORY,
    ACTION_INSPECT_TRAJECTORY,
    ACTION_PICK_FRAMES,
    ACTION_RETRY_LEARNING,
    ACTION_START_LEARNING,
    ACTION_UPDATE_CHARTS,
    ANALYSIS_LATEST,
    ANALYSIS_NEEDS_UPDATE,
    ANALYSIS_NOT_COMPUTABLE,
    ANALYSIS_PARTIAL,
    CandidateFacts,
    ExecutionInput,
    TrajectoryFacts,
    WorkflowState,
    analysis_facts,
    preselect_fixed_check_frames,
    project_workflow_state,
    select_task_card,
)
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_completed,
    mark_run_failed,
    mark_run_running,
)
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _info(fps: float = 10.0, frame_count: int = 20) -> VideoStreamInfo:
    return VideoStreamInfo(64, 48, fps, frame_count, "fake", "cfr")


def _session_with_track(tmp_path: Path, *, zone_frames: int = 20):
    session = ProjectSession.start(ProjectRepository(), name="Projection")
    session.save_as(tmp_path / "proj")
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"dummy")
    video, _ = session.register_external_video(video_file, _info(frame_count=zone_frames))
    track = session.add_track(video.video_id)
    return session, track, video


def _run(session, track, task_type: str, *, status: str = "completed",
         with_snapshot: bool = True, with_observations: bool = False) -> TrackingRun:
    run = create_tracking_run(track.video_id, track.track_id, task_type,
                              engine_version="mock")
    if with_snapshot and task_type == "train":
        snap = f"data/engines/{run.run_id}/snap.pt"
        file = session.project_root / snap
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"w")
        run = mark_run_completed(run, model_snapshot=snap)
    elif status == "completed":
        if task_type == "infer" and with_observations:
            _fake_observations(session, run)
        run = mark_run_completed(run)
    elif status == "failed":
        run = mark_run_failed(run, "boom")
    session.record_tracking_run(run)
    return run


def _fake_observations(session: ProjectSession, run: TrackingRun) -> None:
    """激活路径需要的 observations.json 产物（复用 5.4 测试形态）。"""
    from dataclasses import asdict
    import json

    from ai_physics_tracker.domain.track import TrackPoint
    from ai_physics_tracker.domain.types import utc_now
    from uuid import uuid4 as _uuid4

    out_dir = session.project_root / "data" / "engines" / str(run.run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    points = []
    for frame in range(6):
        point = TrackPoint(
            point_id=_uuid4(), track_id=run.track_id, frame_index=frame,
            time_s=frame / 10.0, pixel_x=5.0 + frame, pixel_y=6.0 + frame,
            source=run.engine, confidence=0.95, visibility="visible",
            status="active", source_detail=run.source_detail,
            created_at=now, modified_at=now,
        )
        points.append(asdict(point))
    (out_dir / "observations.json").write_text(
        json.dumps(points, ensure_ascii=False, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# C1 — 预选规则（确定性）
# ---------------------------------------------------------------------------


def test_preselect_matches_design_examples() -> None:
    # 设计 §6.3：10 帧预选 2 帧检查、8 帧训练
    assert preselect_fixed_check_frames(list(range(10))) == (3, 6)
    # n=8：1 帧
    assert preselect_fixed_check_frames(list(range(8))) == (3,)
    # n=4：最早可用组合（1 帧，平局取较早帧）
    assert preselect_fixed_check_frames([10, 11, 12, 13]) == (11,)
    # 大 n：n−3 上限生效（n=20 → 0.2n=4 < 17）
    assert len(preselect_fixed_check_frames(list(range(20)))) == 4
    # 标签不足：不预选
    assert preselect_fixed_check_frames([1, 2, 3]) == ()
    assert preselect_fixed_check_frames([]) == ()


def test_preselect_is_deterministic_and_deduplicates() -> None:
    once = preselect_fixed_check_frames([5, 3, 9, 1, 7, 11])
    again = preselect_fixed_check_frames([11, 1, 9, 5, 3, 7])
    assert once == again
    assert once == tuple(sorted(set(once)))


# ---------------------------------------------------------------------------
# 分析可用性四态
# ---------------------------------------------------------------------------


def test_analysis_not_computable_without_points(tmp_path: Path) -> None:
    session, track, _video = _session_with_track(tmp_path)
    assert analysis_facts(session, track.track_id).state == ANALYSIS_NOT_COMPUTABLE
    assert analysis_facts(session, None).state == ANALYSIS_NOT_COMPUTABLE


def test_analysis_needs_update_then_partial_then_latest(tmp_path: Path) -> None:
    session, track, _video = _session_with_track(tmp_path, zone_frames=10)
    # 有 manual 点但未计算 → 待更新（尚未计算）
    for frame in range(10):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    facts = analysis_facts(session, track.track_id)
    assert facts.state == ANALYSIS_NEEDS_UPDATE
    assert facts.reason == "charts have not been computed yet"

    # 计算（四类派生 valid、无缺测、无待审）→ latest
    session.compute_kinematics(track.track_id)
    assert analysis_facts(session, track.track_id).state == ANALYSIS_LATEST

    # 制造缺测（删除一段中唯一帧的覆盖：再标一条含缺测的轨迹不可行——
    # 用部分覆盖的第二个 track 验证 partial）
    other = session.add_track(_video_id_of(session, track))
    for frame in range(4):  # 10 帧区段只覆盖 4 帧
        session.mark_point(other.track_id, frame, 1.0, 1.0)
    session.compute_kinematics(other.track_id)
    partial = analysis_facts(session, other.track_id)
    assert partial.state == ANALYSIS_PARTIAL
    assert any("no effective observation" in line for line in partial.limitations)


def _video_id_of(session: ProjectSession, track) -> object:
    return track.video_id


def test_analysis_partial_when_active_result_has_pending_review(tmp_path: Path) -> None:
    session, track, video = _session_with_track(tmp_path, zone_frames=6)
    for frame in range(6):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    run = _run(session, track, "infer", with_observations=True)
    session.activate_infer_run(track.track_id, run.run_id)
    # 给该 run 挂一个含待审候选的批次
    candidate = ReviewCandidate(
        frame_index=2, prediction=None, components={}, raw_components={},
        reasons=("low_confidence",), total_score=1.0)
    session.set_active_review_batch(run.run_id, ActiveReviewBatch(
        request_id=uuid4(), candidates=(candidate,), params_snapshot={}))
    session.compute_kinematics(track.track_id)
    facts = analysis_facts(session, track.track_id)
    assert facts.state == ANALYSIS_PARTIAL
    assert any("await review" in line for line in facts.limitations)


# ---------------------------------------------------------------------------
# 任务卡优先级
# ---------------------------------------------------------------------------


def _state(**overrides) -> WorkflowState:
    base = dict(
        execution=ExecutionInput(),
        trajectory=TrajectoryFacts(),
        analysis=_analysis(ANALYSIS_NOT_COMPUTABLE),
    )
    base.update(overrides)
    return WorkflowState(**base)


def _analysis(state: str) -> object:
    from ai_physics_tracker.application.workflow_projection import AnalysisFacts
    return AnalysisFacts(state=state)


def test_card_setup_when_prerequisites_missing() -> None:
    card = select_task_card(_state(prerequisites=("select or create a track",)))
    assert card.primary is not None and card.primary.action_id == "create_track"


def test_card_priority_running_beats_everything() -> None:
    state = _state(
        execution=ExecutionInput(kind="training"),
        trajectory=TrajectoryFacts(manual_count=5),
        prerequisites=(),  # 前置已满足
    )
    card = select_task_card(state)
    assert card.mode == "learning"
    assert card.primary.action_id == ACTION_CANCEL_TASK


def test_card_priority_candidate_review_beats_generate_and_learn() -> None:
    cand = CandidateFacts(run_id=uuid4(), version=2, pending_review=3)
    state = _state(trajectory=TrajectoryFacts(manual_count=8, candidate=cand))
    card = select_task_card(state)
    assert card.mode == "reviewing"
    assert "3 suggested frame(s)" in card.explanation[0]


def test_card_first_candidate_offers_check_then_adopt() -> None:
    cand = CandidateFacts(run_id=uuid4(), version=1, reviewed_count=5)
    state = _state(trajectory=TrajectoryFacts(manual_count=8, candidate=cand))
    card = select_task_card(state)
    assert card.mode == "adopt"
    assert card.primary.action_id == ACTION_INSPECT_TRAJECTORY
    assert any(a.action_id == ACTION_ADOPT_TRAJECTORY for a in card.secondary)


def test_card_replace_candidate_keeps_current_charts() -> None:
    cand = CandidateFacts(run_id=uuid4(), version=2)
    state = _state(trajectory=TrajectoryFacts(
        manual_count=8, active_status="active", active_version=1, candidate=cand))
    card = select_task_card(state)
    assert card.primary.action_id == ACTION_ADOPT_TRAJECTORY
    assert any("Charts keep using" in line for line in card.explanation)


def test_card_learned_not_generated_prompts_generate() -> None:
    state = _state(
        trajectory=TrajectoryFacts(manual_count=5),
        completed_train_count=1, completed_infer_count=0, learned_not_generated=True)
    card = select_task_card(state)
    assert card.mode == "generate_ready"
    assert card.primary.action_id == ACTION_GENERATE_TRAJECTORY


def test_card_insufficient_labels_then_learn_ready() -> None:
    card = select_task_card(_state(trajectory=TrajectoryFacts(manual_count=0)))
    assert card.mode == "annotate"
    assert card.primary.action_id == ACTION_PICK_FRAMES

    card3 = select_task_card(_state(trajectory=TrajectoryFacts(manual_count=2)))
    assert card3.mode == "annotate"

    card4 = select_task_card(_state(
        trajectory=TrajectoryFacts(manual_count=4), completed_train_count=0))
    assert card4.mode == "learn_ready"
    assert card4.primary.action_id == ACTION_START_LEARNING
    assert any("fixed-check" in line for line in card4.evidence)


def test_card_failure_recovery_beats_learning() -> None:
    state = _state(
        trajectory=TrajectoryFacts(manual_count=5),
        failed_run_id=uuid4(), completed_train_count=0)
    card = select_task_card(state)
    assert card.primary.action_id == ACTION_RETRY_LEARNING
    assert any("unchanged" in line for line in card.explanation)


def test_card_optimize_then_analysis_exit() -> None:
    state = _state(
        trajectory=TrajectoryFacts(manual_count=6, active_status="active",
                                   active_version=1),
        completed_train_count=1, completed_infer_count=1,
        new_labels_since_last_train=3,
        analysis=_analysis(ANALYSIS_NEEDS_UPDATE))
    card = select_task_card(state)
    assert card.mode == "optimize"
    assert card.primary.action_id == ACTION_CONTINUE_OPTIMIZING

    settled = _state(
        trajectory=TrajectoryFacts(manual_count=6, active_status="active",
                                   active_version=1),
        completed_train_count=1, completed_infer_count=1,
        analysis=_analysis(ANALYSIS_NEEDS_UPDATE))
    assert select_task_card(settled).primary.action_id == ACTION_UPDATE_CHARTS


# ---------------------------------------------------------------------------
# project_workflow_state 组合事实（走真实 session）
# ---------------------------------------------------------------------------


def test_projection_from_real_session_lifecycle(tmp_path: Path) -> None:
    session, track, video = _session_with_track(tmp_path, zone_frames=8)

    # 初始：无标签 → annotate
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert select_task_card(state).mode == "annotate"

    # 3+ 标签 → learn_ready
    for frame in range(4):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    card = select_task_card(state)
    assert card.mode == "learn_ready"

    # 完成一次训练（无推理）→ generate_ready
    _run(session, track, "train")
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert select_task_card(state).mode == "generate_ready"

    # 完成推理 → 候选卡（首个，未采用）
    infer_run = _run(session, track, "infer", with_observations=True)
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert select_task_card(state).mode == "adopt"
    assert state.trajectory.candidate is not None
    assert state.trajectory.candidate.version == 1

    # 激活后 → 无候选；分析待更新
    session.activate_infer_run(track.track_id, infer_run.run_id)
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert state.trajectory.candidate is None
    assert state.trajectory.active_version == 1
    assert state.analysis.state == ANALYSIS_NEEDS_UPDATE
    assert select_task_card(state).primary.action_id == ACTION_UPDATE_CHARTS


def test_projection_marks_failed_training_for_recovery(tmp_path: Path) -> None:
    session, track, _video = _session_with_track(tmp_path)
    for frame in range(3):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    _run(session, track, "train", status="failed", with_snapshot=False)
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert state.failed_run_id is not None
    card = select_task_card(state)
    assert card.mode == "blocked"
    assert card.primary.action_id == ACTION_RETRY_LEARNING
