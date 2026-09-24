"""同帧四 role 引导标注的状态投影（P1.2-S3，application 层，Qt-free）。

引导只是呈现层：点击落点仍经 `session.mark_point` 写入 role 对应的
Track（无第二落点路径），本模块只从当前事实计算"该帧还缺哪个 role、
这一帧是否完整、下一帧是哪帧"。partial 是合法编辑状态（契约 §3），
引导不阻止用户经时间轴离开——Next gate 只约束引导内的推进按钮。
"""

from dataclasses import dataclass

from ai_physics_tracker.application.annotation_join import (
    join_complete_frames,
)
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumExperiment
from ai_physics_tracker.domain.project import Project


@dataclass(frozen=True)
class AnnotationGuideState:
    """当前帧的引导状态；全部从 join 事实派生，无第二真值。"""

    frame_index: int
    pending_roles: tuple[str, ...]     # 该帧尚无 manual 的 role（规范序）
    done_roles: tuple[str, ...]        # 已有 manual 的 role
    frame_complete: bool               # 4/4
    frame_in_frame_set: bool           # 是否属于共享帧集
    next_frame_set_index: int | None   # 帧集中当前帧之后的下一帧

    @property
    def current_role(self) -> str | None:
        """引导点击的落点 role：第一个待标 role；4/4 时为 None。"""

        return self.pending_roles[0] if self.pending_roles else None

    @property
    def progress_label(self) -> str:
        return f"{len(self.done_roles)}/4 landmark roles marked"

    def hint(self) -> str:
        """侧栏引导条文案；complete 时给出推进提示。"""

        if self.frame_complete:
            if self.next_frame_set_index is not None:
                return (
                    f"Frame {self.frame_index} complete (4/4). "
                    f"Continue to frame {self.next_frame_set_index}."
                )
            return f"Frame {self.frame_index} complete (4/4)."
        role = self.current_role
        assert role is not None
        remaining = " → ".join(self.pending_roles)
        return (
            f"Frame {self.frame_index}: click the {role} "
            f"({len(self.done_roles)}/4 done; remaining: {remaining}). "
            "Partial frames are saved but never used for training."
        )


def annotation_guide_state(
    project: Project,
    experiment: PendulumExperiment,
    frame_index: int,
) -> AnnotationGuideState:
    """从 join 事实重建 frame_index 处的引导状态。"""

    result = join_complete_frames(project, experiment)
    _ = result  # join 的 complete 分类同时是 gate 依据；此处按帧取 role 集合
    manual_by_role_frame: dict[int, set[str]] = {}
    role_track_ids = experiment.roles.track_ids()
    for point in project.observations:
        if point.source != "manual" or point.track_id not in role_track_ids:
            continue
        if point.status != "active":
            continue
        role = ROLE_ORDER[role_track_ids.index(point.track_id)]
        manual_by_role_frame.setdefault(point.frame_index, set()).add(role)

    done_roles = frozenset(manual_by_role_frame.get(frame_index, ()))
    pending = tuple(role for role in ROLE_ORDER if role not in done_roles)
    frame_set_frames = (
        experiment.frame_set.frames if experiment.frame_set is not None else ()
    )
    next_index = next(
        (frame for frame in frame_set_frames if frame > frame_index),
        None,
    )
    return AnnotationGuideState(
        frame_index=frame_index,
        pending_roles=pending,
        done_roles=tuple(role for role in ROLE_ORDER if role in done_roles),
        frame_complete=len(done_roles) == len(ROLE_ORDER),
        frame_in_frame_set=frame_index in frame_set_frames,
        next_frame_set_index=next_index,
    )


def frame_set_worklist(experiment: PendulumExperiment) -> tuple[int, ...]:
    """共享帧集的引导遍历顺序（升序；frame_set 为空时返回空）。"""

    if experiment.frame_set is None:
        return ()
    return experiment.frame_set.frames


def frame_set_progress(
    project: Project, experiment: PendulumExperiment
) -> tuple[int, int, tuple[int, ...]] | None:
    """帧集完成度投影（F4/F5，2026-09-24 HR）：还要标多少帧的单一事实源。

    返回 ``(4/4 完成帧数, 帧集总帧数, 未完成帧号升序)``；无帧集返回
    None。单次 join 同时服务引导条进度与测量卡"下一缺帧"指引，避免
    逐帧调用 annotation_guide_state 的 O(k·n) 重复投影。
    """

    frames = experiment.frame_set.frames if experiment.frame_set is not None else ()
    if not frames:
        return None
    complete = set(join_complete_frames(project, experiment).complete_frame_indices)
    remaining = tuple(frame for frame in frames if frame not in complete)
    return len(frames) - len(remaining), len(frames), remaining
