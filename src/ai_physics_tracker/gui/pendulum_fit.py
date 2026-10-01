"""GUI层：拟合后台任务、当前输入拒收与历史读回；线程不访问widget。"""

from concurrent.futures import CancelledError, ThreadPoolExecutor
import logging
from time import monotonic
from queue import Empty, SimpleQueue
from threading import Event

from PySide6.QtCore import QObject, QTimer, Signal

from ai_physics_tracker.application.pendulum_analysis import analysis_input_state
from ai_physics_tracker.application.pendulum_fit import (
    FIT_KIND, discard_fit_result, load_fit_result, options_from_payload,
    prepare_fit_job, run_fit_job,
)
from ai_physics_tracker.application.pendulum_setup import pendulum_setup_status
from ai_physics_tracker.gui.pendulum_analysis import _videoStamp
from ai_physics_tracker.gui.pendulum_fit_panel import PendulumFitPanel

logger = logging.getLogger(__name__)


def _readFit(session, record, cancel):
    if cancel.is_set(): raise CancelledError()
    stamp = _videoStamp(session, record.experiment_id)
    payload, valid, reason = load_fit_result(session, record)
    if cancel.is_set(): raise CancelledError()
    if _videoStamp(session, record.experiment_id) != stamp:
        valid, reason = False, "video changed during verification"
    return payload, valid, reason, stamp


def _discardUnused(future, job, cancel, accepted):
    """callback只持有任务所属root/事件，窗口销毁后仍可清理迟到文件。"""
    if job is None or not future.done() or not cancel.is_set() or accepted.is_set(): return
    try:
        result = future.result()
    except Exception:
        return  # 失败任务未返回产物；run_fit_job负责发布过程的取消清理。
    try:
        discard_fit_result(job.session, result)
    except OSError:
        logger.exception("Could not remove unused pendulum fit payload")


class PendulumFitActions(QObject):
    resultChanged = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.panel = PendulumFitPanel(window)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pendulum-fit")
        self._future = None; self._job = None; self._context = None
        self._cancel = Event(); self._accepted = Event()
        self._progress = SimpleQueue()
        self._closed = False; self._key = None; self._video_id = None; self._lastAttempt = ""
        self._timer = QTimer(self); self._timer.timeout.connect(self._poll)
        self._refreshTimer = QTimer(self); self._refreshTimer.setSingleShot(True)
        self._refreshTimer.timeout.connect(self.refresh)
        window.analysisChanged.connect(self.scheduleRefresh)
        window.projectChanged.connect(self.resetContext)
        window.selectedTrackChanged.connect(self.scheduleRefresh)
        window.presentedFrameChanged.connect(self.panel.presentFrame)
        window.closing.connect(self.shutdown)
        self.panel.runButton.clicked.connect(self.compute)
        self.panel.cancelButton.clicked.connect(self.cancel)
        self.panel.frameRequested.connect(window.seekSourceFrame)
        self.panel.settingsChanged.connect(self._optionsChanged)
        self.panel.releaseAngleButton.clicked.connect(self.fillReleaseAngle)
        self.panel.timingRequested.connect(self._requestTiming)
        self.refresh()

    @property
    def pending(self):
        return self._future is not None and self._context[0] == "compute"

    def scheduleRefresh(self, *_args):
        if not self._closed: self._refreshTimer.start(0)

    def _refreshProjectActions(self):
        refresh = getattr(self.window.projectActions, "refresh", None)
        if refresh is not None: refresh()

    def _retire(self):
        self._cancel.set()
        if self._future is not None:
            _discardUnused(self._future, self._job, self._cancel, self._accepted)
        self._future = None; self._job = None; self._timer.stop()
        self.panel.setBusy(False)
        self._refreshProjectActions()
        self.resultChanged.emit()

    def resetContext(self):
        self._retire(); self._key = None; self._video_id = None
        self.panel.clearData(); self._lastAttempt = ""; self.refresh()

    def _experiment(self):
        session = self.window.analysisSession
        return next((e for e in session.project.experiments if e.video_id == self.window.activeVideoId), None) if session else None

    def _optionsChanged(self):
        if self._future is not None or self._closed: return
        try:
            options = self.panel.options()
        except ValueError as error:
            self.panel.runButton.setEnabled(False)
            self.panel.statusLabel.setText(f"Invalid fit settings: {error}")
            return
        if self.panel.payload is not None:
            saved = options_from_payload(self.panel.payload["config"]["options"])
            self.panel.statusLabel.setText(self.panel.resultStatusText + self._lastAttempt + (
                " · Settings changed — Run fit to apply; plots retain saved settings" if options != saved else ""))
        self._enableRun()

    def _requestTiming(self):
        button = getattr(self.window, "timingButton", None)
        if button is not None: button.click()

    def _enableRun(self):
        session, experiment = self.window.analysisSession, self._experiment()
        enabled = False
        if session is not None and experiment is not None and self._future is None:
            try:
                options = self.panel.options()
                enabled = (pendulum_setup_status(session.project, experiment).can_analyze
                    and experiment.active_infer_run_id is not None and session.can_measure(experiment.video_id)
                    and (options.explicit_ic is not None or options.rest_confirmed)
                    and options.end_frame_index >= (options.start_frame_index or experiment.release_frame_index or 0))
            except ValueError:
                enabled = False
        locked = session is not None and experiment is not None and not session.can_measure(experiment.video_id)
        timing = getattr(self.window, "timingActions", None)
        button = getattr(self.window, "timingButton", None)
        validating = timing is not None and timing.pending
        action = button.text() if button is not None and not validating else ""
        self.panel.setTimingRequirement("Run fit requires video timing confirmation. " +
            ("Validating timing in background…" if validating else "Use the button here to confirm approximate timing or retry validation.")
            if locked else "", action if locked else "", locked and not validating and self._future is None)
        self.panel.runButton.setEnabled(enabled)
        self.panel.releaseAngleButton.setEnabled(self._future is None and self._releaseAngle() is not None)

    def _releaseAngle(self):
        analysis = getattr(self.window, "pendulumAnalysisActions", None)
        session, experiment = self.window.analysisSession, self._experiment()
        if (analysis is None or session is None or experiment is None or analysis._future is not None
                or not analysis.panel.payload_valid or analysis._key is None
                or analysis._key[0] != analysis_input_state(session, experiment.experiment_id)
                or analysis._key[2] != _videoStamp(session, experiment.experiment_id)):
            return None
        row = next((r for r in analysis.panel.payload["rows"] if r["frame_index"] == experiment.release_frame_index), None)
        return row["theta_rad"] if row and row["is_qc_valid"] else None

    def fillReleaseAngle(self):
        theta = self._releaseAngle()
        if theta is None:
            self.panel.statusLabel.setText("Compute current Kinematics first; release frame must have a QC-valid tip angle")
            return
        self.panel.theta0.setText(str(theta))


    def refresh(self):
        if self._closed: return
        session, experiment = self.window.analysisSession, self._experiment()
        if session is None or experiment is None:
            self._retire(); self._key = None; self._video_id = None; self.panel.clearData(); return
        video_id = experiment.video_id
        if self._video_id != (video_id, experiment.experiment_id):
            self._retire(); self._key = None; self.panel.clearData()
            self._video_id = (video_id, experiment.experiment_id)
            video = next(v for v in session.project.videos if v.video_id == video_id)
            for control, value in ((self.panel.startFrame, experiment.release_frame_index or 0),
                                   (self.panel.endFrame, video.frame_count-1)):
                control.blockSignals(True)
                control.setRange(experiment.release_frame_index or 0, video.frame_count-1)
                control.setValue(value); control.blockSignals(False)
            self.panel._startIsDefault = True
            self.panel.restConfirmed.blockSignals(True); self.panel.restConfirmed.setChecked(False)
            self.panel.restConfirmed.blockSignals(False)
            self.panel.theta0.clear(); self.panel.omega0.clear(); self.panel.resetDefaults()
        else:
            self.panel.startFrame.setMinimum(experiment.release_frame_index or 0)
            self.panel.endFrame.setMinimum(experiment.release_frame_index or 0)
        self.panel.setBusy(self._future is not None); self._enableRun()
        if self._future is not None: return
        records = [r for r in session.project.scientific_results if r.kind == FIT_KIND and r.experiment_id == experiment.experiment_id]
        good = [r for r in records if r.execution_status in ("success", "nonconverged")]
        record = max(good or records, key=lambda r: r.created_at) if records else None
        if record is None:
            status = pendulum_setup_status(session.project, experiment)
            text = "Ready — confirm held-rest IC or enter fixed θ₀ / ω₀, then Run fit."
            if not status.can_analyze: text = "Complete experiment setup: " + ", ".join(status.missing_for_analysis)
            elif experiment.active_infer_run_id is None: text = "Adopt a joint inference first; manual tip corrections will be included."
            elif session.project_root is None: text = "Save the project before fitting."
            self.panel.statusLabel.setText(text)
            return
        state = analysis_input_state(session, experiment.experiment_id)
        key = (state, record, _videoStamp(session, experiment.experiment_id))
        if key != self._key:
            restore = self.panel.payload is None or self._key is None or self._key[1].result_id != record.result_id
            self._key = key
            self._submit("read", state, None, restore=restore, record=record)
            self.panel.statusLabel.setText("Historical fit — verifying artifact and inputs…")
        self.panel.presentFrame(self.window.presentedFrameIndex)

    def _submit(self, mode, state, job, *, restore=False, record=None):
        self._cancel = Event(); self._accepted = Event(); self._progress = SimpleQueue()
        self._job = job
        options = job.options if job is not None else None
        self._context = (mode, self.window.deliveryGeneration, state, options, restore)
        self._startedAt = monotonic()
        self._progressText = "Fitting raw θ" if mode == "compute" else "Verifying saved fit"
        if job is None:
            future = self._executor.submit(_readFit, self.window.analysisSession.detached(), record, self._cancel)
        else:
            queue = self._progress
            future = self._executor.submit(run_fit_job, job, self._cancel,
                progress=lambda *args: queue.put(args))
            cancel, accepted = self._cancel, self._accepted
            future.add_done_callback(lambda done: _discardUnused(done, job, cancel, accepted))
        self._future = future; self.panel.setBusy(True); self._timer.start(30)
        self._refreshProjectActions()
        self.resultChanged.emit()

    def compute(self):
        if self._future is not None or self._closed or self.window.projectActions.busy: return
        session, experiment = self.window.analysisSession, self._experiment()
        if session is None or experiment is None: return
        try:
            job = prepare_fit_job(session, experiment.experiment_id, self.panel.options())
            self._lastAttempt = ""
            self._submit("compute", job.captured_state, job)
            self.panel.statusLabel.setText("Fitting raw θ with fixed release IC…")
        except Exception as error:
            self.panel.statusLabel.setText(f"Fit not started: {error}")

    def cancel(self):
        self._cancel.set()
        self.panel.statusLabel.setText("Cancelling — previous fit kept; pending result will be discarded")

    def _poll(self):
        if self._future is not None:
            stage = "Cancelling" if self._cancel.is_set() else self._progressText
            self.panel.progressLabel.setText(f"{stage} · elapsed {int(monotonic()-self._startedAt)} s · running in background")
        try:
            while True:
                model, done, total = self._progress.get_nowait()
                if not self._cancel.is_set():
                    self._progressText = f"Fitting {model}: {done}/{total} starts complete"
                    self.panel.statusLabel.setText(self._progressText + "…")
        except Empty:
            pass
        future = self._future
        if future is None or not future.done() or self.window.projectActions.busy: return
        self._timer.stop(); self._future = None
        mode, generation, state, options, restore = self._context
        job, cancel, accepted = self._job, self._cancel, self._accepted
        session = self.window.analysisSession
        try:
            result = future.result()
            if cancel.is_set() or generation != self.window.deliveryGeneration or session is None:
                raise CancelledError()
            if (self.window.activeVideoId != state[3].video_id
                    or analysis_input_state(session, state[2].experiment_id) != state):
                raise ValueError("fit inputs changed — result discarded; recompute")
            if mode == "compute":
                if options != self.panel.options(): raise ValueError("fit settings changed — result discarded")
                session.apply_pendulum_fit_result(result); accepted.set()
                if result.record.execution_status in ("success", "nonconverged") or self.panel.payload is None:
                    self._key = (state, result.record, result.verified_video_stamp)
                    self.panel.setPayload(result.payload, True)
                else:
                    reasons = "; ".join(f["reason"] or f["status"] for f in result.payload["fits"].values())
                    self._lastAttempt = " · Last attempt: " + reasons + "; previous fit kept"
                    self.panel.statusLabel.setText(self.panel.resultStatusText + self._lastAttempt)
                self.window._refreshHistoryButtons()
            else:
                payload, valid, reason, stamp = result
                if _videoStamp(session, state[2].experiment_id) != stamp:
                    valid, reason = False, "video changed after input verification"
                if restore: self.panel.restoreOptions(options_from_payload(payload["config"]["options"]))
                self.panel.setPayload(payload, valid, reason)
                self.panel.statusLabel.setText(self.panel.resultStatusText + self._lastAttempt)
            self.panel.presentFrame(self.window.presentedFrameIndex)
        except CancelledError:
            self.panel.statusLabel.setText("Cancelled — previous fit kept")
        except Exception as error:
            self.panel.statusLabel.setText(f"Fit not updated: {error}")
        finally:
            if job is not None and not accepted.is_set():
                cancel.set(); _discardUnused(future, job, cancel, accepted)
            self._job = None
            self.panel.setBusy(False); self._enableRun(); self._refreshProjectActions()
            if self._key is not None and session is not None and self._experiment() is not None:
                current = analysis_input_state(session, self._experiment().experiment_id)
                if self._key[0] != current or self._key[2] != _videoStamp(session, self._experiment().experiment_id):
                    self.scheduleRefresh()
            self.resultChanged.emit()

    def shutdown(self):
        self._closed = True; self._retire(); self._refreshTimer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
