"""可缩放/平移的视频帧展示 widget（QGraphicsView 实现）。

view 的 transform 承担缩放与平移；scene 坐标即图像像素坐标
（item 位于原点、无附加变换），因此 screen→pixel 逆映射 =
mapToScene，越界返回 None（data-model.md §6.1：逆映射发生在 GUI
边界，落点前钳位并验证图像范围）。
"""

import math
from dataclasses import dataclass, replace

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QGraphicsView,
    QWidget,
)

from ai_physics_tracker.application.video import DecodedFrame

MIN_SCALE = 0.05
MAX_SCALE = 32.0
ZOOM_STEP = 1.25
# fit 时为滚动条边缘保留的像素余量，避免临界尺寸下出现滚动条
FIT_MARGIN_PX = 2.0
# 标注点的屏幕直径（ItemIgnoresTransformations：不随缩放变化）
MARKER_DIAMETER_PX = 9.0


@dataclass(frozen=True)
class MarkerView:
    """overlay 标注点的视图模型（gui 层，不携带领域对象）。"""

    pixel_x: float
    pixel_y: float
    color: str
    is_current_frame: bool = False
    source: str = "manual"
    frame_index: int | None = None


@dataclass(frozen=True)
class CalibrationView:
    """overlay 标定与坐标系的视图模型（gui 层，不携带领域对象）。"""

    scale_end_1_px: tuple[float, float]
    scale_end_2_px: tuple[float, float]
    known_length: float
    unit: str
    origin_px: tuple[float, float] | None = None
    rotation_deg: float = 0.0


class VideoView(QGraphicsView):
    """展示解耦的 RGB 帧；fit 模式自动适配，自由缩放后保持用户缩放。"""

    scaleChanged = Signal(float)
    annotationClicked = Signal(QPoint)
    scaleLineDrawn = Signal(QPointF, QPointF)
    originClicked = Signal(QPointF)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._placeholder_item: QGraphicsTextItem | None = None
        self._marker_items: list[QGraphicsItem] = []
        self._marker_views: list[MarkerView] = []
        self._marker_indices_by_frame: dict[int, tuple[int, ...]] = {}
        self._current_frame: int | None = None
        self._calibration_items: list[QGraphicsItem] = []
        self._calibration_view: CalibrationView | None = None
        self._calibration_mode: str | None = None
        self._scale_draw_start: tuple[float, float] | None = None
        self._scale_preview_item: QGraphicsLineItem | None = None
        self._is_scale_dragging = False
        self._annotation_mode = False
        self._fit_pending = True
        self.setMinimumSize(320, 240)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # 触摸板/触摸屏 pinch 由 Qt 合成为 QGestureEvent 发给 grab 了
        # 该手势的 widget（scripts/diagnose_pinch.py 实测直达 VideoView；
        # NativeGesture 路径到 viewport 即止，不向上传播，不可依赖）
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.setStyleSheet("background-color: #181818; border: none;")
        self.setPlaceholder("Open a video to begin")

    def setFrame(self, frame: DecodedFrame) -> None:
        """将 RGB 帧写入独立 QPixmap 并显示；fit 模式下重新适配视口。"""

        pixels = frame.pixels_rgb
        height_px, width_px, _ = pixels.shape
        image = QImage(
            pixels.data,
            width_px,
            height_px,
            int(pixels.strides[0]),
            QImage.Format.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(image)
        if self._pixmap_item is None:
            self._pixmap_item = self._scene.addPixmap(pixmap)
            self._pixmap_item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation
            )
            if self._annotation_mode:
                self._pixmap_item.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._pixmap_item.setPixmap(pixmap)
        self._removePlaceholder()
        self._scene.setSceneRect(QRectF(0.0, 0.0, width_px, height_px))
        if self._fit_pending:
            self.zoomFit()

    def clearFrame(self) -> None:
        """移除当前图像并恢复空状态提示。"""

        if self._pixmap_item is not None:
            self._scene.removeItem(self._pixmap_item)
            self._pixmap_item = None
        self._current_frame = None
        self.set_calibration(None)
        self._clear_scale_preview()
        self._scene.setSceneRect(QRectF(0.0, 0.0, 0.0, 0.0))
        self.zoomFit()
        self.setPlaceholder("Open a video to begin")

    def mapScreenToPixel(self, view_pos: QPoint) -> tuple[float, float] | None:
        """viewport 像素坐标（鼠标事件）→ 图像像素坐标；图像外返回 None。

        QGraphicsView 的滚动对齐对映射引入最多 0.5 像素的舍入；对
        手工标记（本身是亚像素浮点观测）该精度足够。scene 坐标即
        图像像素坐标，见模块 docstring。
        """

        if self._pixmap_item is None:
            return None
        scene_pos = self.mapToScene(view_pos)
        pixel_x = scene_pos.x()
        pixel_y = scene_pos.y()
        width_px = self._pixmap_item.pixmap().width()
        height_px = self._pixmap_item.pixmap().height()
        if 0.0 <= pixel_x < width_px and 0.0 <= pixel_y < height_px:
            return (pixel_x, pixel_y)
        return None

    def hasFrame(self) -> bool:
        """当前是否持有可显示的帧图像。"""

        return self._pixmap_item is not None

    def currentScale(self) -> float:
        """当前水平缩放系数（等比缩放下即整体缩放）。"""

        return self.transform().m11()

    def captureViewState(self) -> dict:
        """仅捕获视图上下文，不将播放/标注开关持久化。"""

        if not self.hasFrame():
            return {}
        center = self.mapToScene(self.viewport().rect().center())
        return {"fit": self._fit_pending, "scale": self.currentScale(),
                "center": [center.x(), center.y()]}

    def restoreViewState(self, state: object) -> None:
        """未知或不合法 UI 值使用 Fit；不修复领域数据。"""

        from math import isfinite
        if not isinstance(state, dict) or state.get("fit", True):
            self.zoomFit()
            return
        scale = state.get("scale")
        if isinstance(scale, bool) or not isinstance(scale, (float, int)) or not isfinite(scale):
            self.zoomFit()
            return
        self.zoomTo(scale)
        center = state.get("center")
        if isinstance(center, list) and len(center) == 2 and all(
            not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)
            for value in center
        ):
            rect = self.sceneRect()
            self.centerOn(max(rect.left(), min(center[0], rect.right())),
                          max(rect.top(), min(center[1], rect.bottom())))

    def zoomFit(self) -> None:
        """适配整个图像到视口，保持宽高比；进入/维持 fit 模式。"""

        self._fit_pending = True
        rect = self._scene.sceneRect()
        if rect.isEmpty():
            self.resetTransform()
            self.scaleChanged.emit(1.0)
            return
        self.resetTransform()
        viewport_size = self.viewport().size()
        scale_x = (viewport_size.width() - FIT_MARGIN_PX) / rect.width()
        scale_y = (viewport_size.height() - FIT_MARGIN_PX) / rect.height()
        scale = max(MIN_SCALE, min(scale_x, scale_y))
        self.scale(scale, scale)
        self._centerOnSceneCenter()
        self.scaleChanged.emit(self.currentScale())

    def zoomOriginal(self) -> None:
        """恢复 1:1 像素显示（100%）。"""

        self._fit_pending = False
        self.resetTransform()
        self._centerOnSceneCenter()
        self.scaleChanged.emit(self.currentScale())

    def zoomIn(self) -> None:
        self._zoomBy(ZOOM_STEP)

    def zoomOut(self) -> None:
        self._zoomBy(1.0 / ZOOM_STEP)

    def zoomTo(self, scale: float) -> None:
        """缩放到指定倍率（如 1.0 = 100%、2.0 = 200%），越界钳位。"""

        clamped = max(MIN_SCALE, min(MAX_SCALE, scale))
        self._fit_pending = False
        self.resetTransform()
        self.scale(clamped, clamped)
        self._centerOnSceneCenter()
        self.scaleChanged.emit(self.currentScale())

    def wheelEvent(self, event: QWheelEvent) -> None:
        # 滚轮/双指滑动 = 滚动视图（平移）；缩放由 pinch 手势、
        # 快捷键与菜单承担（Human Review 结论：滑动缩放不符合直觉）
        super().wheelEvent(event)

    def event(self, event: QEvent) -> bool:
        # 手势事件的汇聚点（scripts/diagnose_pinch.py 实测的事件流）：
        # - macOS 触摸板捏合：NativeGesture(QZoomNativeGesture) 先到
        #   viewport、未处理时传播到本 widget 的 event()；
        # - 触摸屏/合成手势：QGestureEvent(Pinch) 由 grabGesture 直接
        #   发给本 widget。两条路径都在这里处理。
        if event.type() == QEvent.Type.NativeGesture:
            gesture = event  # QNativeGestureEvent
            if gesture.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                factor = gesture.value()
                if factor > 0 and factor != 1.0:
                    self._applyPinchScale(factor)
                    return True
        elif event.type() == QEvent.Type.Gesture:
            gesture_event = event  # QGestureEvent
            pinch = gesture_event.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None:
                factor = float(pinch.scaleFactor())
                if factor > 0 and factor != 1.0:
                    self._applyPinchScale(factor)
                    gesture_event.accept()
                    return True
        return super().event(event)

    def _applyPinchScale(self, factor: float) -> None:
        """按 pinch 连续因子缩放（锚定光标），越界钳位。

        手势事件带平滑因子（如 1.02），直接相乘累积，无档位感。
        """

        if self._pixmap_item is None:
            return
        new_scale = self.currentScale() * factor
        if new_scale < MIN_SCALE or new_scale > MAX_SCALE:
            return
        self._fit_pending = False
        self.scale(factor, factor)
        self.scaleChanged.emit(self.currentScale())

    def set_calibration_mode(self, mode: str | None) -> None:
        """设置标定交互模式：'scale'（绘制比例尺）、'origin'（设置原点）或 None。"""

        self._calibration_mode = mode
        if mode is not None:
            self._annotation_mode = False
        self._clear_scale_preview()
        self._update_cursors()

    def is_calibration_mode(self) -> str | None:
        return self._calibration_mode

    def _update_cursors(self) -> None:
        shape = (
            Qt.CursorShape.CrossCursor
            if (self._annotation_mode or self._calibration_mode is not None)
            else Qt.CursorShape.ArrowCursor
        )
        if self._annotation_mode or self._calibration_mode is not None:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        if self._pixmap_item is not None:
            self._pixmap_item.setCursor(shape)
        for item in self._marker_items:
            item.setCursor(shape)
        for item in self._calibration_items:
            item.setCursor(shape)

    def set_annotation_mode(self, enabled: bool) -> None:
        """标注模式：左键点击落点（发 annotationClicked），禁用拖拽平移。

        十字光标设在图像/marker item 上：QGraphicsScene 的 hover 管理
        会用 item 光标覆盖 viewport 光标，只设 viewport 会在移动鼠标时
        被 scene 重置回箭头（Human Review 反馈的闪变 bug）。
        """

        self._annotation_mode = enabled
        if enabled:
            self._calibration_mode = None
            self._clear_scale_preview()
        self._update_cursors()

    def is_annotation_mode(self) -> bool:
        return self._annotation_mode

    def set_markers(self, markers: list[MarkerView]) -> None:
        """替换 marker 数据并按几何/来源复用现有图元。"""

        previous_items = list(self._marker_items)
        previous_views = list(self._marker_views)
        reusable: dict[
            tuple[float, float, str, str], list[tuple[QGraphicsItem, MarkerView]]
        ] = {}
        for item, marker in zip(previous_items, previous_views):
            reusable.setdefault(self._marker_style_key(marker), []).append((item, marker))

        next_items: list[QGraphicsItem] = []
        next_views: list[MarkerView] = []
        for marker in markers:
            key = self._marker_style_key(marker)
            candidates = reusable.get(key)
            current = self._marker_is_current(marker)
            view = marker if marker.is_current_frame == current else replace(
                marker, is_current_frame=current
            )
            if candidates:
                item, previous_view = candidates.pop()
                if previous_view.is_current_frame != view.is_current_frame:
                    self._update_marker_item(item, view)
            else:
                item = self._create_marker_item(marker)
                self._update_marker_item(item, view)
            next_items.append(item)
            next_views.append(view)
            if candidates is not None and not candidates:
                reusable.pop(key, None)

        for items in reusable.values():
            for item, _marker in items:
                self._scene.removeItem(item)
        self._marker_items = next_items
        self._marker_views = next_views
        self._rebuild_marker_frame_index()

    def set_current_frame(self, frame_index: int) -> None:
        """只更新前后当前帧的 marker 高亮，不扫描整条轨迹。"""

        previous_frame = self._current_frame
        self._current_frame = frame_index
        affected = set(self._marker_indices_by_frame.get(frame_index, ()))
        if previous_frame is not None:
            affected.update(self._marker_indices_by_frame.get(previous_frame, ()))
        for index in affected:
            marker = self._marker_views[index]
            current = marker.frame_index == frame_index
            if marker.is_current_frame == current:
                continue
            marker = replace(marker, is_current_frame=current)
            self._marker_views[index] = marker
            self._update_marker_item(self._marker_items[index], marker)

    def marker_count(self) -> int:
        return len(self._marker_items)

    def marker_views(self) -> list[MarkerView]:
        """当前 overlay 的标记视图快照（测试与语义断言用）。"""

        return list(self._marker_views)

    @staticmethod
    def _marker_style_key(marker: MarkerView) -> tuple[float, float, str, str]:
        return (marker.pixel_x, marker.pixel_y, marker.color, marker.source)

    def _marker_is_current(self, marker: MarkerView) -> bool:
        if marker.frame_index is None or self._current_frame is None:
            return marker.is_current_frame
        return marker.frame_index == self._current_frame

    def _rebuild_marker_frame_index(self) -> None:
        indexed: dict[int, list[int]] = {}
        for index, marker in enumerate(self._marker_views):
            if marker.frame_index is not None:
                indexed.setdefault(marker.frame_index, []).append(index)
        self._marker_indices_by_frame = {
            frame_index: tuple(indices) for frame_index, indices in indexed.items()
        }

    def _create_marker_item(self, marker: MarkerView) -> QGraphicsItem:
        radius = MARKER_DIAMETER_PX / 2.0
        if marker.source == "manual":
            item: QGraphicsItem = QGraphicsEllipseItem(
                -radius, -radius, MARKER_DIAMETER_PX, MARKER_DIAMETER_PX
            )
        else:
            item = QGraphicsPolygonItem(
                QPolygonF(
                    (
                        QPointF(0.0, -radius),
                        QPointF(radius, 0.0),
                        QPointF(0.0, radius),
                        QPointF(-radius, 0.0),
                    )
                )
            )
        # 屏幕固定大小：忽略 view transform（ItemIgnoresTransformations）。
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        item.setZValue(10.0)
        self._scene.addItem(item)
        return item

    def _update_marker_item(self, item: QGraphicsItem, marker: MarkerView) -> None:
        # item 原点是 marker 中心，避免缩放后出现 (1-zoom)×pixel 偏移。
        item.setPos(marker.pixel_x, marker.pixel_y)
        color = QColor(marker.color)
        pen = QPen(color)
        pen.setWidthF(2.5 if marker.is_current_frame else 1.2)
        item.setPen(pen)
        # manual 沿用实心当前圆/空心历史圆；AI 与其他来源始终为空心菱形。
        if marker.source == "manual" and marker.is_current_frame:
            item.setBrush(color)
        else:
            item.setBrush(Qt.BrushStyle.NoBrush)
        item.setToolTip(marker.source)
        if self._annotation_mode or self._calibration_mode is not None:
            item.setCursor(Qt.CursorShape.CrossCursor)

    def set_calibration(
        self,
        calibration: CalibrationView | None,
        image_height: int | None = None,
    ) -> None:
        """整批替换 overlay 标定线段与坐标系展示。"""

        for item in self._calibration_items:
            self._scene.removeItem(item)
        self._calibration_items = []
        self._calibration_view = calibration

        if calibration is None:
            return

        # 1. 绘制比例尺线段 (Scale Line)
        p1 = calibration.scale_end_1_px
        p2 = calibration.scale_end_2_px
        line_pen = QPen(QColor("#00e5ff"))
        line_pen.setWidthF(2.0)
        line_pen.setCosmetic(True)

        line_item = QGraphicsLineItem(p1[0], p1[1], p2[0], p2[1])
        line_item.setPen(line_pen)
        line_item.setZValue(20.0)
        self._scene.addItem(line_item)
        self._calibration_items.append(line_item)

        # 两端端点 ticks
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length > 1e-6:
            nx = -dy / length * 6.0
            ny = dx / length * 6.0
            for pt in (p1, p2):
                tick = QGraphicsLineItem(pt[0] - nx, pt[1] - ny, pt[0] + nx, pt[1] + ny)
                tick.setPen(line_pen)
                tick.setZValue(20.0)
                self._scene.addItem(tick)
                self._calibration_items.append(tick)

        # 端点圆点 handle (固定屏幕大小 6px)
        handle_brush = QBrush(QColor("#00e5ff"))
        for pt in (p1, p2):
            handle = QGraphicsEllipseItem(-3, -3, 6, 6)
            handle.setPos(pt[0], pt[1])
            handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            handle.setPen(line_pen)
            handle.setBrush(handle_brush)
            handle.setZValue(20.5)
            self._scene.addItem(handle)
            self._calibration_items.append(handle)

        # 长度文本标签
        text_label = f"{calibration.known_length:g} {calibration.unit}"
        text_item = QGraphicsSimpleTextItem(text_label)
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        text_item.setFont(font)
        text_item.setBrush(QBrush(QColor("#00e5ff")))
        text_item.setPen(QPen(QColor("#000000"), 0.5))
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        mx = (p1[0] + p2[0]) / 2.0
        my = (p1[1] + p2[1]) / 2.0
        offset_x = ny * 1.5 if length > 1e-6 else 0.0
        offset_y = -nx * 1.5 if length > 1e-6 else -10.0
        text_item.setPos(mx + offset_x, my + offset_y)
        text_item.setZValue(21.0)
        self._scene.addItem(text_item)
        self._calibration_items.append(text_item)

        # 2. 绘制世界坐标原点与坐标轴 (Origin & Axes)
        h = image_height or (self._pixmap_item.pixmap().height() if self._pixmap_item else 100)
        ox, oy = calibration.origin_px if calibration.origin_px is not None else (0.0, float(h))

        # 原点标记（十字圆环）
        origin_item = QGraphicsEllipseItem(-5, -5, 10, 10)
        origin_item.setPos(ox, oy)
        origin_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        origin_pen = QPen(QColor("#ffea00"))
        origin_pen.setWidthF(1.5)
        origin_item.setPen(origin_pen)
        origin_item.setBrush(QBrush(QColor(255, 234, 0, 100)))
        origin_item.setZValue(22.0)
        self._scene.addItem(origin_item)
        self._calibration_items.append(origin_item)

        # 坐标轴（X 轴为红，Y 轴为绿）
        axis_len = 50.0
        rad = math.radians(calibration.rotation_deg)

        # +X 轴 (图像中顺时针旋转 rad)
        x_dir_x = math.cos(rad)
        x_dir_y = math.sin(rad)
        x_end = (ox + axis_len * x_dir_x, oy + axis_len * x_dir_y)

        x_axis = QGraphicsLineItem(ox, oy, x_end[0], x_end[1])
        x_pen = QPen(QColor("#ff3333"))
        x_pen.setWidthF(2.0)
        x_pen.setCosmetic(True)
        x_axis.setPen(x_pen)
        x_axis.setZValue(22.0)
        self._scene.addItem(x_axis)
        self._calibration_items.append(x_axis)

        # X 轴标签
        x_label = QGraphicsSimpleTextItem("+X")
        x_label.setFont(font)
        x_label.setBrush(QBrush(QColor("#ff3333")))
        x_label.setPen(QPen(QColor("#000000"), 0.5))
        x_label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        x_label.setPos(x_end[0] + 4 * x_dir_x, x_end[1] + 4 * x_dir_y)
        x_label.setZValue(22.5)
        self._scene.addItem(x_label)
        self._calibration_items.append(x_label)

        # +Y 轴 (世界坐标逆时针 90°；图像中对应 (sin, -cos))
        y_dir_x = math.sin(rad)
        y_dir_y = -math.cos(rad)
        y_end = (ox + axis_len * y_dir_x, oy + axis_len * y_dir_y)

        y_axis = QGraphicsLineItem(ox, oy, y_end[0], y_end[1])
        y_pen = QPen(QColor("#00e676"))
        y_pen.setWidthF(2.0)
        y_pen.setCosmetic(True)
        y_axis.setPen(y_pen)
        y_axis.setZValue(22.0)
        self._scene.addItem(y_axis)
        self._calibration_items.append(y_axis)

        # Y 轴标签
        y_label = QGraphicsSimpleTextItem("+Y")
        y_label.setFont(font)
        y_label.setBrush(QBrush(QColor("#00e676")))
        y_label.setPen(QPen(QColor("#000000"), 0.5))
        y_label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        y_label.setPos(y_end[0] + 4 * y_dir_x, y_end[1] + 4 * y_dir_y)
        y_label.setZValue(22.5)
        self._scene.addItem(y_label)
        self._calibration_items.append(y_label)

        self._update_cursors()

    def calibration_view(self) -> CalibrationView | None:
        """当前 overlay 的标定视图快照。"""

        return self._calibration_view

    def calibration_items_count(self) -> int:
        return len(self._calibration_items)

    def _clear_scale_preview(self) -> None:
        if self._scale_preview_item is not None:
            self._scene.removeItem(self._scale_preview_item)
            self._scale_preview_item = None
        self._scale_draw_start = None
        self._is_scale_dragging = False

    def _update_scale_preview(self, p1: tuple[float, float], p2: tuple[float, float]) -> None:
        if self._scale_preview_item is None:
            self._scale_preview_item = QGraphicsLineItem()
            pen = QPen(QColor("#00e5ff"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidthF(1.5)
            pen.setCosmetic(True)
            self._scale_preview_item.setPen(pen)
            self._scale_preview_item.setZValue(25.0)
            self._scene.addItem(self._scale_preview_item)
        self._scale_preview_item.setLine(p1[0], p1[1], p2[0], p2[1])

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap_item is not None:
            if self._calibration_mode == "scale":
                pt = self.mapScreenToPixel(event.position().toPoint())
                if pt is not None:
                    if self._scale_draw_start is not None:
                        start_pt = self._scale_draw_start
                        self._scale_draw_start = None
                        self._clear_scale_preview()
                        self.scaleLineDrawn.emit(
                            QPointF(start_pt[0], start_pt[1]),
                            QPointF(pt[0], pt[1]),
                        )
                    else:
                        self._scale_draw_start = pt
                        self._is_scale_dragging = True
                        self._update_scale_preview(pt, pt)
                    event.accept()
                    return
            elif self._calibration_mode == "origin":
                pt = self.mapScreenToPixel(event.position().toPoint())
                if pt is not None:
                    self.originClicked.emit(QPointF(pt[0], pt[1]))
                    event.accept()
                    return
            elif self._annotation_mode:
                self.annotationClicked.emit(event.position().toPoint())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._calibration_mode == "scale" and self._scale_draw_start is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._update_scale_preview(self._scale_draw_start, (scene_pos.x(), scene_pos.y()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._calibration_mode == "scale"
            and self._is_scale_dragging
            and self._scale_draw_start is not None
        ):
            self._is_scale_dragging = False
            pt = self.mapScreenToPixel(event.position().toPoint())
            if pt is not None:
                dist = math.hypot(
                    pt[0] - self._scale_draw_start[0], pt[1] - self._scale_draw_start[1]
                )
                if dist >= 5.0:
                    start_pt = self._scale_draw_start
                    self._scale_draw_start = None
                    self._clear_scale_preview()
                    self.scaleLineDrawn.emit(
                        QPointF(start_pt[0], start_pt[1]),
                        QPointF(pt[0], pt[1]),
                    )
                    event.accept()
                    return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # 双击回到 fit 模式（浏览模式专属；标注/标定模式下不重置）
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._pixmap_item
            and not self._annotation_mode
            and self._calibration_mode is None
        ):
            self.zoomFit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._fit_pending:
            self.zoomFit()

    def _zoomBy(self, factor: float) -> None:
        self._fit_pending = False
        new_scale = self.currentScale() * factor
        if new_scale < MIN_SCALE or new_scale > MAX_SCALE:
            return
        self.scale(factor, factor)
        self.scaleChanged.emit(self.currentScale())

    def _centerOnSceneCenter(self) -> None:
        rect = self._scene.sceneRect()
        if not rect.isEmpty():
            self.centerOn(rect.center())

    def setPlaceholder(self, text: str) -> None:
        if self._pixmap_item is not None:
            return
        if self._placeholder_item is None:
            self._placeholder_item = self._scene.addText(text)
            self._placeholder_item.setDefaultTextColor(Qt.GlobalColor.gray)
        else:
            self._placeholder_item.setPlainText(text)

    def _removePlaceholder(self) -> None:
        if self._placeholder_item is not None:
            self._scene.removeItem(self._placeholder_item)
            self._placeholder_item = None
