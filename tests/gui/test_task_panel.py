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
