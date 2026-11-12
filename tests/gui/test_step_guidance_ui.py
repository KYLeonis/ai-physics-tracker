"""UX-04/05 引导与降噪回归：步骤"做什么+为什么"tooltip、阶段过滤 Limits、引导镜像状态栏。"""

from PySide6.QtWidgets import QApplication

from ai_physics_tracker.application.workflow_projection import ActionSpec, TaskCard
from ai_physics_tracker.gui.task_panel import TaskPanel
from ai_physics_tracker.gui.tracking_actions import visible_limitations
from ai_physics_tracker.gui.workflow_header import WorkflowHeader


def _card() -> TaskCard:
    primary = ActionSpec("guided_marking", "2 · Label recommended frames",
                         hint="Teach by example: click the four points per frame.")
    secondary = (
        ActionSpec("pick_landmark_frames", "1 · Recommend 20 frames", enabled=False,
                   reason="Save the project first",
                   hint="Pick the most informative frames."),
        ActionSpec("train_current_labels", "3 · Train / retrain with current labels",
                   hint="The AI learns your labels."),
    )
    return TaskCard("setup", "Next: 2 · Label recommended frames", ("line",), primary, secondary)


def test_task_panel_shows_purpose_hints_and_prefers_disable_reasons(qtbot):
    panel = TaskPanel()
    qtbot.addWidget(panel)
    panel.setTaskCard(_card())
    assert "four points" in panel.cardPrimaryButton.toolTip()
    # 禁用项必须显示禁用原因，hint 只作后备
    assert panel.cardSecondaryButtonA.toolTip() == "Save the project first"
    assert "learns your labels" in panel.cardSecondaryButtonB.toolTip()


def test_workflow_header_shows_purpose_hints(qtbot):
    header = WorkflowHeader()
    qtbot.addWidget(header)
    header.setTaskCard(_card())
    buttons = list(header.nextStepButtons)
    assert any("four points" in b.toolTip() for b in buttons)
    assert any(b.toolTip() == "Save the project first" for b in buttons)


def test_acquire_workspace_hides_analysis_setup_limitations():
    items = (
        "Setup missing: fixed_pivot, true_vertical, active_calibration",
        "Timing not authorized — use the timing controls in Setup",
        "No adopted measurement — activate a reviewed candidate in Acquire",
    )
    acquire = visible_limitations(items, "acquire")
    assert acquire == (items[1], items[2])
    assert visible_limitations(items, "analysis") == items


def test_calibration_guide_mirrors_to_status_bar(qtbot, synthetic_video_path):
    from ai_physics_tracker.application.video_session import VideoSession
    from ai_physics_tracker.gui.main_window import MainWindow
    from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
    from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
    from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

    window = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe())
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window._setCalibrationGuide("Frame 3: click the body_top (1/4 done)")
    assert window.statusBar().currentMessage() == "Frame 3: click the body_top (1/4 done)"
    assert window.calibrationGuideLabel.text() == "Frame 3: click the body_top (1/4 done)"


def test_activity_progress_shows_counter_and_percent(qtbot):
    from ai_physics_tracker.gui.task_panel import TaskPanel

    panel = TaskPanel()
    qtbot.addWidget(panel)
    panel.setActivity("Training", 4, 50, 0.0134, 0.001, unit="epoch")
    assert panel.stageLabel.text() == "Training · epoch 4/50 · 8%"
    assert panel.progressBar.maximum() == 50 and panel.progressBar.value() == 4
    assert "loss" in panel.metricsLabel.text()

    panel.setActivity("Inference", 120, 200, unit="frame")
    assert panel.stageLabel.text() == "Inference · frame 120/200 · 60%"

    panel.setActivity("Training")
    assert panel.stageLabel.text() == "Training"
    assert panel.progressBar.format() == "Working…"

    panel.setActivity("Completed")
    assert panel.progressBar.value() == 1 and panel.progressBar.maximum() == 1
