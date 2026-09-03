"""与持久化后端无关的观测存储语义。"""

from dataclasses import dataclass, replace
from uuid import UUID

from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.types import utc_now


@dataclass(frozen=True)
class BatchWriteResult:
    """单次引擎批次写入的正常 first-wins 结果。"""

    inserted: int
    skipped: int


def resolve_effective_point(
    points: tuple[TrackPoint, ...] | list[TrackPoint],
    track_id: UUID,
    frame_index: int,
) -> TrackPoint | None:
    """生效值解析：manual 优先，否则取最新的 active 引擎观测。"""

    active = [
        point
        for point in points
        if point.track_id == track_id
        and point.frame_index == frame_index
        and point.status == "active"
    ]
    manual = [point for point in active if point.source == "manual"]
    if manual:
        return max(manual, key=lambda point: (point.created_at, str(point.point_id)))
    if not active:
        return None
    return max(active, key=lambda point: (point.created_at, str(point.point_id)))


def resolve_effective_points(
    points: tuple[TrackPoint, ...] | list[TrackPoint],
    track_id: UUID,
) -> tuple[TrackPoint, ...]:
    """批量解析一个 Track 的生效观测，并按源帧号排序。"""

    selected: dict[int, TrackPoint] = {}
    for point in points:
        if point.track_id != track_id or point.status != "active":
            continue
        current = selected.get(point.frame_index)
        if current is None:
            selected[point.frame_index] = point
            continue
        if current.source == "manual" and point.source != "manual":
            continue
        if point.source == "manual" and current.source != "manual":
            selected[point.frame_index] = point
            continue
        if (point.created_at, str(point.point_id)) > (
            current.created_at,
            str(current.point_id),
        ):
            selected[point.frame_index] = point
    return tuple(selected[frame] for frame in sorted(selected))


class TrackStore:
    """实现 Track 与 TrackPoint 写入规则的可变服务。"""

    def __init__(
        self,
        tracks: tuple[Track, ...] = (),
        observations: tuple[TrackPoint, ...] = (),
    ) -> None:
        self._tracks = list(tracks)
        self._observations = list(observations)
        if len({track.track_id for track in tracks}) != len(tracks):
            raise ValueError("track_id values must be unique")
        if len({track.name for track in tracks}) != len(tracks):
            raise ValueError("track names must be unique")
        if len({point.point_id for point in observations}) != len(observations):
            raise ValueError("point_id values must be unique")
        track_ids = {track.track_id for track in tracks}
        if any(point.track_id not in track_ids for point in observations):
            raise ValueError("every observation must reference a known track")

    @property
    def tracks(self) -> tuple[Track, ...]:
        """返回 track 标识的不可变快照。"""

        return tuple(self._tracks)

    @property
    def observations(self) -> tuple[TrackPoint, ...]:
        """返回全部观测的不可变快照。"""

        return tuple(self._observations)

    def add_track(self, track: Track) -> None:
        """添加 track_id 与名称均唯一的 Track。"""

        if any(item.track_id == track.track_id for item in self._tracks):
            raise ValueError(f"track_id already exists: {track.track_id}")
        if any(item.name == track.name for item in self._tracks):
            raise ValueError(f"track name already exists: {track.name}")
        self._tracks.append(track)

    def rename_track(self, track_id: UUID, name: str) -> None:
        """重命名 Track，同时保持项目内名称唯一。"""

        if not name.strip():
            raise ValueError("track name must not be blank")
        if any(item.name == name and item.track_id != track_id for item in self._tracks):
            raise ValueError(f"track name already exists: {name}")
        for index, track in enumerate(self._tracks):
            if track.track_id == track_id:
                self._tracks[index] = replace(track, name=name)
                return
        raise ValueError(f"unknown track_id: {track_id}")

    def update_track(self, track: Track) -> None:
        """更新 Track（如 extra_fields），保持 track_id 存在。"""
        for index, item in enumerate(self._tracks):
            if item.track_id == track.track_id:
                self._tracks[index] = track
                return
        raise ValueError(f"unknown track_id: {track.track_id}")

    def get_track(self, track_id: UUID) -> Track:
        """获取指定 track_id 的 Track，不存在则抛出 ValueError。"""
        for item in self._tracks:
            if item.track_id == track_id:
                return item
        raise ValueError(f"unknown track_id: {track_id}")

    def delete_track(self, track_id: UUID) -> None:
        """删除 Track，并级联删除其全部观测。"""

        if not any(track.track_id == track_id for track in self._tracks):
            raise ValueError(f"unknown track_id: {track_id}")
        self._tracks = [track for track in self._tracks if track.track_id != track_id]
        self._observations = [
            point for point in self._observations if point.track_id != track_id
        ]

    def add_manual_point(self, point: TrackPoint) -> None:
        """按 manual last-wins 写入手动点，被取代的引擎值保留为 superseded。"""

        self._require_known_track(point.track_id)
        if point.source != "manual" or point.status != "active":
            raise ValueError("manual insertion requires an active source=manual point")
        if any(item.point_id == point.point_id for item in self._observations):
            raise ValueError(f"point_id already exists: {point.point_id}")

        prior_manual_ids = {
            item.point_id
            for item in self._observations
            if item.track_id == point.track_id
            and item.frame_index == point.frame_index
            and item.source == "manual"
        }
        now = utc_now()
        updated: list[TrackPoint] = []
        for existing in self._observations:
            if existing.point_id in prior_manual_ids:
                continue
            same_frame = (
                existing.track_id == point.track_id
                and existing.frame_index == point.frame_index
            )
            is_engine = existing.source != "manual"
            linked_to_prior = existing.superseded_by in prior_manual_ids
            if same_frame and is_engine and (existing.status == "active" or linked_to_prior):
                updated.append(
                    replace(
                        existing,
                        status="superseded",
                        superseded_by=point.point_id,
                        modified_at=now,
                    )
                )
            else:
                updated.append(existing)
        updated.append(point)
        self._observations = updated

    def add_engine_points(self, points: tuple[TrackPoint, ...]) -> BatchWriteResult:
        """按 first-wins 帧语义插入引擎观测。"""

        existing_ids = {point.point_id for point in self._observations}
        incoming_ids = [point.point_id for point in points]
        if len(set(incoming_ids)) != len(incoming_ids):
            raise ValueError("engine batch point_id values must be unique")
        if any(point_id in existing_ids for point_id in incoming_ids):
            raise ValueError("engine batch point_id already exists")
        for point in points:
            self._require_known_track(point.track_id)
            if point.source == "manual" or point.status != "active":
                raise ValueError("engine batch requires active non-manual points")

        active_keys = {
            (existing.track_id, existing.frame_index)
            for existing in self._observations
            if existing.status == "active"
        }
        inserted = 0
        skipped = 0
        for point in points:
            key = (point.track_id, point.frame_index)
            if key in active_keys:
                skipped += 1
                continue
            self._observations.append(point)
            active_keys.add(key)
            inserted += 1
        return BatchWriteResult(inserted=inserted, skipped=skipped)

    def delete_manual_point(self, point_id: UUID) -> None:
        """硬删除一个手动点，仅恢复被它取代的那些观测。"""

        target = next(
            (point for point in self._observations if point.point_id == point_id), None
        )
        if target is None:
            raise ValueError(f"unknown point_id: {point_id}")
        if target.source != "manual":
            raise ValueError("engine observations cannot be deleted individually")
        now = utc_now()
        restored: list[TrackPoint] = []
        for point in self._observations:
            if point.point_id == point_id:
                continue
            if point.superseded_by == point_id:
                restored.append(
                    replace(
                        point,
                        status="active",
                        superseded_by=None,
                        modified_at=now,
                    )
                )
            else:
                restored.append(point)
        self._observations = restored

    def clear_engine_run(self, source_detail: str | None) -> int:
        """删除一个引擎运行组（含显式的 legacy null 组）。"""

        if source_detail == "":
            raise ValueError("source_detail must be non-blank or None")
        before = len(self._observations)
        removed_ids = {
            point.point_id
            for point in self._observations
            if point.source != "manual" and point.source_detail == source_detail
        }
        self._observations = [
            point for point in self._observations if point.point_id not in removed_ids
        ]
        return before - len(self._observations)

    def clear_track_engine_points(self, track_id: UUID) -> int:
        """清除指定 Track 的所有引擎观测（保留全部 manual 点）。"""
        self._require_known_track(track_id)
        before = len(self._observations)
        self._observations = [
            point
            for point in self._observations
            if not (point.track_id == track_id and point.source != "manual")
        ]
        return before - len(self._observations)

    def replace_track_engine_points(
        self,
        track_id: UUID,
        points: tuple[TrackPoint, ...] | list[TrackPoint],
    ) -> tuple[int, int]:
        """原子清除当前 Track 的所有旧引擎观测，并装配新的引擎观测。

        若某帧存在 active manual 点，则新引擎观测记录为 status='superseded' 并关联 superseded_by=manual_point.point_id；
        若无 active manual 点，则记录为 status='active'。
        全部 manual 点原样保留。
        返回 (activated_count, superseded_count)。
        """
        self._require_known_track(track_id)
        existing_ids = {
            p.point_id
            for p in self._observations
            if not (p.track_id == track_id and p.source != "manual")
        }
        incoming_ids = [p.point_id for p in points]
        if len(set(incoming_ids)) != len(incoming_ids):
            raise ValueError("engine batch point_id values must be unique")
        if any(pid in existing_ids for pid in incoming_ids):
            raise ValueError("engine batch point_id already exists in store")
        incoming_frames = [p.frame_index for p in points]
        if len(set(incoming_frames)) != len(incoming_frames):
            raise ValueError("engine batch contains duplicate frame_index entries")

        for point in points:
            if point.track_id != track_id:
                raise ValueError(f"point track_id {point.track_id} does not match {track_id}")
            if point.source == "manual":
                raise ValueError("engine batch points cannot have source='manual'")

        # 1. 过滤掉该 track 所有的旧 engine 观测
        remaining = [
            point
            for point in self._observations
            if not (point.track_id == track_id and point.source != "manual")
        ]

        # 2. 建立该 track 当前 active manual 点的 frame_index -> point_id 映射
        manual_by_frame = {
            p.frame_index: p.point_id
            for p in remaining
            if p.track_id == track_id and p.source == "manual" and p.status == "active"
        }

        # 3. 逐个装配 incoming engine points
        activated_count = 0
        superseded_count = 0
        for p in points:
            manual_id = manual_by_frame.get(p.frame_index)
            if manual_id is not None:
                new_p = replace(p, status="superseded", superseded_by=manual_id)
                superseded_count += 1
            else:
                new_p = replace(p, status="active", superseded_by=None)
                activated_count += 1
            remaining.append(new_p)

        self._observations = remaining
        return activated_count, superseded_count

    def query(
        self,
        *,
        track_id: UUID | None = None,
        frame_index: int | None = None,
        source_detail: str | None = None,
    ) -> tuple[TrackPoint, ...]:
        """返回满足给定过滤条件的观测。"""

        return tuple(
            point
            for point in self._observations
            if (track_id is None or point.track_id == track_id)
            and (frame_index is None or point.frame_index == frame_index)
            and (source_detail is None or point.source_detail == source_detail)
        )

    def _require_known_track(self, track_id: UUID) -> None:
        if not any(track.track_id == track_id for track in self._tracks):
            raise ValueError(f"unknown track_id: {track_id}")
