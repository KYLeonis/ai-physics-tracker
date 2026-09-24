"""GUI 跟踪编排：轻量消息轮询、后台候选合并和异步取消。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from uuid import UUID

import logging

from PySide6.QtCore import QObject, QTimer, Qt

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import QMessageBox

from ai_physics_tracker.application.tracking_job import (
    prepare_experiment_frame_selection,
    prepare_tracking_request, run_tracking_worker, prepare_tracking_candidate,
    cancel_tracking_job, read_task_log, verify_request_files, TrackingJobRunner,
    prepare_frame_selection_request, run_frame_selection_worker,
    read_frame_selection_result, FrameSelectionRunner, FrameSelectionJobRequest,
)
from ai_physics_tracker.application.advisor_collection import collect_advisor_input
from ai_physics_tracker.application import user_messages
from ai_physics_tracker.application.refinement_history import extract_refinement_state
from ai_physics_tracker.application.training_advisor import AdvisorInput, recommend_training_action
from ai_physics_tracker.domain.pendulum import ExperimentFrameSet
from ai_physics_tracker.domain.tracking_run import mark_run_running, mark_run_failed, mark_run_cancelled
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.application.tracking_types import TaskProgress, TaskLog, TaskResult
from ai_physics_tracker.gui.task_panel import TaskPanel


if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


def _read_raw_candidate_preview(adapter, path: Path, frame_count: int):
    """后台读取全帧原始预测；低置信度点也必须可见、可修正。"""
    return tuple(
        point for point in adapter.read_raw_predictions(
            path, frame_count=frame_count)
        if isfinite(point.pixel_x) and isfinite(point.pixel_y)
        and isfinite(point.confidence)
    )


def _read_legacy_candidate_preview(path: Path, track_id: UUID, source_detail: str):
    """兼容没有原始预测引用的旧项目。"""
    from ai_physics_tracker.application.inference_job import read_observation_exchange

    return tuple(
        point for point in read_observation_exchange(path)
        if point.track_id == track_id and point.source_detail == source_detail
    )


class TrackingActions(QObject):
    """活动会话只在 GUI 线程修改；worker 仅拥有冻结请求与候选。"""

    def __init__(self, window: "MainWindow", adapter=None, runner=None) -> None:
        super().__init__(window)
        self.window = window
        self.backend = TrackingJobRunner(adapter, runner)
        self.panel = TaskPanel(window)
        # Phase 5.7：“获取轨迹”工作区的上下文卡固定在右侧（设计 §8.1）
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.panel)
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
        self._preview_future = None
        self._preview_expected_key = None
        self._preview_loaded_key = None
        self._generation = -1
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self.panel.trainRequested.connect(self.train)
        self.panel.primaryActionRequested.connect(self._onCardAction)
        self.panel.secondaryActionRequested.connect(self._onCardAction)
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
               self.panel.selectedTrainingRunId(),
               session.can_measure(video_id) if session and video_id else False,
               self.window.projectActions.busy,
               getattr(self.window, "frameSelectionActions", None) is not None
               and self.window.frameSelectionActions.busy,
               self.window.reviewActions.busy if hasattr(self.window, "reviewActions") else False,
               self.window.reviewActions.is_correcting
               if hasattr(self.window, "reviewActions") else False,
               self.window.reviewActions.paused_run_id
               if hasattr(self.window, "reviewActions") else None,
               tuple((item.experiment_id, item.measurement_revision)
                     for item in session.pendulum_experiments()) if session else ())
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
        # P1.1 契约 §2:experiment-bound track 的单轨 AI 写入口 fail closed。
        # 在按钮层提前禁用并说明,而不是点击后才在 activity 区闪一条错误;
        # joint 训练/推理属于 P1.3/P1.4,当前版本 bound track 尚无 AI 路径。
        bound_reason = (
            "Bound to pendulum experiment — single-track AI disabled "
            "(joint training comes in a later phase)"
            if (
                session is not None
                and track_id is not None
                and session.experiment_for_track(track_id) is not None
            )
            else None
        )
        train_reason = reason or bound_reason
        if not train_reason and len(session.manual_points(track_id)) < 3:
            train_reason = "Mark at least 3 frames; cover different target positions"
        infer_reason = reason or bound_reason
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
        self._refresh_workflow_ui(session, track_id, runs, video, track)
        if session and track_id:
            recommendation = self._advisor_recommendation(session, track_id, runs)
            if recommendation is None:
                # 采集失败与"未选 track"区分（review #11）
                self.panel.setAdvisorSummary(None)
                self.panel.advisorLabel.setText(
                    "Advisor: unavailable (input collection failed — see log)")
            else:
                self.panel.setAdvisorSummary(recommendation)
        else:
            self.panel.setAdvisorSummary(None)
        self.window.projectActions.refresh()

    # ------------------------------------------------------------------
    # Phase 5.7 — 状态投影驱动的工作流 UI（决策在 workflow_projection）
    # ------------------------------------------------------------------

    def _execution_input(self):
        from ai_physics_tracker.application.workflow_projection import (
            EXEC_CANCELLING,
            EXEC_FRAME_SELECTION,
            EXEC_IDLE,
            EXEC_INFERRING,
            EXEC_MINING,
            EXEC_TRAINING,
            ExecutionInput,
        )
        review = getattr(self.window, "reviewActions", None)
        correcting = bool(review and review.is_correcting)
        paused_run_id = review.paused_run_id if review is not None else None
        controller = review.controller if review is not None else None
        review_facts = {}
        if controller is not None and controller.current_candidate is not None:
            review_facts = {
                "review_index": controller.current_index,
                "review_total": controller.count,
                "review_frame_index": controller.current_frame_index,
                "review_can_previous": controller.can_navigate_previous,
                "review_can_next": controller.can_navigate_next,
            }
        if self.cancelling:
            return ExecutionInput(
                kind=EXEC_CANCELLING, cancelling=True,
                correcting=correcting, paused_review_run_id=paused_run_id,
                **review_facts)
        if self.pending:
            kind = (EXEC_INFERRING if self._request.run.task_type == "infer"
                    else EXEC_TRAINING)
            return ExecutionInput(
                kind=kind, correcting=correcting,
                paused_review_run_id=paused_run_id, **review_facts)
        frame_selection = getattr(self.window, "frameSelectionActions", None)
        if frame_selection is not None and frame_selection.busy:
            return ExecutionInput(
                kind=EXEC_FRAME_SELECTION, frame_selection=True,
                correcting=correcting, paused_review_run_id=paused_run_id,
                **review_facts)
        if getattr(self.window, "reviewActions", None) and self.window.reviewActions.busy:
            return ExecutionInput(
                kind=EXEC_MINING, mining=True, correcting=correcting,
                paused_review_run_id=paused_run_id, **review_facts)
        return ExecutionInput(
            kind=EXEC_IDLE, correcting=correcting,
            paused_review_run_id=paused_run_id, **review_facts)

    def _workflow_state(self, session, track_id, runs):
        from ai_physics_tracker.application.workflow_projection import (
            project_workflow_state,
        )
        # F5：帧集完成度与选中 track 无关——experiment 由 active video 决定
        experiment = (
            self.window.currentPendulumExperiment()
            if session is not None and session is self.window.analysisSession
            else None
        )
        return project_workflow_state(
            session, track_id, runs, self._execution_input(),
            experiment=experiment)

    def _refresh_workflow_ui(self, session, track_id, runs, video, track) -> None:
        """把投影结果推到任务卡与常驻状态头；决策失败不阻塞面板。"""
        from ai_physics_tracker.application.workflow_projection import select_task_card

        try:
            if session is None:
                self.panel.setTaskCard(None)
                self.window.workflowHeader.setStatus(
                    "No project", "Current trajectory: —", None)
                self._clear_candidate_preview()
                return
            state = self._workflow_state(session, track_id, runs)
            candidate = state.trajectory.candidate
            review = getattr(self.window, "reviewActions", None)
            if (candidate is not None and candidate.pending_review > 0
                    and review is not None
                    and review.ensureReviewRun(candidate.run_id)):
                # 审核器可从持久化批次恢复；重新投影以带上当前序号与帧号。
                state = self._workflow_state(session, track_id, runs)
            card = select_task_card(state)
            if state.failed_run_id is not None:
                failed_run = next(
                    (r for r in runs if r.run_id == state.failed_run_id), None)
                if failed_run is not None and "interrupted" in (
                        failed_run.error_message or "").lower():
                    from ai_physics_tracker.application.user_messages import (
                        interrupted_on_reopen,
                    )
                    ux = interrupted_on_reopen()
                    from dataclasses import replace as _replace
                    card = _replace(card, explanation=ux.body)
            self.panel.setTaskCard(card)
            self._current_workflow_state = state
            self._refresh_header(session, state, video, track)
            self._sync_candidate_preview(session, runs, state, track, video)
        except Exception as error:  # 投影是辅助信息，失败只降级显示
            logger.warning("workflow projection failed: %s", error)
            self.panel.setTaskCard(None)

    def _sync_candidate_preview(self, session, runs, state, track, video) -> None:
        candidate = state.trajectory.candidate
        if (candidate is None or track is None or video is None
                or session.project_root is None):
            self._clear_candidate_preview()
            return
        run = next((item for item in runs if item.run_id == candidate.run_id), None)
        prediction_ref = run.extra_fields.get("prediction_path") if run is not None else None
        raw_preview = isinstance(prediction_ref, str)
        ref = prediction_ref if raw_preview else (
            run.extra_fields.get("observations_path") if run is not None else None)
        if run is None or not isinstance(ref, str):
            self._clear_candidate_preview()
            self.window.videoView.set_preview_markers(
                [], f"Preview: {candidate.label} · not adopted · positions unavailable")
            return
        root = session.project_root.resolve()
        path = (root / ref).resolve()
        try:
            path.relative_to(root)
            stat = path.stat()
        except (OSError, ValueError):
            self._clear_candidate_preview()
            self.window.videoView.set_preview_markers(
                [], f"Preview: {candidate.label} · not adopted · prediction file unavailable")
            return
        file_info = run.extra_fields.get(
            "prediction_file_info" if raw_preview else "observations_file_info")
        if isinstance(file_info, list) and file_info:
            recorded_size = file_info[0]
            if type(recorded_size) is not int or recorded_size != stat.st_size:
                logger.warning(
                    "candidate preview artifact size no longer matches run %s",
                    run.run_id)
                self._clear_candidate_preview()
                self.window.videoView.set_preview_markers(
                    [], f"Preview: {candidate.label} · not adopted · prediction file changed")
                return
        threshold = run.config.get("min_confidence", 0.0)
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            threshold = 0.0
        threshold = float(threshold)
        if not isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            threshold = 0.0
        key = (id(session), candidate.run_id, ref, stat.st_size, stat.st_mtime_ns,
               raw_preview, threshold)
        self._preview_expected_key = key
        if key == self._preview_loaded_key:
            return
        if self._preview_future is not None and self._preview_future[0] == key:
            return
        self.window.videoView.set_preview_markers([], "")
        if raw_preview:
            future = self._executor.submit(
                _read_raw_candidate_preview, self.adapter, path,
                video.frame_count)
        else:
            future = self._executor.submit(
                _read_legacy_candidate_preview, path, track.track_id,
                run.source_detail)
        self._preview_future = (key, candidate.label, threshold, raw_preview, future)

    def _clear_candidate_preview(self) -> None:
        self._preview_expected_key = None
        self._preview_loaded_key = None
        self.window.videoView.set_preview_markers([], "")

    def _poll_candidate_preview(self) -> None:
        pending = self._preview_future
        if pending is None or not pending[4].done():
            return
        key, label, threshold, raw_preview, future = pending
        self._preview_future = None
        if key != self._preview_expected_key:
            return
        try:
            points = future.result()
        except Exception as error:
            logger.warning("candidate preview unavailable: %s", error)
            self.window.videoView.set_preview_markers(
                [], f"Preview: {label} · not adopted · positions unavailable")
            self._preview_loaded_key = key
            return
        from ai_physics_tracker.gui.video_view import MarkerView

        markers = [
            MarkerView(point.pixel_x, point.pixel_y,
                       "#ff6b6b" if raw_preview and point.confidence < threshold
                       else "#ffb000",
                       source="preview", frame_index=point.frame_index)
            for point in points
        ]
        low_count = sum(
            1 for point in points
            if raw_preview and point.confidence < threshold)
        if not markers:
            suffix = " · no finite AI positions"
        elif low_count:
            suffix = (f" · {len(markers)} AI positions · {low_count} below "
                      "confidence threshold (red)")
        else:
            suffix = f" · {len(markers)} AI positions"
        self.window.videoView.set_preview_markers(
            markers, f"Preview: {label} · not adopted{suffix}")
        self._preview_loaded_key = key

    def _refresh_header(self, session, state, video, track) -> None:
        window = self.window
        project_name = session.project.name
        video_name = video.display_name if video is not None else "No video"
        track_name = track.name if track is not None else "No track"
        zone = "—"
        if video is not None:
            timeline = next(
                (t for t in session.project.timelines
                 if t.video_id == video.video_id), None)
            if timeline is not None:
                start_s = timeline.working_zone[0] / timeline.fps_nominal
                end_s = timeline.working_zone[1] / timeline.fps_nominal
                zone = f"{start_s:.1f}–{end_s:.1f} s"
        saved = "saved" if not session.is_dirty else "unsaved changes"
        context = (f"Project: {project_name} · Video: {video_name} · "
                   f"Object: {track_name} · Range: {zone} · {saved}")

        traj = state.trajectory
        if traj.active_label:
            trajectory_text = (f"Current trajectory: {traj.active_label} AI "
                               f"+ {traj.manual_count} manual position(s)")
        elif traj.manual_count:
            trajectory_text = f"Current trajectory: manual only ({traj.manual_count} position(s))"
        else:
            trajectory_text = "Current trajectory: —"
        if traj.candidate is not None:
            trajectory_text += f"   ·   Preview: {traj.candidate.label} (not adopted)"
        if state.execution.busy:
            kind = state.execution.kind.replace("_", " ")
            window.workflowHeader.setTaskStrip(
                f"{track_name}: {kind} in progress; charts keep the current trajectory")
        else:
            window.workflowHeader.setTaskStrip("")
        window.workflowHeader.setStatus(context, trajectory_text, state.analysis.state)
        window.workflowHeader.setLimitations(state.analysis.limitations)

    # --- C2：系统计划 → 显式执行（与 Advanced 同一入口与校验）---

    def _learning_plan(self, session, track_id, runs):
        from ai_physics_tracker.application.workflow_projection import (
            default_resume_source,
            recommended_learning_plan,
        )
        completed = any(
            r.track_id == track_id and r.task_type == "train"
            and r.status == "completed" for r in runs)
        resume_source = default_resume_source(session, track_id, runs)
        recommendation = None
        if completed:
            recommendation = self._advisor_recommendation(session, track_id, runs)
        return recommended_learning_plan(
            recommendation, first_training=not completed,
            resume_source_run_id=resume_source,
            default_epochs=self.panel.epochsSpinBox.value(),
            default_batch=self.panel.batchSizeSpinBox.value(),
        )

    def _confirm_fixed_check_set(self, session, track_id) -> bool:
        """C1：无有效检查集时预选并请用户确认；KEEP 时停用失效旧集并 freeze。

        P6R-03：被 train run 引用的旧集不删除，只停用（保留历史标签溯源）。
        """
        from ai_physics_tracker.application.workflow_projection import (
            preselect_fixed_check_frames,
        )
        from ai_physics_tracker.gui.fixed_check_dialog import (
            RESULT_CHOOSE,
            RESULT_KEEP,
            FixedCheckConfirmDialog,
        )

        ref_state = session.get_refinement_state(track_id)
        active_series = ref_state.active_series
        series_valid = session.validate_active_validation_series(track_id)[0]
        if active_series is not None and series_valid:
            return False  # 已有有效集合，直接复用
        manual_frames = tuple(p.frame_index for p in session.manual_points(track_id))
        preselect = preselect_fixed_check_frames(manual_frames)
        if not preselect:
            return False  # 标签不足（<4）：不建检查集，学习走无比较路径
        before = session.project
        dialog = FixedCheckConfirmDialog(preselect, len(manual_frames), self.window)
        dialog.frameJumpRequested.connect(self.window.jumpToFrame)
        dialog.exec()
        if dialog.result_choice == RESULT_KEEP:
            if active_series is not None:
                session.set_active_validation_series(track_id, None)
            session.create_validation_series(track_id, "Fixed check frames", preselect)
            self.window.statusBar().showMessage(
                f"Kept {len(preselect)} fixed-check frame(s)")
        elif dialog.result_choice == RESULT_CHOOSE:
            from ai_physics_tracker.gui.validation_dialog import ManageValidationDialog

            ManageValidationDialog(session, track_id, self.window).exec()
        # skip：沿用无 fixed validation 的能力，不建立虚假基准
        return session.project != before

    def _start_learning_with_system_plan(self, session, track_id, runs) -> None:
        """C1+C2：必要时确认预选检查帧，然后把系统计划写入表单并启动。"""
        changed = self._confirm_fixed_check_set(session, track_id)

        def start() -> None:
            if session is not self.window.analysisSession:
                return
            plan = self._learning_plan(session, track_id, session.tracking_runs())
            self.panel.setTrainingMode(plan.training_mode)
            self.panel.epochsSpinBox.setValue(plan.epochs)
            self.panel.batchSizeSpinBox.setValue(plan.batch_size)
            if plan.training_mode == "resume":
                self.panel.setSelectedTrainingRun(plan.resume_from_run_id)
            self._context_key = None
            self.train()

        if changed:
            self.window.projectActions.autosave(
                "fixed-check frames confirmed", after=start)
        else:
            start()

    def _generate_trajectory_with_latest_model(self, session, track_id, runs) -> None:
        """生成轨迹绑定本目标最新完成的模型，不让用户在列表里挑（§12.1）。"""
        latest_train = next(
            (r for r in reversed(runs)
             if r.track_id == track_id and r.task_type == "train"
             and r.status == "completed" and r.model_snapshot),
            None)
        if latest_train is None:
            self.panel.setActivity("Cannot generate: no completed learning run")
            return
        self.panel.setSelectedTrainingRun(latest_train.run_id)
        self._context_key = None
        self.infer()

    def _jump_to_next_attention_frame(self, session, track_id) -> None:
        """跳到下一个待标注/待审核画面（不创建任何数据）。"""
        window = self.window
        review = getattr(window, "reviewActions", None)
        if review is not None and getattr(review, "busy", False):
            return  # 审核队列自己负责导航
        state = getattr(self, "_current_workflow_state", None)
        if state is not None and state.trajectory.candidate is not None:
            # 候选待审：打开审核队列（显式筛查入口）
            candidate_run = state.trajectory.candidate.run_id
            window.reviewActions.requestMining(candidate_run)
            return
        # 标注路径：跳到第一个无 manual 点的帧
        manual_frames = {p.frame_index for p in session.manual_points(track_id)}
        track = next((t for t in session.tracks if t.track_id == track_id), None)
        if track is None:
            return
        timeline = next(
            (t for t in session.project.timelines if t.video_id == track.video_id),
            None)
        if timeline is None:
            return
        for frame in range(timeline.working_zone[0], timeline.working_zone[1] + 1):
            if frame not in manual_frames:
                window.jumpToFrame(frame)
                return

    def _adopt_candidate(self, session, track_id, facts) -> None:
        """[采用此轨迹]：单次影响确认 + 既有原子事务（R1 F4：不再叠加
        history 入口的第二层 run-ID 确认；该确认保留给 history 路径）。"""
        candidate_run_id = facts.candidate.run_id
        manual_count = facts.manual_count
        newline = "\n"
        try:
            if facts.has_active_result:
                message = (
                    f"Adopt {facts.candidate.label} for this object?{newline}{newline}"
                    f"This replaces the currently adopted {facts.active_label} AI "
                    f"result.{newline}{manual_count} manual point(s) stay and keep "
                    f"priority.{newline}Charts will need an update afterwards.")
                if not self._confirm_adopt(message):
                    return
                record = session.replace_active_infer_run(track_id, candidate_run_id)
                self.window.statusBar().showMessage(
                    f"Adopted {facts.candidate.label}: {record.point_count} active "
                    f"points, {record.superseded_count} superseded by manual")
            else:
                message = (
                    f"Adopt {facts.candidate.label} for this object?{newline}{newline}"
                    f"{manual_count} manual point(s) stay and keep priority."
                    f"{newline}Charts will need an update afterwards.")
                if not self._confirm_adopt(message):
                    return
                record = session.activate_infer_run(track_id, candidate_run_id)
                self.window.statusBar().showMessage(
                    f"Adopted {facts.candidate.label}: {record.point_count} active "
                    f"points, {record.superseded_count} superseded by manual")
        except Exception as error:
            self.panel.appendLog(
                user_messages.activation_failure(str(error)).full_text())
            self.panel.setActivity("Adoption failed — current trajectory unchanged")
            return
        self.window._refreshMarkers()
        self.window._refreshHistoryButtons()
        self.window.projectActions.autosave("trajectory adopted")
        self._context_key = None
        self.refresh()

    def _confirm_adopt(self, message: str) -> bool:
        from PySide6.QtWidgets import QMessageBox

        # 测试环境（offscreen conftest）将 question 桩化为 Discard；这里用
        # Yes/No 对话框，测试经 monkeypatch 控制回答
        reply = QMessageBox.question(
            self.window, "Adopt trajectory", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        return reply == QMessageBox.StandardButton.Yes

    def _onCardAction(self, action_id: str) -> None:
        """任务卡动作分发：全部走既有执行入口（与 Advanced 同一验证路径）。"""
        window = self.window
        session = window.analysisSession
        if action_id == "view_analysis":
            window.setWorkspace("analysis")
            return
        if action_id == "update_charts":
            window.setWorkspace("analysis")
            window.chartActions.recompute()
            return
        if action_id == "cancel_task":
            if self.pending:
                self.cancel()
            elif window.frameSelectionActions.busy:
                window.frameSelectionActions.cancel()
            elif getattr(self.window, "reviewActions", None) and self.window.reviewActions.busy:
                self.window.reviewActions.cancelMining()
            return
        if action_id == "pick_frames":
            window.setWorkspace("acquire")
            window.frameSelectionActions.requestSuggestion(10, "kmeans")
            return
        if action_id == "create_track":
            window.addTrackButton.click()
            return
        if action_id == "save_project":
            window.projectActions.save()
            return
        if action_id == "add_video":
            window.projectActions.openVideo()
            return
        if action_id == "set_scale":
            window.beginCalibrationFlow("acquire")
            return
        if action_id == "create_experiment":
            window.projectActions.createPendulumExperiment()
            return
        if action_id == "guided_marking":
            window.beginExperimentAnnotation()
            return
        if action_id == "setup_fixed_pivot":
            window.setWorkspace("setup")
            window.beginPivotPick()
            return
        if action_id == "setup_true_vertical":
            window.setWorkspace("setup")
            window.beginVerticalPick()
            return
        if action_id == "setup_physical":
            window.openPhysicalDialog()
            return
        if action_id == "set_release_frame":
            window._setReleaseToCurrentFrame()
            return
        track_id = window.selectedTrackId
        if session is None or track_id is None:
            return
        runs = session.tracking_runs()

        if action_id == "confirm_check_frames":
            window.setWorkspace("acquire")
            if self._confirm_fixed_check_set(session, track_id):
                window.projectActions.autosave("fixed-check frames confirmed")
            self._context_key = None
            self.refresh()
            return
        if action_id in ("start_learning", "retry_learning", "continue_optimizing"):
            window.setWorkspace("acquire")
            self._start_learning_with_system_plan(session, track_id, runs)
            return
        if action_id == "generate_trajectory":
            window.setWorkspace("acquire")
            self._generate_trajectory_with_latest_model(session, track_id, runs)
            return
        if action_id == "review_accept":
            window.reviewActions.acceptCurrent()
            return
        if action_id == "review_correct":
            window.reviewActions.startCorrectCurrent()
            return
        if action_id == "review_skip":
            window.reviewActions.skipCurrent()
            return
        if action_id == "review_previous":
            window.reviewActions.previousCandidate()
            return
        if action_id == "review_next":
            window.reviewActions.nextCandidate()
            return
        if action_id == "finish_checking":
            window.reviewActions.finishChecking()
            return
        if action_id == "cancel_placement":
            window.reviewActions.cancelCorrectMode()
            self._context_key = None
            self.refresh()
            return
        if action_id == "inspect_trajectory":
            window.setWorkspace("acquire")
            from ai_physics_tracker.application.workflow_projection import (
                trajectory_facts,
            )
            facts = trajectory_facts(session, track_id, runs)
            # 检查对象 = 当前候选（设计 §6.5“检查对象只有一个”），
            # 绝不能落到注册序最旧的 completed infer run（R1 F1）
            if facts.candidate is not None:
                self.window.reviewActions.requestMining(facts.candidate.run_id)
            else:
                latest_infer = next(
                    (r for r in reversed(runs)
                     if r.track_id == track_id and r.task_type == "infer"
                     and r.status == "completed"), None)
                if latest_infer is not None:
                    self.window.reviewActions.requestMining(latest_infer.run_id)
            return
        if action_id == "recheck_trajectory":
            window.setWorkspace("acquire")
            from ai_physics_tracker.application.workflow_projection import (
                trajectory_facts,
            )
            facts = trajectory_facts(session, track_id, runs)
            if facts.candidate is not None:
                self.window.reviewActions.requestMining(
                    facts.candidate.run_id, force=True)
            return
        if action_id == "adopt_trajectory":
            from ai_physics_tracker.application.workflow_projection import (
                trajectory_facts,
            )
            facts = trajectory_facts(session, track_id, runs)
            if facts.candidate is not None:
                self._adopt_candidate(session, track_id, facts)
            return
        if action_id == "label_frame":
            self._jump_to_next_attention_frame(session, track_id)
            return
        logger.warning("unhandled task-card action: %s", action_id)

    def train(self) -> None:
        # 仅 Resume 模式携带 source；Restart 带选中项会被 prepare 拒绝（review Blocker 1）
        resume_source = (self.panel.selectedTrainingRunId()
                         if self.panel.trainingMode() == "resume" else None)
        self._start(self.panel.trainingParameters(),
                    training_mode=self.panel.trainingMode(),
                    resume_from_run_id=resume_source)

    def infer(self) -> None:
        self._start(self.panel.inferenceParameters(), self.panel.selectedTrainingRunId())

    def _advisor_recommendation(self, session, track_id, runs):
        """从活动会话采集不可变快照并计算 Advisor 建议（纯计算，不落盘）。"""
        try:
            return recommend_training_action(self._build_advisor_input(session, track_id, runs))
        except Exception as error:  # Advisor 属辅助信息，采集失败不阻塞面板
            logger.warning("advisor input failed: %s", error)
            return None

    def _build_advisor_input(self, session, track_id, runs) -> AdvisorInput:
        """委托 Qt-free 采集器（P6R-04）；GUI 只补充 pending 任务与表单参数。"""
        return collect_advisor_input(
            session, track_id, runs,
            has_active_task=self.pending or any(
                r.status in {"pending", "running"} for r in runs),
            requested_batch_size=self.panel.batchSizeSpinBox.value(),
            requested_epochs=self.panel.epochsSpinBox.value(),
            resume_source_run_id=self.panel.selectedTrainingRunId(),
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
            self.window.projectActions.autosave("trajectory activated")
        except Exception as error:
            QMessageBox.critical(self.window, "Activation Failed", user_messages.activation_failure(str(error)).full_text())
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
            self.window.projectActions.autosave("trajectory replaced")
        except Exception as error:
            QMessageBox.critical(self.window, "Replacement Failed", user_messages.activation_failure(str(error)).full_text())
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
            self.window.projectActions.autosave("active AI trajectory cleared")
        except Exception as error:
            QMessageBox.critical(self.window, "Clear Failed", user_messages.activation_failure(str(error)).full_text())
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
        self._poll_candidate_preview()
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
        # Phase 5.7 §13：失败结论回答三问；原始错误进日志，卡片给恢复出口。
        # ux 标题作为 activity 文案，后续 _finish(f"Failed: …") 调用点替换为该标题。
        if self._request.run.task_type == "train":
            self._ux_failure = user_messages.training_failure(
                error, unsaved_changes=self._session.is_dirty)
        else:
            self._ux_failure = user_messages.inference_failure(error)
        for line in (*self._ux_failure.body, f"Next: {self._ux_failure.next_hint}"):
            self.panel.appendLog(line)
        if self._handle is not None and self._handle.is_alive():
            self._failure_error = error
            self._cancelling = True
            self.panel.setActivity("Stopping failed task")
            self._future = self._executor.submit(cancel_tracking_job, self._handle, self._request)
            return
        self._finish(getattr(self, "_ux_failure", None) and self._ux_failure.title
                     or f"Failed: {error}")

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
        self._context_key = None  # 卡片立即切到“正在停止”（R1 F7b）
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
        if self._failure_error:
            ux = getattr(self, "_ux_failure", None) or user_messages.inference_failure(
                self._failure_error)
            self._finish(ux.title)
        else:
            self._finish(user_messages.task_cancelled(
                self._request.run.task_type).title)

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
        if message == "Completed" and self.window.analysisSession is session \
                and finished is not None and finished.task_type == "train":
            evaluation = finished.extra_fields.get("evaluation")
            if isinstance(evaluation, dict) and evaluation.get("status") == "unavailable":
                from ai_physics_tracker.application.user_messages import (
                    evaluation_unavailable,
                )
                ux = evaluation_unavailable()
                self.panel.setActivity(ux.title)
                for line in (*ux.body, f"Next: {ux.next_hint}"):
                    self.panel.appendLog(line)
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
        self._preview_future = None
        self._clear_candidate_preview()
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
        self._running_experiment_id = None
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
        if session is None:
            self.panel.setSuggestStatus("No track selected")
            return
        # P1.2:experiment 存在于当前视频时帧集归 experiment(契约 §3),
        # 排除集为四 role 并集;结果回填后持久化到 experiment.frame_set。
        experiment = next(
            (
                item
                for item in session.pendulum_experiments()
                if item.video_id == self.window.activeVideoId
            ),
            None,
        )
        try:
            if experiment is not None:
                owner_id = experiment.experiment_id
                job_request = prepare_experiment_frame_selection(
                    session, owner_id, n_frames, algorithm=algorithm
                )
            else:
                track_id = self.window.selectedTrackId
                if track_id is None:
                    self.panel.setSuggestStatus("No track selected")
                    return
                owner_id = track_id
                job_request = prepare_frame_selection_request(
                    session, track_id, n_frames, algorithm=algorithm
                )
        except Exception as error:
            self.panel.setSuggestStatus(f"Cannot start: {error}")
            return

        request_id = _uuid4()
        self._request_id = request_id
        self._job_request = job_request
        self._running_track_id = owner_id
        self._running_experiment_id = (
            experiment.experiment_id if experiment is not None else None
        )
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
        if self._running_experiment_id is not None and result.suggested_frames:
            # 契约 §3:共享帧集持久化到 experiment(可撤销事务)
            session = self.window.analysisSession
            if session is not None:
                try:
                    session.set_experiment_frame_set(
                        self._running_experiment_id,
                        ExperimentFrameSet(
                            frames=tuple(result.suggested_frames),
                            algorithm=result.request_algorithm,
                            created_at=utc_now(),
                        ),
                    )
                    self.panel.setSuggestStatus(
                        f"Saved as shared frame set "
                        f"({len(result.suggested_frames)} frames, undoable)")
                except Exception as error:
                    self.panel.setSuggestStatus(
                        f"Saved result could not persist: {error}")
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
        self._running_experiment_id = None
        self._reset()
        self._refreshEnabled()

    def _finish_error(self, message: str) -> None:
        self.panel.setSuggestStatus(f"Failed: {message}")
        self._result_track_id = None
        self._cached_result = None
        self._cached_status = ""
        self._running_experiment_id = None
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
