"""P1.4-S4 experiment 联合推理/审核/激活的 GUI 控制器(Qt GUI 层)。

执行边界与 ModelActions 相同:prepare/verify/审核/激活是 session 应用
动作(GUI 线程);推理经 external worker 子进程执行,QTimer 轮询句柄。
审核对话框只呈现队列与诊断,写路径全部经本控制器走 session 动作。
Correct 的落点在主窗口视频上点击(对话框非模态保持可见)。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.application.experiment_inference_job import (
    prepare_experiment_inference,
    verify_experiment_inference_result,
)
from ai_physics_tracker.application.model_worker import (
    ModelWorkerError,
    ModelWorkerRunner,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.domain.tracking_run import mark_run_cancelled, mark_run_failed

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 250

# 审核帧 overlay 的固定配色(role 顺序无关,便于与 track 颜色区分)
_REVIEW_PREVIEW_COLORS = {
    "pivot": "#7b61ff",
    "body_top": "#00b8d9",
    "body_bottom": "#36b37e",
    "tip": "#ff5630",
}


class ExperimentInferenceActions(QObject):
    """experiment 四 role 推理、run-scoped 审核与四轨激活的 GUI 控制器。"""

    def __init__(
        self,
        window,
        runtime_python: str | Path | None = None,
        *,
        runner_factory=None,
    ) -> None:
        super().__init__(window)
        import sys

        self.window = window
        self._runtime_python = str(runtime_python or sys.executable)
        # 测试缝:注入假 runner;产品恒为 ModelWorkerRunner(经 application 层)
        self._runner_factory = runner_factory or (
            lambda: ModelWorkerRunner(self._runtime_python)
        )
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._handle: Any = None
        self._run = None
        self._request = None
        self._job_dir: Path | None = None
        self._session: ProjectSession | None = None
        self._user_cancel = False

        # 审核会话态(不持久化;queue/records 本身在 run extras)
        self._dialog = None
        self._review_run_id: UUID | None = None
        self._review_frames: tuple[int, ...] = ()
        self._review_current: int | None = None
        self._correcting_role: str | None = None

        window.projectChanged.connect(self._on_project_changed)
        window.closing.connect(self.shutdown)

        # HR 2026-09-28 同款模式:面板 Cancel 归在途控制器;空闲时 no-op
        tracking_panel = getattr(
            getattr(window, "trackingActions", None), "panel", None)
        if tracking_panel is not None:
            tracking_panel.cancelRequested.connect(self._onCancelRequested)

    def _onCancelRequested(self) -> None:
        if self.busy:
            self.cancel()

    # ------------------------------------------------------------------
    # busy / 查询
    # ------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._handle is not None

    @property
    def review_open(self) -> bool:
        return self._dialog is not None

    @property
    def is_correcting(self) -> bool:
        return self._correcting_role is not None

    def shutdown(self) -> None:
        """窗口关闭:在途 job 取消并回收;审核状态丢弃(queue 已持久化)。"""

        self._timer.stop()
        if self._handle is not None:
            self._handle.cancel()

    def _set_activity(self, text: str, *, running: bool | None = None) -> None:
        tracking = getattr(self.window, "trackingActions", None)
        panel = tracking.panel if tracking is not None else None
        if panel is None:
            return
        panel.setActivity(text)
        panel.cancelButton.setEnabled(
            self.busy if running is None else running)

    def _others_busy(self) -> str | None:
        """互斥检查:返回阻断原因或 None(model/frame/review/project 在途)。"""

        models = getattr(self.window, "modelActions", None)
        if models is not None and models.busy:
            return "A model task is already running"
        tracking = getattr(self.window, "trackingActions", None)
        if tracking is not None and tracking.pending:
            return "Cancel the active AI task first"
        frames = getattr(self.window, "frameSelectionActions", None)
        if frames is not None and frames.busy:
            return "Cancel frame selection first"
        review = getattr(self.window, "reviewActions", None)
        if review is not None and review.busy:
            return "Cancel difficult-frame mining first"
        if self.window.projectActions.busy:
            return "A project task is running"
        return None

    # ------------------------------------------------------------------
    # 联合推理(P1.4-S4a)
    # ------------------------------------------------------------------

    def runJointInference(self, model_id: UUID, params) -> None:
        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            self.window.statusBar().showMessage(
                "Joint inference needs a pendulum experiment on the current video")
            return
        if self.busy:
            return
        blocked = self._others_busy()
        if blocked:
            self.window.statusBar().showMessage(blocked)
            return
        try:
            run, request = prepare_experiment_inference(
                session, experiment.experiment_id, model_id, params,
            )
        except (ProjectSessionError, ValueError) as error:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self.window, "Cannot start joint inference", str(error))
            self.window.statusBar().showMessage(f"Cannot start: {error}")
            return
        try:
            handle = self._runner_factory().start_inference(
                session.project_root, request, device="cpu",
            )
        except (ModelWorkerError, OSError) as error:
            # prepare 已登记 pending run;启动失败必须回写 failed(死端守卫)
            session.update_tracking_run(mark_run_failed(run, str(error)))
            self.window.statusBar().showMessage(f"Cannot start: {error}")
            self.window.projectActions.refresh()
            return
        from ai_physics_tracker.domain.tracking_run import mark_run_running

        session.update_tracking_run(mark_run_running(run))
        self._handle = handle
        self._run = run
        self._request = request
        self._job_dir = session.project_root / "data" / "engines" / str(run.run_id)
        self._session = session
        self._timer.start()
        self._set_activity("Inferring (external worker)")
        self.window.statusBar().showMessage(
            f"Joint inference run {run.run_id} started on cpu "
            "(external worker; logs in the run directory)")
        self.window.projectActions.refresh()

    def cancel(self) -> None:
        """用户取消:必须经 handle.cancel(),迟到 success 才会被拒。"""

        if self._handle is None:
            return
        self._user_cancel = True
        self.window.statusBar().showMessage(
            "Cancelling joint inference (forcing termination may take a few seconds)…")
        self._handle.cancel()

    def _poll(self) -> None:
        handle = self._handle
        if handle is None or handle.is_alive():
            return
        self._timer.stop()
        if self._session is not None and self.window.analysisSession is not self._session:
            logger.warning("joint inference finished after session swap; discarding")
            handle.cancel()
            self._set_activity("Discarded (project changed)", running=False)
            self._reset_job()
            return
        try:
            result = handle.read_result()
        except ModelWorkerError as error:
            if self._user_cancel:
                self._finish_cancelled()
            else:
                self._finish_failure(str(error))
            return
        if result.get("status") == "cancelled":
            self._finish_cancelled()
            return
        if result.get("status") == "failed":
            error = (result.get("error") or {}).get("message", "inference failed")
            self._finish_failure(error)
            return
        self._finish_success(result, handle)

    def _finish_success(self, result: dict, handle) -> None:
        session = self.window.analysisSession
        run, request = self._run, self._request
        if session is None or run is None or request is None:
            self._reset_job()
            return
        try:
            completed = verify_experiment_inference_result(
                session, run, request, result, self._job_dir,
            )
        except (ProjectSessionError, ValueError) as error:
            self._finish_failure(f"verification rejected the result: {error}")
            return
        from dataclasses import replace as _replace

        completed = _replace(
            completed,
            extra_fields={
                **completed.extra_fields,
                "elapsed_s": round(handle.elapsed_s, 3),
            },
        )
        session.update_tracking_run(completed)
        self._set_activity("Completed", running=False)
        self._reset_job()
        complete = completed.extra_fields.get("complete_count")
        self.window.statusBar().showMessage(
            f"Joint inference complete: candidate run {str(run.run_id)[:8]} "
            f"({complete} complete frames, not active). Review it next.")
        self._refresh_workflow()

    def _finish_failure(self, message: str) -> None:
        session = self.window.analysisSession
        if session is not None and self._run is not None:
            try:
                session.update_tracking_run(mark_run_failed(self._run, message))
            except ProjectSessionError:
                logger.warning("could not mark the inference run failed")
        logger.warning("joint inference failed: %s", message)
        self._set_activity(f"Failed: {message[:60]}", running=False)
        self._reset_job()
        self.window.statusBar().showMessage(f"Joint inference failed: {message}")
        self._refresh_workflow()

    def _finish_cancelled(self) -> None:
        session = self.window.analysisSession
        if session is not None and self._run is not None:
            try:
                session.update_tracking_run(mark_run_cancelled(self._run))
            except ProjectSessionError:
                logger.warning("could not mark the inference run cancelled")
        self._set_activity("Cancelled", running=False)
        self._reset_job()
        self.window.statusBar().showMessage("Joint inference cancelled")
        self._refresh_workflow()

    def _reset_job(self) -> None:
        self._handle = None
        self._run = None
        self._request = None
        self._job_dir = None
        self._session = None
        self._user_cancel = False

    # ------------------------------------------------------------------
    # 审核队列(P1.4-S4b)
    # ------------------------------------------------------------------

    def openReviewQueue(self, run_id: UUID | None = None) -> None:
        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            self.window.statusBar().showMessage(
                "Joint review needs the experiment on the current video")
            return
        if run_id is None:
            # 卡片入口:取最新 completed candidate(非 active)
            runs = sorted(
                (r for r in session.tracking_runs()
                 if r.task_type == "infer"
                 and r.config.get("request_kind") == "experiment-joint-inference-v1"
                 and r.experiment_id == experiment.experiment_id
                 and r.status == "completed"
                 and r.run_id != experiment.active_infer_run_id),
                key=lambda r: r.created_at,
            )
            if not runs:
                self.window.statusBar().showMessage(
                    "No joint candidate to review — run joint inference first")
                return
            run_id = runs[-1].run_id
        try:
            state = session.get_experiment_review(run_id)
            if state is None:
                candidates = session.create_experiment_review_queue(run_id)
            else:
                candidates = state[0]
        except (ProjectSessionError, ValueError) as error:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self.window, "Cannot open joint review", str(error))
            return
        from ai_physics_tracker.gui.experiment_review_dialog import JointReviewDialog

        if self._dialog is None:
            self._dialog = JointReviewDialog(run_id, self.window)
            self._connect_dialog(self._dialog)
        records = session.get_experiment_review(run_id)[1]
        self._review_run_id = run_id
        self._review_frames = tuple(c.frame_index for c in candidates)
        self._review_current = self._first_pending_frame(records)
        self._dialog.set_roles(self._role_order())
        self._dialog.show()
        self._dialog.raise_()
        self._sync_review(records)

    def _role_order(self):
        from ai_physics_tracker.domain.pendulum import ROLE_ORDER

        return ROLE_ORDER

    def _first_pending_frame(self, records: dict) -> int | None:
        for frame in self._review_frames:
            if frame not in records:
                return frame
        return self._review_frames[-1] if self._review_frames else None

    def _connect_dialog(self, dialog) -> None:
        dialog.acceptRequested.connect(self.acceptCurrent)
        dialog.skipRequested.connect(self.skipCurrent)
        dialog.correctRequested.connect(self.startCorrect)
        dialog.cancelCorrectRequested.connect(self.cancelCorrect)
        dialog.previousRequested.connect(self.previousFrame)
        dialog.nextRequested.connect(self.nextFrame)
        dialog.finishRequested.connect(self.finishReviewing)
        dialog.frameJumped.connect(self.jumpToFrame)
        dialog.finished.connect(self._on_dialog_closed)

    def _on_dialog_closed(self, *_args) -> None:
        # 用户关闭窗口 == Finish:保留进度与已写 manual 点,退出点击模式
        self.finishReviewing()

    def _records(self) -> dict:
        session = self.window.analysisSession
        if session is None or self._review_run_id is None:
            return {}
        state = session.get_experiment_review(self._review_run_id)
        return state[1] if state is not None else {}

    def _candidates(self):
        session = self.window.analysisSession
        if session is None or self._review_run_id is None:
            return ()
        state = session.get_experiment_review(self._review_run_id)
        return state[0] if state is not None else ()

    def _sync_review(self, records: dict) -> None:
        """把队列/记录/当前帧推给对话框、视频与 overlay。"""

        if self._dialog is None:
            return
        candidates = self._candidates()
        records = records if records is not None else self._records()
        index = self._index_of(self._review_current)
        self._dialog.sync(candidates, records, self._review_current,
                          self._correcting_role)
        self._dialog.set_navigation(
            index is not None and index > 0,
            index is not None and index < len(self._review_frames) - 1)
        if self._review_current is not None:
            self.window.seekFrame(self._review_current)
            self._refresh_preview(candidates)
        if self._correcting_role:
            self.window.videoView.set_annotation_mode(True)

    def _index_of(self, frame: int | None) -> int | None:
        if frame is None:
            return None
        try:
            return self._review_frames.index(frame)
        except ValueError:
            return None

    def _refresh_preview(self, candidates) -> None:
        """当前帧四 role 预测点画为 preview overlay(不触碰 markers)。"""

        current = next(
            (c for c in candidates if c.frame_index == self._review_current),
            None)
        from ai_physics_tracker.gui.video_view import MarkerView

        markers = []
        if current is not None:
            for role, prediction in current.predictions.items():
                if prediction is None:
                    continue
                markers.append(MarkerView(
                    pixel_x=prediction.pixel_x, pixel_y=prediction.pixel_y,
                    color=_REVIEW_PREVIEW_COLORS.get(role, "#ffb000"),
                    source="preview", frame_index=current.frame_index,
                ))
        self.window.videoView.set_preview_markers(
            markers, "joint candidate preview")

    def _advance(self, records: dict) -> None:
        next_frame = None
        started = False
        for frame in self._review_frames:
            if frame not in records:
                if not started:
                    next_frame = frame
                    started = True
        self._review_current = next_frame if next_frame is not None else (
            self._review_frames[-1] if self._review_frames else None)

    def previousFrame(self) -> None:
        index = self._index_of(self._review_current)
        if index is None or index <= 0:
            return
        self._cancel_correct_quietly()
        self._review_current = self._review_frames[index - 1]
        self._sync_review(None)

    def nextFrame(self) -> None:
        index = self._index_of(self._review_current)
        if index is None or index >= len(self._review_frames) - 1:
            return
        self._cancel_correct_quietly()
        self._review_current = self._review_frames[index + 1]
        self._sync_review(None)

    def jumpToFrame(self, frame: int) -> None:
        if self._index_of(frame) is None:
            return
        self._cancel_correct_quietly()
        self._review_current = frame
        self._sync_review(None)

    def acceptCurrent(self) -> None:
        self._decide("accepted")

    def skipCurrent(self) -> None:
        self._decide("skipped")

    def _decide(self, disposition: str) -> None:
        session = self.window.analysisSession
        if session is None or self._review_run_id is None:
            return
        if self._review_current is None:
            return
        self._cancel_correct_quietly()
        try:
            session.review_experiment_frame(
                self._review_run_id, self._review_current, disposition,
            )
        except (ProjectSessionError, ValueError) as error:
            logger.error("joint review %s failed: %s", disposition, error)
            self.window.statusBar().showMessage(f"{disposition.title()} failed: {error}")
            return
        records = self._records()
        self._advance(records)
        self._sync_review(records)
        self._notify_done(records)

    def startCorrect(self, role: str) -> None:
        if self._dialog is None or self._review_current is None:
            return
        self._correcting_role = role
        self.window.videoView.set_annotation_mode(True)
        self.window.statusBar().showMessage(
            f"Correct mode: click the '{role}' position in the video for "
            f"frame {self._review_current} (Esc to cancel)")
        self._sync_review(None)

    def cancelCorrect(self) -> None:
        self._correcting_role = None
        if self._dialog is not None:
            self._sync_review(None)
        self.window.statusBar().showMessage("Correct mode cancelled")

    def _cancel_correct_quietly(self) -> None:
        if self._correcting_role is not None:
            self._correcting_role = None
            self.window.videoView.set_annotation_mode(False)

    def handleCorrectClick(self, pixel_x: float, pixel_y: float) -> bool:
        """主窗口视频点击回调;correcting 时写所选 role 的 manual 点。"""

        if not self.is_correcting:
            return False
        session = self.window.analysisSession
        if session is None or self._review_run_id is None:
            return False
        frame = self._review_current
        role = self._correcting_role
        if self.window.presented_frame_index != frame:
            self.window.statusBar().showMessage(
                f"Ignored click: current frame {self.window.presented_frame_index} "
                f"does not match review frame {frame}")
            return False
        try:
            session.review_experiment_frame(
                self._review_run_id, frame, "corrected",
                role=role, pixel_x=pixel_x, pixel_y=pixel_y,
            )
        except (ProjectSessionError, ValueError) as error:
            logger.error("joint review correction failed: %s", error)
            self.window.statusBar().showMessage(f"Correction failed: {error}")
            return False
        self._correcting_role = None
        self.window.videoView.set_annotation_mode(False)
        records = self._records()
        self._advance(records)
        self._sync_review(records)
        self.window.projectActions.autosave("joint review correction")
        self.window._refreshMarkers()
        self.window.statusBar().showMessage(
            f"Frame {frame}: '{role}' corrected at "
            f"({pixel_x:.1f}, {pixel_y:.1f})")
        self._notify_done(records)
        return True

    def _notify_done(self, records: dict) -> None:
        pending = sum(1 for frame in self._review_frames if frame not in records)
        if pending == 0:
            self.window.projectActions.autosave("joint review completed")
            self.window.statusBar().showMessage(
                "Joint review queue completed. Activate the candidate next "
                "(or keep it for later).")
        self._refresh_workflow()

    def finishReviewing(self) -> None:
        """退出审核;未处置帧与已写 manual 点全部保留(run-scoped 持久化)。"""

        self._cancel_correct_quietly()
        records = self._records()
        pending = sum(1 for frame in self._review_frames if frame not in records)
        if self._dialog is not None:
            dialog, self._dialog = self._dialog, None
            dialog.finished.disconnect(self._on_dialog_closed)
            dialog.deleteLater()
        self._review_run_id = None
        self._review_frames = ()
        self._review_current = None
        self.window.videoView.set_preview_markers([], "")
        if pending:
            self.window.statusBar().showMessage(
                f"Review finished; {pending} frame(s) kept for later.")
        self._refresh_workflow()

    # ------------------------------------------------------------------
    # 四轨激活/替换/清除(P1.4-S4c)
    # ------------------------------------------------------------------

    def activateCandidate(self, run_id: UUID | None = None) -> None:
        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        if run_id is None:
            run_id = self._latest_candidate(session, experiment)
        if run_id is None:
            self.window.statusBar().showMessage("No joint candidate to activate")
            return
        summary = self._candidate_summary(session, run_id)
        if not self._confirm(
                "Activate Joint Candidate",
                f"Activate candidate run {str(run_id)[:8]} as the experiment "
                f"measurement?\n\n{summary}\n\n"
                "All four tracks adopt this candidate in one transaction; "
                "manual points are preserved and keep precedence. "
                "Nothing is deleted — Undo works until you save."):
            return
        try:
            record = session.activate_experiment_candidate(
                experiment.experiment_id, run_id)
        except (ProjectSessionError, ValueError) as error:
            self._activation_error("Activate failed", error)
            return
        self._after_activation("Activated", record)

    def replaceCandidate(self, run_id: UUID | None = None) -> None:
        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        if run_id is None:
            run_id = self._latest_candidate(session, experiment)
        if run_id is None:
            self.window.statusBar().showMessage("No replacement candidate")
            return
        from_text = (
            f"run {str(experiment.active_infer_run_id)[:8]}"
            if experiment.active_infer_run_id else "the current measurement")
        summary = self._candidate_summary(session, run_id)
        if not self._confirm(
                "Replace Active Measurement",
                f"Replace {from_text} with candidate run {str(run_id)[:8]}?\n\n"
                f"{summary}\n\n"
                "The previous run's AI observations are archived in the "
                "activation history; manual points are preserved."):
            return
        try:
            record = session.replace_experiment_candidate(
                experiment.experiment_id, run_id)
        except (ProjectSessionError, ValueError) as error:
            self._activation_error("Replace failed", error)
            return
        self._after_activation("Replaced", record)

    def clearMeasurement(self) -> None:
        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        members = set(experiment.roles.track_ids())
        ai_count = sum(
            1 for point in session.project.observations
            if point.track_id in members and point.source != "manual"
            and point.status == "active")
        manual_count = sum(
            1 for point in session.project.observations
            if point.track_id in members and point.source == "manual"
            and point.status == "active")
        if not self._confirm(
                "Clear Active Measurement",
                f"Clear the active joint measurement?\n\n"
                f"{ai_count} AI point(s) across the four tracks will be "
                f"removed; {manual_count} manual point(s) are NOT deleted.",
                default_yes=False):
            return
        try:
            session.clear_experiment_candidate(experiment.experiment_id)
        except (ProjectSessionError, ValueError) as error:
            self._activation_error("Clear failed", error)
            return
        self.window.statusBar().showMessage(
            "Active measurement cleared (manual points kept)")
        self.window._refreshMarkers()
        self.window._refreshHistoryButtons()
        self.window.projectActions.autosave("joint measurement cleared")
        self._refresh_workflow()

    # ------------------------------------------------------------------
    # 激活辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _latest_candidate(session, experiment) -> UUID | None:
        runs = sorted(
            (r for r in session.tracking_runs()
             if r.task_type == "infer"
             and r.config.get("request_kind") == "experiment-joint-inference-v1"
             and r.experiment_id == experiment.experiment_id
             and r.status == "completed"
             and r.run_id != experiment.active_infer_run_id),
            key=lambda r: r.created_at,
        )
        return runs[-1].run_id if runs else None

    @staticmethod
    def _candidate_summary(session, run_id: UUID) -> str:
        run = next(
            (r for r in session.tracking_runs() if r.run_id == run_id), None)
        if run is None:
            return "candidate details unavailable"
        complete = run.extra_fields.get("complete_count")
        missing = run.extra_fields.get("missing_by_role") or {}
        missing_note = ", ".join(
            f"{role}: {count}" for role, count in missing.items() if count
        ) or "none"
        manual_note = ""
        experiment = next(
            (e for e in session.pendulum_experiments()
             if run.experiment_id is not None
             and e.experiment_id == run.experiment_id), None)
        if experiment is not None:
            manual_total = sum(
                1 for point in session.project.observations
                if point.track_id in set(experiment.roles.track_ids())
                and point.source == "manual" and point.status == "active")
            manual_note = f"\nManual points on the four tracks: {manual_total}."
        return (
            f"Complete frames: {complete if complete is not None else '?'}. "
            f"Missing by role — {missing_note}.{manual_note}"
        )

    def _confirm(self, title: str, text: str, *, default_yes: bool = True) -> bool:
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self.window, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes if default_yes
            else QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _activation_error(self, title: str, error: Exception) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(self.window, title, str(error))
        self.window.statusBar().showMessage(f"{title}: {error}")

    def _after_activation(self, verb: str, record) -> None:
        counts = ", ".join(
            f"{item.role}: {item.adopted_count} AI/"
            f"{item.manual_preserved_count} manual"
            for item in record.role_counts)
        self.window.statusBar().showMessage(
            f"{verb} candidate {str(record.to_run_id)[:8]} — {counts}; "
            f"measurement revision is now active.")
        self.window._refreshMarkers()
        self.window._refreshHistoryButtons()
        self.window.projectActions.autosave(
            f"joint measurement {verb.lower()}")
        self._refresh_workflow()

    # ------------------------------------------------------------------
    # 会话事件
    # ------------------------------------------------------------------

    def _refresh_workflow(self) -> None:
        tracking = getattr(self.window, "trackingActions", None)
        if tracking is not None:
            tracking._context_key = None
            tracking.refresh()
        else:
            self.window.projectActions.refresh()

    def _on_project_changed(self, *_args) -> None:
        self._reset_job()
        self._timer.stop()
        self._correcting_role = None
        if self._dialog is not None:
            dialog, self._dialog = self._dialog, None
            dialog.finished.disconnect(self._on_dialog_closed)
            dialog.deleteLater()
        self._review_run_id = None
        self._review_frames = ()
        self._review_current = None
