"""单摆 scalar 分析页与后台编排；复用主窗口的视频/项目生命周期。"""

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from collections import Counter
from math import isfinite, pi
from threading import Event

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QTimer, Signal, Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSpinBox,
                              QTabWidget, QVBoxLayout, QWidget)

from ai_physics_tracker.application.pendulum_analysis import (
    ANALYSIS_KIND, analysis_input_state, analysis_video_stamp, load_analysis_result,
    prepare_analysis_job, run_analysis_job,
)
from ai_physics_tracker.application.pendulum_setup import pendulum_setup_status
from ai_physics_tracker.domain.angular_analysis import (
    AngularSeries, STUDENT, SG_WINDOW, SG_POLYORDER, UNIFORM_DT_REL_TOL,
    analysis_config, valid_segments,
)
from ai_physics_tracker.application.project_session import ProjectSessionError


def _videoStamp(session, experiment_id):
    try:
        return analysis_video_stamp(session, experiment_id)
    except (OSError, ProjectSessionError):
        return None


def _readJob(session, record, cancel):
    if cancel.is_set():
        raise CancelledError()
    stamp = _videoStamp(session, record.experiment_id)
    payload, valid, reason = load_analysis_result(session, record)
    if _videoStamp(session, record.experiment_id) != stamp:
        valid, reason = False, "video changed during input verification"
    return payload, valid, reason, stamp


class PendulumAnalysisPanel(QWidget):
    frameRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.payload = None
        self._series = None
        self.repair_frames = ()
        self.payload_valid = False
        self.repairButton = QPushButton("Repair suggested frames (tip only)", self)
        self.repairButton.hide()
        self.statusLabel = QLabel("No pendulum analysis yet", self)
        self.statusLabel.setWordWrap(True)
        self.summaryLabel = QLabel("", self)
        self.summaryLabel.setWordWrap(True)
        self.frameLabel = QLabel("Click a plotted point to inspect its source frame", self)
        self.frameLabel.setWordWrap(True)
        self.endFrame = QSpinBox(self)
        self.computeButton = QPushButton("Compute pendulum analysis", self)
        self.cancelButton = QPushButton("Cancel", self)
        self.cancelButton.setEnabled(False)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Last source frame:", self))
        controls.addWidget(self.endFrame)
        controls.addWidget(self.computeButton)
        controls.addWidget(self.cancelButton)
        self.sgWindow = QSpinBox(self)
        self.sgWindow.setRange(3, 9999)
        self.sgWindow.setSingleStep(2)
        self.sgWindow.setValue(SG_WINDOW)
        self.sgPolyorder = QSpinBox(self)
        self.sgPolyorder.setRange(1, 9998)
        self.sgPolyorder.setValue(SG_POLYORDER)
        self.sgHint = QLabel(self)
        self.sgHint.setWordWrap(True)
        sg_controls = QHBoxLayout()
        sg_controls.addWidget(QLabel("SG window (frames):", self))
        sg_controls.addWidget(self.sgWindow)
        sg_controls.addWidget(QLabel("Polynomial order:", self))
        sg_controls.addWidget(self.sgPolyorder)
        self.sgPresets = []
        for window, order, title in ((9, 3, "Default 9/3"), (7, 3, "7/3"), (5, 2, "5/2")):
            button = QPushButton(title, self)
            button.clicked.connect(lambda _checked=False, w=window, p=order: self.setSG(w, p))
            sg_controls.addWidget(button)
            self.sgPresets.append(button)
        self.sgWindow.valueChanged.connect(self.updateSGHint)
        self.sgPolyorder.valueChanged.connect(self.updateSGHint)
        self.endFrame.valueChanged.connect(self.updateSGHint)
        self.tabs = QTabWidget(self)
        self.plots = {}
        self.items = {}
        self.cursors = {}
        self.highlights = {}
        self.chartMessages = {}
        for kind, title, x_label, x_unit, y_label, y_unit in (
            ("theta", "Angle", "Time from release", "s", "θ", "rad"),
            ("omega", "Angular velocity", "Time from release", "s", "ω", "rad/s"),
            ("phase", "Phase portrait", "θ", "rad", "ω", "rad/s"),
            ("energy", "Reference energy", "Time from release", "s", "Reference energy", "s^-2"),
        ):
            plot = pg.PlotWidget(enableMenu=False)
            plot.setLabel("bottom", x_label, units=x_unit)
            plot.setLabel("left", y_label, units=y_unit)
            plot.showGrid(x=True, y=True, alpha=.2)
            for axis in ("left", "bottom"):
                plot.getAxis(axis).enableAutoSIPrefix(False)
            cursor = pg.InfiniteLine(pen=pg.mkPen("#008ca8", width=2))
            if kind != "phase":
                plot.addItem(cursor, ignoreBounds=True)
            cursor.hide()
            highlight = pg.ScatterPlotItem(size=12, brush="#e4a22e")
            plot.addItem(highlight, ignoreBounds=True)
            self.plots[kind] = plot
            self.cursors[kind] = cursor
            self.highlights[kind] = highlight
            self.items[kind] = plot.plot(pen=pg.mkPen("#2c8cc1", width=2),
                                         symbol="o", symbolSize=5)
            self.items[kind].sigPointsClicked.connect(self._pointClicked)
            page = QWidget(self.tabs)
            message = QLabel("No analysis yet — compute from the adopted trajectory", page)
            message.setWordWrap(True)
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.addWidget(message)
            page_layout.addWidget(plot, 1)
            plot.hide()
            self.chartMessages[kind] = message
            self.tabs.addTab(page, title)
        self.excludedAngles = pg.ScatterPlotItem(symbol="x", size=7, pen=pg.mkPen("#aaaaaa"), brush=None)
        self.plots["theta"].addItem(self.excludedAngles)
        self.excludedAngles.sigClicked.connect(self._pointClicked)
        layout = QVBoxLayout(self)
        layout.addWidget(self.statusLabel)
        layout.addLayout(controls)
        layout.addLayout(sg_controls)
        layout.addWidget(self.sgHint)
        layout.addWidget(self.summaryLabel)
        layout.addWidget(self.repairButton)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.frameLabel)
        self.note = QLabel("Compute from adopted tip + fixed pivot. SG estimates derivatives within continuous valid segments; gaps stay missing.", self)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.updateSGHint()

    def sgSettings(self):
        return self.sgWindow.value(), self.sgPolyorder.value()

    def setSG(self, window, order):
        self.sgWindow.setValue(window)
        self.sgPolyorder.setValue(order)

    def settingsMatchPayload(self):
        if self.payload is None:
            return False
        derivative = self.payload["config"]["angular"]["derivative"]
        return (self.sgSettings() == (derivative["window_frames"], derivative["polyorder"])
                and self.endFrame.value() == self.payload["config"]["end_frame_index"])

    def updateSGHint(self):
        window, order = self.sgSettings()
        try:
            analysis_config(STUDENT, sg_window=window, sg_polyorder=order)
        except ValueError as error:
            self.sgHint.setText(str(error))
            return
        text = "Choose settings, then Compute. Shorter windows use shorter segments but reduce noise averaging."
        if self._series is not None:
            series = self._series
            mask = tuple(t >= 0 and f <= self.endFrame.value()
                         for f, t in zip(series.frame_indices, series.time_release_relative_s))
            segments = valid_segments(series, mask)
            eligible = 0
            for start, end in segments:
                if end-start < window:
                    continue
                dt = np.diff(series.time_release_relative_s[start:end])
                delta = float(np.median(dt))
                if np.all(np.abs(dt-delta) <= UNIFORM_DT_REL_TOL * delta):
                    eligible += end-start
            longest = max((end-start for start, end in segments), default=0)
            text = (f"SG{window}/{order}: {eligible} points eligible for ω / phase / energy; longest block {longest} frames. "
                    f"Window span ≈ {(window-1)/series.fps_nominal:.3g} s. " + text)
        self.sgHint.setText(text)

    def _pointClicked(self, _item, points, _event=None):
        if points:
            self.frameRequested.emit(int(points[0].data()))

    def clearData(self):
        self.payload = None
        self._series = None
        self.repair_frames = ()
        self.payload_valid = False
        self.repairButton.hide()
        for kind, item in self.items.items():
            item.setData([], [])
            self.highlights[kind].setData([], [])
            self.cursors[kind].hide()
            self.plots[kind].hide()
            self.chartMessages[kind].setText("No analysis yet — compute from the adopted trajectory")
            self.chartMessages[kind].setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.excludedAngles.setData([], [])
        self.summaryLabel.clear()
        self.frameLabel.setText("Click a plotted point to inspect its source frame")
        self.updateSGHint()

    def setPayload(self, payload, valid, reason=None):
        self.payload = payload
        self.payload_valid = valid
        self.repair_frames = ()
        rows = payload["rows"]
        end = payload["config"]["end_frame_index"]
        derivative = payload["config"]["angular"]["derivative"]
        window, order = derivative["window_frames"], derivative["polyorder"]
        usable = [r["is_qc_valid"] and 0 <= r["time_release_relative_s"] and r["frame_index"] <= end for r in rows]
        selected = [0 <= r["time_release_relative_s"] and r["frame_index"] <= end for r in rows]
        series = AngularSeries(payload["reconstruction_digest"],
            tuple(r["frame_index"] for r in rows),
            tuple(r["time_release_relative_s"] for r in rows),
            tuple(r["theta_rad"] for r in rows), tuple(r["is_qc_valid"] for r in rows),
            payload["measurement"]["video"]["fps_nominal"])
        self._series = series
        self.updateSGHint()
        longest = max((b-a for a, b in valid_segments(series, tuple(selected))), default=0)
        excluded = [r for r, inside, ok in zip(rows, selected, usable)
                    if inside and not ok and r["theta_rad"] is not None]
        self.excludedAngles.setData(
            [r["time_release_relative_s"] for r in excluded],
            [r["theta_rad"] for r in excluded], data=[r["frame_index"] for r in excluded])
        omega_reasons = Counter(r["omega_reason"] for r, inside in zip(rows, selected)
                                if inside and r["omega_reason"])
        unavailable = (f"SG{window}/{order} needs {window} consecutive QC-valid frames; longest block: {longest}. "
                       "Choose a shorter SG window and Compute to use existing segments, or correct missing tip positions."
                       if longest < window else
                       "No usable derivative: " + ", ".join(f"{reason} ({count} frames)" for reason, count in omega_reasons.items()))
        if longest < window:
            start = min((i for i in range(len(rows)-window+1)
                         if all(selected[i:i+window]) and not all(usable[i:i+window])),
                        key=lambda i: sum(not ok for ok in usable[i:i+window]), default=None)
            if start is not None:
                repair = rows[start:start+window]
                self.repair_frames = tuple(r["frame_index"] for r, ok in zip(repair, usable[start:start+window]) if not ok)
                gaps = ", ".join(map(str, self.repair_frames))
                unavailable += (f"\nRepair example: source block {repair[0]['frame_index']}–{repair[-1]['frame_index']}; "
                                f"inspect/correct the tip at QC-excluded frames {gaps}.")
        for kind, item in self.items.items():
            x_key = "theta_rad" if kind == "phase" else "time_release_relative_s"
            y_key = {"theta": "theta_rad", "omega": "omega_rad_s", "phase": "omega_rad_s", "energy": "energy_s_inv2"}[kind]
            x = np.asarray([r[x_key] if r[x_key] is not None else np.nan for r in rows])
            y = np.asarray([r[y_key] if ok and r[y_key] is not None else np.nan for r, ok in zip(rows, usable)])
            # 无效y对应的时间不能把图范围扩到pre-release区间。
            x = np.where(np.isfinite(y), x, np.nan)
            connect = np.zeros(len(rows), dtype=bool)
            for i in range(len(rows)-1):
                connect[i] = (all(isfinite(v) for v in (x[i], y[i], x[i+1], y[i+1]))
                    and rows[i+1]["frame_index"] == rows[i]["frame_index"]+1
                    and rows[i]["theta_rad"] is not None and rows[i+1]["theta_rad"] is not None
                    and abs(rows[i+1]["theta_rad"]-rows[i]["theta_rad"]) <= pi)
            has_values = bool(np.any(np.isfinite(x) & np.isfinite(y)))
            if has_values:
                item.setData(x, y, connect=connect, data=[r["frame_index"] for r in rows])
            else:
                # 全NaN散点的bounds会把pyqtgraph空图范围放大到异常数量级。
                item.setData([], [])
            visible = has_values or (kind == "theta" and bool(excluded))
            self.plots[kind].setVisible(visible)
            message = self.chartMessages[kind]
            message.setAlignment(Qt.AlignmentFlag.AlignLeft if visible else Qt.AlignmentFlag.AlignCenter)
            if kind == "theta":
                message.setText(f"Blue: {sum(usable)} QC-valid angles. Gray crosses: {len(excluded)} geometry-only previews, excluded from derivatives/energy/fitting. "
                               + ("" if visible else "No adopted tip positions in this interval."))
            elif has_values:
                edge_count = sum(ok and r[y_key] is not None and r["edge_window"] for r, ok in zip(rows, usable))
                message.setText(f"Computed with SG{window}/{order} from continuous QC-valid segments; gaps remain missing. "
                                f"{edge_count} points use edge-window estimates.")
            else:
                message.setText({"omega": "Angular velocity", "phase": "Phase portrait", "energy": "Reference energy"}[kind]
                                + " unavailable.\n" + (
                                    "Energy calculation unavailable: " + ", ".join(sorted({r["energy_reason"] for r, ok in zip(rows, usable)
                                        if ok and r["energy_reason"]}))
                                    if kind == "energy" and any(r["omega_rad_s"] is not None for r, ok in zip(rows, usable) if ok)
                                    else unavailable))
            if visible:
                self.plots[kind].autoRange()
        self.repairButton.setVisible(bool(self.repair_frames))
        self.repairButton.setEnabled(valid)
        self.repairButton.setText(f"Repair suggested frames: {', '.join(map(str, self.repair_frames))} (tip only)")
        periods, tail = payload["periods"], payload["tail"]
        q = payload["q_reference_s_inv2"]
        tail_text = (f"q_tail = {tail['omega2_mean_s_inv2']:.6g} s⁻²" if tail["omega2_mean_s_inv2"] is not None
                     else "unavailable: " + str(tail["reason"]))
        omega_count = sum(ok and r["omega_rad_s"] is not None for r, ok in zip(rows, usable))
        energy_count = sum(ok and r["energy_s_inv2"] is not None for r, ok in zip(rows, usable))
        qc_counts = Counter(reason for r, inside in zip(rows, selected) if inside for reason in r["qc_reasons"])
        labels = {"radius_out_of_tolerance": "tip radius outside tolerance", "body_length_out_of_tolerance": "body length outside tolerance"}
        qc_text = "; ".join(f"{labels.get(reason, reason.replace(':no_adopted_point', ' missing adopted points'))}: {count}"
                            for reason, count in qc_counts.most_common()
                            if reason.endswith(":no_adopted_point") or reason in labels or reason.startswith("user_excluded:"))
        if not qc_text and qc_counts:
            qc_text = "; ".join(f"{reason}: {count}" for reason, count in qc_counts.items())
        auxiliary_count = sum(bool(r.get("auxiliary_qc_reasons")) for r, inside in zip(rows, selected) if inside)
        self.summaryLabel.setText(f"Auxiliary landmark warnings: {auxiliary_count} frames (do not exclude tip angular analysis).\n"
            + f"QC-valid in selected interval: {sum(usable)}/{sum(0 <= r['time_release_relative_s'] and r['frame_index'] <= end for r in rows)} · ω available: {omega_count} · reference energy available: {energy_count}" + (" (unavailable: no usable SG segment)" if not omega_count else " (energy unavailable; inspect its reasons)" if not energy_count else "") + "\n"
            + f"Longest QC-valid block: {longest} frames (SG needs {window}). Main exclusions (counts may overlap): {qc_text or 'none'}.\n"
            + f"Reference energy = ω²/2 + q(1−cos θ), q=g/L={q:.6g} s⁻² (proxy; not fitted energy or joules).\n"
            f"Complete periods: {len(periods['periods'])} · Tail t>{tail['start_s']:.4g} s: {len(tail['periods'])} periods; {tail_text}")
        self.resultStatusText = (("Current — tip + fixed pivot; auxiliary landmarks are diagnostic only" if valid else "Historical / STALE — " + (reason or "inputs changed"))
            + f" · source run {payload['measurement']['active_run_id'][:8]} · "
            + ("student default " if (window, order) == (SG_WINDOW, SG_POLYORDER) else "custom ") + f"SG{window}/{order}")
        self.statusLabel.setText(self.resultStatusText)
        self.note.setText(f"Analysis uses the adopted run + manual corrections; candidate previews are not included. "
                         f"These plots use SG{window}/{order}, minimum {window} consecutive QC-valid frames. "
                         f"Gaps stay missing; first/last {window//2} points of each segment are edge estimates. "
                         "Click a point to inspect its source frame. SG settings do not change complete-period or tail requirements.")

    def presentFrame(self, frame_index):
        if self.payload is None or frame_index is None:
            for cursor in self.cursors.values():
                cursor.hide()
            return
        row = next((r for r in self.payload["rows"] if r["frame_index"] == frame_index), None)
        if row is None:
            return
        for kind, cursor in self.cursors.items():
            if kind != "phase":
                cursor.setValue(row["time_release_relative_s"])
                cursor.show()
            y_key = {"theta": "theta_rad", "omega": "omega_rad_s", "phase": "omega_rad_s", "energy": "energy_s_inv2"}[kind]
            x = row["theta_rad"] if kind == "phase" else row["time_release_relative_s"]
            y = row[y_key]
            self.highlights[kind].setData([] if x is None or y is None else [x], [] if x is None or y is None else [y])
        sources = ", ".join(f"{role}: {point['source'] if point else 'missing'}" for role, point in row["points_by_role"].items())
        self.frameLabel.setText(f"Source frame {frame_index} · t={row['time_release_relative_s']:.4g} s · "
            + ("QC valid" if row["is_qc_valid"] else "QC excluded: " + ", ".join(row["qc_reasons"]))
            + (" · SG edge window" if row["edge_window"] else "")
            + (" · ω unavailable: " + row["omega_reason"] if row["omega_reason"] else "") + "\n" + sources)


class PendulumAnalysisActions(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.panel = PendulumAnalysisPanel(window)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pendulum-analysis")
        self._future: Future | None = None
        self._cancel = Event()
        self._closed = False
        self._key = None
        self._context = None
        self._video_id = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        window.analysisChanged.connect(self.scheduleRefresh)
        window.projectChanged.connect(self.resetContext)
        window.selectedTrackChanged.connect(self.scheduleRefresh)
        window.presentedFrameChanged.connect(self.panel.presentFrame)
        window.closing.connect(self.shutdown)
        self.panel.frameRequested.connect(window.seekSourceFrame)
        self.panel.computeButton.clicked.connect(self.compute)
        self.panel.repairButton.clicked.connect(self.repairSuggestedFrames)
        self.panel.cancelButton.clicked.connect(self.cancel)
        self.panel.endFrame.valueChanged.connect(self._intervalChanged)
        self.panel.sgWindow.valueChanged.connect(self._intervalChanged)
        self.panel.sgPolyorder.valueChanged.connect(self._intervalChanged)
        self.refresh()

    def scheduleRefresh(self, *_args):
        if not self._closed:
            self._refresh_timer.start(0)

    def resetContext(self):
        self._cancel.set()
        self._future = None
        self._timer.stop()
        self._key = None
        self._video_id = None
        self.panel.clearData()
        self.refresh()

    def _intervalChanged(self):
        try:
            window, order = self.panel.sgSettings()
            analysis_config(STUDENT, sg_window=window, sg_polyorder=order)
            settings_valid = True
        except ValueError:
            settings_valid = False
        if self.panel.payload is not None:
            self.panel.repairButton.setEnabled(self.panel.payload_valid and self._future is None
                and self.panel.settingsMatchPayload())
            if not self.panel.settingsMatchPayload():
                self.panel.statusLabel.setText("Settings changed — Compute to apply; plots still show saved settings")
            else:
                self.panel.statusLabel.setText(self.panel.resultStatusText)
        if not settings_valid:
            self.panel.computeButton.setEnabled(False)
        elif self._future is None:
            self.refresh()

    def refresh(self):
        if self._closed:
            return
        session, video_id = self.window.analysisSession, self.window.activeVideoId
        experiment = next((e for e in session.project.experiments if e.video_id == video_id), None) if session else None
        self.panel.setVisible(experiment is not None)
        self.window.chartActions.panel.setVisible(experiment is None)
        if experiment is None:
            return
        video = next(v for v in session.project.videos if v.video_id == video_id)
        if self._video_id != video_id:
            self._video_id = video_id
            self.panel.clearData()
            self.panel.endFrame.blockSignals(True)
            self.panel.endFrame.setRange(experiment.release_frame_index or 0, video.frame_count-1)
            self.panel.endFrame.setValue(video.frame_count-1)
            self.panel.endFrame.blockSignals(False)
            for control, value in ((self.panel.sgWindow, SG_WINDOW), (self.panel.sgPolyorder, SG_POLYORDER)):
                control.blockSignals(True)
                control.setValue(value)
                control.blockSignals(False)
        else:
            self.panel.endFrame.setMinimum(experiment.release_frame_index or 0)
        status = pendulum_setup_status(session.project, experiment)
        self.panel.computeButton.setEnabled(status.can_analyze and experiment.active_infer_run_id is not None
                                           and session.can_measure(video_id) and self._future is None)
        try:
            analysis_config(STUDENT, sg_window=self.panel.sgWindow.value(), sg_polyorder=self.panel.sgPolyorder.value())
        except ValueError:
            self.panel.computeButton.setEnabled(False)
        for control in (self.panel.endFrame, self.panel.sgWindow, self.panel.sgPolyorder, *self.panel.sgPresets):
            control.setEnabled(self._future is None)
        self.panel.cancelButton.setEnabled(self._future is not None)
        records = [r for r in session.project.scientific_results if r.experiment_id == experiment.experiment_id and r.kind == ANALYSIS_KIND]
        record = max(records, key=lambda r: r.created_at) if records else None
        state = analysis_input_state(session, experiment.experiment_id)
        video_stamp = _videoStamp(session, experiment.experiment_id)
        key = (state, record, video_stamp)
        if record is None:
            if self._future is None:
                self.panel.clearData()
                message = "Ready — compute tip + fixed-pivot analysis"
                if not status.can_analyze:
                    message = "Complete experiment setup. Missing: " + ", ".join(g.replace("_", " ") for g in status.missing_for_analysis)
                    if "tip_radius_reference" in status.missing_for_analysis:
                        message += ". In Acquire, choose a trustworthy labelled tip frame → Use current tip as radius reference (QC only)."
                elif experiment.active_infer_run_id is None:
                    message = "Adopt a completed joint inference first, then compute analysis"
                elif not session.can_measure(video_id):
                    message = "Video timing is not authorized — complete the timing check first"
                self.panel.statusLabel.setText(message)
            return
        if key != self._key and self._future is None:
            record_changed = self._key is None or self._key[1].result_id != record.result_id
            self._key = key
            if self.panel.payload is None or record_changed:
                saved_end = record.extra_fields.get("end_frame_index")
                if type(saved_end) is int:
                    self.panel.endFrame.blockSignals(True)
                    self.panel.endFrame.setValue(saved_end)
                    self.panel.endFrame.blockSignals(False)
                derivative = record.extra_fields.get("config", {}).get("angular", {}).get("derivative", {})
                for control, value in ((self.panel.sgWindow, derivative.get("window_frames", SG_WINDOW)),
                                       (self.panel.sgPolyorder, derivative.get("polyorder", SG_POLYORDER))):
                    if type(value) is int:
                        control.blockSignals(True)
                        control.setValue(value)
                        control.blockSignals(False)
            self.panel.statusLabel.setText("Historical result — verifying payload and current inputs…")
            self._submit("read", state, self._executor.submit(_readJob, session.detached(), record, self._newCancel()))
        self.panel.presentFrame(self.window.presentedFrameIndex)

    def _newCancel(self):
        self._cancel = Event()
        return self._cancel

    def _submit(self, mode, state, future):
        self._context = (mode, self.window.deliveryGeneration, state,
                         (self.panel.endFrame.value(), *self.panel.sgSettings()))
        self._future = future
        self._timer.start(30)
        self.panel.cancelButton.setEnabled(True)
        self.panel.computeButton.setEnabled(False)
        self.panel.repairButton.setEnabled(False)
        for control in (self.panel.endFrame, self.panel.sgWindow, self.panel.sgPolyorder, *self.panel.sgPresets):
            control.setEnabled(False)

    def repairSuggestedFrames(self):
        """只用当前已验证结果的建议；复用主窗口manual tip写入和自动跳帧。"""
        session, experiment = self.window.analysisSession, self.window.currentPendulumExperiment()
        if session is None or experiment is None or self._future is not None or self._closed or self.window.projectActions.busy:
            return
        if (not self.panel.payload_valid or not self.panel.repair_frames or self._key is None
                or self._key[0] != analysis_input_state(session, experiment.experiment_id)
                or self._key[2] != _videoStamp(session, experiment.experiment_id)
                or not self.panel.settingsMatchPayload()):
            self.panel.repairButton.setEnabled(False)
            self.panel.statusLabel.setText("Inputs changed — recompute before starting the suggested repair")
            return
        try:
            self.window.beginExperimentAnnotation(self.panel.repair_frames, tip_only=True)
        except (ProjectSessionError, ValueError) as error:
            self.panel.statusLabel.setText(f"Cannot start repair: {error}")

    def compute(self):
        if self._future is not None or self._closed or self.window.projectActions.busy:
            return
        session, experiment = self.window.analysisSession, self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        try:
            window, order = self.panel.sgSettings()
            job = prepare_analysis_job(session, experiment.experiment_id, self.panel.endFrame.value(),
                                       sg_window=window, sg_polyorder=order)
            self._submit("compute", job.captured_state, self._executor.submit(run_analysis_job, job, self._newCancel()))
        except Exception as error:
            self.panel.statusLabel.setText(str(error))
        else:
            self.panel.statusLabel.setText("Computing tip + fixed-pivot analysis…")

    def cancel(self):
        self._cancel.set()
        self.panel.statusLabel.setText("Cancelled — pending results will be discarded")

    def _poll(self):
        future = self._future
        if future is None or not future.done() or self.window.projectActions.busy:
            return
        self._timer.stop()
        self._future = None
        mode, generation, state, settings = self._context
        session = self.window.analysisSession
        try:
            result = future.result()
            if self._cancel.is_set() or generation != self.window.deliveryGeneration or session is None:
                raise CancelledError()
            if self.window.activeVideoId != state[3].video_id or analysis_input_state(session, state[2].experiment_id) != state:
                raise ValueError("analysis inputs changed — result discarded; recompute")
            if mode == "compute":
                if settings != (self.panel.endFrame.value(), *self.panel.sgSettings()):
                    raise ValueError("analysis settings changed — result discarded; recompute")
                session.apply_pendulum_analysis_result(result)
                self._key = (state, result.record, result.verified_video_stamp)
                self.panel.setPayload(result.payload, True)
                self.window._refreshHistoryButtons()
            else:
                payload, valid, reason, stamp = result
                if _videoStamp(session, state[2].experiment_id) != stamp:
                    valid, reason = False, "video changed after input verification"
                self.panel.setPayload(payload, valid, reason)
            self.panel.presentFrame(self.window.presentedFrameIndex)
        except CancelledError:
            self.panel.statusLabel.setText("Cancelled — previous result kept")
        except Exception as error:
            self.panel.statusLabel.setText(f"Analysis not updated: {error}")
        self.refresh()
        self._intervalChanged()

    def shutdown(self):
        self._closed = True
        self._cancel.set()
        self._future = None
        self._timer.stop()
        self._refresh_timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
