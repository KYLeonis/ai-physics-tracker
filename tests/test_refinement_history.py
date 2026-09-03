"""Tests for Phase 5.4 Refinement History, Fixed Validation Series, and Result Activation contracts."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID, uuid4
import pytest

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.refinement_history import (
    ActivationRecord,
    PredictionSummary,
    RefinementIterationInfo,
    RefinementState,
    ValidationLabelSnapshot,
    ValidationSeries,
    attach_prediction_summary,
    attach_refinement_iteration,
    attach_refinement_state,
    check_validation_series_consistency,
    deserialize_prediction_summary,
    deserialize_refinement_iteration,
    deserialize_refinement_state,
    deserialize_validation_series,
    extract_prediction_summary,
    extract_refinement_iteration,
    extract_refinement_state,
    serialize_prediction_summary,
    serialize_refinement_iteration,
    serialize_refinement_state,
    serialize_validation_series,
)
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    SuggestedFrameReviewState,
    attach_review_state,
    extract_review_state,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.project import Project, create_project
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import TrackingRun, create_tracking_run
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _make_sample_snapshot(frame_index: int = 10, px: float = 100.0, py: float = 200.0) -> ValidationLabelSnapshot:
    return ValidationLabelSnapshot(
        point_id=uuid4(),
        frame_index=frame_index,
        pixel_x=px,
        pixel_y=py,
        modified_at="2026-09-03T12:00:00Z",
    )


def test_validation_label_snapshot_validation() -> None:
    snap = _make_sample_snapshot(5, 50.5, 60.5)
    assert snap.frame_index == 5
    assert snap.pixel_x == 50.5
    assert snap.pixel_y == 60.5

    # Negative frame index
    with pytest.raises(ValueError, match="non-negative int"):
        ValidationLabelSnapshot(uuid4(), -1, 10.0, 10.0, "2026-09-03T12:00:00Z")

    # Non-finite coordinates
    with pytest.raises(ValueError, match="finite"):
        ValidationLabelSnapshot(uuid4(), 0, float("nan"), 10.0, "2026-09-03T12:00:00Z")
    with pytest.raises(ValueError, match="finite"):
        ValidationLabelSnapshot(uuid4(), 0, 10.0, float("inf"), "2026-09-03T12:00:00Z")


def test_validation_series_sorting_and_properties() -> None:
    s1 = _make_sample_snapshot(30)
    s2 = _make_sample_snapshot(10)
    s3 = _make_sample_snapshot(20)

    series = ValidationSeries(
        series_id=uuid4(),
        name="Validation Set 1",
        created_at="2026-09-03T12:00:00Z",
        label_snapshots=(s1, s2, s3),
    )

    # Should be sorted by frame_index ascending
    assert series.frame_indices == (10, 20, 30)
    assert series.label_snapshots[0].frame_index == 10
    assert series.label_snapshots[1].frame_index == 20
    assert series.label_snapshots[2].frame_index == 30

    with pytest.raises(ValueError, match="name must be a non-empty string"):
        ValidationSeries(uuid4(), "", "2026-09-03T12:00:00Z", ())


def test_activation_record_validation() -> None:
    rec = ActivationRecord(
        record_id=uuid4(),
        timestamp="2026-09-03T12:00:00Z",
        action="replace",
        from_run_id=uuid4(),
        to_run_id=uuid4(),
        point_count=100,
        manual_preserved_count=5,
    )
    assert rec.action == "replace"

    with pytest.raises(ValueError, match="action must be"):
        ActivationRecord(
            record_id=uuid4(),
            timestamp="2026-09-03T12:00:00Z",
            action="invalid_action",
            from_run_id=None,
            to_run_id=None,
            point_count=0,
            manual_preserved_count=0,
        )


def test_refinement_state_helpers() -> None:
    ser1 = ValidationSeries(uuid4(), "V1", "2026-09-03T12:00:00Z", (_make_sample_snapshot(1),))
    ser2 = ValidationSeries(uuid4(), "V2", "2026-09-03T12:00:00Z", (_make_sample_snapshot(2),))

    state = RefinementState(
        active_infer_run_id=uuid4(),
        active_validation_series_id=ser2.series_id,
        validation_series=(ser1, ser2),
    )

    assert state.get_series(ser1.series_id) == ser1
    assert state.get_series(ser2.series_id) == ser2
    assert state.get_series(uuid4()) is None
    assert state.active_series == ser2


def test_refinement_iteration_info_and_prediction_summary() -> None:
    iter_info = RefinementIterationInfo(
        iteration_index=1,
        previous_training_run_id=uuid4(),
        source_infer_run_id=uuid4(),
        validation_series_id=uuid4(),
        training_labels=(_make_sample_snapshot(0),),
        review_summary={"accepted": 2, "corrected": 3},
    )
    assert iter_info.iteration_index == 1

    summary = PredictionSummary(
        row_count=100,
        eligible_count=85,
        missing_count=5,
        low_confidence_count=10,
        threshold=0.6,
        coverage=0.85,
    )
    assert summary.coverage == 0.85

    with pytest.raises(ValueError, match="threshold must be in"):
        PredictionSummary(100, 85, 5, 10, threshold=1.5, coverage=0.85)


def test_check_validation_series_consistency() -> None:
    pid1, pid2 = uuid4(), uuid4()
    t_id = uuid4()
    now = datetime.now(timezone.utc)

    snap1 = ValidationLabelSnapshot(pid1, 10, 100.0, 200.0, now.isoformat())
    snap2 = ValidationLabelSnapshot(pid2, 20, 150.0, 250.0, now.isoformat())
    series = ValidationSeries(uuid4(), "Series A", now.isoformat(), (snap1, snap2))

    # Exact match
    pts_exact = [
        TrackPoint(
            point_id=pid1,
            track_id=t_id,
            frame_index=10,
            time_s=0.33,
            pixel_x=100.0,
            pixel_y=200.0,
            source="manual",
            visibility="visible",
            status="active",
            created_at=now,
            modified_at=now,
        ),
        TrackPoint(
            point_id=pid2,
            track_id=t_id,
            frame_index=20,
            time_s=0.66,
            pixel_x=150.0,
            pixel_y=250.0,
            source="manual",
            visibility="visible",
            status="active",
            created_at=now,
            modified_at=now,
        ),
    ]
    valid, reason = check_validation_series_consistency(series, pts_exact)
    assert valid is True
    assert reason is None

    # Point deleted (pid2 missing)
    valid, reason = check_validation_series_consistency(series, [pts_exact[0]])
    assert valid is False
    assert "deleted" in (reason or "")

    # Point moved to a different frame
    pts_moved = [
        pts_exact[0],
        TrackPoint(
            point_id=pid2,
            track_id=t_id,
            frame_index=25,
            time_s=0.83,
            pixel_x=150.0,
            pixel_y=250.0,
            source="manual",
            visibility="visible",
            status="active",
            created_at=now,
            modified_at=now,
        ),
    ]
    valid, reason = check_validation_series_consistency(series, pts_moved)
    assert valid is False
    assert "moved" in (reason or "")

    # Coordinates modified
    pts_modified = [
        pts_exact[0],
        TrackPoint(
            point_id=pid2,
            track_id=t_id,
            frame_index=20,
            time_s=0.66,
            pixel_x=150.5,  # changed by 0.5px
            pixel_y=250.0,
            source="manual",
            visibility="visible",
            status="active",
            created_at=now,
            modified_at=now,
        ),
    ]
    valid, reason = check_validation_series_consistency(series, pts_modified)
    assert valid is False
    assert "modified" in (reason or "")


def test_serialization_and_deserialization_roundtrips() -> None:
    now = datetime.now(timezone.utc).isoformat()
    snap = _make_sample_snapshot(15, 10.2, 20.4)
    series = ValidationSeries(uuid4(), "Test Series", now, (snap,))
    rec = ActivationRecord(uuid4(), now, "activate", None, uuid4(), 50, 2)
    state = RefinementState(
        active_infer_run_id=uuid4(),
        activation_history=(rec,),
        active_validation_series_id=series.series_id,
        validation_series=(series,),
    )

    state_dict = serialize_refinement_state(state)
    # Ensure JSON serializable
    json_str = json.dumps(state_dict)
    loaded_dict = json.loads(json_str)

    restored_state = deserialize_refinement_state(loaded_dict)
    assert restored_state.active_infer_run_id == state.active_infer_run_id
    assert restored_state.active_validation_series_id == state.active_validation_series_id
    assert len(restored_state.activation_history) == 1
    assert restored_state.activation_history[0].action == "activate"
    assert len(restored_state.validation_series) == 1
    assert restored_state.validation_series[0].name == "Test Series"
    assert restored_state.validation_series[0].label_snapshots[0].frame_index == 15

    # RefinementIterationInfo roundtrip
    iter_info = RefinementIterationInfo(
        iteration_index=2,
        previous_training_run_id=uuid4(),
        source_infer_run_id=uuid4(),
        validation_series_id=series.series_id,
        training_labels=(snap,),
        review_summary={"accepted": 1},
    )
    iter_dict = serialize_refinement_iteration(iter_info)
    restored_iter = deserialize_refinement_iteration(json.loads(json.dumps(iter_dict)))
    assert restored_iter is not None
    assert restored_iter.iteration_index == 2
    assert restored_iter.validation_series_id == series.series_id
    assert len(restored_iter.training_labels) == 1

    # PredictionSummary roundtrip
    summary = PredictionSummary(100, 80, 5, 15, 0.5, 0.8)
    sum_dict = serialize_prediction_summary(summary)
    restored_sum = deserialize_prediction_summary(json.loads(json.dumps(sum_dict)))
    assert restored_sum is not None
    assert restored_sum.coverage == 0.8


def test_attach_and_extract_helpers_and_coexistence() -> None:
    now = datetime.now(timezone.utc)
    track = Track(uuid4(), uuid4(), "Track 1", "#FF0000", now)
    state = RefinementState(active_infer_run_id=uuid4())

    track_with_state = attach_refinement_state(track, state)
    extracted = extract_refinement_state(track_with_state)
    assert extracted.active_infer_run_id == state.active_infer_run_id

    # TrackingRun with both suggested_frame_review and refinement_iteration
    run = create_tracking_run(
        video_id=track.video_id,
        track_id=track.track_id,
        engine="dlc",
        engine_version="3.0",
        task_type="train",
        config={},
        source_detail="test",
    )
    # Attach suggested frame review (5.3)
    rev_state = SuggestedFrameReviewState(
        active_batch=ActiveReviewBatch(uuid4(), {}, ()),
        reviewed_frames={},
    )
    run = attach_review_state(run, rev_state)

    # Attach refinement iteration (5.4)
    iter_info = RefinementIterationInfo(iteration_index=0)
    run = attach_refinement_iteration(run, iter_info)

    # Extract both
    assert extract_review_state(run) is not None
    assert extract_refinement_iteration(run) is not None
    assert extract_refinement_iteration(run).iteration_index == 0


def test_project_session_validation_series_lifecycle(tmp_path) -> None:
    session = ProjectSession.start(ProjectRepository())
    video, _ = session.register_external_video(
        tmp_path / "clip.mp4",
        VideoStreamInfo(64, 48, 30.0, 100, "fake", "cfr"),
    )

    # Add track
    t = session.add_track(video.video_id, name="Pendulum")
    t_id = t.track_id

    # Mark manual points at frames 5, 10, 15
    session.mark_point(t_id, 5, 10.0, 20.0)
    session.mark_point(t_id, 10, 15.0, 25.0)
    session.mark_point(t_id, 15, 20.0, 30.0)

    # Initial refinement state should be empty
    st = session.get_refinement_state(t_id)
    assert st.active_validation_series_id is None
    assert len(st.validation_series) == 0

    # Validation check when no active series
    valid, reason = session.validate_active_validation_series(t_id)
    assert valid is False
    assert "No active" in (reason or "")

    # Cannot create validation series on a frame with no manual point
    with pytest.raises(ProjectSessionError, match="No active manual point found"):
        session.create_validation_series(t_id, "Series 1", [5, 99])

    # Create validation series on frames 5 and 15
    series = session.create_validation_series(t_id, "Series 1", [5, 15])
    assert series.name == "Series 1"
    assert series.frame_indices == (5, 15)

    # Active validation series is automatically set
    st2 = session.get_refinement_state(t_id)
    assert st2.active_validation_series_id == series.series_id
    assert len(st2.validation_series) == 1

    # Validate active series: should be True
    valid, reason = session.validate_active_validation_series(t_id)
    assert valid is True
    assert reason is None

    # Undo should revert creation of validation series
    assert session.can_undo
    session.undo()
    st_undone = session.get_refinement_state(t_id)
    assert st_undone.active_validation_series_id is None
    assert len(st_undone.validation_series) == 0

    # Redo should restore it
    assert session.can_redo
    session.redo()
    st_redone = session.get_refinement_state(t_id)
    assert st_redone.active_validation_series_id == series.series_id
    assert len(st_redone.validation_series) == 1

    # Modify manual point at frame 5 (move by 5px)
    session.mark_point(t_id, 5, 15.0, 20.0)
    valid, reason = session.validate_active_validation_series(t_id)
    assert valid is False
    assert "modified" in (reason or "")

    # Set active validation series to None
    session.set_active_validation_series(t_id, None)
    st_inactive = session.get_refinement_state(t_id)
    assert st_inactive.active_validation_series_id is None

    # Set active validation series back to series.series_id
    session.set_active_validation_series(t_id, series.series_id)
    assert session.get_refinement_state(t_id).active_validation_series_id == series.series_id

    # Delete validation series
    session.delete_validation_series(t_id, series.series_id)
    st_deleted = session.get_refinement_state(t_id)
    assert st_deleted.active_validation_series_id is None
    assert len(st_deleted.validation_series) == 0
