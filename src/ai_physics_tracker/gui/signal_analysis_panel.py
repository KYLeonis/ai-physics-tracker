"""GUI层：单量公式 / 参数编辑与独立重复间隔工具，不执行拟合。"""

from uuid import UUID

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, QSize, Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QSlider, QSizePolicy,
)

from ai_physics_tracker.application.signal_analysis_job import SignalSelection
from ai_physics_tracker.domain.analysis import QUANTITIES
from ai_physics_tracker.domain.derived import DerivedData
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec
from ai_physics_tracker.domain.recurrence import RecurrenceSpec
from ai_physics_tracker.gui.formula_editor import FormulaEditor
from ai_physics_tracker.gui.analysis_plot import AnalysisPlot


class _ToolTabs(QTabWidget):
    """只给当前工具留空间，避免较长的拟合表单撑高间隔工具。"""

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        if self.currentWidget() is not None:
            size.setHeight(self.currentWidget().sizeHint().height() + self.tabBar().sizeHint().height() + 4)
        return size

    def minimumSizeHint(self) -> QSize:
        size = super().minimumSizeHint()
        if self.currentWidget() is not None:
            size.setHeight(self.currentWidget().minimumSizeHint().height() + self.tabBar().sizeHint().height() + 4)
        return size


class SignalAnalysisPanel(QWidget):
    """一条轨迹一个量；草稿与保存结果分别显示，点选真实样本发源帧导航。"""

    settingsChanged = Signal()
    targetChanged = Signal()
    fitRequested = Signal()
    recurrenceRequested = Signal()
    previewRequested = Signal()
    sourcePreviewRequested = Signal()
    pageScrollRequested = Signal(int)
    cancelRequested = Signal()
    frameRequested = Signal(int)
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        self._context = None
        self._cache = None
        self._valueRange = None
        self._eventLines = []
        self.trackChoice, self.quantityChoice, self.sourceChoice = QComboBox(), QComboBox(), QComboBox()
        self.quantityChoice.addItems(QUANTITIES)
        self.sourceChoice.addItems(("Measured (default)", "Smoothed (optional)"))
        self.startFrame, self.endFrame = QSpinBox(), QSpinBox()
        self.startFrame.setPrefix("Start frame ")
        self.endFrame.setPrefix("End frame ")
        self.contextLabel = QLabel("Select a video and compute its source charts first.")
        self.contextLabel.setWordWrap(True)
        self.jobLabel = QLabel()
        self.jobLabel.setWordWrap(True)
        self.draftLabel = QLabel("Draft — no analysis applied")
        self.draftLabel.setWordWrap(True)
        self.editor = FormulaEditor()
        self.parameterTable = QTableWidget(0, 5)
        self.parameterTable.setHorizontalHeaderLabels(("Parameter", "Initial", "Lower (optional)", "Upper (optional)", "Fixed"))
        self.parameterTable.setMaximumHeight(170)
        self.budget = QSpinBox()
        self.budget.setRange(1, 10000)
        self.budget.setValue(1000)
        self.resultName, self.resultFormula = QLineEdit(), QLineEdit()
        self.resultName.setPlaceholderText("Result name (optional), e.g. T")
        self.resultFormula.setPlaceholderText("Parameters only, e.g. 2*pi/Omega")
        self.previewButton, self.fitButton = QPushButton("Preview initial curve"), QPushButton("Fit")
        self.cancelButton = QPushButton("Cancel calculation")
        self.restoreButton = QPushButton("Restore saved settings")
        self.undoButton, self.redoButton = QPushButton("Undo result"), QPushButton("Redo result")
        for button in (self.undoButton, self.redoButton):
            button.setToolTip("Only the next fit / crossing-result transaction; source data and calibration remain read-only")
        self.level = self._number(0)
        self.hysteresis = self._number(0, nonnegative=True)
        self.separation = self._number(0, nonnegative=True)
        self.direction = QComboBox()
        self.direction.addItems(("Rising", "Falling"))
        self.recurrenceButton = QPushButton("Measure crossing intervals")
        self.methods = _ToolTabs()
        self.methods.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        fit = QWidget()
        fitLayout = QVBoxLayout(fit)
        fitLayout.addWidget(self.editor)
        fitLayout.addWidget(self.parameterTable)
        parameterOptions = QGroupBox("Parameter bounds / fixed values")
        parameterOptions.setCheckable(True)
        parameterOptions.setChecked(False)
        parameterOptions.toggled.connect(lambda checked: [self.parameterTable.setColumnHidden(col, not checked) for col in (2, 3, 4)])
        for col in (2, 3, 4):
            self.parameterTable.setColumnHidden(col, True)
        fitLayout.addWidget(parameterOptions)
        advanced = QGroupBox("Optional settings")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        form = QFormLayout(advanced)
        form.addRow("Model evaluation limit", self.budget)
        form.addRow(self.resultName, self.resultFormula)
        for widget in (self.budget, self.resultName, self.resultFormula):
            widget.setVisible(False)
        budgetLabel = form.labelForField(self.budget)
        budgetLabel.hide()
        advanced.toggled.connect(budgetLabel.setVisible)
        advanced.toggled.connect(lambda checked: [widget.setVisible(checked) for widget in (self.budget, self.resultName, self.resultFormula)])
        fitLayout.addWidget(advanced)
        fitButtons = QHBoxLayout()
        fitButtons.addWidget(self.previewButton)
        fitButtons.addWidget(self.fitButton)
        fitLayout.addLayout(fitButtons)
        self.methods.addTab(fit, "Function fit")
        recurrence = QWidget()
        recurrenceLayout = QFormLayout(recurrence)
        note = QLabel("Show source → set the orange reference → Measure intervals.\nRepeat intervals are a period only with one crossing per cycle.")
        note.setWordWrap(True)
        note.setToolTip("Interpret intervals as a period only when each cycle has one same-direction crossing. Gaps and wrapped-angle jumps are never bridged.")
        recurrenceLayout.addRow(note)
        self.showSourceButton = QPushButton("Show source")
        recurrenceLayout.addRow(self.showSourceButton)
        self.levelSlider = QSlider(Qt.Orientation.Horizontal)
        self.levelSlider.setRange(0, 1000)
        self.levelSlider.setAccessibleName("Reference level within measured range")
        self.centerReferenceButton = QPushButton("Center reference")
        self.showReferenceButton = QPushButton("Find reference")
        referenceButtons = QHBoxLayout()
        referenceButtons.addWidget(self.centerReferenceButton)
        referenceButtons.addWidget(self.showReferenceButton)
        recurrenceLayout.addRow("Reference value", self.level)
        recurrenceLayout.addRow("Adjust within signal", self.levelSlider)
        recurrenceLayout.addRow(referenceButtons)
        self.referenceStatus = QLabel("Show source to see its range.")
        self.referenceStatus.setWordWrap(True)
        recurrenceLayout.addRow(self.referenceStatus)
        recurrenceLayout.addRow("Crossing direction", self.direction)
        noiseOptions = QGroupBox("Noise / separation options")
        noiseOptions.setCheckable(True)
        noiseOptions.setChecked(False)
        noiseFields = QWidget()
        noiseForm = QFormLayout(noiseFields)
        noiseForm.addRow("Confirmation band", self.hysteresis)
        noiseForm.addRow("Minimum separation (s)", self.separation)
        QVBoxLayout(noiseOptions).addWidget(noiseFields)
        noiseFields.hide()
        noiseOptions.toggled.connect(noiseFields.setVisible)
        recurrenceLayout.addRow(noiseOptions)
        recurrenceLayout.addRow(self.recurrenceButton)
        self.methods.addTab(recurrence, "Crossing intervals")
        self.signalPlot, self.residualPlot = AnalysisPlot(), AnalysisPlot()
        for plot in (self.signalPlot, self.residualPlot):
            plot.setMinimumHeight(270)
            plot.pageScrollRequested.connect(self.pageScrollRequested)
        self.signalPlot.addLegend()
        self.signalPlot.setLabel("bottom", "Time from interval start", units="s")
        self.residualPlot.setLabel("bottom", "Time from interval start", units="s")
        self.residualPlot.setLabel("left", "Measured − predicted")
        self.referenceLine = pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("#bb7700", width=3),
                                             hoverPen=pg.mkPen("#ff9900", width=4), label="Reference: {value:.6g}")
        self.referenceLine.sigPositionChanged.connect(self._referenceDragged)
        self.referenceLine.sigPositionChangeFinished.connect(self._referenceDragged)
        self.plotTabs = QTabWidget()
        self.plotTabs.addTab(self.signalPlot, "Signal / model")
        self.plotTabs.addTab(self.residualPlot, "Residuals")
        self.resetViewButton = QPushButton("Reset view")
        self.zoomInButton, self.zoomOutButton = QPushButton("Zoom +"), QPushButton("Zoom −")
        plotActions = QHBoxLayout()
        for button in (self.resetViewButton, self.zoomInButton, self.zoomOutButton):
            plotActions.addWidget(button)
        self.resetViewButton.clicked.connect(lambda: self.plotTabs.currentWidget().resetView())
        self.zoomInButton.clicked.connect(lambda: self.plotTabs.currentWidget().zoom(0.8))
        self.zoomOutButton.clicked.connect(lambda: self.plotTabs.currentWidget().zoom(1.25))
        self.levelSlider.valueChanged.connect(self._sliderChanged)
        self.level.valueChanged.connect(self._referenceChanged)
        self.centerReferenceButton.clicked.connect(self._centerReference)
        self.showReferenceButton.clicked.connect(lambda: self.signalPlot.showReference(self.level.value()))
        self.showSourceButton.clicked.connect(self.sourcePreviewRequested)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(180)
        layout = QVBoxLayout(self)
        dataGroup = QGroupBox("1. Choose data")
        choices = QFormLayout(dataGroup)
        for widget in (self.trackChoice, self.quantityChoice, self.sourceChoice):
            widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            widget.setMinimumContentsLength(8)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        choices.addRow("Track", self.trackChoice)
        choices.addRow("Quantity", self.quantityChoice)
        choices.addRow("Source", self.sourceChoice)
        interval = QHBoxLayout()
        interval.addWidget(self.startFrame)
        interval.addWidget(self.endFrame)
        choices.addRow("Interval", interval)
        layout.addWidget(dataGroup)
        layout.addWidget(self.contextLabel)
        layout.addWidget(self.methods)
        actions = QHBoxLayout()
        actions.addWidget(self.restoreButton)
        actions.addWidget(self.cancelButton)
        layout.addLayout(actions)
        layout.addWidget(self.draftLabel)
        history = QHBoxLayout()
        history.addWidget(self.undoButton)
        history.addWidget(self.redoButton)
        history.addStretch()
        layout.addLayout(history)
        layout.addWidget(self.jobLabel)
        layout.addLayout(plotActions)
        layout.addWidget(self.plotTabs)
        helpLabel = QLabel("Scroll: page · Ctrl+scroll / buttons: zoom · Click a point: source frame")
        helpLabel.setWordWrap(True)
        layout.addWidget(helpLabel)
        self.resultLabel = QLabel("No saved result yet.")
        self.resultLabel.setWordWrap(True)
        layout.addWidget(self.resultLabel)
        self.detailsGroup = QGroupBox("Result details / provenance")
        self.detailsGroup.setCheckable(True)
        self.detailsGroup.setChecked(False)
        QVBoxLayout(self.detailsGroup).addWidget(self.summary)
        self.summary.hide()
        self.detailsGroup.toggled.connect(self.summary.setVisible)
        layout.addWidget(self.detailsGroup)
        self.editor.formulaChanged.connect(self._formulaChanged)
        self.parameterTable.itemChanged.connect(self._edited)
        for widget in (self.budget, self.level, self.hysteresis, self.separation):
            widget.valueChanged.connect(self._edited)
        for widget in (self.resultName, self.resultFormula):
            widget.textChanged.connect(self._edited)
        self.direction.currentIndexChanged.connect(self._edited)
        self.sourceChoice.currentIndexChanged.connect(self._sourceChanged)
        self.startFrame.valueChanged.connect(self._sourceChanged)
        self.endFrame.valueChanged.connect(self._sourceChanged)
        self.trackChoice.currentIndexChanged.connect(self._targetChanged)
        self.quantityChoice.currentIndexChanged.connect(self._targetChanged)
        self.methods.currentChanged.connect(self._methodChanged)
        self.fitButton.clicked.connect(self.fitRequested)
        self.previewButton.clicked.connect(self.previewRequested)
        self.recurrenceButton.clicked.connect(self.recurrenceRequested)
        self.cancelButton.clicked.connect(self.cancelRequested)
        self.restoreButton.clicked.connect(self.restoreSaved)
        self.undoButton.clicked.connect(self.undoRequested)
        self.redoButton.clicked.connect(self.redoRequested)
        for widget in (self.trackChoice, self.quantityChoice, self.sourceChoice, self.direction,
                       self.startFrame, self.endFrame, self.level, self.levelSlider,
                       self.hysteresis, self.separation, self.budget):
            widget.installEventFilter(self)
        self._formulaChanged()
        self.editor.setQuantityLabel("x(t)")

    def eventFilter(self, watched, event) -> bool:
        # 滚动表单时不能因为指针经过数字框 / 下拉框就意外修改测量配方。
        if event.type() == QEvent.Type.Wheel:
            delta = event.pixelDelta().y() or event.angleDelta().y() / 120 * 40
            self.pageScrollRequested.emit(round(delta))
            event.accept()
            return True
        return super().eventFilter(watched, event)

    @staticmethod
    def _number(value, nonnegative=False):
        widget = QDoubleSpinBox()
        widget.setDecimals(8)
        widget.setRange(0 if nonnegative else -1e12, 1e12)
        widget.setValue(value)
        return widget

    def _formulaChanged(self, *_args) -> None:
        expression = self.editor.expression()
        previous = {self.parameterTable.item(row, 0).text(): [self.parameterTable.item(row, col) for col in range(1, 5)]
                    for row in range(self.parameterTable.rowCount())}
        old = {name: [(item.text(), item.checkState()) for item in cells] for name, cells in previous.items()}
        with QSignalBlocker(self.parameterTable):
            names = expression.parameter_names if expression else ()
            self.parameterTable.setRowCount(len(names))
            for row, name in enumerate(names):
                label = QTableWidgetItem(name)
                label.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.parameterTable.setItem(row, 0, label)
                for col in range(1, 5):
                    item = QTableWidgetItem(old[name][col-1][0] if name in old else ("1" if col == 1 else ""))
                    if col == 4:
                        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(old[name][3][1] if name in old else Qt.CheckState.Unchecked)
                    self.parameterTable.setItem(row, col, item)
        self._edited()

    def _edited(self, *_args) -> None:
        if not self._loading:
            self.draftLabel.setText("Draft changed — saved results use their recorded settings")
            self.settingsChanged.emit()

    def _sourceChanged(self, *_args) -> None:
        if not self._loading:
            self._edited()
            if self.methods.currentIndex() == 1:
                self.sourcePreviewRequested.emit()

    def _targetChanged(self, *_args) -> None:
        if self._loading:
            return
        self.editor.setQuantityLabel(self.quantityChoice.currentText() + "(t)")
        self.sourceChoice.setEnabled(self.quantityChoice.currentText() in ("x", "y", "theta"))
        self._cache = None
        self.targetChanged.emit()

    def _methodChanged(self, *_args) -> None:
        self._edited()
        self.methods.updateGeometry()
        self.plotTabs.setTabVisible(1, self.methods.currentIndex() == 0)
        self.plotTabs.setCurrentIndex(0)
        self.displaySaved()
        if self.methods.currentIndex() == 1 and self.savedRecord() is None:
            self.sourcePreviewRequested.emit()

    def _referenceDragged(self, *_args) -> None:
        self.level.setValue(self.referenceLine.value())

    def _referenceChanged(self, value: float) -> None:
        self.referenceLine.setValue(value)
        if self._valueRange is not None:
            low, high, unit = self._valueRange
            with QSignalBlocker(self.levelSlider):
                fraction = float(np.clip((value-low)/(high-low), 0, 1)) if high > low else 0.5
                self.levelSlider.setValue(round(1000 * fraction))
            outside = " · reference outside signal; use Center reference" if not low <= value <= high else ""
            self.referenceStatus.setText(f"Signal range: {low:.6g} … {high:.6g} {unit}" + outside)

    def _sliderChanged(self, position: int) -> None:
        if self._valueRange is not None:
            low, high, _unit = self._valueRange
            self.level.setValue(low + (high-low)*position/1000)

    def _centerReference(self) -> None:
        if self._valueRange is not None:
            low, high, _unit = self._valueRange
            self.level.setValue((low+high)/2)
            self.signalPlot.resetView()

    def refreshDraftDisplay(self) -> None:
        """参考线编辑不重建图表，避免拖动中失去把手；旧事件只对应原配方。"""
        if self.methods.currentIndex() == 0:
            self.displaySaved()
            return
        record = self.savedRecord()
        metadata = record.extra_fields.get("analysis") if record else None
        matches = False
        if isinstance(metadata, dict) and metadata.get("version") == 1:
            try:
                spec = metadata["spec"]
                selection = metadata["selection"]
                matches = (self.recurrenceSpec() == RecurrenceSpec(**spec)
                           and self.selection().start_frame == selection["start_frame"]
                           and self.selection().end_frame == selection["end_frame"]
                           and self.selection().smoothed == selection["smoothed"])
            except (KeyError, TypeError, ValueError):
                pass
        for line in self._eventLines:
            line.setVisible(matches)

    def selection(self) -> SignalSelection:
        track_id = self.trackChoice.currentData()
        if track_id is None:
            raise ValueError("Select a track")
        return SignalSelection(UUID(str(track_id)), self.quantityChoice.currentText(), self.startFrame.value(),
                               self.endFrame.value(), self.sourceChoice.currentIndex() == 1)

    def fitSpec(self) -> FitSpec:
        parameters = []
        for row in range(self.parameterTable.rowCount()):
            texts = [self.parameterTable.item(row, col).text().strip() for col in range(4)]
            parameters.append(FitParameter(texts[0], float(texts[1]), float(texts[2]) if texts[2] else None,
                                           float(texts[3]) if texts[3] else None,
                                           self.parameterTable.item(row, 4).checkState() == Qt.CheckState.Checked))
        return FitSpec(self.editor.text(), tuple(parameters), self.budget.value())

    def resultFormulas(self) -> tuple[tuple[str, str], ...]:
        if not self.resultFormula.text().strip() and not self.resultName.text().strip():
            return ()
        return ((self.resultName.text().strip(), self.resultFormula.text().strip()),)

    def recurrenceSpec(self) -> RecurrenceSpec:
        wrapped = self.quantityChoice.currentText() == "theta" and self.sourceChoice.currentIndex() == 0
        return RecurrenceSpec(self.level.value(), "rising" if self.direction.currentIndex() == 0 else "falling",
                               self.hysteresis.value(), self.separation.value(), wrapped)

    def setContext(self, session, video_id, *, pending=False) -> None:
        tracks = tuple(track for track in session.tracks if track.video_id == video_id) if session else ()
        timeline = next((item for item in session.project.timelines if item.video_id == video_id), None) if session else None
        context = (session.project.project_id, video_id) if session else None
        self._loading = True
        selected = self.trackChoice.currentData()
        choices = [(self.trackChoice.itemData(i), self.trackChoice.itemText(i)) for i in range(self.trackChoice.count())]
        wanted = [(str(track.track_id), track.name) for track in tracks]
        if choices != wanted:
            self.trackChoice.clear()
            for identity, name in wanted:
                self.trackChoice.addItem(name, identity)
            index = self.trackChoice.findData(selected)
            self.trackChoice.setCurrentIndex(max(0, index))
        if timeline:
            for widget in (self.startFrame, self.endFrame):
                widget.setRange(*timeline.working_zone)
            if context != self._context:
                self.startFrame.setValue(timeline.working_zone[0])
                self.endFrame.setValue(timeline.working_zone[1])
        changed_context = context != self._context
        self._context = context
        self._loading = False
        enabled = bool(tracks) and session.can_measure(video_id) and not pending
        for button in (self.previewButton, self.fitButton, self.recurrenceButton):
            button.setEnabled(enabled)
        self.cancelButton.setEnabled(pending)
        self.undoButton.setEnabled(bool(session) and not pending and session.can_undo_analysis)
        self.redoButton.setEnabled(bool(session) and not pending and session.can_redo_analysis)
        self._session = session
        self._video_id = video_id
        if changed_context:
            self._cache = None
            self.jobLabel.clear()
            self.draftLabel.setText("Draft — no analysis applied")
        if timeline:
            self.contextLabel.setText("Source charts required · t = 0 at interval start · angles in rad. "
                                      + ("Approximate timing (details retained)." if session.measurement_timing_detail(video_id) else "Verified nominal timing."))
        key = (context, self.trackChoice.currentData(), self.quantityChoice.currentText(), session.project.derived if session else ())
        if key != self._cache:
            self._cache = key
            self.displaySaved()

    def savedRecord(self) -> DerivedData | None:
        session = getattr(self, "_session", None)
        if session is None or self.trackChoice.currentData() is None:
            return None
        family = "function_fit" if self.methods.currentIndex() == 0 else "signal_recurrence"
        return session.derived_data(UUID(self.trackChoice.currentData()), f"{family}_{self.quantityChoice.currentText()}")

    def restoreSaved(self) -> None:
        record = self.savedRecord()
        metadata = record.extra_fields.get("analysis") if record else None
        if not isinstance(metadata, dict) or metadata.get("version") != 1:
            self.jobLabel.setText("No readable saved settings for this track / quantity / tool")
            return
        interval = metadata.get("interval")
        if (not isinstance(interval, list) or len(interval) != 2
                or not all(type(value) is int for value in interval)
                or not self.startFrame.minimum() <= interval[0] <= interval[1] <= self.endFrame.maximum()):
            self.jobLabel.setText("Saved interval is outside the working zone or unreadable; expand the working zone before restoring")
            return
        self._loading = True
        try:
            selection = metadata["selection"]
            self.sourceChoice.setCurrentIndex(1 if selection["smoothed"] else 0)
            self.startFrame.setValue(selection["start_frame"])
            self.endFrame.setValue(selection["end_frame"])
            spec = metadata["spec"]
            if record.kind.startswith("function_fit_"):
                self.editor.setText(spec["expression"])
                parameters = {parameter["name"]: parameter for parameter in spec["parameters"]}
                for row in range(self.parameterTable.rowCount()):
                    parameter = parameters[self.parameterTable.item(row, 0).text()]
                    for col, key in enumerate(("initial", "lower", "upper"), 1):
                        self.parameterTable.item(row, col).setText("" if parameter[key] is None else str(parameter[key]))
                    self.parameterTable.item(row, 4).setCheckState(Qt.CheckState.Checked if parameter["fixed"] else Qt.CheckState.Unchecked)
                self.budget.setValue(spec["max_evaluations"])
                formulas = metadata["summary"].get("result_formulas", [])
                self.resultName.setText(formulas[0]["name"] if formulas else "")
                self.resultFormula.setText(formulas[0]["formula"] if formulas else "")
            else:
                self.level.setValue(spec["level"])
                self.hysteresis.setValue(spec["hysteresis"])
                self.separation.setValue(spec["min_separation_s"])
                self.direction.setCurrentIndex(0 if spec["direction"] == "rising" else 1)
        except (KeyError, TypeError, ValueError) as error:
            self.jobLabel.setText(f"Saved settings are unreadable: {error}")
            self.draftLabel.setText("Saved settings could not be fully restored")
            return
        finally:
            self._loading = False
        self.settingsChanged.emit()
        self.draftLabel.setText("Saved settings restored; stale results remain read-only")
        self.displaySaved()

    def renderSamples(self, samples, unit, predicted=None, residual=None, *, wrapped=False, title="Initial preview") -> None:
        self.signalPlot.clear()
        self.residualPlot.clear()
        self._eventLines = []
        if not samples:
            return
        frames = [int(row[0]) for row in samples]
        times, values = np.array([row[2] for row in samples]), np.array([row[3] for row in samples])
        connect = np.array([right == left+1 for left, right in zip(frames, frames[1:])] + [False])
        if wrapped:
            connect[:-1] &= np.abs(np.diff(values)) <= np.pi
        self._valueRange = (float(np.min(values)), float(np.max(values)), unit)
        self.signalPlot.setDataRange(times, values)
        self._referenceChanged(self.level.value())
        self.signalPlot.setLabel("left", self.quantityChoice.currentText(), units=unit)
        actual = self.signalPlot.plot(times, values, connect=connect, pen=pg.mkPen("#008ca8", width=2),
                                       symbol="o", symbolSize=5, data=frames, name="Measured source")
        actual.sigPointsClicked.connect(lambda _curve, points, _event: self.frameRequested.emit(int(points[0].data())) if points else None)
        if predicted is not None:
            self.signalPlot.plot(times, predicted, connect=connect, pen=pg.mkPen("#d05a32", width=2), name=title)
        if residual is not None:
            self.residualPlot.setDataRange(times, np.asarray(residual))
            self.residualPlot.setLabel("left", "Measured − predicted", units=unit)
            scatter = self.residualPlot.plot(times, residual, connect=connect, pen=pg.mkPen("#008ca8"), symbol="o", symbolSize=5, data=frames)
            scatter.sigPointsClicked.connect(lambda _curve, points, _event: self.frameRequested.emit(int(points[0].data())) if points else None)
        if self.methods.currentIndex() == 1:
            self.signalPlot.addItem(self.referenceLine, ignoreBounds=True)
            self.referenceLine.setValue(self.level.value())

    def displaySaved(self) -> None:
        record = self.savedRecord()
        self.restoreButton.setEnabled(record is not None)
        metadata = record.extra_fields.get("analysis") if record else None
        if not isinstance(metadata, dict) or metadata.get("version") != 1:
            self.signalPlot.clear()
            self.residualPlot.clear()
            self.summary.setPlainText("Unsupported saved result version (read-only)." if record else "No saved result for this quantity / tool.")
            self.resultLabel.setText(self.summary.toPlainText())
            self._valueRange = None
            self._eventLines = []
            return
        try:
            samples = [tuple(row[key] for key in ("frame_index", "video_time_s", "relative_time_s", "value", "segment_index")) for row in metadata["samples"]]
            fitting = record.kind.startswith("function_fit_")
            predicted = [row[0] for row in record.values] if fitting else None
            residual = [row[1] for row in record.values] if fitting else None
            source = metadata["source_snapshot"]
            self.renderSamples(samples, record.unit, predicted, residual, wrapped=source["kind"] == "angular_position", title="Saved fit")
            summary = metadata["summary"]
            if not fitting:
                for event in summary["events"]:
                    relative = event["time_s"] - (samples[0][1] - samples[0][2])
                    line = pg.InfiniteLine(pos=relative, angle=90, pen=pg.mkPen("#c07800", style=Qt.PenStyle.DashLine))
                    self.signalPlot.addItem(line, ignoreBounds=True)
                    self._eventLines.append(line)
            if fitting:
                self.resultLabel.setText(f"Saved fit ({record.status}) · RMSE {summary['rmse']:.6g} {record.unit} · {len(samples)} samples")
                details = (f"{summary['status']}: {summary['message']}\n"
                           + f"RMSE: {summary['rmse']:.8g} {record.unit}; evaluations: {summary['evaluations']}\n"
                           + "Parameters: " + ", ".join(f"{name}={value:.8g}" for name, value in summary["parameter_values"])
                           + "\nSaved formula: " + metadata["spec"]["expression"])
                self.resultLabel.setText(self.resultLabel.text() + "\n" + ", ".join(f"{name}={value:.6g}" for name, value in summary["parameter_values"]))
                for item in summary.get("result_formulas", []):
                    self.resultLabel.setText(self.resultLabel.text() + f"\n{item['name']}: " + (f"{item['value']:.6g}" if item["error"] is None else item["error"]))
                    details += f"\nUser result {item['name']} = {item['formula']}: " + (str(item["value"]) if item["error"] is None else item["error"])
            else:
                mean, std = summary["mean_interval_s"], summary["sample_std_s"]
                meanText = f"{mean:.6g} s" if mean is not None else "unavailable"
                stdText = f"{std:.6g} s" if std is not None else "unavailable"
                self.resultLabel.setText(f"Saved crossings ({record.status}) · {len(summary['events'])} events\nMean interval: {meanText} · sample std: {stdText}\n{summary['message']}")
                details = (f"{summary['measurement_status']}: {summary['message']}\n"
                           + f"Events: {len(summary['events'])}; intervals: {len(summary['intervals_s'])}; "
                           + f"mean: {mean if mean is not None else 'unavailable'} s; sample std: {std if std is not None else 'unavailable'} s\n"
                           + "Intervals (s): " + ", ".join(f"{value:.6g}" for value in summary["intervals_s"])
                           + "\nSaved crossing settings: " + str(metadata["spec"]))
                for event in summary["events"]:
                    details += f"\nEvent: frames {event['lower_frame_index']}–{event['upper_frame_index']}, video time {event['time_s']:.6f} s"
                self.refreshDraftDisplay()
            source_extras = source.get("extra_fields")
            timing = source_extras.get("timing_context") if isinstance(source_extras, dict) else None
            if not isinstance(timing, dict):
                timing_message = "Saved timing metadata unreadable; cached result only\n"
            else:
                timing_message = "Approximate timing\n" if timing.get("approximation") else ""
            if timing_message:
                self.resultLabel.setText(self.resultLabel.text() + "\n" + timing_message.strip())
            self.summary.setPlainText(f"Saved result: {record.status} — {source['kind']} [{record.unit}]\n"
                                     + f"Samples: {len(samples)}; source frames {metadata['interval']}; t=0 at interval start\n"
                                     + timing_message
                                     + details)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            self.summary.setPlainText(f"Saved result is read-only; metadata cannot be displayed: {error}")
            self.resultLabel.setText(self.summary.toPlainText())
