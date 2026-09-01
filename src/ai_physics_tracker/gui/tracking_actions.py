"""GUI 跟踪编排：轻量消息轮询、后台候选合并和异步取消。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QTimer, Qt

from ai_physics_tracker.application.tracking_job import (
    prepare_tracking_request, run_tracking_worker, prepare_tracking_candidate,
    cancel_tracking_job, read_task_log, verify_request_files, TrackingJobRunner,
)
from ai_physics_tracker.domain.tracking_run import mark_run_running, mark_run_failed, mark_run_cancelled
from ai_physics_tracker.application.tracking_types import TaskProgress, TaskLog, TaskResult
from ai_physics_tracker.gui.task_panel import TaskPanel

if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


class TrackingActions(QObject):
    """活动会话只在 GUI 线程修改；worker 仅拥有冻结请求与候选。"""

    def __init__(self, window: "MainWindow", adapter=None, runner=None) -> None:
        super().__init__(window)
        self.window = window
        self.backend = TrackingJobRunner(adapter, runner)
        self.panel = TaskPanel(window)
        window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.panel)
        window.tabifyDockWidget(window.chartActions.panel, self.panel)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tracking-result")
        self._request = None
        self._session = None
        self._handle = None
        self._start_future = None
        self._future = None
        self._result_path = None
        self._cancelling = False
        self._failure_error = None
        self._recovering_model = False
        self._after_cancel: list[Callable] = []
        self._closed = False
        self._context_key = None
        self._log_future = None
        self._log_run_id = None
        self._generation = -1
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self.panel.trainRequested.connect(self.train)
        self.panel.inferRequested.connect(self.infer)
        self.panel.cancelRequested.connect(self.cancel)
        self.panel.runSelected.connect(self.showLog)
        window.projectChanged.connect(self.resetContext)
        window.selectedTrackChanged.connect(self.refresh)
        window.analysisChanged.connect(self.refresh)
        window.closing.connect(self.shutdown)
        self._timer.start()
        self.refresh()

    @property
    def runner(self):
        return self.backend.runner

    @runner.setter
    def runner(self, value):
        self.backend.runner = value

    @property
    def adapter(self):
        return self.backend.adapter

    @adapter.setter
    def adapter(self, value):
        self.backend.adapter = value

    @property
    def pending(self) -> bool:
        return self._request is not None

    @property
    def activeTrackId(self):
        return self._request.run.track_id if self._request else None

    @property
    def cancelling(self) -> bool:
        return self._cancelling or self._recovering_model

    def refresh(self, *_args) -> None:
        if self._closed:
            return
        session = self.window.analysisSession
        video_id, track_id = self.window.activeVideoId, self.window.selectedTrackId
        key = (id(session.project) if session else None, video_id, track_id, self.pending,
               session.can_measure(video_id) if session and video_id else False)
        if key == self._context_key:
            return
        self._context_key = key
        runs = session.tracking_runs() if session else ()
        track = next((t for t in session.tracks if t.track_id == track_id), None) if session else None
        video = next((v for v in session.project.videos if v.video_id == video_id), None) if session else None
        reason = None
        if session is None or track is None:
            reason = "Select a current track"
        elif session.project_root is None:
            reason = "Save the project first"
        elif not session.can_measure(video_id):
            reason = "Video timing is not authorized"
        elif self.pending or any(run.status in {"pending", "running"} for run in runs):
            reason = "An AI task is active"
        train_reason = reason
        if not train_reason and len(session.manual_points(track_id)) < 3:
            train_reason = "Mark at least 3 frames; cover different target positions"
        infer_reason = reason
        if not infer_reason and not any(run.track_id == track_id and run.task_type == "train"
                and run.status == "completed" and run.model_snapshot for run in runs):
            infer_reason = "Train a model for this track first"
        self.panel.setRuns(runs, track_id)
        self.panel.setContext(video.display_name if video else "No video", track.name if track else "No track",
                              train_reason, infer_reason, self.pending)
        self.window.projectActions.refresh()

    def train(self) -> None:
        self._start(self.panel.trainingParameters())

    def infer(self) -> None:
        self._start(self.panel.inferenceParameters(), self.panel.selectedTrainingRunId())

    def _start(self, parameters, training_run_id=None) -> None:
        if self.pending or self.window.projectActions.busy:
            return
        session = self.window.analysisSession
        try:
            request = prepare_tracking_request(session, self.window.selectedTrackId, parameters, training_run_id)
            run = replace(request.run, extra_fields={"log_path": f"data/engines/{request.run.run_id}.log"})
            request = replace(request, run=run)
            session.record_tracking_run(run)
            self._request, self._session = request, session
            self._generation = self.window.deliveryGeneration
            self._log_run_id = run.run_id
            self.panel.setLog("")
            self.panel.setActivity("Preparing")
            self._start_future = self._executor.submit(self.backend.start, request)
        except Exception as error:
            if self._request is not None:
                self._fail(str(error))
            else:
                self.panel.setActivity(f"Cannot start: {error}")
        self.refresh()

    def _context_matches(self) -> bool:
        request = self._request
        return (request is not None and self.window.analysisSession is self._session
                and self.window.deliveryGeneration == self._generation
                and self.window.activeVideoId == request.run.video_id
                and self._session.project_root == request.project_root
                and self._session.can_measure(request.run.video_id)
                and self._session.measurement_timing_detail(request.run.video_id) == request.timing_detail
                and any(t.track_id == request.run.track_id and t.video_id == request.run.video_id
                        for t in self._session.tracks)
                and next((v for v in self._session.project.videos if v.video_id == request.run.video_id), None)
                    == next((v for v in request.project.videos if v.video_id == request.run.video_id), None)
                and next((t for t in self._session.project.timelines if t.video_id == request.run.video_id), None)
                    == next((t for t in request.project.timelines if t.video_id == request.run.video_id), None))

    def _poll(self) -> None:
        if self._closed:
            return
        self.refresh()
        if self._log_future is not None and self._log_future[2].done():
            session, run_id, future = self._log_future
            self._log_future = None
            if session is self.window.analysisSession and run_id == self._log_run_id:
                try:
                    self.panel.setLog(future.result())
                except Exception as error:
                    self.panel.setLog(f"Cannot read log: {error}")
        if not self.pending:
            return
        if self._start_future is not None:
            if not self._start_future.done():
                return
            try:
                self._handle = self._start_future.result()
                self._start_future = None
                run = next(r for r in self._session.tracking_runs() if r.run_id == self._request.run.run_id)
                if run.status == "pending" and not self._cancelling:
                    self._session.update_tracking_run(mark_run_running(run))
            except Exception as error:
                self._fail(str(error))
                return
        if not self._context_matches() and not self._cancelling:
            if self._recovering_model:
                self._fail("Project context changed before the trained model could be recorded")
                return
            self.cancel()
        if self._cancelling:
            self._poll_cancel()
            return
        messages = [] if self._recovering_model else self._handle.poll_messages(limit=200)
        if not self._handle.is_alive() and not self._recovering_model:
            messages.extend(self._handle.poll_messages(limit=200))
        for message in messages:
            if message.run_id != self._request.run.run_id:
                continue
            if isinstance(message, TaskProgress):
                self.panel.setActivity("Training" if self._request.run.task_type == "train" else "Inference",
                    message.step, message.total_steps, message.loss, message.learning_rate)
            elif isinstance(message, TaskLog):
                if self._log_run_id == message.run_id:
                    self.panel.appendLog(message.message)
            elif isinstance(message, TaskResult):
                payload = message.payload or {}
                if payload.get("status") == "model_ready":
                    self.panel.setActivity("Evaluating model")
                elif message.success and payload.get("status") == "completed" and payload.get("result_path"):
                    self._result_path = self._request.project_root / payload["result_path"]
                elif payload.get("status") == "cancelled":
                    self.cancel()
                    return
                else:
                    self._fail(message.error or "AI task failed")
                    return
        if self._result_path is not None and self._future is None:
            self._prepare_candidate()
        if self._future is not None and self._future.done() and not self._handle.is_alive():
            if self.window.projectActions.busy:
                return
            try:
                candidate = self._future.result()
                self._future = None
                verify_request_files(self._request)
                if not self._context_matches():
                    self.cancel()
                elif not self._session.apply_tracking_candidate(candidate):
                    self._prepare_candidate()
                else:
                    self._finish("Completed")
            except Exception as error:
                self._fail(str(error))
        elif not self._handle.is_alive() and not messages and self._future is None and self._result_path is None:
            self._fail(f"Task exited without a result (exitcode={self._handle.exitcode})")

    def _prepare_candidate(self) -> None:
        self.panel.setActivity("Validating and importing")
        self._future = self._executor.submit(prepare_tracking_candidate, self._session.project,
                                            self._request, self._result_path)

    def _fail(self, error: str) -> None:
        if self._request is None:
            return
        run = next((r for r in self._session.tracking_runs() if r.run_id == self._request.run.run_id), None)
        if run and run.status in {"pending", "running"}:
            self._session.update_tracking_run(mark_run_failed(run, error))
        self.panel.appendLog(error)
        if self._handle is not None and self._handle.is_alive():
            self._failure_error = error
            self._cancelling = True
            self.panel.setActivity("Stopping failed task")
            self._future = self._executor.submit(cancel_tracking_job, self._handle, self._request)
            return
        self._finish(f"Failed: {error}")

    def cancel(self, after: Callable | None = None) -> None:
        if not self.pending:
            if after:
                after()
            return
        if after:
            self._after_cancel.append(after)
        if self.cancelling:
            return
        self._cancelling = True
        self.panel.setActivity("Cancelling")
        if self._handle is None:
            start = self._start_future
            request = self._request
            self._future = self._executor.submit(lambda: cancel_tracking_job(start.result(), request))
        else:
            self._future = self._executor.submit(cancel_tracking_job, self._handle, self._request)

    def _poll_cancel(self) -> None:
        if not self._future.done():
            return
        try:
            path = self._future.result()
            if path is not None and self._context_matches() and self._failure_error is None:
                self._cancelling = False
                self._recovering_model = True
                self._future = None
                self._result_path = path
                self._prepare_candidate()
                return
        except Exception as error:
            self.panel.appendLog(str(error))
        run = next((r for r in self._session.tracking_runs() if r.run_id == self._request.run.run_id), None)
        if run and run.status in {"pending", "running"}:
            self._session.update_tracking_run(mark_run_cancelled(run))
        self._finish(f"Failed: {self._failure_error}" if self._failure_error else "Cancelled")

    def _finish(self, message: str) -> None:
        session = self._session
        finished = next((run for run in session.tracking_runs() if run.run_id == self._request.run.run_id), None)
        if finished is not None and self.window.analysisSession is session:
            self.panel.setRunDetails(finished)
        self._handle = self._request = self._future = self._result_path = self._start_future = None
        self._cancelling = False
        self._failure_error = None
        self._recovering_model = False
        self._session = None
        self.panel.setActivity(message)
        if self.window.analysisSession is session:
            self.window._refreshMarkers()
            self.window._refreshHistoryButtons()
            self.window.analysisChanged.emit()
            if message == "Completed":
                self.window.statusBar().showMessage("AI task completed. Recompute charts to use updated observations.")
        self._context_key = None
        self.refresh()
        callbacks, self._after_cancel = self._after_cancel, []
        for callback in callbacks:
            callback()

    def showLog(self, run_id) -> None:
        session = self.window.analysisSession
        if session is None or session.project_root is None:
            return
        run = next((run for run in session.tracking_runs() if run.run_id == run_id), None)
        if run:
            self.panel.setRunDetails(run)
            self._log_run_id = run_id
            self._log_future = (session, run_id, self._executor.submit(read_task_log, session.project_root, run))

    def resetContext(self) -> None:
        if self.pending and not self._context_matches():
            self.cancel()
        self._log_future = None
        self._log_run_id = None
        self._context_key = None
        self.panel.setLog("")
        self.panel.detailsLabel.setText("Select a task to view its result details.")
        self.refresh()

    def shutdown(self) -> None:
        self._closed = True
        self._timer.stop()
        if self._handle is not None:
            self._executor.submit(cancel_tracking_job, self._handle, self._request)
        elif self._start_future is not None:
            start, request = self._start_future, self._request
            self._executor.submit(lambda: cancel_tracking_job(start.result(), request))
        self._executor.shutdown(wait=False, cancel_futures=False)
