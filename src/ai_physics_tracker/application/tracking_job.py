"""应用层 GUI 跟踪任务：不可变请求、独占子进程、后台候选与原子提交。"""

from concurrent.futures import CancelledError
from dataclasses import asdict, dataclass, replace
from contextlib import redirect_stdout, redirect_stderr
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.training_job import TrainingCoordinator
from ai_physics_tracker.application.inference_job import (
    InferenceCoordinator, _inference_process_worker, read_inference_result, read_observation_exchange,
)
from ai_physics_tracker.domain.project import Project
from ai_physics_tracker.domain.track_store import TrackStore
from ai_physics_tracker.domain.tracking_run import TrackingRun, create_tracking_run, mark_run_completed
from ai_physics_tracker.infrastructure.engine_adapter import EngineAdapter, TrainingParams, InferenceParams
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter, _QueueLogStream, detect_device
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.project_serializer import _tracking_run_from_payload, _tracking_run_to_payload
from ai_physics_tracker.infrastructure.task_runner import TaskLog, send_log
from ai_physics_tracker.infrastructure.task_runner import TaskResult, BackgroundTaskRunner


@dataclass(frozen=True)
class TrackingRequest:
    """project 为不可变领域快照；可变会话和 Qt 对象不跨进程。"""

    project: Project
    project_root: Path
    run: TrackingRun
    parameters: TrainingParams | InferenceParams
    timing_detail: str | None
    training_run_id: UUID | None = None
    video_path: Path | None = None
    video_file_info: tuple[int, int] | None = None


def prepare_tracking_request(session: ProjectSession, track_id: UUID,
                             parameters: TrainingParams | InferenceParams,
                             training_run_id: UUID | None = None) -> TrackingRequest:
    """仅检查内存条件和捕获快照；不导入引擎、读视频或扫描文件。"""
    if session.project_root is None:
        raise ProjectSessionError("Save the project before starting an AI task")
    track = next((track for track in session.tracks if track.track_id == track_id), None)
    if track is None or not session.can_measure(track.video_id):
        raise ProjectSessionError("Select a track with authorized video timing")
    if any(run.status in {"pending", "running"} for run in session.tracking_runs()):
        raise ProjectSessionError("Another AI task is active")
    detail = session.measurement_timing_detail(track.video_id)
    if isinstance(parameters, TrainingParams):
        if len(session.manual_points(track_id)) < 3:
            raise ProjectSessionError("Mark at least 3 distinct frames before training")
        config = parameters.to_config()
        task_type = "train"
    else:
        trained = next((run for run in session.tracking_runs() if run.run_id == training_run_id), None)
        if (trained is None or trained.task_type != "train" or trained.status != "completed"
                or trained.track_id != track_id or not trained.model_snapshot):
            raise ProjectSessionError("Select a completed model for the current track")
        config = {**asdict(parameters), "training_run_id": str(trained.run_id),
                  "shuffle": trained.config.get("shuffle", 1),
                  "trainingsetindex": trained.config.get("trainingsetindex", 0), "timing_detail": detail}
        task_type = "infer"
    run = create_tracking_run(track.video_id, track_id, task_type, engine_version="pending", config=config)
    video = next(video for video in session.project.videos if video.video_id == track.video_id)
    path = session.video_path(video)
    if path is None:
        raise ProjectSessionError("Video file is missing")
    stat = path.stat()
    return TrackingRequest(session.project, session.project_root, run, parameters, detail,
                           training_run_id, path.resolve(), (stat.st_size, stat.st_mtime_ns))


def _owned_session(project: Project, request: TrackingRequest) -> ProjectSession:
    # 授权只来自 prepare_tracking_request 已核实的请求；不用于从磁盘加载用户项目。
    session = ProjectSession(ProjectRepository(), project, request.project_root)
    session._verified_videos.add(request.run.video_id)
    if request.timing_detail is not None:
        session._approximate_timing[request.run.video_id] = request.timing_detail
    return session


class _LogQueue:
    """同一份日志流写文件并送 UI；不改变现有 TaskMessage 协议。"""

    def __init__(self, queue: Any, stream: Any) -> None:
        self.queue, self.stream = queue, stream

    def put(self, message: Any) -> None:
        if isinstance(message, TaskLog):
            self.stream.write(message.message + "\n")
            self.stream.flush()
        self.queue.put(message)


def run_tracking_worker(run_id: UUID, queue: Any, cancel_event: Any,
                        request: TrackingRequest, adapter: EngineAdapter) -> dict[str, Any]:
    """整个引擎工作流在一个 spawn 子进程内运行，不嵌套引擎进程。"""
    log_path = request.project_root / "data" / "engines" / f"{run_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("x", encoding="utf-8") as log:
        messages = _LogQueue(queue, log)
        output = _QueueLogStream(messages, run_id)
        try:
            with redirect_stdout(output), redirect_stderr(output):
                result = _run_pipeline(run_id, messages, cancel_event, request, adapter)
            return result
        except CancelledError:
            return {"status": "cancelled"}
        except Exception as error:
            send_log(messages, run_id, "ERROR", str(error))
            raise
        finally:
            output.flush()


def _run_pipeline(run_id, queue, cancel_event, request, adapter):
    if cancel_event.is_set():
        raise CancelledError()
    session = _owned_session(request.project, request)
    verify_request_files(request)
    if isinstance(request.parameters, TrainingParams):
        run = _train(session, run_id, queue, cancel_event, request, adapter)
        points_path = None
    else:
        send_log(queue, run_id, "INFO", "Preparing inference")
        coordinator = InferenceCoordinator()
        run = coordinator.prepare_inference(session, request.training_run_id, request.parameters,
                                            adapter=adapter, run_id=run_id)
        prepared = coordinator.prepared_request(run_id)
        payload = _inference_process_worker(run_id, queue, cancel_event, prepared, adapter)
        if payload["status"] == "cancelled":
            raise CancelledError()
        _, run = read_inference_result(prepared, request.project_root, run, payload)
        points_path = (prepared.output_dir / "observations.json").relative_to(request.project_root).as_posix()
    run = replace(run, run_id=run_id, source_detail=request.run.source_detail,
                  created_at=request.run.created_at,
                  extra_fields={**run.extra_fields, "log_path": f"data/engines/{run_id}.log"})
    folder = request.project_root / "data" / "engines" / str(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / "task-result.json"
    _write_result(destination, run, points_path)
    return {"status": "completed", "result_path": destination.relative_to(request.project_root).as_posix()}


def _train(session, run_id, queue, cancel_event, request, adapter):
    video = next(video for video in session.project.videos if video.video_id == request.run.video_id)
    path = session.video_path(video)
    if path is None:
        raise ProjectSessionError("Video file is missing")
    actual_device = detect_device() if request.parameters.device == "auto" else request.parameters.device
    parameters = replace(request.parameters, device=actual_device)
    send_log(queue, run_id, "INFO", f"Preparing training dataset on {actual_device}")
    reader = OpenCVVideoReader()
    try:
        reader.open(path)
        run, config_path = TrainingCoordinator().prepare_training(
            session, request.run.track_id, reader, parameters, adapter,
            working_dir=request.project_root / "data" / "engines" / str(run_id))
    finally:
        reader.close()
    if cancel_event.is_set():
        raise CancelledError()
    outcome = adapter.train(run_id, queue, cancel_event, config_path, parameters)
    if outcome.status == "cancelled":
        raise CancelledError()
    if outcome.status != "completed" or not outcome.snapshot_path or not Path(outcome.snapshot_path).is_file():
        raise ProjectSessionError(outcome.error_message or "Training did not produce a model")
    snapshot = Path(outcome.snapshot_path).resolve()
    stat = snapshot.stat()
    extras = {**run.extra_fields, "model_file_info": [stat.st_size, stat.st_mtime_ns],
              "device": actual_device, "requested_device": request.parameters.device}
    ready = replace(mark_run_completed(run, model_snapshot=snapshot.relative_to(request.project_root).as_posix()),
                    run_id=run_id, source_detail=request.run.source_detail, created_at=request.run.created_at,
                    engine_version=outcome.engine_version, extra_fields=extras)
    folder = request.project_root / "data" / "engines" / str(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    _write_result(folder / "model-ready.json", ready, None)
    queue.put(TaskResult(run_id, True, {"status": "model_ready"}))
    try:
        if cancel_event.is_set():
            raise CancelledError("Evaluation cancelled after model training")
        send_log(queue, run_id, "INFO", "Evaluating trained model")
        evaluation = adapter.evaluate(config_path, snapshot, parameters)
        evaluation["snapshot_path"] = snapshot.relative_to(request.project_root).as_posix()
        if evaluation.get("results_csv"):
            original_csv = Path(evaluation["results_csv"])
            archive = folder / "evaluation.csv"
            shutil.copyfile(original_csv, archive)
            evaluation["results_csv"] = archive.relative_to(request.project_root).as_posix()
        extras["evaluation"] = evaluation
    except Exception as error:
        # 模型已成功产出，评价失败/取消单独记录，不伪称训练失败。
        extras["evaluation"] = {"status": "unavailable", "reason": str(error)}
        send_log(queue, run_id, "WARNING", f"Model ready; evaluation unavailable: {error}")
    return replace(mark_run_completed(run, model_snapshot=snapshot.relative_to(request.project_root).as_posix()),
                   engine_version=outcome.engine_version, extra_fields=extras)


def _write_result(path: Path, run: TrackingRun, points_path: str | None) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"run": _tracking_run_to_payload(run), "points_path": points_path},
                                    ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def verify_request_files(request: TrackingRequest) -> None:
    """仅比较轻量文件状态，不进行内容哈希。"""
    stat = request.video_path.stat()
    if (stat.st_size, stat.st_mtime_ns) != request.video_file_info:
        raise ProjectSessionError("Video file changed during the task")


def cancel_tracking_job(handle: Any, request: TrackingRequest) -> Path | None:
    """后台回收进程；若只取消了评价，保留已成功产出的模型。"""
    handle.cancel(timeout_s=1.0)
    ready = request.project_root / "data" / "engines" / str(request.run.run_id) / "model-ready.json"
    if request.run.task_type != "train" or not ready.is_file():
        return None
    record = json.loads(ready.read_text(encoding="utf-8"))
    run = _tracking_run_from_payload(record["run"])
    run = replace(run, extra_fields={**run.extra_fields,
        "log_path": f"data/engines/{run.run_id}.log",
        "evaluation": {"status": "cancelled", "reason": "Evaluation cancelled; trained model retained"}})
    destination = ready.with_name("task-result.json")
    _write_result(destination, run, None)
    return destination


@dataclass(frozen=True)
class TrackingCandidate:
    """后台准备的提交候选；base_project 必须仍是活动快照。"""

    base_project: Project
    project: Project
    store: TrackStore
    observations_changed: bool


def prepare_tracking_candidate(project: Project, request: TrackingRequest,
                               result_path: Path) -> TrackingCandidate:
    """在后台解析结果并按最新人工点合并；不碰活动 session。"""
    if result_path.resolve() != (request.project_root / "data" / "engines" /
                                 str(request.run.run_id) / "task-result.json").resolve():
        raise ProjectSessionError("Unexpected task result path")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    verify_request_files(request)
    run = _tracking_run_from_payload(result["run"])
    if (run.run_id != request.run.run_id or run.track_id != request.run.track_id
            or run.video_id != request.run.video_id or run.task_type != request.run.task_type):
        raise ProjectSessionError("Task result belongs to another request")
    session = _owned_session(project, request)
    if run.task_type == "infer":
        path = (request.project_root / result["points_path"]).resolve()
        expected = request.project_root / "data" / "engines" / str(run.run_id) / "observations.json"
        if path != expected.resolve():
            raise ProjectSessionError("Unexpected observation path")
        session.import_engine_points(read_observation_exchange(path), run)
    else:
        session.update_tracking_run(run)
    return TrackingCandidate(project, session.project, session._store,
                             session.project.observations != project.observations)


def read_task_log(root: Path, run: TrackingRun) -> str:
    """仅在后台读取日志末尾；旧任务没有日志时明示。"""
    relative = run.extra_fields.get("log_path") or f"data/engines/{run.run_id}.log"
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return "No saved log for this task."
    with path.open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 256_000))
        return stream.read().decode("utf-8", errors="replace")


class TrackingJobRunner:
    """应用层封装引擎与 spawn 入口，GUI 不直接创建基础设施对象。"""

    def __init__(self, adapter=None, runner=None) -> None:
        self.adapter = adapter or DLCAdapter()
        self.runner = runner or BackgroundTaskRunner()

    def start(self, request: TrackingRequest):
        return self.runner.start_task(request.run.run_id, run_tracking_worker, request, self.adapter)
