"""与 Qt 无关的标注会话：协调 Project 快照、TrackStore 与视频登记。

application 层组件：持有当前 Project（frozen）与 TrackStore，GUI 不
直接修改 Project（phase2-requirements.md §2 R1/R5）。每次写操作经
TrackStore 语义落地后同步生成新的 Project 快照；dirty 状态驱动
2.4 的未保存提示。
"""

import logging
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.domain.project import (
    Project,
    add_video,
    create_project,
    relink_video,
    delete_track,
    register_video_reference,
)
from ai_physics_tracker.domain.derived import DerivedData, mark_tracks_stale
from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.track_store import (
    TrackStore,
    resolve_effective_point,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.domain.video import Video

logger = logging.getLogger(__name__)


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
        self._saved_project = deepcopy(project)
        self._project_root = project_root
        self._store = TrackStore(project.tracks, project.observations)
        self._verified_videos: set[UUID] = set()
        self._undo_stack: list[tuple[tuple[Track, ...], tuple[TrackPoint, ...], tuple[DerivedData, ...]]] = []
        self._redo_stack: list[tuple[tuple[Track, ...], tuple[TrackPoint, ...], tuple[DerivedData, ...]]] = []

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
            vfr_suspected=info.timing_status == "vfr_suspected",
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
        """删除 Track 并级联删除其观测。"""

        candidate = delete_track(self._project, track_id)
        self._commit_store(TrackStore(candidate.tracks, candidate.observations), candidate.derived)

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

    def save(self) -> Project:
        """保存到已绑定的项目根目录并清除 dirty；无根目录时报错。"""

        if self._project_root is None:
            raise ProjectSessionError(
                "project has no root directory; use save-as workflow first"
            )
        self._project = self._repository.save(self._project_root, self._project)
        self._saved_project = deepcopy(self._project)
        # 保存点是安全边界：跨保存的回溯会让 dirty 语义混乱
        self._undo_stack.clear()
        self._redo_stack.clear()
        return self._project

    @classmethod
    def load(cls, repository: ProjectRepositoryPort, project_root: Path) -> "ProjectSession":
        """候选会话工厂；失败不触碰当前窗口持有的会话。"""

        return cls(repository, repository.load(project_root), project_root.resolve())

    def save_as(self, destination: Path) -> Project:
        """首存或另存，IO 成功后才提交根目录、clean 基线与历史边界。"""

        destination = destination.resolve()
        if self._project_root is None:
            saved = self._repository.create_from_project(destination, self._project)
        else:
            saved = self._repository.save_as(self._project_root, destination, self._project)
        self._project = saved
        self._project_root = destination
        self._saved_project = deepcopy(saved)
        self._undo_stack.clear()
        self._redo_stack.clear()
        return saved

    def detached(self) -> "ProjectSession":
        """后台 IO 使用独立快照；活动会话不被工作线程修改。"""

        candidate = ProjectSession(self._repository, deepcopy(self._project), self._project_root)
        candidate._saved_project = deepcopy(self._saved_project)
        candidate._verified_videos = set(self._verified_videos)
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

    def confirm_video_timing(self, video_id: UUID, report: TimingReport) -> None:
        """应用在本次文件探测完成后授予测量能力；该集合不持久化。"""

        if report.status == "cfr":
            self._verified_videos.add(video_id)
        else:
            self._verified_videos.discard(video_id)

    def video_path(self, video: Video) -> Path | None:
        """缺媒体为可恢复状态；只解析，不自动修改 locator。"""

        if self._project_root is not None:
            return self._repository.resolve_video_path(self._project_root, video)
        path = Path(video.original_path) if video.original_path else None
        return path if path is not None and path.is_file() else None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        """撤销最近一次写操作（含"替换后恢复旧点"）；无可撤销时返回 False。"""

        if not self._undo_stack:
            return False
        self._redo_stack.append(self._current_data_snapshot())
        tracks, observations, derived = self._undo_stack.pop()
        self._store = TrackStore(tracks, observations)
        self._project = replace(self._project, tracks=tracks, observations=observations, derived=derived)
        return True

    def redo(self) -> bool:
        """重做被撤销的操作；无可重做时返回 False。"""

        if not self._redo_stack:
            return False
        self._undo_stack.append(self._current_data_snapshot())
        tracks, observations, derived = self._redo_stack.pop()
        self._store = TrackStore(tracks, observations)
        self._project = replace(self._project, tracks=tracks, observations=observations, derived=derived)
        return True

    def _current_data_snapshot(
        self,
    ) -> tuple[tuple[Track, ...], tuple[TrackPoint, ...], tuple[DerivedData, ...]]:
        return (self._store.tracks, self._store.observations, self._project.derived)

    def _push_undo_snapshot(self) -> None:
        self._undo_stack.append(self._current_data_snapshot())
        del self._undo_stack[:-UNDO_STACK_LIMIT]
        self._redo_stack.clear()

    def _next_track_name(self) -> str:
        index = len(self._store.tracks) + 1
        existing = {track.name for track in self._store.tracks}
        while f"Track {index}" in existing:
            index += 1
        return f"Track {index}"

    def _commit_store(self, store: TrackStore, derived: tuple[DerivedData, ...]) -> None:
        # 先完成跨对象校验；失败不能污染原 store 或提前清 redo。
        project = replace(self._project, tracks=store.tracks,
                          observations=store.observations, derived=derived)
        self._push_undo_snapshot()
        self._store = store
        self._project = project
