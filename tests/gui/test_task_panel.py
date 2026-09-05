"""TaskPanel 的参数、禁用原因、模型选择和有界日志测试。"""

from dataclasses import replace
from uuid import uuid4

from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ai_physics_tracker.domain.tracking_run import (
    create_tracking_run,
    mark_run_completed,
)
from ai_physics_tracker.gui.task_panel import TaskPanel


def _panel(qtbot: QtBot) -> TaskPanel:
    panel = TaskPanel(None if QApplication.instance() else QApplication([]))
    qtbot.addWidget(panel)
    return panel


def test_default_parameters_and_shared_inference_settings(qtbot: QtBot) -> None:
    panel = _panel(qtbot)

    assert panel.trainingParameters().epochs == 50
    assert panel.trainingParameters().batch_size == 8
    assert panel.trainingParameters().device == "auto"
    assert panel.inferenceParameters().min_confidence == 0.6
    assert panel.inferenceParameters().device == "auto"
    assert panel.inferenceParameters().batch_size == 8

    panel.batchSizeSpinBox.setValue(4)
    panel.deviceComboBox.setCurrentText("cpu")
    assert panel.inferenceParameters().batch_size == 4
    assert panel.inferenceParameters().device == "cpu"


def test_context_disables_actions_and_exposes_reasons(qtbot: QtBot) -> None:
    panel = _panel(qtbot)

    panel.setContext("pendulum.mp4", "bob", "Need three manual points", None, False)

    assert "pendulum.mp4" in panel.contextLabel.text()
    assert "bob" in panel.contextLabel.text()
    assert not panel.trainButton.isEnabled()
    assert panel.trainReasonLabel.text() == "Need three manual points"
    assert panel.inferButton.isEnabled()
    assert panel.cancelButton.isEnabled() is False

    panel.setContext("pendulum.mp4", "bob", None, None, True)
    assert not panel.trainButton.isEnabled()
    assert not panel.inferButton.isEnabled()
    assert panel.cancelButton.isEnabled()
    assert "running" in panel.trainReasonLabel.text().lower()


def test_models_filter_current_track_but_history_keeps_all_runs(qtbot: QtBot) -> None:
    panel = _panel(qtbot)
    video_id = uuid4()
    track_id = uuid4()
    other_track_id = uuid4()
    selected = mark_run_completed(
        create_tracking_run(video_id, track_id, "train"),
        model_snapshot="models/snapshot.pt",
    )
    other_track = mark_run_completed(
        create_tracking_run(video_id, other_track_id, "train"),
        model_snapshot="models/other.pt",
    )
    infer = mark_run_completed(create_tracking_run(video_id, track_id, "infer"))

    panel.setRuns((selected, other_track, infer), track_id)

    assert panel.modelList.count() == 1
    assert panel.historyList.count() == 3
    panel.modelList.setCurrentRow(0)
    assert panel.selectedTrainingRunId() == selected.run_id

    emitted = []
    panel.runSelected.connect(emitted.append)
    panel.historyList.setCurrentRow(1)
    assert emitted == [other_track.run_id]


def test_activity_progress_unknown_state_and_bounded_log(qtbot: QtBot) -> None:
    panel = _panel(qtbot)

    panel.setActivity("Training", step=3, total=10, loss=0.125, learning_rate=0.001)
    assert panel.stageLabel.text() == "Training"
    assert panel.progressBar.maximum() == 10
    assert panel.progressBar.value() == 3
    assert "loss=0.125" in panel.metricsLabel.text()
    assert "lr=0.001" in panel.metricsLabel.text()

    panel.setActivity("Preparing")
    assert panel.progressBar.minimum() == 0
    assert panel.progressBar.maximum() == 0

    panel.setLog("old")
    for index in range(2_500):
        panel.appendLog(str(index))
    assert panel.logText.document().blockCount() <= 2_000
    assert "2499" in panel.logText.toPlainText()


def test_task_panel_activation_controls_and_state_transitions(qtbot: QtBot) -> None:
    from ai_physics_tracker.application.refinement_history import (
        RefinementState,
        ValidationLabelSnapshot,
        ValidationSeries,
    )

    panel = _panel(qtbot)
    video_id = uuid4()
    track_id = uuid4()

    run1 = mark_run_completed(create_tracking_run(video_id, track_id, "infer"))
    run2 = mark_run_completed(create_tracking_run(video_id, track_id, "infer"))

    panel.setRuns((run1, run2), track_id)
    panel.setRefinementInfo(
        active_status="none",
        active_run_id=None,
        ref_state=None,
        validation_valid=False,
        validation_reason=None,
    )

    assert "None" in panel.activeRunLabel.text()
    assert "None" in panel.activeValidationLabel.text()
    assert not panel.activateButton.isEnabled()
    assert not panel.replaceButton.isEnabled()
    assert not panel.clearActivationButton.isEnabled()

    # Select Run 1 (candidate, not active, no other active run)
    panel.historyList.setCurrentRow(0)
    assert panel.activateButton.isEnabled()
    assert not panel.replaceButton.isEnabled()
    assert not panel.clearActivationButton.isEnabled()

    # Click Activate
    emitted_activate = []
    panel.activateRunRequested.connect(emitted_activate.append)
    panel.activateButton.click()
    assert emitted_activate == [run1.run_id]

    # Now simulate Run 1 becoming active
    val_series = ValidationSeries(
        series_id=uuid4(),
        name="Test Series",
        created_at="2026-09-03T12:00:00Z",
        label_snapshots=(
            ValidationLabelSnapshot(uuid4(), 1, 10.0, 20.0, "2026-09-03T12:00:00Z"),
            ValidationLabelSnapshot(uuid4(), 3, 30.0, 40.0, "2026-09-03T12:00:00Z"),
        ),
    )
    ref_state = RefinementState(
        active_infer_run_id=run1.run_id,
        active_validation_series_id=val_series.series_id,
        validation_series=(val_series,),
    )
    panel.setRefinementInfo(
        active_status="active",
        active_run_id=run1.run_id,
        ref_state=ref_state,
        validation_valid=True,
        validation_reason=None,
    )

    assert str(run1.run_id)[:8] in panel.activeRunLabel.text()
    assert "Test Series" in panel.activeValidationLabel.text()
    assert "2 frames, Valid" in panel.activeValidationLabel.text()

    # Since row 0 (Run 1) is active: Activate and Replace disabled, Clear enabled
    assert not panel.activateButton.isEnabled()
    assert not panel.replaceButton.isEnabled()
    assert panel.clearActivationButton.isEnabled()

    # Select Run 2 (completed, not active, but track HAS active run): Replace enabled!
    panel.historyList.setCurrentRow(1)
    assert not panel.activateButton.isEnabled()
    assert panel.replaceButton.isEnabled()
    assert panel.clearActivationButton.isEnabled()

    # Click Replace
    emitted_replace = []
    panel.replaceRunRequested.connect(emitted_replace.append)
    panel.replaceButton.click()
    assert emitted_replace == [run2.run_id]

    # Click Clear
    emitted_clear = []
    panel.clearActivationRequested.connect(lambda: emitted_clear.append(True))
    panel.clearActivationButton.click()
    assert emitted_clear == [True]

    # Click Validation
    emitted_val = []
    panel.manageValidationRequested.connect(lambda: emitted_val.append(True))
    panel.manageValidationButton.click()
    assert emitted_val == [True]

    # Verify history list labels
    assert "Active" in panel.historyList.item(0).text()
    assert "Completed · Not active" in panel.historyList.item(1).text()

    # Cross-track infer run should NOT enable activate or replace buttons
    other_track_id = uuid4()
    run_other = mark_run_completed(create_tracking_run(video_id, other_track_id, "infer"))
    train_raw = mark_run_completed(create_tracking_run(video_id, track_id, "train"))
    train_with_iter = replace(
        train_raw,
        extra_fields={"refinement_iteration_v1": {"iteration_index": 1}},
    )
    panel.setRuns((run1, run2, run_other, train_with_iter), track_id)
    assert "iter 1" in panel.historyList.item(3).text()

    # Selecting cross-track run
    panel.historyList.setCurrentRow(2)
    assert not panel.activateButton.isEnabled()
    assert not panel.replaceButton.isEnabled()

    # Busy state disables all activation and validation buttons
    panel.setContext("vid.mp4", "track", None, None, busy=True)
    assert not panel.activateButton.isEnabled()
    assert not panel.replaceButton.isEnabled()
    assert not panel.clearActivationButton.isEnabled()
    assert not panel.manageValidationButton.isEnabled()

    # Legacy status display
    panel.setContext("vid.mp4", "track", None, None, busy=False)
    panel.setRefinementInfo("legacy_inferred", run1.run_id, None, False, None)
    assert "(legacy)" in panel.activeRunLabel.text()
    panel.setRefinementInfo("legacy_mixed", None, None, False, None)
    assert "Legacy mixed" in panel.activeRunLabel.text()



def test_run_details_expose_iteration_traceability(qtbot: QtBot) -> None:
    """Entry Gate：train run details 展示 label 数/审核摘要/coverage/可比性。"""
    from ai_physics_tracker.application.refinement_history import (
        RefinementState, ValidationLabelSnapshot, ValidationSeries,
    )
    from datetime import UTC, datetime

    panel = _panel(qtbot)
    track_id = uuid4()
    run_id = uuid4()
    source_infer_id = uuid4()
    series_id = uuid4()
    now = datetime.now(UTC).isoformat()

    snapshot = ValidationLabelSnapshot(
        point_id=uuid4(), frame_index=10, pixel_x=1.0, pixel_y=2.0,
        modified_at=now,
    )
    series = ValidationSeries(
        series_id=series_id, name="Val", created_at=now,
        label_snapshots=(snapshot,),
    )
    panel.setRefinementInfo(
        active_status="active", active_run_id=None,
        ref_state=RefinementState(
            active_validation_series_id=series_id,
            validation_series=(series,),
        ),
        validation_valid=True, validation_reason=None,
    )

    run = mark_run_completed(
        create_tracking_run(track_id, track_id, "train", engine="dlc"),
        model_snapshot="data/engines/x/snapshot.pt",
    )
    source_run = mark_run_completed(
        create_tracking_run(track_id, track_id, "infer", engine="dlc"),
        model_snapshot="data/engines/y/snapshot.pt",
    )
    source_run = replace(source_run, extra_fields={
        "prediction_summary_v1": {"coverage": 0.93, "row_count": 100},
    })
    run = replace(run, extra_fields={
        "refinement_iteration_v1": {
            "iteration_index": 1,
            "previous_training_run_id": None,
            "source_infer_run_id": str(source_infer_id),
            "validation_series_id": str(series_id),
            "training_labels": [{"frame_index": 10}],
            "review_summary": {"total_candidates": 10, "reviewed_count": 7,
                               "pending_count": 3, "accepted_count": 4,
                               "corrected_count": 2, "skipped_count": 1},
            "training_mode": "resume",
            "resume_from_training_run_id": str(uuid4()),
        },
        "evaluation": {"status": "completed"},
    })
    run = replace(run, config={**run.config, "epochs": 25, "training_mode": "resume"})
    panel._runs_by_id = {source_infer_id: source_run, run_id: run}

    panel.setRunDetails(run)
    text = panel.detailsLabel.text()
    assert "iteration=1" in text
    assert "training_mode=resume" in text
    assert "resume_source=" in text
    assert "epochs_this_run=25" in text
    assert "training_labels=1" in text
    assert "validation_labels=1" in text
    assert str(series_id) in text
    assert "pending_count=3" in text
    assert "remaining_candidates=3" in text
    assert "prediction_coverage=93.0%" in text

    # 无固定验证集的 train run：明示不可跨轮比较
    run_no_val = replace(run, extra_fields={
        "refinement_iteration_v1": {
            "iteration_index": 0,
            "source_infer_run_id": None,
            "validation_series_id": None,
            "training_labels": [{"frame_index": 1}, {"frame_index": 2}],
            "training_mode": "restart",
            "resume_from_training_run_id": None,
        },
    })
    panel.setRunDetails(run_no_val)
    text = panel.detailsLabel.text()
    assert "training_labels=2" in text
    assert "training_mode=restart" in text
    assert "resume_source" not in text
    assert "no fixed validation" in text
    assert "cross-iteration RMSE comparison unavailable" in text
