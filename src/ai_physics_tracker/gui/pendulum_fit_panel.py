"""GUI层：同一FitOptions的普通/高级编辑与原始角度、残差显示。"""

from dataclasses import asdict
import json
from math import degrees

import pyqtgraph as pg
from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from ai_physics_tracker.application.pendulum_fit import FitOptions, HIGH_PRECISION
from ai_physics_tracker.domain.pendulum_fit import FitSettings
from ai_physics_tracker.domain.pendulum_ode import M0, M1, InitialCondition, IntegrationSettings


class PendulumFitPanel(QWidget):
    frameRequested = Signal(int)
    settingsChanged = Signal()
    timingRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.payload = None
        self.payload_valid = False
        self._startIsDefault = True
        self.statusLabel = QLabel("No ODE fit yet", self)
        self.statusLabel.setWordWrap(True)
        self.timingHint = QLabel(self); self.timingHint.setWordWrap(True)
        self.timingButton = QPushButton("Use approximate timing…", self)
        self.timingButton.clicked.connect(self.timingRequested)
        self.timingHint.hide(); self.timingButton.hide()
        self.progressBar = QProgressBar(self); self.progressBar.setRange(0, 0); self.progressBar.hide()
        self.progressLabel = QLabel(self); self.progressLabel.hide()
        self.model = QComboBox(self)
        self.model.addItems(["Compare M0 + M1", "M0: linear damping"])
        self.precision = QComboBox(self)
        self.precision.addItems(["High precision: rtol 2e-10 / atol 2e-12", "Historical: rtol 2e-7 / atol 2e-9", "Custom (Advanced)"])
        self.icMode = QComboBox(self)
        self.icMode.addItems(["Held at rest before release", "Explicit fixed initial condition"])
        self.restConfirmed = QCheckBox("I confirm the pendulum was held at rest before release", self)
        self.theta0 = QLineEdit(self)
        self.theta0.setPlaceholderText("θ at release, rad (signed from vertical)")
        self.omega0 = QLineEdit(self)
        self.omega0.setPlaceholderText("ω at release, rad/s (0 if held at rest)")
        self.startFrame, self.endFrame = QSpinBox(self), QSpinBox(self)
        self.releaseAngleButton = QPushButton("Fill θ₀ from measured release frame", self)
        self.runButton, self.cancelButton = QPushButton("Run fit", self), QPushButton("Cancel", self)
        self.cancelButton.setEnabled(False)
        self.advancedButton = QPushButton("Advanced settings ▸", self)
        self.advancedButton.setCheckable(True)
        self.defaultsButton = QPushButton("Restore profile defaults", self)
        normal = QFormLayout()
        normal.addRow("Model", self.model)
        normal.addRow("DOP853 precision", self.precision)
        normal.addRow("Initial condition at release t=0", self.icMode)
        normal.addRow(self.restConfirmed)
        icRow = QHBoxLayout(); icRow.addWidget(self.theta0); icRow.addWidget(self.omega0)
        normal.addRow("Explicit θ₀ (rad) / ω₀ (rad/s)", icRow)
        self.icLabel = normal.labelForField(icRow)
        normal.addRow(self.releaseAngleButton)
        interval = QHBoxLayout()
        for title, widget in (("First source frame", self.startFrame), ("Last source frame", self.endFrame)):
            interval.addWidget(QLabel(title, self)); interval.addWidget(widget)
        interval.addWidget(self.runButton); interval.addWidget(self.cancelButton)
        self.icHint = QLabel("Rest IC requires the five consecutive QC-valid frames immediately before release. Otherwise enter θ₀ and ω₀ explicitly. IC remains at release even when the fit starts later.", self)
        self.icHint.setWordWrap(True)
        self.precisionHint = QLabel(self); self.precisionHint.setWordWrap(True)
        self.advanced = QScrollArea(self)
        self.advanced.setWidgetResizable(True); self.advanced.setMaximumHeight(260)
        advancedPage = QWidget(self.advanced); advancedLayout = QVBoxLayout(advancedPage)
        advancedTabs = QTabWidget(advancedPage)
        self.commonFields = {}
        commonPage = QWidget(advancedTabs); commonForm = QFormLayout(commonPage)
        for key, title in (
            ("maximum_samples", "Maximum valid samples"), ("f_scale_rad", "Robust loss scale (rad)"),
            ("rtol", "DOP853 rtol"), ("atol", "DOP853 atol"),
            ("max_step_s", "Maximum step (s), blank = unlimited"), ("first_step_s", "First step (s), blank = automatic"),
        ):
            field = QLineEdit(commonPage); self.commonFields[key] = field; commonForm.addRow(title, field)
        self.loss = QComboBox(commonPage); self.loss.addItems(["soft_l1", "linear"])
        commonForm.addRow("Loss", self.loss); advancedTabs.addTab(commonPage, "Objective / solver")
        self.modelFields = {}
        for model, title in ((M0, "M0"), (M1, "M1")):
            page = QWidget(advancedTabs); form = QFormLayout(page); fields = {}
            for key, label in (
                ("alpha1_bounds", "α₁* bounds (s⁻¹): low, high"), ("alpha2_bounds", "α₂* bounds (rad⁻¹): low, high"),
                ("omega2_bounds", "q bounds (s⁻²), blank = [0.20, 1.60] g/L"),
                ("max_nfev", "Maximum evaluations per start"), ("ftol", "ftol"), ("xtol", "xtol"), ("gtol", "gtol"),
                ("starts", "Starts: one vector per line; blank = deterministic defaults"),
            ):
                field = QTextEdit(page) if key == "starts" else QLineEdit(page)
                if key == "starts":
                    field.setMaximumHeight(65)
                    field.setPlaceholderText("α₁*, q" if model == M0 else "α₁*, α₂*, q")
                fields[key] = field; form.addRow(label, field)
            if model == M0:
                fields["alpha2_bounds"].setEnabled(False)
            self.modelFields[model] = fields; advancedTabs.addTab(page, title)
        advancedLayout.addWidget(advancedTabs); advancedLayout.addWidget(self.defaultsButton)
        self.advanced.setWidget(advancedPage); self.advanced.hide()
        self.advancedButton.toggled.connect(self._toggleAdvanced)
        self.defaultsButton.clicked.connect(self.resetDefaults)
        self.tabs = QTabWidget(self); self.plots = {}; self.curves = {}; self.chartMessages = {}
        for key, title, ylabel in (("overlay", "Angle overlay", "θ"), ("residual", "Raw residual (prediction − observation)", "Residual")):
            plot = pg.PlotWidget(enableMenu=False)
            plot.setLabel("bottom", "Time from release", units="s"); plot.setLabel("left", ylabel, units="rad")
            plot.showGrid(x=True, y=True, alpha=.2); plot.addLegend()
            plot.setMinimumHeight(240)
            for axis in ("left", "bottom"):
                plot.getAxis(axis).enableAutoSIPrefix(False)
            self.plots[key] = plot
            for model, name, color in ((M0, "M0", "#00b8e4"), (M1, "M1", "#e69f00")):
                item = plot.plot(pen=pg.mkPen(color, width=2.5, style=Qt.PenStyle.DashLine if model == M1 else Qt.PenStyle.SolidLine) if key == "overlay" else None, name=name,
                                 symbol=("t" if model == M1 else "o") if key == "residual" else None, symbolSize=6, symbolBrush=color, symbolPen=None)
                item.sigPointsClicked.connect(self._pointClicked); self.curves[key, model] = item
            page = QWidget(self.tabs); pageLayout = QVBoxLayout(page)
            message = QLabel("No fit yet — choose fixed IC and Run fit", page); message.setWordWrap(True)
            pageLayout.addWidget(message); pageLayout.addWidget(plot, 1)
            self.chartMessages[key] = message; plot.hide()
            self.tabs.addTab(page, title)
        self.differencePlot = pg.PlotWidget(enableMenu=False)
        self.differencePlot.setMinimumHeight(240)
        self.differencePlot.setLabel("bottom", "Time from release", units="s")
        self.differencePlot.setLabel("left", "M1 − M0 prediction", units="deg")
        self.differencePlot.showGrid(x=True, y=True, alpha=.2)
        self.differenceCurve = self.differencePlot.plot(pen=pg.mkPen("#e69f00", width=2))
        self.differencePlot.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#888888")))
        differencePage = QWidget(self.tabs); differenceLayout = QVBoxLayout(differencePage)
        self.differenceHint = QLabel("Run Compare M0 + M1 to see their prediction difference", differencePage)
        self.differenceHint.setWordWrap(True)
        differenceLayout.addWidget(self.differenceHint); differenceLayout.addWidget(self.differencePlot, 1)
        self.differencePlot.hide(); self.tabs.addTab(differencePage, "M1 − M0 difference")
        self.observations = self.plots["overlay"].plot(pen=None, symbol="o", symbolSize=3, symbolPen=None,
            symbolBrush=(180, 180, 180, 100), name="QC-valid raw θ")
        self.observations.setZValue(-1)
        self.observations.sigPointsClicked.connect(self._pointClicked)
        self.details = QTextEdit(self); self.details.setReadOnly(True)
        self.diagnostics = QTabWidget(self)
        self.parameterTable = self._table(["Quantity", "Unit", "M0", "M1"])
        self.rmsePlot = pg.PlotWidget(enableMenu=False)
        self.rmsePlot.setLabel("left", "Full RMSE", units="rad")
        self.rmsePlot.getAxis("bottom").setTicks([[(0, "M0"), (1, "M1")]])
        parameterPage = QWidget(self); parameterLayout = QVBoxLayout(parameterPage)
        parameterLayout.addWidget(self.parameterTable, 1); parameterLayout.addWidget(self.rmsePlot, 1)
        self.diagnostics.addTab(parameterPage, "Parameters / RMSE")
        self.startPlot = pg.PlotWidget(enableMenu=False)
        self.startPlot.setLabel("left", "Robust objective cost", units="rad²")
        self.startPlot.setLabel("bottom", "Start number (star = selected)"); self.startPlot.addLegend()
        self.startTable = self._table(["Model", "Start", "Cost (rad²)", "Evaluations", "Outcome"])
        startPage = QWidget(self); startLayout = QVBoxLayout(startPage)
        startLayout.addWidget(self.startPlot, 1); startLayout.addWidget(self.startTable, 1)
        self.diagnostics.addTab(startPage, "Multistart")
        self.diagnostics.addTab(self.details, "Technical details")
        self.tabs.addTab(self.diagnostics, "Parameters / start diagnostics")
        self.summaryLabel = QLabel(self); self.summaryLabel.setWordWrap(True)
        self.frameLabel = QLabel("Click an observation or residual to inspect its source frame", self)
        self.frameLabel.setWordWrap(True)
        layout = QVBoxLayout(self); layout.addWidget(self.statusLabel)
        timingRow = QHBoxLayout(); timingRow.addWidget(self.timingHint, 1); timingRow.addWidget(self.timingButton)
        layout.addLayout(timingRow)
        settingsPage = QWidget(self); settingsLayout = QVBoxLayout(settingsPage)
        settingsLayout.addLayout(normal); settingsLayout.addWidget(self.icHint); settingsLayout.addWidget(self.precisionHint)
        settingsLayout.addWidget(self.advancedButton); settingsLayout.addWidget(self.advanced)
        self.settingsScroll = QScrollArea(self); self.settingsScroll.setWidgetResizable(True)
        self.settingsScroll.setMaximumHeight(240); self.settingsScroll.setWidget(settingsPage)
        layout.addWidget(self.settingsScroll); layout.addLayout(interval)
        layout.addWidget(self.progressLabel); layout.addWidget(self.progressBar)
        layout.addWidget(self.summaryLabel); layout.addWidget(self.tabs, 1); layout.addWidget(self.frameLabel)
        note = QLabel("Fits use adopted raw tip θ + fixed pivot; SG and auxiliary landmarks do not gate fitting. Lower RMSE alone does not prove quadratic damping or unique parameters.", self)
        note.setWordWrap(True); layout.addWidget(note)
        self.resetDefaults()
        self.controls = [self.model, self.precision, self.icMode, self.restConfirmed, self.theta0, self.omega0,
            self.startFrame, self.endFrame, self.loss, self.defaultsButton, self.releaseAngleButton, *self.commonFields.values(),
            *(w for fields in self.modelFields.values() for w in fields.values())]
        for widget in self.controls:
            if isinstance(widget, QComboBox): widget.currentIndexChanged.connect(self._changed)
            elif isinstance(widget, QCheckBox): widget.toggled.connect(self._changed)
            elif isinstance(widget, QSpinBox): widget.valueChanged.connect(self._changed)
            else: widget.textChanged.connect(self._changed) if hasattr(widget, "textChanged") else None
        self.precision.currentIndexChanged.connect(self._precisionChanged)
        for key in ("rtol", "atol"):
            self.commonFields[key].textChanged.connect(self._solverEdited)
        self.startFrame.valueChanged.connect(lambda _v: setattr(self, "_startIsDefault", False))
        self._changed()

    def _table(self, headers):
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def setTimingRequirement(self, text, action="", enabled=False):
        self.timingHint.setText(text); self.timingHint.setVisible(bool(text))
        self.timingButton.setText(action); self.timingButton.setVisible(bool(action))
        self.timingButton.setEnabled(enabled)

    def _toggleAdvanced(self, enabled):
        self.advanced.setVisible(enabled)
        self.advancedButton.setText("Advanced settings ▾" if enabled else "Advanced settings ▸")

    def _changed(self, *_args):
        explicit = self.icMode.currentIndex() == 1
        self.theta0.setVisible(explicit); self.omega0.setVisible(explicit); self.icLabel.setVisible(explicit)
        self.releaseAngleButton.setVisible(explicit)
        self.restConfirmed.setVisible(not explicit)
        self.precisionHint.setText("Historical precision has known M1 sensitivity (ADR-0020). No automatic precision retry."
            if self.precision.currentIndex() == 1 else "High precision is an explicit student setting; the frozen historical profile is unchanged."
            if self.precision.currentIndex() == 0 else "Custom precision uses the DOP853 values in Advanced settings.")
        self.settingsChanged.emit()

    def _precisionChanged(self, index):
        if index < 2:
            setting = HIGH_PRECISION if index == 0 else IntegrationSettings()
            for key in ("rtol", "atol"):
                field = self.commonFields[key]
                blocker = QSignalBlocker(field)
                field.setText(str(getattr(setting, key)))
                del blocker
            self._changed()

    def _solverEdited(self):
        if self.precision.currentIndex() < 2:
            setting = HIGH_PRECISION if self.precision.currentIndex() == 0 else IntegrationSettings()
            try:
                matches = all(float(self.commonFields[key].text()) == getattr(setting, key) for key in ("rtol", "atol"))
            except ValueError:
                matches = False
            if not matches:
                self.precision.setCurrentIndex(2)

    def resetDefaults(self):
        self.setAdvanced(FitOptions(self.endFrame.value()))
        self.precision.setCurrentIndex(0)
        self._precisionChanged(0)

    def setAdvanced(self, options):
        self.loss.setCurrentText(options.loss)
        values = {"maximum_samples": options.maximum_samples, "f_scale_rad": options.f_scale_rad,
                  **asdict(options.integration)}
        for key, widget in self.commonFields.items():
            widget.setText("" if values[key] is None else str(values[key]))
        for model, settings in ((M0, options.m0_settings), (M1, options.m1_settings)):
            for key, value in asdict(settings).items():
                widget = self.modelFields[model][key]
                if key == "starts":
                    widget.setPlainText("" if value is None else "\n".join(", ".join(map(str, vector)) for vector in value))
                else:
                    widget.setText("" if value is None else ", ".join(map(str, value)) if isinstance(value, tuple) else str(value))

    def options(self) -> FitOptions:
        integration = IntegrationSettings(**{key: None if not self.commonFields[key].text().strip()
            and key.endswith("step_s") else float(self.commonFields[key].text())
            for key in ("rtol", "atol", "max_step_s", "first_step_s")})
        settings = []
        for model in (M0, M1):
            values = {}
            for key, widget in self.modelFields[model].items():
                text = widget.toPlainText().strip() if key == "starts" else widget.text().strip()
                if key == "starts":
                    values[key] = None if not text else tuple(tuple(float(v.strip()) for v in line.split(",")) for line in text.splitlines())
                elif key.endswith("bounds"):
                    values[key] = None if key == "omega2_bounds" and not text else tuple(float(v.strip()) for v in text.split(","))
                else:
                    values[key] = int(text) if key == "max_nfev" else float(text)
            settings.append(FitSettings(**values))
        explicit = self.icMode.currentIndex() == 1
        ic = InitialCondition(float(self.theta0.text()), float(self.omega0.text()), "explicit") if explicit else None
        return FitOptions(self.endFrame.value(), models=(M0,) if self.model.currentIndex() else (M0, M1),
            rest_confirmed=self.restConfirmed.isChecked() if not explicit else False, explicit_ic=ic,
            integration=integration, maximum_samples=int(self.commonFields["maximum_samples"].text()),
            loss=self.loss.currentText(), f_scale_rad=float(self.commonFields["f_scale_rad"].text()),
            m0_settings=settings[0], m1_settings=settings[1], start_frame_index=None if self._startIsDefault and self.startFrame.value() == self.startFrame.minimum() else self.startFrame.value())

    def restoreOptions(self, options):
        widgets = self.controls
        for widget in widgets: widget.blockSignals(True)
        try:
            self.model.setCurrentIndex(1 if options.models == (M0,) else 0)
            self.icMode.setCurrentIndex(1 if options.explicit_ic is not None else 0)
            self.restConfirmed.setChecked(options.rest_confirmed)
            self.theta0.setText("" if options.explicit_ic is None else str(options.explicit_ic.theta0_rad))
            self.omega0.setText("" if options.explicit_ic is None else str(options.explicit_ic.omega0_rad_s))
            self._startIsDefault = options.start_frame_index is None
            self.endFrame.setValue(options.end_frame_index)
            self.startFrame.setValue(self.startFrame.minimum() if options.start_frame_index is None else options.start_frame_index)
            self.setAdvanced(options)
            self.precision.setCurrentIndex(0 if options.integration == HIGH_PRECISION else
                1 if options.integration == IntegrationSettings() else 2)
        finally:
            for widget in widgets: widget.blockSignals(False)
        self._changed()

    def setBusy(self, busy):
        for widget in self.controls: widget.setEnabled(not busy)
        self.modelFields[M0]["alpha2_bounds"].setEnabled(False)
        self.runButton.setEnabled(not busy); self.cancelButton.setEnabled(busy)
        self.progressBar.setVisible(busy); self.progressLabel.setVisible(busy)
        if busy: self.progressLabel.setText("Working in background… elapsed 0 s; duration varies by optimizer start")

    def clearData(self):
        self.payload = None; self.payload_valid = False
        self.observations.clear()
        for curve in self.curves.values(): curve.clear()
        for key, plot in self.plots.items():
            plot.hide(); self.chartMessages[key].setText("No fit yet — choose fixed IC and Run fit"); self.chartMessages[key].show()
        self.summaryLabel.clear(); self.details.clear()
        self.differenceCurve.clear(); self.differencePlot.hide()
        self.differenceHint.setText("Run Compare M0 + M1 to see their prediction difference")
        self.parameterTable.setRowCount(0); self.startTable.setRowCount(0)
        self.rmsePlot.clear(); self.startPlot.clear()
        self.frameLabel.setText("Click an observation or residual to inspect its source frame")
        self.statusLabel.setText("No ODE fit yet")

    def setPayload(self, payload, valid, reason=None):
        self.payload, self.payload_valid = payload, valid
        self.resultStatusText = "Current ODE fit" if valid else "STALE historical fit — " + (reason or "inputs changed")
        self.statusLabel.setText(self.resultStatusText)
        rows = payload["rows"]
        observed = [r for r in rows if r["is_qc_valid"] and r["theta_rad"] is not None and
            r["frame_index"] >= payload["config"]["models"][M0]["objective"]["interval"]["start_frame_index"] and
            r["frame_index"] <= payload["config"]["options"]["end_frame_index"]]
        self.observations.setData([r["time_release_relative_s"] for r in observed],
            [r["theta_rad"] for r in observed], data=[r["frame_index"] for r in observed])
        eligibility = payload["eligibility"]
        ic = payload["config"]["resolved_ic"]
        summaries = [f"Input: {eligibility['valid_count']} valid angles (needs {eligibility['required_count']}); "
            f"valid time span {eligibility['valid_span_s']:.4g} s (needs {eligibility['required_span_s']:.4g} s). "
            f"Fixed IC θ₀={ic['theta0_rad']:.6g} rad, ω₀={ic['omega0_rad_s']:.6g} rad/s at release."]
        detail = ["Fixed IC at release t=0: " + json.dumps(ic)]
        for model, prefix, label in ((M0, "m0", "M0"), (M1, "m1", "M1")):
            fit = payload["fits"].get(model)
            for key, column in (("overlay", prefix+"_theta_rad"), ("residual", prefix+"_residual_rad")):
                selected = [r for r in rows if r[column] is not None and (key == "overlay" or r["is_qc_valid"])]
                self.curves[key, model].setData([r["time_release_relative_s"] for r in selected],
                    [r[column] for r in selected], data=[r["frame_index"] for r in selected],
                    connect="all" if key == "overlay" else "finite")
            if fit is None: continue
            trajectory = fit["trajectory"]; rmse = trajectory["rmse_rad"] if trajectory else None
            parameters = fit["parameters"]
            text = label + ": " + fit["status"]
            if rmse is not None: text += f" · full RMSE {rmse:.6g} rad ({degrees(rmse):.6g}°)"
            if parameters:
                text += f" · α₁*={parameters['alpha1_s_inv']:.6g} s⁻¹"
                if model == M1: text += f" · α₂*={parameters['alpha2_rad_inv']:.6g} rad⁻¹"
                text += f" · q={parameters['omega2_s_inv2']:.6g} s⁻²"
            if fit["reason"]: text += " · " + fit["reason"]
            if fit["warnings"]: text += " · " + ", ".join(fit["warnings"])
            summaries.append(text)
            detail.append(label + "\n" + json.dumps({k: v for k, v in fit.items() if k != "trajectory"}, indent=2))
        comparison = payload.get("comparison")
        if comparison:
            improvement = comparison["rmse_improvement_percent"]
            summaries.append(f"M1 full-RMSE improvement: {improvement:.4g}%" if improvement is not None else
                "Comparison: " + (comparison["reason"] or comparison["status"]))
        self.summaryLabel.setText("\n".join(summaries)); self.details.setPlainText("\n\n".join(detail))
        for key, plot in self.plots.items():
            available = any(self.curves[key, model].getData()[0] is not None and
                len(self.curves[key, model].getData()[0]) > 0 for model in (M0, M1))
            if key == "overlay": available = available or bool(observed)
            plot.setVisible(available); self.chartMessages[key].setVisible(not available)
            self.chartMessages[key].setText("No " + key + " available: " + "; ".join(
                f["reason"] or f["status"] for f in payload["fits"].values()))
            plot.enableAutoRange(axis="y")
            if observed:
                plot.setXRange(observed[0]["time_release_relative_s"], observed[-1]["time_release_relative_s"], padding=.02)

        difference = [r for r in rows if r["m0_theta_rad"] is not None and r["m1_theta_rad"] is not None]
        self.differenceCurve.setData([r["time_release_relative_s"] for r in difference],
            [degrees(r["m1_theta_rad"]-r["m0_theta_rad"]) for r in difference])
        self.differencePlot.setVisible(bool(difference))
        self.differenceHint.setText("Prediction difference in degrees; zero means overlapping models. This is not residual error."
            if difference else "Prediction difference unavailable — both M0 and M1 need a fitted trajectory.")
        if difference:
            self.differencePlot.enableAutoRange(axis="y")
            self.differencePlot.setXRange(difference[0]["time_release_relative_s"], difference[-1]["time_release_relative_s"], padding=.02)
        self._showDiagnostics(payload)

    def _showDiagnostics(self, payload):
        models = [payload["fits"].get(m) for m in (M0, M1)]
        values = [("Status", "", [f["status"] if f else "Not run" for f in models])]
        for label, unit, key in (("α₁*", "s⁻¹", "alpha1_s_inv"), ("α₂*", "rad⁻¹", "alpha2_rad_inv"), ("q", "s⁻²", "omega2_s_inv2")):
            values.append((label, unit, [f"{f['parameters'][key]:.6g}" if f and f["parameters"] else "—" for f in models]))
        errors = [f["trajectory"]["rmse_rad"] if f and f["trajectory"] else None for f in models]
        values.append(("Full RMSE", "rad", [f"{v:.6g}" if v is not None else "—" for v in errors]))
        self.parameterTable.setRowCount(len(values))
        for row, (label, unit, cells) in enumerate(values):
            for column, value in enumerate([label, unit, *cells]):
                self.parameterTable.setItem(row, column, QTableWidgetItem(value))
        self.rmsePlot.clear(); self.startPlot.clear(); self.startTable.setRowCount(0)
        for index, (fit, label, color) in enumerate(zip(models, ("M0", "M1"), ("#00b8e4", "#e69f00"))):
            if fit is None: continue
            if errors[index] is not None:
                self.rmsePlot.addItem(pg.BarGraphItem(x=[index], height=[errors[index]], width=.5, brush=color))
            for start_index, start in enumerate(fit["starts"]):
                selected = start_index == fit["selected_start_index"]
                cost = start["cost_rad2"]
                if cost is not None:
                    self.startPlot.plot([start_index+1], [cost], pen=None, symbol="star" if selected else "o",
                        symbolBrush=color, symbolSize=13 if selected else 7, name=label if start_index == 0 else None)
                row = self.startTable.rowCount(); self.startTable.insertRow(row)
                outcome = ("Selected · " if selected else "") + start["status"]
                if any(start["at_bound"]): outcome += " · at bound"
                for column, value in enumerate((label, str(start_index+1), f"{cost:.6g}" if cost is not None else "—", str(start["nfev"]), outcome)):
                    item = QTableWidgetItem(value); item.setToolTip(start["message"])
                    self.startTable.setItem(row, column, item)
        self.rmsePlot.setXRange(-.6, 1.6, padding=0)
        self.rmsePlot.enableAutoRange(axis="y")
        self.startPlot.enableAutoRange()

    def _pointClicked(self, _item, points, _event=None):
        if points: self.frameRequested.emit(int(points[0].data()))

    def presentFrame(self, frame_index):
        if self.payload is None or frame_index is None: return
        row = next((r for r in self.payload["rows"] if r["frame_index"] == frame_index), None)
        if row:
            self.frameLabel.setText(f"Source frame {frame_index} · t={row['time_release_relative_s']:.6g} s · " +
                ("QC valid" if row["is_qc_valid"] else "QC excluded: " + ", ".join(row["qc_reasons"])))
