"""单摆 scalar 分析页与后台编排；复用主窗口的视频/项目生命周期。"""

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from math import isfinite, pi
from threading import Event

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSpinBox,
                              QTabWidget, QVBoxLayout, QWidget)

from ai_physics_tracker.application.pendulum_analysis import (
    ANALYSIS_KIND, analysis_input_state, analysis_video_stamp, load_analysis_result,
    prepare_analysis_job, run_analysis_job,
)
from ai_physics_tracker.application.pendulum_setup import pendulum_setup_status
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
        self.tabs = QTabWidget(self)
        self.plots = {}
        self.items = {}
        self.cursors = {}
        self.highlights = {}
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
            self.tabs.addTab(plot, title)
        layout = QVBoxLayout(self)
        layout.addWidget(self.statusLabel)
        layout.addLayout(controls)
        layout.addWidget(self.summaryLabel)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.frameLabel)
        note = QLabel("Gaps stay missing. SG9/3 uses no presmoothing; first/last 4 points of each segment are edge windows. Click a point → inspect video; return to Acquire to relabel, then recompute.", self)
        note.setWordWrap(True)
        layout.addWidget(note)

    def _pointClicked(self, _item, points, _event=None):
        if points:
            self.frameRequested.emit(int(points[0].data()))

    def clearData(self):
        self.payload = None
        for kind, item in self.items.items():
            item.setData([], [])
            self.highlights[kind].setData([], [])
            self.cursors[kind].hide()
        self.summaryLabel.clear()
        self.frameLabel.setText("Click a plotted point to inspect its source frame")

    def setPayload(self, payload, valid, reason=None):
        self.payload = payload
        rows = payload["rows"]
        end = payload["config"]["end_frame_index"]
        usable = [r["is_qc_valid"] and 0 <= r["time_release_relative_s"] and r["frame_index"] <= end for r in rows]
        for kind, item in self.items.items():
            x_key = "theta_rad" if kind == "phase" else "time_release_relative_s"
            y_key = {"theta": "theta_rad", "omega": "omega_rad_s", "phase": "omega_rad_s", "energy": "energy_s_inv2"}[kind]
            x = np.asarray([r[x_key] if r[x_key] is not None else np.nan for r in rows])
            y = np.asarray([r[y_key] if ok and r[y_key] is not None else np.nan for r, ok in zip(rows, usable)])
            connect = np.zeros(len(rows), dtype=bool)
            for i in range(len(rows)-1):
                connect[i] = (all(isfinite(v) for v in (x[i], y[i], x[i+1], y[i+1]))
                    and rows[i+1]["frame_index"] == rows[i]["frame_index"]+1
                    and rows[i]["theta_rad"] is not None and rows[i+1]["theta_rad"] is not None
                    and abs(rows[i+1]["theta_rad"]-rows[i]["theta_rad"]) <= pi)
            item.setData(x, y, connect=connect, data=[r["frame_index"] for r in rows])
            self.plots[kind].autoRange()
        periods, tail = payload["periods"], payload["tail"]
        q = payload["q_reference_s_inv2"]
        tail_text = (f"q_tail = {tail['omega2_mean_s_inv2']:.6g} s⁻²" if tail["omega2_mean_s_inv2"] is not None
                     else "unavailable: " + str(tail["reason"]))
        omega_count = sum(r["omega_rad_s"] is not None for r in rows)
        energy_count = sum(r["energy_s_inv2"] is not None for r in rows)
        self.summaryLabel.setText(f"QC-valid in selected interval: {sum(usable)}/{sum(0 <= r['time_release_relative_s'] and r['frame_index'] <= end for r in rows)} · ω available: {omega_count} · reference energy available: {energy_count}" + (" (unavailable: no usable SG segment)" if not energy_count else "") + "\n"
            + f"Reference energy = ω²/2 + q(1−cos θ), q=g/L={q:.6g} s⁻² (proxy; not fitted energy or joules).\n"
            f"Complete periods: {len(periods['periods'])} · Tail t>{tail['start_s']:.4g} s: {len(tail['periods'])} periods; {tail_text}")
        self.statusLabel.setText(("Current — adopted four landmarks + manual corrections" if valid else "Historical / STALE — " + (reason or "inputs changed"))
            + f" · source run {payload['measurement']['active_run_id'][:8]} · student SG9/3")

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
        self.panel.cancelButton.clicked.connect(self.cancel)
        self.panel.endFrame.valueChanged.connect(self._intervalChanged)
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
        if self.panel.payload is not None:
            applied = self.panel.payload["config"]["end_frame_index"]
            if self.panel.endFrame.value() != applied:
                self.panel.statusLabel.setText("Interval changed — recompute to apply; plots still show saved interval")

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
        else:
            self.panel.endFrame.setMinimum(experiment.release_frame_index or 0)
        status = pendulum_setup_status(session.project, experiment)
        self.panel.computeButton.setEnabled(status.can_analyze and experiment.active_infer_run_id is not None
                                           and session.can_measure(video_id) and self._future is None)
        self.panel.cancelButton.setEnabled(self._future is not None)
        records = [r for r in session.project.scientific_results if r.experiment_id == experiment.experiment_id and r.kind == ANALYSIS_KIND]
        record = max(records, key=lambda r: r.created_at) if records else None
        state = analysis_input_state(session, experiment.experiment_id)
        video_stamp = _videoStamp(session, experiment.experiment_id)
        key = (state, record, video_stamp)
        if record is None:
            if self._future is None:
                self.panel.clearData()
                message = "Ready — compute adopted four-landmark analysis"
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
            self._key = key
            if self.panel.payload is None:
                saved_end = record.extra_fields.get("end_frame_index")
                if type(saved_end) is int:
                    self.panel.endFrame.blockSignals(True)
                    self.panel.endFrame.setValue(saved_end)
                    self.panel.endFrame.blockSignals(False)
            self.panel.statusLabel.setText("Historical result — verifying payload and current inputs…")
            self._submit("read", state, self._executor.submit(_readJob, session.detached(), record, self._newCancel()))
        self.panel.presentFrame(self.window.presentedFrameIndex)

    def _newCancel(self):
        self._cancel = Event()
        return self._cancel

    def _submit(self, mode, state, future):
        self._context = (mode, self.window.deliveryGeneration, state)
        self._future = future
        self._timer.start(30)
        self.panel.cancelButton.setEnabled(True)
        self.panel.computeButton.setEnabled(False)

    def compute(self):
        if self._future is not None or self._closed or self.window.projectActions.busy:
            return
        session, experiment = self.window.analysisSession, self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        try:
            job = prepare_analysis_job(session, experiment.experiment_id, self.panel.endFrame.value())
            self._submit("compute", job.captured_state, self._executor.submit(run_analysis_job, job, self._newCancel()))
        except Exception as error:
            self.panel.statusLabel.setText(str(error))
        else:
            self.panel.statusLabel.setText("Computing adopted four-landmark analysis…")

    def cancel(self):
        self._cancel.set()
        self.panel.statusLabel.setText("Cancelled — pending results will be discarded")

    def _poll(self):
        future = self._future
        if future is None or not future.done() or self.window.projectActions.busy:
            return
        self._timer.stop()
        self._future = None
        mode, generation, state = self._context
        session = self.window.analysisSession
        try:
            result = future.result()
            if self._cancel.is_set() or generation != self.window.deliveryGeneration or session is None:
                raise CancelledError()
            if self.window.activeVideoId != state[3].video_id or analysis_input_state(session, state[2].experiment_id) != state:
                raise ValueError("analysis inputs changed — result discarded; recompute")
            if mode == "compute":
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
