"""Phase 2.2 播放控制与时间轴的 Qt offscreen 测试。

合成视频为 5 帧 10 fps（conftest），播放全程依赖真实解码回调，
验证 phase2-requirements.md §2 R3：播放不阻塞 GUI、scrub/commit 分离。
"""

from pathlib import Path

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader

LAST_FRAME_LABEL = "Frame: 4 / 4"


def _opened_window(qtbot: QtBot, synthetic_video_path: Path) -> MainWindow:
    window = MainWindow(VideoSession(OpenCVVideoReader()))
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    return window


def test_playback_runs_to_last_frame_and_pauses(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)

    window.startPlayback()
    assert window.isPlaying

    qtbot.waitUntil(lambda: window.frameLabel.text() == LAST_FRAME_LABEL, timeout=5000)
    qtbot.waitUntil(lambda: not window.isPlaying)

    assert window.playButton.text() == "Play"
    assert window.timelineSlider.value() == 4


def test_play_button_and_toggle_pause_playback(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)

    qtbot.mouseClick(window.playButton, Qt.MouseButton.LeftButton)
    assert window.isPlaying

    window.togglePlayback()
    assert not window.isPlaying


def test_replay_from_end_restarts_at_first_frame(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    window.frameSpinBox.setValue(4)
    qtbot.waitUntil(lambda: window.frameLabel.text() == LAST_FRAME_LABEL)

    window.startPlayback()

    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 1 / 4", timeout=5000)


def test_scrub_commits_final_slider_position(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)

    window.timelineSlider.setSliderDown(True)
    window.timelineSlider.sliderPressed.emit()
    window.timelineSlider.sliderMoved.emit(2)
    window.timelineSlider.sliderMoved.emit(3)
    window.timelineSlider.setSliderPosition(3)
    window.timelineSlider.sliderReleased.emit()
    window.timelineSlider.setSliderDown(False)

    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 3 / 4")
    assert window.timelineSlider.value() == 3


def test_scrub_pauses_active_playback(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    window.startPlayback()
    assert window.isPlaying

    window.timelineSlider.sliderPressed.emit()

    assert not window.isPlaying


def test_manual_step_pauses_active_playback(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    window.startPlayback()

    qtbot.mouseClick(window.nextButton, Qt.MouseButton.LeftButton)

    assert not window.isPlaying
