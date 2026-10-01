"""GUI层：raw等价族与条件objective曲面；数值由Qt-free应用层提供。"""

from dataclasses import astuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel,
    QProgressBar, QPushButton, QSlider, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ai_physics_tracker.application.pendulum_exploration import teaching_bounds
from ai_physics_tracker.domain.pendulum_identifiability import (
    feasible_lambda_range, illustrative_raw_reference,
)

COLORS = ("#00bcd4", "#ff9800")


def read_only_table(headers, parent):
    table = QTableWidget(0, len(headers), parent)
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return table


def fill_table(table, rows):
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value)); item.setToolTip(str(value))
            table.setItem(row, col, item)
    table.resizeRowsToContents()


class ParameterEquivalencePanel(QWidget):
    buildRequested = Signal()
    cancelRequested = Signal()
    previewRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.status = QLabel("Run or open a current ODE fit first", self); self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.buildButton = QPushButton("Build conditional surface", self)
        self.cancelButton = QPushButton("Cancel", self); self.cancelButton.setEnabled(False)
        buttons.addWidget(self.buildButton); buttons.addWidget(self.cancelButton)
        layout.addLayout(buttons)
        self.progress = QProgressBar(self); self.progress.setRange(0, 0); self.progress.hide()
        layout.addWidget(self.progress)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("λ", self))
        self.lambdaValue = QDoubleSpinBox(self); self.lambdaValue.setDecimals(4); self.lambdaValue.setSingleStep(.01)
        self.slider = QSlider(Qt.Horizontal, self); self.slider.setRange(0, 1000)
        self.control = QCheckBox("Non-equivalent control: q +5%", self)
        controls.addWidget(self.lambdaValue); controls.addWidget(self.slider, 1); controls.addWidget(self.control)
        layout.addLayout(controls)
        self._range = (1., 1.12); self._syncing = False
        self._surfaceBounds = None
        self._surfaceMessage = "Surface not built — use Build conditional surface."
        self.slider.valueChanged.connect(self._sliderChanged)
        self.lambdaValue.valueChanged.connect(self._valueChanged)
        self.control.toggled.connect(self.previewRequested)
        self.buildButton.clicked.connect(self.buildRequested); self.cancelButton.clicked.connect(self.cancelRequested)
        self.rawTable = read_only_table(["Parameter / unit", "Reference A", "Displayed B"], self)
        self.rawTable.setMaximumHeight(220); layout.addWidget(self.rawTable)
        self.tabs = QTabWidget(self); layout.addWidget(self.tabs, 1)
        self.plots = {}
        for key, title, x, y, unit in (
            ("overlay", "Independent raw forwards", "Time from release (s)", "θ", "rad"),
            ("difference", "B − A", "Time from release (s)", "Difference", "rad"),
            ("surface", "Conditional objective surface", "Raw αa (dimensionless)", "Raw ω₀²", "s^-2"),
        ):
            plot = pg.PlotWidget(enableMenu=False); plot.setMinimumHeight(260)
            plot.setLabel("bottom", x); plot.setLabel("left", y, units=unit)
            plot.showGrid(x=True, y=True, alpha=.2)
            self.plots[key] = plot; self.tabs.addTab(plot, title)
        self.plots["overlay"].addLegend()
        self.referenceCurve = self.plots["overlay"].plot(name="Reference A", pen=pg.mkPen(COLORS[0], width=2.5))
        self.otherCurve = self.plots["overlay"].plot(name="Displayed B", pen=pg.mkPen(COLORS[1], width=2.5, style=Qt.DashLine))
        self.differenceCurve = self.plots["difference"].plot(pen=pg.mkPen(COLORS[1], width=2))
        self.plots["difference"].addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#888888")))
        self.image = pg.ImageItem(axisOrder="row-major"); self.plots["surface"].addItem(self.image)
        self.colorBar = pg.ColorBarItem(values=(0, 1), colorMap=pg.colormap.get("viridis"),
            interactive=False, label="log10(objective / fitted)")
        self.colorBar.setImageItem(self.image, insert_in=self.plots["surface"].plotItem)
        self.locus = self.plots["surface"].plot(pen=pg.mkPen("w", width=1.5))
        self.cursor = self.plots["surface"].plot(pen=None, symbol="star", symbolSize=16, symbolBrush=COLORS[1])
        self.nodeLabel = QLabel(self); self.nodeLabel.setWordWrap(True); layout.addWidget(self.nodeLabel)
        hint = QLabel("Illustrative raw parameters, not measured values. λ preserves three starred parameters. "
            "The surface fixes starred damping, IC, samples, weights and loss; it scans q without refitting. "
            "It is a conditional slice, not a confidence interval or profile likelihood. "
            "The teaching raw αa range is 0–0.12; forward precision is rtol 1e−10 / atol 1e−12. "
            "Forward display runs from release to the saved end (at most 25 s); the objective uses the complete saved fit interval and its precision.", self)
        hint.setWordWrap(True); layout.addWidget(hint)
        self.configure(None)

    def _sliderChanged(self, value):
        if self._syncing: return
        lo, hi = self._range
        self.lambdaValue.setValue(lo+(hi-lo)*value/1000)

    def _valueChanged(self, value):
        if self._syncing: return
        lo, hi = self._range
        self._syncing = True; self.slider.setValue(round(1000*(value-lo)/(hi-lo)) if hi > lo else 0)
        self._syncing = False; self.previewRequested.emit()

    def configure(self, source):
        ready = source is not None and source.parameters is not None
        for widget in (self.slider, self.lambdaValue, self.control): widget.setEnabled(ready)
        if not ready: return
        interval = feasible_lambda_range(illustrative_raw_reference(source.parameters), teaching_bounds(source.parameters))
        self._range = (interval.min_lambda, interval.max_lambda)
        self._syncing = True
        self.lambdaValue.setRange(*self._range); self.lambdaValue.setValue(1.); self.slider.setValue(0)
        self.control.blockSignals(True); self.control.setChecked(False); self.control.blockSignals(False)
        self._syncing = False

    def setBusy(self, busy, *, scanning=False):
        self.progress.setVisible(busy); self.cancelButton.setEnabled(busy); self.buildButton.setEnabled(not busy)
        for widget in (self.slider, self.lambdaValue, self.control):
            widget.setEnabled(not scanning and self.rawTable.rowCount() > 0)

    def clearData(self):
        self.rawTable.setRowCount(0)
        for curve in (self.referenceCurve, self.otherCurve, self.differenceCurve, self.locus, self.cursor): curve.clear()
        self.image.clear(); self.nodeLabel.clear(); self.configure(None)
        self._surfaceBounds = None; self._surfaceMessage = "Surface not built — use Build conditional surface."

    def setSurface(self, surface):
        values = np.array([[np.nan if v is None else v for v in row]
                           for row in surface.log10_objective_ratio_grid], dtype=float).T
        finite = values[np.isfinite(values)]
        if not finite.size:
            self.image.clear(); self._surfaceBounds = None
            self._surfaceMessage = "Surface ratio unavailable: zero fitted objective or failed nodes."
            self.nodeLabel.setText(self._surfaceMessage)
            return
        a, q = surface.alpha_a_values, surface.omega0_sq_s_inv2_values
        da, dq = a[1]-a[0], q[1]-q[0]
        self.image.setImage(values, autoLevels=False)
        self.image.setRect(QRectF(a[0]-da/2, q[0]-dq/2, a[-1]-a[0]+da, q[-1]-q[0]+dq))
        self.colorBar.setLevels((float(finite.min()), float(finite.max())+1e-12))
        self.plots["surface"].setXRange(a[0], a[-1], padding=.02)
        self.plots["surface"].setYRange(q[0], q[-1], padding=.02)
        self._surfaceBounds = (a[0], a[-1], q[0], q[-1])
        fitted = surface.fitted_mean_objective_rad2
        self._surfaceMessage = f"Surface colors: interpolated conditional slice; fitted mean objective {fitted:.6g} rad²."
        self.nodeLabel.setText(self._surfaceMessage)

    def setPreview(self, source, preview):
        a, b = preview.state.reference_raw, preview.displayed_raw
        pa, pb = preview.state.reference_lumped, preview.displayed_lumped
        rows = [(name, f"{left:.8g}", f"{right:.8g}") for name, left, right in zip(
            ("raw αa (dimensionless)", "raw α₁ (s⁻¹)", "raw α₂ (rad⁻¹)", "raw ω₀² (s⁻²)"), astuple(a), astuple(b))]
        rows += [(name, f"{left:.8g}", f"{right:.8g}") for name, left, right in (
            ("starred α₁* (s⁻¹)", pa.alpha1_s_inv, pb.alpha1_s_inv),
            ("starred α₂* (rad⁻¹)", pa.alpha2_rad_inv, pb.alpha2_rad_inv),
            ("starred q (s⁻²)", pa.omega2_s_inv2, pb.omega2_s_inv2))]
        fill_table(self.rawTable, rows)
        forward = preview.forwards
        if forward.raw_reference.status == forward.raw_transformed.status == "success":
            self.referenceCurve.setData(forward.time_s, forward.raw_reference.theta_rad)
            self.otherCurve.setData(forward.time_s, forward.raw_transformed.theta_rad)
            self.differenceCurve.setData(forward.time_s, np.asarray(forward.raw_transformed.theta_rad)-np.asarray(forward.raw_reference.theta_rad))
            for key in ("overlay", "difference"): self.plots[key].setXRange(forward.time_s[0], forward.time_s[-1], padding=.02)
        else:
            for curve in (self.referenceCurve, self.otherCurve, self.differenceCurve): curve.clear()
        self.cursor.setData([b.alpha_a], [b.omega0_sq_s_inv2])
        outside = False
        if self._surfaceBounds is not None:
            x0, x1, y0, y1 = self._surfaceBounds
            outside = not (x0 <= b.alpha_a <= x1 and y0 <= b.omega0_sq_s_inv2 <= y1)
            self.plots["surface"].setXRange(min(x0, b.alpha_a), max(x1, b.alpha_a), padding=.02)
            self.plots["surface"].setYRange(min(y0, b.omega0_sq_s_inv2), max(y1, b.omega0_sq_s_inv2), padding=.02)
        alpha = np.linspace(0, .12, 101)
        self.locus.setData(alpha, pa.omega2_s_inv2*(1+alpha))
        delta = forward.raw_overlap_max_abs_difference_rad
        meaning = "NON-EQUIVALENT q +5% control" if preview.non_equivalent_control else "Equivalent family"
        self.status.setText(f"{meaning} · λ={preview.state.lambda_scale:.4f} · source {source.model} / {str(source.result_id)[:8]} · "
            f"max |B−A|={delta:.3g} rad (tolerance {forward.tolerance_rad:g})" if delta is not None else f"Forward unavailable: {forward.reason}")
        node = preview.node
        ratio = f"unavailable ({node.reason})" if node.objective_ratio is None else f"{node.objective_ratio:.8g}"
        objective = f"{node.mean_objective_rad2:.8g} rad²" if node.mean_objective_rad2 is not None else f"unavailable ({node.reason})"
        self.nodeLabel.setText(f"Cursor direct ODE mean objective: {objective} · ratio to saved fit: {ratio}. "
            + self._surfaceMessage + (" Cursor outside raster; no color extrapolation." if outside else "") + " No damping refit.")
