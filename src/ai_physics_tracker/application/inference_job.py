"""应用层全帧推理编排：独立进程产出、当前会话校验、原子观测导入。"""

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun, create_tracking_run, mark_run_running, mark_run_completed,
    mark_run_failed, mark_run_cancelled,
)
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.engine_adapter import (
    EngineAdapter, InferenceParams, InferenceRequest,
)
from ai_physics_tracker.infrastructure.task_runner import (
    BackgroundTaskRunner, TaskHandle, TaskMessage, TaskResult,
)


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _stamp(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


def _project_path(root: Path, value: str) -> Path:
    """兼容旧绝对模型路径；相对引用不能逃出项目。"""
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ProjectSessionError("Engine path escapes the project directory")
    return resolved


def _inference_process_worker(
    run_id: UUID, queue: Any, cancel_event: Any,
    request: InferenceRequest, adapter: EngineAdapter,
) -> JsonObject:
    """大批量结果落盘交换，队列只返回小型摘要，避免退出时等待巨量 IPC。"""
    try:
        digest = _sha256(request.model_snapshot)
        if request.model_sha256 is None or digest != request.model_sha256:
            raise ValueError("Selected training snapshot has changed; retrain or select another run")
        if request.video_sha256 is None or _sha256(request.video_path) != request.video_sha256:
            raise ValueError("Video content changed before inference")
        if request.config_sha256 is None or _sha256(request.config_path) != request.config_sha256:
            raise ValueError("DLC config changed before inference")
        outcome = adapter.infer(run_id, queue, cancel_event, request)
        if cancel_event.is_set():
            raise CancelledError("Inference cancelled")
        if outcome.model_snapshot.resolve() != request.model_snapshot.resolve():
            raise ValueError("Engine used a different snapshot")
        if _sha256(request.model_snapshot) != digest:
            raise ValueError("Model snapshot changed during inference")
        if _sha256(request.video_path) != request.video_sha256:
            raise ValueError("Video content changed during inference")
        if _sha256(request.config_path) != request.config_sha256:
            raise ValueError("DLC config changed during inference")
        if outcome.row_count != request.frame_count:
            raise ValueError("Engine returned an incomplete frame batch")
        if (outcome.missing_count < 0 or outcome.low_confidence_count < 0
                or len(outcome.points) + outcome.missing_count + outcome.low_confidence_count != outcome.row_count):
            raise ValueError("Engine returned inconsistent prediction counts")
        raw_path = outcome.prediction_path.resolve()
        if not raw_path.is_relative_to(request.output_dir.resolve()) or not raw_path.is_file():
            raise ValueError("Engine result is outside its output directory or missing")
        if request.archive_model:
            for source, name in ((request.model_snapshot, "model-used.pt"),
                                 (request.config_path, "config-used.yaml")):
                with source.open("rb") as incoming, (request.output_dir / name).open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
            if _sha256(request.output_dir / "model-used.pt") != digest:
                raise ValueError("Model changed while archiving the verified legacy snapshot")
        exchange = request.output_dir / "observations.json"
        with exchange.open("x", encoding="utf-8") as stream:
            json.dump([asdict(point) for point in outcome.points], stream,
                      ensure_ascii=False, allow_nan=False, default=str)
        return {
            "status": "completed", "engine_version": outcome.engine_version,
            "device": outcome.device, "model_sha256": digest,
            "video_sha256": request.video_sha256,
            "config_sha256": request.config_sha256,
            "prediction_path": raw_path.name, "prediction_sha256": _sha256(raw_path),
            "observations_sha256": _sha256(exchange),
            "row_count": outcome.row_count, "missing_count": outcome.missing_count,
            "low_confidence_count": outcome.low_confidence_count,
        }
    except CancelledError:
        return {"status": "cancelled"}


@dataclass
class _InferenceJob:
    session: ProjectSession
    request: InferenceRequest
    project_root: Path
    video: Video
    timing_detail: str | None
    media_stamp: tuple[int, int, int]
    config_stamp: tuple[int, int, int]
    model_stamp: tuple[int, int, int]
    adapter: EngineAdapter
    handle: TaskHandle | None = None


class InferenceCoordinator:
    """单活动推理任务；切换/关闭前由调用者执行 cancel_all，4.4 负责窗口接线。"""

    def __init__(self, task_runner: BackgroundTaskRunner | None = None) -> None:
        self._runner = task_runner or BackgroundTaskRunner()
        self._jobs: dict[UUID, _InferenceJob] = {}

    def prepare_inference(
        self, session: ProjectSession, training_run_id: UUID, params: InferenceParams,
        *, adapter: EngineAdapter | None = None, config_path: Path | None = None,
    ) -> TrackingRun:
        """验证模型来源、视频时序与文件身份，准备一个尚未启动的推理 run。"""
        root = session.project_root
        if root is None:
            raise ProjectSessionError("Save the project before inference")
        root = root.resolve()
        trained = next((r for r in session.tracking_runs() if r.run_id == training_run_id), None)
        if trained is None or trained.task_type != "train" or trained.status != "completed":
            raise ProjectSessionError("Select a completed training run")
        model_digest = trained.extra_fields.get("model_sha256")
        if not isinstance(model_digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", model_digest) is None:
            raise ProjectSessionError("Training run has no verified model hash; retrain before inference")
        track = next((t for t in session.tracks if t.track_id == trained.track_id), None)
        if track is None or track.video_id != trained.video_id:
            raise ProjectSessionError("Training run does not match a current track/video")
        self._require_idle(session, trained.track_id)
        video = next(v for v in session.project.videos if v.video_id == trained.video_id)
        video_path = session.video_path(video)
        if video_path is None or not video_path.is_file() or not session.can_measure(video.video_id):
            raise ProjectSessionError("Video is missing or its timing is not authorized")
        media_digest = _sha256(video_path)
        if video.sha256 is not None and media_digest != video.sha256.lower():
            raise ProjectSessionError("Video content does not match the registered SHA-256; relink and verify it")
        stored_config = trained.extra_fields.get("config_path")
        if config_path is None and isinstance(stored_config, str):
            config_path = _project_path(root, stored_config)
        if config_path is None or not config_path.is_file() or not trained.model_snapshot:
            raise ProjectSessionError("Training config/snapshot is missing; retrain or supply a verified config")
        config_path = config_path.resolve()
        snapshot = _project_path(root, trained.model_snapshot)
        if not snapshot.is_file():
            raise ProjectSessionError("Training snapshot is missing; retrain before inference")
        archive_model = not config_path.is_relative_to(root) or not snapshot.is_relative_to(root)
        timeline = next(t for t in session.project.timelines if t.video_id == video.video_id)
        config = {
            **asdict(params), "training_run_id": str(trained.run_id),
            "shuffle": trained.config.get("shuffle", 1),
            "trainingsetindex": trained.config.get("trainingsetindex", 0),
            "timing_detail": session.measurement_timing_detail(video.video_id),
        }
        engine = adapter or DLCAdapter()
        run = create_tracking_run(video.video_id, track.track_id, "infer",
            engine=trained.engine, engine_version=trained.engine_version,
            config=config)
        output_dir = root / "data" / "engines" / str(run.run_id)
        request = InferenceRequest(config_path, video_path.resolve(), snapshot,
            output_dir, track.track_id, timeline,
            run.source_detail, video.frame_count, params,
            shuffle=config["shuffle"], trainingsetindex=config["trainingsetindex"],
            model_sha256=model_digest.lower(), video_sha256=media_digest, archive_model=archive_model,
            config_sha256=_sha256(config_path))
        extras = {"model_sha256": request.model_sha256, "config_sha256": request.config_sha256}
        if not archive_model:
            extras["config_path"] = config_path.relative_to(root).as_posix()
        # legacy 归档尚不存在；失败/取消的 run 不应持有虚构文件引用。
        run = replace(run, model_snapshot=None if archive_model else snapshot.relative_to(root).as_posix(),
                      extra_fields=extras)
        job = _InferenceJob(session, request, root, video, config["timing_detail"],
                            _stamp(request.video_path), _stamp(config_path), _stamp(snapshot), deepcopy(engine))
        session.record_tracking_run(run)
        self._jobs[run.run_id] = job
        return run

    def _require_idle(self, session: ProjectSession, track_id: UUID) -> None:
        if any(job.handle is not None for job in self._jobs.values()):
            raise ProjectSessionError("Another inference task is active")
        if any(r.track_id == track_id and r.status == "running" for r in session.tracking_runs()):
            raise ProjectSessionError("This track already has an active engine task")

    def _validate_context(self, session: ProjectSession, job: _InferenceJob) -> None:
        request = job.request
        video = next((v for v in session.project.videos if v.video_id == job.video.video_id), None)
        timeline = next((t for t in session.project.timelines if t.video_id == job.video.video_id), None)
        media_path = session.video_path(job.video)
        if (session is not job.session or session.project_root != job.project_root
                or video != job.video or timeline != request.timeline
                or not session.can_measure(job.video.video_id)
                or session.measurement_timing_detail(job.video.video_id) != job.timing_detail
                or not any(t.track_id == request.track_id and t.video_id == job.video.video_id for t in session.tracks)
                or media_path is None or media_path.resolve() != request.video_path
                or _stamp(request.video_path) != job.media_stamp
                or _sha256(request.video_path) != request.video_sha256
                or _stamp(request.config_path) != job.config_stamp
                or _sha256(request.config_path) != request.config_sha256
                or _stamp(request.model_snapshot) != job.model_stamp):
            raise ProjectSessionError("Inference context changed; results were not imported")

    def start_inference(self, session: ProjectSession, run_id: UUID) -> TaskHandle:
        """启动 spawn worker；启动失败也结束已登记 run，不留下 running 假象。"""
        job = self._jobs.get(run_id)
        run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
        if job is None or job.session is not session or run is None or run.status != "pending":
            raise ProjectSessionError("No pending inference job belongs to this session")
        self._require_idle(session, run.track_id)
        try:
            self._validate_context(session, job)
            handle = self._runner.start_task(run_id, _inference_process_worker, job.request, job.adapter)
        except Exception as error:
            session.update_tracking_run(mark_run_failed(run, str(error)))
            self._jobs.pop(run_id, None)
            raise ProjectSessionError(f"Cannot start inference: {error}") from error
        job.handle = handle
        session.update_tracking_run(mark_run_running(run))
        return handle

    def _apply_result(self, job: _InferenceJob, run: TrackingRun, payload: JsonObject) -> None:
        self._validate_context(job.session, job)
        folder = job.request.output_dir
        raw_name = payload.get("prediction_path")
        if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
            raise ProjectSessionError("Invalid prediction artifact reference")
        raw = folder / raw_name
        exchange = folder / "observations.json"
        if (_sha256(raw) != payload.get("prediction_sha256")
                or _sha256(exchange) != payload.get("observations_sha256")):
            raise ProjectSessionError("Inference artifacts changed before import")
        if job.request.archive_model:
            if (_sha256(folder / "model-used.pt") != payload.get("model_sha256")
                    or _sha256(folder / "config-used.yaml") != job.request.config_sha256):
                raise ProjectSessionError("Archived model/config differs from the inference inputs")
        records = json.loads(exchange.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ProjectSessionError("Invalid observation batch")
        points = []
        for record in records:
            for field in ("point_id", "track_id"):
                record[field] = UUID(record[field])
            if record["superseded_by"] is not None:
                record["superseded_by"] = UUID(record["superseded_by"])
            for field in ("created_at", "modified_at"):
                record[field] = datetime.fromisoformat(record[field])
            record["quality_flags"] = tuple(record["quality_flags"])
            points.append(TrackPoint(**record))
        counts = [payload.get(key) for key in ("row_count", "missing_count", "low_confidence_count")]
        if (any(type(n) is not int or n < 0 for n in counts)
                or counts[0] != job.request.frame_count or len(points) + counts[1] + counts[2] != counts[0]
                or any(p.confidence is None or p.confidence < job.request.params.min_confidence for p in points)):
            raise ProjectSessionError("Invalid prediction counts or confidence")
        extras = {**run.extra_fields, "prediction_path": raw.relative_to(job.project_root).as_posix(),
            "prediction_sha256": payload["prediction_sha256"],
            "observations_path": exchange.relative_to(job.project_root).as_posix(),
            "observations_sha256": payload["observations_sha256"],
            "model_sha256": payload["model_sha256"], "device": payload["device"],
            "video_sha256": payload["video_sha256"],
            "config_sha256": payload["config_sha256"],
            "import_summary": dict(zip(("row_count", "missing_count", "low_confidence_count"), counts))}
        snapshot_ref = run.model_snapshot
        if job.request.archive_model:
            snapshot_ref = (folder / "model-used.pt").relative_to(job.project_root).as_posix()
            extras["config_path"] = (folder / "config-used.yaml").relative_to(job.project_root).as_posix()
        completed = replace(mark_run_completed(run, model_snapshot=snapshot_ref),
                            engine_version=str(payload["engine_version"]), extra_fields=extras)
        job.session.import_engine_points(tuple(points), completed)

    def poll_messages(self, session: ProjectSession, run_id: UUID) -> list[TaskMessage]:
        """只允许拥有任务的会话接收结果，进程退出后再排空末尾消息。"""
        job = self._jobs.get(run_id)
        if job is None or job.handle is None:
            return []
        if job.session is not session:
            self.cancel_inference(job.session, run_id, timeout_s=0)
            raise ProjectSessionError("Inference belongs to a different session")
        handle = job.handle
        messages = handle.poll_messages()
        if not handle.is_alive():
            handle.join(timeout_s=0)
            messages.extend(handle.poll_messages())
        forwarded: list[TaskMessage] = []
        for message in messages:
            if message.run_id != run_id:
                continue
            if not isinstance(message, TaskResult):
                forwarded.append(message)
                continue
            run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
            if run is None or run.status != "running":
                continue
            payload = message.payload or {}
            try:
                if payload.get("status") == "cancelled":
                    session.update_tracking_run(mark_run_cancelled(run))
                elif message.success and payload.get("status") == "completed":
                    self._apply_result(job, run, payload)
                else:
                    raise ProjectSessionError(message.error or "Inference failed")
            except Exception as error:
                session.update_tracking_run(mark_run_failed(run, str(error)))
            committed = next(r for r in session.tracking_runs() if r.run_id == run_id)
            # GUI 收到的终态必须对应实际导入，而不是仅表示引擎进程执行成功。
            forwarded.append(TaskResult(run_id, committed.status == "completed",
                {**payload, "status": committed.status}, committed.error_message))
        if not handle.is_alive():
            run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
            if run is not None and run.status == "running":
                error = f"Inference process exited without a result (exitcode={handle.exitcode})"
                session.update_tracking_run(mark_run_failed(run, error))
                forwarded.append(TaskResult(run_id, False, {"status": "failed"}, error))
            self._jobs.pop(run_id, None)
        return forwarded

    def is_running(self, run_id: UUID) -> bool:
        job = self._jobs.get(run_id)
        return job is not None and job.handle is not None and job.handle.is_alive()

    def cancel_inference(self, session: ProjectSession, run_id: UUID, timeout_s: float = 1.0) -> None:
        """取消含 pending 在内的任务；所有磁盘产物保留但不导入。"""
        job = self._jobs.get(run_id)
        if job is None:
            return
        if job.session is not session:
            raise ProjectSessionError("Inference belongs to a different session")
        if job.handle is not None:
            job.handle.cancel(timeout_s=timeout_s)
        run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
        if run is not None and run.status in {"pending", "running"}:
            session.update_tracking_run(mark_run_cancelled(run))
        self._jobs.pop(run_id, None)

    def cancel_all(self, session: ProjectSession) -> None:
        """D1：只回收该会话拥有的全部任务，迟到消息不再应用。"""
        for run_id, job in list(self._jobs.items()):
            if job.session is session:
                self.cancel_inference(session, run_id)
