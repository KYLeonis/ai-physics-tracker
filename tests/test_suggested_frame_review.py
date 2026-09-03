"""Phase 5.3 建议帧审核契约与序列化单元测试（ADR-0013）。"""

import json
from uuid import UUID, uuid4
import pytest

from pathlib import Path

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.suggested_frame_review import (
    SUGGESTED_FRAME_REVIEW_KEY,
    ActiveReviewBatch,
    ReviewCandidate,
    ReviewPredictionSnapshot,
    ReviewQueueController,
    ReviewRecord,
    SuggestedFrameReviewState,
    attach_review_state,
    compute_batch_summary,
    extract_review_state,
    get_candidate_disposition,
    get_excluded_frames_for_run,
    get_prior_correct_frames_for_run,
    serialize_review_state,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_completed,
    mark_run_running,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.dlc_predictions import RawPrediction
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _sample_run(extra_fields: dict | None = None) -> TrackingRun:
    now = utc_now()
    return TrackingRun(
        run_id=uuid4(),
        video_id=uuid4(),
        track_id=uuid4(),
        engine="dlc",
        engine_version="3.0.1",
        task_type="infer",
        config={},
        source_detail="test-detail",
        created_at=now,
        model_snapshot="models/snapshot.pt",
        status="completed",
        completed_at=now,
        extra_fields=dict(extra_fields or {}),
    )


def test_review_prediction_snapshot_validates_finite_and_range() -> None:
    snap = ReviewPredictionSnapshot(pixel_x=100.5, pixel_y=200.25, confidence=0.85)
    assert snap.pixel_x == 100.5
    assert snap.pixel_y == 200.25
    assert snap.confidence == 0.85
    assert snap.to_dict() == {"pixel_x": 100.5, "pixel_y": 200.25, "confidence": 0.85}

    with pytest.raises(ValueError, match="pixel_x must be a finite float"):
        ReviewPredictionSnapshot(pixel_x=float("nan"), pixel_y=200.0, confidence=0.5)

    with pytest.raises(ValueError, match="confidence must be in range"):
        ReviewPredictionSnapshot(pixel_x=10.0, pixel_y=20.0, confidence=1.5)

    with pytest.raises(ValueError, match="confidence must be in range"):
        ReviewPredictionSnapshot(pixel_x=10.0, pixel_y=20.0, confidence=-0.1)


def test_review_prediction_from_raw_prediction_handles_nan_and_missing() -> None:
    assert ReviewPredictionSnapshot.from_raw_prediction(None) is None

    missing = RawPrediction(frame_index=1, pixel_x=float("nan"), pixel_y=float("nan"), confidence=float("nan"))
    assert ReviewPredictionSnapshot.from_raw_prediction(missing) is None

    valid_raw = RawPrediction(frame_index=2, pixel_x=50.0, pixel_y=60.0, confidence=0.9)
    snap = ReviewPredictionSnapshot.from_raw_prediction(valid_raw)
    assert snap is not None
    assert snap.pixel_x == 50.0
    assert snap.confidence == 0.9


def test_review_candidate_validates_invariants() -> None:
    cand = ReviewCandidate(
        frame_index=10,
        prediction=ReviewPredictionSnapshot(pixel_x=1.0, pixel_y=2.0, confidence=0.7),
        components={"uncertainty": 0.8, "jump": 0.1},
        raw_components={"uncertainty": 0.3},
        reasons=("low_confidence",),
        total_score=0.9,
    )
    assert cand.frame_index == 10
    assert cand.reasons == ("low_confidence",)

    with pytest.raises(ValueError, match="frame_index must be an integer"):
        ReviewCandidate(
            frame_index=True,  # type: ignore[arg-type]
            prediction=None,
            components={},
            raw_components={},
            reasons=(),
            total_score=0.0,
        )

    with pytest.raises(ValueError, match="total_score must be a finite float"):
        ReviewCandidate(
            frame_index=0,
            prediction=None,
            components={},
            raw_components={},
            reasons=(),
            total_score=float("nan"),
        )


def test_review_record_enforces_manual_point_id_contract() -> None:
    req_id = uuid4()
    point_id = uuid4()

    # Correct requires manual_point_id
    rec_correct = ReviewRecord(
        disposition="corrected",
        reviewed_at="2026-09-03T12:00:00Z",
        request_id=req_id,
        prediction=None,
        manual_point_id=point_id,
    )
    assert rec_correct.disposition == "corrected"
    assert rec_correct.manual_point_id == point_id

    with pytest.raises(ValueError, match="corrected disposition requires a valid UUID"):
        ReviewRecord(
            disposition="corrected",
            reviewed_at="2026-09-03T12:00:00Z",
            request_id=req_id,
            prediction=None,
            manual_point_id=None,
        )

    # Accept & Skip must have manual_point_id = None
    rec_accept = ReviewRecord(
        disposition="accepted",
        reviewed_at="2026-09-03T12:00:00Z",
        request_id=req_id,
        prediction=None,
        manual_point_id=None,
    )
    assert rec_accept.disposition == "accepted"

    with pytest.raises(ValueError, match="accepted disposition must not have a manual_point_id"):
        ReviewRecord(
            disposition="accepted",
            reviewed_at="2026-09-03T12:00:00Z",
            request_id=req_id,
            prediction=None,
            manual_point_id=point_id,
        )


def test_active_review_batch_rejects_duplicate_frames() -> None:
    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=5,
        prediction=None,
        components={},
        raw_components={},
        reasons=(),
        total_score=0.5,
    )
    c2 = ReviewCandidate(
        frame_index=5,
        prediction=None,
        components={},
        raw_components={},
        reasons=(),
        total_score=0.3,
    )
    with pytest.raises(ValueError, match="duplicate frame_index"):
        ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1, c2))


def test_serialization_and_extraction_roundtrip() -> None:
    req_id = uuid4()
    point_id = uuid4()

    c1 = ReviewCandidate(
        frame_index=12,
        prediction=ReviewPredictionSnapshot(pixel_x=321.5, pixel_y=205.0, confidence=0.42),
        components={"uncertainty": 0.8},
        raw_components={"uncertainty": 0.58},
        reasons=("low_confidence",),
        total_score=0.8,
    )
    c2 = ReviewCandidate(
        frame_index=25,
        prediction=None,  # missing prediction -> null in json
        components={"jump": 0.9},
        raw_components={"jump": 4.5},
        reasons=("jump_outlier",),
        total_score=0.85,
    )

    batch = ActiveReviewBatch(
        request_id=req_id,
        params_snapshot={"top_n": 10, "seed": 42},
        candidates=(c1, c2),
    )

    r1 = ReviewRecord(
        disposition="corrected",
        reviewed_at="2026-09-03T12:00:00Z",
        request_id=req_id,
        prediction=c1.prediction,
        manual_point_id=point_id,
    )
    r2 = ReviewRecord(
        disposition="skipped",
        reviewed_at="2026-09-03T12:05:00Z",
        request_id=req_id,
        prediction=None,
        manual_point_id=None,
    )

    state = SuggestedFrameReviewState(
        active_batch=batch,
        reviewed_frames={12: r1, 25: r2},
    )

    serialized = serialize_review_state(state)
    # Check JSON serializability and null for missing prediction
    dumped = json.dumps(serialized)
    parsed_json = json.loads(dumped)
    assert parsed_json["active_batch"]["candidates"][1]["prediction"] is None
    assert parsed_json["reviewed_frames"]["12"]["manual_point_id"] == str(point_id)
    assert parsed_json["reviewed_frames"]["25"]["manual_point_id"] is None

    # Attach to run and verify sibling key preservation
    run = _sample_run(extra_fields={"existing_metric": 123})
    updated_run = attach_review_state(run, state)
    assert updated_run.extra_fields["existing_metric"] == 123
    assert SUGGESTED_FRAME_REVIEW_KEY in updated_run.extra_fields

    extracted = extract_review_state(updated_run)
    assert extracted is not None
    assert extracted.active_batch is not None
    assert extracted.active_batch.request_id == req_id
    assert len(extracted.active_batch.candidates) == 2
    assert extracted.active_batch.candidates[0].prediction == c1.prediction
    assert extracted.active_batch.candidates[1].prediction is None

    assert len(extracted.reviewed_frames) == 2
    assert extracted.reviewed_frames[12].disposition == "corrected"
    assert extracted.reviewed_frames[12].manual_point_id == point_id
    assert extracted.reviewed_frames[25].disposition == "skipped"
    assert extracted.reviewed_frames[25].manual_point_id is None


def test_extract_review_state_handles_old_project_and_corruption() -> None:
    # 1. No key -> None (old project compatibility)
    clean_run = _sample_run()
    assert extract_review_state(clean_run) is None

    # 2. Corrupted top-level type -> ValueError
    bad_run1 = _sample_run(extra_fields={SUGGESTED_FRAME_REVIEW_KEY: "not_a_dict"})
    with pytest.raises(ValueError, match="corrupted"):
        extract_review_state(bad_run1)

    # 3. Corrupted record -> ValueError
    bad_run2 = _sample_run(
        extra_fields={
            SUGGESTED_FRAME_REVIEW_KEY: {
                "active_batch": None,
                "reviewed_frames": {"1": {"disposition": "invalid_disp"}},
            }
        }
    )
    with pytest.raises(ValueError, match="malformed review record"):
        extract_review_state(bad_run2)


def test_batch_summary_and_disposition_helpers() -> None:
    req_id = uuid4()
    c1 = ReviewCandidate(frame_index=1, prediction=None, components={}, raw_components={}, reasons=(), total_score=1.0)
    c2 = ReviewCandidate(frame_index=2, prediction=None, components={}, raw_components={}, reasons=(), total_score=0.9)
    c3 = ReviewCandidate(frame_index=3, prediction=None, components={}, raw_components={}, reasons=(), total_score=0.8)
    c4 = ReviewCandidate(frame_index=4, prediction=None, components={}, raw_components={}, reasons=(), total_score=0.7)

    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1, c2, c3, c4))

    now_iso = utc_now().isoformat()
    state = SuggestedFrameReviewState(
        active_batch=batch,
        reviewed_frames={
            1: ReviewRecord(disposition="accepted", reviewed_at=now_iso, request_id=req_id, prediction=None),
            2: ReviewRecord(disposition="corrected", reviewed_at=now_iso, request_id=req_id, prediction=None, manual_point_id=uuid4()),
            3: ReviewRecord(disposition="skipped", reviewed_at=now_iso, request_id=req_id, prediction=None),
        },
    )

    summary = compute_batch_summary(state)
    assert summary.total_candidates == 4
    assert summary.accepted_count == 1
    assert summary.corrected_count == 1
    assert summary.skipped_count == 1
    assert summary.pending_count == 1
    assert summary.total_reviewed == 3

    assert get_candidate_disposition(state, 1) == "accepted"
    assert get_candidate_disposition(state, 2) == "corrected"
    assert get_candidate_disposition(state, 3) == "skipped"
    assert get_candidate_disposition(state, 4) == "pending"
    assert get_candidate_disposition(state, 99) == "pending"

    # R2.8 suppression sets
    assert get_excluded_frames_for_run(state) == frozenset({1, 3})
    assert get_prior_correct_frames_for_run(state) == frozenset({2})


def _setup_session_and_controller(
    tmp_path: Path,
) -> tuple[ProjectSession, TrackingRun, ReviewQueueController]:
    session = ProjectSession.start(ProjectRepository())
    info = VideoStreamInfo(64, 48, 10.0, 10, "fake", "cfr")
    session.register_external_video(tmp_path / "clip.mp4", info)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    run = mark_run_running(
        create_tracking_run(
            video.video_id,
            track.track_id,
            "infer",
            engine="dlc",
            engine_version="3.0.1",
            source_detail="test-infer",
        )
    )
    session.record_tracking_run(run)
    completed_run = mark_run_completed(run)
    session.update_tracking_run(completed_run)

    req_id = uuid4()
    c1 = ReviewCandidate(frame_index=1, prediction=ReviewPredictionSnapshot(10.0, 20.0, 0.5), components={}, raw_components={}, reasons=(), total_score=1.0)
    c2 = ReviewCandidate(frame_index=2, prediction=ReviewPredictionSnapshot(15.0, 25.0, 0.4), components={}, raw_components={}, reasons=(), total_score=0.9)
    c3 = ReviewCandidate(frame_index=3, prediction=None, components={}, raw_components={}, reasons=(), total_score=0.8)
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1, c2, c3))
    session.set_active_review_batch(completed_run.run_id, batch)

    ctrl = ReviewQueueController(session, completed_run.run_id)
    return session, completed_run, ctrl


def test_review_queue_controller_navigation_and_bounds(tmp_path: Path) -> None:
    session, run, ctrl = _setup_session_and_controller(tmp_path)

    assert ctrl.count == 3
    assert ctrl.current_index == 0
    assert ctrl.current_frame_index == 1
    assert ctrl.current_disposition == "pending"
    assert ctrl.can_navigate_next is True
    assert ctrl.can_navigate_previous is False
    assert ctrl.has_pending is True

    # Next
    assert ctrl.next_candidate() is not None
    assert ctrl.current_index == 1
    assert ctrl.current_frame_index == 2
    assert ctrl.can_navigate_previous is True

    # Next to end
    assert ctrl.next_candidate() is not None
    assert ctrl.current_index == 2
    assert ctrl.current_frame_index == 3
    assert ctrl.can_navigate_next is False
    assert ctrl.next_candidate() is None

    # Previous back to start
    assert ctrl.previous_candidate() is not None
    assert ctrl.current_index == 1
    assert ctrl.previous_candidate() is not None
    assert ctrl.current_index == 0
    assert ctrl.previous_candidate() is None

    # Direct select by frame
    assert ctrl.select_frame(3) is not None
    assert ctrl.current_index == 2
    assert ctrl.select_frame(99) is None
    assert ctrl.current_index == 2


def test_review_queue_controller_accept_skip_correct_and_auto_advance(tmp_path: Path) -> None:
    session, run, ctrl = _setup_session_and_controller(tmp_path)

    # Frame 1: Accept -> auto-advances to frame 2
    rec1 = ctrl.accept_current(auto_advance=True)
    assert rec1.disposition == "accepted"
    assert ctrl.current_index == 1
    assert ctrl.current_frame_index == 2
    assert ctrl.summary.accepted_count == 1
    assert ctrl.summary.pending_count == 2

    # Frame 2: Skip -> auto-advances to frame 3
    rec2 = ctrl.skip_current(auto_advance=True)
    assert rec2.disposition == "skipped"
    assert ctrl.current_index == 2
    assert ctrl.current_frame_index == 3
    assert ctrl.summary.skipped_count == 1
    assert ctrl.summary.pending_count == 1

    # Frame 3: Correct (12.0, 22.0)
    ctrl.set_correcting(True)
    assert ctrl.is_correcting is True
    point, rec3 = ctrl.correct_current(12.0, 22.0, auto_advance=True)
    assert point.pixel_x == 12.0
    assert rec3.disposition == "corrected"
    assert ctrl.is_correcting is False
    assert ctrl.summary.corrected_count == 1
    assert ctrl.summary.pending_count == 0
    assert ctrl.has_pending is False


def test_review_queue_controller_empty_batch(tmp_path: Path) -> None:
    session = ProjectSession.start(ProjectRepository())
    info = VideoStreamInfo(64, 48, 10.0, 10, "fake", "cfr")
    session.register_external_video(tmp_path / "clip.mp4", info)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    run = mark_run_completed(mark_run_running(create_tracking_run(video.video_id, track.track_id, "infer")))
    session.record_tracking_run(run)

    ctrl = ReviewQueueController(session, run.run_id)
    assert ctrl.count == 0
    assert ctrl.current_candidate is None
    assert ctrl.current_frame_index is None
    assert ctrl.current_disposition == "pending"
    assert ctrl.can_navigate_next is False
    assert ctrl.can_navigate_previous is False
    assert ctrl.next_candidate() is None
    assert ctrl.previous_candidate() is None
    with pytest.raises(ValueError, match="No candidate currently selected"):
        ctrl.accept_current()

