"""Phase 5.3 困难帧挖掘与建议帧审核 GUI 编排控制器。

职责划分：
1. 监听 Task history 的 run 选择；
2. 校验当前 run 是否为当前 track 的 completed infer run；
3. 协调后台 DifficultFrameRunner 执行挖掘任务，处理进度、结果与中性取消；
4. 构造并提交 ActiveReviewBatch，实例化/同步 ReviewQueueController；
5. 驱动前后跳帧导航，并在跳帧时经 window.seekFrame 定位画面。
"""

from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.application.difficult_frame_job import (
    DifficultFrameJobRequest,
    DifficultFrameResult,
    DifficultFrameRunner,
    prepare_difficult_frame_request,
    read_difficult_frame_result,
)
from ai_physics_tracker.application.difficult_frames import MiningParams
from ai_physics_tracker.application.project_session import ProjectSessionError
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    ReviewCandidate,
    ReviewQueueController,
)
from ai_physics_tracker.application.tracking_types import TaskProgress, TaskResult

if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow
    from ai_physics_tracker.gui.task_panel import TaskPanel

logger = logging.getLogger(__name__)


class DifficultFrameReviewActions(QObject):
    """协调困难帧挖掘与建议帧审核队列。"""

    def __init__(
        self,
        window: MainWindow,
        panel: TaskPanel,
        runner: DifficultFrameRunner | None = None,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.panel = panel
        self._runner = runner or DifficultFrameRunner()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="review-mining")

        self._selected_run_id: UUID | None = None
        self._active_run_id: UUID | None = None
        self._request_id: UUID | None = None
        self._job_request: DifficultFrameJobRequest | None = None
        self._handle: Any = None
        self._start_future: Future | None = None
        self._result_future: Future[DifficultFrameResult] | None = None

        self._controller: ReviewQueueController | None = None
        self._running_track_id: UUID | None = None
        self._closed = False

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)

        # 信号连接
        self.panel.runSelected.connect(self.onRunSelected)
        self.panel.mineDifficultRequested.connect(self.requestMining)
        self.panel.mineCancelRequested.connect(self.cancelMining)
        self.panel.reviewNextRequested.connect(self.nextCandidate)
        self.panel.reviewPrevRequested.connect(self.previousCandidate)
        self.panel.reviewAcceptRequested.connect(self.acceptCurrent)
        self.panel.reviewSkipRequested.connect(self.skipCurrent)
        self.panel.reviewCorrectRequested.connect(self.startCorrectCurrent)
        self.panel.deleteManualPointRequested.connect(self.deleteCurrentManualPoint)
        self.panel.reviewCandidateJumpRequested.connect(self.jumpToFrame)
        window.selectedTrackChanged.connect(self.onSelectedTrackChanged)
        window.projectChanged.connect(self.onProjectChanged)
        window.analysisChanged.connect(self.refresh)
        window.closing.connect(self.shutdown)

    @property
    def adapter(self) -> Any:
        return self._runner.adapter

    @adapter.setter
    def adapter(self, value: Any) -> None:
        self._runner.adapter = value

    @property
    def runner(self) -> DifficultFrameRunner:
        return self._runner

    @runner.setter
    def runner(self, value: DifficultFrameRunner) -> None:
        self._runner = value

    @property
    def busy(self) -> bool:
        return self._request_id is not None

    @property
    def controller(self) -> ReviewQueueController | None:
        return self._controller

    @property
    def selected_run_id(self) -> UUID | None:
        return self._selected_run_id

    def onRunSelected(self, run_id: UUID | None) -> None:
        """用户在 Task history 中选择一个 run 时触发。"""
        self._selected_run_id = run_id
        session = self.window.analysisSession
        if session is None:
            self._controller = None
            self.panel.setReviewBatch(None, None)
            self._refresh_mining_enabled()
            return

        run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
        selected_track = self.window.selectedTrackId
        if (
            run is not None
            and run.task_type == "infer"
            and run.status == "completed"
            and selected_track is not None
            and run.track_id == selected_track
        ):
            state = session.get_suggested_frame_review(run.run_id)
            if state is not None and state.active_batch is not None:
                self._controller = ReviewQueueController(session, run.run_id)
                self._active_run_id = run.run_id
                self._sync_panel_with_controller()
            else:
                self._controller = None
                self.panel.setReviewBatch(None, None)
        else:
            self._controller = None
            self.panel.setReviewBatch(None, None)

        self._refresh_mining_enabled()

    def refresh(self) -> None:
        """刷新当前选中 run 与会话状态下的审核与挖掘可用性。"""
        self._refresh_mining_enabled()
        if self._controller is not None:
            self._sync_panel_with_controller()

    def _refresh_mining_enabled(self) -> None:
        session = self.window.analysisSession
        track_id = self.window.selectedTrackId
        run_id = self._selected_run_id

        if self.busy:
            self.panel.setMineEnabled(False, "Difficult frame mining is in progress")
            return
        if (
            (hasattr(self.window, "trackingActions") and self.window.trackingActions.pending)
            or (hasattr(self.window, "frameSelectionActions") and self.window.frameSelectionActions.busy)
            or self.window.projectActions.busy
        ):
            self.panel.setMineEnabled(False, "Another background task is in progress")
            return

        if session is None:
            self.panel.setMineEnabled(False, "No project open")
            return
        if session.project_root is None:
            self.panel.setMineEnabled(False, "Save the project before mining")
            return
        if track_id is None:
            self.panel.setMineEnabled(False, "No track selected")
            return
        if run_id is None:
            self.panel.setMineEnabled(False, "Select a completed inference run from Task history")
            return

        run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
        if run is None:
            self.panel.setMineEnabled(False, "Inference run not found")
            return
        if run.task_type != "infer":
            self.panel.setMineEnabled(False, f"Selected task is {run.task_type}, not infer")
            return
        if run.status != "completed":
            self.panel.setMineEnabled(False, f"Inference run status is {run.status}, not completed")
            return
        if run.track_id != track_id:
            self.panel.setMineEnabled(False, "Selected run belongs to another track")
            return

        prediction_ref = run.extra_fields.get("prediction_path")
        if not prediction_ref or not isinstance(prediction_ref, str):
            self.panel.setMineEnabled(False, "Run has no stored raw prediction artifact")
            return

        self.panel.setMineEnabled(True, "")

    def requestMining(self, run_id: UUID | None = None, params: MiningParams | None = None) -> None:
        """用户点击挖掘困难帧时发起后台任务（Phase 5.2/5.3）。"""
        if (
            self.busy
            or self._closed
            or (hasattr(self.window, "trackingActions") and self.window.trackingActions.pending)
            or (hasattr(self.window, "frameSelectionActions") and self.window.frameSelectionActions.busy)
            or self.window.projectActions.busy
        ):
            return
        session = self.window.analysisSession
        target_run_id = run_id or self._selected_run_id
        if session is None or target_run_id is None:
            return

        mining_params = params or MiningParams(
            top_n=self.panel.mineTopNSpinBox.value(),
            min_gap_s=self.panel.mineMinGapSpinBox.value(),
        )

        try:
            job_request = prepare_difficult_frame_request(
                session, target_run_id, mining_params
            )
        except Exception as error:
            self.panel.setMineStatus(f"Cannot start: {error}")
            return

        request_id = uuid4()
        self._request_id = request_id
        self._job_request = job_request
        self._running_track_id = job_request.mining_request.track_id
        self._active_run_id = target_run_id

        self.panel.setMineStatus("Mining difficult frames…")
        self.panel.setMineBusy(True)
        self._start_future = self._executor.submit(self._runner.start, job_request, request_id)
        self._timer.start()

    def cancelMining(self) -> None:
        """用户点击取消挖掘。"""
        if not self.busy:
            return
        self._cancel_active_task()
        self._finish_cancelled("Mining cancelled")

    def _cancel_active_task(self) -> None:
        handle = self._handle
        start = self._start_future
        if handle is not None:
            self._executor.submit(handle.cancel)
        elif start is not None:
            self._executor.submit(lambda: start.result().cancel() if start.done() else None)

    def _poll(self) -> None:
        if self._closed or not self.busy:
            self._timer.stop()
            return

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

        messages = self._handle.poll_messages(limit=200)
        for message in messages:
            if isinstance(message, TaskProgress):
                if message.message:
                    self.panel.setMineStatus(message.message)
                elif message.total_steps > 0:
                    pct = int(100 * message.step / message.total_steps)
                    self.panel.setMineStatus(f"Mining… {pct}%")
            elif isinstance(message, TaskResult):
                payload = message.payload or {}
                if payload.get("status") == "cancelled":
                    self._finish_cancelled("Mining cancelled")
                    return
                elif not message.success:
                    self._finish_error(message.error or "Mining failed")
                    return

        if not self._handle.is_alive():
            if self._result_future is None:
                request_id = self._request_id
                project_root = self._job_request.project_root if self._job_request else None
                if project_root is not None and request_id is not None:
                    self._result_future = self._executor.submit(
                        read_difficult_frame_result, project_root, request_id
                    )
        if self._result_future is not None and self._result_future.done():
            try:
                result = self._result_future.result()
                self._finish_success(result)
            except Exception as error:
                self._finish_error(str(error))

    def _finish_success(self, result: DifficultFrameResult) -> None:
        self._timer.stop()
        session = self.window.analysisSession
        run_id = self._active_run_id

        # 上下文复核（R8）
        if (
            session is None
            or run_id is None
            or self.window.selectedTrackId != self._running_track_id
            or not any(r.run_id == run_id for r in session.tracking_runs())
        ):
            logger.warning("Context changed during mining; discarding result for run %s", run_id)
            self._reset()
            self._refresh_mining_enabled()
            return

        # 转换为 ActiveReviewBatch 并原子更新会话
        batch = result.to_active_batch()
        session.set_active_review_batch(run_id, batch)

        # 实例化控制器并更新 UI
        self._controller = ReviewQueueController(session, run_id)
        self.panel.setMineStatus(f"Found {result.actual_n} difficult frame(s)")
        self._sync_panel_with_controller()

        # 跳到首个候选帧
        if self._controller.current_frame_index is not None:
            self.jumpToFrame(self._controller.current_frame_index)

        self._reset()
        self._refresh_mining_enabled()

    def _finish_cancelled(self, message: str = "Mining cancelled") -> None:
        self._timer.stop()
        self.panel.setMineStatus(message)
        self._reset()
        self._refresh_mining_enabled()

    def _finish_error(self, message: str) -> None:
        self._timer.stop()
        self.panel.setMineStatus(f"Failed: {message}")
        self._reset()
        self._refresh_mining_enabled()

    def _reset(self) -> None:
        self._timer.stop()
        self._request_id = None
        self._job_request = None
        self._handle = None
        self._start_future = None
        self._result_future = None
        self._running_track_id = None
        self.panel.setMineBusy(False)

    def _sync_panel_with_controller(self) -> None:
        ctrl = self._controller
        if ctrl is None:
            self.panel.setReviewBatch(None, None)
            return
        self.panel.setReviewBatch(ctrl, ctrl.summary)

    # --- 队列导航与处置操作 ---

    def nextCandidate(self) -> None:
        if self._controller is None:
            return
        c = self._controller.next_candidate()
        if c is not None:
            self.jumpToFrame(c.frame_index)
        self._sync_panel_with_controller()

    def previousCandidate(self) -> None:
        if self._controller is None:
            return
        c = self._controller.previous_candidate()
        if c is not None:
            self.jumpToFrame(c.frame_index)
        self._sync_panel_with_controller()

    def jumpToFrame(self, frame_index: int) -> None:
        if self._controller is not None:
            self._controller.select_frame(frame_index)
            self._sync_panel_with_controller()
        # 跳帧经 seekFrame 钳位在 working zone 内呈现给用户
        self.window.seekFrame(frame_index)

    def acceptCurrent(self) -> None:
        if self._controller is None or self._controller.current_candidate is None:
            return
        try:
            self._controller.accept_current(auto_advance=True)
        except (ProjectSessionError, ValueError) as error:
            logger.error("accept suggested frame failed: %s", error)
            self.window.statusBar().showMessage(f"Accept failed: {error}")
            return
        if self._controller.current_frame_index is not None:
            self.jumpToFrame(self._controller.current_frame_index)
        self._sync_panel_with_controller()
        self.window._refreshHistoryButtons()
        self.window._refreshDeletePointButton()
        self.window._register_mark_for_autosave()

    def skipCurrent(self) -> None:
        if self._controller is None or self._controller.current_candidate is None:
            return
        try:
            self._controller.skip_current(auto_advance=True)
        except (ProjectSessionError, ValueError) as error:
            logger.error("skip suggested frame failed: %s", error)
            self.window.statusBar().showMessage(f"Skip failed: {error}")
            return
        if self._controller.current_frame_index is not None:
            self.jumpToFrame(self._controller.current_frame_index)
        self._sync_panel_with_controller()
        self.window._refreshHistoryButtons()
        self.window._refreshDeletePointButton()
        self.window._register_mark_for_autosave()

    @property
    def is_correcting(self) -> bool:
        return self._controller is not None and self._controller.is_correcting

    def startCorrectCurrent(self) -> None:
        if self._controller is None or self._controller.current_candidate is None:
            return
        c = self._controller.current_candidate
        if self.window.presented_frame_index != c.frame_index:
            self.window.seekFrame(c.frame_index)
        self._controller.set_correcting(True)
        self.window.videoView.set_annotation_mode(True)
        self.window.statusBar().showMessage(
            f"Correct Mode: Click on video to place corrected point for Frame {c.frame_index} (Esc to cancel)"
        )
        self._sync_panel_with_controller()

    def cancelCorrectMode(self) -> None:
        if self._controller is not None and self._controller.is_correcting:
            self._controller.set_correcting(False)
            self._sync_panel_with_controller()
        self.window.videoView.set_annotation_mode(False)

    def handleCorrectClick(self, pixel_x: float, pixel_y: float) -> bool:
        if not self.is_correcting:
            return False
        ctrl = self._controller
        if ctrl is None or ctrl.current_candidate is None:
            return False
        c = ctrl.current_candidate
        if self.window.presented_frame_index != c.frame_index:
            self.window.statusBar().showMessage(
                f"Ignored click: current frame {self.window.presented_frame_index} does not match candidate frame {c.frame_index}"
            )
            return False
        try:
            ctrl.correct_current(pixel_x, pixel_y, auto_advance=True)
        except (ProjectSessionError, ValueError) as error:
            logger.error("correct suggested frame failed", exc_info=True)
            self.window.statusBar().showMessage(f"Correction failed: {error}")
            return False
        if ctrl.current_frame_index is not None:
            self.jumpToFrame(ctrl.current_frame_index)
        self._sync_panel_with_controller()
        self.window.statusBar().showMessage(
            f"Frame {c.frame_index} corrected at ({pixel_x:.1f}, {pixel_y:.1f})"
        )
        return True

    def deleteCurrentManualPoint(self) -> None:
        self.window._deleteCurrentManualPoint()

    def onSelectedTrackChanged(self, *_args) -> None:
        if self.is_correcting:
            self.cancelCorrectMode()
        current = self.window.selectedTrackId
        if self.busy and current != self._running_track_id:
            self._cancel_active_task()
            self._reset()
            self.panel.setMineStatus("")
        self.onRunSelected(self._selected_run_id)

    def onProjectChanged(self, *_args) -> None:
        if self.is_correcting:
            self.cancelCorrectMode()
        if self.busy:
            self._cancel_active_task()
            self._reset()
        self.panel.setMineStatus("")
        self._controller = None
        self._selected_run_id = None
        self.panel.setReviewBatch(None, None)
        self._refresh_mining_enabled()

    def shutdown(self) -> None:
        self._closed = True
        self._timer.stop()
        self._cancel_active_task()
        self._reset()
        self._executor.shutdown(wait=False, cancel_futures=False)
