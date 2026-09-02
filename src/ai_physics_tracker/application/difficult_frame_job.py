"""应用层困难帧挖掘后台任务：不可变请求、run/产物身份绑定与原子结果（Phase 5.2）。

与 5.1 选帧任务同规则：worker 只持有冻结快照与文件指纹，不持有活动
ProjectSession；结果只含帧号与解释性分量，不创建 TrackPoint。
"""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from uuid import UUID

from ai_physics_tracker.application.difficult_frames import MiningParams
from ai_physics_tracker.application.inference_job import _project_path
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError


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
        if not (0 <= self.zone_start <= self.zone_end < self.frame_count):
            raise ValueError(
                f"working zone [{self.zone_start}, {self.zone_end}] is out of range "
                f"for frame_count={self.frame_count}"
            )
        if not isfinite(self.fps_nominal) or self.fps_nominal <= 0:
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
    原始预测与模型文件存在性及指纹一致性（R8.2）。
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
    if track is None or video is None or timeline is None:
        raise ProjectSessionError("The inference run does not match a current track/video")

    prediction_ref = run.extra_fields.get("prediction_path")
    if not isinstance(prediction_ref, str) or not prediction_ref:
        raise ProjectSessionError("The inference run has no stored raw prediction artifact")
    prediction_path = _project_path(root, prediction_ref)
    if not prediction_path.is_file():
        raise ProjectSessionError("Raw prediction artifact is missing; re-run inference")

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
        prior_correct_frames=frozenset(prior_correct_frames),
        manual_frames=manual_frames,
    )
    return DifficultFrameJobRequest(
        mining_request=mining_request,
        project_root=root,
        prediction_file_info=_file_info(prediction_path),
        model_file_info=model_info,
        video_file_info=_file_info(video_path.resolve()),
    )
