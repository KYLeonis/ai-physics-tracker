"""TrackStore overwrite and correction tests for AC-5."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.track_store import TrackStore, resolve_effective_point

_NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _track() -> Track:
    return Track(uuid4(), uuid4(), "bob", "#12AB34", _NOW)


def _point(
    track_id: UUID,
    frame_index: int,
    *,
    source: str,
    created_offset_s: int = 0,
    pixel_x: float = 10.0,
    source_detail: str | None = None,
) -> TrackPoint:
    created_at = _NOW + timedelta(seconds=created_offset_s)
    return TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=frame_index,
        time_s=frame_index / 30.0,
        pixel_x=pixel_x,
        pixel_y=20.0,
        source=source,
        source_detail=source_detail,
        confidence=None if source == "manual" else 0.8,
        visibility="visible" if source == "manual" else "unknown",
        status="active",
        created_at=created_at,
        modified_at=created_at,
    )


def test_engine_batch_is_first_wins_and_reports_skips() -> None:
    track = _track()
    first = _point(track.track_id, 1, source="template", source_detail="run-1")
    duplicate = _point(track.track_id, 1, source="template", source_detail="run-1")
    second = _point(track.track_id, 2, source="template", source_detail="run-1")
    store = TrackStore((track,))

    result = store.add_engine_points((first, duplicate, second))

    assert (result.inserted, result.skipped) == (2, 1)
    assert store.observations == (first, second)


def test_manual_correction_supersedes_engine_and_delete_restores_original() -> None:
    track = _track()
    engine = _point(track.track_id, 4, source="template", pixel_x=11.5)
    manual = _point(track.track_id, 4, source="manual", pixel_x=12.25)
    store = TrackStore((track,), (engine,))

    store.add_manual_point(manual)

    stored_engine = next(point for point in store.observations if point.source != "manual")
    assert stored_engine.pixel_x == 11.5
    assert stored_engine.status == "superseded"
    assert stored_engine.superseded_by == manual.point_id
    assert resolve_effective_point(store.observations, track.track_id, 4) == manual

    store.delete_manual_point(manual.point_id)

    assert store.observations[0].status == "active"
    assert store.observations[0].superseded_by is None
    assert resolve_effective_point(store.observations, track.track_id, 4).pixel_x == 11.5


def test_manual_last_wins_rewires_engine_without_losing_prediction() -> None:
    track = _track()
    engine = _point(track.track_id, 5, source="template")
    first = _point(track.track_id, 5, source="manual", created_offset_s=1)
    replacement = _point(track.track_id, 5, source="manual", created_offset_s=2)
    store = TrackStore((track,), (engine,))

    store.add_manual_point(first)
    store.add_manual_point(replacement)

    assert first not in store.observations
    stored_engine = next(point for point in store.observations if point.source != "manual")
    assert stored_engine.superseded_by == replacement.point_id
    assert resolve_effective_point(store.observations, track.track_id, 5) == replacement


def test_effective_resolution_uses_newest_active_engine_point() -> None:
    track = _track()
    old = _point(track.track_id, 2, source="template", created_offset_s=1)
    new = _point(track.track_id, 2, source="template", created_offset_s=2)

    assert resolve_effective_point((old, new), track.track_id, 2) == new


def test_engine_point_cannot_be_deleted_individually() -> None:
    track = _track()
    engine = _point(track.track_id, 1, source="template")
    store = TrackStore((track,), (engine,))

    with pytest.raises(ValueError, match="cannot be deleted individually"):
        store.delete_manual_point(engine.point_id)


def test_delete_track_cascades_observations() -> None:
    track = _track()
    store = TrackStore((track,), (_point(track.track_id, 1, source="manual"),))

    store.delete_track(track.track_id)

    assert store.tracks == ()
    assert store.observations == ()
