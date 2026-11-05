"""UX-07/08 标注辅助回归：4/4 自动下一帧勾选、全幅细准线。"""

import numpy as np
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
