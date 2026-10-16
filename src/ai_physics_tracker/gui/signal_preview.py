"""GUI层：合并草稿预览请求，后台纯计算，主线程核对身份后显示。"""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor, CancelledError
from threading import Event

import numpy as np
from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.domain.fit_initial import estimate_initial, adopt_estimate


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

    def request(self, *, estimate=False, immediate=False):
        self.invalidate()
        self._estimate = estimate
        if self.actions._closed or self.panel.methods.currentIndex() != 0:
            return
        self.panel.signalPlot.clear()
        self.panel.residualPlot.clear()
        self.panel._previewRange = None
        self.panel.draftLabel.setText("Current draft — initial preview; no fitted result published")
        self.panel.summary.setPlainText("Current draft — no fitted result published. Inspect the initial preview; use Latest applied result / Previous saved result to review recorded results.")
        self.panel._viewingDiskSaved = False
        self.panel.conversionActions.hide()
        self.panel.resultLabel.setText("Recorded results: Latest applied result or Previous saved result.")
        self.panel.jobLabel.setText("Preparing initial preview…")
        self.describe()
        self._debounce.start(0 if immediate else 250)

    def describe(self):
        expression = self.panel.editor.expression()
        if expression is None:
            self.panel.meaningLabel.setText(self.panel.editor.errorLabel.text())
            return
        quantity = self.panel.quantityChoice.currentText()
        names = ", ".join(expression.parameter_names) or "none"
        text = f"Target: {quantity}(t). t is seconds from interval start. Parameters: {names}. "
        if not expression.uses_time:
            text += "Fits a constant level; no time variation is modeled. Symbols such as theta on the right are parameters, not another data column."
        else:
            text += "Inspect the orange initial curve, then Fit to adjust the free parameters."
        self.panel.meaningLabel.setText(text)

    def launch(self):
        if self.actions._closed:
            return
        if self.actions.pending or self.actions.window.projectActions.busy:
            self._debounce.start(250)
            return
        try:
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
            job = replace(self._job, spec=spec)
            values = np.array([row[3] for row in job.samples])
            self.panel.renderSamples(job.samples, job.source.unit, prediction, values-prediction,
                                     wrapped=job.source.kind == "angular_position")
            self.panel.draftLabel.setText("Initial preview — current editable values; not a fitted result")
            self.panel.jobLabel.setText("Initial curve only — no fitted result published. Click Fit to calculate.")
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
