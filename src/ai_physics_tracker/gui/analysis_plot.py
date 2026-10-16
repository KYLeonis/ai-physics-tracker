"""GUI层：分析图表的明确缩放操作和常驻页面滚动条。"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPalette, QWheelEvent
from PySide6.QtWidgets import QScrollArea, QStyleFactory, QWidget


class AnalysisScrollArea(QScrollArea):
    """页面只纵向滚动；使用非瞬态滚动条，避免macOS自动隐藏轨道。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scrollStyle = QStyleFactory.create("Fusion")
        if self._scrollStyle is not None:
            self._scrollStyle.setParent(self)
            self.verticalScrollBar().setStyle(self._scrollStyle)
        self.verticalScrollBar().setMinimumWidth(16)

    def event(self, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Resize, QEvent.Type.Show) and self.widget() is not None:
            # 跟随实际表单最小宽度约束分栏 / 窗口，不能只隐藏横向条后裁掉控件。
            bar = self.verticalScrollBar()
            self.setMinimumWidth(self.widget().minimumSizeHint().width()
                                 + max(bar.minimumWidth(), bar.sizeHint().width()) + 2 * self.frameWidth())
        return super().event(event)

    def scrollPage(self, delta: int) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() - delta)


class AnalysisPlot(pg.PlotWidget):
    """滚轮滚页面；Ctrl+滚轮才缩放，普通拖动不平移坐标系。"""

    pageScrollRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, enableMenu=False)
        self.setBackground(self.palette().color(QPalette.ColorRole.Base))
        self.setMouseEnabled(x=False, y=False)
        self.hideButtons()
        self.showGrid(x=True, y=True, alpha=.2)
        for name in ("left", "bottom"):
            axis = self.getAxis(name)
            axis.enableAutoSIPrefix(False)
            axis.setPen(self.palette().color(QPalette.ColorRole.Text))
            axis.setTextPen(self.palette().color(QPalette.ColorRole.Text))
        self.setToolTip("Scroll: page. Ctrl+scroll or zoom buttons: chart. Reset view: show the signal.")
        self._dataRange = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            self.zoom(1.2 ** (-float(np.clip(delta / 120, -3, 3))))
        else:
            delta = event.pixelDelta().y() or event.angleDelta().y() / 120 * 40
            self.pageScrollRequested.emit(round(delta))
        event.accept()

    def setDataRange(self, time_s: np.ndarray, values: np.ndarray) -> None:
        """默认范围来自源信号；初值模型和参考线不把量测曲线压成一条线。"""
        if not len(time_s) or not len(values):
            self._dataRange = None
            return
        low, high = float(np.min(values)), float(np.max(values))
        padding = max((high - low) * .1, max(abs(low), abs(high)) * 1e-6) or .1
        start, end = float(time_s[0]), float(time_s[-1])
        time_padding = max((end - start) * .03, .01)
        self._dataRange = ((start-time_padding, end+time_padding), (low-padding, high+padding))
        self.resetView()

    def resetView(self) -> None:
        if self._dataRange is not None:
            x_range, y_range = self._dataRange
            self.setRange(xRange=x_range, yRange=y_range, padding=0, disableAutoRange=True)

    def zoom(self, factor: float) -> None:
        if self._dataRange is not None:
            self.getViewBox().scaleBy((factor, factor))

    def showReference(self, value: float) -> None:
        """显式找回参考线；默认数据范围不受离群参考值影响。"""
        if self._dataRange is not None:
            x_range, (low, high) = self._dataRange
            padding = (high-low) * .05
            self.setRange(xRange=x_range, yRange=(min(low, value-padding), max(high, value+padding)),
                          padding=0, disableAutoRange=True)
