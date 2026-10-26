"""图表控件：只渲染适配后的序列并发出导航意图，不计算运动学或修改项目。

Phase 6.2 在既有线性五图之外新增角运动时间图（theta_t / omega_t / alpha_t）
与相空间图（theta_omega / x_vx）；前五个标签页与 API 保持不变。相空间图
没有时间游标，点击按屏幕距离选择真实样本的源帧，绝不把横轴当秒。
"""

from uuid import UUID
from math import isclose

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal, QSignalBlocker
from PySide6.QtGui import QKeyEvent, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStyleFactory,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
import pyqtgraph as pg

from ai_physics_tracker.application.chart_data import (
    ANGLE_UNIT_DEGREE,
    ANGLE_UNIT_RAD,
    ChartData,
    ChartKind,
    ChartSeries,
)
from ai_physics_tracker.application.kinematics_job import SmoothingParameters
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.gui.angular_chart_controls import AngularReferenceControls
from ai_physics_tracker.gui.check_state_delegate import CheckStateDelegate

LINEAR_CHART_KINDS: tuple[ChartKind, ...] = ("x_t", "y_t", "v_t", "a_t", "xy")
ANGULAR_CHART_KINDS: tuple[ChartKind, ...] = (
    "theta_t", "omega_t", "alpha_t", "theta_omega", "x_vx",
)
CHART_KINDS: tuple[ChartKind, ...] = LINEAR_CHART_KINDS + ANGULAR_CHART_KINDS
TAB_TITLES: tuple[str, ...] = (
    "x-t", "y-t", "v-t", "a-t", "x-y", "θ(t)", "ω(t)", "α(t)", "θ–ω", "x–vx",
)

# 横轴为绝对源帧时间的图（有 actual / seek 双游标）；其余是相空间类图。
_TIME_CHART_KINDS = frozenset(
    {"x_t", "y_t", "v_t", "a_t", "theta_t", "omega_t", "alpha_t"}
)
# 图例中追加参考披露（实际支点或 A→B）的角运动图。
_LEGEND_REFERENCE_KINDS = frozenset(
    {"theta_t", "omega_t", "alpha_t", "theta_omega"}
)


class ChartPlot(pg.PlotWidget):
    """正式游标不可拖拽；单独的请求游标表示尚未呈现的 seek 目标。

    相空间类图（xy / theta_omega / x_vx）没有时间游标；点击按屏幕距离
    选择真实样本的源帧，重合时按确定性顺序决胜并披露定位轨迹。
    """

    timeRequested = Signal(float)
    frameRequested = Signal(int)
    sampleLocated = Signal(int, str)

    def __init__(self, kind: ChartKind, parent: QWidget) -> None:
        super().__init__(parent, enableMenu=False)
        self.kind = kind
        self.is_time_chart = kind in _TIME_CHART_KINDS
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
        # 仅 xy（两轴同量同单位）锁定纵横比；θ–ω / x–vx 两轴单位不同，
        # 锁定会任意拉伸数据形状，属误导。
        self.setAspectLocked(kind == "xy")
        self.actualLine = pg.InfiniteLine(pen=pg.mkPen("#008ca8", width=2), movable=False)
        self.requestLine = pg.InfiniteLine(pen=pg.mkPen("#c07800", style=Qt.PenStyle.DotLine),
                                           movable=True, label="seek")
        if self.is_time_chart:
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
                name=self._legendName(series))
            self._items.append(item)
        self.fitData()
        self._updateHighlight()

    def _legendName(self, series: ChartSeries) -> str:
        name = f"{series.name} · {series.component}" + (" [stale]" if series.status == "stale" else "")
        if self.kind in _LEGEND_REFERENCE_KINDS and series.reference_label:
            name += " · " + series.reference_label
        if self.kind == "theta_t":
            name += " · " + ("smoothed unwrapped" if series.source_smoothed else "raw wrapped")
        return name

    def fitData(self) -> None:
        self.enableAutoRange(x=False, y=False)
        self.autoRange()

    def setFrame(self, frame_index: int | None, time_s: float | None) -> None:
        self.currentFrame = frame_index
        self.actualLine.setVisible(time_s is not None and self.is_time_chart)
        self.requestLine.setVisible(time_s is not None and self.canNavigate and self.is_time_chart)
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
        if self.is_time_chart:
            self.timeRequested.emit(float(self.getViewBox().mapSceneToView(event.scenePos()).x()))
            return
        # 相空间：只在真实样本的命中半径内挑选，先比屏幕距离；距离相同/
        # 重合时按活动轨迹 → 离当前帧 → 帧号 → trackID 决胜。绝不从横轴
        # 反推时间，也不吸附到最近插值位置。
        best_key = None
        best = None
        for item in self._items:
            local = item.scatter.mapFromScene(event.scenePos())
            for point in item.scatter.pointsAt(local):
                track_id, frame_index = point.data()
                scene_pos = item.scatter.mapToScene(point.pos())
                dx = scene_pos.x() - event.scenePos().x()
                dy = scene_pos.y() - event.scenePos().y()
                # 屏幕上无法区分的浮点尾差按重合处理，保留确定的帧决胜顺序。
                key = (round(dx * dx + dy * dy, 9),
                       track_id != self.activeTrack,
                       abs(frame_index - (self.currentFrame or 0)),
                       frame_index, str(track_id))
                if best_key is None or key < best_key:
                    best_key = key
                    best = (track_id, frame_index)
        if best is not None:
            track_id, frame_index = best
            assert self.data is not None
            name = next((series.name for series in self.data.series
                         if series.track_id == track_id), str(track_id))
            self.sampleLocated.emit(frame_index, name)
            self.frameRequested.emit(frame_index)


class _PanelWheelForwarder(QObject):
    """内容被裁剪时把图表视口上的普通滚轮转发给面板滚动条（HR 反馈）。

    Ctrl+滚轮放行给 pyqtgraph 缩放；滚动条无滚动余量时也放行，
    保持图表默认滚轮行为不变。
    """

    def __init__(self, scroll: QScrollArea, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scroll = scroll

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt 命名)
        if event.type() == QEvent.Type.Wheel and not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            bar = self._scroll.verticalScrollBar()
            if bar.minimum() != bar.maximum():
                # 每滚轮刻度固定 40px：singleStep 随平台/布局变化（可能为 0），
                # 不能作为滚动步长依据
                scroll_px = int(event.angleDelta().y() * 40 / 120)
                bar.setValue(bar.value() - scroll_px)
                return True
        return False


class ChartPanel(QWidget):
    """十个图表与独立的 Track 勾选/计算设置；不复用标注列表的选择模式。

    前五个标签是既有线性图；后五个是角运动时间图与相空间图。角运动族
    额外显示参考配置行（:class:`AngularReferenceControls`）；当前分析的
    族由 ``currentFamily`` 披露，供任务卡投影与重算路由使用。

    Phase 5.7 起作为“分析与图表”工作区的主体（非 dock）；由 MainWindow
    挂入分析页。
    """

    selectionChanged = Signal()
    parametersChanged = Signal()
    displayChanged = Signal()      # 仅显示选项（角度单位），无需重算
    familyChanged = Signal(str)    # 当前标签的分析族切换（"linear"/"angular"）
    recomputeRequested = Signal()
    cancelRequested = Signal()
    timeRequested = Signal(float)
    frameRequested = Signal(int)
    sampleLocated = Signal(int, str)

    def _make_help_label(self, text: str) -> QLabel:
        """参数旁的 "?" 提示：hover 显示自绘气泡（QToolTip 在 macOS 渲染异常）。"""

        label = QLabel("?")
        label.setProperty("helpText", text)
        label.setMouseTracking(True)
        label.installEventFilter(self)
        label.setStyleSheet(
            "color: #888; border: 1px solid #bbb; border-radius: 7px;"
            "min-width: 14px; max-width: 14px; min-height: 14px; max-height: 14px;"
            "qproperty-alignment: AlignCenter;"
        )
        return label

    def _savePng(self) -> None:
        """把当前可见图表卡渲染为 PNG；grab 走设备像素比（Retina 天然 2x）。"""

        index = self.tabs.currentIndex()
        kind = CHART_KINDS[index]
        suggested = f"{self.tabs.tabText(index).replace('-', '')}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save chart as PNG", suggested, "PNG image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        pixmap = self.plots[kind].grab()
        if pixmap.save(path, "PNG"):
            self.statusLabel.setText(f"Chart saved: {path}")
        else:
            self.statusLabel.setText(f"Failed to save chart: {path}")

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (obj is self.trackChoices and event.type() == QEvent.Type.ShortcutOverride
                and isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Space
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            # 列表中的空格用于勾选，不触发窗口的全局播放快捷键。
            event.accept()
            return True
        # 拦截原生 Tooltip 事件（平台渲染不可靠），Enter/Leave 控制自绘气泡
        if event.type() == QEvent.Type.Enter and obj.property("helpText"):
            self._showHelpBubble(obj)
        elif event.type() == QEvent.Type.Leave:
            self._hideHelpBubble()
        elif event.type() == QEvent.Type.ToolTip:
            return True  # 抑制原生 QToolTip，避免叠加显示
        return super().eventFilter(obj, event)

    def _showHelpBubble(self, label: QLabel) -> None:
        if self._help_bubble is None:
            bubble = QLabel(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
            bubble.setWordWrap(True)
            bubble.setFixedWidth(380)
            bubble.setStyleSheet(
                "background: #ffffe8; color: #222; border: 1px solid #999;"
                "border-radius: 4px; padding: 8px; font-size: 12px;"
            )
            self._help_bubble = bubble
        self._help_bubble.setText(label.property("helpText"))
        self._help_bubble.adjustSize()
        top_left = label.mapToGlobal(QPoint(0, label.height() + 6))
        screen = QApplication.primaryScreen().availableGeometry()
        x = min(max(top_left.x(), screen.left() + 8), screen.right() - self._help_bubble.width() - 8)
        y = min(top_left.y(), screen.bottom() - self._help_bubble.height() - 8)
        self._help_bubble.move(x, y)
        self._help_bubble.show()
        self._help_bubble.raise_()

    def _hideHelpBubble(self) -> None:
        if self._help_bubble is not None:
            self._help_bubble.hide()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._help_bubble: QLabel | None = None
        self._family = "linear"
        self.setObjectName("kinematicsCharts")
        self.trackChoices = QListWidget()
        self.trackChoices.installEventFilter(self)
        self.trackChoices.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.trackChoices.setItemDelegate(CheckStateDelegate(self.trackChoices))
        # macOS 原生列表的空框不明显，限定此列表使用清晰的复选框样式。
        style = QStyleFactory.create("Fusion")
        if style is not None:
            style.setParent(self.trackChoices)
            self.trackChoices.setStyle(style)
        self.trackChoices.setToolTip("Click a track name or checkbox to include it in charts. Multiple tracks can be checked.")
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
        self.positionSource.setToolTip("Position and θ charts only; velocity, acceleration, ω and α use the recorded SG pipeline.")
        self.angleUnit = QComboBox()
        self.angleUnit.addItems([ANGLE_UNIT_RAD, ANGLE_UNIT_DEGREE])
        self.angleUnit.setToolTip("Display unit for angular charts. Display-only conversion; stored results stay in radians.")
        # QToolTip 中文在部分平台渲染为乱码（HR 反馈），提示统一用英文
        self.sgHelp = self._make_help_label(
            "Savitzky-Golay smoothing window, in frames.\n"
            "What it does: smooths annotated points with a local polynomial fit, "
            "suppressing hand-tremor and tracking noise.\n"
            "Larger -> smoother curve, but fast motion is flattened and edges distort "
            "more; smaller (min 3) -> close to the raw data.\n"
            "Must be odd and no longer than the longest continuous segment; gaps are "
            "never filled across."
        )
        self.orderHelp = self._make_help_label(
            "Polynomial order of the local fit.\n"
            "2 = quadratic, matches constant-velocity / constant-acceleration motion "
            "(the usual physics default).\n"
            "Higher -> follows complex trajectories more closely but amplifies marking "
            "noise; must stay below the SG window length."
        )
        self.sourceHelp = self._make_help_label(
            "Which recorded result the position and θ charts show:\n"
            "Measured = the raw points (θ stays wrapped at ±π); Smoothed = after "
            "smoothing (θ shown unwrapped).\n"
            "Velocity, acceleration, ω and α charts always come from the same "
            "smoothing pipeline and ignore this switch."
        )
        self.unitHelp = self._make_help_label(
            "Display unit for the angular charts (θ, ω, α, θ–ω):\n"
            "degree only converts numbers for display; the project always stores "
            "rad, rad/s and rad/s². Changing it never triggers a recomputation."
        )
        self.angularControls = AngularReferenceControls()
        self.angularControls._help.installEventFilter(self)
        self.angularControls.setVisible(False)
        self.recomputeButton = QPushButton("Recompute checked tracks")
        self.cancelButton = QPushButton("Cancel calculation")
        self.cancelButton.setEnabled(False)
        self.fitButton = QPushButton("Fit chart")
        self.savePngButton = QPushButton("Save PNG…")
        self.savePngButton.setToolTip("Export the currently visible chart as a PNG image")
        self.savePngButton.clicked.connect(self._savePng)
        settings = QHBoxLayout()
        for widget in (QLabel("SG window (frames)"), self.sgHelp, self.windowLength,
                       QLabel("Order"), self.orderHelp, self.polyorder,
                       self.positionSource, self.sourceHelp,
                       self.angleUnit, self.unitHelp):
            settings.addWidget(widget)
        settings.addStretch(1)
        buttons = QHBoxLayout()
        for widget in (self.recomputeButton, self.cancelButton, self.fitButton, self.savePngButton):
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
        for kind, title in zip(CHART_KINDS, TAB_TITLES):
            plot = self.plots[kind]
            self.tabs.addTab(plot, title)
            plot.timeRequested.connect(self.timeRequested)
            plot.frameRequested.connect(self.frameRequested)
            plot.sampleLocated.connect(self._showLocatedSample)
        layout = QVBoxLayout()
        layout.addLayout(header)
        layout.addWidget(self.contextLabel)
        layout.addWidget(self.jobLabel)
        layout.addWidget(self.angularControls)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.statusLabel)
        content = QWidget()
        content.setLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self._scroll_area = scroll
        panel_layout = QVBoxLayout(self)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)
        self.trackChoices.itemChanged.connect(lambda _item: self.selectionChanged.emit())
        self.positionSource.currentIndexChanged.connect(lambda _index: self.selectionChanged.emit())
        self.angleUnit.currentIndexChanged.connect(lambda _index: self.displayChanged.emit())
        self.windowLength.valueChanged.connect(lambda _value: self.parametersChanged.emit())
        self.polyorder.valueChanged.connect(lambda _value: self.parametersChanged.emit())
        self.recomputeButton.clicked.connect(self.recomputeRequested)
        self.cancelButton.clicked.connect(self.cancelRequested)
        self.fitButton.clicked.connect(lambda: self.currentPlot.fitData())
        self.tabs.currentChanged.connect(self._tabChanged)
        # dock 过矮时控制区可能被滚出视口，而滚轮悬在图上默认被 pyqtgraph
        # 消费（缩放），面板滚动条收不到事件，macOS 覆盖式滚动条又不可见，
        # 用户会彻底失去滚回顶部的途径（HR 反馈）。内容被裁剪时接管图表上的
        # 普通滚轮用于滚动面板；Ctrl+滚轮仍交给图表缩放；内容完整时行为不变。
        self._wheel_filter = _PanelWheelForwarder(self._scroll_area)
        for plot in self.plots.values():
            plot.viewport().installEventFilter(self._wheel_filter)

    @property
    def currentPlot(self) -> ChartPlot:
        return self.plots[CHART_KINDS[self.tabs.currentIndex()]]

    @staticmethod
    def familyForIndex(index: int) -> str:
        return "angular" if 0 <= index < len(CHART_KINDS) and CHART_KINDS[index] in _LEGEND_REFERENCE_KINDS else "linear"

    @property
    def currentFamily(self) -> str:
        """当前标签的分析族（"linear" / "angular"）；任务卡与重算路由据此分流。"""

        return self.familyForIndex(self.tabs.currentIndex())

    def currentAngleUnit(self) -> str:
        """当前角度显示单位（combo 只含两个合法值）。"""

        return self.angleUnit.currentText()

    def _tabChanged(self, index: int) -> None:
        angular = self.familyForIndex(index) == "angular"
        self.angularControls.setVisible(angular)
        if self._family != ("angular" if angular else "linear"):
            self._family = self.currentFamily
            self.familyChanged.emit(self._family)
        self.updateStatus()

    def _showLocatedSample(self, frame_index: int, track_name: str) -> None:
        self.statusLabel.setText(f"Located frame {frame_index} · track '{track_name}'")

    def captureViewState(self, previous: dict | None = None) -> dict:
        """图表显示选项的 additive 视图状态；未知字段由 update_view_state 保留。"""

        state = dict(previous) if isinstance(previous, dict) else {}
        if state.get("version", 1) != 1:
            return state
        state.update({
            "version": 1,
            "current_tab": self.tabs.currentIndex(),
            "angle_unit": self.angleUnit.currentText(),
            "position_source_index": self.positionSource.currentIndex(),
        })
        return state

    def restoreViewState(self, state: dict) -> None:
        """缺省恢复默认显示；未来版本保持当前值，不降级覆盖。"""

        if isinstance(state, dict) and state.get("version", 1) != 1:
            return

        with QSignalBlocker(self.angleUnit), QSignalBlocker(self.positionSource), QSignalBlocker(self.tabs):
            self.angleUnit.setCurrentIndex(0)
            self.positionSource.setCurrentIndex(0)
            self.tabs.setCurrentIndex(0)
        self._tabChanged(0)
        if not isinstance(state, dict):
            return
        unit = state.get("angle_unit")
        if unit in (ANGLE_UNIT_RAD, ANGLE_UNIT_DEGREE):
            index = self.angleUnit.findText(unit)
            if index >= 0:
                self.angleUnit.setCurrentIndex(index)
        source = state.get("position_source_index")
        if type(source) is int and 0 <= source < self.positionSource.count():
            self.positionSource.setCurrentIndex(source)
        tab = state.get("current_tab")
        if type(tab) is int and 0 <= tab < self.tabs.count():
            self.tabs.setCurrentIndex(tab)

    def checkedTracks(self) -> tuple[UUID, ...]:
        return tuple(self.trackChoices.item(index).data(Qt.ItemDataRole.UserRole)
                     for index in range(self.trackChoices.count())
                     if self.trackChoices.item(index).checkState() == Qt.CheckState.Checked)

    def parameters(self) -> SmoothingParameters:
        return SmoothingParameters(self.windowLength.value(), self.polyorder.value())

    def setTracks(self, tracks: tuple[Track, ...], selected: UUID | None, *, reset: bool = False) -> None:
        for plot in self.plots.values():
            plot.activeTrack = selected
        # 勾选刷新不重建相同列表，保留当前行和键盘焦点。
        if not reset and tuple((self.trackChoices.item(i).data(Qt.ItemDataRole.UserRole),
                                self.trackChoices.item(i).text())
                               for i in range(self.trackChoices.count())) == tuple(
                                   (track.track_id, track.name) for track in tracks):
            return
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

    def updateStatus(self) -> None:
        data = self.currentPlot.data
        if data is None:
            self.statusLabel.setText("No data — select tracks and recompute")
            return
        summaries = tuple(dict.fromkeys(series.pipeline_summary for series in data.series
                                        if series.pipeline_summary))
        self.statusLabel.setText(" | ".join((*data.messages, *summaries)) or "Results ready")
