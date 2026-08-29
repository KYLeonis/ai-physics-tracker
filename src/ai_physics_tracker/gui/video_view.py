"""保持宽高比的 RGB 视频帧展示 widget。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ai_physics_tracker.application.video import DecodedFrame


class VideoView(QLabel):
    """展示解耦的 RGB 帧，自身不持有解码器状态。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: #181818; color: #d0d0d0;")
        self.setText("Open a video to begin")

    def setFrame(self, frame: DecodedFrame) -> None:
        """将 NumPy 内存复制为独立的 QImage 并显示，不与源缓冲共享。"""

        pixels = frame.pixels_rgb
        height_px, width_px, _ = pixels.shape
        image = QImage(
            pixels.data,
            width_px,
            height_px,
            int(pixels.strides[0]),
            QImage.Format.Format_RGB888,
        ).copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self.setText("")
        self._updateScaledPixmap()

    def clearFrame(self) -> None:
        """移除当前图像并恢复空状态提示文案。"""

        self._source_pixmap = None
        self.clear()
        self.setText("Open a video to begin")

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._updateScaledPixmap()

    def _updateScaledPixmap(self) -> None:
        if self._source_pixmap is None or self.size().isEmpty():
            return
        scaled = self._source_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
