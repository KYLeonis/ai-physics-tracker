"""应用层训练编排服务：协调标注导出、DLC 项目目录复用、后台多进程训练与 TrackingRun 状态机。"""

from dataclasses import replace
import logging
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_cancelled,
    mark_run_completed,
    mark_run_failed,
    mark_run_running,
)
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.engine_adapter import (
    EngineAdapter,
    TrainingParams,
    TrainOutcome,
)
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.task_runner import (
    BackgroundTaskRunner,
    TaskHandle,
    TaskMessage,
    TaskProgress,
    TaskResult,
)

logger = logging.getLogger(__name__)

MIN_MANUAL_POINTS_FOR_TRAINING = 3


def _training_process_worker(
    run_id: UUID,
    queue: Any,
    cancel_event: Any,
    config_path_str: str,
    params_config: dict[str, Any],
    adapter_class: type[EngineAdapter],
) -> dict[str, Any]:
    """子进程顶层入口函数，通过传入的 adapter 执行训练（兼容 spawn 模式）。"""

    config_path = Path(config_path_str)
    params = TrainingParams.from_config(params_config)
    adapter = adapter_class()
    outcome = adapter.train(run_id, queue, cancel_event, config_path, params)
    return {
        "status": outcome.status,
        "epochs_completed": outcome.epochs_completed,
        "snapshot_path": outcome.snapshot_path,
        "engine_version": outcome.engine_version,
        "error_message": outcome.error_message,
    }


class TrainingCoordinator:
    """管理项目会话中训练生命周期的应用服务。"""

    def __init__(self, task_runner: BackgroundTaskRunner | None = None) -> None:
        self._runner = task_runner or BackgroundTaskRunner()
        self._active_handles: dict[UUID, TaskHandle] = {}
        self._config_paths: dict[UUID, Path] = {}
        self._adapter_classes: dict[UUID, type[EngineAdapter]] = {}

    def prepare_training(
        self,
        session: ProjectSession,
        track_id: UUID,
        video_reader: OpenCVVideoReader,
        params: TrainingParams | None = None,
        adapter: EngineAdapter | None = None,
        working_dir: Path | None = None,
    ) -> tuple[TrackingRun, Path]:
        """为指定 Track 准备 DLC 项目、导出最新标注并生成 pending 状态的 TrackingRun。"""

        track = next((t for t in session.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"Unknown track_id: {track_id}")

        if any(r.track_id == track_id and r.status == "running" for r in session.tracking_runs()):
            raise ProjectSessionError("This track already has an active engine task")

        manual_points = tuple(
            p
            for p in session.manual_points(track_id)
            if p.status == "active"
        )
        if len(manual_points) < MIN_MANUAL_POINTS_FOR_TRAINING:
            raise ProjectSessionError(
                f"At least {MIN_MANUAL_POINTS_FOR_TRAINING} active manual points are required for training, got {len(manual_points)}"
            )

        video = next((v for v in session.project.videos if v.video_id == track.video_id), None)
        if video is None:
            raise ProjectSessionError(f"Video not found for track: {track.name}")

        # 解析实际可读取的视频本地路径
        resolved_video_path = session.resolve_video_path(video)
        if resolved_video_path is None or not resolved_video_path.is_file():
            raise ProjectSessionError(f"Cannot resolve local video file for: {video.display_name}")

        actual_adapter = adapter or DLCAdapter()
        actual_params = params or TrainingParams()

        # 确定 DLC 项目目录（优先 session.project_root / data / engines / dlc / <track_id_prefix>）
        track_prefix = str(track_id)[:8]
        if working_dir is not None:
            base_dir = working_dir
        elif session.project_root is not None:
            base_dir = session.project_root / "data" / "engines" / "dlc"
        else:
            base_dir = Path.cwd() / "data" / "engines" / "dlc"

        base_dir.mkdir(parents=True, exist_ok=True)
        proj_name = f"dlc_{track_prefix}"
        proj_dir = base_dir / proj_name

        config_path = proj_dir / "config.yaml"
        # 目录复用：若 config.yaml 存在则复用，否则新建
        if not config_path.is_file():
            config_path = actual_adapter.create_project(
                project_name=proj_name,
                experimenter="AIPhysicsTracker",
                video_path=resolved_video_path,
                working_dir=base_dir,
                bodyparts=["target"],
            )

        # 导出最新手工标注
        exported_count = actual_adapter.export_annotations(
            track_points=manual_points,
            video_reader=video_reader,
            config_path=config_path,
            scorer="AIPhysicsTracker",
            bodyparts=["target"],
        )
        logger.info(
            "Exported %d annotations to DLC project: %s",
            exported_count,
            config_path,
        )

        # 创建训练集
        actual_adapter.create_training_dataset(
            config_path=config_path,
            num_shuffles=actual_params.shuffle,
        )

        # 构造并登记 TrackingRun
        run = create_tracking_run(
            video_id=track.video_id,
            track_id=track_id,
            task_type="train",
            engine="dlc",
            engine_version=actual_adapter.engine_version(),
            config=actual_params.to_config(),
        )
        if session.project_root is not None:
            try:
                relative_config = config_path.resolve().relative_to(session.project_root.resolve()).as_posix()
            except ValueError:
                relative_config = None
            if relative_config is not None:
                run = replace(run, extra_fields={"config_path": relative_config})
        session.record_tracking_run(run)

        # 记录配置路径与适配器类型供后续启动使用
        self._config_paths[run.run_id] = config_path
        self._adapter_classes[run.run_id] = type(actual_adapter)

        return run, config_path

    def start_training(
        self,
        session: ProjectSession,
        run_id: UUID,
        config_path: Path | None = None,
        adapter_class: type[EngineAdapter] | None = None,
    ) -> TaskHandle:
        """启动后台子进程训练，更新 run 状态为 running。"""

        run = next((r for r in session.project.tracking_runs if r.run_id == run_id), None)
        if run is None:
            raise ProjectSessionError(f"Unknown tracking run_id: {run_id}")
        if run.status != "pending":
            raise ProjectSessionError(f"Cannot start training run in '{run.status}' status")

        if any(r.run_id != run_id and r.track_id == run.track_id and r.status == "running"
               for r in session.tracking_runs()):
            raise ProjectSessionError("This track already has an active engine task")
        stored_config = run.extra_fields.get("config_path")
        saved_path = (session.project_root / stored_config
                      if session.project_root and isinstance(stored_config, str) else None)
        cfg_path = config_path or self._config_paths.get(run_id) or saved_path
        if cfg_path is None or not cfg_path.is_file():
            raise ProjectSessionError(f"DLC config.yaml not found for run: {run_id}")

        ad_class = adapter_class or self._adapter_classes.get(run_id) or DLCAdapter

        # 启动后台进程
        handle = self._runner.start_task(
            run_id,
            _training_process_worker,
            str(cfg_path),
            run.config,
            ad_class,
        )
        self._active_handles[run_id] = handle

        # 领域状态流转为 running
        running_run = mark_run_running(run)
        session.update_tracking_run(running_run)
        return handle

    def poll_messages(
        self,
        session: ProjectSession,
        run_id: UUID,
    ) -> list[TaskMessage]:
        """轮询后台任务进度并自动同步最终完成/失败状态至 session。"""

        handle = self._active_handles.get(run_id)
        if handle is None:
            return []

        messages = handle.poll_messages()
        if not handle.is_alive():
            handle.join(timeout_s=0)
            # 退出后再排空队列，避免首次轮询与最后一条消息到达竞态。
            messages.extend(handle.poll_messages())
        has_result = False
        for msg in messages:
            if isinstance(msg, TaskResult):
                has_result = True
                run = next((r for r in session.project.tracking_runs if r.run_id == run_id), None)
                if run is not None and run.status == "running":
                    payload = msg.payload or {}
                    status_str = payload.get("status")
                    if msg.success and status_str == "completed":
                        snapshot = str(payload.get("snapshot_path") or "") or None
                        if snapshot is None or not Path(snapshot).is_file():
                            session.update_tracking_run(mark_run_failed(run, "Training returned no existing model snapshot"))
                            continue
                        snapshot_path = Path(snapshot).resolve()
                        with snapshot_path.open("rb") as model_file:
                            digest = hashlib.file_digest(model_file, "sha256").hexdigest()
                        if session.project_root is not None:
                            try:
                                snapshot = snapshot_path.relative_to(session.project_root.resolve()).as_posix()
                            except ValueError:
                                # 兼容显式外部 working_dir；不猜测或迁移外部权重。
                                snapshot = str(snapshot_path)
                        completed_run = replace(mark_run_completed(run, model_snapshot=snapshot),
                            engine_version=str(payload.get("engine_version") or run.engine_version),
                            extra_fields={**run.extra_fields, "model_sha256": digest})
                        session.update_tracking_run(completed_run)
                    elif status_str == "cancelled" or (not msg.success and "cancelled" in str(msg.error).lower()):
                        cancelled_run = mark_run_cancelled(run)
                        session.update_tracking_run(cancelled_run)
                    else:
                        error = payload.get("error_message") or msg.error or "Training failed"
                        failed_run = mark_run_failed(run, error_message=str(error))
                        session.update_tracking_run(failed_run)

        # 检查未正常返回 TaskResult 的异常终止情况（如崩溃退出/OOM）
        if not handle.is_alive():
            if not has_result:
                run = next((r for r in session.project.tracking_runs if r.run_id == run_id), None)
                if run is not None and run.status == "running":
                    exitcode = handle.exitcode
                    failed_run = mark_run_failed(
                        run,
                        error_message=f"Training process terminated unexpectedly (exitcode={exitcode})",
                    )
                    session.update_tracking_run(failed_run)
            self._active_handles.pop(run_id, None)

        return messages

    def is_running(self, run_id: UUID) -> bool:
        """检查特定训练任务是否处于活动运行中。"""
        handle = self._active_handles.get(run_id)
        return handle is not None and handle.is_alive()

    def cancel_training(
        self,
        session: ProjectSession,
        run_id: UUID,
        timeout_s: float = 3.0,
    ) -> None:
        """安全取消正在运行的训练任务，回收子进程并更新 TrackingRun 状态为 cancelled。"""

        handle = self._active_handles.pop(run_id, None)
        if handle is not None:
            handle.cancel(timeout_s=timeout_s)

        run = next((r for r in session.project.tracking_runs if r.run_id == run_id), None)
        if run is not None and run.status in {"pending", "running"}:
            cancelled_run = mark_run_cancelled(run)
            session.update_tracking_run(cancelled_run)

    def cancel_all(self, session: ProjectSession) -> None:
        """取消当前所有正在运行的任务（用于项目切换或关闭，满足 D1 策略）。"""

        for run_id in list(self._active_handles.keys()):
            self.cancel_training(session, run_id, timeout_s=1.0)
