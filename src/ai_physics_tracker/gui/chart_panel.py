"""图表控件：只渲染适配后的序列并发出导航意图，不计算运动学或修改项目。"""

from uuid import UUID
from math import isclose

import numpy as np
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QComboBox, QDockWidget, QHBoxLayout, QLabel, QListWidget,
                              QListWidgetItem, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)
import pyqtgraph as pg

from ai_physics_tracker.application.chart_data import ChartData, ChartKind
from ai_physics_tracker.application.kinematics_job import SmoothingParameters
from ai_physics_tracker.domain.track import Track

CHART_KINDS: tuple[ChartKind, ...] = ("x_t", "y_t", "v_t", "a_t", "xy")


class ChartPlot(pg.PlotWidget):
    """正式游标不可拖拽；单独的请求游标表示尚未呈现的 seek 目标。"""

    timeRequested = Signal(float)
    frameRequested = Signal(int)

    def __init__(self, kind: ChartKind, parent: QWidget) -> None:
        super().__init__(parent, enableMenu=False)
        self.kind = kind
        self.data: ChartData | None = None
        self.activeTrack: UUID | None = None
        self.currentFrame: int | None = None
        self.canNavigate = False
        self._dragging = False
        self._requested_time_s: float | None = None
        self._items: list[pg.PlotDataItem] = []
        self._highlight = pg.ScatterPlotItem(size=11, pen=pg.mkPen("k", width=1))
        self.addItem(self._highlight, ignoreBounds=True)
        self.legend = self.addLegend()
        self.setBackground(self.palette().color(QPalette.ColorRole.Base))
        for axis in ("left", "bottom"):
            self.getAxis(axis).enableAutoSIPrefix(False)
            self.getAxis(axis).setPen(self.palette().color(QPalette.ColorRole.Text))
            self.getAxis(axis).setTextPen(self.palette().color(QPalette.ColorRole.Text))
        self.showGrid(x=True, y=True, alpha=0.2)
        self.setAspectLocked(kind == "xy")
        self.actualLine = pg.InfiniteLine(pen=pg.mkPen("#008ca8", width=2), movable=False)
        self.requestLine = pg.InfiniteLine(pen=pg.mkPen("#c07800", style=Qt.PenStyle.DotLine),
                                           movable=True, label="seek")
        if kind != "xy":
            self.addItem(self.actualLine, ignoreBounds=True)
            self.addItem(self.requestLine, ignoreBounds=True)
        self.actualLine.hide()
        self.requestLine.hide()
        self.requestLine.sigDragged.connect(self._dragged)
        self.requestLine.sigPositionChangeFinished.connect(self._dragFinished)
        self.scene().sigMouseClicked.connect(self._sceneClicked)

    def renderData(self, data: ChartData) -> None:
        self.data = data
        for item in self._items:
            self.removeItem(item)
        self._items.clear()
        self.legend.clear()
        self.setLabel("bottom", data.x_label, units=data.x_unit)
        self.setLabel("left", data.y_label, units=data.y_unit)
        self.getViewBox().invertY(self.kind == "xy" and data.pixel_coordinates)
        for series in data.series:
            color = pg.mkColor(series.color)
            if series.status == "stale":
                color.setAlpha(85)
            style = Qt.PenStyle.DashLine if series.component in ("vy", "ay") else Qt.PenStyle.SolidLine
            item = self.plot(np.asarray(series.x_values), np.asarray(series.y_values),
                connect=np.asarray(series.connect, dtype=bool), pen=pg.mkPen(color, width=2, style=style),
                symbol="o", symbolSize=5, symbolBrush=color, symbolPen=None,
                data=[(series.track_id, frame) for frame in series.frames],
                name=f"{series.name} · {series.component}" + (" [stale]" if series.status == "stale" else ""))
            self._items.append(item)
        self.fitData()
        self._updateHighlight()

    def fitData(self) -> None:
        self.enableAutoRange(x=False, y=False)
        self.autoRange()

    def setFrame(self, frame_index: int | None, time_s: float | None) -> None:
        self.currentFrame = frame_index
        self.actualLine.setVisible(time_s is not None and self.kind != "xy")
        self.requestLine.setVisible(time_s is not None and self.canNavigate and self.kind != "xy")
        if time_s is not None:
            self.actualLine.setValue(time_s)
            if (not self._dragging and (self._requested_time_s is None
                    or isclose(time_s, self._requested_time_s, rel_tol=0.0, abs_tol=1e-9))):
                self._requested_time_s = None
                self.requestLine.setValue(time_s)
        self._updateHighlight()

    def setRequestedTime(self, time_s: float | None) -> None:
        """保留请求目标，防止较早的在途帧交付将目标游标拉回去。"""

        self._requested_time_s = time_s
        if time_s is not None and not self._dragging:
            self.requestLine.setValue(time_s)
        elif time_s is None and self.currentFrame is not None:
            self.requestLine.setValue(self.actualLine.value())

    def setNavigation(self, enabled: bool, bounds: tuple[float, float] | None) -> None:
        self.canNavigate = enabled
        self.requestLine.setMovable(enabled)
        # InfiniteLine 构造器接受 None，setBounds 却要求可索引的二元边界。
        self.requestLine.setBounds(bounds if bounds is not None else (None, None))
        if not enabled:
            self.requestLine.hide()

    def _updateHighlight(self) -> None:
        spots = []
        if self.data is not None and self.currentFrame is not None:
            for series in self.data.series:
                if self.currentFrame in series.frames:
                    index = series.frames.index(self.currentFrame)
                    spots.append({"pos": (series.x_values[index], series.y_values[index]),
                                  "brush": series.color})
        self._highlight.setData(spots)

    def _dragged(self, _line) -> None:
        if self.canNavigate:
            self._dragging = True
            self.timeRequested.emit(float(self.requestLine.value()))

    def _dragFinished(self, _line) -> None:
        self._dragging = False
        if self.canNavigate:
            self.timeRequested.emit(float(self.requestLine.value()))

    def _sceneClicked(self, event) -> None:
        if (not self.canNavigate or event.button() != Qt.MouseButton.LeftButton
                or not self.getViewBox().sceneBoundingRect().contains(event.scenePos())):
            return
        if self.kind != "xy":
            self.timeRequested.emit(float(self.getViewBox().mapSceneToView(event.scenePos()).x()))
            return
        # 用 scatter 的屏幕命中范围查找实际点；重合时按活动轨迹/距当前帧/帧号决胜。
        candidates = []
        for item in self._items:
            local = item.scatter.mapFromScene(event.scenePos())
            for point in item.scatter.pointsAt(local):
                track_id, frame_index = point.data()
                candidates.append((track_id != self.activeTrack,
                                   abs(frame_index - (self.currentFrame or 0)), frame_index, str(track_id)))
        if candidates:
            self.frameRequested.emit(min(candidates)[2])


class ChartPanel(QDockWidget):
    """五个图表与独立的 Track 勾选/计算设置；不复用标注列表的选择模式。"""

    selectionChanged = Signal()
    parametersChanged = Signal()
    recomputeRequested = Signal()
    cancelRequested = Signal()
    timeRequested = Signal(float)
    frameRequested = Signal(int)

    def _make_help_label(self, text: str) -> QLabel:
        """参数旁的 "?" 提示：hover 显示解释与调参效果。"""

        label = QLabel("?")
        label.setToolTip(text)
        label.setToolTipDuration(20000)
        label.setStyleSheet(
            "color: #888; border: 1px solid #bbb; border-radius: 7px;"
            "min-width: 14px; max-width: 14px; min-height: 14px; max-height: 14px;"
            "qproperty-alignment: AlignCenter;"
        )
        return label

    def __init__(self, parent: QWidget) -> None:
        super().__init__("Kinematics charts", parent)
        self.setObjectName("kinematicsCharts")
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.trackChoices = QListWidget()
        self.trackChoices.setMaximumHeight(72)
        self.trackChoices.setMaximumWidth(240)
        self.windowLength = QSpinBox()
        self.windowLength.setRange(3, 999)
        self.windowLength.setSingleStep(2)
        self.windowLength.setValue(7)
        self.windowLength.setToolTip(
            "Requested odd window in frames. Short continuous segments use a smaller valid window; gaps are never filled.")
        self.polyorder = QSpinBox()
        self.polyorder.setRange(2, 998)
        self.polyorder.setValue(2)
        self.positionSource = QComboBox()
        self.positionSource.addItems(["Measured position", "Smoothed position"])
        self.positionSource.setToolTip("Position charts only; velocity and acceleration use the recorded SG pipeline.")
        self.sgHelp = self._make_help_label(
            "Savitzky-Golay 平滑窗口（单位：帧）。\n"
            "作用：对标注点做局部多项式平滑，抑制手抖/拖影带来的噪声。\n"
            "调大 → 曲线更平滑，但会抹平快速变化、增大边界失真；调小（最小 3）→ 接近原始数据。\n"
            "必须为奇数且不超过最长连续标注段；有缺测时按连续段分别取窗口。"
        )
        self.orderHelp = self._make_help_label(
            "局部多项式拟合的阶数。\n"
            "2 ≈ 二次多项式，适合匀速/匀加速运动（物理实验常用默认值）。\n"
            "调高 → 更贴合复杂轨迹，但会放大标注噪声；必须小于 SG 窗口长度。"
        )
        self.sourceHelp = self._make_help_label(
            "位置类图表（x-t / y-t / x-y）显示哪个位置：\n"
            "Measured position = 原始标注点；Smoothed position = 平滑后的点。\n"
            "速度/加速度图表始终由同一条平滑管线计算，不受此选择影响。"
        )
        self.recomputeButton = QPushButton("Recompute checked tracks")
        self.cancelButton = QPushButton("Cancel calculation")
        self.cancelButton.setEnabled(False)
        self.fitButton = QPushButton("Fit chart")
        settings = QHBoxLayout()
        for widget in (QLabel("SG window (frames)"), self.sgHelp, self.windowLength,
                       QLabel("Order"), self.orderHelp, self.polyorder,
                       self.positionSource, self.sourceHelp):
            settings.addWidget(widget)
        settings.addStretch(1)
        buttons = QHBoxLayout()
        for widget in (self.recomputeButton, self.cancelButton, self.fitButton):
            buttons.addWidget(widget)
        controls = QVBoxLayout()
        controls.addLayout(settings)
        controls.addLayout(buttons)
        header = QHBoxLayout()
        header.addWidget(self.trackChoices)
        header.addLayout(controls, 1)
        self.contextLabel = QLabel("No video selected")
        self.contextLabel.setWordWrap(True)
        self.jobLabel = QLabel("")
        self.statusLabel = QLabel("No data — select tracks and recompute")
        self.statusLabel.setWordWrap(True)
        self.tabs = QTabWidget()
        self.plots = {kind: ChartPlot(kind, self) for kind in CHART_KINDS}
        for kind, title in zip(CHART_KINDS, ("x-t", "y-t", "v-t", "a-t", "x-y")):
            plot = self.plots[kind]
            self.tabs.addTab(plot, title)
            plot.timeRequested.connect(self.timeRequested)
            plot.frameRequested.connect(self.frameRequested)
        layout = QVBoxLayout()
        layout.addLayout(header)
        layout.addWidget(self.contextLabel)
        layout.addWidget(self.jobLabel)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.statusLabel)
        content = QWidget()
        content.setLayout(layout)
        self.setWidget(content)
        self.trackChoices.itemChanged.connect(lambda _item: self.selectionChanged.emit())
        self.positionSource.currentIndexChanged.connect(lambda _index: self.selectionChanged.emit())
        self.windowLength.valueChanged.connect(lambda _value: self.parametersChanged.emit())
        self.polyorder.valueChanged.connect(lambda _value: self.parametersChanged.emit())
        self.recomputeButton.clicked.connect(self.recomputeRequested)
        self.cancelButton.clicked.connect(self.cancelRequested)
        self.fitButton.clicked.connect(lambda: self.currentPlot.fitData())
        self.tabs.currentChanged.connect(lambda _index: self.updateStatus())

    @property
    def currentPlot(self) -> ChartPlot:
        return self.plots[CHART_KINDS[self.tabs.currentIndex()]]

    def checkedTracks(self) -> tuple[UUID, ...]:
        return tuple(self.trackChoices.item(index).data(Qt.ItemDataRole.UserRole)
                     for index in range(self.trackChoices.count())
                     if self.trackChoices.item(index).checkState() == Qt.CheckState.Checked)

    def parameters(self) -> SmoothingParameters:
        return SmoothingParameters(self.windowLength.value(), self.polyorder.value())

    def setTracks(self, tracks: tuple[Track, ...], selected: UUID | None, *, reset: bool = False) -> None:
        checked = set() if reset else set(self.checkedTracks())
        previous = set() if reset else {self.trackChoices.item(i).data(Qt.ItemDataRole.UserRole)
                                      for i in range(self.trackChoices.count())}
        if selected is not None and selected not in previous:
            checked.add(selected)
        if not previous and selected is None and tracks:
            checked.add(tracks[0].track_id)
        with QSignalBlocker(self.trackChoices):
            self.trackChoices.clear()
            for track in tracks:
                item = QListWidgetItem(track.name)
                item.setData(Qt.ItemDataRole.UserRole, track.track_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if track.track_id in checked else Qt.CheckState.Unchecked)
                self.trackChoices.addItem(item)
        for plot in self.plots.values():
            plot.activeTrack = selected

    def updateStatus(self) -> None:
        data = self.currentPlot.data
        if data is None:
            self.statusLabel.setText("No data — select tracks and recompute")
            return
        summaries = tuple(dict.fromkeys(series.pipeline_summary for series in data.series
                                        if series.pipeline_summary))
        self.statusLabel.setText(" | ".join((*data.messages, *summaries)) or "Results ready")
