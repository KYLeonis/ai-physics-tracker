"""GUI层：只读模型批判图；科学判断与来源核对由领域核心提供。"""

import pyqtgraph as pg
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget

from ai_physics_tracker.gui.pendulum_teaching_panel import COLORS, fill_table, read_only_table
from ai_physics_tracker.domain.pendulum_ode import M0, M1


def _metric_text(metric):
    return f"{metric.value:.6g} {metric.unit} (n={metric.count})" if metric.value is not None else f"Unavailable: {metric.reason} (n={metric.count})"


class ModelCriticismPanel(QWidget):
    refreshRequested = Signal()
    cancelRequested = Signal()
    frameRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        layout = QVBoxLayout(self)
        self.status = QLabel("Open a current ODE fit first", self); self.status.setWordWrap(True)
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        self.refreshButton = QPushButton("Refresh diagnostics", self)
        self.cancelButton = QPushButton("Cancel", self); self.cancelButton.setEnabled(False)
        self.models = QComboBox(self)
        controls.addWidget(self.refreshButton); controls.addWidget(self.cancelButton)
        controls.addWidget(QLabel("Display", self)); controls.addWidget(self.models)
        layout.addLayout(controls)
        self.refreshButton.clicked.connect(self.refreshRequested)
        self.cancelButton.clicked.connect(self.cancelRequested)
        self.models.currentIndexChanged.connect(self._render)
        self.progress = QProgressBar(self); self.progress.setRange(0, 0); self.progress.hide()
        layout.addWidget(self.progress)
        self.tabs = QTabWidget(self); layout.addWidget(self.tabs, 1)
        self.plots = {}; self.messages = {}
        for key, title, x, y, unit in (
            ("residual", "Raw residual", "Time from release (s)", "Prediction − observation", "rad"),
            ("phase", "Zero-crossing phase", "Observed crossing time (s)", "Predicted − observed time", "s"),
            ("physical", "Physical consistency", "q source", "q", "s^-2"),
        ):
            page = QWidget(self); page_layout = QVBoxLayout(page)
            message = QLabel(page); message.setWordWrap(True); page_layout.addWidget(message)
            plot = pg.PlotWidget(enableMenu=False); plot.setMinimumHeight(250)
            plot.setLabel("bottom", x); plot.setLabel("left", y, units=unit); plot.showGrid(x=True, y=True, alpha=.2)
            plot.addLegend(); page_layout.addWidget(plot, 1)
            self.plots[key] = plot; self.messages[key] = message
            self.tabs.addTab(page, title)
        rmse_page = QWidget(self); rmse_layout = QVBoxLayout(rmse_page)
        self.rmseMessage = QLabel(rmse_page); self.rmseMessage.setWordWrap(True); rmse_layout.addWidget(self.rmseMessage)
        graphs = QHBoxLayout(); rmse_layout.addLayout(graphs, 1)
        for key, title in (("time", "RMSE: first / all / last valid samples"), ("speed", "RMSE: observed |ω| strata (SG9/3)")):
            plot = pg.PlotWidget(enableMenu=False, title=title); plot.setMinimumHeight(250)
            plot.setLabel("left", "RMSE", units="rad"); plot.showGrid(y=True, alpha=.2); plot.addLegend()
            self.plots[key] = plot; graphs.addWidget(plot, 1)
        self.tabs.insertTab(1, rmse_page, "RMSE strata")
        self.physicalTable = read_only_table(["Evidence / unit", "M0", "M1"], self)
        self.tabs.widget(3).layout().addWidget(self.physicalTable, 1)
        self.frameLabel = QLabel("Click a raw residual point to inspect its source frame", self)
        layout.addWidget(self.frameLabel)
        hint = QLabel("Raw θ residuals do not require SG. Lower RMSE alone does not prove quadratic damping or unique parameters. "
            "Auxiliary evidence can be unavailable without hiding raw residuals. Diagnostics use the saved fit interval and inputs.", self)
        hint.setWordWrap(True); layout.addWidget(hint)

    def setBusy(self, busy):
        self.progress.setVisible(busy); self.cancelButton.setEnabled(busy); self.refreshButton.setEnabled(not busy)

    def clearData(self):
        self._source = None
        self.models.blockSignals(True); self.models.clear(); self.models.blockSignals(False)
        for plot in self.plots.values(): plot.clear()
        for label in self.messages.values(): label.clear()
        self.rmseMessage.clear(); self.physicalTable.setRowCount(0)
        self.frameLabel.setText("Click a raw residual point to inspect its source frame")

    def setSource(self, source):
        self._source = source
        previous = self.models.currentData()
        self.models.blockSignals(True); self.models.clear()
        result = source.criticism
        if result.comparison.status == "comparable": self.models.addItem("M0 + M1 (same inputs)", "both")
        for model in result.models: self.models.addItem(model.model, model.model)
        index = self.models.findData(previous)
        if index >= 0: self.models.setCurrentIndex(index)
        self.models.blockSignals(False)
        self._render()

    def _pointClicked(self, _item, points):
        if points:
            frame = points[0].data()
            self.frameLabel.setText(f"Source frame {frame} — residual uses adopted tip + fixed pivot")
            self.frameRequested.emit(frame)

    def _render(self, *_args):
        if self._source is None: return
        source = self._source; result = source.criticism
        comparison = result.comparison
        meaning = f"Same-input M1 RMSE improvement: {_metric_text(comparison.rmse_improvement_percent)}" if comparison.status == "comparable" else f"Comparison unavailable: {comparison.reason}; individual model diagnostics only"
        self.status.setText(f"Current saved fit {str(source.result_id)[:8]} · source frames {source.request.start_frame_index}–{source.request.end_frame_index} · {meaning}")
        selected = self.models.currentData()
        models = [model for model in result.models if selected in ("both", model.model)]
        for plot in self.plots.values(): plot.clear()
        residual_text = []; phase_text = []; strata_text = []
        for model in models:
            index = 0 if model.model == M0 else 1
            color = COLORS[index]; symbol = "o" if index == 0 else "t"
            residual = model.residuals
            points = residual.points
            item = pg.ScatterPlotItem(x=[p.time_s for p in points], y=[p.residual_rad for p in points],
                data=[p.frame_index for p in points], pen=pg.mkPen(color), brush=pg.mkBrush(color), size=6, symbol=symbol, name=model.model.upper())
            item.sigClicked.connect(self._pointClicked); self.plots["residual"].addItem(item)
            residual_text.append(f"{model.model.upper()}: full {_metric_text(residual.rmse_rad)}")
            metrics = (residual.early_rmse_rad, residual.rmse_rad, residual.late_rmse_rad)
            self._bars("time", metrics, index, color, model.model.upper())
            speed = residual.speed
            if speed.quantiles_rad_s is not None:
                strata_text.append(f"{model.model.upper()} |ω| cuts: {speed.quantiles_rad_s[0]:.5g}, {speed.quantiles_rad_s[1]:.5g} rad/s; counts " + "/".join(str(s.count) for s in speed.strata))
            else: strata_text.append(f"{model.model.upper()} speed strata unavailable: {speed.reason}")
            self._bars("speed", tuple(s.rmse_rad for s in speed.strata), index, color, model.model.upper())
            phase = model.phase
            for direction, marker in (("upward", "t1"), ("downward", "t")):
                matched = [p for p in phase.matched if p.direction == direction]
                self.plots["phase"].plot([p.observed_time_s for p in matched], [p.delta_s for p in matched],
                    pen=None, symbol=marker, symbolSize=8, symbolBrush=color, symbolPen=color, name=f"{model.model.upper()} {direction}")
            phase_text.append(f"{model.model.upper()}: {phase.status}; observed/predicted/matched={phase.observed_crossing_count}/{phase.predicted_crossing_count}/{len(phase.matched)}; median Δt {_metric_text(phase.median_delta_s)}" + (f"; {phase.reason}" if phase.reason else ""))
        self.plots["residual"].addItem(pg.InfiniteLine(pos=0, angle=0, pen="#888888"))
        self.plots["phase"].addItem(pg.InfiniteLine(pos=0, angle=0, pen="#888888"))
        self.messages["residual"].setText(" · ".join(residual_text) + ". Points retain source IDs; gaps are not connected.")
        self.rmseMessage.setText("First and last thirds count valid samples, not equal elapsed time. " + " · ".join(strata_text))
        for key, ticks in (("time", ("Early third", "Full", "Late third")), ("speed", ("Low |ω|", "Middle |ω|", "High |ω|"))):
            self.plots[key].getAxis("bottom").setTicks([list(enumerate(ticks))])
            self.plots[key].setXRange(-.5, 2.5, padding=0)
        self.messages["phase"].setText("Each series is centered by its own fit-window mean. Match same source segment + direction by ordinal; never cross gaps. " + " · ".join(phase_text))
        self._physical(models, result.reference_energy_proxy, source.request)
        for key in ("residual", "phase"):
            times = [t for f, t in zip(source.request.series.frame_indices, source.request.series.time_release_relative_s)
                     if source.request.start_frame_index <= f <= source.request.end_frame_index]
            self.plots[key].setXRange(times[0], times[-1], padding=.02)

    def _bars(self, key, metrics, index, color, name):
        pairs = [(i, metric.value) for i, metric in enumerate(metrics) if metric.value is not None]
        if pairs:
            self.plots[key].addItem(pg.BarGraphItem(x=[i+(index-.5)*.32 for i, _ in pairs],
                height=[value for _, value in pairs], width=.3, brush=color, name=name))

    def _physical(self, models, proxy, request):
        rows = []
        evidence = {model.model: model for model in models}
        def add(name, getter):
            rows.append((name, *(getter(evidence[key]) if key in evidence else "Not displayed" for key in (M0, M1))))
        add("Fit / identity status", lambda m: f"{m.fit_status} / {m.fit_identity_status}" + (f": {m.fit_identity_reason}" if m.fit_identity_reason else ""))
        add("q / (g/L) (ratio)", lambda m: _metric_text(m.length_consistency.fit_to_g_over_l_ratio))
        add("g/q apparent dynamical length (m)", lambda m: _metric_text(m.length_consistency.apparent_dynamical_length_m))
        add("Apparent length vs calibrated L (%)", lambda m: _metric_text(m.length_consistency.apparent_length_difference_percent))
        add("Tail window / complete periods", lambda m: f"{m.tail.start_s:.5g}–{m.tail.end_s:.5g} s / {m.tail.period_count}")
        add("Tail q (s⁻²; needs ≥10 periods)", lambda m: _metric_text(m.tail.q_tail_s_inv2))
        add("Tail q vs fitted q (%)", lambda m: _metric_text(m.tail.tail_to_fit_q_difference_percent))
        add("ODE energy-balance trapezoid RMSE (s⁻²)", lambda m: _metric_text(m.energy_dissipation.energy_balance_rmse_s_inv2))
        add("ODE maximum adjacent energy increase (s⁻²)", lambda m: _metric_text(m.energy_dissipation.maximum_energy_increase_s_inv2))
        add("ODE maximum dissipation rate (s⁻³)", lambda m: _metric_text(m.energy_dissipation.maximum_dissipation_rate_s_inv3))
        rows.append(("Shared observed reference energy min / max (q=g/L; s⁻²)",
            _metric_text(proxy.total_energy_min_s_inv2) + " / " + _metric_text(proxy.total_energy_max_s_inv2), "Shared reference; not an M1 fit"))
        fill_table(self.physicalTable, rows)
        q_values = [request.g_m_s2/request.effective_length_m]
        labels = ["Physical g/L"]
        brushes = ["#aaaaaa"]
        for model in models:
            value = model.length_consistency.fit_q_s_inv2
            if value is not None:
                q_values.append(value); labels.append(model.model.split("_")[0]+" fit q"); brushes.append(COLORS[0 if model.model == M0 else 1])
        self.plots["physical"].addItem(pg.BarGraphItem(x=list(range(len(q_values))), height=q_values, width=.5, brushes=brushes))
        self.plots["physical"].getAxis("bottom").setTicks([list(enumerate(labels))])
        self.plots["physical"].setXRange(-.5, len(q_values)-.5, padding=0)
        self.messages["physical"].setText("q is a lumped inertia/geometry diagnostic. g/q is an apparent dynamical length, not a measured COM length. "
            "ODE E=ω²/2+q(1−cosθ) and dE/dt=−α₁*ω²−α₂*|ω|³ are an internal no-refit identity check, not agreement with observed energy. "
            f"Observed reference energy uses physical q=g/L and SG9/3 separately ({proxy.status}" + (f": {proxy.reason}" if proxy.reason else "") + ").")
