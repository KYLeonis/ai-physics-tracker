"""应用层全帧推理边界：准备不可变请求、执行引擎并读取落盘结果。"""

from concurrent.futures import CancelledError
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun, create_tracking_run, mark_run_completed,
)
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.infrastructure.engine_adapter import (
    EngineAdapter, InferenceParams, InferenceRequest,
)


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
        files = (request.model_snapshot, request.video_path, request.config_path)
        before = tuple(_stamp(path) for path in files)
        outcome = adapter.infer(run_id, queue, cancel_event, request)
        if cancel_event.is_set():
            raise CancelledError("Inference cancelled")
        if outcome.model_snapshot.resolve() != request.model_snapshot.resolve():
            raise ValueError("Engine used a different snapshot")
        if tuple(_stamp(path) for path in files) != before:
            raise ValueError("Inference input files changed during execution")
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
        exchange = request.output_dir / "observations.json"
        with exchange.open("x", encoding="utf-8") as stream:
            json.dump([asdict(point) for point in outcome.points], stream,
                      ensure_ascii=False, allow_nan=False, default=str)
        return {
            "status": "completed", "engine_version": outcome.engine_version,
            "device": outcome.device, "model_file_info": list(before[0][:2]),
            "config_file_info": list(before[2][:2]),
            "prediction_path": raw_path.name, "prediction_file_info": list(_stamp(raw_path)),
            "observations_file_info": list(_stamp(exchange)),
            "row_count": outcome.row_count, "missing_count": outcome.missing_count,
            "low_confidence_count": outcome.low_confidence_count,
        }
    except CancelledError:
        return {"status": "cancelled"}


def prepare_inference(
    session: ProjectSession,
    training_run_id: UUID,
    params: InferenceParams,
    *,
    config_path: Path | None = None,
    run_id: UUID | None = None,
) -> tuple[TrackingRun, InferenceRequest]:
    """验证模型、视频时序与文件身份，登记 run 并返回不可变推理请求。"""
    root = session.project_root
    if root is None:
        raise ProjectSessionError("Save the project before inference")
    root = root.resolve()
    trained = next((run for run in session.tracking_runs() if run.run_id == training_run_id), None)
    if trained is None or trained.task_type != "train" or trained.status != "completed":
        raise ProjectSessionError("Select a completed training run")
    track = next((item for item in session.tracks if item.track_id == trained.track_id), None)
    if track is None or track.video_id != trained.video_id:
        raise ProjectSessionError("Training run does not match a current track/video")
    if any(
        run.track_id == trained.track_id and run.status == "running"
        for run in session.tracking_runs()
    ):
        raise ProjectSessionError("This track already has an active engine task")

    video = next(item for item in session.project.videos if item.video_id == trained.video_id)
    video_path = session.video_path(video)
    if video_path is None or not video_path.is_file() or not session.can_measure(video.video_id):
        raise ProjectSessionError("Video is missing or its timing is not authorized")
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
    timeline = next(item for item in session.project.timelines if item.video_id == video.video_id)
    config = {
        **asdict(params),
        "training_run_id": str(trained.run_id),
        "shuffle": trained.config.get("shuffle", 1),
        "trainingsetindex": trained.config.get("trainingsetindex", 0),
        "timing_detail": session.measurement_timing_detail(video.video_id),
    }
    run = create_tracking_run(
        video.video_id,
        track.track_id,
        "infer",
        engine=trained.engine,
        engine_version=trained.engine_version,
        config=config,
        run_id=run_id,
    )
    output_dir = root / "data" / "engines" / str(run.run_id)
    request = InferenceRequest(
        config_path,
        video_path.resolve(),
        snapshot,
        output_dir,
        track.track_id,
        timeline,
        run.source_detail,
        video.frame_count,
        params,
        shuffle=config["shuffle"],
        trainingsetindex=config["trainingsetindex"],
        archive_model=archive_model,
    )
    recorded_stamp = trained.extra_fields.get("model_file_info")
    if recorded_stamp is not None and tuple(recorded_stamp) != _stamp(snapshot)[:2]:
        raise ProjectSessionError("Selected model file has changed; select a current training run")
    extras = {"model_file_info": list(_stamp(snapshot)[:2])}
    if not archive_model:
        extras["config_path"] = config_path.relative_to(root).as_posix()
    # legacy 归档尚不存在；失败/取消的 run 不应持有虚构文件引用。
    run = replace(
        run,
        model_snapshot=None if archive_model else snapshot.relative_to(root).as_posix(),
        extra_fields=extras,
    )
    session.record_tracking_run(run)
    return run, request


def read_inference_result(request: InferenceRequest, project_root: Path,
                          run: TrackingRun, payload: JsonObject) -> tuple[tuple[TrackPoint, ...], TrackingRun]:
    """后台读取已完成推理结果，校验结构/文件状态；不修改活动会话。"""
    folder = request.output_dir
    raw_name = payload.get("prediction_path")
    if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
        raise ProjectSessionError("Invalid prediction artifact reference")
    raw = folder / raw_name
    exchange = folder / "observations.json"
    if (list(_stamp(raw)) != payload.get("prediction_file_info")
            or list(_stamp(exchange)) != payload.get("observations_file_info")):
        raise ProjectSessionError("Inference artifacts changed before import")
    points = read_observation_exchange(exchange)
    counts = [payload.get(key) for key in ("row_count", "missing_count", "low_confidence_count")]
    if (any(type(n) is not int or n < 0 for n in counts)
            or counts[0] != request.frame_count or len(points) + counts[1] + counts[2] != counts[0]
            or any(p.confidence is None or p.confidence < request.params.min_confidence for p in points)):
        raise ProjectSessionError("Invalid prediction counts or confidence")
    extras = {**run.extra_fields, "prediction_path": raw.relative_to(project_root).as_posix(),
        "observations_path": exchange.relative_to(project_root).as_posix(),
        "model_file_info": payload["model_file_info"],
        "config_file_info": payload["config_file_info"], "device": payload["device"],
        # 预测产物指纹基线：后续消费（如 5.2 mining）可发现推理后被替换的文件
        "prediction_file_info": list(_stamp(raw)[:2]),
        "import_summary": dict(zip(("row_count", "missing_count", "low_confidence_count"), counts))}
    snapshot_ref = run.model_snapshot
    if request.archive_model:
        snapshot_ref = (folder / "model-used.pt").relative_to(project_root).as_posix()
        extras["config_path"] = (folder / "config-used.yaml").relative_to(project_root).as_posix()
        extras["model_file_info"] = list(_stamp(folder / "model-used.pt")[:2])
        extras["config_file_info"] = list(_stamp(folder / "config-used.yaml")[:2])
    completed = replace(mark_run_completed(run, model_snapshot=snapshot_ref),
                        engine_version=str(payload["engine_version"]), extra_fields=extras)
    return tuple(points), completed



def read_observation_exchange(path: Path) -> tuple[TrackPoint, ...]:
    """后台读取内部观测交换文件，不在 GUI 主线程解析批量数据。"""
    records = json.loads(path.read_text(encoding="utf-8"))
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
    return tuple(points)
