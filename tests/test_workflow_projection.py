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
    ACTION_FINISH_CHECKING,
    ACTION_PICK_FRAMES,
    ACTION_RETRY_LEARNING,
    ACTION_START_LEARNING,
    ACTION_UPDATE_CHARTS,
    ACTION_VIEW_ANALYSIS,
    ANALYSIS_LATEST,
    ANALYSIS_NEEDS_UPDATE,
    ANALYSIS_NOT_COMPUTABLE,
    ANALYSIS_PARTIAL,
    NO_SCALE_LIMITATION,
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
         with_snapshot: bool = True, with_observations: bool = False,
         config: dict | None = None) -> TrackingRun:
    run = create_tracking_run(track.video_id, track.track_id, task_type,
                              engine_version="mock", config=config)
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
    latest = analysis_facts(session, track.track_id)
    assert latest.state == ANALYSIS_LATEST
    assert NO_SCALE_LIMITATION in latest.limitations

    session.add_calibration(
        track.video_id,
        scale_end_1_px=(0.0, 0.0), scale_end_2_px=(10.0, 0.0),
        known_length=1.0, unit="m")
    assert NO_SCALE_LIMITATION not in analysis_facts(
        session, track.track_id).limitations

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
    assert card.primary.action_id == "review_correct"
    assert any(action.action_id == ACTION_FINISH_CHECKING
               for action in card.secondary)


def test_finished_checking_exits_review_without_discarding_pending_count() -> None:
    run_id = uuid4()
    cand = CandidateFacts(run_id=run_id, version=2, pending_review=3)
    state = _state(
        execution=ExecutionInput(paused_review_run_id=run_id),
        trajectory=TrajectoryFacts(manual_count=8, candidate=cand))

    card = select_task_card(state)

    assert card.mode == "adopt"
    assert card.primary.action_id == ACTION_INSPECT_TRAJECTORY


def test_card_first_candidate_offers_check_then_adopt() -> None:
    cand = CandidateFacts(run_id=uuid4(), version=1, reviewed_count=5)
    state = _state(trajectory=TrajectoryFacts(manual_count=8, candidate=cand))
    card = select_task_card(state)
    assert card.mode == "adopt"
    assert card.primary.action_id == ACTION_INSPECT_TRAJECTORY
    assert any(a.action_id == ACTION_ADOPT_TRAJECTORY for a in card.secondary)


def test_card_replace_candidate_without_comparison_defaults_to_incomparable() -> None:
    cand = CandidateFacts(run_id=uuid4(), version=2)
    state = _state(trajectory=TrajectoryFacts(
        manual_count=8, active_status="active", active_version=1, candidate=cand))
    card = select_task_card(state)
    # 无比较证据：不显示优劣，主动作是检查；采用保持显式次要入口
    assert card.primary.action_id == ACTION_INSPECT_TRAJECTORY
    assert any(a.action_id == ACTION_ADOPT_TRAJECTORY for a in card.secondary)
    assert any("Charts keep using" in line for line in card.explanation)


def test_card_comparison_conclusions_drive_primary_action() -> None:
    from ai_physics_tracker.application.workflow_projection import (
        COMPARISON_BETTER,
        COMPARISON_FLAT,
        COMPARISON_WORSE,
        ComparisonFacts,
    )
    cand = CandidateFacts(run_id=uuid4(), version=2)
    base_traj = TrajectoryFacts(manual_count=8, active_status="active",
                                active_version=1, candidate=cand)

    better = _state(trajectory=base_traj, candidate_comparison=ComparisonFacts(
        conclusion=COMPARISON_BETTER, detail="improved 8%", limitation="trend only"))
    card = select_task_card(better)
    assert card.primary.action_id == ACTION_ADOPT_TRAJECTORY
    assert any(a.action_id == ACTION_VIEW_ANALYSIS for a in card.secondary)

    for conclusion, expect_primary in (
            (COMPARISON_FLAT, ACTION_VIEW_ANALYSIS),
            (COMPARISON_WORSE, ACTION_VIEW_ANALYSIS)):
        state = _state(trajectory=base_traj, candidate_comparison=ComparisonFacts(
            conclusion=conclusion, detail="changed", limitation="trend only"))
        card = select_task_card(state)
        assert card.primary.action_id == expect_primary, conclusion
        # 保留当前为默认建议，但显式采用仍在次要入口
        assert any(a.action_id == ACTION_ADOPT_TRAJECTORY for a in card.secondary)
        assert "keep the current trajectory" in card.title


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
    train_run = _run(session, track, "train")
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert select_task_card(state).mode == "generate_ready"

    # 完成推理 → 候选卡（首个，未采用）
    infer_run = _run(
        session, track, "infer", with_observations=True,
        config={"training_run_id": str(train_run.run_id)})
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


def test_generate_prompt_uses_training_lineage_not_timestamps(tmp_path: Path) -> None:
    session, track, _video = _session_with_track(tmp_path, zone_frames=8)
    for frame in range(4):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    train1 = _run(session, track, "train")
    _run(session, track, "infer",
         config={"training_run_id": str(train1.run_id)})
    train2 = _run(session, track, "train")

    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert state.learned_not_generated is True

    _run(session, track, "infer",
         config={"training_run_id": str(train2.run_id)})
    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    assert state.learned_not_generated is False


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


# ---------------------------------------------------------------------------
# C2 — 推荐学习计划 / 默认 resume 源
# ---------------------------------------------------------------------------


def test_learning_plan_first_training_uses_defaults() -> None:
    from ai_physics_tracker.application.workflow_projection import (
        recommended_learning_plan,
    )
    plan = recommended_learning_plan(None, first_training=True,
                                     resume_source_run_id=None)
    assert plan.training_mode == "restart"
    assert plan.epochs == 50 and plan.batch_size == 8
    assert plan.resume_from_run_id is None


def test_learning_plan_maps_advisor_resume_with_source() -> None:
    from ai_physics_tracker.application.training_advisor import (
        AdvisorRecommendation,
    )
    from ai_physics_tracker.application.workflow_projection import (
        recommended_learning_plan,
    )
    rec = AdvisorRecommendation(
        action="resume", epochs=25, training_mode="resume",
        evidence=("3 new label(s)",))
    source = uuid4()
    plan = recommended_learning_plan(rec, first_training=False,
                                     resume_source_run_id=source)
    assert plan.training_mode == "resume"
    assert plan.epochs == 25 and plan.resume_from_run_id == source


def test_learning_plan_resume_without_source_falls_back_to_restart() -> None:
    from ai_physics_tracker.application.training_advisor import (
        AdvisorRecommendation,
    )
    from ai_physics_tracker.application.workflow_projection import (
        recommended_learning_plan,
    )
    rec = AdvisorRecommendation(action="resume", training_mode="resume")
    plan = recommended_learning_plan(rec, first_training=False,
                                     resume_source_run_id=None)
    assert plan.training_mode == "restart"
    assert "falling back" in plan.basis


def test_default_resume_source_requires_clean_qualification(tmp_path: Path) -> None:
    from ai_physics_tracker.application.refinement_history import (
        RefinementIterationInfo,
        ValidationLabelSnapshot,
        attach_refinement_iteration,
    )
    from ai_physics_tracker.application.workflow_projection import (
        default_resume_source,
    )

    session, track, _video = _session_with_track(tmp_path, zone_frames=8)
    for frame in range(4):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    series = session.create_validation_series(track.track_id, "fixed", [3])

    def _labels(frames):
        return tuple(
            ValidationLabelSnapshot(point_id=uuid4(), frame_index=f,
                                    pixel_x=1.0, pixel_y=1.0,
                                    modified_at="2026-01-01T00:00:00+00:00")
            for f in frames)

    clean = create_tracking_run(track.video_id, track.track_id, "train",
                                engine_version="mock")
    clean = attach_refinement_iteration(clean, RefinementIterationInfo(
        iteration_index=0, training_mode="restart", training_labels=_labels([0, 1])))
    clean = mark_run_completed(clean, model_snapshot="data/engines/x/s.pt")
    contaminated = create_tracking_run(track.video_id, track.track_id, "train",
                                       engine_version="mock")
    contaminated = attach_refinement_iteration(contaminated, RefinementIterationInfo(
        iteration_index=1, training_mode="restart",
        training_labels=_labels([3, 2])))  # 训练过验证帧 3
    contaminated = mark_run_completed(contaminated,
                                      model_snapshot="data/engines/y/s.pt")
    session.record_tracking_run(clean)
    session.record_tracking_run(contaminated)
    runs = session.tracking_runs()

    # 有活动验证集：污染源被跳过，即使它更新
    assert default_resume_source(session, track.track_id, runs) == clean.run_id

    # 无活动验证集：资格不设限，取最新
    session.set_active_validation_series(track.track_id, None)
    assert default_resume_source(session, track.track_id, runs) \
        == contaminated.run_id


# ---------------------------------------------------------------------------
# candidate_comparison：四种结论（真实 session）
# ---------------------------------------------------------------------------


def _completed_train_with_eval(session, track, runs_registry, *, training_frames,
                               series_id, val_rmse, mode="restart", resume_from=None):
    from ai_physics_tracker.application.refinement_history import (
        RefinementIterationInfo,
        ValidationLabelSnapshot,
        attach_refinement_iteration,
    )
    from ai_physics_tracker.domain.types import utc_now
    import dataclasses

    run = create_tracking_run(track.video_id, track.track_id, "train",
                              engine_version="mock")
    snap_rel = f"data/engines/{run.run_id}/snap.pt"
    snap = session.project_root / snap_rel
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_bytes(b"w")
    run = mark_run_completed(run, model_snapshot=snap_rel)
    labels = tuple(
        ValidationLabelSnapshot(point_id=uuid4(), frame_index=f,
                                pixel_x=1.0, pixel_y=1.0,
                                modified_at=utc_now().isoformat())
        for f in training_frames)
    run = attach_refinement_iteration(run, RefinementIterationInfo(
        iteration_index=len(runs_registry), validation_series_id=series_id,
        training_mode=mode, resume_from_training_run_id=resume_from,
        training_labels=labels))
    run = dataclasses.replace(run, extra_fields={
        **run.extra_fields,
        "evaluation": {"metrics": {"train_rmse": 4.0, "test_rmse": val_rmse},
                       "unit": "px"},
    })
    session.record_tracking_run(run)
    return run


def _completed_infer(session, track, source_train, *, observations=False):
    import dataclasses

    run = create_tracking_run(track.video_id, track.track_id, "infer",
                              engine="dlc", engine_version="mock",
                              config={"training_run_id": str(source_train.run_id)})
    if observations:
        _fake_observations(session, run)
    run = mark_run_completed(run)
    session.record_tracking_run(run)
    return run


def _comparison_session(tmp_path, *, second_val_rmse: float, tag: str = "a"):
    session = ProjectSession.start(ProjectRepository(), name="Comparison")
    session.save_as(tmp_path / f"proj-{tag}")
    video_file = tmp_path / f"clip-{tag}.mp4"
    video_file.write_bytes(b"dummy")
    video, _ = session.register_external_video(video_file, _info(frame_count=10))
    track = session.add_track(video.video_id)
    for frame in range(8):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    series = session.create_validation_series(track.track_id, "fixed", [7])
    runs = session.tracking_runs()
    first = _completed_train_with_eval(session, track, runs,
                                       training_frames=[0, 1, 2],
                                       series_id=series.series_id, val_rmse=5.0)
    second = _completed_train_with_eval(session, track, runs + (first,),
                                        training_frames=[0, 1, 3],
                                        series_id=series.series_id,
                                        val_rmse=second_val_rmse)
    older_infer = _completed_infer(session, track, first, observations=True)
    candidate_infer = _completed_infer(session, track, second)
    session.activate_infer_run(track.track_id, older_infer.run_id)
    return session, track, first, second, older_infer, candidate_infer, series


def test_candidate_comparison_better_flat_worse(tmp_path: Path) -> None:
    from ai_physics_tracker.application.workflow_projection import (
        COMPARISON_BETTER,
        COMPARISON_FLAT,
        COMPARISON_WORSE,
        candidate_comparison,
    )

    for rmse, expected in ((4.0, COMPARISON_BETTER), (4.9, COMPARISON_FLAT),
                           (6.0, COMPARISON_WORSE)):
        session, track, *_rest = _comparison_session(
            tmp_path, second_val_rmse=rmse, tag=expected)
        facts = candidate_comparison(session, track.track_id,
                                     session.tracking_runs())
        assert facts is not None and facts.conclusion == expected, rmse
        assert facts.limitation and "whole trajectory" in facts.limitation


def test_candidate_comparison_incomparable_on_contaminated_lineage(tmp_path: Path) -> None:
    from ai_physics_tracker.application.refinement_history import (
        RefinementIterationInfo,
        ValidationLabelSnapshot,
        attach_refinement_iteration,
    )
    from ai_physics_tracker.application.workflow_projection import (
        COMPARISON_INCOMPARABLE,
        candidate_comparison,
    )
    from ai_physics_tracker.domain.types import utc_now

    session, track, first, second, older, _cand, series = _comparison_session(
        tmp_path, second_val_rmse=4.0)
    # 把候选来源学习改成 resume 自一个训练过验证帧的祖先 → 资格污染
    contaminated_ancestor = create_tracking_run(
        track.video_id, track.track_id, "train", engine_version="mock")
    labels = (ValidationLabelSnapshot(
        point_id=uuid4(), frame_index=7, pixel_x=1.0, pixel_y=1.0,
        modified_at=utc_now().isoformat()),)
    contaminated_ancestor = attach_refinement_iteration(
        contaminated_ancestor, RefinementIterationInfo(
            iteration_index=99, training_labels=labels))
    session.record_tracking_run(contaminated_ancestor)
    session.update_tracking_run(attach_refinement_iteration(
        second, RefinementIterationInfo(
            iteration_index=1, validation_series_id=series.series_id,
            training_mode="resume",
            resume_from_training_run_id=contaminated_ancestor.run_id,
            training_labels=tuple())))

    facts = candidate_comparison(session, track.track_id, session.tracking_runs())
    assert facts.conclusion == COMPARISON_INCOMPARABLE
    assert "not qualified" in facts.detail.lower() or "saw validation" in facts.detail


def test_invalid_fixed_check_set_drives_rebuild_card(tmp_path: Path) -> None:
    """R1 F2：集合失效 → 主动作 = 查看并确认建议检查帧。"""
    from ai_physics_tracker.application.workflow_projection import (
        select_task_card,
        project_workflow_state,
    )

    session, track, _video = _session_with_track(tmp_path, zone_frames=10)
    for frame in range(6):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    series = session.create_validation_series(track.track_id, "fixed", [5])
    # 使集合失效：改动检查帧上的 manual 点
    session.mark_point(track.track_id, 5, 99.0, 99.0)
    assert not session.validate_active_validation_series(track.track_id)[0]

    state = project_workflow_state(session, track.track_id, session.tracking_runs())
    card = select_task_card(state)
    assert card.mode == "learn_ready"
    assert card.primary.action_id == "confirm_check_frames"
    assert "rebuilding" in card.title


def test_candidate_comparison_non_finite_metrics_are_incomparable(
    tmp_path: Path,
) -> None:
    """R1 F3：NaN/inf 指标不得产出 flat 伪结论。"""
    from ai_physics_tracker.application.workflow_projection import (
        COMPARISON_INCOMPARABLE,
        candidate_comparison,
    )

    session, track, first, second, older, _cand, series = _comparison_session(
        tmp_path, second_val_rmse=float("nan"), tag="nan")
    facts = candidate_comparison(session, track.track_id, session.tracking_runs())
    assert facts.conclusion == COMPARISON_INCOMPARABLE
    assert "nan" in facts.detail
