"""P1.3-S6 模型动作控制器:联合训练 / 教师导入 / runtime 自检(Qt GUI 层)。

执行边界:prepare/verify/register/import/apply 是 session 应用动作(GUI
线程);训练与自检经 ``ExternalWorkerRunner`` 外部 worker 子进程执行,
QTimer 轮询句柄——与 FrameSelectionActions 相同的 handle/poll 语义。

超时策略(i3①,S1 review 交接):训练时长不可预估,本层不设自动超时;
用户取消是唯一中止入口,且必须经 ``handle.cancel()``(它置位
``_cancel_requested`` 才能拒绝迟到 success)。未来若加自动超时,同样
必须走 ``cancel()``。elapsed_s 记入 run extras(i3②)。
"""

import logging
import sys
from pathlib import Path
from uuid import UUID
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.application.experiment_training_job import (
    prepare_experiment_training,
    verify_experiment_training_result,
)
from ai_physics_tracker.application.project_session import (
    ProjectSessionError,
)
from ai_physics_tracker.domain.tracking_run import (
    mark_run_cancelled,
    mark_run_failed,
)
from ai_physics_tracker.application.model_worker import (
    ModelWorkerError,
    ModelWorkerRunner,
)

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 250


class ModelActions(QObject):
    """experiment 联合训练、teacher import 与模型自检的 GUI 控制器。"""

    def __init__(
        self,
        window,
        runtime_python: str | Path | None = None,
        *,
        runner_factory=None,
    ) -> None:
        super().__init__(window)
        self.window = window
        self._runtime_python = str(runtime_python or sys.executable)
        # 测试缝:注入假 runner;产品恒为 ExternalWorkerRunner
        self._runner_factory = runner_factory or (
            lambda: ModelWorkerRunner(self._runtime_python)
        )
        self._activity_text = "Idle"
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._handle = None
        self._job_kind: str | None = None   # "train" | "selftest"
        self._train_run = None
        self._train_request = None
        self._job_dir: Path | None = None
        self._selftest_model_id: UUID | None = None
        self._selftest_on_success: Callable[[], None] | None = None
        self._session = None                 # B1:启动时的 session 身份
        self._user_cancel = False            # M1:取消语义(强杀→cancelled 而非 failed)
        # HR 2026-09-28:模型任务接 Activity 区(Cancel 共用面板按钮)
        panel = getattr(window, "trackingActions", None)
        self._panel = panel.panel if panel is not None else None
        if self._panel is not None:
            self._panel.cancelRequested.connect(self._onCancelRequested)

    def _onCancelRequested(self) -> None:
        """面板 Cancel:tracking 在途时归 trackingActions(先连接者),
        model 在途时归本控制器;两者都空闲则 no-op。"""

        if self.busy:
            self.cancel()

    @property
    def activity_text(self) -> str:
        return self._activity_text

    def _set_activity(self, text: str, *, running: bool | None = None) -> None:
        self._activity_text = text
        if self._panel is not None:
            self.window.trackingActions._context_key = None
            self.window.trackingActions.refresh()
            self._panel.setActivity(text)
            # running 缺省跟随当前 busy;终态文案(Completed/Failed/Cancelled)
            # 由调用方传 running=False,避免 reset 顺序把 Cancel 留在可用态
            self._panel.cancelButton.setEnabled(
                self.busy if running is None else running)

    # ------------------------------------------------------------------
    # busy / 查询
    # ------------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._handle is not None

    def shutdown(self) -> None:
        """窗口关闭:在途 job 取消并回收(取消是拒绝迟到 success 的唯一入口)。"""

        self._timer.stop()
        self._selftest_on_success = None
        if self._handle is not None:
            self._handle.cancel()

    # ------------------------------------------------------------------
    # 联合训练
    # ------------------------------------------------------------------

    def runJointTraining(self) -> None:
        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            self.window.statusBar().showMessage(
                "Joint training needs a pendulum experiment on the current video")
            return
        if self.busy or self.window.projectActions.busy:
            self.window.statusBar().showMessage(
                "A model task is already running")
            return
        # F1(S6 review):与其他在途任务互斥(frame selection 改标注会使
        # digest stale,白烧一次训练)
        tracking = getattr(self.window, "trackingActions", None)
        if tracking is not None and tracking.pending:
            self.window.statusBar().showMessage(
                "Cancel the active AI task before joint training")
            return
        frames = getattr(self.window, "frameSelectionActions", None)
        if frames is not None and frames.busy:
            self.window.statusBar().showMessage(
                "Cancel frame selection before joint training")
            return
        try:
            run, request = prepare_experiment_training(
                session, experiment.experiment_id
            )
        except ProjectSessionError as error:
            # HR 反馈(2026-09-28):状态栏消息一闪而过被读作"死按钮";
            # 用户发起动作的失败用模态框,必须被看到
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self.window, "Cannot start joint training", str(error))
            self.window.statusBar().showMessage(f"Cannot start: {error}")
            return
        params = dict(request.params_config)
        device = params.pop("device", "cpu")
        if device == "auto":
            device = "cpu"  # GUI 默认 CPU;mps/cuda 经高级设置接入属后续
        try:
            handle = self._runner_factory().start_training(
                session.project_root, request, device=device
            )
        except (ModelWorkerError, OSError) as error:
            # M2/F5(a)(S6 review):prepare 已登记 pending run;启动失败必须
            # 回写 failed,否则 active-run 守卫把该 experiment 永久锁死
            session.update_tracking_run(mark_run_failed(run, str(error)))
            self.window.statusBar().showMessage(f"Cannot start: {error}")
            self.window.projectActions.refresh()
            return
        from ai_physics_tracker.domain.tracking_run import mark_run_running

        session.update_tracking_run(mark_run_running(run))
        self._handle = handle
        self._job_kind = "train"
        self._train_run = run
        self._train_request = request
        self._job_dir = (
            session.project_root / "data" / "engines" / str(run.run_id)
        )
        self._session = session
        self._timer.start()
        self._set_activity("Training (external worker)")
        self.window.statusBar().showMessage(
            f"Joint training run {run.run_id} started on {device} "
            "(external worker; logs in the run directory)")
        self.window.projectActions.refresh()

    # ------------------------------------------------------------------
    # runtime 自检
    # ------------------------------------------------------------------

    def trainWithCurrentLabels(self) -> None:
        """显式训练按钮：必要时确认检查帧，确认后继续同一训练入口。"""

        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        if self.busy or self.window.projectActions.busy or any(
                getattr(self.window, name, None) is not None and getattr(self.window, name).busy
                for name in ("frameSelectionActions", "experimentInferenceActions")):
            self.window.statusBar().showMessage("Finish or cancel the active task first")
            return
        from ai_physics_tracker.application.annotation_join import fixed_check_status

        if not fixed_check_status(session.project, experiment)[0]:
            if not self.freezeFixedCheck():
                return
        self.window._exitExperimentGuide()
        self.runJointTraining()

    def freezeFixedCheck(self) -> bool:
        """冻结共享固定检查帧集(P1.3-S6 最小 GUI 入口,C1 预选+用户确认)。

        P1.2 S4 只交付了 session 动作;无入口则联合训练(fixed check 是
        prepare 的硬前置)无法从界面走通。预选按 §6.3 确定性规则,用户
        在确认框中看到具体帧号才冻结。
        """

        session = self.window.analysisSession
        experiment = self.window.currentPendulumExperiment()
        if session is None or experiment is None:
            return False
        if self.busy or self.window.projectActions.busy:
            self.window.statusBar().showMessage("A model task is running")
            return False
        from ai_physics_tracker.application.annotation_join import (
            join_complete_frames,
        )
        from ai_physics_tracker.application.workflow_projection import (
            preselect_fixed_check_frames,
        )
        from PySide6.QtWidgets import QMessageBox

        complete = join_complete_frames(
            session.project, experiment
        ).complete_frame_indices
        if not complete:
            self.window.statusBar().showMessage(
                "No complete (4/4) frames to freeze; finish guided marking first")
            return False
        frames = preselect_fixed_check_frames(complete)
        answer = QMessageBox.question(
            self.window, "Freeze fixed-check frames",
            f"Freeze these complete frames as the shared fixed-check set?\n\n"
            f"{list(frames)}\n\n"
            "They are excluded from training and kept for comparison; "
            "label edits invalidate the set until you re-freeze.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        try:
            session.freeze_experiment_fixed_check(experiment.experiment_id, frames)
        except ProjectSessionError as error:
            self.window.statusBar().showMessage(f"Cannot freeze: {error}")
            return False
        self.window.statusBar().showMessage(
            f"Fixed-check set frozen: {list(frames)}")
        self.window.projectActions.refresh()
        return True

    def runSelftest(
        self, model_id: UUID, *, on_success: Callable[[], None] | None = None,
    ) -> None:
        from ai_physics_tracker.application.teacher_models import (
            build_model_selftest_payload,
        )

        session = self.window.analysisSession
        if session is None:
            self.window.statusBar().showMessage("Self-test needs an open project")
            return
        if self.busy or self.window.projectActions.busy:
            self.window.statusBar().showMessage(
                "A model task is already running")
            return
        model = next(
            (m for m in session.project.model_references if m.model_id == model_id),
            None,
        )
        if model is None:
            return
        video = next(
            (v for v in session.project.videos if v.video_id == model_source_video(model, session)),
            None,
        )
        video_path = session.video_path(video) if video is not None else None
        if video_path is None:
            self.window.statusBar().showMessage(
                "Self-test needs the experiment video on disk")
            return
        try:
            payload_fields = build_model_selftest_payload(
                session.project_root, model, Path(video_path)
            )
        except ValueError as error:
            self.window.statusBar().showMessage(f"Cannot self-test: {error}")
            return
        try:
            handle = self._runner_factory().start_selftest(
                session.project_root, model.model_id, payload_fields, device="cpu"
            )
        except ModelWorkerError as error:
            self.window.statusBar().showMessage(f"Cannot start: {error}")
            return
        self._handle = handle
        self._job_kind = "selftest"
        self._selftest_model_id = model_id
        self._selftest_on_success = on_success
        self._job_dir = None   # selftest 无 job_dir 消费者(m5①);真实目录带 uuid 后缀
        self._session = session
        self._timer.start()
        self._set_activity("Self-testing model")
        self.window.statusBar().showMessage(
            f"Compatibility self-test for model {model.model_id} running (cpu)")
        self.window.projectActions.refresh()

    # ------------------------------------------------------------------
    # 取消
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """用户取消:i3① 交接——必须经 handle.cancel(),迟到 success 才会被拒。"""

        if self._handle is None:
            return
        self._user_cancel = True
        self.window.statusBar().showMessage(
            "Cancelling model task (forcing termination may take a few seconds)…")
        self._handle.cancel()

    # ------------------------------------------------------------------
    # 轮询与收尾
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        handle = self._handle
        if handle is None or handle.is_alive():
            return
        self._timer.stop()
        if self._session is not None and self.window.analysisSession is not self._session:
            # B1:项目已被替换,旧 job 的结果不适用新 session——静默放弃
            logger.warning("model job finished after session swap; discarding result")
            handle.cancel()
            self._set_activity("Discarded (project changed)", running=False)
            self._reset()
            return
        try:
            result = handle.read_result()
        except ModelWorkerError as error:
            if self._user_cancel:
                # M1:用户取消后的强杀/迟到拒绝是取消语义,不是失败
                self._finish_cancelled()
            else:
                self._finish_failure(str(error))
            return
        if self._user_cancel or result.get("status") == "cancelled":
            self._finish_cancelled()
            return
        if result.get("status") == "failed":
            error = (result.get("error") or {}).get("message", "training failed")
            self._finish_failure(error)
            return
        if self._job_kind == "train":
            self._finish_train_success(result, handle)
        elif self._job_kind == "selftest":
            self._finish_selftest_success(result)
        else:
            self._reset()   # m5②:未知 kind 防永久 busy

    def _finish_train_success(self, result: dict, handle) -> None:
        session = self.window.analysisSession
        run = self._train_run
        request = self._train_request
        if session is None or run is None or request is None:
            self._reset()
            return
        try:
            completed = verify_experiment_training_result(
                session, run, request, result, self._job_dir
            )
        except (ProjectSessionError, ValueError) as error:
            self._finish_failure(f"verification rejected the result: {error}")
            return
        from dataclasses import replace

        completed = replace(
            completed,
            extra_fields={
                **completed.extra_fields,
                "elapsed_s": round(handle.elapsed_s, 3),   # i3②
            },
        )
        session.update_tracking_run(completed)
        try:
            reference = session.register_trained_model_reference(run.run_id)
        except (ProjectSessionError, ValueError) as error:
            self.window.statusBar().showMessage(
                f"Trained, but the model reference was rejected: {error}")
            self._reset()
            self.window.projectActions.refresh()
            return
        self._set_activity("Completed", running=False)
        self._reset()
        self.window.statusBar().showMessage(
            f"Joint training complete: model {reference.model_id} registered "
            f"as unverified ({result.get('actual_device')}, "
            f"{completed.extra_fields.get('elapsed_s')}s)")
        self.window.projectActions.refresh()
        self.runSelftest(reference.model_id)

    def _finish_selftest_success(self, result: dict) -> None:
        session = self.window.analysisSession
        model_id = self._selftest_model_id
        if session is None or model_id is None:
            self._reset()
            return
        try:
            updated = session.apply_model_selftest(model_id, result)
        except ProjectSessionError as error:
            self.window.statusBar().showMessage(
                f"Self-test result rejected: {error}")
            self._set_activity(f"Self-test rejected: {error}", running=False)
            self._reset()
            return
        continuation = self._selftest_on_success
        self._set_activity("Completed", running=False)
        self._reset()
        self.window.statusBar().showMessage(
            f"Model {model_id} is {updated.compatibility_state} "
            f"({result.get('actual_device')})")
        self.window.projectActions.refresh()
        if updated.compatibility_state == "compatible" and continuation is not None:
            continuation()

    def _finish_failure(self, message: str) -> None:
        session = self.window.analysisSession
        if self._job_kind == "train" and session is not None and self._train_run is not None:
            try:
                session.update_tracking_run(
                    mark_run_failed(self._train_run, message)
                )
            except ProjectSessionError:
                logger.warning("could not mark the training run failed (session changed)")
        logger.warning("model task failed: %s", message)
        self._set_activity(f"Failed: {message[:60]}", running=False)
        self._reset()
        self.window.statusBar().showMessage(f"Model task failed: {message}")
        self.window.projectActions.refresh()

    def _finish_cancelled(self) -> None:
        session = self.window.analysisSession
        if self._job_kind == "train" and session is not None and self._train_run is not None:
            try:
                session.update_tracking_run(
                    mark_run_cancelled(self._train_run)
                )
            except ProjectSessionError:
                logger.warning("could not mark the training run cancelled (session changed)")
        self._set_activity("Cancelled", running=False)
        self._reset()
        self.window.statusBar().showMessage("Model task cancelled")
        self.window.projectActions.refresh()

    def _reset(self) -> None:
        self._handle = None
        self._job_kind = None
        self._activity_text = "Idle"
        self._session = None
        self._user_cancel = False
        self._train_run = None
        self._train_request = None
        self._job_dir = None
        self._selftest_model_id = None
        self._selftest_on_success = None

    # ------------------------------------------------------------------
    # 教师导入入口
    # ------------------------------------------------------------------

    def openImportDialog(self) -> None:
        from ai_physics_tracker.gui.teacher_import_dialog import run_import_dialog

        run_import_dialog(self.window, self)


def model_source_video(model, session):
    """自检输入视频:trained 用来源 experiment 的视频,imported 用首个视频。"""

    if model.origin == "trained" and model.source_experiment_id is not None:
        experiment = next(
            (e for e in session.pendulum_experiments()
             if e.experiment_id == model.source_experiment_id),
            None,
        )
        if experiment is not None:
            return experiment.video_id
    videos = session.project.videos
    return videos[0].video_id if videos else None
