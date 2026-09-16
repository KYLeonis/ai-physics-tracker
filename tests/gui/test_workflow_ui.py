"""Phase 5.7 — 工作区切换、常驻状态头与任务卡的 GUI 冒烟（offscreen）。

重点测状态与语义（卡片内容、工作区可见性、导航不改数据），不测像素布局。
"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _window() -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )


def test_three_workspaces_switch_without_touching_data(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    session = window.analysisSession
    assert session is not None
    session.mark_point(session.tracks[0].track_id, 0, 10.0, 10.0)
    observations_before = session.project.observations

    assert window.currentWorkspace == "acquire"
    assert window.trackingActions.panel.isVisible()

    # 切到分析：视频参照重挂、任务面板隐藏、图表可见
    window.setWorkspace("analysis")
    assert window.currentWorkspace == "analysis"
    assert window.chartActions.panel.isVisible()
    assert not window.trackingActions.panel.isVisible()
    assert window.videoView.parent() is not None  # 仍存活，只是换了宿主

    # 切到实验设置：回到视频页，数据不变（导航只改视图）
    window.setWorkspace("setup")
    assert window.currentWorkspace == "setup"
    assert session.project.observations == observations_before

    # 切回获取轨迹：视频视图回到原列
    window.setWorkspace("acquire")
    assert window.trackingActions.panel.isVisible()


def test_header_shows_context_and_card_follows_projection(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()

    # 无项目：卡片为空、状态头显示 No project
    assert window.workflowHeader.contextLabel.text() == "No project"
    assert not window.trackingActions.panel.cardPrimaryButton.isVisible()

    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    session = window.analysisSession
    track = session.tracks[0]

    # 保存（选帧/学习前置）后：卡片进入标注模式（<3 帧）
    session.save_as(tmp_path / "proj")
    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    card = window.trackingActions.panel
    assert "mark example positions" in card.cardTitleLabel.text()
    assert card.cardPrimaryButton.text() == "Pick representative frames"

    # 状态头显示项目/视频/目标/范围
    header_text = window.workflowHeader.contextLabel.text()
    assert "Project:" in header_text and "Object:" in header_text and "Range:" in header_text
    assert window.workflowHeader.trajectoryLabel.text().startswith("Current trajectory:")


def test_card_running_task_shows_cancel(qtbot: QtBot, synthetic_video_path: Path,
                                         tmp_path: Path) -> None:
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                               _FakeRunner(_FakeHandle()))
    panel = window.trackingActions.panel

    # 该 fixture 已标 3 帧：卡片进入“可开始学习”（系统备好计划，用户显式启动）
    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    assert panel.cardPrimaryButton.text() == "Start learning"
    assert "fixed-check" in panel.evidenceTextLabel.text()

    # 清空标注路径不可行（保存后），改用直接验证选帧运行卡片：手动触发选帧
    window.frameSelectionActions.requestSuggestion(n_frames=5, algorithm="kmeans")
    assert window.frameSelectionActions.busy
    qtbot.waitUntil(
        lambda: panel.cardTitleLabel.text().startswith("Current: picking"),
        timeout=3000)
    assert panel.cardPrimaryButton.text() == "Cancel"
