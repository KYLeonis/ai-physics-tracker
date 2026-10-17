"""GUI层：合并草稿预览请求，后台纯计算，主线程核对身份后显示。"""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor, CancelledError
from threading import Event

import numpy as np
from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.domain.fit_initial import estimate_initial, adopt_estimate
from ai_physics_tracker.domain.derived import ANGULAR_KINDS
from ai_physics_tracker.application.kinematics_job import analysis_inputs
from ai_physics_tracker.application.signal_analysis_job import signal_source
from ai_physics_tracker.application.project_session import ProjectSessionError


def _preview(job, estimate, cancel=None):
    """worker只持有不可变输入，不访问Qt或活动工程。"""
    if cancel is not None and cancel.is_set():
        raise CancelledError()
    samples = np.asarray(job.samples)
    spec, suggestion = job.spec, None
    if estimate:
        suggestion = estimate_initial(samples[:, 2], samples[:, 3], spec.expression,
                                      segment_indices=samples[:, 4], wrapped=job.source.kind == "angular_position")
        if suggestion.values:
            spec = adopt_estimate(spec, suggestion)
    if cancel is not None and cancel.is_set():
        raise CancelledError()
    prediction = parse_expression(spec.expression).evaluate(
        samples[:, 2], {parameter.name: parameter.initial for parameter in spec.parameters})
    return spec, suggestion, prediction


class SignalPreview(QObject):
    """独立预览不阻塞正式任务、不发布结果；草稿变化使旧预览失效。"""

    def __init__(self, actions):
        super().__init__(actions)
        self.actions = actions
        self.panel = actions.signalPanel
        self._revision = 0
        self._future = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="signal-preview")
        self._cancel = Event()
        self._estimate = False
        self._context = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self.launch)
        self._pollTimer = QTimer(self)
        self._pollTimer.timeout.connect(self.poll)
        self.panel.estimateRequested.connect(lambda: self.request(estimate=True, immediate=True))
        self.panel.editor.exampleSelected.connect(self.example)

    def invalidate(self):
        self._revision += 1
        self._cancel.set()
        self._debounce.stop()
        if self._future is not None:
            self._future.cancel()
        self._future = None
        self._pollTimer.stop()

    def example(self):
        self.request(estimate=not self.panel.initialProtected)

    def syncContext(self, *, refresh=True):
        """相关源变化与编辑共用预览入口；保存和无关结果不触发重算。"""
        window = self.actions.window
        if (self.panel.history.active or window.currentWorkspace != "analysis"
                or not hasattr(window, "analysisTabs") or window.analysisTabs.currentIndex() != 1
                or self.panel.methods.currentIndex() != 0):
            self._context = None
            self.invalidate()
            return
        session = window.analysisSession
        try:
            selection = self.panel.selection()
            kind, _ = signal_source(selection.quantity, selection.smoothed)
            sources = tuple(item for item in session.project.derived
                            if item.track_id == selection.track_id and item.kind == kind)
            reference = self.actions.panel.angularControls.appliedReference() if kind in ANGULAR_KINDS else None
            reference_id = getattr(reference, "reference_track_id", None)
            tracks = tuple(dict.fromkeys((selection.track_id,) + ((reference_id,) if reference_id else ())))
            key = (id(session), window.deliveryGeneration, selection, sources,
                   analysis_inputs(session, window.activeVideoId, tracks),
                   self.actions.panel.parameters() if kind not in ("world_position", "angular_position") else None,
                   reference)
        except (ValueError, AttributeError, ProjectSessionError) as error:
            key = (id(session), window.deliveryGeneration, self.panel.trackChoice.currentData(),
                   self.panel.quantityChoice.currentText(), str(error))
        if key != self._context:
            if refresh and self.actions._signal_job is not None:
                return
            self._context = key
            if refresh:
                self.request(estimate=self._estimate)

    def request(self, *, estimate=False, immediate=False):
        self.invalidate()
        self._estimate = estimate
        if self.actions._closed or self.panel.history.active or self.panel.methods.currentIndex() != 0:
            return
        self.panel.signalPlot.clear()
        self.panel.residualPlot.clear()
        self.panel._previewRange = None
        self.panel.draftLabel.setText("Current draft — initial preview; no fitted result published")
        self.panel.summary.setPlainText("Current draft — no fitted result published. Inspect the initial preview; use Latest applied result / Last saved result to review recorded results.")
        self.panel._viewingDiskSaved = False
        self.panel.conversionActions.hide()
        self.panel.resultLabel.setText("Recorded results: Latest applied result or Last saved result.")
        self.panel.jobLabel.setText("Preparing initial preview…")
        self.panel.contextLabel.setText(f"{self.panel.quantityChoice.currentText()} · checking the current source and interval…")
        if immediate:
            self.panel.feedbackRequested.emit()
        self.describe()
        self._debounce.start(0 if immediate else 250)

    def describe(self):
        self.panel.showFormula(self.panel.editor.text(), tuple(
            (self.panel.parameterTable.item(row, 0).text(), self.panel.parameterTable.item(row, 1).text())
            for row in range(self.panel.parameterTable.rowCount())))

    def launch(self):
        self._debounce.stop()
        if self.actions._closed:
            return
        if self.actions.pending or self.actions.window.projectActions.busy:
            self._debounce.start(250)
            return
        try:
            if self.actions.ensureSignalSource():
                return
            job = self.actions._prepareSignal(True)
        except Exception as error:
            # 准备错误必须当前可见；不让旧曲线冒充新草稿。
            self.panel.jobLabel.setText(f"Preview unavailable: {error}. Use preparation actions below or edit the formula / values.")
            return
        self._job = job
        self._generation = self.actions.window.deliveryGeneration
        self._request_revision = self._revision
        try:
            self._cancel = Event()
            self._future = self._executor.submit(_preview, job, self._estimate, self._cancel)
            self._pollTimer.start(30)
        except Exception as error:
            self._future = None
            self.panel.jobLabel.setText(f"Preview could not start: {error}. Edit values or retry Preview.")

    def poll(self):
        if self._future is None or not self._future.done() or self.actions.window.projectActions.busy:
            return
        future, self._future = self._future, None
        self._pollTimer.stop()
        if self.actions.pending or self.actions._closed or self._request_revision != self._revision:
            return
        try:
            if self._generation != self.actions.window.deliveryGeneration or self.actions._prepareSignal(True) != self._job:
                self.panel.jobLabel.setText("Preview discarded because its source / result changed. Preview again to use the current data.")
                return
            spec, suggestion, prediction = future.result()
            if suggestion is not None:
                if suggestion.values:
                    self.panel.setEstimatedValues(spec, suggestion.reason)
                else:
                    self.panel.estimateLabel.setText(suggestion.reason)
            self.describe()
            job = replace(self._job, spec=spec)
            values = np.array([row[3] for row in job.samples])
            self.panel.renderSamples(job.samples, job.source.unit, prediction, values-prediction,
                                     wrapped=job.source.kind == "angular_position")
            self.panel.draftLabel.setText("Initial preview — current editable values; not a fitted result")
            if suggestion is not None:
                preparation = suggestion.reason
            elif self.panel.initialProtected:
                preparation = "Manual / restored values are protected; use Estimate to replace free initial values."
            else:
                preparation = "Current initial values are shown above the chart."
            if np.min(prediction) < np.min(values) or np.max(prediction) > np.max(values):
                preparation += " Initial model extends outside the measured range; use Show whole model above the chart to see it."
            self.panel.jobLabel.setText("Initial curve only — no fitted result published. Click Fit to calculate.\n" + preparation)
            self.panel.contextLabel.setText(f"{job.selection.quantity} [{job.source.unit}] · {len(job.samples)} actual samples · "
                                            f"frames {job.selection.start_frame}–{job.selection.end_frame} · "
                                            f"{job.source.kind} · t = 0 at interval start"
                                            + (" · Approximate timing" if self.actions.window.analysisSession.measurement_timing_detail(job.inputs.video.video_id) else ""))
        except Exception as error:
            self.panel.signalPlot.clear()
            self.panel.residualPlot.clear()
            self.panel.jobLabel.setText(f"Initial preview failed: {error}. Check the formula domain and initial values.")

    def shutdown(self):
        """失效所有交付并取消排队工作；原生计算仅协作停止。"""
        self.invalidate()
        self._executor.shutdown(wait=False, cancel_futures=True)
