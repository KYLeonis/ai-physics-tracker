"""P6R-01 GUI 路径：撤销越过已登记 AI 任务时的原子拒绝反馈（offscreen）。"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.tracking_run import create_tracking_run
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _window() -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )


def test_undo_button_rejects_crossing_registered_task_without_corrupting(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()

    session = window._annotation_session
    assert session is not None
    track = session.tracks[0]
    session.mark_point(track.track_id, 0, 10.0, 10.0)
    session.mark_point(track.track_id, 1, 12.0, 12.0)
    session.record_tracking_run(
        create_tracking_run(track.video_id, track.track_id, "train", engine_version="mock")
    )

    # 两次撤销标注本身合法
    window.undoButton.click()
    window.undoButton.click()
    assert len(session.tracks) == 1

    # 第三次撤销（建 Track）被会话层原子拒绝：GUI 给出可见反馈、状态不变
    window.undoButton.click()
    message = window.statusBar().currentMessage()
    assert message.startswith("Undo unavailable:")
    assert len(session.tracks) == 1
    assert len(session.project.tracking_runs) == 1
    assert session.can_undo
    # 标注撤销后 redo 仍然可用（会话未被毒化）
    window.redoButton.click()
    assert len(session.manual_points(track.track_id)) == 1
