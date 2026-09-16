"""P6R-02：Resume ancestry 与固定验证集的隔离资格（Pre-Phase 6 stabilization）。

覆盖：clean 直系 resume、直接 parent 污染、更早祖先污染、更换验证集、
legacy/缺失祖先的 unknown 保守处理、restart 不受影响、无活动验证集。
"""

from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.refinement_history import (
    VALIDATION_COMPARISON_CLEAN,
    VALIDATION_COMPARISON_CONTAMINATED,
    VALIDATION_COMPARISON_UNKNOWN,
    RefinementIterationInfo,
    ValidationLabelSnapshot,
    attach_refinement_iteration,
    validation_training_exposure,
)
from ai_physics_tracker.application.tracking_job import prepare_tracking_request
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_completed,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _labels(frames) -> tuple[ValidationLabelSnapshot, ...]:
    return tuple(
        ValidationLabelSnapshot(
            point_id=uuid4(),
            frame_index=frame,
            pixel_x=1.0,
            pixel_y=2.0,
            modified_at=utc_now().isoformat(),
        )
        for frame in frames
    )


def _train_run(track_id, video_id, *, training_frames, mode="restart",
               resume_from=None, with_iteration=True) -> TrackingRun:
    run = create_tracking_run(video_id, track_id, "train", engine_version="mock")
    if with_iteration:
        run = attach_refinement_iteration(
            run,
            RefinementIterationInfo(
                iteration_index=0,
                training_mode=mode,
                resume_from_training_run_id=resume_from,
                training_labels=_labels(training_frames),
            ),
        )
    return run


# ---------------------------------------------------------------------------
# 纯函数：validation_training_exposure
# ---------------------------------------------------------------------------


def test_clean_lineage_has_no_exposure() -> None:
    parent = _train_run(uuid4(), uuid4(), training_frames=[1, 2, 3])
    runs = (parent,)

    exposure = validation_training_exposure(runs, parent.run_id, [0, 4, 5])

    assert exposure.qualification == VALIDATION_COMPARISON_CLEAN
    assert exposure.exposed_frames == ()
    assert exposure.exposed_ancestors == ()


def test_direct_parent_contamination_reports_frames_and_ancestor() -> None:
    parent = _train_run(uuid4(), uuid4(), training_frames=[1, 2, 3])
    runs = (parent,)

    exposure = validation_training_exposure(runs, parent.run_id, [1])

    assert exposure.qualification == VALIDATION_COMPARISON_CONTAMINATED
    assert exposure.exposed_frames == (1,)
    assert exposure.exposed_ancestors == (parent.run_id,)


def test_earlier_ancestor_contamination_is_detected_through_chain() -> None:
    video_id, track_id = uuid4(), uuid4()
    grandparent = _train_run(track_id, video_id, training_frames=[1, 2, 3])
    parent = _train_run(
        track_id, video_id, training_frames=[5, 6],
        mode="resume", resume_from=grandparent.run_id,
    )
    child = _train_run(
        track_id, video_id, training_frames=[7],
        mode="resume", resume_from=parent.run_id,
    )
    runs = (grandparent, parent, child)

    # parent 自己干净，但 grandparent 见过帧 1
    exposure = validation_training_exposure(runs, child.run_id, [1])

    assert exposure.qualification == VALIDATION_COMPARISON_CONTAMINATED
    assert exposure.exposed_frames == (1,)
    assert exposure.exposed_ancestors == (grandparent.run_id,)


def test_legacy_ancestor_without_membership_is_unknown_not_clean() -> None:
    video_id, track_id = uuid4(), uuid4()
    legacy = _train_run(track_id, video_id, training_frames=[1], with_iteration=False)
    parent = _train_run(
        track_id, video_id, training_frames=[2],
        mode="resume", resume_from=legacy.run_id,
    )

    exposure = validation_training_exposure((legacy, parent), parent.run_id, [9])

    assert exposure.qualification == VALIDATION_COMPARISON_UNKNOWN
    assert "no recorded training membership" in exposure.reasons[0]


def test_missing_ancestor_run_is_unknown() -> None:
    parent = _train_run(
        uuid4(), uuid4(), training_frames=[2],
        mode="resume", resume_from=uuid4(),  # 引用不在注册表中的 run
    )

    exposure = validation_training_exposure((parent,), parent.run_id, [0])

    assert exposure.qualification == VALIDATION_COMPARISON_UNKNOWN
    assert "not registered" in exposure.reasons[0]


def test_lineage_cycle_is_unknown() -> None:
    video_id, track_id = uuid4(), uuid4()
    first = _train_run(track_id, video_id, training_frames=[1])
    second = _train_run(
        track_id, video_id, training_frames=[2],
        mode="resume", resume_from=first.run_id,
    )
    first = attach_refinement_iteration(
        first,
        RefinementIterationInfo(
            iteration_index=0,
            training_mode="resume",
            resume_from_training_run_id=second.run_id,
            training_labels=_labels([1]),
        ),
    )

    exposure = validation_training_exposure((first, second), first.run_id, [0])

    assert exposure.qualification == VALIDATION_COMPARISON_UNKNOWN
    assert "cycle" in exposure.reasons[0]


# ---------------------------------------------------------------------------
# 入口：prepare_tracking_request 的 Resume 门
# ---------------------------------------------------------------------------


def _saved_session(tmp_path: Path) -> tuple[ProjectSession, object, Path]:
    session = ProjectSession.start(ProjectRepository(), name="Lineage")
    proj_dir = tmp_path / "proj"
    session.save_as(proj_dir)
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"dummy video")
    info = VideoStreamInfo(64, 48, 10.0, 20, "fake", "cfr")
    video, _ = session.register_external_video(video_file, info)
    track = session.add_track(video.video_id)
    for frame in range(4):
        session.mark_point(track.track_id, frame, 5.0 + frame, 6.0 + frame)
    return session, track, proj_dir


def _register_completed_train(
    session: ProjectSession, track, proj_dir: Path, *, training_frames,
    mode="restart", resume_from=None, with_iteration=True,
) -> TrackingRun:
    run = _train_run(
        track.track_id, track.video_id,
        training_frames=training_frames, mode=mode, resume_from=resume_from,
        with_iteration=with_iteration,
    )
    snapshot_rel = f"data/engines/{run.run_id}/snapshot.pt"
    snapshot_file = proj_dir / snapshot_rel
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_bytes(b"mock snapshot")
    run = mark_run_completed(run, model_snapshot=snapshot_rel)
    session.record_tracking_run(run)
    return run


def _activate_series(session: ProjectSession, track, frames) -> None:
    session.create_validation_series(track.track_id, f"series-{frames}", frames)


def _resume(session: ProjectSession, track, parent_run_id):
    return prepare_tracking_request(
        session, track.track_id, TrainingParams(epochs=1),
        training_mode="resume", resume_from_training_run_id=parent_run_id,
    )


def test_clean_resume_with_active_series_is_allowed(tmp_path: Path) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    parent = _register_completed_train(
        session, track, proj_dir, training_frames=[1, 2, 3])
    _activate_series(session, track, [0])

    request = _resume(session, track, parent.run_id)

    assert request.training_mode == "resume"


def test_resume_blocked_when_parent_trained_validation_frames(tmp_path: Path) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    parent = _register_completed_train(
        session, track, proj_dir, training_frames=[1, 2, 3])
    _activate_series(session, track, [1])

    with pytest.raises(ProjectSessionError) as excinfo:
        _resume(session, track, parent.run_id)

    message = str(excinfo.value)
    assert "Resume blocked" in message
    assert "[1]" in message
    assert str(parent.run_id)[:8] in message
    assert "Restart" in message


def test_resume_blocked_when_only_earlier_ancestor_is_contaminated(
    tmp_path: Path,
) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    grandparent = _register_completed_train(
        session, track, proj_dir, training_frames=[1, 2, 3])
    parent = _register_completed_train(
        session, track, proj_dir, training_frames=[0],  # 自己干净
        mode="resume", resume_from=grandparent.run_id,
    )
    _activate_series(session, track, [1])

    with pytest.raises(ProjectSessionError) as excinfo:
        _resume(session, track, parent.run_id)

    assert str(grandparent.run_id)[:8] in str(excinfo.value)


def test_changing_validation_series_requalifies_resume_source(tmp_path: Path) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    parent = _register_completed_train(
        session, track, proj_dir, training_frames=[1, 2, 3])

    disjoint = session.create_validation_series(track.track_id, "disjoint", [0])
    assert _resume(session, track, parent.run_id) is not None
    assert session.get_refinement_state(track.track_id).active_validation_series_id \
        == disjoint.series_id

    overlapping = session.create_validation_series(track.track_id, "overlapping", [2])
    assert session.get_refinement_state(track.track_id).active_validation_series_id \
        == overlapping.series_id
    with pytest.raises(ProjectSessionError):
        _resume(session, track, parent.run_id)


def test_legacy_parent_without_membership_blocks_resume(tmp_path: Path) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    legacy = _register_completed_train(
        session, track, proj_dir, training_frames=[1], with_iteration=False)
    _activate_series(session, track, [0])

    with pytest.raises(ProjectSessionError) as excinfo:
        _resume(session, track, legacy.run_id)

    assert "cannot be verified" in str(excinfo.value)


def test_missing_ancestor_in_registry_blocks_resume(tmp_path: Path) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    parent = _register_completed_train(
        session, track, proj_dir, training_frames=[0],
        mode="resume", resume_from=uuid4(),  # 祖先不在注册表
    )
    _activate_series(session, track, [1])

    with pytest.raises(ProjectSessionError):
        _resume(session, track, parent.run_id)


def test_restart_is_not_gated_by_lineage_exposure(tmp_path: Path) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    parent = _register_completed_train(
        session, track, proj_dir, training_frames=[1, 2, 3])
    _activate_series(session, track, [1])

    request = prepare_tracking_request(
        session, track.track_id, TrainingParams(epochs=1), training_mode="restart")

    assert request.training_mode == "restart"


def test_resume_without_active_series_is_not_gated(tmp_path: Path) -> None:
    session, track, proj_dir = _saved_session(tmp_path)
    parent = _register_completed_train(
        session, track, proj_dir, training_frames=[0, 1, 2])
    # 无活动验证集：没有独立比较要保护，resume 不受门限制

    request = _resume(session, track, parent.run_id)

    assert request.training_mode == "resume"
