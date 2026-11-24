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


def test_pick_modes_hide_system_cursor_in_favour_of_hairlines(qtbot):
    # UX-16：拾取/标注模式隐藏系统十字光标，1px 准线即指针
    from PySide6.QtCore import QEvent, Qt as _Qt
    from ai_physics_tracker.gui.video_view import PendulumOverlayView

    view = VideoView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()

    # 未加载帧时即使开启拾取模式，viewport 光标仍保持可见（避免黑屏/占位时指针失踪）
    view.set_annotation_mode(True)
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    view.setFrame(_frame())
    assert view._pixmap_item.cursor().shape() == _Qt.CursorShape.BlankCursor
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    # 鼠标进入视频画面内：显示 1px 准线且 viewport 切为 BlankCursor
    inside = view.mapFromScene(32.0, 24.0)
    view._update_crosshair(inside)
    assert view._crosshair_v.isVisible() and view._crosshair_h.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor

    # 鼠标移到视频外黑边留白区：隐藏准线且 viewport 恢复可见 ArrowCursor
    outside = view.mapFromScene(-10.0, -10.0)
    view._update_crosshair(outside)
    assert not view._crosshair_v.isVisible() and not view._crosshair_h.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    # 标定模式与 pendulum 持久图元同样隐藏系统光标；离开视口恢复可见光标
    view.set_calibration_mode("scale")
    view.set_pendulum_overlay(PendulumOverlayView(fixed_pivot_px=(20.0, 15.0)))
    assert view._pixmap_item.cursor().shape() == _Qt.CursorShape.BlankCursor
    assert all(item.cursor().shape() == _Qt.CursorShape.BlankCursor
               for item in view._pendulum_items)
    view._update_crosshair(inside)
    assert view.viewport().cursor().shape() == _Qt.CursorShape.BlankCursor
    view.leaveEvent(QEvent(QEvent.Type.Leave))
    assert not view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    # clearFrame 后同样隐藏准线并恢复 viewport 可见光标
    view._update_crosshair(inside)
    view.clearFrame()
    assert not view._crosshair_v.isVisible()
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor

    view.set_calibration_mode(None)
    view.set_annotation_mode(False)
    assert view.viewport().cursor().shape() == _Qt.CursorShape.ArrowCursor
    assert all(item.cursor().shape() == _Qt.CursorShape.ArrowCursor
               for item in view._pendulum_items)
