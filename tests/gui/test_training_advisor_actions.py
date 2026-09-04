"""Training Advisor 的 GUI 集成测试（Phase 5.5 Slice 3）。

覆盖：Advisor 摘要展示、Apply Suggestion 只填表不启动、Resume 模式贯通
resume source、缺 source 的 Resume 被拒绝且不启动训练。
"""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtWidgets import QApplication

from ai_physics_tracker.application.training_advisor import (
    ACTION_RESUME,
    ACTION_RESTART,
    ACTION_STOP_AND_COMPARE,
    ADDITIONAL_EPOCHS_DEFAULT,
    AdvisorInput,
    AdvisorRecommendation,
    RoundMetrics,
    recommend_training_action,
)
from ai_physics_tracker.domain.tracking_run import create_tracking_run, mark_run_completed
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from tests.gui.test_tracking_actions import (
    _FakeHandle,
    _FakeRunner,
    _opened_window,
    _StaticTimingProbe,
)
from ai_physics_tracker.application.video_session import VideoSession


def _completed_train_run(session, track_id, *, snapshot: bool = True):
    track = next(t for t in session.tracks if t.track_id == track_id)
    run = create_tracking_run(track.video_id, track_id, "train", engine="dlc")
    if snapshot:
        snap_dir = session.project_root / "data" / "engines" / "advisor-test"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap = snap_dir / "snapshot-parent.pt"
        snap.write_bytes(b"weights")
    else:
        snap = None
    completed = mark_run_completed(
        run,
        model_snapshot=None if snap is None else
        snap.relative_to(session.project_root).as_posix(),
    )
    session.record_tracking_run(completed)
    return completed


def test_advisor_summary_shown_and_apply_fills_form_only(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    win, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                            _FakeRunner(_FakeHandle()))
    panel = win.trackingActions.panel

    recommendation = AdvisorRecommendation(
        action=ACTION_RESUME,
        epochs=ADDITIONAL_EPOCHS_DEFAULT,
        batch_size=4,
        training_mode=ACTION_RESUME,
        evidence=("3 new manual label(s)",),
        limits=("Epochs value means additional epochs.",),
    )
    panel.setAdvisorSummary(recommendation)
    assert "resume" in panel.advisorLabel.text()
    assert panel.advisorApplyButton.isEnabled()

    # 改变表单值 → Apply 后被建议值覆盖
    panel.epochsSpinBox.setValue(120)
    panel.batchSizeSpinBox.setValue(16)
    panel.setTrainingMode("restart")
    panel._onApplySuggestionClicked()
    assert panel.epochsSpinBox.value() == ADDITIONAL_EPOCHS_DEFAULT
    assert panel.batchSizeSpinBox.value() == 4
    assert panel.trainingMode() == ACTION_RESUME


def test_apply_suggestion_never_starts_training(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    win, _session, _track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                              _FakeRunner(_FakeHandle()))
    runner = _FakeRunner(_FakeHandle())
    win.trackingActions.runner = runner
    panel = win.trackingActions.panel
    panel.setAdvisorSummary(AdvisorRecommendation(
        action=ACTION_RESUME, epochs=25, batch_size=4, training_mode=ACTION_RESUME))
    panel._onApplySuggestionClicked()
    assert runner.calls == 0  # 只填表，不启动


def test_stop_and_compare_is_not_fillable(qtbot, synthetic_video_path: Path, tmp_path: Path) -> None:
    win, _session, _track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                              _FakeRunner(_FakeHandle()))
    panel = win.trackingActions.panel
    panel.setAdvisorSummary(AdvisorRecommendation(
        action=ACTION_STOP_AND_COMPARE,
        evidence=("plateau",),
        limits=("Stop iterating.",),
    ))
    assert not panel.advisorApplyButton.isEnabled()


def test_refresh_computes_advisor_from_session_state(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    win, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                            _FakeRunner(_FakeHandle()))
    panel = win.trackingActions.panel
    # 无 train run → restart 建议
    win.trackingActions._context_key = None
    win.trackingActions.refresh()
    assert "restart" in panel.advisorLabel.text()

    # 有 completed train run 且无新增标签、无可比评价 → freeze 前置建议
    _completed_train_run(session, track_id)
    win.trackingActions._context_key = None
    win.trackingActions.refresh()
    assert "fix_prerequisite" in panel.advisorLabel.text()


def test_resume_mode_requires_source_and_passes_it_when_present(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    win, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                            _FakeRunner(_FakeHandle()))
    runner = _FakeRunner(_FakeHandle())
    win.trackingActions.runner = runner
    panel = win.trackingActions.panel

    # 无可选模型：Resume 缺 source → 不启动训练，提示原因
    panel.setTrainingMode("resume")
    win.trackingActions.train()
    assert runner.calls == 0
    assert "resume source" in panel.stageLabel.text().lower()

    # 注册一个带 snapshot 的 completed train run → 作为 resume source
    completed = _completed_train_run(session, track_id)
    win.trackingActions._context_key = None
    win.trackingActions.refresh()
    handle = _FakeHandle()
    win.trackingActions.runner = _FakeRunner(handle)
    win.trackingActions.train()
    assert win.trackingActions.pending
    recorded = next(r for r in session.tracking_runs() if r.run_id == win.trackingActions._request.run.run_id)
    assert recorded.config.get("training_mode") == "resume"
