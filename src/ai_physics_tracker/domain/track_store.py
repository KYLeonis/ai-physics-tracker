"""Observation storage semantics independent of the persistence backend."""

from dataclasses import dataclass, replace
from uuid import UUID

from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.types import utc_now


@dataclass(frozen=True)
class BatchWriteResult:
    """Normal first-wins outcome for one engine batch."""

    inserted: int
    skipped: int


def resolve_effective_point(
    points: tuple[TrackPoint, ...] | list[TrackPoint],
    track_id: UUID,
    frame_index: int,
) -> TrackPoint | None:
    """Resolve manual first, otherwise the newest active engine observation."""

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


class TrackStore:
    """Mutable service implementing Track and TrackPoint write rules."""

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
        """Return an immutable snapshot of track identities."""

        return tuple(self._tracks)

    @property
    def observations(self) -> tuple[TrackPoint, ...]:
        """Return an immutable snapshot of all observations."""

        return tuple(self._observations)

    def add_track(self, track: Track) -> None:
        """Add a uniquely identified and named Track."""

        if any(item.track_id == track.track_id for item in self._tracks):
            raise ValueError(f"track_id already exists: {track.track_id}")
        if any(item.name == track.name for item in self._tracks):
            raise ValueError(f"track name already exists: {track.name}")
        self._tracks.append(track)

    def rename_track(self, track_id: UUID, name: str) -> None:
        """Rename one Track while preserving project-wide uniqueness."""

        if not name.strip():
            raise ValueError("track name must not be blank")
        if any(item.name == name and item.track_id != track_id for item in self._tracks):
            raise ValueError(f"track name already exists: {name}")
        for index, track in enumerate(self._tracks):
            if track.track_id == track_id:
                self._tracks[index] = replace(track, name=name)
                return
        raise ValueError(f"unknown track_id: {track_id}")

    def delete_track(self, track_id: UUID) -> None:
        """Delete a Track and cascade to its observations."""

        if not any(track.track_id == track_id for track in self._tracks):
            raise ValueError(f"unknown track_id: {track_id}")
        self._tracks = [track for track in self._tracks if track.track_id != track_id]
        self._observations = [
            point for point in self._observations if point.track_id != track_id
        ]

    def add_manual_point(self, point: TrackPoint) -> None:
        """Apply manual last-wins and retain superseded engine values."""

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
        """Insert engine observations with first-wins frame semantics."""

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

        inserted = 0
        skipped = 0
        for point in points:
            has_active = any(
                existing.track_id == point.track_id
                and existing.frame_index == point.frame_index
                and existing.status == "active"
                for existing in self._observations
            )
            if has_active:
                skipped += 1
                continue
            self._observations.append(point)
            inserted += 1
        return BatchWriteResult(inserted=inserted, skipped=skipped)

    def delete_manual_point(self, point_id: UUID) -> None:
        """Hard-delete a manual point and reactivate only points it superseded."""

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
        """Remove one engine run group, including the explicit legacy null group."""

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

    def query(
        self,
        *,
        track_id: UUID | None = None,
        frame_index: int | None = None,
        source_detail: str | None = None,
    ) -> tuple[TrackPoint, ...]:
        """Return observations matching the supplied filters."""

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
