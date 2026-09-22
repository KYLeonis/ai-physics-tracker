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
from typing import Any, Iterable, Protocol, TYPE_CHECKING, runtime_checkable
from uuid import UUID, uuid4

from ai_physics_tracker.application.refinement_history import (
    ActivationRecord,
    REFINEMENT_STATE_KEY,
    RefinementState,
    ValidationLabelSnapshot,
    ValidationSeries,
    _now_iso_utc,
    attach_refinement_state,
    check_validation_series_consistency,
    extract_refinement_iteration,
    extract_refinement_state,
)
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
from ai_physics_tracker.domain.pendulum import (
    PendulumExperiment,
    PendulumRoles,
    PhysicalParameters,
    RoleBindingEditRecord,
    TrueVertical,
    create_pendulum_experiment,
)
from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
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
from ai_physics_tracker.domain.scientific_result import ScientificResult
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


@runtime_checkable
class PublicationRepositoryPort(Protocol):
    """v1→v2 Save As 迁移端口（ADR-0017）；由 infrastructure.ProjectRepository 实现。"""

    def save_as_publication(
        self, source_root: Path, destination_root: Path, project: Project
    ) -> Project: ...

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


# 会话历史快照（含 TrackStore 数据、标定、派生数据、publication 集合、
# TrackingRun 注册表与可选的审核事务作用域快照）。registry 参与快照使
# Undo/Redo 能感知 Track↔run 结构依赖（P6R-01）；合并规则见
# ProjectSession._history_transition。前 _SNAPSHOT_DATA_FIELDS 个元素是
# "用户数据"；末位的 registry 仅用于历史转换，不参与
# accept_saved_snapshot 的"保存期间产生新数据"判定（stabilization R1 F2）。
_SessionDataSnapshot = tuple[
    tuple[Track, ...],
    tuple[TrackPoint, ...],
    tuple[Calibration, ...],
    dict[UUID, UUID],
    tuple[DerivedData, ...],
    dict[UUID, dict[str, Any] | None] | None,
    tuple[PendulumExperiment, ...],
    tuple[ScientificResult, ...],
    tuple[TrackingRun, ...],
]
_SNAPSHOT_DATA_FIELDS = 8


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

        try:
            candidate = delete_track(self._project, track_id)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
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
        project = replace(
            self._project,
            tracks=candidate.tracks,
            observations=candidate.observations,
            derived=mark_tracks_stale(self._project.derived, {track_id}),
        )
        project = self._with_manual_edit_experiment_state(project, track_id)
        self._commit_project(project, candidate)
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

        for member in completed_run.member_track_ids:
            self._require_unbound_track(member, "engine point import")
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
        # registry 不参与"保存期间产生了新数据"判定：run 状态演进（如
        # pending→running）不是需要保留撤销步的用户数据变化（stabilization R1 F2）。
        current = self._current_data_snapshot()
        changed = current[:_SNAPSHOT_DATA_FIELDS] != (
            saved._current_data_snapshot()[:_SNAPSHOT_DATA_FIELDS])
        self._project_root = saved.project_root
        self._saved_project = saved._saved_project
        self._project = replace(self._project, modified_at=saved.project.modified_at,
                                ui_state=saved.project.ui_state)
        # 保存模态窗口期间若后台产生了新数据，保留一次回到该保存点的撤销。
        self._undo_stack = [saved._current_data_snapshot()] if changed else []
        self._redo_stack.clear()

    def accept_autosaved_snapshot(self, saved: "ProjectSession") -> None:
        """更新自动保存基线，同时保留当前会话的 undo/redo 历史。"""
        if saved.project.project_id != self.project.project_id:
            raise ProjectSessionError("Saved snapshot belongs to another project")
        self._project_root = saved.project_root
        self._saved_project = saved._saved_project
        self._project = replace(
            self._project,
            modified_at=saved.project.modified_at,
            ui_state=saved.project.ui_state,
        )

    def accept_migrated_snapshot(self, saved: "ProjectSession") -> None:
        """整会话采纳迁移结果：迁移会改写 tracks（清 legacy 指针），因此
        不走 accept_saved_snapshot 的"保留 live 数据"语义。

        时序验证状态（_verified_videos）保留：迁移不改 video 身份，
        重验只会浪费用户时间。undo/redo 清空（保存边界语义）。
        """

        if saved.project.project_id != self.project.project_id:
            raise ProjectSessionError("Saved snapshot belongs to another project")
        self._project = saved.project
        self._saved_project = saved._saved_project
        self._project_root = saved._project_root
        self._store = TrackStore(saved.project.tracks, saved.project.observations)
        self._undo_stack.clear()
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
        """登记一个新的 TrackingRun。

        新 run 登记是一次前向写入：清空 redo 栈，防止 redo 越过它恢复到
        "该 run 所依赖的 Track 尚不存在/已被删除"的历史状态（P6R-01）。
        """
        if any(r.run_id == run.run_id for r in self._project.tracking_runs):
            raise ProjectSessionError(f"tracking run_id already exists: {run.run_id}")
        if run.experiment_id is None:
            for member in run.member_track_ids:
                self._require_unbound_track(member, "single-track run registration")
        self._project = replace(
            self._project,
            tracking_runs=(*self._project.tracking_runs, run),
        )
        self._redo_stack.clear()

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
        if run.experiment_id is None:
            for member in run.member_track_ids:
                self._require_unbound_track(member, "single-track run updates")
        self._project = replace(self._project, tracking_runs=tuple(runs))

    def tracking_runs(self, track_id: UUID | None = None) -> tuple[TrackingRun, ...]:
        """返回项目中的 TrackingRun，可选按 track_id 过滤。"""
        if track_id is None:
            return self._project.tracking_runs
        return tuple(r for r in self._project.tracking_runs if track_id in r.member_track_ids)

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
                # active 解释基准变化使该 video experiment 的科学结果失效（契约 §6）
                updated_project = self._with_stale_results_for_video(updated_project, vid)
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

        removed = next(
            (c for c in self._project.calibrations if c.calibration_id == calibration_id),
            None,
        )
        try:
            updated_project = delete_domain_calibration(self._project, calibration_id)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        if removed is not None:
            updated_project = self._with_stale_results_for_video(
                updated_project, removed.video_id
            )
        self._commit_project(updated_project)

    delete_calibration = remove_calibration

    def set_active_calibration(self, video_id: UUID, calibration_id: UUID | None) -> None:
        """切换或清除视频的 active 标定方案。"""

        previous = self._project.active_calibration_by_video.get(video_id)
        try:
            updated_project = set_domain_active_calibration(
                self._project, video_id, calibration_id
            )
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        if previous != calibration_id:
            updated_project = self._with_stale_results_for_video(updated_project, video_id)
        self._commit_project(updated_project)

    def update_calibration(self, calibration: Calibration) -> None:
        """替换已有标定的参数（如修改原点或旋转角）。"""

        try:
            updated_project = replace_domain_calibration(self._project, calibration)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        updated_project = self._with_stale_results_for_video(
            updated_project, calibration.video_id
        )
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
        """撤销最近一次写操作；无可撤销时返回 False。

        越过"快照之外登记的 run 依赖"的结构性撤销（如新建 Track 后又登记了
        训练任务再撤销建 Track）抛出 ProjectSessionError 且五个状态——Project、
        TrackStore、Undo 栈、Redo 栈、run registry——完全不变（P6R-01）。
        """

        if not self._undo_stack:
            return False
        snapshot = self._undo_stack[-1]  # 先 peek：校验失败不动任何栈
        current_scoped = self._capture_current_scoped_reviews(snapshot[5])
        candidate_project, candidate_store = self._history_transition(snapshot, is_undo=True)
        self._undo_stack.pop()
        self._redo_stack.append(self._current_data_snapshot(current_scoped))
        self._store = candidate_store
        self._project = candidate_project
        return True

    def redo(self) -> bool:
        """重做被撤销的操作；无可重做时返回 False。事务边界与 undo 对称。"""

        if not self._redo_stack:
            return False
        snapshot = self._redo_stack[-1]
        current_scoped = self._capture_current_scoped_reviews(snapshot[5])
        candidate_project, candidate_store = self._history_transition(snapshot, is_undo=False)
        self._redo_stack.pop()
        self._undo_stack.append(self._current_data_snapshot(current_scoped))
        self._store = candidate_store
        self._project = candidate_project
        return True

    def _capture_current_scoped_reviews(
        self, scoped_reviews: dict[UUID, dict[str, Any] | None] | None
    ) -> dict[UUID, dict[str, Any] | None] | None:
        """抓取当前受影响 run 的 review 状态，作为反向步骤的恢复点。"""

        if scoped_reviews is None:
            return None
        current_scoped: dict[UUID, dict[str, Any] | None] = {}
        for run_id in scoped_reviews:
            run = next((r for r in self._project.tracking_runs if r.run_id == run_id), None)
            if run is not None:
                rev_dict = run.extra_fields.get(SUGGESTED_FRAME_REVIEW_KEY)
                current_scoped[run_id] = deepcopy(rev_dict) if isinstance(rev_dict, dict) else None
            else:
                current_scoped[run_id] = None
        return current_scoped

    def _history_transition(
        self, snapshot: _SessionDataSnapshot, *, is_undo: bool
    ) -> tuple[Project, TrackStore]:
        """构造历史切换的目标状态；任何校验失败都不触碰当前会话（P6R-01）。

        run registry 合并规则：
        - 存续 Track 的 run 保持当前状态——pending/running/completed 的生命周期
          演进（后台事实）不被 Undo/Redo 回滚；
        - 被恢复 Track（当前不存在、快照存在）的 run 随快照恢复，保证 active
          pointer / observations / refinement state 引用可解析；
        - 被移除 Track 的当前 run 随之移除；undo 方向上若存在快照之外登记的
          run（record_tracking_run 不产生快照），说明该 run 依赖未被任何历史
          步骤覆盖，原子拒绝。
        """

        tracks, observations, calibrations, active_map, derived, scoped_reviews, experiments, results, snapshot_runs = snapshot
        target_ids = {t.track_id for t in tracks}
        current_ids = {t.track_id for t in self._store.tracks}
        restored_ids = target_ids - current_ids
        removed_ids = current_ids - target_ids

        merged_runs: list[TrackingRun]
        if restored_ids or removed_ids:
            snapshot_run_ids = {r.run_id for r in snapshot_runs}
            # 多成员 run（experiment joint run）按每个成员登记；恢复时按
            # run_id 去重，避免一个 run 被多个成员重复追加。
            snapshot_runs_by_track: dict[UUID, list[TrackingRun]] = {}
            for run in snapshot_runs:
                for member in run.member_track_ids:
                    snapshot_runs_by_track.setdefault(member, []).append(run)
            merged_runs = []
            for run in self._project.tracking_runs:
                if any(member in restored_ids for member in run.member_track_ids):
                    continue  # 恢复 Track 的 run 一律以快照为准
                if any(member in removed_ids for member in run.member_track_ids):
                    if is_undo and run.run_id not in snapshot_run_ids:
                        # 该拒绝仅在 undo 方向可达：redo 的栈在每次前向写入
                        # （含 record_tracking_run）时已清空，被移除 track 的 run
                        # 只可能来自配对快照的恢复。
                        raise ProjectSessionError(
                            f"cannot undo: tracking run {run.run_id} references a "
                            "track created after this history point; undo across a "
                            "registered AI task is not supported"
                        )
                    continue
                merged_runs.append(run)
            restored_run_ids: set[UUID] = set()
            for track_id in restored_ids:
                for run in snapshot_runs_by_track.get(track_id, ()):
                    if run.run_id not in restored_run_ids:
                        restored_run_ids.add(run.run_id)
                        merged_runs.append(run)
        else:
            merged_runs = list(self._project.tracking_runs)

        updated_runs = tuple(merged_runs)
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

        # replace() 触发 validate_project：聚合级引用完整性先于任何赋值
        candidate_project = replace(
            self._project,
            tracks=tracks,
            observations=observations,
            calibrations=calibrations,
            active_calibration_by_video=active_map,
            derived=derived,
            experiments=experiments,
            scientific_results=results,
            tracking_runs=updated_runs,
        )
        self._check_validation_series_removal(candidate_project)
        return candidate_project, TrackStore(tracks, observations)

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
            self._project.experiments,
            self._project.scientific_results,
            self._project.tracking_runs,
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

    def _check_validation_series_removal(self, candidate: Project) -> None:
        """所有用户事务共同保护历史标签；在途 train 尚未回传 iteration 时保守保留。"""
        current_tracks = {track.track_id: track for track in self._project.tracks}
        for track in candidate.tracks:
            previous = current_tracks.get(track.track_id)
            if previous is None:
                continue
            retained = {s.series_id for s in extract_refinement_state(track).validation_series}
            removed = {s.series_id for s in extract_refinement_state(previous).validation_series} - retained
            if not removed:
                continue
            for run in candidate.tracking_runs:
                if track.track_id not in run.member_track_ids or run.task_type != "train":
                    continue
                iteration = extract_refinement_iteration(run)
                if (run.status in {"pending", "running"}
                        or (iteration is not None and iteration.validation_series_id in removed)):
                    raise ProjectSessionError(
                        "Cannot remove validation series used by training history or an "
                        "active training task; deactivate it instead so labels stay traceable"
                    )

    def _commit_project(
        self,
        project: Project,
        store: TrackStore | None = None,
        scoped_reviews: dict[UUID, dict[str, Any] | None] | None = None,
    ) -> None:
        self._check_validation_series_removal(project)
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

    def accept_suggested_frame(self, run_id: UUID, frame_index: int) -> ReviewRecord:
        """将候选帧标记为已接受（不创建 TrackPoint，AC-5）。"""
        run = self._validate_infer_run_for_review(run_id)
        state = self.get_suggested_frame_review(run_id)
        if state is None or state.active_batch is None:
            raise ProjectSessionError("no active review batch for this run")
        candidate = next((c for c in state.active_batch.candidates if c.frame_index == frame_index), None)
        if candidate is None:
            raise ProjectSessionError(f"frame {frame_index} is not in current active review batch")

        curr_rec = state.reviewed_frames.get(frame_index)
        if curr_rec is not None and curr_rec.disposition == DISPOSITION_CORRECTED:
            raise ProjectSessionError(
                f"frame {frame_index} has already been corrected; delete the manual point first to change disposition"
            )

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
        return record

    def skip_suggested_frame(self, run_id: UUID, frame_index: int) -> ReviewRecord:
        """将候选帧标记为跳过（不创建 TrackPoint，AC-5）。"""
        run = self._validate_infer_run_for_review(run_id)
        state = self.get_suggested_frame_review(run_id)
        if state is None or state.active_batch is None:
            raise ProjectSessionError("no active review batch for this run")
        candidate = next((c for c in state.active_batch.candidates if c.frame_index == frame_index), None)
        if candidate is None:
            raise ProjectSessionError(f"frame {frame_index} is not in current active review batch")

        curr_rec = state.reviewed_frames.get(frame_index)
        if curr_rec is not None and curr_rec.disposition == DISPOSITION_CORRECTED:
            raise ProjectSessionError(
                f"frame {frame_index} has already been corrected; delete the manual point first to change disposition"
            )

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
        return record

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
        if len(run.member_track_ids) != 1:
            raise ProjectSessionError(
                "frame review is a single-track workflow; joint runs are not reviewable here"
            )
        track = next(
            (t for t in self._store.tracks if t.track_id == run.member_track_ids[0]),
            None,
        )
        if track is None:
            raise ProjectSessionError(f"track {run.member_track_ids[0]} not found")
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
        updated_project = self._with_manual_edit_experiment_state(
            updated_project, track.track_id
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
            rev_state = self.get_suggested_frame_review(r.run_id)
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
        updated_project = self._with_manual_edit_experiment_state(
            updated_project, track_id
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

    # --- Phase 5.4: Refinement State & Fixed Validation Series ---

    def get_refinement_state(self, track_id: UUID) -> RefinementState:
        """获取指定 Track 的迭代与结果激活状态。"""
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")
        return extract_refinement_state(track)

    def create_validation_series(
        self,
        track_id: UUID,
        name: str,
        frame_indices: Iterable[int],
    ) -> ValidationSeries:
        """从当前 active manual points 创建不可变的固定验证集，并将其设为活动验证集。"""
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        clean_name = name.strip()
        if not clean_name:
            raise ProjectSessionError("Validation series name must not be empty")

        frames_set = sorted(set(frame_indices))
        if not frames_set:
            raise ProjectSessionError("Validation series must contain at least one frame")

        snapshots: list[ValidationLabelSnapshot] = []
        for f_idx in frames_set:
            manual_pt = next(
                (
                    p
                    for p in self._store.observations
                    if p.track_id == track_id
                    and p.frame_index == f_idx
                    and p.source == "manual"
                    and p.status == "active"
                ),
                None,
            )
            if manual_pt is None:
                raise ProjectSessionError(
                    f"No active manual point found on track '{track.name}' at frame {f_idx}"
                )
            snapshots.append(
                ValidationLabelSnapshot(
                    point_id=manual_pt.point_id,
                    frame_index=f_idx,
                    pixel_x=manual_pt.pixel_x,
                    pixel_y=manual_pt.pixel_y,
                    modified_at=manual_pt.modified_at.isoformat(),
                )
            )

        new_series = ValidationSeries(
            series_id=uuid4(),
            name=clean_name,
            created_at=_now_iso_utc(),
            label_snapshots=tuple(snapshots),
        )

        current_state = extract_refinement_state(track)
        updated_state = RefinementState(
            active_infer_run_id=current_state.active_infer_run_id,
            activation_history=current_state.activation_history,
            active_validation_series_id=new_series.series_id,
            validation_series=(*current_state.validation_series, new_series),
        )
        updated_track = attach_refinement_state(track, updated_state)

        candidate_store = TrackStore(
            tuple(updated_track if t.track_id == track_id else t for t in self._store.tracks),
            self._store.observations,
        )
        updated_project = replace(
            self._project,
            tracks=candidate_store.tracks,
        )
        self._commit_project(updated_project, candidate_store)
        logger.info(
            "created validation series track=%s series_id=%s name=%s labels=%d",
            track.name,
            new_series.series_id,
            new_series.name,
            len(new_series.label_snapshots),
        )
        return new_series

    def set_active_validation_series(
        self,
        track_id: UUID,
        series_id: UUID | None,
    ) -> None:
        """设置或清空当前 Track 的活动固定验证集。"""
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        current_state = extract_refinement_state(track)
        if series_id is not None and current_state.get_series(series_id) is None:
            raise ProjectSessionError(
                f"Validation series '{series_id}' does not exist on track '{track.name}'"
            )

        updated_state = RefinementState(
            active_infer_run_id=current_state.active_infer_run_id,
            activation_history=current_state.activation_history,
            active_validation_series_id=series_id,
            validation_series=current_state.validation_series,
        )
        updated_track = attach_refinement_state(track, updated_state)

        candidate_store = TrackStore(
            tuple(updated_track if t.track_id == track_id else t for t in self._store.tracks),
            self._store.observations,
        )
        updated_project = replace(
            self._project,
            tracks=candidate_store.tracks,
        )
        self._commit_project(updated_project, candidate_store)

    def delete_validation_series(
        self,
        track_id: UUID,
        series_id: UUID,
    ) -> None:
        """删除指定 Track 的固定验证集。若为活动验证集则自动清空活动指针。

        P6R-03：series 是历史 validation labels 的第一方快照；被本 Track 任一
        train run 的迭代记录引用时拒绝物理删除（改用停用保留溯源），未被引用
        的 series 删除行为不变。
        """
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        current_state = extract_refinement_state(track)
        target = current_state.get_series(series_id)
        if target is None:
            raise ProjectSessionError(
                f"Validation series '{series_id}' does not exist on track '{track.name}'"
            )

        new_series_list = tuple(s for s in current_state.validation_series if s.series_id != series_id)
        new_active_id = (
            None
            if current_state.active_validation_series_id == series_id
            else current_state.active_validation_series_id
        )

        updated_state = RefinementState(
            active_infer_run_id=current_state.active_infer_run_id,
            activation_history=current_state.activation_history,
            active_validation_series_id=new_active_id,
            validation_series=new_series_list,
        )
        updated_track = attach_refinement_state(track, updated_state)

        candidate_store = TrackStore(
            tuple(updated_track if t.track_id == track_id else t for t in self._store.tracks),
            self._store.observations,
        )
        updated_project = replace(
            self._project,
            tracks=candidate_store.tracks,
        )
        self._commit_project(updated_project, candidate_store)

    def validate_active_validation_series(
        self,
        track_id: UUID,
    ) -> tuple[bool, str | None]:
        """校验当前 Track 活动验证集与当前 manual points 是否一致。"""
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        state = extract_refinement_state(track)
        active_series = state.active_series
        if active_series is None:
            return False, "No active validation series"

        manual_points = [
            p
            for p in self._store.observations
            if p.track_id == track_id and p.source == "manual" and p.status == "active"
        ]
        return check_validation_series_consistency(active_series, manual_points)

    # ------------------------------------------------------------------
    # Pendulum experiment setup (P1.1, contract §1–§2)
    # ------------------------------------------------------------------

    def pendulum_experiments(self) -> tuple[PendulumExperiment, ...]:
        """项目中的全部 Pendulum experiment（publication 项目；v1 为空）。"""

        return self._project.experiments

    def pendulum_experiment(self, experiment_id: UUID) -> PendulumExperiment:
        experiment = next(
            (
                item
                for item in self._project.experiments
                if item.experiment_id == experiment_id
            ),
            None,
        )
        if experiment is None:
            raise ProjectSessionError(f"unknown experiment_id: {experiment_id}")
        return experiment

    def experiment_for_track(self, track_id: UUID) -> PendulumExperiment | None:
        """返回绑定了该 Track 的 experiment；未绑定时 None（guard 查询）。"""

        for experiment in self._project.experiments:
            if track_id in experiment.roles.track_ids():
                return experiment
        return None

    def _require_unbound_track(self, track_id: UUID, action: str) -> None:
        """experiment-bound Track 拒绝旧单轨 AI 写入（契约 §2，fail closed）。"""

        experiment = self.experiment_for_track(track_id)
        if experiment is not None:
            role = next(
                role
                for role, member in experiment.roles.by_role().items()
                if member == track_id
            )
            raise ProjectSessionError(
                f"Track is bound to pendulum experiment role '{role}'; "
                f"use the pendulum workflow instead of {action}"
            )

    def _with_stale_results_for_experiment(
        self, project: Project, experiment_id: UUID
    ) -> Project:
        """保守失效：experiment 事实变化置其全部科学结果 stale（契约 §6）。"""

        results = tuple(
            replace(result, freshness="stale")
            if result.experiment_id == experiment_id and result.freshness == "valid"
            else result
            for result in project.scientific_results
        )
        if results == project.scientific_results:
            return project
        return replace(project, scientific_results=results)

    def _with_manual_edit_experiment_state(
        self, project: Project, track_id: UUID
    ) -> Project:
        """契约 §2：bound Track 的人工单点修正递增 measurement_revision
        并置结果 stale，不改变 active run 身份。"""

        experiment = self.experiment_for_track(track_id)
        if experiment is None:
            return project
        updated = replace(
            experiment, measurement_revision=experiment.measurement_revision + 1
        )
        project = replace(
            project,
            experiments=tuple(
                updated
                if item.experiment_id == experiment.experiment_id
                else item
                for item in project.experiments
            ),
        )
        return self._with_stale_results_for_experiment(
            project, experiment.experiment_id
        )

    def _with_stale_results_for_video(self, project: Project, video_id: UUID) -> Project:
        results = tuple(
            replace(result, freshness="stale")
            if any(
                experiment.video_id == video_id
                and experiment.experiment_id == result.experiment_id
                for experiment in project.experiments
            )
            and result.freshness == "valid"
            else result
            for result in project.scientific_results
        )
        if results == project.scientific_results:
            return project
        return replace(project, scientific_results=results)

    def create_pendulum_experiment(
        self, video_id: UUID, roles: PendulumRoles
    ) -> PendulumExperiment:
        """在 publication 项目上创建 experiment：四 role 一次提交，revision 1。

        v1 generic 项目不承载 experiment：先经 save_as_publication 迁移，
        或对新项目以 v2 首存（设计决策 1/2）。
        """

        if not self._project.required_capabilities:
            raise ProjectSessionError(
                "creating a pendulum experiment requires a publication project; "
                "use Save As publication first"
            )
        if any(item.video_id == video_id for item in self._project.experiments):
            raise ProjectSessionError(
                "this video already has a pendulum experiment"
            )
        experiment = create_pendulum_experiment(uuid4(), video_id, roles)
        # 契约 §2：绑定即清除/归档旧单轨 active 指针（与迁移路径同语义），
        # 避免 guard 封死后留下不可清理的双真值状态。
        stripped_tracks = tuple(
            self._strip_legacy_active_pointer(track)
            if track.track_id in roles.track_ids()
            else track
            for track in self._store.tracks
        )
        try:
            candidate = replace(
                self._project,
                tracks=stripped_tracks,
                experiments=(*self._project.experiments, experiment),
            )
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        self._commit_project(
            candidate, TrackStore(candidate.tracks, candidate.observations)
        )
        logger.info(
            "pendulum experiment created: experiment=%s video=%s",
            experiment.experiment_id,
            video_id,
        )
        return experiment

    def rebind_pendulum_roles(
        self, experiment_id: UUID, new_roles: PendulumRoles
    ) -> PendulumExperiment:
        """整体替换四 role 绑定：一次事务清除旧成员 AI 投影并记录历史。

        旧 active run 不得重新解释为新 role：rebind 在同一事务内清除旧四成员
        的引擎观测（manual 保留）、active 指针置空、追加绑定历史并使科学
        结果 stale（契约 §2）。
        """

        experiment = self.pendulum_experiment(experiment_id)
        candidate_store = TrackStore(self._store.tracks, self._store.observations)
        for old_member in experiment.roles.track_ids():
            candidate_store.clear_track_engine_points(old_member)
        record = RoleBindingEditRecord(
            record_id=uuid4(),
            timestamp=utc_now(),
            old_roles=experiment.roles,
            new_roles=new_roles,
            revision=experiment.measurement_revision + 1,
        )
        updated = replace(
            experiment,
            roles=new_roles,
            measurement_revision=experiment.measurement_revision + 1,
            active_infer_run_id=None,
            activation_history=(*experiment.activation_history, record),
        )
        try:
            candidate = replace(
                self._project,
                experiments=tuple(
                    updated if item.experiment_id == experiment_id else item
                    for item in self._project.experiments
                ),
                tracks=candidate_store.tracks,
                observations=candidate_store.observations,
            )
            candidate = self._with_stale_results_for_experiment(candidate, experiment_id)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        self._commit_project(candidate, candidate_store)
        return updated

    def delete_pendulum_experiment(self, experiment_id: UUID) -> None:
        """删除 experiment；被 run 或科学结果引用时拒绝（契约 §5）。"""

        experiment = self.pendulum_experiment(experiment_id)
        referencing_runs = [
            run.run_id
            for run in self._project.tracking_runs
            if run.experiment_id == experiment_id
        ]
        if referencing_runs:
            raise ProjectSessionError(
                "cannot delete an experiment referenced by tracking runs; "
                "delete those runs first"
            )
        referencing_results = [
            result.result_id
            for result in self._project.scientific_results
            if result.experiment_id == experiment_id
        ]
        if referencing_results:
            raise ProjectSessionError(
                "cannot delete an experiment referenced by scientific results"
            )
        candidate = replace(
            self._project,
            experiments=tuple(
                item
                for item in self._project.experiments
                if item.experiment_id != experiment_id
            ),
        )
        self._commit_project(candidate)
        logger.info("pendulum experiment deleted: %s", experiment.experiment_id)

    def _commit_experiment_change(
        self, experiment_id: UUID, updated: PendulumExperiment
    ) -> PendulumExperiment:
        """实验事实变更的公共提交：revision 递增已由调用方完成，这里统一
        失效科学结果并单次提交。"""

        try:
            candidate = replace(
                self._project,
                experiments=tuple(
                    updated if item.experiment_id == experiment_id else item
                    for item in self._project.experiments
                ),
            )
            candidate = self._with_stale_results_for_experiment(candidate, experiment_id)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        self._commit_project(candidate)
        return updated

    def _bump_experiment(self, experiment_id: UUID) -> tuple[PendulumExperiment, int]:
        experiment = self.pendulum_experiment(experiment_id)
        return experiment, experiment.measurement_revision + 1

    def set_fixed_pivot(
        self, experiment_id: UUID, pivot_px: tuple[float, float] | None
    ) -> PendulumExperiment:
        """保存/清除固定 pivot（像素）；tracked pivot 永不写入此字段。"""

        experiment, revision = self._bump_experiment(experiment_id)
        try:
            geometry = replace(experiment.geometry, fixed_pivot_px=pivot_px)
            updated = replace(experiment, geometry=geometry, measurement_revision=revision)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        return self._commit_experiment_change(experiment_id, updated)

    def set_true_vertical(
        self,
        experiment_id: UUID,
        top_px: tuple[float, float],
        bottom_px: tuple[float, float],
    ) -> PendulumExperiment:
        """设置 true vertical 端点（top→bottom 为待确认的向下方向）。

        端点变化即撤销既有确认（契约 §2）：新对象从 direction_confirmed=False
        开始，用户需重新 confirm。
        """

        experiment, revision = self._bump_experiment(experiment_id)
        try:
            vertical = TrueVertical(top_px=top_px, bottom_px=bottom_px)
            geometry = replace(experiment.geometry, true_vertical=vertical)
            updated = replace(experiment, geometry=geometry, measurement_revision=revision)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        return self._commit_experiment_change(experiment_id, updated)

    def confirm_true_vertical(self, experiment_id: UUID) -> PendulumExperiment:
        """确认当前端点的 top→bottom 即重力向下方向（绑定端点 digest）。"""

        experiment, revision = self._bump_experiment(experiment_id)
        vertical = experiment.geometry.true_vertical
        if vertical is None:
            raise ProjectSessionError("set true vertical endpoints before confirming")
        try:
            geometry = replace(experiment.geometry, true_vertical=vertical.confirmed())
            updated = replace(experiment, geometry=geometry, measurement_revision=revision)
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        return self._commit_experiment_change(experiment_id, updated)

    def clear_true_vertical(self, experiment_id: UUID) -> PendulumExperiment:
        """清除 true vertical 事实。"""

        experiment, revision = self._bump_experiment(experiment_id)
        geometry = replace(experiment.geometry, true_vertical=None)
        updated = replace(experiment, geometry=geometry, measurement_revision=revision)
        return self._commit_experiment_change(experiment_id, updated)

    def set_physical(
        self, experiment_id: UUID,
        physical: PhysicalParameters | None,
    ) -> PendulumExperiment:
        """保存/清除物理参数（effective pivot-to-COM 长度与 g，来源必须显式）。"""

        experiment, revision = self._bump_experiment(experiment_id)
        try:
            updated = replace(
                experiment, physical=physical, measurement_revision=revision
            )
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        return self._commit_experiment_change(experiment_id, updated)

    def set_release_frame(
        self, experiment_id: UUID, frame_index: int | None
    ) -> PendulumExperiment:
        """保存/清除 release 帧（当前源帧，不做 -1 调整；D06/U04）。"""

        experiment, revision = self._bump_experiment(experiment_id)
        video = next(
            (
                video
                for video in self._project.videos
                if video.video_id == experiment.video_id
            ),
            None,
        )
        if video is None:
            raise ProjectSessionError("experiment video is not registered")
        if frame_index is not None and not 0 <= frame_index < video.frame_count:
            raise ProjectSessionError(
                f"release frame {frame_index} is outside the video frame range"
            )
        try:
            updated = replace(
                experiment,
                release_frame_index=frame_index,
                measurement_revision=revision,
            )
        except ValueError as error:
            raise ProjectSessionError(str(error)) from error
        return self._commit_experiment_change(experiment_id, updated)

    def save_as_publication(
        self, destination: Path, roles: PendulumRoles | None = None
    ) -> Project:
        """保存为 publication 项目（ADR-0017）；成功后切换会话根目录。

        已有 v1 根目录 → 显式迁移到新目录（记录 source manifest SHA）；
        尚未保存的新项目 → 以 v2 首存（设计决策 2，无迁移记录）。`roles`
        提供时在同一 candidate 中创建首个 experiment（向导的
        "destination + 完整四 role draft 一次提交"）。任何失败保持当前
        session/root/manifest/backup 不变。
        """

        if not isinstance(self._repository, PublicationRepositoryPort):
            raise ProjectSessionError(
                "repository does not support publication migration"
            )
        if self._project.required_capabilities:
            raise ProjectSessionError(
                "project is already a publication project"
            )
        if self._project_root is None:
            return self._first_save_publication(destination, roles)
        candidate = replace(
            self._project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )
        if roles is not None:
            # 契约 §2：迁移时清除/归档 bound Track 的旧单轨 active 指针——
            # experiment 是唯一 activation 真值，遗留指针会造成双源显示且
            # guard 封死了应用内清理路径。activation_history 保留在
            # refinement state 内作为归档记录。
            candidate = self._candidate_with_experiment(candidate, roles)
        destination = destination.resolve()
        saved = self._repository.save_as_publication(
            self._project_root, destination, candidate
        )
        self._project = saved
        self._project_root = destination
        self._saved_project = saved
        # tracks 可能被迁移事务改写（清除 legacy 指针），重建镜像 store
        self._store = TrackStore(saved.tracks, saved.observations)
        self._undo_stack.clear()
        self._redo_stack.clear()
        return saved

    def _first_save_publication(
        self, destination: Path, roles: PendulumRoles | None
    ) -> Project:
        """新项目 v2 首存：无 v1 源，不写 migration 记录（设计决策 2）。"""

        candidate = replace(
            self._project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )
        if roles is not None:
            candidate = self._candidate_with_experiment(candidate, roles)
        destination = destination.resolve()
        saved = self._repository.create_from_project(destination, candidate)
        self._project = saved
        self._project_root = destination
        self._saved_project = saved
        self._store = TrackStore(saved.tracks, saved.observations)
        self._undo_stack.clear()
        self._redo_stack.clear()
        return saved

    def _candidate_with_experiment(
        self, candidate: Project, roles: PendulumRoles
    ) -> Project:
        video_ids = {
            track.video_id for track in candidate.tracks
            if track.track_id in roles.track_ids()
        }
        if len(video_ids) != 1:
            raise ProjectSessionError(
                "pendulum roles must reference four tracks of one video"
            )
        experiment = create_pendulum_experiment(uuid4(), video_ids.pop(), roles)
        # 契约 §2：绑定即清除/归档旧单轨 active 指针（guard 会封死旧清理路径）
        stripped_tracks = tuple(
            self._strip_legacy_active_pointer(track)
            if track.track_id in roles.track_ids()
            else track
            for track in candidate.tracks
        )
        return replace(
            candidate, tracks=stripped_tracks, experiments=(experiment,)
        )

    @staticmethod
    def _strip_legacy_active_pointer(track: Track) -> Track:
        state = extract_refinement_state(track)
        if state.active_infer_run_id is None:
            return track
        cleared = replace(state, active_infer_run_id=None)
        return attach_refinement_state(track, cleared)

    # ------------------------------------------------------------------
    # Inference Result Activation & Replacement (Phase 5.4 ADR-0014)
    # ------------------------------------------------------------------

    def get_track_activation_status(
        self,
        track_id: UUID,
    ) -> tuple[str, UUID | None, str | None]:
        """获取指定 Track 的 AI 观测激活状态。

        返回 (status, active_run_id, detail):
        - ("active", run_id, None): 存在显式激活的 infer run
        - ("none", None, detail): 无激活的 AI 观测
        - ("legacy_inferred", run_id, detail): 5.4 前项目且存在唯一定位明确的 infer run
        - ("legacy_mixed", None, detail): 5.4 前项目且存在多 run 混合或无法归属的 AI 观测
        """
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        ref_state = extract_refinement_state(track)
        if ref_state.active_infer_run_id is not None:
            return "active", ref_state.active_infer_run_id, None

        # 检查 TrackStore 中是否存在非 manual 的 AI 观测
        ai_points = [
            p
            for p in self._store.observations
            if p.track_id == track_id and p.source != "manual"
        ]
        if not ai_points:
            return "none", None, "No active AI observations"

        source_details = {p.source_detail for p in ai_points}
        matching_runs = [
            r
            for r in self.tracking_runs()
            if track_id in r.member_track_ids and r.task_type == "infer" and r.source_detail in source_details
        ]
        if len(source_details) == 1 and len(matching_runs) == 1:
            return "legacy_inferred", matching_runs[0].run_id, "Inferred from single matching infer run"
        return "legacy_mixed", None, "Legacy mixed observations from multiple runs or unmapped sources"

    def activate_infer_run(
        self,
        track_id: UUID,
        run_id: UUID,
    ) -> ActivationRecord:
        """激活指定的 completed infer run（当前 Track 必须尚未激活任何 AI 结果）。"""
        self._require_unbound_track(track_id, "activate_infer_run")
        status, active_run_id, _ = self.get_track_activation_status(track_id)
        if status in ("active", "legacy_inferred", "legacy_mixed"):
            raise ProjectSessionError(
                f"Track already has active AI observations (status: {status}). "
                f"Use replace_active_infer_run instead of activate_infer_run."
            )
        return self._activate_or_replace_infer_run(track_id, run_id, action="activate")

    def replace_active_infer_run(
        self,
        track_id: UUID,
        run_id: UUID,
    ) -> ActivationRecord:
        """用指定的 completed infer run 替换当前 Track 的活动 AI 结果（ADR-0014：须已有结果）。"""
        self._require_unbound_track(track_id, "replace_active_infer_run")
        status, _active_run_id, _ = self.get_track_activation_status(track_id)
        if status == "none":
            raise ProjectSessionError(
                "Track has no active AI result; use activate_infer_run instead of replace"
            )
        return self._activate_or_replace_infer_run(track_id, run_id, action="replace")

    def clear_active_ai_observations(
        self,
        track_id: UUID,
    ) -> ActivationRecord:
        """清除当前 Track 的所有活动 AI 观测，全部 manual 点完好保留。"""
        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")
        self._require_unbound_track(track_id, "clear_active_ai_observations")

        ref_state = extract_refinement_state(track)
        status, prev_run_id, _ = self.get_track_activation_status(track_id)
        if status == "none":
            raise ProjectSessionError("Track has no active AI observations to clear")

        if any(track_id in r.member_track_ids and r.status in {"pending", "running"} for r in self.tracking_runs()):
            raise ProjectSessionError("Cannot activate or modify tracking results while a task is running on this track")

        candidate_store = TrackStore(self._store.tracks, self._store.observations)
        candidate_store.clear_track_engine_points(track_id)

        now_str = _now_iso_utc()
        manual_cnt = len(
            [
                p
                for p in self._store.observations
                if p.track_id == track_id and p.source == "manual" and p.status == "active"
            ]
        )
        record = ActivationRecord(
            record_id=uuid4(),
            timestamp=now_str,
            action="clear",
            from_run_id=ref_state.active_infer_run_id or prev_run_id,
            to_run_id=None,
            point_count=0,
            manual_preserved_count=manual_cnt,
        )
        new_ref_state = replace(
            ref_state,
            active_infer_run_id=None,
            activation_history=(*ref_state.activation_history, record),
        )
        updated_track = attach_refinement_state(track, new_ref_state)
        candidate_store.update_track(updated_track)

        updated_project = replace(
            self._project,
            tracks=candidate_store.tracks,
            observations=candidate_store.observations,
            derived=mark_tracks_stale(self._project.derived, {track_id}),
        )
        self._commit_project(updated_project, candidate_store)
        return record

    def _activate_or_replace_infer_run(
        self,
        track_id: UUID,
        run_id: UUID,
        action: str,
    ) -> ActivationRecord:
        """底层激活/替换事务：校验产物、指纹与时序，原子写入并标记 DerivedData stale。"""
        from ai_physics_tracker.application.inference_job import read_observation_exchange

        track = next((t for t in self._store.tracks if t.track_id == track_id), None)
        if track is None:
            raise ProjectSessionError(f"unknown track_id: {track_id}")

        target_run = next((r for r in self.tracking_runs() if r.run_id == run_id), None)
        if target_run is None:
            raise ProjectSessionError(f"unknown tracking run_id: {run_id}")
        if target_run.track_id != track_id:
            raise ProjectSessionError(f"Run {run_id} does not belong to track {track_id}")
        if target_run.task_type != "infer":
            raise ProjectSessionError(f"Run {run_id} is not an inference run")
        if target_run.status != "completed":
            raise ProjectSessionError(f"Run {run_id} is not completed (status: {target_run.status})")

        if any(track_id in r.member_track_ids and r.status in {"pending", "running"} for r in self.tracking_runs()):
            raise ProjectSessionError("Cannot activate or modify tracking results while a task is running on this track")

        root = self.project_root
        if root is None:
            raise ProjectSessionError("Save project before activating tracking results")
        root = root.resolve()

        obs_rel = target_run.extra_fields.get("observations_path") or f"data/engines/{run_id}/observations.json"
        obs_file = (root / obs_rel).resolve()
        if not obs_file.is_file() or not obs_file.is_relative_to(root):
            raise ProjectSessionError(f"Observation artifact missing for run {run_id}: {obs_rel}")

        file_info = target_run.extra_fields.get("observations_file_info")
        if file_info is not None:
            st = obs_file.stat()
            # 5.6 Slice 0（用户批复方案 2）：仅比对文件大小。合法拷贝/备份还原会
            # 更新 mtime，纳秒级强等值会永久拒绝激活；接受防篡改强度下降。
            recorded_size = int(file_info[0])
            if st.st_size != recorded_size:
                raise ProjectSessionError("Observation artifact was modified after inference completed")

        video = next((v for v in self._project.videos if v.video_id == target_run.video_id), None)
        timeline = next((t for t in self._project.timelines if t.video_id == target_run.video_id), None)
        if video is None or timeline is None:
            raise ProjectSessionError("Video or timeline missing for run")
        if not self.can_measure(target_run.video_id):
            # 与 import_engine_points 同一授权口径（review L-6）：激活重建的观测
            # 同样依赖已核实的 CFR 时间轴
            raise ProjectSessionError("Video timing is not authorized for activation")

        try:
            points = read_observation_exchange(obs_file)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError,
                OSError) as error:
            raise ProjectSessionError(
                f"Observation artifact for run {run_id} is unreadable: {obs_file}: {error}"
            ) from error
        for p in points:
            if (
                p.track_id != track_id
                or p.source != target_run.engine
                or p.source_detail != target_run.source_detail
            ):
                raise ProjectSessionError("Engine point does not match target run metadata")
            if not 0 <= p.frame_index < video.frame_count:
                raise ProjectSessionError(f"Engine point frame {p.frame_index} out of bounds")
            expected_time = frame_to_time(p.frame_index, timeline)
            if abs(p.time_s - expected_time) >= TIME_COMPARISON_TOLERANCE_S:
                raise ProjectSessionError(f"Engine point time does not match timeline at frame {p.frame_index}")

        candidate_store = TrackStore(self._store.tracks, self._store.observations)
        act_cnt, sup_cnt = candidate_store.replace_track_engine_points(track_id, points)
        manual_cnt = len(
            [
                p
                for p in self._store.observations
                if p.track_id == track_id and p.source == "manual" and p.status == "active"
            ]
        )

        ref_state = extract_refinement_state(track)
        status, prev_inferred_id, _ = self.get_track_activation_status(track_id)
        prev_run_id = ref_state.active_infer_run_id or prev_inferred_id

        now_str = _now_iso_utc()
        record = ActivationRecord(
            record_id=uuid4(),
            timestamp=now_str,
            action=action,
            from_run_id=prev_run_id,
            to_run_id=run_id,
            point_count=act_cnt,
            manual_preserved_count=manual_cnt,
            superseded_count=sup_cnt,
        )
        new_ref_state = replace(
            ref_state,
            active_infer_run_id=run_id,
            activation_history=(*ref_state.activation_history, record),
        )
        updated_track = attach_refinement_state(track, new_ref_state)
        candidate_store.update_track(updated_track)

        updated_project = replace(
            self._project,
            tracks=candidate_store.tracks,
            observations=candidate_store.observations,
            derived=mark_tracks_stale(self._project.derived, {track_id}),
        )
        self._commit_project(updated_project, candidate_store)
        return record

