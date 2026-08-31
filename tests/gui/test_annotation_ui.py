"""Phase 2.3 手工标注的 Qt offscreen 测试。

验证 phase2-requirements.md §2 R5 交互契约：选中 Track 进入标注
模式、点击落点（mapScreenToPixel 换算）、同帧 last-wins、overlay
同步、Esc/列表空白退出标注模式（决策 D1=A / D2=点击空白算退出）。
"""

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe


def _window() -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )


def _opened_with_track(qtbot: QtBot, synthetic_video_path: Path) -> MainWindow:
    window = _window()
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    return window


def test_add_track_lists_and_selects_it(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)

    assert window.trackList.count() == 1
    assert window.trackList.item(0).text() == "Track 1"
    assert window._selected_track_id is not None
    assert window.videoView.is_annotation_mode()

    window.addTrackButton.click()
    assert window.trackList.count() == 2
    assert window.trackList.item(1).text() == "Track 2"


def test_annotation_click_marks_point_and_overlays_it(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)

    # 合成视频 64x48，fit 模式下点击中心 → 像素 ≈ (32, 24)
    center = QPoint(window.videoView.viewport().width() // 2,
                    window.videoView.viewport().height() // 2)
    window._onAnnotationClicked(center)

    session = window._annotation_session
    assert session is not None
    assert session.is_dirty
    points = session.manual_points(session.tracks[0].track_id)
    assert len(points) == 1
    assert points[0].frame_index == 0
    assert abs(points[0].pixel_x - 32.0) <= 1.5
    assert abs(points[0].pixel_y - 24.0) <= 1.5
    assert window.videoView.marker_count() == 1


def _inside_point(window: MainWindow, pixel_x: float, pixel_y: float) -> QPoint:
    """图像像素坐标 → 保证命中的 viewport 坐标（不依赖 fit 布局）。"""

    return window.videoView.mapFromScene(QPointF(pixel_x, pixel_y))


def test_same_frame_reclick_replaces_point(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)

    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))
    window._onAnnotationClicked(_inside_point(window, 40.0, 30.0))

    session = window._annotation_session
    assert session is not None
    points = session.manual_points(session.tracks[0].track_id)
    assert len(points) == 1  # manual last-wins：旧点硬删除（data-model §4.2）
    assert window.videoView.marker_count() == 1


def test_escape_and_empty_list_click_exit_annotation_mode(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)
    assert window.videoView.is_annotation_mode()

    window._exitAnnotationMode()

    assert window._selected_track_id is None
    assert not window.videoView.is_annotation_mode()
    assert window.trackList.currentRow() == -1
    # 退出后点击画面不再落点
    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))
    session = window._annotation_session
    assert session is not None
    assert session.manual_points(session.tracks[0].track_id) == ()
    assert window.videoView.marker_count() == 0


def test_delete_track_clears_markers_and_selection(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)
    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))
    assert window.videoView.marker_count() == 1

    window.deleteTrackButton.click()

    assert window.trackList.count() == 0
    assert window.videoView.marker_count() == 0
    assert window._selected_track_id is None
    session = window._annotation_session
    assert session is not None
    assert session.tracks == ()
    assert session.project.observations == ()


def test_markers_trail_across_frames_with_current_highlight(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    # 拖尾语义：显示该 Track 全部 active 点；当前帧实心、其余空心
    window = _opened_with_track(qtbot, synthetic_video_path)
    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))
    qtbot.waitUntil(lambda: window.videoView.marker_count() == 1)
    assert window.videoView.marker_views()[0].is_current_frame

    window.frameSpinBox.setValue(2)
    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 2 / 4")
    qtbot.waitUntil(
        lambda: not window.videoView.marker_views()[0].is_current_frame
    )

    assert window.videoView.marker_count() == 1  # 帧 0 的点仍以空心环显示


def test_click_outside_image_is_ignored(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)

    window._onAnnotationClicked(QPoint(10000, 10000))

    session = window._annotation_session
    assert session is not None
    assert session.manual_points(session.tracks[0].track_id) == ()
    assert window.videoView.marker_count() == 0


def test_track_actions_without_video_are_noop(qtbot: QtBot) -> None:
    window = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )
    qtbot.addWidget(window)

    window.addTrackButton.click()
    window._onAnnotationClicked(QPoint(10, 10))

    assert window._annotation_session is None
    assert window.trackList.count() == 0


def test_click_while_frame_in_flight_is_rejected(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    # 回归（独立 review B2）：跳帧请求在途时点击不得落点，
    # 避免把旧帧图像上的坐标写进新帧
    window = _opened_with_track(qtbot, synthetic_video_path)

    window.frameSpinBox.setValue(4)  # 触发在途解码请求
    assert window._has_pending_request
    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))

    session = window._annotation_session
    assert session is not None
    assert session.manual_points(session.tracks[0].track_id) == ()
    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 4 / 4")


def test_real_mouse_click_in_annotation_mode_marks_point(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)

    target = _inside_point(window, 32.0, 24.0)
    qtbot.mouseClick(
        window.videoView.viewport(), Qt.MouseButton.LeftButton, pos=target
    )

    session = window._annotation_session
    assert session is not None
    points = session.manual_points(session.tracks[0].track_id)
    assert len(points) == 1
    assert abs(points[0].pixel_x - 32.0) <= 1.5
    assert abs(points[0].pixel_y - 24.0) <= 1.5


def test_undo_redo_buttons_drive_annotation_state(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)
    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))
    qtbot.waitUntil(lambda: window.videoView.marker_count() == 1)
    assert window.undoButton.isEnabled()
    assert not window.redoButton.isEnabled()

    window.undoButton.click()

    assert window.videoView.marker_count() == 0
    # add_track 本身也可撤销：一次 undo 后按钮仍可用
    assert window.undoButton.isEnabled()
    assert window.redoButton.isEnabled()

    window.redoButton.click()

    assert window.videoView.marker_count() == 1


def test_undo_after_track_deletion_restores_track(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_with_track(qtbot, synthetic_video_path)
    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))
    qtbot.waitUntil(lambda: window.videoView.marker_count() == 1)
    window.deleteTrackButton.click()
    assert window.trackList.count() == 0

    window.undoButton.click()

    assert window.trackList.count() == 1
    assert window.videoView.marker_count() == 1
    # 选择随撤销恢复（track 重新出现并保持选中）
    assert window._selected_track_id is not None


def test_multiselection_overlays_all_selected_tracks(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    # HR 反馈：同时选中 Track 1 与 Track 2 → overlay 同时显示两条轨迹的点
    window = _opened_with_track(qtbot, synthetic_video_path)
    session = window._annotation_session
    assert session is not None
    track_one = session.tracks[0]
    window._onAnnotationClicked(_inside_point(window, 20.0, 15.0))
    qtbot.waitUntil(lambda: window.videoView.marker_count() == 1)
    window.addTrackButton.click()  # 新 Track 成为唯一选中并是标注目标
    track_two = session.tracks[1]
    assert window._selected_track_id == track_two.track_id

    # 两条轨迹各有真实点；当前项仍是 Track 2。
    window.frameSpinBox.setValue(1)
    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 1 / 4")
    window._onAnnotationClicked(_inside_point(window, 40.0, 30.0))
    qtbot.waitUntil(lambda: window.videoView.marker_count() == 1)
    window.trackList.item(0).setSelected(True)
    window._onTrackSelectionChanged()

    markers = window.videoView.marker_views()
    assert len(markers) == 2
    assert {marker.color for marker in markers} == {track_one.color, track_two.color}
    assert sum(marker.is_current_frame for marker in markers) == 1
    assert next(marker for marker in markers if marker.is_current_frame).color == track_two.color

    # 标注目标仍是 currentItem（Track 2），新增点不得落到 Track 1。
    window.frameSpinBox.setValue(2)
    qtbot.waitUntil(lambda: window.frameLabel.text() == "Frame: 2 / 4")
    window._onAnnotationClicked(_inside_point(window, 45.0, 32.0))
    qtbot.waitUntil(lambda: window.videoView.marker_count() == 3)
    assert window._selected_track_id == track_two.track_id
    assert len(session.manual_points(track_one.track_id)) == 1
    assert len(session.manual_points(track_two.track_id)) == 2
    assert session.manual_points(track_two.track_id)[-1].frame_index == 2


def test_deselect_all_exits_annotation_target(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    # 回归：clearSelection 后 currentItem 残留不得复活旧标注目标
    window = _opened_with_track(qtbot, synthetic_video_path)
    window.trackList.clearSelection()
    window._onTrackSelectionChanged()

    assert window._selected_track_id is None
    assert not window.videoView.is_annotation_mode()
