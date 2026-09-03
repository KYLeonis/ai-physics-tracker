"""应用层困难帧挖掘后台任务：不可变请求、run/产物身份绑定与原子结果（Phase 5.2）。

与 5.1 选帧任务同规则：worker 只持有冻结快照与文件指纹，不持有活动
ProjectSession；结果只含帧号与解释性分量，不创建 TrackPoint。
"""

from concurrent.futures import CancelledError
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import UUID
import json

from ai_physics_tracker.application.difficult_frames import (
    FrameCandidate, MiningParams, mine_difficult_frames,
)
from ai_physics_tracker.application.inference_job import _project_path
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    ReviewCandidate,
    ReviewPredictionSnapshot,
    get_excluded_frames_for_run,
    get_prior_correct_frames_for_run,
)
from ai_physics_tracker.application.tracking_types import FrameSelectionRequest
from ai_physics_tracker.infrastructure.engine_adapter import EngineAdapter
from ai_physics_tracker.infrastructure.task_runner import (
    BackgroundTaskRunner, send_log, send_progress,
)


@dataclass(frozen=True)
class DifficultFrameMiningRequest:
    """单个 completed infer run 的挖掘请求；绑定原始预测产物与视频身份（R2.1）。

    prior_correct_frames 为调用方显式传入的既有 Correct 帧集合
    （5.2 无审阅历史时为空）；manual_frames 为已有 active manual 标注帧，
    这些帧已有 ground truth，不进入候选池。
    """

    run_id: UUID
    video_id: UUID
    track_id: UUID
    video_path: Path                 # 视觉多样性抽帧用；绝对路径
    prediction_path: Path            # 原始预测产物（HDF5/CSV）；绝对路径
    model_path: Path                 # 该 run 使用的模型快照；绝对路径
    frame_count: int
    zone_start: int                  # working zone 起始帧（含）
    zone_end: int                    # working zone 结束帧（含）
    fps_nominal: float
    params: MiningParams
    prior_correct_frames: frozenset[int]
    manual_frames: frozenset[int]

    def __post_init__(self) -> None:
        if type(self.frame_count) is not int or self.frame_count <= 0:
            raise ValueError("frame_count must be a positive integer")
        if type(self.zone_start) is not int or type(self.zone_end) is not int:
            raise ValueError("zone_start and zone_end must be integers")
        if not (0 <= self.zone_start <= self.zone_end < self.frame_count):
            raise ValueError(
                f"working zone [{self.zone_start}, {self.zone_end}] is out of range "
                f"for frame_count={self.frame_count}"
            )
        if (isinstance(self.fps_nominal, bool) or not isinstance(self.fps_nominal, (int, float))
                or not isfinite(float(self.fps_nominal)) or self.fps_nominal <= 0):
            raise ValueError("fps_nominal must be finite and positive")
        for label, path in (("video_path", self.video_path), ("prediction_path", self.prediction_path),
                            ("model_path", self.model_path)):
            if not path.is_absolute():
                raise ValueError(f"{label} must be an absolute path")
        for label, frames in (("prior_correct_frames", self.prior_correct_frames),
                              ("manual_frames", self.manual_frames)):
            if any(type(f) is not int or not 0 <= f < self.frame_count for f in frames):
                raise ValueError(f"{label} must contain in-range frame indices")


@dataclass(frozen=True)
class DifficultFrameJobRequest:
    """后台挖掘请求；封装 mining 请求与产物文件指纹（st_size, st_mtime_ns）。"""

    mining_request: DifficultFrameMiningRequest
    project_root: Path
    prediction_file_info: tuple[int, int]
    model_file_info: tuple[int, int]
    video_file_info: tuple[int, int]


def _file_info(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def prepare_difficult_frame_request(
    session: ProjectSession,
    infer_run_id: UUID,
    params: MiningParams,
    *,
    prior_correct_frames: frozenset[int] = frozenset(),
) -> DifficultFrameJobRequest:
    """验证 completed infer run 与产物身份，捕获不可变挖掘请求（Phase 5.2 R2.1）。

    不读取预测内容、不调用引擎；仅校验 run 状态、video/track/timeline、
    原始预测与模型文件存在性、run 从属目录与指纹基线（R8.2）。
    """
    if not isinstance(params, MiningParams):
        raise ProjectSessionError("params must be MiningParams")
    root = session.project_root
    if root is None:
        raise ProjectSessionError("Save the project before mining difficult frames")
    root = root.resolve()

    run = next((r for r in session.tracking_runs() if r.run_id == infer_run_id), None)
    if run is None or run.task_type != "infer" or run.status != "completed":
        raise ProjectSessionError("Select a completed inference run")

    track = next((t for t in session.tracks if t.track_id == run.track_id), None)
    video = next((v for v in session.project.videos if v.video_id == run.video_id), None)
    timeline = next((t for t in session.project.timelines if t.video_id == run.video_id), None)
    if track is None or video is None or timeline is None or track.video_id != run.video_id:
        raise ProjectSessionError("The inference run does not match a current track/video")

    prediction_ref = run.extra_fields.get("prediction_path")
    if not isinstance(prediction_ref, str) or not prediction_ref:
        raise ProjectSessionError("The inference run has no stored raw prediction artifact")
    if Path(prediction_ref).is_absolute():
        # 写入方恒存项目内相对 posix 路径；绝对引用无法证明属于本 run 的产物目录
        raise ProjectSessionError("Raw prediction artifact reference must be project-relative")
    prediction_path = _project_path(root, prediction_ref)
    # 产物从属校验（R2.1 不混合不同 run）：推理只写自己的 data/engines/<run_id>/ 目录
    if prediction_path.parent != (root / "data" / "engines" / str(run.run_id)).resolve():
        raise ProjectSessionError("Raw prediction artifact does not belong to this run")
    if not prediction_path.is_file():
        raise ProjectSessionError("Raw prediction artifact is missing; re-run inference")
    prediction_info = _file_info(prediction_path)
    recorded_prediction_info = run.extra_fields.get("prediction_file_info")
    if recorded_prediction_info is not None and list(prediction_info) != list(recorded_prediction_info):
        raise ProjectSessionError("Raw prediction artifact has changed; re-run inference")

    if not run.model_snapshot:
        raise ProjectSessionError("The inference run has no model snapshot reference")
    model_path = _project_path(root, run.model_snapshot)
    if not model_path.is_file():
        raise ProjectSessionError("The model snapshot of this run is missing")
    recorded_model_info = run.extra_fields.get("model_file_info")
    model_info = _file_info(model_path)
    if recorded_model_info is not None and list(model_info) != list(recorded_model_info):
        raise ProjectSessionError("The model snapshot of this run has changed; re-run inference")

    video_path = session.video_path(video)
    if video_path is None or not video_path.is_file():
        raise ProjectSessionError("Video file is missing; cannot mine difficult frames")

    zone_start, zone_end = timeline.working_zone
    if not 0 <= zone_start <= zone_end < video.frame_count:
        raise ProjectSessionError("Timeline working zone is out of range for this video")

    manual_frames = frozenset(
        p.frame_index for p in session.manual_points(track.track_id)
        if zone_start <= p.frame_index <= zone_end
    )
    # AC-8 / R2.8: 排除本 run 历史已审阅的 accepted 和 skipped 帧（过滤在有效帧范围内）
    excluded_review_frames = frozenset(
        f for f in get_excluded_frames_for_run(run) if 0 <= f < video.frame_count
    )
    all_excluded = manual_frames | excluded_review_frames

    # prior_correct_frames 若未显式传入，自动从本 run 的审核记录中读取（过滤在有效帧范围内）
    raw_prior_correct = (
        frozenset(prior_correct_frames)
        if prior_correct_frames
        else get_prior_correct_frames_for_run(run)
    )
    resolved_prior_correct = frozenset(
        f for f in raw_prior_correct if 0 <= f < video.frame_count
    )

    mining_request = DifficultFrameMiningRequest(
        run_id=run.run_id,
        video_id=video.video_id,
        track_id=track.track_id,
        video_path=video_path.resolve(),
        prediction_path=prediction_path,
        model_path=model_path,
        frame_count=video.frame_count,
        zone_start=zone_start,
        zone_end=zone_end,
        fps_nominal=timeline.fps_nominal,
        params=params,
        prior_correct_frames=resolved_prior_correct,
        manual_frames=all_excluded,
    )
    return DifficultFrameJobRequest(
        mining_request=mining_request,
        project_root=root,
        prediction_file_info=_file_info(prediction_path),
        model_file_info=model_info,
        video_file_info=_file_info(video_path.resolve()),
    )


def _verify_file(path: Path, expected: tuple[int, int], label: str) -> None:
    """轻量文件指纹复核：不读内容，只比 (st_size, st_mtime_ns)。"""
    try:
        stat = path.stat()
    except OSError as error:
        raise ProjectSessionError(f"{label} file is inaccessible: {error}") from error
    if (stat.st_size, stat.st_mtime_ns) != tuple(expected):
        raise ProjectSessionError(f"{label} file changed before difficult frame mining started")


@dataclass(frozen=True)
class DifficultFrameResult:
    """挖掘结果；candidates 按总分降序，含帧号、原始预测与解释性分量（R2.4）。"""

    request_id: UUID
    run_id: UUID
    candidates: tuple[ReviewCandidate, ...]
    actual_n: int
    diversity_status: str
    params_snapshot: dict[str, Any]

    def to_active_batch(self) -> ActiveReviewBatch:
        """转换为可供审核队列控制器消费的 ActiveReviewBatch。"""
        return ActiveReviewBatch(
            request_id=self.request_id,
            params_snapshot=dict(self.params_snapshot),
            candidates=self.candidates,
        )


def run_difficult_frame_worker(
    request_id: UUID,
    queue: Any,
    cancel_event: Any,
    job_request: DifficultFrameJobRequest,
    adapter: EngineAdapter,
) -> dict[str, Any]:
    """后台挖掘 worker：指纹复核 → 全帧读取 → 纯策略 → 视觉多样性 → 原子落盘。

    取消通过 CancelledError 优雅返回 status=cancelled；错误以异常上报。
    结果写入 `data/engines/<request_id>/difficult-frames-result.json`。
    """
    mining = job_request.mining_request
    _verify_file(mining.prediction_path, job_request.prediction_file_info, "Prediction")
    _verify_file(mining.model_path, job_request.model_file_info, "Model")
    _verify_file(mining.video_path, job_request.video_file_info, "Video")
    if cancel_event.is_set():
        raise CancelledError()

    send_progress(queue, request_id, 0, 1, message="Reading raw predictions")
    predictions = adapter.read_raw_predictions(
        mining.prediction_path, frame_count=mining.frame_count)
    if cancel_event.is_set():
        raise CancelledError()

    outcome = mine_difficult_frames(
        predictions,
        zone_start=mining.zone_start,
        zone_end=mining.zone_end,
        fps_nominal=mining.fps_nominal,
        params=mining.params,
        prior_correct_frames=mining.prior_correct_frames,
        manual_frames=mining.manual_frames,
    )
    send_progress(queue, request_id, 1, 2,
                  message=f"Pool of {outcome.pool_size} frames; selecting top candidates")
    candidates, diversity_status = _apply_visual_diversity(
        adapter, mining, outcome, queue, cancel_event, request_id)

    pred_by_frame = {p.frame_index: p for p in predictions}
    payload = {
        "request_id": str(request_id),
        "run_id": str(mining.run_id),
        "video_id": str(mining.video_id),
        "track_id": str(mining.track_id),
        "diversity_status": diversity_status,
        "actual_n": len(candidates),
        "params_snapshot": {**outcome.params_snapshot, "diversity_status": diversity_status},
        "candidates": [
            {
                "frame_index": candidate.frame_index,
                "prediction": (
                    None
                    if pred_by_frame.get(candidate.frame_index) is None
                    or not isfinite(pred_by_frame[candidate.frame_index].pixel_x)
                    or not isfinite(pred_by_frame[candidate.frame_index].pixel_y)
                    or not isfinite(pred_by_frame[candidate.frame_index].confidence)
                    else {
                        "pixel_x": float(pred_by_frame[candidate.frame_index].pixel_x),
                        "pixel_y": float(pred_by_frame[candidate.frame_index].pixel_y),
                        "confidence": float(pred_by_frame[candidate.frame_index].confidence),
                    }
                ),
                "components": candidate.components,
                "raw_components": candidate.raw_components,
                "reasons": list(candidate.reasons),
                "total_score": candidate.total_score,
            }
            for candidate in candidates
        ],
    }
    out_dir = job_request.project_root / "data" / "engines" / str(request_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "difficult-frames-result.json"
    tmp = out_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(out_file)
    send_progress(queue, request_id, 2, 2, message=f"Selected {len(candidates)} difficult frames")
    return {
        "status": "completed",
        "result_path": out_file.relative_to(job_request.project_root).as_posix(),
    }


class _RemappedRunIdQueue:
    """把适配器发出的消息 run_id 统一改写为本任务 id（dataclass 消息不可变）。"""

    def __init__(self, queue: Any, run_id: UUID) -> None:
        self._queue, self._run_id = queue, run_id

    def put(self, message: Any) -> None:
        if hasattr(message, "run_id") and message.run_id != self._run_id:
            message = replace(message, run_id=self._run_id)
        self._queue.put(message)


def _apply_visual_diversity(
    adapter: EngineAdapter,
    mining: DifficultFrameMiningRequest,
    outcome: Any,
    queue: Any,
    cancel_event: Any,
    request_id: UUID,
) -> tuple[tuple[FrameCandidate, ...], str]:
    """对时间去重后的 shortlist 复用 5.1 K-means 做视觉多样性，再取 Top N。

    shortlist 不超过 top_n 时无需多样性；K-means 失败（如视频不可解码）按
    总分顺序补齐，不静默改变候选分数，失败原因记入 diversity_status。
    """
    params = mining.params
    shortlist = outcome.shortlist
    if len(shortlist) <= params.top_n:
        return shortlist, "not_needed"

    try:
        selection_request = FrameSelectionRequest(
            video_id=mining.video_id,
            track_id=mining.track_id,
            video_path=mining.video_path,
            frame_count=mining.frame_count,
            zone_start=mining.zone_start,
            zone_end=mining.zone_end,
            n_frames=params.top_n,
            algorithm="kmeans",
            excluded_frames=frozenset(),
            seed=params.seed,
            candidate_frames=frozenset(candidate.frame_index for candidate in shortlist),
        )
        # suggest_frames 的进度消息携带 request.track_id 作为 run_id；
        # 统一改写为本挖掘任务 id，避免未来 GUI 按任务过滤时串台
        selection = adapter.suggest_frames(
            selection_request, _RemappedRunIdQueue(queue, request_id), cancel_event)
        selected = frozenset(selection.suggested_frames)
    except CancelledError:
        raise
    except Exception as error:
        send_log(queue, request_id, "WARNING", f"Visual diversity unavailable: {error}")
        return shortlist[:params.top_n], f"unavailable: {error}"

    # 先取被 K-means 选中的（保持总分降序），再按总分补齐至 top_n
    ordered = [candidate for candidate in shortlist if candidate.frame_index in selected]
    for candidate in shortlist:
        if len(ordered) >= params.top_n:
            break
        if candidate.frame_index not in selected:
            ordered.append(candidate)
    return tuple(ordered[:params.top_n]), "applied"


def read_difficult_frame_result(project_root: Path, request_id: UUID) -> DifficultFrameResult:
    """读取已完成的挖掘结果文件（供 GUI/基准脚本回调使用）。

    文件损坏或字段缺失统一转成 ProjectSessionError，调用方按任务失败处理。
    """
    out_file = (project_root / "data" / "engines" / str(request_id)
                / "difficult-frames-result.json")
    if not out_file.is_file():
        raise ProjectSessionError(f"Difficult frame result not found: {out_file}")
    try:
        payload = json.loads(out_file.read_text(encoding="utf-8"))

        def _parse_pred(rec: dict[str, Any]) -> ReviewPredictionSnapshot | None:
            pred_dict = rec.get("prediction")
            if not isinstance(pred_dict, dict):
                return None
            try:
                px = float(pred_dict["pixel_x"])
                py = float(pred_dict["pixel_y"])
                conf = float(pred_dict["confidence"])
                if isfinite(px) and isfinite(py) and isfinite(conf):
                    return ReviewPredictionSnapshot(px, py, conf)
            except (KeyError, TypeError, ValueError):
                pass
            return None

        candidates = tuple(
            ReviewCandidate(
                frame_index=int(record["frame_index"]),
                prediction=_parse_pred(record),
                components={name: float(value) for name, value in record["components"].items()},
                raw_components={name: float(value) for name, value in record["raw_components"].items()},
                reasons=tuple(record["reasons"]),
                total_score=float(record["total_score"]),
            )
            for record in payload["candidates"]
        )
        result = DifficultFrameResult(
            request_id=UUID(payload["request_id"]),
            run_id=UUID(payload["run_id"]),
            candidates=candidates,
            actual_n=int(payload["actual_n"]),
            diversity_status=str(payload["diversity_status"]),
            params_snapshot=payload["params_snapshot"],
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as error:
        raise ProjectSessionError(
            f"Difficult frame result is corrupt: {out_file}: {error}") from error
    return result


class DifficultFrameRunner:
    """应用层封装挖掘后台任务；复用 BackgroundTaskRunner（与 5.1 同模式）。"""

    def __init__(self, adapter: EngineAdapter | None = None, runner: Any = None) -> None:
        if adapter is None:
            from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
            adapter = DLCAdapter()
        self.adapter: EngineAdapter = adapter
        self.runner = runner or BackgroundTaskRunner()

    def start(self, job_request: DifficultFrameJobRequest, request_id: UUID) -> Any:
        """启动后台挖掘任务，返回 task handle。"""
        return self.runner.start_task(
            request_id, run_difficult_frame_worker, job_request, self.adapter
        )
