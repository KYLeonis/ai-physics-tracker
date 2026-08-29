"""Qt offscreen tests for the Phase 2.1 desktop shell."""

from pathlib import Path

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


def _window() -> MainWindow:
    return MainWindow(VideoSession(OpenCVVideoReader()))


def test_main_window_opens_video_and_navigates_frames(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()

    assert window.openVideo(synthetic_video_path, show_error=False)
    assert window.videoView.pixmap() is not None
    assert window.frameSpinBox.value() == 0
    assert window.frameLabel.text() == "Frame: 0 / 4"
    assert window.timeLabel.text() == "Time: 0.000 s nominal"
    assert not window.previousButton.isEnabled()

    qtbot.mouseClick(window.nextButton, Qt.MouseButton.LeftButton)

    assert window.frameSpinBox.value() == 1
    assert window.frameLabel.text() == "Frame: 1 / 4"
    assert window.timeLabel.text() == "Time: 0.100 s nominal"

    window.frameSpinBox.setValue(4)

    assert window.frameLabel.text() == "Frame: 4 / 4"
    assert not window.nextButton.isEnabled()


def test_main_window_reports_invalid_path_without_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window()
    qtbot.addWidget(window)

    assert not window.openVideo(tmp_path / "missing.mp4", show_error=False)
    assert window.frameLabel.text() == "Frame: —"
    assert "not found" in window.statusBar().currentMessage()
