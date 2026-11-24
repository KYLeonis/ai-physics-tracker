"""UX-07/08 标注辅助回归：4/4 自动下一帧勾选、全幅细准线。"""

import numpy as np
import pytest
from PySide6.QtCore import QPoint

from test_model_actions_ui import _experiment_window, long_video_path  # noqa: F401
from ai_physics_tracker.application.video import DecodedFrame
from ai_physics_tracker.gui.video_view import VideoView


def _frame(w=64, h=48):
    return DecodedFrame(frame_index=0, pixels_rgb=np.full((h, w, 3), 120, dtype=np.uint8))


def test_crosshair_guides_follow_mouse_only_in_annotation_mode(qtbot):
    view = VideoView()
    qtbot.addWidget(view)
    view.resize(320, 240)
    view.show()
    view.setFrame(_frame())
    centre = QPoint(view.viewport().width() // 2, view.viewport().height() // 2)
    view.set_annotation_mode(False)
    view._update_crosshair(centre)
    assert not view._crosshair_v.isVisible()
    assert not view._crosshair_h.isVisible()

    view.set_annotation_mode(True)
    view._update_crosshair(centre)
    assert view._crosshair_v.isVisible() and view._crosshair_h.isVisible()
    line = view._crosshair_v.line()
    assert line.y1() == 0.0 and line.y2() == 48.0  # 贯穿整幅画面
    assert view._crosshair_v.pen().widthF() == 0.0  # 1px 细线

    view.set_annotation_mode(False)
    assert not view._crosshair_v.isVisible()


@pytest.mark.parametrize("mode", ["scale", "origin", "pivot", "vertical"])
def test_leaving_calibration_hides_stationary_crosshair(qtbot, mode):
    view = VideoView()
    qtbot.addWidget(view)
    view.resize(320, 240)
    view.show()
    view.setFrame(_frame())
    view.set_calibration_mode(mode)
    centre = QPoint(view.viewport().width() // 2, view.viewport().height() // 2)
    view._update_crosshair(centre)
    assert view._crosshair_v.isVisible() and view._crosshair_h.isVisible()

    view.set_calibration_mode(None)

    assert not view._crosshair_v.isVisible()
    assert not view._crosshair_h.isVisible()


def test_auto_advance_after_four_point_completion(qtbot, tmp_path, long_video_path, monkeypatch):
    import ai_physics_tracker.gui.main_window as main_window

    window, _, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
    window._guide_experiment_id = experiment.experiment_id
    monkeypatch.setattr(window, "_frameSetProgressSuffix", lambda e: "")

    class StubState:
        frame_complete = True
        next_frame_set_index = 7

        def hint(self):
            return "Frame complete."

    monkeypatch.setattr(main_window, "annotation_guide_state",
                        lambda *a, **k: StubState())
    jumps = []
    monkeypatch.setattr(window, "jumpToFrame", lambda frame: jumps.append(frame))

    window.autoAdvanceCheck.setChecked(False)
    window._refreshAnnotationGuide()
    assert not jumps
    assert "Next frame" in window.calibrationGuideButton.text()

    window.autoAdvanceCheck.setChecked(True)
    window._refreshAnnotationGuide()
    assert jumps == [7]


def test_review_prediction_marker_carries_text_label(qtbot):
    from ai_physics_tracker.gui.video_view import MarkerView

    view = VideoView()
    qtbot.addWidget(view)
    view.show()
    view.setFrame(_frame())
    view.set_review_prediction(MarkerView(30.0, 20.0, "#ffb000",
                                          source="preview", frame_index=3, label="AI"))
    item = view._review_prediction_item
    texts = [c.text() for c in item.childItems()
             if type(c).__name__ == "QGraphicsSimpleTextItem"]
    assert texts == ["AI"]

    # 无 label 的预览 marker 不显示文字
    view.set_review_prediction(MarkerView(31.0, 21.0, "#ffb000",
                                          source="preview", frame_index=3))
    item = view._review_prediction_item
    texts = [c.text() for c in item.childItems()
             if type(c).__name__ == "QGraphicsSimpleTextItem"]
    assert texts == []  # 无 label 的预览点不创建文字子项


def _send_mouse_move(view: VideoView, view_pos: QPoint) -> None:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(view_pos)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos,
        pos,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), event)


def test_pick_modes_hide_system_cursor_in_favour_of_hairlines(qtbot):
    # UX-16：拾取/标注模式仅在有帧且位于画面内时隐藏系统光标，退出恢复 ArrowCursor
    from PySide6.QtCore import Qt as _Qt

    view = VideoView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()

    view.set_annotation_mode(True)
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    view.setFrame(_frame())
    assert view._pixmap_item.cursor().shape() == _Qt.CursorShape.BlankCursor
    _send_mouse_move(view, view.mapFromScene(32.0, 24.0))
    assert view._crosshair_v.isVisible() and view._crosshair_h.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor

    for mode in ("scale", "origin", "pivot", "vertical"):
        view.set_calibration_mode(mode)
        assert view._pixmap_item.cursor().shape() == _Qt.CursorShape.BlankCursor
        _send_mouse_move(view, view.mapFromScene(32.0, 24.0))
        assert view._crosshair_v.isVisible() and view._crosshair_h.isVisible()
        assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor

    view.set_calibration_mode(None)
    assert view._pixmap_item.cursor().shape() == _Qt.CursorShape.ArrowCursor
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor


def test_cursor_remains_visible_in_black_margin_and_after_leave(qtbot):
    # UX-16：经真实 MouseMove 从画面移出到黑边或 Leave 后重入黑边，指针不得隐身
    from PySide6.QtCore import QEvent, Qt as _Qt
    from PySide6.QtWidgets import QApplication

    view = VideoView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    view.setFrame(_frame())
    view.set_annotation_mode(True)

    inside = view.mapFromScene(32.0, 24.0)
    outside = view.mapFromScene(-10.0, -10.0)

    _send_mouse_move(view, inside)
    assert view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor

    _send_mouse_move(view, outside)
    assert not view._crosshair_v.isVisible() and not view._crosshair_h.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    # 移回画面后再触发 viewport Leave（如滑到滚动条），然后重入黑边区域
    _send_mouse_move(view, inside)
    assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor
    QApplication.sendEvent(view.viewport(), QEvent(QEvent.Type.Leave))
    assert not view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    _send_mouse_move(view, outside)
    assert not view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor


def test_overlay_items_outside_frame_or_after_clear_keep_visible_cursor(qtbot):
    # 伸出画面外的叠加图元及 clearFrame 后的残留 marker 不得在无准线时触发 BlankCursor
    from PySide6.QtCore import Qt as _Qt
    from ai_physics_tracker.gui.video_view import MarkerView, PendulumOverlayView

    view = VideoView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    view.setFrame(_frame())
    view.set_annotation_mode(True)
    view.set_markers([MarkerView(32.0, 24.0, "#e6194b", True, "manual", 0)])
    # 垂直参考线靠近底边，使 "down — NOT confirmed" 标签落到画面外黑边区
    view.set_pendulum_overlay(
        PendulumOverlayView(vertical_top_px=(58.0, 44.0), vertical_bottom_px=(60.0, 46.0))
    )

    # 画面内移到 marker 上：准线显示、光标隐藏
    _send_mouse_move(view, view.mapFromScene(32.0, 24.0))
    assert view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor

    # 移到画面外标签位置：准线隐藏、光标必须保持 ArrowCursor
    _send_mouse_move(view, view.mapFromScene(75.0, 44.0))
    assert not view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    # clearFrame 后残留 marker 上方也必须恢复可见光标
    _send_mouse_move(view, view.mapFromScene(32.0, 24.0))
    view.clearFrame()
    assert not view.hasFrame()
    assert not view._crosshair_v.isVisible()
    _send_mouse_move(view, view.mapFromScene(32.0, 24.0))
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor


def test_shrinking_frame_hides_out_of_bounds_crosshair_and_restores_cursor(qtbot):
    from PySide6.QtCore import Qt as _Qt

    view = VideoView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    view.setFrame(_frame(100, 80))
    view.zoomOriginal()
    view.set_annotation_mode(True)

    _send_mouse_move(view, view.mapFromScene(80.0, 60.0))
    assert view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor

    view.setFrame(_frame(40, 30))
    assert not view._crosshair_v.isVisible() and not view._crosshair_h.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor
