"""P1.4-S4 experiment 联合推理/审核/激活的 GUI 控制器(Qt GUI 层)。

执行边界与 ModelActions 相同:prepare/verify/审核/激活是 session 应用
动作(GUI 线程);推理经 external worker 子进程执行,QTimer 轮询句柄。
审核对话框只呈现队列与诊断,写路径全部经本控制器走 session 动作。
Correct 的落点在主窗口视频上点击(对话框非模态保持可见)。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.application.experiment_review import (
    EXPERIMENT_REVIEW_KEY,
)
from ai_physics_tracker.application.experiment_inference_job import (
    prepare_experiment_inference,
    verify_experiment_inference_result,
)
from ai_physics_tracker.application.model_worker import (
    ModelWorkerError,
    ModelWorkerRunner,
    read_inference_progress,
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

        self.window = window
        if runtime_python is None:
            from ai_physics_tracker.gui.launch_context import (
                runtime_python as _resolve_runtime_python,
            )

            runtime_python = _resolve_runtime_python()
        # frozen 且无 managed runtime 时为 None:AI 入口显示安装占位,不启动 worker
        self._runtime_python: str | None = (
            str(runtime_python) if runtime_python is not None else None
        )
        # frozen 下 worker 源码根与 host 归档不同源,必须显式注入(P6.1)
        from ai_physics_tracker.gui.launch_context import worker_package_root

        self._package_root = worker_package_root()
        # 测试缝:注入假 runner;产品恒为 ModelWorkerRunner(package_root 随 frozen)
        self._runner_factory = runner_factory or (
            lambda: ModelWorkerRunner(self._runtime_python, package_root=self._package_root)
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
        self._predicted_frames = 0
        self._progress_phase = "Loading model"

        # 审核会话态(不持久化;queue/records 本身在 run extras)
        self._dialog = None
        self._review_run_id: UUID | None = None
        self._review_frames: tuple[int, ...] = ()
        self._review_current: int | None = None
        self._correcting_role: str | None = None
        self._relabel_tasks: tuple[tuple[int, str], ...] = ()
        self._relabel_index = 0
        self._relabel_completed: set[int] = set()
        self._relabel_skipped: set[int] = set()
        self._relabel_message = ""
        self._suggest_count = 15     # 每批推荐帧数(用户可调,1–40)
        self._batch_index = 0
        self._total_relabeled = 0

        window.projectChanged.connect(self._on_project_changed)
        window.presentedFrameChanged.connect(self._on_review_frame_presented)
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

    def _ensure_runtime(self) -> bool:
        """AI 任务启动前的 runtime 守卫：不可用则占位提示并拒绝（P6.1）。"""

        if self._runtime_python and Path(self._runtime_python).is_file():
            return True
        from ai_physics_tracker.gui.launch_context import show_ai_runtime_missing

        show_ai_runtime_missing(self.window)
        return False

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

    def runJointInference(self, model_id: UUID, params, *, _device_checked: bool = False) -> None:
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
        if not self._ensure_runtime():
            return
        from ai_physics_tracker.application.teacher_models import effective_compatibility_state

        model = next((m for m in session.project.model_references
                      if m.model_id == model_id), None)
        checked_device = str(((model.self_test_evidence or {}).get("runtime") or {}).get("device", "")) if model else ""
        # auto必须在worker运行环境重新探测；CPU自检不能证明GPU可用。
        needs_device_check = (params.device == "auto" and not _device_checked) or (
            params.device != "auto" and checked_device.split(":")[0] != params.device)
        if model is not None and (effective_compatibility_state(model) == "unverified" or needs_device_check):
            experiment_id = experiment.experiment_id

            def continue_inference():
                current = self.window.currentPendulumExperiment()
                if (self.window.analysisSession is session and current is not None
                        and current.experiment_id == experiment_id):
                    self.runJointInference(model_id, params, _device_checked=True)

            self.window.modelActions.runSelftest(
                model_id, device=params.device, on_success=continue_inference)
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
                session.project_root, request, device=request.expected_device.split(":")[0],
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
        self._refresh_inference_progress()
        self.window.statusBar().showMessage(
            f"Joint inference run {run.run_id} started: {params.device} → {request.expected_device} "
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
        if handle is None:
            return
        if handle.is_alive():
            self._refresh_inference_progress()
            return
        self._timer.stop()
        if self._session is not None and self.window.analysisSession is not self._session:
            logger.warning("joint inference finished after session swap; discarding")
            handle.cancel()
            self._set_activity("Discarded (project changed)", running=False)
            self._reset_job()
            return
        if self._user_cancel:
            # worker可能已退出但终态尚未poll；用户取消仍拒收迟到success。
            self._finish_cancelled()
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
        self._refresh_inference_progress()
        self.window.trackingActions.panel.setActivity(
            "Verifying prediction result", step=self._predicted_frames, total=self._request.frame_count)
        self._finish_success(result, handle)

    def _refresh_inference_progress(self) -> None:
        """真实已后处理帧数；ETA用累计吞吐估算，未出首批不猜时间。"""

        if self._handle is None or self._request is None or self._job_dir is None or self._run is None:
            return
        if self.window.analysisSession is not self._session:
            return
        total = self._request.frame_count
        progress = read_inference_progress(self._job_dir, self._run.run_id, total)
        if progress is not None and progress[0] >= self._predicted_frames:
            self._predicted_frames, self._progress_phase = progress
        step = self._predicted_frames
        elapsed = max(0., self._handle.elapsed_s)
        minutes, seconds = divmod(int(elapsed), 60)
        stage = "Saving / checking predictions" if step == total else (
            "Inferring" if step else self._progress_phase)
        panel = self.window.trackingActions.panel
        panel.setActivity(stage, step=step, total=total)
        panel.progressBar.setFormat(f"%p% · {step}/{total} frames")
        # macOS原生进度条可能不绘制format文本；标签保证帧数/百分比可见。
        details = [f"Device {self._request.expected_device}", f"{step}/{total} frames ({step / total:.0%})",
                   f"Elapsed {minutes:02d}:{seconds:02d}"]
        if 0 < step < total and elapsed > 0:
            rate = step / elapsed
            remaining = int((total - step) / rate)
            mins, secs = divmod(remaining, 60)
            details.extend((f"{rate:.2f} frames/s", f"ETA ≈ {mins:02d}:{secs:02d}"))
        elif step == 0:
            details.append("Waiting for the first predicted batch; ETA unavailable")
        else:
            details.append("All frames predicted; result not confirmed yet")
        panel.metricsLabel.setText(" · ".join(details))
        panel.cancelButton.setEnabled(True)

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
        self._predicted_frames = 0
        self._progress_phase = "Loading model"

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
            # 有新 candidate 时优先推荐它;否则允许从已激活 run 继续选训练帧
            runs = sorted(
                (r for r in session.tracking_runs()
                 if r.task_type == "infer"
                 and r.config.get("request_kind") == "experiment-joint-inference-v1"
                 and r.experiment_id == experiment.experiment_id
                 and r.status == "completed"),
                key=lambda r: r.created_at,
            )
            if not runs:
                self.window.statusBar().showMessage(
                    "No joint run to inspect — run joint inference first")
                return
            run_id = runs[-1].run_id
        self._batch_index = 1
        self._total_relabeled = 0
        try:
            candidates = self._create_suggestions(session, run_id)
        except (ProjectSessionError, ValueError) as error:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self.window, "Cannot open joint review", str(error))
            return
        from ai_physics_tracker.gui.experiment_review_dialog import JointReviewDialog

        if self._dialog is not None:
            self.finishReviewing()
        self._dialog = JointReviewDialog(run_id, self.window)
        self._connect_dialog(self._dialog)
        self._dialog.reset_suggestions(candidates)
        self._dialog.set_suggestion_count(self._suggest_count)
        records = session.get_experiment_review(run_id)[1]
        self._review_run_id = run_id
        self._sync_pool()
        self._review_frames = tuple(c.frame_index for c in candidates)
        self._review_current = self._review_frames[0] if self._review_frames else None
        self._dialog.show()
        self._dialog.raise_()
        self._refresh_workflow()
        self._sync_review(records)

    def _role_order(self):
        from ai_physics_tracker.domain.pendulum import ROLE_ORDER

        return ROLE_ORDER

    def _connect_dialog(self, dialog) -> None:
        dialog.cancelCorrectRequested.connect(self.cancelCorrect)
        dialog.skipFrameRequested.connect(self.skipRelabelFrame)
        dialog.previousRequested.connect(self.previousFrame)
        dialog.nextRequested.connect(self.nextFrame)
        dialog.finishRequested.connect(self.finishReviewing)
        dialog.frameJumped.connect(self.jumpToFrame)
        dialog.labelSelectedRequested.connect(self.startRelabelSelected)
        dialog.refreshRequested.connect(self.refreshSuggestions)
        dialog.trainRequested.connect(self.doneLabelingTrain)
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
        if state is None:
            return ()
        by_frame = {item.frame_index: item for item in state[0]}
        return tuple(by_frame[frame] for frame in self._review_frames if frame in by_frame)

    def _sync_review(self, records: dict, *, seek: bool = True) -> None:
        """把队列/记录/当前帧推给对话框、视频与 overlay。"""

        if self._dialog is None:
            return
        candidates = self._candidates()
        records = records if records is not None else self._records()
        index = self._index_of(self._review_current)
        experiment = self.window.currentPendulumExperiment()
        training_frames = (frozenset(experiment.frame_set.frames)
                           if experiment and experiment.frame_set else frozenset())
        frame_ready = self.window.presented_frame_index == self._review_current
        pending = self._relabel_index < len(self._relabel_tasks)
        progress = self._relabel_message
        if pending:
            frame, role = self._relabel_tasks[self._relabel_index]
            position = self._relabel_index // 4 + 1
            progress = (
                f"Frame {position}/{len(self._relabel_tasks) // 4} · source frame {frame} · "
                f"Point {self._relabel_index % 4 + 1}/4: {role}. "
                + ("Click its position in the video." if frame_ready else
                   f"Waiting for frame {frame} to appear…")
                if self._correcting_role else
                f"Paused at frame {frame}, {role}. Click Resume to continue.")
        elif self._correcting_role:
            progress = (f"Frame {self._review_current}: click {self._correcting_role}."
                        if frame_ready else f"Waiting for frame {self._review_current}…")
        self._dialog.sync(candidates, records, self._review_current,
                          self._correcting_role, training_frames, frame_ready,
                          progress=progress, batch_pending=pending)
        self._dialog.set_navigation(
            index is not None and index > 0,
            index is not None and index < len(self._review_frames) - 1)
        if self.window.projectActions.busy:
            self._dialog.trainButton.setEnabled(False)
        if seek and self._review_current is not None:
            self._schedule_seek()
        if self._review_current is not None:
            self._refresh_preview(candidates)
        if self._correcting_role:
            self.window.videoView.set_annotation_mode(
                frame_ready and self.window.currentWorkspace != "analysis")
        if pending:
            # 批量进行中:用户在主窗口点视频,引导条只显示逐帧操作指引
            self.window._setCalibrationGuide(progress)
        elif self._relabel_message:
            # 批次结束:细节留在推荐窗(自动置前),引导条只给一句方向
            self.window._setCalibrationGuide(
                "Batch finished — the suggestion window (brought to front) "
                "has the next batch and the train button.")
            if self._dialog is not None:
                self._dialog.show()
                self._dialog.raise_()
                self._dialog.activateWindow()

    def _on_review_frame_presented(self, *_args) -> None:
        if self._dialog is not None and self._correcting_role is not None:
            self._sync_review(None, seek=False)

    def _schedule_seek(self, attempts: int = 8) -> None:
        """呈现当前审核帧;被异步保存等短暂 busy 拒绝时延迟重试。"""

        frame = self._review_current
        if frame is None or self.window.presented_frame_index == frame:
            return
        if not self.window.seekFrame(frame) and attempts > 0:
            QTimer.singleShot(150, lambda: self._schedule_seek(attempts - 1))

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
            session = self.window.analysisSession
            experiment = self.window.currentPendulumExperiment()
            for role, prediction in current.predictions.items():
                manual = next((p for p in session.manual_points(
                    experiment.roles.track_id_for(role))
                    if p.frame_index == current.frame_index), None)
                shown = manual or prediction
                if shown is None:
                    continue
                markers.append(MarkerView(
                    pixel_x=shown.pixel_x, pixel_y=shown.pixel_y,
                    color=_REVIEW_PREVIEW_COLORS.get(role, "#ffb000"),
                    source="manual" if manual else "preview", frame_index=current.frame_index,
                ))
        self.window.videoView.set_preview_markers(
            markers, "Filled: manual labels · Hollow: AI predictions")

    def previousFrame(self) -> None:
        if self._relabel_index < len(self._relabel_tasks):
            return
        index = self._index_of(self._review_current)
        if index is None or index <= 0:
            return
        self._cancel_correct_quietly()
        self._review_current = self._review_frames[index - 1]
        self._sync_review(None)

    def nextFrame(self) -> None:
        if self._relabel_index < len(self._relabel_tasks):
            return
        index = self._index_of(self._review_current)
        if index is None or index >= len(self._review_frames) - 1:
            return
        self._cancel_correct_quietly()
        self._review_current = self._review_frames[index + 1]
        self._sync_review(None)

    def jumpToFrame(self, frame: int) -> None:
        if self._relabel_index < len(self._relabel_tasks):
            return
        if self._index_of(frame) is None:
            return
        self._cancel_correct_quietly()
        self._review_current = frame
        self._sync_review(None)

    def startCorrect(self, role: str) -> None:
        if self._dialog is None or self._review_current is None:
            return
        self.window.setWorkspace("acquire")
        self._correcting_role = role
        self.window.videoView.set_annotation_mode(True)
        # HR 反馈(2026-09-29):macOS 非活动窗口的第一次点击只用于激活
        # 窗口(click-through 默认关闭)——主动激活主窗口,视频立即可点
        self.window.raise_()
        self.window.activateWindow()
        self.window.statusBar().showMessage(
            f"Correct mode: click the '{role}' position in the video for "
            f"frame {self._review_current} (Esc to stop)")
        self._sync_review(None)

    def cancelCorrect(self) -> None:
        self._correcting_role = None
        self.window.videoView.set_annotation_mode(False)
        self.window.projectActions.autosave(
            "relabeling paused", after=lambda: self._sync_review(None))
        if self._dialog is not None:
            self._sync_review(None)
        self.window.statusBar().showMessage("Relabeling paused; recorded points kept")

    def _cancel_correct_quietly(self) -> None:
        if self._correcting_role is not None:
            self._correcting_role = None
            self.window.videoView.set_annotation_mode(False)

    def handleCorrectClick(self, pixel_x: float, pixel_y: float) -> bool:
        """主窗口视频点击回调;只修正当前推荐帧的一个 role。"""

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
        if self._relabel_index < len(self._relabel_tasks):
            self._relabel_index += 1
            if self._relabel_index % 4 == 0:
                self._relabel_completed.add(frame)
            self._continue_relabeling()
        else:
            self._correcting_role = None
            self.window.videoView.set_annotation_mode(False)
            self.window.projectActions.autosave("joint review correction")
        records = self._records()
        self._sync_review(records)
        self.window._refreshMarkers()
        self._refresh_workflow()
        return True

    def _create_suggestions(self, session, run_id):
        """按当前 Suggest N 重算推荐(排除已 complete 帧);持久化进 run。"""

        return session.create_experiment_review_queue(
            run_id, top_n=self._suggest_count)

    def _sync_pool(self) -> None:
        """把 run policy 里的总困难池推给对话框(信息,非任务量)。"""

        if self._dialog is None or self._review_run_id is None:
            return
        session = self.window.analysisSession
        pool = None
        if session is not None:
            run = next((r for r in session.tracking_runs()
                        if r.run_id == self._review_run_id), None)
            if run is not None:
                policy = run.extra_fields.get(EXPERIMENT_REVIEW_KEY)
                if isinstance(policy, dict):
                    raw_pool = policy.get("policy", {}).get("difficulty_pool")
                    pool = raw_pool if isinstance(raw_pool, int) else None
        self._dialog.set_pool(pool)

    def refreshSuggestions(self, count: int | None = None) -> None:
        """按新 N 重算推荐并全选;批量进行中拒绝刷新。"""

        if count is not None:
            self._suggest_count = max(1, min(40, int(count)))
        session = self.window.analysisSession
        if session is None or self._review_run_id is None or self._dialog is None:
            return
        if self._relabel_index < len(self._relabel_tasks):
            self.window.statusBar().showMessage(
                "Finish or pause the current batch before refreshing")
            return
        try:
            candidates = self._create_suggestions(session, self._review_run_id)
        except (ProjectSessionError, ValueError) as error:
            self.window.statusBar().showMessage(f"Cannot refresh: {error}")
            return
        self._review_frames = tuple(c.frame_index for c in candidates)
        self._review_current = self._review_frames[0] if self._review_frames else None
        self._dialog.reset_suggestions(candidates)
        self._dialog.set_suggestion_count(self._suggest_count)
        self._sync_pool()
        self._sync_review(None)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        self.window.statusBar().showMessage(
            f"{len(self._review_frames)} suggested frame(s) for this batch "
            f"(pool shown in the window).")

    def doneLabelingTrain(self) -> None:
        """结束标注,直接进入训练准备:先冻结 fixed-check(若失效)再指向训练。"""

        self._relabel_tasks = ()
        self._relabel_index = 0
        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()

        def train_after_save() -> None:
            current = self.window.currentPendulumExperiment()
            if self.window.analysisSession is session and experiment is not None \
                    and current is not None and current.experiment_id == experiment.experiment_id:
                self._launch_training_flow()

        self.finishReviewing(after=train_after_save)

    def _launch_training_flow(self) -> None:
        models = getattr(self.window, "modelActions", None)
        if models is not None:
            models.trainWithCurrentLabels()

    def startRelabelSelected(self) -> None:
        """冻结勾选帧为本次任务；每帧四次点击，不进入另一套帧导航。"""

        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None or self._review_run_id is None:
            return
        if self._dialog is None or self.window.projectActions.busy:
            return
        if self._relabel_index < len(self._relabel_tasks):
            self._continue_relabeling()
            self.window.raise_()
            self.window.activateWindow()
            return
        frames = self._dialog.checkedFrames()
        if not frames:
            self.window.statusBar().showMessage(
                "Check at least one suggested frame, or press Refresh for "
                "new suggestions")
            return
        try:
            session.extend_experiment_frame_set(experiment.experiment_id, frames)
        except (ProjectSessionError, ValueError) as error:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self.window, "Cannot extend frame set", str(error))
            return
        self.window._exitExperimentGuide()
        self.window.stopPlayback()
        self._relabel_tasks = tuple((frame, role) for frame in frames
                                   for role in self._role_order())
        self._relabel_index = 0
        self._relabel_completed.clear()
        self._relabel_skipped.clear()
        self._relabel_message = ""
        self._review_current, role = self._relabel_tasks[0]
        self.startCorrect(role)

    def _continue_relabeling(self) -> None:
        if self._relabel_index < len(self._relabel_tasks):
            self._review_current, self._correcting_role = self._relabel_tasks[self._relabel_index]
        else:
            self._correcting_role = None
            self.window.videoView.set_annotation_mode(False)
            self._total_relabeled += len(self._relabel_completed)
            self._relabel_message = (
                f"Batch {self._batch_index} finished: "
                f"{len(self._relabel_completed)} relabeled, "
                f"{len(self._relabel_skipped)} skipped.")
            # 保存落盘后自动推荐下一批(排除刚标完的帧);随时可改去训练
            self.window.projectActions.autosave(
                "recommended frames relabeled", after=self._advance_batch)
        self._sync_review(None)

    def _advance_batch(self) -> None:
        """一批标完:自动推荐下一批;池耗尽时明确指向训练(用户决策 2026-09-30)。"""

        session = self.window.analysisSession
        if session is None or self._review_run_id is None or self._dialog is None:
            return
        self._batch_index += 1
        try:
            candidates = self._create_suggestions(session, self._review_run_id)
        except (ProjectSessionError, ValueError) as error:
            self.window.statusBar().showMessage(f"Cannot suggest next batch: {error}")
            return
        self._review_frames = tuple(c.frame_index for c in candidates)
        self._review_current = self._review_frames[0] if self._review_frames else None
        self._dialog.reset_suggestions(candidates)
        self._sync_pool()
        if self._review_frames:
            self._relabel_message = (
                f"Next batch ready: {len(self._review_frames)} more suggested "
                f"frame(s) (batch {self._batch_index}, {self._total_relabeled} "
                f"relabeled so far). Start to continue, or press "
                f"'Done labeling — train with these labels' anytime. "
                f"Skipped frames may reappear until labeled — that is fine.")
        else:
            self._relabel_message = (
                f"No more difficult frames worth labeling "
                f"({self._total_relabeled} relabeled in total). Freeze the "
                f"fixed-check set and train with the updated labels next.")
        self._sync_review(None)
        # 批次边界:推荐窗置前,用户不必去后台找窗口
        if self._dialog is not None:
            self._dialog.show()
            self._dialog.raise_()
            self._dialog.activateWindow()

    def skipRelabelFrame(self) -> None:
        if self._relabel_index >= len(self._relabel_tasks):
            return
        self._relabel_skipped.add(self._review_current)
        self._relabel_index = (self._relabel_index // 4 + 1) * 4
        self._continue_relabeling()

    def finishReviewing(self, *, after: Callable[[], None] | None = None) -> None:
        """关闭推荐列表;保留候选和已写 manual 点。"""

        self._cancel_correct_quietly()
        self._relabel_tasks = ()
        self._relabel_index = 0
        self._relabel_message = ""
        self._suggest_count = self._dialog.suggestion_count() \
            if self._dialog is not None else self._suggest_count
        self.window._hidePendulumGuide()
        if self._dialog is not None:
            dialog, self._dialog = self._dialog, None
            dialog.finished.disconnect(self._on_dialog_closed)
            dialog.deleteLater()
        self._review_run_id = None
        self._review_frames = ()
        self._review_current = None
        self.window.videoView.set_preview_markers([], "")
        self.window.statusBar().showMessage("Suggestions closed; candidate kept for later")
        self._refresh_workflow()
        self.window.projectActions.autosave("relabeling closed", after=after)

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
             and r.status == "completed"),
            key=lambda r: r.created_at,
        )
        latest = runs[-1].run_id if runs else None
        return latest if latest != experiment.active_infer_run_id else None

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
            f"Missing by role — {missing_note}."
            f"\nScreening threshold {run.extra_fields.get('verified_min_confidence')}: "
            "predictions below it are not written (missing frames)."
            f"{manual_note}"
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
        self._relabel_tasks = ()
        self._relabel_index = 0
        self._relabel_message = ""
        if self._dialog is not None:
            dialog, self._dialog = self._dialog, None
            dialog.finished.disconnect(self._on_dialog_closed)
            dialog.deleteLater()
        self._review_run_id = None
        self._review_frames = ()
        self._review_current = None
