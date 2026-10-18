"""GUI层：单量公式 / 参数编辑与独立重复间隔工具，不执行拟合。"""

from uuid import UUID

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, QSize, Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QSlider, QSizePolicy,
)

from ai_physics_tracker.application.signal_analysis_job import SignalSelection
from ai_physics_tracker.domain.analysis import QUANTITIES
from ai_physics_tracker.domain.derived import DerivedData
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec
from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.domain.recurrence import RecurrenceSpec, CrossingEvent
from ai_physics_tracker.gui.formula_editor import FormulaEditor
from ai_physics_tracker.gui.fit_explanation import explain_fit
from ai_physics_tracker.gui.analysis_plot import AnalysisPlot, AnalysisScrollArea
from ai_physics_tracker.gui.signal_history import SignalHistory


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

    estimateRequested = Signal()
    prepareRequested = Signal()
    setupRequested = Signal()
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
    feedbackRequested = Signal()
    historyChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading = False
        self.initialProtected = False
        self._viewingDiskSaved = False
        self._previewRange = None
        self._context = None
        self._cache = None
        self._valueRange = None
        self._eventLines = []
        self._eventPreview = False
        self._eventSamplesMatch = False
        self._allowCachedEvents = True
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
        self.fitReadinessLabel, self.crossingReadinessLabel = QLabel(), QLabel()
        for label in (self.fitReadinessLabel, self.crossingReadinessLabel):
            label.setWordWrap(True)
        self.draftLabel = QLabel("Draft — no analysis applied")
        self.draftLabel.setWordWrap(True)
        self.modelLabel = QLabel()
        self.modelLabel.setTextFormat(Qt.TextFormat.PlainText)
        self.modelLabel.setWordWrap(True)
        self.modelLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
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
        self.restoreButton = QPushButton("Use recorded setup")
        self.returnDraftButton = QPushButton("Return to my draft")
        self.returnDraftButton.hide()
        self.returnDraftButton.clicked.connect(lambda: self.history.leave())
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
        parameterOptions = QCheckBox("Parameter bounds / fixed values")
        self.parameterOptions = parameterOptions
        parameterOptions.setChecked(False)
        parameterOptions.toggled.connect(lambda checked: [self.parameterTable.setColumnHidden(col, not checked) for col in (2, 3, 4)])
        for col in (2, 3, 4):
            self.parameterTable.setColumnHidden(col, True)
        fitLayout.addWidget(parameterOptions)
        advanced = QCheckBox("Optional settings")
        self.optionalGroup = advanced
        advanced.setChecked(False)
        advancedFields = QWidget()
        form = QFormLayout(advancedFields)
        form.addRow("Model evaluation limit", self.budget)
        form.addRow(self.resultName, self.resultFormula)
        advancedFields.hide()
        advanced.toggled.connect(advancedFields.setVisible)
        fitLayout.addWidget(advanced)
        fitLayout.addWidget(advancedFields)
        fitButtons = QHBoxLayout()
        fitButtons.addWidget(self.previewButton)
        fitButtons.addWidget(self.fitButton)

        self.methods.addTab(fit, "Function fit")
        recurrence = QWidget()
        recurrenceLayout = QFormLayout(recurrence)
        note = QLabel("Source and crossing preview update automatically.\nSet the orange reference → Measure intervals.\nRepeat intervals are a period only with one crossing per cycle.")
        note.setWordWrap(True)
        note.setToolTip("Interpret intervals as a period only when each cycle has one same-direction crossing. Gaps and wrapped-angle jumps are never bridged.")
        recurrenceLayout.addRow(note)
        self.showSourceButton = QPushButton("Preview source / crossings")
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
        noiseOptions = QCheckBox("Noise / separation options")
        self.noiseOptions = noiseOptions
        noiseOptions.setChecked(False)
        noiseFields = QWidget()
        noiseForm = QFormLayout(noiseFields)
        noiseForm.addRow("Confirmation band", self.hysteresis)
        noiseForm.addRow("Minimum separation (s)", self.separation)
        noiseFields.hide()
        noiseOptions.toggled.connect(noiseFields.setVisible)
        recurrenceLayout.addRow(noiseOptions)
        recurrenceLayout.addRow(noiseFields)

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
        layout.addWidget(self.contextLabel)
        workspace = QHBoxLayout()
        chartColumn = QVBoxLayout()
        chartColumn.addWidget(self.draftLabel)
        chartColumn.addWidget(self.modelLabel)
        chartColumn.addLayout(plotActions)
        self.showModelButton = QPushButton("Show whole model")
        self.showModelButton.clicked.connect(self.showWholeModel)
        chartColumn.addWidget(self.showModelButton)
        chartColumn.addWidget(self.plotTabs, 1)
        helpLabel = QLabel("Scroll: page · Ctrl+scroll / buttons: zoom · Click a point: source frame")
        helpLabel.setWordWrap(True)
        chartColumn.addWidget(helpLabel)
        workspace.addLayout(chartColumn, 3)
        side = QWidget()
        side.setMinimumWidth(300)
        side.setMaximumWidth(460)
        sideLayout = QVBoxLayout(side)
        sideLayout.setContentsMargins(0, 0, 0, 0)
        self.meaningLabel = QLabel("Choose data and an editable example, then inspect the initial curve and Fit.")
        self.meaningLabel.setWordWrap(True)
        sideLayout.addWidget(self.jobLabel)
        sideLayout.addWidget(self.meaningLabel)
        self.resultLabel = QLabel("No saved result yet.")
        self.resultLabel.setWordWrap(True)
        sideLayout.addWidget(self.resultLabel)
        sideLayout.addWidget(self.returnDraftButton)
        sideLayout.addWidget(self.restoreButton)
        self.conversionActions = QWidget()
        conversionLayout = QVBoxLayout(self.conversionActions)
        self.editConversionButton = QPushButton("Edit optional result formula")
        self.removeConversionButton = QPushButton("Clear optional result formula")
        self.measureInsteadButton = QPushButton("Measure repeat intervals instead")
        for button in (self.editConversionButton, self.removeConversionButton, self.measureInsteadButton):
            conversionLayout.addWidget(button)
        self.editConversionButton.clicked.connect(self.editConversion)
        self.removeConversionButton.clicked.connect(self.clearConversion)
        self.measureInsteadButton.clicked.connect(lambda: self.methods.setCurrentIndex(1))
        self.conversionActions.hide()
        sideLayout.addWidget(self.conversionActions)
        sideLayout.addWidget(self.fitReadinessLabel)
        sideLayout.addWidget(self.crossingReadinessLabel)
        sideLayout.addLayout(fitButtons)
        sideLayout.addWidget(self.recurrenceButton)
        sideLayout.addWidget(self.cancelButton)
        self.estimateButton = QPushButton("Estimate initial values from data")
        self.estimateButton.clicked.connect(self.estimateRequested)
        self.estimateLabel = QLabel("Initial values are editable. Estimation supports the examples below.")
        self.estimateLabel.setWordWrap(True)
        preparation = QHBoxLayout()
        self.prepareSourceButton = QPushButton("Retry source / preview")
        for button, signal in ((self.prepareSourceButton, self.prepareRequested),
                               (QPushButton("Calibration / reference"), self.setupRequested)):
            button.clicked.connect(signal)
            preparation.addWidget(button)
        # 准备入口分行，窄窗不靠隐藏横向条裁掉按钮。
        preparationHost = QWidget()
        self.preparationHost = preparationHost
        preparationLayout = QVBoxLayout(preparationHost)
        while preparation.count():
            preparationLayout.addWidget(preparation.takeAt(0).widget())
        controls = QWidget()
        controlsLayout = QVBoxLayout(controls)
        controlsLayout.addWidget(dataGroup)
        controlsLayout.addWidget(self.estimateLabel)
        controlsLayout.addWidget(self.estimateButton)
        controlsLayout.addWidget(self.methods)
        controlsLayout.addWidget(preparationHost)
        history = QHBoxLayout()
        self.previousButton = QPushButton("Last saved result")
        self.previousButton.clicked.connect(lambda: self.displaySaved(previous=True, notify=True))
        self.latestButton = QPushButton("Latest applied result")
        self.latestButton.clicked.connect(lambda: self.displaySaved(notify=True))
        history.addWidget(self.latestButton)
        history.addWidget(self.previousButton)
        controlsLayout.addLayout(history)
        resultHistory = QHBoxLayout()
        resultHistory.addWidget(self.undoButton)
        resultHistory.addWidget(self.redoButton)
        controlsLayout.addLayout(resultHistory)
        self.detailsGroup = QCheckBox("Result details / provenance")
        self.detailsGroup.setChecked(False)
        self.summary.hide()
        self.detailsGroup.toggled.connect(self.summary.setVisible)
        controlsLayout.addWidget(self.detailsGroup)
        controlsLayout.addWidget(self.summary)
        self.attemptChoice = QComboBox()
        self.attemptChoice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.attemptChoice.setMinimumContentsLength(8)
        self.attemptDetails = QPlainTextEdit()
        self.attemptDetails.setReadOnly(True)
        self.attemptDetails.setMaximumHeight(130)
        self.journalLabel = QLabel()
        self.journalLabel.setWordWrap(True)
        controlsLayout.addWidget(QLabel("Fit history — select an attempt"))
        controlsLayout.addWidget(self.attemptChoice)
        controlsLayout.addWidget(self.attemptDetails)
        controlsLayout.addWidget(self.journalLabel)
        self.retryJournalButton = QPushButton("Retry saving attempt log")
        controlsLayout.addWidget(self.retryJournalButton)
        self.controlsScroll = AnalysisScrollArea()
        self.controlsScroll.setWidget(controls)
        self.controlsScroll.setMinimumHeight(220)
        sideLayout.addWidget(self.controlsScroll, 1)
        workspace.addWidget(side, 2)
        layout.addLayout(workspace, 1)
        self.setMinimumHeight(540)
        self.pageScrollRequested.connect(self.controlsScroll.scrollPage)
        self.editor.formulaChanged.connect(self._formulaChanged)
        self.parameterTable.itemChanged.connect(self._parameterEdited)
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
        self.history = SignalHistory(self)
        self._formulaChanged()
        self._methodVisibility()
        self.editor.setQuantityLabel("x(t)")

    def eventFilter(self, watched, event) -> bool:
        # 滚动表单时不能因为指针经过数字框 / 下拉框就意外修改测量配方。
        if event.type() == QEvent.Type.Wheel:
            delta = event.pixelDelta().y() or event.angleDelta().y() / 120 * 40
            self.pageScrollRequested.emit(round(delta))
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def showFeedback(self, text: str) -> None:
        """显式操作反馈定位到图旁；自动预览不抢夺用户正在编辑的滚动位置。"""
        self.jobLabel.setText(text)
        self.feedbackRequested.emit()

    def showFormula(self, expression: str, parameters: tuple[tuple[str, str], ...], *, fitted: bool = False) -> None:
        """展示当前曲线实际使用的公式和参数，不从仍可编辑的草稿推断历史模型。"""
        self.modelLabel.setText(
            f"Displayed formula: {self.quantityChoice.currentText()}(t) = {expression}\n"
            + ("Fitted parameters: " if fitted else "Initial values: ")
            + (", ".join(f"{name}={value}" for name, value in parameters) or "none"))
        try:
            parsed = parse_expression(expression)
        except ValueError as error:
            self.meaningLabel.setText(f"Invalid formula: {error}")
            return
        if not parsed.uses_time:
            self.meaningLabel.setText(
                "Fits a constant level: no t, so no time variation is modeled. "
                "Right-hand symbols such as theta are fitted parameters, not another measured quantity.")
        else:
            self.meaningLabel.setText(
                "t is seconds from interval start. "
                + ("This curve uses the recorded fitted values. The parameter table shows the recorded initial values."
                   if fitted else "This is an initial curve. Click Fit to adjust the free parameters."))

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

    def _parameterEdited(self, *_args) -> None:
        if not self._loading:
            self.initialProtected = True
            self.estimateLabel.setText("Manual values / constraints protected. Use Estimate to explicitly replace free initial values.")
        self._edited()

    def _methodVisibility(self) -> None:
        fitting = self.methods.currentIndex() == 0
        self.prepareSourceButton.setText("Retry source / preview")
        for widget in (self.previewButton, self.fitButton, self.fitReadinessLabel, self.estimateButton, self.estimateLabel):
            widget.setVisible(fitting)
        self.recurrenceButton.setVisible(not fitting)
        self.crossingReadinessLabel.setVisible(not fitting and bool(self.crossingReadinessLabel.text()))

    def setEstimatedValues(self, spec: FitSpec, reason: str) -> None:
        """只更新已由编排层核对通过的初值；不修改Fixed或边界。"""
        with QSignalBlocker(self.parameterTable):
            values = {parameter.name: parameter.initial for parameter in spec.parameters}
            for row in range(self.parameterTable.rowCount()):
                self.parameterTable.item(row, 1).setText(format(values[self.parameterTable.item(row, 0).text()], '.16g'))
        self.estimateLabel.setText(reason)

    def editConversion(self) -> None:
        self.optionalGroup.setChecked(True)
        self.controlsScroll.ensureWidgetVisible(self.resultFormula)
        self.resultFormula.setFocus()

    def clearConversion(self) -> None:
        self.resultName.clear()
        self.resultFormula.clear()
        self.conversionActions.hide()

    def showWholeModel(self) -> None:
        if self._previewRange is not None:
            times, values = self._previewRange
            sourceRange = self.signalPlot._dataRange
            self.signalPlot.setDataRange(times, values)
            self.signalPlot._dataRange = sourceRange
            self.showFeedback("Showing the whole model range. Reset view restores the measured signal range.")

    def _edited(self, *_args) -> None:
        if not self._loading:
            self.draftLabel.setText("Draft changed — saved results use their recorded settings")
            self.settingsChanged.emit()

    def _sourceChanged(self, *_args) -> None:
        if not self._loading:
            self.estimateLabel.setText("Data / interval changed. Current initial values kept; choose Estimate to refresh them.")
            self._edited()
            if self.methods.currentIndex() == 1:
                self.sourcePreviewRequested.emit()

    def _targetChanged(self, *_args) -> None:
        if self._loading:
            return
        self.editor.setQuantityLabel(self.quantityChoice.currentText() + "(t)")
        self.refreshSourceChoice()
        self._cache = None
        self.estimateLabel.setText("Target changed. Current initial values kept; choose Estimate to prepare values for this signal.")
        self.targetChanged.emit()

    def refreshSourceChoice(self) -> None:
        """导数量只有既定SG来源，显示真实含义而非遗留的平滑选择。"""
        selectable = self.quantityChoice.currentText() in ("x", "y", "theta")
        self.sourceChoice.setItemText(0, "Measured" if selectable else "SG derivative")
        self.sourceChoice.setItemText(1, "Smoothed" if selectable else "SG derivative")
        self.sourceChoice.setEnabled(selectable and not self.history.active)

    def _methodChanged(self, *_args) -> None:
        if self._loading:
            return
        self._edited()
        self.methods.updateGeometry()
        self._methodVisibility()
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

    def clearCrossingEvents(self) -> None:
        for line in self._eventLines:
            self.signalPlot.removeItem(line)
        self._eventLines = []
        self._eventPreview = False
        self._eventSamplesMatch = False

    def renderCrossingPreview(self, events: tuple[CrossingEvent, ...], origin: float) -> None:
        """只绘制当前草稿候选事件，不改保存结果或参考线。"""
        self.clearCrossingEvents()
        for event in events:
            line = pg.InfiniteLine(pos=event.time_s-origin, angle=90,
                                   pen=pg.mkPen("#7661aa", width=2, style=Qt.PenStyle.DotLine))
            self.signalPlot.addItem(line, ignoreBounds=True)
            self._eventLines.append(line)
        self._eventPreview = True

    def refreshDraftDisplay(self) -> None:
        """参考线编辑不重建图表，避免拖动中失去把手；旧事件只对应原配方。"""
        if self.methods.currentIndex() == 0:
            return
        if self._eventPreview:
            self.clearCrossingEvents()
        record = self.savedRecord()
        metadata = record.extra_fields.get("analysis") if record else None
        matches = False
        if isinstance(metadata, dict) and metadata.get("version") == 1:
            try:
                spec = metadata["spec"]
                selection = metadata["selection"]
                matches = (self._eventSamplesMatch and self.recurrenceSpec() == RecurrenceSpec(**spec)
                           and self.selection().start_frame == selection["start_frame"]
                           and self.selection().end_frame == selection["end_frame"]
                           and self.selection().smoothed == selection["smoothed"])
                if matches and not self._eventLines:
                    first = metadata["samples"][0]
                    origin = first["video_time_s"] - first["relative_time_s"]
                    for event in metadata["summary"]["events"]:
                        line = pg.InfiniteLine(pos=event["time_s"]-origin, angle=90,
                                               pen=pg.mkPen("#c07800", style=Qt.PenStyle.DashLine))
                        self.signalPlot.addItem(line, ignoreBounds=True)
                        self._eventLines.append(line)
            except (KeyError, IndexError, TypeError, ValueError):
                matches = False
        for line in self._eventLines:
            line.setVisible(matches)

    def selection(self) -> SignalSelection:
        track_id = self.trackChoice.currentData()
        if track_id is None:
            raise ValueError("Select a track")
        return SignalSelection(UUID(str(track_id)), self.quantityChoice.currentText(), self.startFrame.value(),
                               self.endFrame.value(), self.smoothedSource())

    def smoothedSource(self) -> bool:
        return self.sourceChoice.currentIndex() == 1 and self.quantityChoice.currentText() in ("x", "y", "theta")

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
        if self.history.active:
            if context == self._context:
                self._session, self._video_id = session, video_id
                self.history.lock()
                return
            self.history.leave(discard=True)
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
        if pending:
            reason = "Calculation in progress — wait or Cancel calculation."
        elif session is None or video_id is None:
            reason = "Open a project and select a video before fitting or measuring."
        elif not tracks:
            reason = "Add a track before fitting or measuring."
        elif not session.can_measure(video_id):
            reason = "Timing detection is incomplete or unavailable. See the video timing status; retry detection if offered. Cached results remain readable."
        else:
            reason = ""
        for label in (self.fitReadinessLabel, self.crossingReadinessLabel):
            label.setText(reason)
            label.setVisible(bool(reason))
        for button in (self.previewButton, self.fitButton, self.recurrenceButton):
            button.setEnabled(not reason)
            button.setToolTip(reason)
        self.cancelButton.setEnabled(pending)
        self.undoButton.setEnabled(bool(session) and not pending and session.can_undo_analysis)
        self.redoButton.setEnabled(bool(session) and not pending and session.can_redo_analysis)
        self._session = session
        self._video_id = video_id
        self.previousButton.setEnabled(not pending and self.savedRecord(disk=True) is not None)
        self.latestButton.setEnabled(not pending and self.savedRecord(disk=False) is not None)
        if changed_context:
            self._cache = None
            self.initialProtected = False
            self.jobLabel.clear()
            self.draftLabel.setText("Draft — no analysis applied")
        if timeline and self._valueRange is None:
            self.contextLabel.setToolTip(session.measurement_timing_detail(video_id) or "Nominal video time is retained with every sample.")
            self.contextLabel.setText("Source charts required · t = 0 at interval start · angles: rad · derivatives: recorded SG. "
                                      + ("Timing not authorized; cached results only." if not session.can_measure(video_id)
                                         else "Approximate timing (details retained)." if session.measurement_timing_detail(video_id) else "Verified nominal timing."))
        key = (context, self.trackChoice.currentData(), self.quantityChoice.currentText(), session.project.derived if session else (), self.savedRecord(disk=True))
        if key != self._cache:
            self._cache = key
            self.displaySaved()

    def savedRecord(self, *, disk: bool | None = None) -> DerivedData | None:
        if disk is None and self.history.active:
            return self.history.record
        session = getattr(self, "_session", None)
        if session is None or self.trackChoice.currentData() is None:
            return None
        family = "function_fit" if self.methods.currentIndex() == 0 else "signal_recurrence"
        reader = session.saved_derived_data if (self._viewingDiskSaved if disk is None else disk) else session.derived_data
        return reader(UUID(self.trackChoice.currentData()), f"{family}_{self.quantityChoice.currentText()}")

    def restoreSaved(self) -> None:
        if not self.history.active:
            record = self.savedRecord()
            metadata = record.extra_fields.get("analysis") if record else None
            if not isinstance(metadata, dict) or metadata.get('version') != 1:
                self.showFeedback('No readable recorded setup for this target.')
                return
            try:
                self.history.view(metadata, record=record)
            except (KeyError, TypeError, ValueError) as error:
                self.history.lock()
                self.showFeedback(f'History is unreadable: {error}. Return to my draft to continue.')
                return
        self.history.leave(adopt=True)

    def renderSamples(self, samples, unit, predicted=None, residual=None, *, wrapped=False, title="Initial preview") -> None:
        self.signalPlot.clear()
        self.residualPlot.clear()
        self._eventLines = []
        self._eventPreview = False
        self._eventSamplesMatch = False
        record = self.savedRecord()
        metadata = record.extra_fields.get("analysis") if record else None
        if self._allowCachedEvents and isinstance(metadata, dict) and metadata.get("version") == 1:
            try:
                expected = tuple(tuple(row[key] for key in ("frame_index", "video_time_s", "relative_time_s", "value", "segment_index")) for row in metadata["samples"])
                self._eventSamplesMatch = tuple(samples) == expected
            except (KeyError, TypeError, ValueError):
                pass
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
        actual.sigPointsClicked.connect(lambda _curve, points, _event: self._requestSampleFrame(int(points[0].data())) if points else None)
        self._previewRange = (times, np.concatenate((values, predicted))) if predicted is not None else None
        outside = predicted is not None and (min(predicted) < min(values) or max(predicted) > max(values))
        self.showModelButton.setText("Model outside source view — show whole model" if outside else "Show whole model")
        if predicted is not None:
            self.signalPlot.plot(times, predicted, connect=connect, pen=pg.mkPen("#d05a32", width=2), name=title)
        if residual is not None:
            self.residualPlot.setDataRange(times, np.asarray(residual))
            self.residualPlot.setLabel("left", "Measured − predicted", units=unit)
            scatter = self.residualPlot.plot(times, residual, connect=connect, pen=pg.mkPen("#008ca8"), symbol="o", symbolSize=5, data=frames)
            scatter.sigPointsClicked.connect(lambda _curve, points, _event: self._requestSampleFrame(int(points[0].data())) if points else None)
        if self.methods.currentIndex() == 1:
            self.signalPlot.addItem(self.referenceLine, ignoreBounds=True)
            self.referenceLine.setValue(self.level.value())

    def _requestSampleFrame(self, frame: int) -> None:
        if self.history.active and not any(str(track.track_id) == self.trackChoice.currentData() and track.video_id == self._video_id
                                           for track in self._session.tracks):
            self.showFeedback('This record belongs to another video or a missing track. Open its original video to locate a source frame.')
            return
        self.frameRequested.emit(frame)

    def displaySaved(self, *, previous: bool = False, notify: bool = False) -> None:
        if self.history.active and not notify:
            return
        self._allowCachedEvents = True
        if notify and self.cancelButton.isEnabled():
            self.showFeedback('Wait for the current calculation or cancel it before viewing history.')
            return
        self._viewingDiskSaved = previous
        record = self.savedRecord(disk=previous)
        if notify:
            if record is None:
                self.showFeedback('No saved result for this quantity / tool.')
                return
            try:
                metadata = record.extra_fields.get('analysis', {})
                if not isinstance(metadata, dict) or metadata.get('version') != 1:
                    raise ValueError('Unsupported recorded result version')
                self.signalPlot.clear()
                self.residualPlot.clear()
                self._previewRange = self._valueRange = None
                self.history.view(metadata, record=record)
            except (KeyError, TypeError, ValueError) as error:
                self.signalPlot.clear()
                self.residualPlot.clear()
                self._previewRange = self._valueRange = None
                self.history.lock()
                self.showFeedback(f'History is unreadable: {error}. Return to your draft to continue.')
                return
        self.previousButton.setEnabled(self.savedRecord(disk=True) is not None)
        self.latestButton.setEnabled(self.savedRecord(disk=False) is not None)
        self.conversionActions.hide()
        self.restoreButton.setEnabled(record is not None)
        self.draftLabel.setText("Last disk-saved result — most recent Save snapshot" if previous else "Latest applied result — recorded settings; edits require a new Fit")
        if notify:
            self.showFeedback(
                ("Showing the last disk-saved result (most recent Save, not the previous attempt). " if previous else "Showing the latest applied result. ")
                + "The full form now shows its recorded setup, read-only. Your draft is kept; Return to my draft or Use recorded setup to continue.")
        metadata = record.extra_fields.get("analysis") if record else None
        if not isinstance(metadata, dict) or metadata.get("version") != 1:
            self.signalPlot.clear()
            self.residualPlot.clear()
            self.summary.setPlainText("Unsupported saved result version (read-only)." if record else "No saved result for this quantity / tool.")
            self.resultLabel.setText(self.summary.toPlainText())
            self.modelLabel.clear()
            self.meaningLabel.clear()
            self._valueRange = None
            self._eventLines = []
            return
        try:
            samples = [tuple(row[key] for key in ("frame_index", "video_time_s", "relative_time_s", "value", "segment_index")) for row in metadata["samples"]]
            fitting = record.kind.startswith("function_fit_")
            predicted = [row[0] for row in record.values] if fitting else None
            residual = [row[1] for row in record.values] if fitting else None
            source = metadata["source_snapshot"]
            self.renderSamples(samples, record.unit, predicted, residual, wrapped=source["kind"] == "angular_position", title="Last disk-saved result" if previous else "Latest applied result")
            summary = metadata["summary"]
            if fitting:
                self.showFormula(metadata["spec"]["expression"],
                                 tuple((name, f"{value:.6g}") for name, value in summary["parameter_values"]), fitted=True)
                self.conversionActions.setVisible(not self.history.active and any(item.get("error") for item in summary.get("result_formulas", [])))
                self.resultLabel.setText(f"{'Last disk-saved fit (snapshot)' if previous else 'Latest applied fit'} · {record.status} · {len(samples)} samples\n" + explain_fit(metadata, record.unit))
                details = (f"{summary['status']}: {summary['message']}\n"
                           + f"RMSE: {summary['rmse']:.8g} {record.unit}; evaluations: {summary['evaluations']}\n"
                           + "Parameters: " + ", ".join(f"{name}={value:.8g}" for name, value in summary["parameter_values"])
                           + "\nRecorded formula: " + metadata["spec"]["expression"]
                           + "\nConvergence does not validate the physical model; residuals are not measurement uncertainty.")
                for item in summary.get("result_formulas", []):
                    details += f"\nUser result {item['name']} = {item['formula']}: " + (str(item["value"]) if item["error"] is None else item["error"])
            else:
                self.modelLabel.setText(f"Displayed crossing settings: {metadata['spec']}")
                self.meaningLabel.setText("Recorded same-direction crossings; repeat intervals are not automatically a physical period.")
                mean, std = summary["mean_interval_s"], summary["sample_std_s"]
                meanText = f"{mean:.6g} s" if mean is not None else "unavailable"
                stdText = f"{std:.6g} s" if std is not None else "unavailable"
                self.resultLabel.setText(f"{'Disk-saved snapshot' if previous else 'Latest applied'} crossings ({record.status}) · {len(summary['events'])} events\nMean interval: {meanText} · sample std: {stdText}\n{summary['message']}")
                details = (f"{summary['measurement_status']}: {summary['message']}\n"
                           + f"Events: {len(summary['events'])}; intervals: {len(summary['intervals_s'])}; "
                           + f"mean: {mean if mean is not None else 'unavailable'} s; sample std: {std if std is not None else 'unavailable'} s\n"
                           + "Intervals (s): " + ", ".join(f"{value:.6g}" for value in summary["intervals_s"])
                           + "\nRecorded crossing settings: " + str(metadata["spec"]))
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
            self.summary.setPlainText(f"{'Disk-saved snapshot' if previous else 'Latest applied'} result: {record.status} — {source['kind']} [{record.unit}]\n"
                                     + f"Samples: {len(samples)}; source frames {metadata['interval']}; t=0 at interval start\n"
                                     + timing_message
                                     + details)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            self.signalPlot.clear()
            self.residualPlot.clear()
            self._previewRange = self._valueRange = None
            self.summary.setPlainText(f"Saved result is read-only; metadata cannot be displayed: {error}")
            self.resultLabel.setText(self.summary.toPlainText())
            self.modelLabel.clear()
            self.meaningLabel.clear()
