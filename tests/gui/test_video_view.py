"""VideoView 缩放/平移与 screen→pixel 逆映射的解析几何测试。

验证 phase2-requirements.md §2 R4：宽高比保持、缩放范围钳位、
mapScreenToPixel 在任意缩放下映射正确、越界返回 None。
"""

import numpy as np
from PySide6.QtCore import QPointF, QSize
from PySide6.QtCore import QPoint
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video import DecodedFrame
from ai_physics_tracker.gui.video_view import (
    MAX_SCALE,
    MIN_SCALE,
    VideoView,
)

WIDTH_PX = 100
HEIGHT_PX = 60


def _frame(frame_index: int = 0) -> DecodedFrame:
    pixels = np.zeros((HEIGHT_PX, WIDTH_PX, 3), dtype=np.uint8)
    pixels[:, :, 0] = frame_index
    return DecodedFrame(frame_index, pixels)


def _shown_view(qtbot: QtBot, size: QSize = QSize(400, 300)) -> VideoView:
    view = VideoView()
    qtbot.addWidget(view)
    view.resize(size)
    view.show()
    view.setFrame(_frame())
    return view


def test_original_scale_maps_identity(qtbot: QtBot) -> None:
    view = _shown_view(qtbot)
    view.zoomOriginal()

    assert view.currentScale() == 1.0
    # 1:1 时 viewport 坐标与图像像素坐标重合（中心点往返）
    center = QPointF(WIDTH_PX / 2, HEIGHT_PX / 2)
    mapped = view.mapScreenToPixel(view.mapFromScene(center))
    assert mapped == (WIDTH_PX / 2, HEIGHT_PX / 2)


def test_pixel_edges_and_outside_return_none(qtbot: QtBot) -> None:
    view = _shown_view(qtbot)
    view.zoomOriginal()

    def pixel_of(scene_x: float, scene_y: float) -> tuple[float, float] | None:
        return view.mapScreenToPixel(view.mapFromScene(QPointF(scene_x, scene_y)))

    assert pixel_of(0.0, 0.0) == (0.0, 0.0)
    # 整数内点避开 Qt 滚动对齐的 0.5px 舍入（见 mapScreenToPixel docstring）
    assert pixel_of(WIDTH_PX - 1, HEIGHT_PX - 1) == (WIDTH_PX - 1, HEIGHT_PX - 1)
    # 图像边界外返回 None（取整像素距离避开 ±0.5px 舍入带）
    assert pixel_of(-1.0, 0.0) is None
    assert pixel_of(0.0, HEIGHT_PX + 1.0) is None
    assert pixel_of(WIDTH_PX + 1.0, 0.0) is None
    # viewport 内但落在图像外的点
    assert view.mapScreenToPixel(QPoint(9999, 9999)) is None


def test_mapping_survives_scaling_and_panning(qtbot: QtBot) -> None:
    view = _shown_view(qtbot)
    view.zoomOriginal()
    view.zoomIn()
    view.zoomIn()  # 1.25^2 ≈ 1.5625

    scale = view.currentScale()
    assert abs(scale - 1.25**2) < 1e-9
    # 缩放后 scene→view 变换改变，但 scene（=像素）坐标语义不变；
    # 0.5px 容差覆盖 Qt 滚动对齐舍入
    quarter = QPointF(WIDTH_PX / 4, HEIGHT_PX / 4)
    mapped = view.mapScreenToPixel(view.mapFromScene(quarter))
    assert mapped is not None
    assert abs(mapped[0] - WIDTH_PX / 4) <= 0.5
    assert abs(mapped[1] - HEIGHT_PX / 4) <= 0.5


def test_fit_mode_keeps_aspect_ratio(qtbot: QtBot) -> None:
    view = _shown_view(qtbot, QSize(400, 300))
    view.zoomFit()

    transform = view.transform()
    assert transform.m11() == transform.m22()  # 等比缩放不变形
    expected = min(
        (400 - 2) / WIDTH_PX,
        (300 - 2) / HEIGHT_PX,
    )
    assert abs(view.currentScale() - expected) < 1e-6


def test_zoom_clamps_to_bounds(qtbot: QtBot) -> None:
    view = _shown_view(qtbot)
    view.zoomOriginal()
    for _ in range(60):
        view.zoomIn()
    assert view.currentScale() <= MAX_SCALE + 1e-9
    for _ in range(120):
        view.zoomOut()
    assert view.currentScale() >= MIN_SCALE - 1e-9


def test_clear_frame_resets_to_placeholder(qtbot: QtBot) -> None:
    view = _shown_view(qtbot)

    view.clearFrame()

    assert not view.hasFrame()
    assert view.mapScreenToPixel(QPointF(10.0, 10.0)) is None


def test_pinch_scale_factor_accumulates_continuously(qtbot: QtBot) -> None:
    # pinch 连续因子直接相乘（无档位感），并受 MIN/MAX 钳位
    view = _shown_view(qtbot)
    view.zoomOriginal()

    for _ in range(10):
        view._applyPinchScale(1.05)
    assert abs(view.currentScale() - 1.05**10) < 1e-9

    for _ in range(200):
        view._applyPinchScale(1.5)
    assert view.currentScale() <= MAX_SCALE + 1e-9

    for _ in range(300):
        view._applyPinchScale(0.5)
    assert view.currentScale() >= MIN_SCALE - 1e-9


def test_pinch_without_frame_is_noop(qtbot: QtBot) -> None:
    view = VideoView()
    qtbot.addWidget(view)

    view._applyPinchScale(2.0)

    assert view.currentScale() == 1.0


def test_native_gesture_zoom_event_scales_in_view_event(qtbot: QtBot) -> None:
    # NativeGesture(Zoom) 若传播到 view.event() 时的处理逻辑
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QNativeGestureEvent, QPointingDevice

    view = _shown_view(qtbot)
    view.zoomOriginal()
    device = QPointingDevice.primaryPointingDevice()
    assert device is not None

    for _ in range(3):
        gesture = QNativeGestureEvent(
            Qt.NativeGestureType.ZoomNativeGesture,
            device,
            2,
            QPointF(50, 50),
            QPointF(50, 50),
            QPointF(60, 60),
            1.1,
            QPointF(0, 0),
        )
        assert view.event(gesture) is True

    assert abs(view.currentScale() - 1.1**3) < 1e-9


def test_pinch_gesture_event_scales_in_view_event(qtbot: QtBot) -> None:
    # 诊断实测的可靠路径：QGestureEvent(Pinch) 直达 VideoView.event()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QGestureEvent
    from PySide6.QtWidgets import QPinchGesture

    view = _shown_view(qtbot)
    view.zoomOriginal()

    for _ in range(2):
        pinch = QPinchGesture()
        pinch.setScaleFactor(1.2)
        gesture_event = QGestureEvent([pinch])
        assert view.event(gesture_event) is True

    assert abs(view.currentScale() - 1.2**2) < 1e-9
