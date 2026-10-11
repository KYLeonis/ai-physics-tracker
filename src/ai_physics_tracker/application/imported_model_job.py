"""将通过实际帧自检的教师模型接入既有候选轨迹事务。"""

from concurrent.futures import CancelledError
from dataclasses import asdict, replace
import shutil
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.tracking_types import InferenceRequest, InferenceParams
from ai_physics_tracker.domain.tracking_run import TrackingRun, create_tracking_run
from ai_physics_tracker.domain.imported_model import ImportedModel
from ai_physics_tracker.infrastructure.imported_models import import_model, verify_model, verified_self_test
from ai_physics_tracker.infrastructure.imported_model_inference import run_model_self_test
from ai_physics_tracker.infrastructure.task_runner import BackgroundTaskRunner, TaskResult


def prepare_imported_inference(session: ProjectSession, track_id: UUID, model_id: UUID,
                               bodypart: str, params: InferenceParams, run_id: UUID
                               ) -> tuple[TrackingRun, InferenceRequest]:
    """后台校验模型身份并准备标准 infer run；不接触活动 GUI 会话。"""
    model = next((m for m in session.project.imported_models if m.model_id == model_id), None)
    if model is None or bodypart not in model.bodyparts or not verified_self_test(model, params.device):
        raise ProjectSessionError("Select a teacher model/bodypart and repeat its actual-frame self-test")
    root = session.project_root
    verify_model(root, model)
    track = next(t for t in session.tracks if t.track_id == track_id)
    video = next(v for v in session.project.videos if v.video_id == track.video_id)
    timeline = next(t for t in session.project.timelines if t.video_id == track.video_id)
    run = create_tracking_run(video.video_id, track_id, "infer", run_id=run_id,
                              engine_version=model.self_test["runtime"]["deeplabcut"],
                              config={**asdict(params), "imported_model_id": str(model_id),
                                      "bodypart": bodypart, "manifest_hash": model.manifest_hash,
                                      "timing_detail": session.measurement_timing_detail(video.video_id)})
    folder = root / model.directory
    config = folder / "config.yaml"
    snapshot = folder / "checkpoint.pt"
    run = replace(run, model_snapshot=snapshot.relative_to(root).as_posix(), extra_fields={
        "config_path": config.relative_to(root).as_posix(),
        "imported_model_sha256": dict(model.sha256),
        "imported_model_directory": model.directory,
        "model_file_info": [snapshot.stat().st_size, snapshot.stat().st_mtime_ns]})
    request = InferenceRequest(config, session.video_path(video), snapshot,
                               root / "data" / "engines" / str(run_id), track_id,
                               timeline, run.source_detail, video.frame_count, params,
                               imported_model=model, model_root=root, bodypart=bodypart)
    session.record_tracking_run(run)
    return run, request


def probe_model(runner: Any, cancel: Any, *args: Any) -> dict[str, Any]:
    """拥有从启动到回收的完整生命周期；取消不能遗留晚到的进程。"""
    handle = runner.start_task(uuid4(), run_model_self_test, *args)
    dead_at = None
    try:
        while True:
            if cancel.is_set():
                raise CancelledError()
            for message in handle.poll_messages():
                if isinstance(message, TaskResult) and message.run_id == handle.run_id:
                    if not message.success or not message.payload or message.payload.get("status") != "completed":
                        raise ValueError(message.error or "Model self-test did not complete")
                    if cancel.is_set():
                        raise CancelledError()
                    return message.payload["evidence"]
            if not handle.is_alive():
                dead_at = dead_at or time.monotonic()
                if time.monotonic() - dead_at > 1:
                    raise ValueError("Self-test process exited without a result")
            time.sleep(0.02)
    finally:
        handle.cancel(timeout_s=0.5)


def import_teacher_model(root: Path, paths: tuple[Path, Path, Path], cancel: Any) -> ImportedModel:
    """发布受管副本；取消后清理本次独占目录。"""
    model = import_model(root, *paths, cancel)
    if cancel.is_set():
        shutil.rmtree(root / model.directory)
        raise CancelledError()
    return model


class ModelJobRunner:
    """后台模型操作的应用边界；GUI 不导入基础设施或管理子进程。"""

    def __init__(self, runner: Any = None) -> None:
        self.runner = runner or BackgroundTaskRunner()

    def probe(self, cancel: Any, *args: Any) -> dict[str, Any]:
        return probe_model(self.runner, cancel, *args)

    @staticmethod
    def import_model(root: Path, paths: tuple[Path, Path, Path], cancel: Any) -> ImportedModel:
        return import_teacher_model(root, paths, cancel)

    @staticmethod
    def discard(root: Path, model: ImportedModel) -> None:
        shutil.rmtree(root / model.directory)
