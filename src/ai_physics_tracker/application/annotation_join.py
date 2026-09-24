"""同帧四 role 标注 join 与完整度投影（P1.2-S2，Qt-free 纯函数）。

契约 §3：complete training frame = 同一源帧上四个 role 各有一个当前
active、finite、非 superseded 的 manual label；不拼邻帧、不用 AI 补点。
本模块只读 Project/Experiment 事实，不做任何写入；训练 request 与
exporter 一律先经这里重新 join，不信 UI 计数（P1 计划 Risks）。
"""

from dataclasses import dataclass
from math import isfinite
from typing import Any

from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumExperiment
from ai_physics_tracker.domain.project import Project
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import canonical_json_digest


@dataclass(frozen=True)
class CompleteFrameLabel:
    """一个 complete 帧的四 role label 引用（按规范 role 顺序对齐）。"""

    frame_index: int
    points: tuple[TrackPoint, ...]
    point_ids: tuple[str, ...]
    coordinates: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class AnnotationJoinResult:
    """join 诊断：complete/partial/disqualified 三类互斥分类。"""

    complete: tuple[CompleteFrameLabel, ...]
    partial: tuple[tuple[int, int], ...]
    ai_only_frames: tuple[int, ...]
    superseded_frames: tuple[int, ...]
    nonfinite_frames: tuple[int, ...]

    @property
    def complete_frame_indices(self) -> tuple[int, ...]:
        return tuple(label.frame_index for label in self.complete)


def join_complete_frames(
    project: Project, experiment: PendulumExperiment
) -> AnnotationJoinResult:
    """按 experiment role binding join 出 complete/partial 帧分类。

    语义（契约 §3）：
    - 同一帧上四个 role 各有一个 **active** manual 且坐标 finite → complete；
    - 一到三个 active manual → partial（计数为 role 数）；
    - 帧上只有非 active（superseded）manual → superseded_frames（不计入）；
    - 帧上只有 AI 观测 → ai_only_frames（manual 缺席即不完整，AI 不补位）；
    - active manual 含 non-finite 坐标 → nonfinite_frames（整体不完整，
      不产出半个 label）。

    分类优先级：count<4 先归 partial（此时坐标损坏一并记入 nonfinite
    诊断）；superseded_frames 与 nonfinite_frames 两桶是对外部改写
    manifest 的 defense-in-depth——产品写路径中 manual superseded 不产生
    （add_manual_point 直接删旧点）、非有限值被 TrackPoint 构造期拒绝，
    正常流程两桶为空。
    """

    role_track_ids = experiment.roles.track_ids()
    role_names = ROLE_ORDER
    active_by_frame: dict[int, list[TrackPoint | None]] = {}
    any_manual_frames: set[int] = set()
    superseded_only: dict[int, int] = {}
    ai_frames: set[int] = set()

    for point in project.observations:
        if point.track_id not in role_track_ids:
            continue
        role_index = role_track_ids.index(point.track_id)
        if point.source == "manual":
            any_manual_frames.add(point.frame_index)
            if point.status == "superseded":
                superseded_only[point.frame_index] = (
                    superseded_only.get(point.frame_index, 0) + 1
                )
                continue
            active_by_frame.setdefault(point.frame_index, [None] * 4)
            if active_by_frame[point.frame_index][role_index] is not None:
                # add_manual_point 的 last-wins 保证同帧同 track 至多一个
                # active manual；此处出现重复说明数据被外部改写，整体拒绝。
                raise ValueError(
                    f"duplicate active manual points for role "
                    f"'{role_names[role_index]}' at frame {point.frame_index}"
                )
            active_by_frame[point.frame_index][role_index] = point
        else:
            ai_frames.add(point.frame_index)

    complete: list[CompleteFrameLabel] = []
    partial: list[tuple[int, int]] = []
    nonfinite: list[int] = []
    for frame_index in sorted(active_by_frame):
        slots = active_by_frame[frame_index]
        count = sum(1 for point in slots if point is not None)
        if count < 4:
            partial.append((frame_index, count))
            if any(
                not isfinite(point.pixel_x) or not isfinite(point.pixel_y)
                for point in slots
                if point is not None
            ):
                nonfinite.append(frame_index)
            continue
        if any(
            not isfinite(point.pixel_x) or not isfinite(point.pixel_y)
            for point in slots
            if point is not None
        ):
            nonfinite.append(frame_index)
            continue
        points = tuple(point for point in slots if point is not None)
        complete.append(
            CompleteFrameLabel(
                frame_index=frame_index,
                points=points,
                point_ids=tuple(str(point.point_id) for point in points),
                coordinates=tuple(
                    (point.pixel_x, point.pixel_y) for point in points
                ),
            )
        )

    pure_superseded = tuple(
        sorted(
            frame
            for frame in superseded_only
            if frame not in active_by_frame
        )
    )
    ai_only = tuple(
        sorted(
            frame
            for frame in ai_frames
            if frame not in any_manual_frames
        )
    )
    return AnnotationJoinResult(
        complete=tuple(complete),
        partial=tuple(partial),
        ai_only_frames=ai_only,
        superseded_frames=pure_superseded,
        nonfinite_frames=tuple(sorted(nonfinite)),
    )


def canonical_label_digest(
    result: AnnotationJoinResult, frames: tuple[int, ...] | None = None
) -> str:
    """complete 标签集合的 canonical digest（训练 request 与 fixed-check 共用）。

    覆盖帧号、每帧 point_id 与坐标；role 顺序即规范序。显示名、颜色、
    created_at 等非语义字段不进入 digest。`frames` 给出时只对子集计算
    （fixed-check 的冻结比较只看检查帧——帧外的点改动不应使检查失效）。
    """

    selected = (
        result.complete
        if frames is None
        else [label for label in result.complete if label.frame_index in set(frames)]
    )
    payload: dict[str, Any] = {
        "kind": "pendulum-four-role-labels-v1",
        "frames": [
            {
                "frame_index": label.frame_index,
                "points": [
                    {
                        "role_index": role_index,
                        "point_id": str(point.point_id),
                        "pixel_x": point.pixel_x,
                        "pixel_y": point.pixel_y,
                    }
                    for role_index, point in enumerate(label.points)
                ],
            }
            for label in selected
        ],
    }
    return canonical_json_digest(payload)


def fixed_check_status(
    project: Project, experiment: PendulumExperiment
) -> tuple[bool, str | None]:
    """experiment 级 fixed-check 一致性：帧仍 4/4 且子集 digest 未变。

    返回 (valid, reason)；无 fixed_check 返回 (False, "no fixed check set")。
    """

    fixed_check = experiment.fixed_check
    if fixed_check is None:
        return False, "no fixed check set"
    result = join_complete_frames(project, experiment)
    complete_frames = set(result.complete_frame_indices)
    missing = [frame for frame in fixed_check.frames if frame not in complete_frames]
    if missing:
        return False, f"frames no longer complete: {sorted(missing)}"
    current = canonical_label_digest(result, tuple(fixed_check.frames))
    if current != fixed_check.label_digest:
        return False, "labels changed since the check set was frozen"
    return True, None
