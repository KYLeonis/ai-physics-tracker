"""Phase 2.1 桌面外壳的 Qt offscreen 测试。"""

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QMessageBox, QScrollArea
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video import (
    DecodedFrame,
    VideoFrameError,
    VideoStreamInfo,
)
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe


def _window() -> MainWindow:
    return MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe())


def test_main_chart_and_ai_panels_allow_window_resizing(qtbot: QtBot) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()

    window.resize(900, 520)
    assert window.size().width() == 900
    assert window.size().height() == 520
    assert window.centralWidget().findChild(QScrollArea) is not None
    assert not window.isFullScreen()
    assert not window.isMaximized()

    for panel in (window.chartActions.panel, window.trackingActions.panel):
        assert isinstance(panel.widget(), QScrollArea)
        assert not panel.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable

    window.resize(1100, 760)
    assert window.size().width() == 1100
    assert window.size().height() == 760


def test_main_window_opens_video_and_navigates_frames(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()

    assert window.openVideo(synthetic_video_path, show_error=False)
    assert window.videoView.hasFrame()
    assert window.frameSpinBox.value() == 0
    assert window.frameLabel.text() == "Frame: 0 / 4"
    assert window.timeLabel.text() == "Time: 0.000 s nominal"
    assert not window.previousButton.isEnabled()

    qtbot.mouseClick(window.nextButton, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 1 / 4")
    assert window.timeLabel.text() == "Time: 0.100 s nominal"

    window.frameSpinBox.setValue(4)
    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 4 / 4")
    assert not window.nextButton.isEnabled()

    window.close()
    renamed = synthetic_video_path.with_name("gui-closed.avi")
    synthetic_video_path.rename(renamed)
    assert renamed.is_file()


def test_main_window_reports_invalid_path_without_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window()
    qtbot.addWidget(window)

    assert not window.openVideo(tmp_path / "missing.mp4", show_error=False)
    assert window.frameLabel.text() == "Frame: —"
    assert "not found" in window.statusBar().currentMessage()


def test_failed_jump_restores_spinbox_to_current_frame(
    qtbot: QtBot, monkeypatch
) -> None:
    class FailingReader:
        is_open = False
        info = VideoStreamInfo(8, 6, 10.0, 3, "fake", "cfr")

        def open(self, path: Path) -> VideoStreamInfo:
            self.is_open = True
            return self.info

        def read_frame(self, frame_index: int) -> DecodedFrame:
            if frame_index == 2:
                raise VideoFrameError("synthetic decode failure")
            return DecodedFrame(frame_index, np.zeros((6, 8, 3), dtype=np.uint8))

        def close(self) -> None:
            self.is_open = False

    window = MainWindow(lambda: VideoSession(FailingReader()), ProjectRepository(), FFprobeTimingProbe())
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: QMessageBox.Ok)
    assert window.openVideo(Path("fake.video"), show_error=False)

    window.frameSpinBox.setValue(2)
    qtbot.waitUntil(lambda: window.frameSpinBox.value() == 0)
    assert window.frameLabel.text() == "Frame: 0 / 2"
