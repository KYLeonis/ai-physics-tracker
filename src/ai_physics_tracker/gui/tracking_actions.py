"""GUI 跟踪编排：轻量消息轮询、后台候选合并和异步取消。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from uuid import UUID

import logging

from PySide6.QtCore import QObject, QTimer, Qt

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import QMessageBox

from ai_physics_tracker.application.tracking_job import (
    prepare_tracking_request, run_tracking_worker, prepare_tracking_candidate,
    cancel_tracking_job, read_task_log, verify_request_files, TrackingJobRunner,
    prepare_frame_selection_request, run_frame_selection_worker,
    read_frame_selection_result, FrameSelectionRunner, FrameSelectionJobRequest,
)
from ai_physics_tracker.application.refinement_history import extract_refinement_state
from ai_physics_tracker.application.training_advisor import (
    OOM_MARKERS, AdvisorInput, RoundMetrics, recommend_training_action)
from ai_physics_tracker.domain.tracking_run import mark_run_running, mark_run_failed, mark_run_cancelled
from ai_physics_tracker.application.tracking_types import TaskProgress, TaskLog, TaskResult
from ai_physics_tracker.gui.task_panel import TaskPanel


def _evaluation_rmse(evaluation: dict) -> tuple[float, float, str, str] | None:
    """从 train run 的 evaluation 提取 (train, validation) RMSE 与名称/单位。

    兼容两种形态：DLC 原生 {train: {metrics: {...}}, test: {...}} 与
    Mock 的 {metrics: {train_rmse, test_rmse}, unit}；无共同指标返回 None。
    """
    if not isinstance(evaluation, dict):
        return None
    unit = "px"
    if isinstance(evaluation.get("metrics"), dict):
        metrics = evaluation["metrics"]
        if isinstance(metrics.get("train_rmse"), (int, float)) and                 isinstance(metrics.get("test_rmse"), (int, float)):
            unit = str(evaluation.get("unit", "px"))
            return float(metrics["train_rmse"]), float(metrics["test_rmse"]), "rmse", unit
        return None
    train_block = evaluation.get("train")
    test_block = evaluation.get("test")
    if not (isinstance(train_block, dict) and isinstance(test_block, dict)):
        return None
    train_metrics = train_block.get("metrics")
    test_metrics = test_block.get("metrics")
    if not (isinstance(train_metrics, dict) and isinstance(test_metrics, dict)):
        return None
    common = set(train_metrics) & set(test_metrics)
    preferred = [name for name in sorted(common) if "rmse" in name.lower()]
    if not preferred:
        return None
    name = preferred[0]
    train_value, test_value = train_metrics[name], test_metrics[name]
    if not (isinstance(train_value, (int, float)) and isinstance(test_value, (int, float))):
        return None
    units = evaluation.get("units")
    if isinstance(units, dict):
        unit = str((train_block.get("units") or {}).get(name, "px"))
    return float(train_value), float(test_value), name, unit

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
        self.panel.activateRunRequested.connect(self.activateRun)
        self.panel.replaceRunRequested.connect(self.replaceRun)
        self.panel.clearActivationRequested.connect(self.clearActivation)
        self.panel.manageValidationRequested.connect(self.manageValidation)
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
        elif hasattr(self.window, "frameSelectionActions") and self.window.frameSelectionActions.busy:
            reason = "Frame selection is running"
        elif hasattr(self.window, "reviewActions") and self.window.reviewActions.busy:
            reason = "Difficult frame mining is running"
        train_reason = reason
        if not train_reason and len(session.manual_points(track_id)) < 3:
            train_reason = "Mark at least 3 frames; cover different target positions"
        infer_reason = reason
        if not infer_reason and not any(run.track_id == track_id and run.task_type == "train"
                and run.status == "completed" and run.model_snapshot for run in runs):
            infer_reason = "Train a model for this track first"
        active_status, active_run_id, _ = (
            session.get_track_activation_status(track_id)
            if (session and track_id)
            else ("none", None, None)
        )
        ref_state = (
            session.get_refinement_state(track_id)
            if (session and track_id)
            else None
        )
        val_valid, val_reason = (
            session.validate_active_validation_series(track_id)
            if (session and track_id)
            else (False, None)
        )
        self.panel.setRefinementInfo(
            active_status=active_status,
            active_run_id=active_run_id,
            ref_state=ref_state,
            validation_valid=val_valid,
            validation_reason=val_reason,
        )
        # 项目级 historyList 需要知道每个 track 的 active run 才能正确标注
        # "Active (other track)"（review F-4）
        active_by_track: dict = {}
        if session:
            active_by_track = {
                t.track_id: extract_refinement_state(t).active_infer_run_id
                for t in session.tracks
                if extract_refinement_state(t).active_infer_run_id is not None
            }
        self.panel.setRuns(runs, track_id, active_run_ids_by_track=active_by_track)
        self.panel.setContext(video.display_name if video else "No video", track.name if track else "No track",
                              train_reason, infer_reason, self.pending,
                              project_busy=self.window.projectActions.busy)
        if session and track_id:
            self.panel.setAdvisorSummary(self._advisor_recommendation(session, track_id, runs))
        else:
            self.panel.setAdvisorSummary(None)
        self.window.projectActions.refresh()

    def train(self) -> None:
        self._start(self.panel.trainingParameters(),
                    training_mode=self.panel.trainingMode(),
                    resume_from_run_id=self.panel.selectedTrainingRunId())

    def infer(self) -> None:
        self._start(self.panel.inferenceParameters(), self.panel.selectedTrainingRunId())

    def _advisor_recommendation(self, session, track_id, runs):
        """从活动会话采集不可变快照并计算 Advisor 建议（纯计算，不落盘）。"""
        from concurrent.futures import CancelledError  # noqa: F401 (保持导入面一致)
        try:
            return recommend_training_action(self._build_advisor_input(session, track_id, runs))
        except Exception as error:  # Advisor 属辅助信息，采集失败不阻塞面板
            logger.warning("advisor input failed: %s", error)
            return None

    def _build_advisor_input(self, session, track_id, runs) -> AdvisorInput:
        timeline = next((t for t in session.project.timelines if t.video_id == track_id), None)
        completed_train = [r for r in runs
                           if r.track_id == track_id and r.task_type == "train"
                           and r.status == "completed"]
        failed_train = [r for r in runs
                        if r.track_id == track_id and r.task_type == "train"
                        and r.status == "failed"]
        last_failed = failed_train[-1] if failed_train else None
        last_failure_oom = False
        if last_failed is not None:
            error_text = str(last_failed.error_message or "").lower()
            last_failure_oom = any(marker in error_text for marker in OOM_MARKERS)

        latest_train = completed_train[-1] if completed_train else None
        manual_points = [p for p in session.manual_points(track_id)]
        new_labels = 0
        if latest_train is not None and latest_train.completed_at is not None:
            new_labels = sum(
                1 for p in manual_points if p.modified_at > latest_train.completed_at)

        recent_rounds: list[RoundMetrics] = []
        for train_run in completed_train:
            evaluation = train_run.extra_fields.get("evaluation")
            iteration = train_run.extra_fields.get("refinement_iteration_v1")
            if not isinstance(evaluation, dict) or not isinstance(iteration, dict):
                continue
            metrics_pair = _evaluation_rmse(evaluation)
            if metrics_pair is None:
                continue
            train_rmse, val_rmse, metric_name, unit = metrics_pair
            recent_rounds.append(RoundMetrics(
                training_run_id=str(train_run.run_id),
                validation_series_id=iteration.get("validation_series_id"),
                train_rmse=train_rmse,
                validation_rmse=val_rmse,
                metric_name=metric_name,
                metric_unit=unit,
            ))

        # 审核统计：当前 track 最新 completed infer run 的 review summary
        infer_runs = [r for r in runs
                      if r.track_id == track_id and r.task_type == "infer"
                      and r.status == "completed"]
        pending_candidates = 0
        correction_yield = None
        if infer_runs:
            latest_infer = infer_runs[-1]
            try:
                rev_sum = session.get_review_summary(latest_infer.run_id)
            except Exception:
                rev_sum = None
            if rev_sum is not None:
                pending_candidates = rev_sum.pending_count
                if rev_sum.total_reviewed > 0:
                    correction_yield = rev_sum.corrected_count / rev_sum.total_reviewed

        has_compatible_source = any(
            r.model_snapshot and (session.project_root / r.model_snapshot).is_file()
            for r in completed_train
        ) if session.project_root is not None else False

        uncovered = False
        if timeline is not None and manual_points:
            zone_start, zone_end = timeline.working_zone
            span = max(zone_end - zone_start, 1)
            quarter_size = span / 4
            covered = set()
            for p in manual_points:
                covered.add(min(int((p.frame_index - zone_start) / quarter_size), 3))
            uncovered = len(covered) < 4

        _ = track_id  # 已由 runs 过滤；保留参数签名稳定
        return AdvisorInput(
            has_active_task=self.pending,
            artifacts_missing=False,
            validation_valid=session.validate_active_validation_series(track_id)[0]
            if session.get_refinement_state(track_id).active_series is not None else True,
            validation_invalid_reason=session.validate_active_validation_series(track_id)[1]
            if session.get_refinement_state(track_id).active_series is not None else None,
            last_train_failed=last_failed is not None,
            last_failure_is_oom=last_failure_oom,
            pending_candidates=pending_candidates,
            completed_train_runs=len(completed_train),
            new_labels_since_last_train=new_labels,
            has_compatible_source=has_compatible_source,
            recent_rounds=tuple(recent_rounds),
            correction_yield=correction_yield,
            uncovered_zone_segments=uncovered,
            requested_batch_size=self.panel.batchSizeSpinBox.value(),
            requested_epochs=self.panel.epochsSpinBox.value(),
        )

    def _interaction_blocked(self) -> bool:
        """激活/验证集操作的统一互斥口径，与 refresh() 的禁用原因对齐（review F-5）。"""
        return bool(
            self.pending
            or self.window.projectActions.busy
            or self.window.frameSelectionActions.busy
            or (hasattr(self.window, "reviewActions") and self.window.reviewActions.busy)
        )

    def activateRun(self, run_id: UUID) -> None:
        if self._interaction_blocked():
            return
        session = self.window.analysisSession
        track_id = self.window.selectedTrackId
        if not session or not track_id:
            return
        track = next((t for t in session.tracks if t.track_id == track_id), None)
        track_name = track.name if track else "selected track"
        manual_count = len(session.manual_points(track_id))
        reply = QMessageBox.question(
            self.window,
            "Activate Tracking Result",
            f"Activate AI tracking result from run {str(run_id)[:8]} on track '{track_name}'?\n\n"
            f"{manual_count} manual point(s) will take precedence and be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            rec = session.activate_infer_run(track_id, run_id)
            self.window.statusBar().showMessage(
                f"Activated run {str(run_id)[:8]}: {rec.point_count} active points, "
                f"{rec.superseded_count} superseded by manual"
            )
            self.window._refreshMarkers()
            self.window._refreshHistoryButtons()
        except Exception as error:
            QMessageBox.critical(self.window, "Activation Failed", str(error))
        self._context_key = None
        self.refresh()

    def _replace_dialog_text(self, session, track_id: UUID, run_id: UUID) -> str:
        """替换确认的 from/to run 与影响面统计（plan AC 第 5 条，review F-1）。"""
        track = next((t for t in session.tracks if t.track_id == track_id), None)
        track_name = track.name if track else "selected track"
        status, active_run_id, _ = session.get_track_activation_status(track_id)
        from_part = f"run {str(active_run_id)[:8]}" if active_run_id else f"current result ({status})"
        manual_count = len(session.manual_points(track_id))
        target_run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
        target_count = None
        if target_run is not None:
            summary = target_run.extra_fields.get("prediction_summary_v1")
            if isinstance(summary, dict):
                target_count = summary.get("eligible_count")
        counts = f"{manual_count} manual point(s) will remain preserved"
        if target_count is not None:
            counts += f"; about {target_count} prediction point(s) will be loaded"
        return (
            f"Replace {from_part} with run {str(run_id)[:8]} on track '{track_name}'?\n\n"
            f"All previous AI observations for this track will be replaced. {counts}."
        )

    def replaceRun(self, run_id: UUID) -> None:
        if self._interaction_blocked():
            return
        session = self.window.analysisSession
        track_id = self.window.selectedTrackId
        if not session or not track_id:
            return
        reply = QMessageBox.question(
            self.window,
            "Replace Active Tracking Result",
            self._replace_dialog_text(session, track_id, run_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            rec = session.replace_active_infer_run(track_id, run_id)
            self.window.statusBar().showMessage(
                f"Replaced active run with {str(run_id)[:8]}: {rec.point_count} active points, "
                f"{rec.superseded_count} superseded by manual"
            )
            self.window._refreshMarkers()
            self.window._refreshHistoryButtons()
        except Exception as error:
            QMessageBox.critical(self.window, "Replacement Failed", str(error))
        self._context_key = None
        self.refresh()

    def clearActivation(self) -> None:
        if self._interaction_blocked():
            return
        session = self.window.analysisSession
        track_id = self.window.selectedTrackId
        if not session or not track_id:
            return
        track = next((t for t in session.tracks if t.track_id == track_id), None)
        track_name = track.name if track else "selected track"
        ai_count = len([
            p for p in session.project.observations
            if p.track_id == track_id and p.source != "manual" and p.status == "active"
        ])
        manual_count = len(session.manual_points(track_id))
        reply = QMessageBox.question(
            self.window,
            "Clear Active AI Result",
            f"Clear all active AI tracking observations for track '{track_name}'?\n\n"
            f"{ai_count} AI point(s) will be removed; {manual_count} manual point(s) will NOT be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            rec = session.clear_active_ai_observations(track_id)
            self.window.statusBar().showMessage(
                f"Cleared active AI observations on track '{track_name}'"
            )
            self.window._refreshMarkers()
            self.window._refreshHistoryButtons()
        except Exception as error:
            QMessageBox.critical(self.window, "Clear Failed", str(error))
        self._context_key = None
        self.refresh()

    def manageValidation(self) -> None:
        if self._interaction_blocked():
            return
        from ai_physics_tracker.gui.validation_dialog import ManageValidationDialog

        session = self.window.analysisSession
        track_id = self.window.selectedTrackId
        if not session or not track_id:
            return
        dialog = ManageValidationDialog(session, track_id, self.window)
        dialog.exec()
        self.window._refreshHistoryButtons()
        self._context_key = None
        self.refresh()

    def _start(self, parameters, training_run_id=None,
               training_mode: str = "restart", resume_from_run_id: UUID | None = None) -> None:
        if self.pending or self.window.projectActions.busy:
            return
        if self.window.frameSelectionActions.busy:
            self.panel.setActivity("Cannot start: frame selection is running")
            return
        if hasattr(self.window, "reviewActions") and self.window.reviewActions.busy:
            self.panel.setActivity("Cannot start: difficult frame mining is running")
            return
        session = self.window.analysisSession
        try:
            request = prepare_tracking_request(
                session, self.window.selectedTrackId, parameters, training_run_id,
                training_mode=training_mode, resume_from_training_run_id=resume_from_run_id)
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
        if message == "Completed" and self.window.analysisSession is session:
            # 训练/推理结果已提交：落盘一次，防止未手存丢失（用户实测需求）
            self.window.projectActions.autosave("AI task completed")
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


# ---------------------------------------------------------------------------
# Phase 5.1 — 代表帧选取 GUI 编排
# ---------------------------------------------------------------------------

from uuid import uuid4 as _uuid4
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor


class FrameSelectionActions(QObject):
    """管理 Task Panel 中代表帧选取请求、后台任务和结果展示（Phase 5.1）。

    遵循与 TrackingActions 相同的设计规则：
    - GUI 线程只修改活动会话；worker 只持有冻结快照。
    - 结果通过 _poll_timer 轮询，不在 worker 线程触碰 Qt 对象。
    - 建议帧不创建 TrackPoint；双击列表项通知 MainWindow 跳帧。
    """

    def __init__(
        self,
        window: "MainWindow",
        panel: TaskPanel,
        adapter=None,
        runner=None,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.panel = panel
        self._backend = FrameSelectionRunner(adapter, runner)
        self._executor = _ThreadPoolExecutor(max_workers=1, thread_name_prefix="frame-sel")
        self._request_id = None
        self._job_request: FrameSelectionJobRequest | None = None
        self._handle = None
        self._start_future = None
        self._result_future = None
        self._closed = False
        # 结果/运行中任务所属的 track：Track 列表对同一 track 的重复点击会重发
        # selectedTrackChanged，只有真正切换 track/project 才取消或清空；
        # 结果按 track 缓存，取消选择/切走后重新选中同一 track 时恢复显示
        self._running_track_id = None
        self._result_track_id = None
        self._cached_result = None
        self._cached_status = ""

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        self.panel.suggestFramesRequested.connect(self.requestSuggestion)
        self.panel.suggestCancelRequested.connect(self.cancel)
        self.panel.suggestedFrameJumped.connect(self._onFrameJumped)
        window.selectedTrackChanged.connect(self._onSelectedTrackChanged)
        window.projectChanged.connect(self._onProjectChanged)
        window.analysisChanged.connect(self._onAnalysisChanged)
        window.closing.connect(self.shutdown)

        self._refreshEnabled()

    @property
    def adapter(self):
        return self._backend.adapter

    @adapter.setter
    def adapter(self, value):
        self._backend.adapter = value

    @property
    def runner(self):
        return self._backend.runner

    @runner.setter
    def runner(self, value):
        self._backend.runner = value

    @property
    def busy(self) -> bool:
        return self._request_id is not None

    def requestSuggestion(self, n_frames: int, algorithm: str) -> None:
        """用户点击"建议帧"时触发，发起后台选帧任务（Phase 5.1）。"""
        if (
            self.busy
            or self._closed
            or self.window.trackingActions.pending
            or self.window.projectActions.busy
            or (hasattr(self.window, "reviewActions") and self.window.reviewActions.busy)
        ):
            return
        session = self.window.analysisSession
        track_id = self.window.selectedTrackId
        if session is None or track_id is None:
            self.panel.setSuggestStatus("No track selected")
            return
        try:
            job_request = prepare_frame_selection_request(
                session, track_id, n_frames, algorithm=algorithm
            )
        except Exception as error:
            self.panel.setSuggestStatus(f"Cannot start: {error}")
            return

        request_id = _uuid4()
        self._request_id = request_id
        self._job_request = job_request
        self._running_track_id = track_id
        self._result_track_id = None
        self._cached_result = None
        self._cached_status = ""
        self.panel.setSuggestResult(None)
        self.panel.setSuggestStatus("Working…")
        self.panel.setSuggestEnabled(False, "Frame selection running")
        self._start_future = self._executor.submit(self._backend.start, job_request, request_id)

    def _poll(self) -> None:
        if self._closed or not self.busy:
            return
        # 等待 start_future 完成以获取 handle
        if self._start_future is not None:
            if not self._start_future.done():
                return
            try:
                self._handle = self._start_future.result()
                self._start_future = None
            except Exception as error:
                self._finish_error(str(error))
                return

        if self._handle is None:
            return

        # 消费消息并更新进度或捕获取消与错误
        messages = self._handle.poll_messages(limit=200)
        for message in messages:
            if isinstance(message, TaskProgress):
                if message.message:
                    self.panel.setSuggestStatus(message.message)
                elif message.total_steps > 0:
                    pct = int(100 * message.step / message.total_steps)
                    self.panel.setSuggestStatus(f"Working… {pct}%")
            elif isinstance(message, TaskResult):
                payload = message.payload or {}
                if payload.get("status") == "cancelled":
                    self._finish_cancelled("Frame selection cancelled")
                    return
                elif not message.success:
                    self._finish_error(message.error or "Frame selection failed")
                    return

        # 检查后台进程是否结束
        if not self._handle.is_alive():
            if self._result_future is None:
                request_id = self._request_id
                project_root = self._job_request.project_root if self._job_request else None
                if project_root is not None:
                    self._result_future = self._executor.submit(
                        read_frame_selection_result, project_root, request_id
                    )
        if self._result_future is not None and self._result_future.done():
            try:
                result = self._result_future.result()
                self._finish_success(result)
            except Exception as error:
                self._finish_error(str(error))

    def _finish_success(self, result) -> None:
        self.panel.setSuggestResult(result)
        self._result_track_id = self._running_track_id
        self._cached_result = result
        self._cached_status = self.panel.suggestStatusLabel.text()
        self._reset()
        self._refreshEnabled()

    def cancel(self) -> None:
        """用户点击取消建议帧任务（F4 / AC-9）。"""
        if not self.busy:
            return
        self._cancel_active_task()
        self._finish_cancelled("Frame selection cancelled")

    def _finish_cancelled(self, message: str = "Frame selection cancelled") -> None:
        self.panel.setSuggestStatus(message)
        self._result_track_id = None
        self._cached_result = None
        self._cached_status = ""
        self._reset()
        self._refreshEnabled()

    def _finish_error(self, message: str) -> None:
        self.panel.setSuggestStatus(f"Failed: {message}")
        self._result_track_id = None
        self._cached_result = None
        self._cached_status = ""
        self._reset()
        self._refreshEnabled()

    def _cancel_active_task(self) -> None:
        handle = self._handle
        start = self._start_future
        if handle is not None:
            self._executor.submit(handle.cancel)
        elif start is not None:
            self._executor.submit(lambda: start.result().cancel() if start.done() else None)

    def _reset(self) -> None:
        self._request_id = None
        self._job_request = None
        self._handle = None
        self._start_future = None
        self._result_future = None

    def _onSelectedTrackChanged(self, *_args) -> None:
        """按 track 恢复/隐藏建议帧；同一 track 重复点击不破坏状态，切走再切回可恢复。"""
        current = self.window.selectedTrackId
        if self.busy and current != self._running_track_id:
            self._cancel_active_task()
            self._reset()
        if current == self._result_track_id and self._cached_result is not None:
            self.panel.setSuggestResult(self._cached_result)
            self.panel.setSuggestStatus(self._cached_status)
        else:
            self.panel.setSuggestResult(None)
            self.panel.setSuggestStatus("")
        self._refreshEnabled()

    def _onProjectChanged(self, *_args) -> None:
        """项目切换无条件取消后台任务并清空建议帧结果与缓存。"""
        if self.busy:
            self._cancel_active_task()
            self._reset()
        self._result_track_id = None
        self._cached_result = None
        self._cached_status = ""
        self.panel.setSuggestResult(None)
        self.panel.setSuggestStatus("")
        self._refreshEnabled()

    def _onAnalysisChanged(self, *_args) -> None:
        """项目保存或分析状态更新时刷新按钮可用性。"""
        self._refreshEnabled()

    def _onFrameJumped(self, frame_index: int) -> None:
        """双击建议帧列表项时，通知 MainWindow 跳帧（frame_index 是 0-based）。"""
        self.window.jumpToFrame(frame_index)

    def _refreshEnabled(self) -> None:
        session = self.window.analysisSession
        track_id = self.window.selectedTrackId
        if self.busy:
            self.panel.setSuggestEnabled(False, "Frame selection running")
        elif self.window.trackingActions.pending:
            self.panel.setSuggestEnabled(False, "An AI tracking task is active")
        elif hasattr(self.window, "reviewActions") and self.window.reviewActions.busy:
            self.panel.setSuggestEnabled(False, "Difficult frame mining running")
        elif self.window.projectActions.busy:
            self.panel.setSuggestEnabled(False, "Project operation in progress")
        elif session is None or track_id is None:
            self.panel.setSuggestEnabled(False, "Select a track first")
        elif session.project_root is None:
            # 首次选帧必须先保存项目：tooltip 之外给出可见提示（用户 HR 反馈）
            self.panel.setSuggestEnabled(
                False, "Save the project first — frame selection needs a saved project",
                hint=True)
        else:
            self.panel.setSuggestEnabled(True)

    def shutdown(self) -> None:
        self._closed = True
        self._poll_timer.stop()
        if self.busy:
            self._cancel_active_task()
        self._reset()
        self._executor.shutdown(wait=False, cancel_futures=False)
