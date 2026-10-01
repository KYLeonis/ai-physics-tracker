"""GUI层：只读科学诊断/等价族后台任务，按fit身份缓存并拒收迟到结果。"""

from concurrent.futures import CancelledError, ThreadPoolExecutor
from queue import Empty, SimpleQueue
from threading import Event
from time import monotonic

from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.application.pendulum_analysis import analysis_input_state
from ai_physics_tracker.application.pendulum_exploration import read_fit_exploration, preview_equivalence
from ai_physics_tracker.domain.pendulum_identifiability import build_identifiability_curve, build_identifiability_surface
from ai_physics_tracker.gui.pendulum_analysis import _videoStamp
from ai_physics_tracker.gui.pendulum_teaching_panel import ParameterEquivalencePanel


def _explore(session, record, cache, mode, scale, control, cancel, progress):
    """线程只接收快照与纯数据；不捕获widget，不写项目或拟合结果。"""
    source, curve, surface = cache if cache is not None else (read_fit_exploration(session, record, cancel), None, None)
    if mode == "scan" and source.parameters is not None:
        def check():
            if cancel.is_set(): raise CancelledError()
        curve = build_identifiability_curve(source.request, source.parameters, check_cancel=check,
                                           progress=lambda *args: progress.put(args))
        surface = build_identifiability_surface(curve)
    preview = None if source.parameters is None else preview_equivalence(source, scale, control, curve, cancel)
    if cancel.is_set(): raise CancelledError()
    return (source, curve, surface), preview


class PendulumExplorationActions(QObject):
    def __init__(self, window, criticism_panel):
        super().__init__(window)
        self.window = window
        self.criticism = criticism_panel
        self.teaching = ParameterEquivalencePanel(window)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pendulum-explore")
        self._key = None; self._cache = None; self._future = None; self._closed = False
        self._cancel = Event(); self._progress = SimpleQueue()
        self._timer = QTimer(self); self._timer.timeout.connect(self._poll)
        self._refreshTimer = QTimer(self); self._refreshTimer.setSingleShot(True)
        self._refreshTimer.timeout.connect(self.refresh)
        self._previewTimer = QTimer(self); self._previewTimer.setSingleShot(True)
        self._previewTimer.timeout.connect(self._startPreview)
        for signal in (window.analysisChanged, window.projectChanged, window.selectedTrackChanged,
                       window.pendulumFitActions.resultChanged):
            signal.connect(self.scheduleRefresh)
        window.closing.connect(self.shutdown)
        self.criticism.refreshRequested.connect(self.reload)
        self.criticism.cancelRequested.connect(self.cancel)
        self.criticism.frameRequested.connect(window.seekSourceFrame)
        self.teaching.buildRequested.connect(self.scan)
        self.teaching.cancelRequested.connect(self.cancel)
        self.teaching.previewRequested.connect(self.schedulePreview)
        self.refresh()

    def _sourceKey(self):
        session, fit = self.window.analysisSession, self.window.pendulumFitActions
        key = fit._key
        if (session is None or key is None or fit._future is not None or not fit.panel.payload_valid
                or key[1] not in session.project.scientific_results
                or key[0][3].video_id != self.window.activeVideoId
                or key[0] != analysis_input_state(session, key[1].experiment_id)
                or key[2] != _videoStamp(session, key[1].experiment_id)):
            return None
        return key + (self.window.deliveryGeneration,)

    def scheduleRefresh(self, *_args):
        if not self._closed: self._refreshTimer.start(0)

    def _retire(self):
        self._cancel.set(); self._future = None; self._timer.stop(); self._previewTimer.stop()

    def _setBusy(self, busy, *, scanning=False):
        self.criticism.setBusy(busy); self.teaching.setBusy(busy, scanning=scanning)
        ready = self._key is not None
        self.criticism.refreshButton.setEnabled(ready and not busy)
        self.teaching.buildButton.setEnabled(ready and not busy and self._cache is not None
                                             and self._cache[0].parameters is not None)
        self.teaching.buildButton.setText("Show cached surface" if self._cache is not None and self._cache[1] is not None
                                         else "Build conditional surface")

    def refresh(self):
        if self._closed: return
        key = self._sourceKey()
        if key == self._key: return
        self._retire(); self._key = key; self._cache = None
        self.criticism.clearData(); self.teaching.clearData()
        self._setBusy(False)
        if key is None:
            text = "A current verified ODE fit is required — open ODE fitting; Run fit if missing or stale."
            self.criticism.status.setText(text); self.teaching.status.setText(text)
        else:
            self._submit("read")

    def reload(self):
        if self._key is not None and self._future is None:
            self._cache = None; self._submit("read")

    def _submit(self, mode):
        if self._closed or self._key is None or self._sourceKey() != self._key: return
        self._retire(); self._cancel = Event(); self._progress = SimpleQueue()
        self._context = (self._key, mode); self._started = monotonic(); self._counts = None
        self._future = self._executor.submit(_explore, self.window.analysisSession.detached(),
            self._key[1], self._cache, mode, self.teaching.lambdaValue.value() if mode != "read" else 1.,
            self.teaching.control.isChecked() if mode != "read" else False, self._cancel, self._progress)
        self.teaching.progress.setRange(0, 0)
        self._setBusy(True, scanning=mode != "preview")
        self._timer.start(50)

    def scan(self):
        if self._future is None and self._cache is not None:
            if self._cache[1] is None: self._submit("scan")
            else: self.teaching.tabs.setCurrentIndex(2)

    def schedulePreview(self):
        if self._cache is None or self._closed: return
        # 立即拒收旧preview，输入停顿后才启动下一次积分。
        self._cancel.set(); self._previewTimer.start(200)

    def _startPreview(self):
        if self._cache is not None: self._submit("preview")

    def cancel(self):
        self._cancel.set(); self._previewTimer.stop()
        self.teaching.status.setText("Cancelling — previous accepted preview kept")
        if self._future is not None and self._context[1] == "read":
            self.criticism.status.setText("Cancelling diagnostics")

    def _poll(self):
        future = self._future
        if future is None: return
        key, mode = self._context
        try:
            while True: self._counts = self._progress.get_nowait()
        except Empty:
            pass
        stage = {"read": "Verifying current fit and diagnostics", "scan": "Scanning conditional q objective", "preview": "Integrating independent raw forwards"}[mode]
        if self._cancel.is_set(): stage = "Cancelling"
        if self._counts is not None:
            done, total = self._counts
            stage += f" · {done}/{total} nodes"
            self.teaching.progress.setRange(0, total); self.teaching.progress.setValue(done)
        message = f"{stage} · elapsed {int(monotonic()-self._started)} s · running in background"
        self.teaching.status.setText(message)
        if mode == "read": self.criticism.status.setText(message)
        if not future.done() or self.window.projectActions.busy: return
        self._future = None; self._timer.stop()
        try:
            cache, preview = future.result()
            if self._cancel.is_set() or key != self._sourceKey(): raise CancelledError()
            self._cache = cache
            source, _, surface = cache
            self.criticism.setSource(source)
            if mode == "read": self.teaching.configure(source)
            if surface is not None: self.teaching.setSurface(surface)
            if mode == "scan": self.teaching.tabs.setCurrentIndex(2)
            if preview is not None: self.teaching.setPreview(source, preview)
            else: self.teaching.status.setText("Parameter exploration unavailable: no converged model; inspect fit start diagnostics.")
        except CancelledError:
            self.teaching.status.setText("Cancelled — previous accepted preview kept")
            if mode == "read": self.criticism.status.setText("Diagnostics cancelled — use Refresh diagnostics to retry")
        except Exception as error:
            self.teaching.status.setText(f"Exploration unavailable: {error}")
            if mode == "read": self.criticism.status.setText(f"Diagnostics unavailable: {error}")
        finally:
            self._setBusy(False)
            if key != self._sourceKey(): self.scheduleRefresh()

    def shutdown(self):
        self._closed = True; self._retire(); self._refreshTimer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
