"""可缩放/平移的视频帧展示 widget（QGraphicsView 实现）。

view 的 transform 承担缩放与平移；scene 坐标即图像像素坐标
（item 位于原点、无附加变换），因此 screen→pixel 逆映射 =
mapToScene，越界返回 None（data-model.md §6.1：逆映射发生在 GUI
边界，落点前钳位并验证图像范围）。
"""

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QImage,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
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


class VideoView(QGraphicsView):
    """展示解耦的 RGB 帧；fit 模式自动适配，自由缩放后保持用户缩放。"""

    scaleChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._placeholder_item: QGraphicsTextItem | None = None
        self._fit_pending = True
        self.setMinimumSize(320, 240)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Ctrl+滚轮以光标为锚缩放（AnchorUnderMouse）；普通滚轮交给基类滚动
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoomIn()
            else:
                self.zoomOut()
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # 双击回到 fit 模式（常见查看器惯例）
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap_item:
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
