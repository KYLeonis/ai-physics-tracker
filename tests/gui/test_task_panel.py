"""TaskPanel 的参数、禁用原因、模型选择和有界日志测试。"""

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

