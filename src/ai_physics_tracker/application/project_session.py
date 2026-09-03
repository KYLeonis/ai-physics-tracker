"""与 Qt 无关的标注会话：协调 Project 快照、TrackStore 与视频登记。

application 层组件：持有当前 Project（frozen）与 TrackStore，GUI 不
直接修改 Project（phase2-requirements.md §2 R1/R5）。每次写操作经
TrackStore 语义落地后同步生成新的 Project 快照；dirty 状态驱动
2.4 的未保存提示。
"""

import logging
import json
from copy import deepcopy
from dataclasses import replace
from math import isfinite
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING
from uuid import UUID, uuid4

from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    DISPOSITION_ACCEPTED,
    DISPOSITION_CORRECTED,
    DISPOSITION_SKIPPED,
    ReviewBatchSummary,
    ReviewRecord,
    SUGGESTED_FRAME_REVIEW_KEY,
    SuggestedFrameReviewState,
    attach_review_state,
    compute_batch_summary,
    extract_review_state,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.video_timing import TimingReport, approximation_errors
from ai_physics_tracker.domain.calibration import Calibration, CalibrationTransform
from ai_physics_tracker.domain.kinematics import (
    batch_pixel_to_world,
    dense_to_sparse_records,
    derive_unit,
    differentiate_savgol,
    expand_to_dense_grid,
    smooth_savgol,
)
from ai_physics_tracker.domain.project import (
    Project,
    add_calibration as add_domain_calibration,
    add_video,
    create_project,
    delete_calibration as delete_domain_calibration,
    delete_track,
    register_video_reference,
    relink_video,
    replace_calibration as replace_domain_calibration,
    set_active_calibration as set_domain_active_calibration,
)
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput, mark_tracks_stale
from ai_physics_tracker.domain.timeline import (
    TIME_COMPARISON_TOLERANCE_S,
    Timeline,
    frame_to_time,
)
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import TrackingRun, mark_run_failed
from ai_physics_tracker.domain.track_store import (
    BatchWriteResult,
    TrackStore,
    resolve_effective_point,
    resolve_effective_points,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.domain.video import Video

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ai_physics_tracker.application.kinematics_job import KinematicsResult
    from ai_physics_tracker.application.tracking_job import TrackingCandidate


class ProjectRepositoryPort(Protocol):
    """持久化端口的最低契约；由 infrastructure 实现、组合根注入。"""

    def save(self, project_root: Path, project: Project) -> Project: ...

    def load(self, project_root: Path) -> Project: ...

    def create_from_project(self, project_root: Path, project: Project) -> Project: ...

    def save_as(self, source_root: Path, destination_root: Path, project: Project) -> Project: ...

    def resolve_video_path(self, project_root: Path, video: Video) -> Path | None: ...

# 撤销栈深度上限（快照为不可变元组的引用组合，成本极低）
UNDO_STACK_LIMIT = 50

# 自动分配的 Track 颜色轮转调色板（#RRGGBB，domain/track.py 校验格式）
TRACK_COLOR_PALETTE = (
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#46f0f0",
    "#f032e6",
    "#bcf60c",
    "#fabebe",
    "#008080",
)


# 会话历史快照（含 TrackStore 数据、标定、派生数据与可选的审核事务作用域快照）
_SessionDataSnapshot = tuple[
    tuple[Track, ...],
    tuple[TrackPoint, ...],
    tuple[Calibration, ...],
    dict[UUID, UUID],
    tuple[DerivedData, ...],
    dict[UUID, dict[str, Any] | None] | None,
]


class ProjectSessionError(Exception):
    """标注会话的用户可见错误。"""


class ProjectSession:
    """单视频人工标注的最小会话：视频登记、Track 与 manual 点写入。"""

    def __init__(
        self,
        repository: ProjectRepositoryPort,
        project: Project,
        project_root: Path | None = None,
    ) -> None:
        self._repository = repository
        self._project = project
        # Project 及其成员均为 frozen 数据类；保存基线共享引用即可，
        # 写路径一律 replace() 产生新对象，不原地修改（见 detached()）。
        self._saved_project = project
        self._project_root = project_root
        self._store = TrackStore(project.tracks, project.observations)
        self._verified_videos: set[UUID] = set()
        self._approximate_timing: dict[UUID, str] = {}
        self._undo_stack: list[_SessionDataSnapshot] = []
        self._redo_stack: list[_SessionDataSnapshot] = []

    @classmethod
    def start(
        cls,
        repository: ProjectRepositoryPort,
        name: str = "Untitled session",
    ) -> "ProjectSession":
        """创建一个内存中的新项目（无根目录，保存前需先落盘到目录）。"""

        return cls(repository, create_project(name))

    @property
    def project(self) -> Project:
        return self._project

    @property
    def project_root(self) -> Path | None:
        return self._project_root

    @property
    def is_dirty(self) -> bool:
        """自上次保存（或创建）以来是否发生写操作。"""

        # 浏览位置/UI 状态和保存时间不属于未保存的科学数据内容。
        current = replace(self._project, ui_state={}, modified_at=self._saved_project.modified_at)
        baseline = replace(self._saved_project, ui_state={})
        return current != baseline

    @property
    def tracks(self) -> tuple[Track, ...]:
        return self._store.tracks

    @property
    def calibrations(self) -> tuple[Calibration, ...]:
        return self._project.calibrations

    def active_calibration(self, video_id: UUID) -> Calibration | None:
        """返回指定视频当前生效的标定对象；未设置时返回 None。"""

        cal_id = self._project.active_calibration_by_video.get(video_id)
        if cal_id is None:
            return None
        return next(
            (c for c in self._project.calibrations if c.calibration_id == cal_id),
            None,
        )

    def register_external_video(
        self, path: Path, info: VideoStreamInfo, *, sha256: str | None = None
    ) -> tuple[Video, Timeline]:
        """以外部引用（file_path=None）登记视频及其 Timeline。"""

        if info.timing_status != "cfr":
            raise ProjectSessionError("video timing is not verified CFR; browsing only")
        video, timeline = self.register_preview_video(path, info, sha256=sha256)
        self._verified_videos.add(video.video_id)
        return video, timeline

    def register_preview_video(
        self, path: Path, info: VideoStreamInfo, *, sha256: str | None = None
    ) -> tuple[Video, Timeline]:
        """保存只读浏览引用，不授予新增测量能力，也不伪称 CFR。"""

        video_id = uuid4()
        video = Video(
            video_id=video_id,
            file_path=None,
            original_path=str(path),
            display_name=path.name,
            width_px=info.width_px,
            height_px=info.height_px,
            fps_container=info.fps_container,
            frame_count=info.frame_count,
            container_format=info.container_format,
            sha256=sha256,
            vfr_suspected=info.timing_status in ("vfr_suspected", "near_cfr"),
        )
        timeline = Timeline(
            video_id=video_id,
            fps_nominal=info.fps_container,
            working_zone=(0, info.frame_count - 1),
        )
        self._project = register_video_reference(self._project, video, timeline)
        return video, timeline

    def add_track(self, video_id: UUID, name: str | None = None) -> Track:
        """创建 Track；名称缺省自动递增，颜色按调色板轮转。"""

        final_name = name.strip() if name and name.strip() else self._next_track_name()
        color = TRACK_COLOR_PALETTE[len(self._store.tracks) % len(TRACK_COLOR_PALETTE)]
        track = Track(
            track_id=uuid4(),
            video_id=video_id,
            name=final_name,
            color=color,
            created_at=utc_now(),
        )
        candidate = TrackStore(self._store.tracks, self._store.observations)
        candidate.add_track(track)
        self._commit_store(candidate, self._project.derived)
        return track

    def remove_track(self, track_id: UUID) -> None:
        """删除 Track 并级联删除其观测、派生数据与 TrackingRun 记录。"""

        candidate = delete_track(self._project, track_id)
        # 提交整个 candidate：runs 级联发生在 delete_track 返回的聚合里，
        # 只回填 tracks/observations/derived 会把已删除的 run 带回来。
        self._commit_project(candidate, TrackStore(candidate.tracks, candidate.observations))

    def mark_point(
        self,
        track_id: UUID,
        frame_index: int,
        pixel_x: float,
        pixel_y: float,
    ) -> TrackPoint:
        """在当前帧落一个 manual 点；time_s 经 Timeline 冻结（§5.2）。"""

        track = next(
            (item for item in self._store.tracks if item.track_id == track_id), None
        )
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")
        if track.video_id not in self._verified_videos:
            raise ProjectSessionError("video timing is not verified CFR; new measurements disabled")
        timeline = next(
            (
                item
                for item in self._project.timelines
                if item.video_id == track.video_id
            ),
            None,
        )
        if timeline is None:
            raise ProjectSessionError(
                f"no timeline registered for video of track {track.name}"
            )
        now = utc_now()
        point = TrackPoint(
            point_id=uuid4(),
            track_id=track_id,
            frame_index=frame_index,
            time_s=frame_to_time(frame_index, timeline),
            pixel_x=pixel_x,
            pixel_y=pixel_y,
            source="manual",
            source_detail=self._approximate_timing.get(track.video_id),
            # data-model.md §3.5：manual 缺省 visible（用户亲眼所见落点）
            visibility="visible",
            status="active",
            created_at=now,
            modified_at=now,
        )
        candidate = TrackStore(self._store.tracks, self._store.observations)
        candidate.add_manual_point(point)
        self._commit_store(candidate, mark_tracks_stale(self._project.derived, {track_id}))
        logger.info(
            "manual point marked track=%s frame=%d pixel=(%.1f, %.1f)",
            track.name,
            frame_index,
            pixel_x,
            pixel_y,
        )
        return point

    def manual_points(self, track_id: UUID) -> tuple[TrackPoint, ...]:
        """该 Track 的全部 active manual 点（overlay 绘制用）。"""

        return tuple(
            point
            for point in self._store.query(track_id=track_id)
            if point.source == "manual" and point.status == "active"
        )

    def effective_point(
        self, track_id: UUID, frame_index: int
    ) -> TrackPoint | None:
        """该帧生效观测（data-model.md §4.3）：manual 优先。"""

        return resolve_effective_point(
            self._store.observations, track_id, frame_index
        )

    def effective_points(self, track_id: UUID) -> tuple[TrackPoint, ...]:
        """返回一个 Track 的全部 active 生效观测，按 frame_index 排序。"""

        return resolve_effective_points(self._store.observations, track_id)

    def import_engine_points(
        self,
        points: tuple[TrackPoint, ...],
        completed_run: TrackingRun,
    ) -> BatchWriteResult:
        """原子导入已完成推理批次，并记录导入统计。"""

        registered_run = next(
            (run for run in self._project.tracking_runs
             if run.run_id == completed_run.run_id),
            None,
        )
        if registered_run is None:
            raise ProjectSessionError(
                f"unknown tracking run_id: {completed_run.run_id}"
            )
        if registered_run.status != "running" or completed_run.status != "completed":
            raise ProjectSessionError(
                "engine import requires a registered running infer run and a completed result"
            )
        if registered_run.task_type != "infer":
            raise ProjectSessionError("engine import requires an infer run")
        if (
            completed_run.video_id != registered_run.video_id
            or completed_run.track_id != registered_run.track_id
            or completed_run.engine != registered_run.engine
            or completed_run.task_type != registered_run.task_type
            or completed_run.source_detail != registered_run.source_detail
            or completed_run.config != registered_run.config
            or (registered_run.model_snapshot is not None
                and completed_run.model_snapshot != registered_run.model_snapshot)
            or completed_run.created_at != registered_run.created_at
            or (registered_run.extra_fields.get("model_sha256") is not None
                and completed_run.extra_fields.get("model_sha256")
                != registered_run.extra_fields["model_sha256"])
        ):
            raise ProjectSessionError("completed run identity or configuration does not match")

        track = next(
            (item for item in self._store.tracks
             if item.track_id == registered_run.track_id),
            None,
        )
        if track is None or track.video_id != registered_run.video_id:
            raise ProjectSessionError("completed run track does not match the current project")
        if not self.can_measure(registered_run.video_id):
            raise ProjectSessionError(
                "Video timing is not authorized; engine import is disabled"
            )
        video = next(
            (item for item in self._project.videos
             if item.video_id == registered_run.video_id),
            None,
        )
        timeline = next(
            (item for item in self._project.timelines
             if item.video_id == registered_run.video_id),
            None,
        )
        if video is None or timeline is None:
            raise ProjectSessionError("completed run video has no current timeline")

        for point in points:
            if (
                point.track_id != registered_run.track_id
                or point.source != registered_run.engine
                or point.source_detail != registered_run.source_detail
            ):
                raise ProjectSessionError("engine point does not match the completed run")
            if type(point.frame_index) is not int or not 0 <= point.frame_index < video.frame_count:
                raise ProjectSessionError(
                    f"engine point frame_index exceeds video frame_count: {point.frame_index}"
                )
            expected_time = frame_to_time(point.frame_index, timeline)
            if abs(point.time_s - expected_time) >= TIME_COMPARISON_TOLERANCE_S:
                raise ProjectSessionError(
                    f"engine point time does not match current timeline at frame {point.frame_index}"
                )

        candidate = TrackStore(self._store.tracks, self._store.observations)
        try:
            result = candidate.add_engine_points(points)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error

        completed_with_summary = self._with_import_summary(
            registered_run, completed_run, result
        )
        runs = tuple(
            completed_with_summary if run.run_id == completed_run.run_id else run
            for run in self._project.tracking_runs
        )
        if result.inserted:
            updated_project = replace(
                self._project,
                observations=candidate.observations,
                derived=mark_tracks_stale(
                    self._project.derived, {registered_run.track_id}
                ),
                tracking_runs=runs,
            )
            self._commit_project(updated_project, candidate)
        else:
            self._project = replace(self._project, tracking_runs=runs)
        return result

    def save(self) -> Project:
        """保存到已绑定的项目根目录并清除 dirty；无根目录时报错。"""

        if self._project_root is None:
            raise ProjectSessionError(
                "project has no root directory; use save-as workflow first"
            )
        self._project = self._repository.save(self._project_root, self._project)
        self._saved_project = self._project
        # 保存点是安全边界：跨保存的回溯会让 dirty 语义混乱
        self._undo_stack.clear()
        self._redo_stack.clear()
        return self._project

    @classmethod
    def load(cls, repository: ProjectRepositoryPort, project_root: Path) -> "ProjectSession":
        """候选会话工厂；失败不触碰当前窗口持有的会话。"""

        session = cls(repository, repository.load(project_root), project_root.resolve())
        for run in session.tracking_runs():
            if run.status in {"pending", "running"}:
                session.update_tracking_run(mark_run_failed(run, "Previous task was interrupted; start a new task"))
        return session

    def accept_saved_snapshot(self, saved: "ProjectSession") -> None:
        """更新磁盘保存基线，保持活动会话与保存期间产生的数据。"""
        if saved.project.project_id != self.project.project_id:
            raise ProjectSessionError("Saved snapshot belongs to another project")
        changed = self._current_data_snapshot() != saved._current_data_snapshot()
        self._project_root = saved.project_root
        self._saved_project = saved._saved_project
        self._project = replace(self._project, modified_at=saved.project.modified_at,
                                ui_state=saved.project.ui_state)
        # 保存模态窗口期间若后台产生了新数据，保留一次回到该保存点的撤销。
        self._undo_stack = [saved._current_data_snapshot()] if changed else []
        self._redo_stack.clear()

    def apply_tracking_candidate(self, candidate: "TrackingCandidate") -> bool:
        """主线程只接收仍匹配当前快照的后台候选；过期时由调用方重新准备。"""
        if self._project is not candidate.base_project:
            return False
        if candidate.observations_changed:
            self._commit_project(candidate.project, candidate.store)
        else:
            self._project = candidate.project
        return True

    def save_as(self, destination: Path) -> Project:
        """首存或另存，IO 成功后才提交根目录、clean 基线与历史边界。"""

        destination = destination.resolve()
        if self._project_root is None:
            saved = self._repository.create_from_project(destination, self._project)
        else:
            saved = self._repository.save_as(self._project_root, destination, self._project)
        self._project = saved
        self._project_root = destination
        self._saved_project = saved
        self._undo_stack.clear()
        self._redo_stack.clear()
        return saved

    def detached(self) -> "ProjectSession":
        """后台 IO 使用独立快照；活动会话不被工作线程修改。

        Project 全链路（含 Track/TrackPoint/Calibration/DerivedData/
        TrackingRun/元组容器）是 frozen 数据类，写路径只经 replace()
        产生新聚合，因此这里共享不可变结构而不是 deepcopy——deepcopy
        使成本随观测数线性增长并在 GUI 线程上放大（review F5）。
        前提契约：任何代码不得原地修改 ui_state/extra_fields 等 dict，
        需要变更时先复制再 replace（update_view_state 已遵循）。
        """

        candidate = ProjectSession(self._repository, self._project, self._project_root)
        candidate._saved_project = self._saved_project
        candidate._verified_videos = set(self._verified_videos)
        candidate._approximate_timing = dict(self._approximate_timing)
        candidate._undo_stack = list(self._undo_stack)
        candidate._redo_stack = list(self._redo_stack)
        return candidate

    def update_view_state(self, state: JsonObject) -> None:
        """只更新 workflow 命名空间，未知键/其他插件状态保留。"""

        ui_state = deepcopy(self._project.ui_state)
        existing = ui_state.get("workflow", {})
        if isinstance(existing, dict) and existing.get("version", 1) != 1:
            return  # 未来版本命名空间保留，不用当前 UI 状态降级覆盖。
        workflow = dict(existing) if isinstance(existing, dict) else {}
        workflow.update(state)
        ui_state["workflow"] = workflow
        self._project = replace(self._project, ui_state=ui_state)

    def relink(self, video_id: UUID, path: Path) -> None:
        """提交已经过媒体身份校验的外部 locator，不修改观测与 ID。"""

        self._project = relink_video(self._project, video_id, file_path=None,
                                    original_path=str(path.resolve()))
        self._verified_videos.discard(video_id)
        self._approximate_timing.pop(video_id, None)

    def confirm_video_timing(self, video_id: UUID, report: TimingReport) -> None:
        """应用在本次文件探测完成后授予测量能力；该集合不持久化。"""

        self._approximate_timing.pop(video_id, None)
        if report.status == "cfr":
            self._verified_videos.add(video_id)
        else:
            self._verified_videos.discard(video_id)

    def record_media_validation(self, video_id: UUID, report: TimingReport, sha256: str | None) -> None:
        """GUI 线程合并验证结果，不替换用户在探测期间操作的项目快照。"""

        videos = tuple(replace(video, sha256=sha256 or video.sha256,
                               vfr_suspected=(video.vfr_suspected if report.status == "unknown"
                                              else report.status in ("near_cfr", "vfr_suspected")))
                       if video.video_id == video_id else video for video in self._project.videos)
        self._project = replace(self._project, videos=videos)
        self.confirm_video_timing(video_id, report)

    def accept_approximate_timing(self, video_id: UUID, report: TimingReport) -> None:
        """仅在 UI 明确确认后调用；仍在应用层再次检查完整性与当前时间轴误差。"""

        video = next(item for item in self._project.videos if item.video_id == video_id)
        timeline = next(item for item in self._project.timelines if item.video_id == video_id)
        errors = approximation_errors(report, timeline.fps_nominal)
        if errors is None or report.frame_count != video.frame_count:
            raise ProjectSessionError("timing approximation exceeds the allowed error budget")
        self._approximate_timing[video_id] = json.dumps({
            "timing_method": "near_cfr_user_accepted_v1",
            "fps_nominal": timeline.fps_nominal,
            "max_grid_error_s": errors[0], "max_interval_error_s": errors[1],
        }, sort_keys=True)
        self._verified_videos.add(video_id)

    def video_path(self, video: Video) -> Path | None:
        """缺媒体为可恢复状态；只解析，不自动修改 locator。"""

        if self._project_root is not None:
            return self._repository.resolve_video_path(self._project_root, video)
        path = Path(video.original_path) if video.original_path else None
        return path if path is not None and path.is_file() else None

    def resolve_video_path(self, video: Video) -> Path | None:
        """解析视频文件的可访问本地路径（video_path 别名）。"""
        return self.video_path(video)

    def record_tracking_run(self, run: TrackingRun) -> None:
        """登记一个新的 TrackingRun。"""
        if any(r.run_id == run.run_id for r in self._project.tracking_runs):
            raise ProjectSessionError(f"tracking run_id already exists: {run.run_id}")
        self._project = replace(
            self._project,
            tracking_runs=(*self._project.tracking_runs, run),
        )

    def update_tracking_run(self, run: TrackingRun) -> None:
        """更新已存在的 TrackingRun 状态或结果。"""
        found = False
        runs: list[TrackingRun] = []
        for existing in self._project.tracking_runs:
            if existing.run_id == run.run_id:
                runs.append(run)
                found = True
            else:
                runs.append(existing)
        if not found:
            raise ProjectSessionError(f"unknown tracking run_id: {run.run_id}")
        self._project = replace(self._project, tracking_runs=tuple(runs))

    def tracking_runs(self, track_id: UUID | None = None) -> tuple[TrackingRun, ...]:
        """返回项目中的 TrackingRun，可选按 track_id 过滤。"""
        if track_id is None:
            return self._project.tracking_runs
        return tuple(r for r in self._project.tracking_runs if r.track_id == track_id)

    def add_calibration(
        self,
        video_id: UUID | Calibration,
        scale_end_1_px: tuple[float, float] | None = None,
        scale_end_2_px: tuple[float, float] | None = None,
        known_length: float | None = None,
        unit: str = "m",
        name: str | None = None,
        origin_px: tuple[float, float] | None = None,
        rotation_deg: float = 0.0,
        notes: str | None = None,
        set_active: bool = True,
    ) -> Calibration:
        """为已验证视频添加标定；创建 Calibration 对象并更新聚合快照。"""

        if isinstance(video_id, Calibration):
            cal = video_id
            vid = cal.video_id
        else:
            vid = video_id
            if vid not in self._verified_videos:
                raise ProjectSessionError("video timing is not verified CFR; calibration disabled")
            if scale_end_1_px is None or scale_end_2_px is None or known_length is None:
                raise ProjectSessionError(
                    "scale_end_1_px, scale_end_2_px, and known_length are required"
                )
            final_name = name.strip() if name and name.strip() else self._next_calibration_name()
            try:
                cal = Calibration(
                    calibration_id=uuid4(),
                    video_id=vid,
                    name=final_name,
                    scale_end_1_px=scale_end_1_px,
                    scale_end_2_px=scale_end_2_px,
                    known_length=known_length,
                    unit=unit,
                    created_at=utc_now(),
                    origin_px=origin_px,
                    rotation_deg=rotation_deg,
                    notes=notes,
                )
            except ValueError as error:
                raise ProjectSessionError(str(error)) from error

        if vid not in self._verified_videos:
            raise ProjectSessionError("video timing is not verified CFR; calibration disabled")

        try:
            updated_project = add_domain_calibration(self._project, cal)
            if set_active:
                updated_project = set_domain_active_calibration(
                    updated_project, vid, cal.calibration_id
                )
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error

        self._commit_project(updated_project)
        logger.info(
            "calibration added: video=%s id=%s name=%s length=%s %s",
            vid,
            cal.calibration_id,
            cal.name,
            cal.known_length,
            cal.unit,
        )
        return cal

    def remove_calibration(self, calibration_id: UUID) -> None:
        """删除指定标定方案；若为 active 则级联失效。"""

        try:
            updated_project = delete_domain_calibration(self._project, calibration_id)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        self._commit_project(updated_project)

    delete_calibration = remove_calibration

    def set_active_calibration(self, video_id: UUID, calibration_id: UUID | None) -> None:
        """切换或清除视频的 active 标定方案。"""

        try:
            updated_project = set_domain_active_calibration(
                self._project, video_id, calibration_id
            )
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        self._commit_project(updated_project)

    def update_calibration(self, calibration: Calibration) -> None:
        """替换已有标定的参数（如修改原点或旋转角）。"""

        try:
            updated_project = replace_domain_calibration(self._project, calibration)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        self._commit_project(updated_project)

    replace_calibration = update_calibration

    def compute_kinematics(
        self,
        track_id: UUID,
        *,
        window_length: int = 7,
        polyorder: int = 2,
    ) -> tuple[DerivedData, ...]:
        """对指定 Track 执行运动学计算管线（坐标变换、SG 平滑与一/二阶微分）。

        重算触发方式为应用层暴露 `recompute_kinematics`/`compute_kinematics` 接口，
        由上层 GUI 层按需调用。

        Args:
            track_id: 目标 Track 的 UUID。
            window_length: Savitzky-Golay 滤波窗口长度（必须为正奇数，默认 7）。
            polyorder: Savitzky-Golay 多项式拟合阶数（默认 2）。

        Returns:
            生成的 (world_position, smoothed_position, velocity, acceleration)
            四条 DerivedData 元组。
        """
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        timeline = next(
            (item for item in self._project.timelines if item.video_id == track.video_id),
            None,
        )
        if timeline is None:
            raise ProjectSessionError(f"no timeline registered for video of track {track.name}")

        video = next(
            (item for item in self._project.videos if item.video_id == track.video_id),
            None,
        )
        if video is None:
            raise ProjectSessionError(f"no video registered for track {track.name}")

        delta = 1.0 / timeline.fps_nominal
        points = self.effective_points(track_id)

        try:
            frames, px_x, px_y = expand_to_dense_grid(
                points, frame_range=timeline.working_zone
            )

            active_cal = self.active_calibration(track.video_id)
            if active_cal is not None:
                transform = CalibrationTransform(
                    calibration=active_cal, height_px=video.height_px
                )
                pos_x, pos_y = batch_pixel_to_world(px_x, px_y, transform)
                pos_unit = active_cal.unit
                cal_ref = active_cal.calibration_id
                cal_step = [
                    {
                        "step": "calibration_transform",
                        "params": {"calibration_id": str(active_cal.calibration_id)},
                    }
                ]
            else:
                pos_x, pos_y = px_x.copy(), px_y.copy()
                pos_unit = "px"
                cal_ref = None
                cal_step = []

            smooth_x = smooth_savgol(
                pos_x, window_length=window_length, polyorder=polyorder
            )
            smooth_y = smooth_savgol(
                pos_y, window_length=window_length, polyorder=polyorder
            )
            vx = differentiate_savgol(
                pos_x,
                window_length=window_length,
                polyorder=polyorder,
                deriv=1,
                delta=delta,
            )
            vy = differentiate_savgol(
                pos_y,
                window_length=window_length,
                polyorder=polyorder,
                deriv=1,
                delta=delta,
            )
            ax = differentiate_savgol(
                pos_x,
                window_length=window_length,
                polyorder=polyorder,
                deriv=2,
                delta=delta,
            )
            ay = differentiate_savgol(
                pos_y,
                window_length=window_length,
                polyorder=polyorder,
                deriv=2,
                delta=delta,
            )
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error

        now = utc_now()
        derived_input = DerivedInput(
            track_id=track_id,
            source_filter=None,
            include_superseded=False,
            extra_fields={"observation_selection": "effective"},
        )
        produced_by = "ai_physics_tracker.kinematics.v1"

        pos_frames, pos_values = dense_to_sparse_records(frames, pos_x, pos_y)
        smooth_frames, smooth_values = dense_to_sparse_records(frames, smooth_x, smooth_y)
        vel_frames, vel_values = dense_to_sparse_records(frames, vx, vy)
        acc_frames, acc_values = dense_to_sparse_records(frames, ax, ay)

        d_pos = DerivedData(
            derived_id=uuid4(),
            track_id=track_id,
            kind="world_position",
            input=derived_input,
            pipeline=tuple(cal_step),
            frames=pos_frames,
            values=pos_values,
            payload_ref=None,
            unit=pos_unit,
            produced_by=produced_by,
            created_at=now,
            status="valid",
            calibration_ref=cal_ref,
        )

        d_smooth = DerivedData(
            derived_id=uuid4(),
            track_id=track_id,
            kind="smoothed_position",
            input=derived_input,
            pipeline=(
                *cal_step,
                {
                    "step": "savitzky_golay",
                    "params": {
                        "window_length": window_length,
                        "polyorder": polyorder,
                        "deriv": 0,
                        "mode": "interp",
                    },
                },
            ),
            frames=smooth_frames,
            values=smooth_values,
            payload_ref=None,
            unit=pos_unit,
            produced_by=produced_by,
            created_at=now,
            status="valid",
            calibration_ref=cal_ref,
        )

        d_vel = DerivedData(
            derived_id=uuid4(),
            track_id=track_id,
            kind="velocity",
            input=derived_input,
            pipeline=(
                *cal_step,
                {
                    "step": "savitzky_golay",
                    "params": {
                        "window_length": window_length,
                        "polyorder": polyorder,
                        "deriv": 1,
                        "delta": delta,
                        "mode": "interp",
                    },
                },
            ),
            frames=vel_frames,
            values=vel_values,
            payload_ref=None,
            unit=derive_unit(pos_unit, 1),
            produced_by=produced_by,
            created_at=now,
            status="valid",
            calibration_ref=cal_ref,
        )

        d_acc = DerivedData(
            derived_id=uuid4(),
            track_id=track_id,
            kind="acceleration",
            input=derived_input,
            pipeline=(
                *cal_step,
                {
                    "step": "savitzky_golay",
                    "params": {
                        "window_length": window_length,
                        "polyorder": polyorder,
                        "deriv": 2,
                        "delta": delta,
                        "mode": "interp",
                    },
                },
            ),
            frames=acc_frames,
            values=acc_values,
            payload_ref=None,
            unit=derive_unit(pos_unit, 2),
            produced_by=produced_by,
            created_at=now,
            status="valid",
            calibration_ref=cal_ref,
        )

        new_items = (d_pos, d_smooth, d_vel, d_acc)
        new_kinds = {item.kind for item in new_items}
        kept_derived = [
            d
            for d in self._project.derived
            if not (d.track_id == track_id and d.kind in new_kinds)
        ]
        updated_derived = tuple(kept_derived) + new_items

        self._commit_store(self._store, updated_derived)
        logger.info(
            "computed kinematics for track=%s (cal=%s, valid_points=%d)",
            track.name,
            cal_ref,
            len(pos_frames),
        )
        return new_items

    recompute_kinematics = compute_kinematics

    def clear_derived(self, track_id: UUID) -> None:
        """清除指定 Track 的全部 DerivedData。"""
        updated_derived = tuple(
            item for item in self._project.derived if item.track_id != track_id
        )
        self._commit_store(self._store, updated_derived)

    def derived_data(self, track_id: UUID, kind: str) -> DerivedData | None:
        """查询指定 Track 的指定类型派生数据。"""
        matches = [
            item
            for item in self._project.derived
            if item.track_id == track_id and item.kind == kind
        ]
        return matches[-1] if matches else None

    def can_measure(self, video_id: UUID) -> bool:
        """仅表示本次媒体会话的时序授权；不从持久化 vfr 标志猜测权限。"""

        return video_id in self._verified_videos

    def measurement_timing_detail(self, video_id: UUID) -> str | None:
        """近似授权的来源说明；None 表示当前没有近似授权说明。"""

        return self._approximate_timing.get(video_id)

    def apply_kinematics_result(self, result: "KinematicsResult") -> None:
        """主线程原子提交整个批次，共用现有 Undo/Redo 快照边界。"""

        from ai_physics_tracker.application.kinematics_job import validated_derived
        self._commit_store(self._store, validated_derived(self, result))

    @staticmethod
    def _with_import_summary(
        registered_run: TrackingRun,
        completed_run: TrackingRun,
        result: BatchWriteResult,
    ) -> TrackingRun:
        extras = deepcopy(registered_run.extra_fields)
        extras.update(deepcopy(completed_run.extra_fields))
        summary: JsonObject = {}
        for source in (registered_run.extra_fields, completed_run.extra_fields):
            existing = source.get("import_summary")
            if isinstance(existing, dict):
                summary.update(deepcopy(existing))
        summary["inserted"] = result.inserted
        summary["skipped"] = result.skipped
        extras["import_summary"] = summary
        return replace(completed_run, extra_fields=extras)

    def _next_calibration_name(self) -> str:
        index = len(self._project.calibrations) + 1
        existing = {cal.name for cal in self._project.calibrations}
        while f"Calibration {index}" in existing:
            index += 1
        return f"Calibration {index}"

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        """撤销最近一次写操作（含"替换后恢复旧点"与审核记录）；无可撤销时返回 False。"""

        if not self._undo_stack:
            return False
        snapshot = self._undo_stack.pop()
        tracks, observations, calibrations, active_calibration_by_video, derived, scoped_reviews = snapshot

        # 抓取当前受影响 run 的 review 状态作为 redo 恢复点
        current_scoped_reviews: dict[UUID, dict[str, Any] | None] | None = None
        if scoped_reviews is not None:
            current_scoped_reviews = {}
            for r_id in scoped_reviews:
                run = next((r for r in self._project.tracking_runs if r.run_id == r_id), None)
                if run is not None:
                    rev_dict = run.extra_fields.get(SUGGESTED_FRAME_REVIEW_KEY)
                    current_scoped_reviews[r_id] = (
                        deepcopy(rev_dict) if isinstance(rev_dict, dict) else None
                    )
                else:
                    current_scoped_reviews[r_id] = None

        self._redo_stack.append(self._current_data_snapshot(current_scoped_reviews))
        self._store = TrackStore(tracks, observations)

        updated_runs = self._project.tracking_runs
        if scoped_reviews is not None:
            runs_list: list[TrackingRun] = []
            for existing in updated_runs:
                if existing.run_id in scoped_reviews:
                    old_rev = scoped_reviews[existing.run_id]
                    extras = dict(existing.extra_fields)
                    if old_rev is None:
                        extras.pop(SUGGESTED_FRAME_REVIEW_KEY, None)
                    else:
                        extras[SUGGESTED_FRAME_REVIEW_KEY] = deepcopy(old_rev)
                    runs_list.append(replace(existing, extra_fields=extras))
                else:
                    runs_list.append(existing)
            updated_runs = tuple(runs_list)

        self._project = replace(
            self._project,
            tracks=tracks,
            observations=observations,
            calibrations=calibrations,
            active_calibration_by_video=active_calibration_by_video,
            derived=derived,
            tracking_runs=updated_runs,
        )
        return True

    def redo(self) -> bool:
        """重做被撤销的操作；无可重做时返回 False。"""

        if not self._redo_stack:
            return False
        snapshot = self._redo_stack.pop()
        tracks, observations, calibrations, active_calibration_by_video, derived, scoped_reviews = snapshot

        current_scoped_reviews: dict[UUID, dict[str, Any] | None] | None = None
        if scoped_reviews is not None:
            current_scoped_reviews = {}
            for r_id in scoped_reviews:
                run = next((r for r in self._project.tracking_runs if r.run_id == r_id), None)
                if run is not None:
                    rev_dict = run.extra_fields.get(SUGGESTED_FRAME_REVIEW_KEY)
                    current_scoped_reviews[r_id] = (
                        deepcopy(rev_dict) if isinstance(rev_dict, dict) else None
                    )
                else:
                    current_scoped_reviews[r_id] = None

        self._undo_stack.append(self._current_data_snapshot(current_scoped_reviews))
        self._store = TrackStore(tracks, observations)

        updated_runs = self._project.tracking_runs
        if scoped_reviews is not None:
            runs_list: list[TrackingRun] = []
            for existing in updated_runs:
                if existing.run_id in scoped_reviews:
                    target_rev = scoped_reviews[existing.run_id]
                    extras = dict(existing.extra_fields)
                    if target_rev is None:
                        extras.pop(SUGGESTED_FRAME_REVIEW_KEY, None)
                    else:
                        extras[SUGGESTED_FRAME_REVIEW_KEY] = deepcopy(target_rev)
                    runs_list.append(replace(existing, extra_fields=extras))
                else:
                    runs_list.append(existing)
            updated_runs = tuple(runs_list)

        self._project = replace(
            self._project,
            tracks=tracks,
            observations=observations,
            calibrations=calibrations,
            active_calibration_by_video=active_calibration_by_video,
            derived=derived,
            tracking_runs=updated_runs,
        )
        return True

    def _current_data_snapshot(
        self,
        scoped_reviews: dict[UUID, dict[str, Any] | None] | None = None,
    ) -> _SessionDataSnapshot:
        return (
            self._store.tracks,
            self._store.observations,
            self._project.calibrations,
            dict(self._project.active_calibration_by_video),
            self._project.derived,
            deepcopy(scoped_reviews) if scoped_reviews is not None else None,
        )

    def _push_undo_snapshot(
        self, scoped_reviews: dict[UUID, dict[str, Any] | None] | None = None
    ) -> None:
        self._undo_stack.append(self._current_data_snapshot(scoped_reviews))
        del self._undo_stack[:-UNDO_STACK_LIMIT]
        self._redo_stack.clear()

    def _next_track_name(self) -> str:
        index = len(self._store.tracks) + 1
        existing = {track.name for track in self._store.tracks}
        while f"Track {index}" in existing:
            index += 1
        return f"Track {index}"

    def _commit_project(
        self,
        project: Project,
        store: TrackStore | None = None,
        scoped_reviews: dict[UUID, dict[str, Any] | None] | None = None,
    ) -> None:
        self._push_undo_snapshot(scoped_reviews)
        if store is not None:
            self._store = store
        else:
            self._store = TrackStore(project.tracks, project.observations)
        self._project = project

    def _commit_store(
        self,
        store: TrackStore,
        derived: tuple[DerivedData, ...],
        scoped_reviews: dict[UUID, dict[str, Any] | None] | None = None,
    ) -> None:
        # 先完成跨对象校验；失败不能污染原 store 或提前清 redo。
        project = replace(
            self._project,
            tracks=store.tracks,
            observations=store.observations,
            derived=derived,
        )
        self._commit_project(project, store, scoped_reviews)

    # ------------------------------------------------------------------
    # Suggested Frame Review & Correction (Phase 5.3 ADR-0013)
    # ------------------------------------------------------------------

    def _validate_infer_run_for_review(self, run_id: UUID) -> TrackingRun:
        run = next((r for r in self._project.tracking_runs if r.run_id == run_id), None)
        if run is None:
            raise ProjectSessionError(f"unknown tracking run_id: {run_id}")
        if run.task_type != "infer" or run.status != "completed":
            raise ProjectSessionError("review requires a completed inference run")
        return run

    def _commit_review_transaction(
        self, run: TrackingRun, new_state: SuggestedFrameReviewState
    ) -> None:
        old_review_dict = run.extra_fields.get(SUGGESTED_FRAME_REVIEW_KEY)
        scoped_reviews = {
            run.run_id: deepcopy(old_review_dict) if isinstance(old_review_dict, dict) else None
        }
        updated_run = attach_review_state(run, new_state)
        runs = tuple(updated_run if r.run_id == run.run_id else r for r in self._project.tracking_runs)
        updated_project = replace(self._project, tracking_runs=runs)
        self._commit_project(updated_project, self._store, scoped_reviews)

    def get_suggested_frame_review(self, run_id: UUID) -> SuggestedFrameReviewState | None:
        """返回指定 infer run 的建议帧审核状态；未设置或损坏时返回 None。"""
        run = next((r for r in self._project.tracking_runs if r.run_id == run_id), None)
        if run is None:
            return None
        try:
            return extract_review_state(run)
        except ValueError:
            return None

    def get_review_summary(self, run_id: UUID) -> ReviewBatchSummary:
        """计算指定 infer run 当前批次的审核概要。"""
        state = self.get_suggested_frame_review(run_id)
        return compute_batch_summary(state)

    def set_active_review_batch(self, run_id: UUID, batch: ActiveReviewBatch) -> None:
        """设置当前活动的困难帧挖掘批次（保留该 run 既有的 reviewed_frames）。"""
        run = self._validate_infer_run_for_review(run_id)
        current_state = self.get_suggested_frame_review(run_id)
        kept_reviewed = current_state.reviewed_frames if current_state is not None else {}
        new_state = SuggestedFrameReviewState(active_batch=batch, reviewed_frames=kept_reviewed)
        updated_run = attach_review_state(run, new_state)
        self.update_tracking_run(updated_run)
        logger.info("set active review batch for run=%s candidates=%d", run_id, len(batch.candidates))

    def accept_suggested_frame(self, run_id: UUID, frame_index: int) -> None:
        """将候选帧标记为已接受（不创建 TrackPoint，AC-5）。"""
        run = self._validate_infer_run_for_review(run_id)
        state = self.get_suggested_frame_review(run_id)
        if state is None or state.active_batch is None:
            raise ProjectSessionError("no active review batch for this run")
        candidate = next((c for c in state.active_batch.candidates if c.frame_index == frame_index), None)
        if candidate is None:
            raise ProjectSessionError(f"frame {frame_index} is not in current active review batch")

        now_iso = utc_now().isoformat()
        record = ReviewRecord(
            disposition=DISPOSITION_ACCEPTED,
            reviewed_at=now_iso,
            request_id=state.active_batch.request_id,
            prediction=candidate.prediction,
            manual_point_id=None,
        )
        new_reviewed = dict(state.reviewed_frames)
        new_reviewed[frame_index] = record
        new_state = SuggestedFrameReviewState(
            active_batch=state.active_batch,
            reviewed_frames=new_reviewed,
        )
        self._commit_review_transaction(run, new_state)
        logger.info("accepted suggested frame run=%s frame=%d", run_id, frame_index)

    def skip_suggested_frame(self, run_id: UUID, frame_index: int) -> None:
        """将候选帧标记为跳过（不创建 TrackPoint，AC-5）。"""
        run = self._validate_infer_run_for_review(run_id)
        state = self.get_suggested_frame_review(run_id)
        if state is None or state.active_batch is None:
            raise ProjectSessionError("no active review batch for this run")
        candidate = next((c for c in state.active_batch.candidates if c.frame_index == frame_index), None)
        if candidate is None:
            raise ProjectSessionError(f"frame {frame_index} is not in current active review batch")

        now_iso = utc_now().isoformat()
        record = ReviewRecord(
            disposition=DISPOSITION_SKIPPED,
            reviewed_at=now_iso,
            request_id=state.active_batch.request_id,
            prediction=candidate.prediction,
            manual_point_id=None,
        )
        new_reviewed = dict(state.reviewed_frames)
        new_reviewed[frame_index] = record
        new_state = SuggestedFrameReviewState(
            active_batch=state.active_batch,
            reviewed_frames=new_reviewed,
        )
        self._commit_review_transaction(run, new_state)
        logger.info("skipped suggested frame run=%s frame=%d", run_id, frame_index)

    def correct_suggested_frame(
        self,
        run_id: UUID,
        frame_index: int,
        pixel_x: float,
        pixel_y: float,
    ) -> TrackPoint:
        """对候选帧执行人工修正，原子提交 manual point 与 corrected disposition。

        原 AI 观测按 manual last-wins 保留并标记为 superseded；
        原 prediction 快照（无论是否低于导入阈值或缺测）随审核记录持久化。
        """
        run = self._validate_infer_run_for_review(run_id)
        track = next((t for t in self._store.tracks if t.track_id == run.track_id), None)
        if track is None:
            raise ProjectSessionError(f"track {run.track_id} not found")
        if track.video_id not in self._verified_videos:
            raise ProjectSessionError("video timing is not verified CFR; new measurements disabled")
        timeline = next((t for t in self._project.timelines if t.video_id == track.video_id), None)
        if timeline is None:
            raise ProjectSessionError(f"no timeline registered for video of track {track.name}")
        if not (timeline.working_zone[0] <= frame_index <= timeline.working_zone[1]):
            raise ProjectSessionError(f"frame {frame_index} outside working zone")

        state = self.get_suggested_frame_review(run_id)
        if state is None or state.active_batch is None:
            raise ProjectSessionError("no active review batch for this run")
        candidate = next((c for c in state.active_batch.candidates if c.frame_index == frame_index), None)
        if candidate is None:
            raise ProjectSessionError(f"frame {frame_index} is not in current active review batch")

        if (
            isinstance(pixel_x, bool)
            or not isinstance(pixel_x, (int, float))
            or not isfinite(float(pixel_x))
            or isinstance(pixel_y, bool)
            or not isinstance(pixel_y, (int, float))
            or not isfinite(float(pixel_y))
        ):
            raise ProjectSessionError("pixel coordinates must be finite floats")

        now = utc_now()
        point = TrackPoint(
            point_id=uuid4(),
            track_id=track.track_id,
            frame_index=frame_index,
            time_s=frame_to_time(frame_index, timeline),
            pixel_x=float(pixel_x),
            pixel_y=float(pixel_y),
            source="manual",
            source_detail=self._approximate_timing.get(track.video_id),
            visibility="visible",
            status="active",
            created_at=now,
            modified_at=now,
        )

        candidate_store = TrackStore(self._store.tracks, self._store.observations)
        candidate_store.add_manual_point(point)

        record = ReviewRecord(
            disposition=DISPOSITION_CORRECTED,
            reviewed_at=now.isoformat(),
            request_id=state.active_batch.request_id,
            prediction=candidate.prediction,
            manual_point_id=point.point_id,
        )
        new_reviewed = dict(state.reviewed_frames)
        new_reviewed[frame_index] = record
        new_state = SuggestedFrameReviewState(
            active_batch=state.active_batch,
            reviewed_frames=new_reviewed,
        )

        old_review_dict = run.extra_fields.get(SUGGESTED_FRAME_REVIEW_KEY)
        scoped_reviews = {
            run.run_id: deepcopy(old_review_dict) if isinstance(old_review_dict, dict) else None
        }

        updated_run = attach_review_state(run, new_state)
        runs = tuple(updated_run if r.run_id == run.run_id else r for r in self._project.tracking_runs)

        updated_project = replace(
            self._project,
            tracks=candidate_store.tracks,
            observations=candidate_store.observations,
            derived=mark_tracks_stale(self._project.derived, {track.track_id}),
            tracking_runs=runs,
        )
        self._commit_project(updated_project, candidate_store, scoped_reviews)
        logger.info(
            "corrected suggested frame run=%s track=%s frame=%d point_id=%s pixel=(%.1f, %.1f)",
            run_id,
            track.name,
            frame_index,
            point.point_id,
            pixel_x,
            pixel_y,
        )
        return point

    def delete_active_manual_point(self, track_id: UUID, frame_index: int) -> TrackPoint:
        """删除当前 Track 在当前帧的 active manual 点，恢复被它遮蔽的 AI 点。

        若该点由某 infer run 的 Correct 创建，同时把对应候选恢复为 pending。
        可在下一次保存前 Undo；保存后不可通过应用内 Undo 恢复（ADR-0013）。
        """
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        target = next(
            (
                p
                for p in self._store.observations
                if p.track_id == track_id
                and p.frame_index == frame_index
                and p.source == "manual"
                and p.status == "active"
            ),
            None,
        )
        if target is None:
            raise ProjectSessionError(
                f"No active manual point on track {track.name} at frame {frame_index}"
            )

        candidate_store = TrackStore(self._store.tracks, self._store.observations)
        candidate_store.delete_manual_point(target.point_id)

        # 检查是否有 completed infer run 包含由该 manual_point_id 关联的 Correct 记录
        scoped_reviews: dict[UUID, dict[str, Any] | None] = {}
        updated_runs_list: list[TrackingRun] = []
        for r in self._project.tracking_runs:
            rev_state = extract_review_state(r)
            if rev_state is not None and frame_index in rev_state.reviewed_frames:
                rec = rev_state.reviewed_frames[frame_index]
                if rec.manual_point_id == target.point_id:
                    old_dict = r.extra_fields.get(SUGGESTED_FRAME_REVIEW_KEY)
                    scoped_reviews[r.run_id] = deepcopy(old_dict) if isinstance(old_dict, dict) else None

                    new_reviewed = dict(rev_state.reviewed_frames)
                    del new_reviewed[frame_index]
                    new_state = SuggestedFrameReviewState(
                        active_batch=rev_state.active_batch,
                        reviewed_frames=new_reviewed,
                    )
                    updated_runs_list.append(attach_review_state(r, new_state))
                    continue
            updated_runs_list.append(r)

        updated_project = replace(
            self._project,
            tracks=candidate_store.tracks,
            observations=candidate_store.observations,
            derived=mark_tracks_stale(self._project.derived, {track_id}),
            tracking_runs=tuple(updated_runs_list),
        )
        self._commit_project(
            updated_project,
            candidate_store,
            scoped_reviews if scoped_reviews else None,
        )
        logger.info(
            "deleted active manual point track=%s frame=%d point_id=%s (restored superseded observations)",
            track.name,
            frame_index,
            target.point_id,
        )
        return target
