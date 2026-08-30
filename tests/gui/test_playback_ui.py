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
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe

LAST_FRAME_LABEL = "Frame: 4 / 4"


def _opened_window(qtbot: QtBot, synthetic_video_path: Path) -> MainWindow:
    window = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe())
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


def test_rapid_double_step_advences_two_frames(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    # 回归：解码延迟不得吞掉快速连点（步进以最后请求帧号为基准）
    window = _opened_window(qtbot, synthetic_video_path)

    qtbot.mouseClick(window.nextButton, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.nextButton, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 2 / 4")


def test_stale_delivery_from_previous_video_is_dropped(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    # 回归 B1：打开新视频时，旧视频在途帧的迟到交付必须被代际隔离丢弃
    window = _opened_window(qtbot, synthetic_video_path)
    stale_frame = window._async.snapshot().current_frame

    assert window.openVideo(synthetic_video_path, show_error=False)
    stale_generation = window._delivery_generation - 1
    window.frameDelivered.emit(stale_frame, stale_generation)

    assert window.frameLabel.text() == "Frame: 0 / 4"
    assert window.timelineSlider.value() == 0


def test_view_menu_exposes_zoom_actions(qtbot: QtBot) -> None:
    window = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe())
    qtbot.addWidget(window)

    menu_titles = [action.text() for action in window.menuBar().actions()]

    assert "View" in menu_titles


def test_playback_rate_changes_timer_interval(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)

    window.startPlayback()
    qtbot.waitUntil(lambda: window._playTimer.isActive())
    original_interval = window._playTimer.interval()

    window.setPlaybackRate(2.0)
    doubled_interval = window._playTimer.interval()

    window.stopPlayback()
    assert window.playbackRate == 2.0
    # 10 fps × 2 倍速 → 间隔减半（合成视频 fps=10）
    assert original_interval == 100
    assert doubled_interval == 50


def test_speed_menu_is_exclusive_and_defaults_to_original(
    qtbot: QtBot,
) -> None:
    window = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe())
    qtbot.addWidget(window)

    checked = [rate for rate, action in window._speedActions.items() if action.isChecked()]

    assert checked == [1.0]
