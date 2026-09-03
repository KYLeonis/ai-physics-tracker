"""推理候选、结果激活、替换与清除事务测试（Phase 5.4 Slice 3 / ADR-0014）。"""

from dataclasses import asdict, replace
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.inference_job import (
    InferenceParams,
    read_inference_result,
    read_observation_exchange,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.refinement_history import (
    extract_prediction_summary,
    extract_refinement_state,
)
from ai_physics_tracker.application.tracking_job import (
    TrackingCandidate,
    TrackingRequest,
    prepare_tracking_candidate,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import add_video, create_project
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_completed,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _setup_session(tmp_path: Path) -> tuple[ProjectSession, Track, Video, Path]:
    repo = ProjectRepository()
    proj_dir = tmp_path / "test_proj"
    session = ProjectSession.start(repo, "Activation Test")
    session.save_as(proj_dir)

    video_file = tmp_path / "test_vid.mp4"
    video_file.write_bytes(b"dummy video data")

    info = VideoStreamInfo(
        width_px=100,
        height_px=100,
        fps_container=30.0,
        frame_count=20,
        container_format="mp4",
        timing_status="cfr",
    )
    video, _ = session.register_external_video(video_file, info)
    track = session.add_track(video.video_id, name="Test Track")
    return session, track, video, proj_dir


def _create_fake_infer_artifacts(
    proj_dir: Path,
    run: TrackingRun,
    video: Video,
    timeline: Timeline,
    point_frames: tuple[int, ...],
) -> tuple[Path, Path]:
    output_dir = proj_dir / "data" / "engines" / str(run.run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    now = utc_now()
    # 1. raw prediction
    pred_path = output_dir / "predictions.h5"
    pred_path.write_bytes(b"raw_hdf5_data")

    # 2. observations.json
    obs_path = output_dir / "observations.json"
    points = []
    for f in point_frames:
        t_s = f / 30.0
        p = TrackPoint(
            point_id=uuid4(),
            track_id=run.track_id,
            frame_index=f,
            time_s=t_s,
            pixel_x=50.0 + f,
            pixel_y=60.0 + f,
            source=run.engine,
            confidence=0.95,
            visibility="visible",
            status="active",
            source_detail=run.source_detail,
            created_at=now,
            modified_at=now,
        )
        points.append(asdict(p))

    obs_path.write_text(
        json.dumps(points, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return pred_path, obs_path


def test_prepare_tracking_candidate_does_not_mutate_observations(
    tmp_path: Path,
) -> None:
    session, track, video, proj_dir = _setup_session(tmp_path)
    timeline = next(t for t in session.project.timelines if t.video_id == video.video_id)

    # Add manual point at frame 2
    session.mark_point(track.track_id, 2, 20.0, 30.0)
    assert len(session.project.observations) == 1

    # Create completed infer run
    run = create_tracking_run(
        video_id=video.video_id,
        track_id=track.track_id,
        task_type="infer",
        engine="dlc",
        engine_version="3.0.1",
        config={"min_confidence": 0.5},
    )
    session.record_tracking_run(run)

    pred_path, obs_path = _create_fake_infer_artifacts(
        proj_dir, run, video, timeline, point_frames=(0, 1, 2, 3, 4)
    )
    st_pred = pred_path.stat()
    st_obs = obs_path.stat()

    completed_run = replace(
        run,
        status="completed",
        completed_at=utc_now(),
        extra_fields={
            "prediction_path": pred_path.relative_to(proj_dir).as_posix(),
            "observations_path": obs_path.relative_to(proj_dir).as_posix(),
            "prediction_file_info": [st_pred.st_size, st_pred.st_mtime_ns],
            "observations_file_info": [st_obs.st_size, st_obs.st_mtime_ns],
        },
    )

    # Write task-result.json
    res_path = proj_dir / "data" / "engines" / str(run.run_id) / "task-result.json"
    from ai_physics_tracker.infrastructure.project_serializer import tracking_run_to_payload

    res_path.write_text(
        json.dumps(
            {
                "run": tracking_run_to_payload(completed_run),
                "points_path": obs_path.relative_to(proj_dir).as_posix(),
            }
        ),
        encoding="utf-8",
    )

    video_file = Path(video.original_path)
    request = TrackingRequest(
        project=session.project,
        project_root=proj_dir,
        run=completed_run,
        parameters=InferenceParams(min_confidence=0.5),
        timing_detail="cfr",
        video_path=video_file,
        video_file_info=(video_file.stat().st_size, video_file.stat().st_mtime_ns),
    )

    # prepare candidate
    cand = prepare_tracking_candidate(session.project, request, res_path)
    assert cand.observations_changed is False
    assert cand.project.observations == session.project.observations

    # apply candidate
    applied = session.apply_tracking_candidate(cand)
    assert applied is True
    # Observations must remain UNTOUCHED! Only manual point exists
    assert len(session.project.observations) == 1
    # Run status is completed
    st_run = next(r for r in session.tracking_runs() if r.run_id == run.run_id)
    assert st_run.status == "completed"

    # Status shows "none" (not active)
    status, active_id, _ = session.get_track_activation_status(track.track_id)
    assert status == "none"
    assert active_id is None


def test_activate_replace_clear_lifecycle_and_undo_redo(
    tmp_path: Path,
) -> None:
    session, track, video, proj_dir = _setup_session(tmp_path)
    timeline = next(t for t in session.project.timelines if t.video_id == video.video_id)

    # Manual point at frame 2
    manual_pt = session.mark_point(track.track_id, 2, 20.0, 30.0)

    # Mark some dummy derived data to verify stale tracking
    now = utc_now()
    dummy_derived = DerivedData(
        derived_id=uuid4(),
        track_id=track.track_id,
        kind="world_position",
        input=DerivedInput(track_id=track.track_id),
        pipeline=(),
        frames=(2,),
        values=((20.0, 30.0),),
        payload_ref=None,
        unit="px",
        produced_by="test",
        created_at=now,
        status="valid",
    )
    session._commit_store(session._store, (dummy_derived,))
    assert session.project.derived[0].status == "valid"

    # 1. Prepare completed infer run 1
    run1 = create_tracking_run(video.video_id, track.track_id, "infer", engine="dlc")
    _, obs1 = _create_fake_infer_artifacts(
        proj_dir, run1, video, timeline, point_frames=(1, 2, 3)
    )
    run1 = replace(
        run1,
        status="completed",
        completed_at=utc_now(),
        extra_fields={
            "observations_path": obs1.relative_to(proj_dir).as_posix(),
            "observations_file_info": [obs1.stat().st_size, obs1.stat().st_mtime_ns],
        },
    )
    session.record_tracking_run(run1)

    # 2. ACTIVATE Run 1
    rec1 = session.activate_infer_run(track.track_id, run1.run_id)
    assert rec1.action == "activate"
    assert rec1.from_run_id is None
    assert rec1.to_run_id == run1.run_id
    assert rec1.point_count == 2  # frames 1 and 3
    assert rec1.manual_preserved_count == 1  # 操作时 active manual 点数（review M-1 统一语义）
    assert rec1.superseded_count == 1  # frame 2 的 AI 点被 manual 遮蔽

    status, active_id, _ = session.get_track_activation_status(track.track_id)
    assert status == "active"
    assert active_id == run1.run_id
    assert session.project.derived[0].status == "stale"

    # Check observations on track
    eff_points = session.effective_points(track.track_id)
    assert len(eff_points) == 3
    assert session.effective_point(track.track_id, 2) == manual_pt

    # Cannot activate again when already active
    with pytest.raises(ProjectSessionError, match="already has active AI observations"):
        session.activate_infer_run(track.track_id, run1.run_id)

    # 3. REPLACE with Run 2
    run2 = create_tracking_run(video.video_id, track.track_id, "infer", engine="dlc")
    _, obs2 = _create_fake_infer_artifacts(
        proj_dir, run2, video, timeline, point_frames=(1, 2, 3, 4, 5)
    )
    run2 = replace(
        run2,
        status="completed",
        completed_at=utc_now(),
        extra_fields={
            "observations_path": obs2.relative_to(proj_dir).as_posix(),
            "observations_file_info": [obs2.stat().st_size, obs2.stat().st_mtime_ns],
        },
    )
    session.record_tracking_run(run2)

    rec2 = session.replace_active_infer_run(track.track_id, run2.run_id)
    assert rec2.action == "replace"
    assert rec2.from_run_id == run1.run_id
    assert rec2.to_run_id == run2.run_id
    assert rec2.point_count == 4
    assert rec2.manual_preserved_count == 1  # 仍是那 1 个 manual 点（review M-1）
    assert rec2.superseded_count == 1  # frame 2 superseded by manual

    status2, active_id2, _ = session.get_track_activation_status(track.track_id)
    assert status2 == "active"
    assert active_id2 == run2.run_id
    assert len(session.effective_points(track.track_id)) == 5

    # 4. Deleting manual point restores superseded AI point of active run
    session.delete_active_manual_point(track.track_id, 2)
    eff_at_2 = session.effective_point(track.track_id, 2)
    assert eff_at_2 is not None
    assert eff_at_2.source == "dlc"
    assert eff_at_2.status == "active"

    # 5. CLEAR active AI observations
    rec3 = session.clear_active_ai_observations(track.track_id)
    assert rec3.action == "clear"
    assert rec3.from_run_id == run2.run_id
    assert rec3.to_run_id is None

    status3, active_id3, _ = session.get_track_activation_status(track.track_id)
    assert status3 == "none"
    assert active_id3 is None
    # Now there are no points on this track
    assert len(session.effective_points(track.track_id)) == 0

    # 6. UNDO/REDO verification
    # Undo Clear -> restores Run 2 active observations
    assert session.can_undo
    session.undo()
    assert session.get_track_activation_status(track.track_id)[0] == "active"
    assert session.get_track_activation_status(track.track_id)[1] == run2.run_id

    # Undo manual point deletion -> restores manual point at frame 2
    session.undo()
    assert session.effective_point(track.track_id, 2).source == "manual"

    # Undo Replace -> restores Run 1
    session.undo()
    assert session.get_track_activation_status(track.track_id)[1] == run1.run_id

    # Undo Activate -> restores no AI observations
    session.undo()
    assert session.get_track_activation_status(track.track_id)[0] == "none"
    assert len(session.effective_points(track.track_id)) == 1

    # Redo Activate
    assert session.can_redo
    session.redo()
    assert session.get_track_activation_status(track.track_id)[1] == run1.run_id


def test_activation_rejects_missing_or_tampered_artifacts(
    tmp_path: Path,
) -> None:
    session, track, video, proj_dir = _setup_session(tmp_path)
    timeline = next(t for t in session.project.timelines if t.video_id == video.video_id)

    run = create_tracking_run(video.video_id, track.track_id, "infer", engine="dlc")
    _, obs = _create_fake_infer_artifacts(
        proj_dir, run, video, timeline, point_frames=(1, 2)
    )
    st = obs.stat()
    run = replace(
        run,
        status="completed",
        completed_at=utc_now(),
        extra_fields={
            "observations_path": obs.relative_to(proj_dir).as_posix(),
            "observations_file_info": [st.st_size, st.st_mtime_ns],
        },
    )
    session.record_tracking_run(run)

    # 1. Tamper file size/mtime
    obs.write_text("tampered data", encoding="utf-8")
    with pytest.raises(ProjectSessionError, match="Observation artifact was modified"):
        session.activate_infer_run(track.track_id, run.run_id)

    # 2. File missing
    obs.unlink()
    with pytest.raises(ProjectSessionError, match="Observation artifact missing"):
        session.activate_infer_run(track.track_id, run.run_id)


def test_legacy_project_compatibility(tmp_path: Path) -> None:
    session, track, video, _ = _setup_session(tmp_path)
    now = utc_now()

    # Initially empty AI observations -> "none"
    st, active_id, _ = session.get_track_activation_status(track.track_id)
    assert st == "none"

    # Simulate legacy project: add AI observations without refinement_state_v1
    ai_point = TrackPoint(
        point_id=uuid4(),
        track_id=track.track_id,
        frame_index=1,
        time_s=1 / 30.0,
        pixel_x=50.0,
        pixel_y=50.0,
        source="dlc",
        confidence=0.9,
        visibility="visible",
        status="active",
        source_detail="infer-1",
        created_at=now,
        modified_at=now,
    )
    # Put into store
    session._store.replace_track_engine_points(track.track_id, (ai_point,))

    # Without matching run -> legacy_mixed
    st, active_id, _ = session.get_track_activation_status(track.track_id)
    assert st == "legacy_mixed"
    assert active_id is None

    # Register single matching infer run -> legacy_inferred
    matching_run = create_tracking_run(
        video.video_id,
        track.track_id,
        "infer",
        engine="dlc",
        source_detail="infer-1",
    )
    matching_run = mark_run_completed(matching_run)
    session.record_tracking_run(matching_run)

    st, active_id, _ = session.get_track_activation_status(track.track_id)
    assert st == "legacy_inferred"
    assert active_id == matching_run.run_id

    # Clear works on legacy project!
    rec = session.clear_active_ai_observations(track.track_id)
    assert rec.action == "clear"
    assert rec.from_run_id == matching_run.run_id
    assert session.get_track_activation_status(track.track_id)[0] == "none"


def test_activation_rejects_invalid_task_type_incomplete_or_cross_track(
    tmp_path: Path,
) -> None:
    session, track, video, _ = _setup_session(tmp_path)
    other_track = session.add_track(video.video_id, name="Other Track")

    # 1. Reject non-infer run (e.g. train)
    train_run = create_tracking_run(video.video_id, track.track_id, "train", engine="dlc")
    train_run = replace(train_run, status="completed", completed_at=utc_now())
    session.record_tracking_run(train_run)

    with pytest.raises(ProjectSessionError, match="is not an inference run"):
        session.activate_infer_run(track.track_id, train_run.run_id)

    # 2. Reject incomplete infer run (status != completed)
    pending_infer = create_tracking_run(video.video_id, track.track_id, "infer", engine="dlc")
    session.record_tracking_run(pending_infer)

    with pytest.raises(ProjectSessionError, match="is not completed"):
        session.activate_infer_run(track.track_id, pending_infer.run_id)

    # 3. Reject run belonging to another track
    other_infer = create_tracking_run(video.video_id, other_track.track_id, "infer", engine="dlc")
    other_infer = replace(other_infer, status="completed", completed_at=utc_now())
    session.record_tracking_run(other_infer)

    with pytest.raises(ProjectSessionError, match="does not belong to track"):
        session.activate_infer_run(track.track_id, other_infer.run_id)

    # 4. Reject clear when track has no active AI observations
    with pytest.raises(ProjectSessionError, match="has no active AI observations"):
        session.clear_active_ai_observations(track.track_id)


# ---------------------------------------------------------------------------
# 合并后复审（R2）——稳健性加固
# ---------------------------------------------------------------------------

class TestActivationHardening:
    def test_replace_without_active_result_rejected(self, tmp_path: Path):
        """ADR-0014：Replace 仅用于已有 AI 结果的 Track（review L-2）。"""
        session, track, video, proj_dir = _setup_session(tmp_path)
        timeline = next(t for t in session.project.timelines if t.video_id == video.video_id)
        run = create_tracking_run(video.video_id, track.track_id, "infer", engine="dlc")
        _proj, obs = _create_fake_infer_artifacts(proj_dir, run, video, timeline, point_frames=(1, 3))
        run = replace(run, status="completed", completed_at=utc_now(), extra_fields={
            "observations_path": obs.relative_to(proj_dir).as_posix(),
            "observations_file_info": [obs.stat().st_size, obs.stat().st_mtime_ns],
        })
        session.record_tracking_run(run)
        with pytest.raises(ProjectSessionError, match="no active AI result"):
            session.replace_active_infer_run(track.track_id, run.run_id)

    def test_corrupt_observation_artifact_wrapped_as_session_error(self, tmp_path: Path):
        """损坏产物统一转 ProjectSessionError，不裸抛解析异常（review L-1）。"""
        session, track, video, proj_dir = _setup_session(tmp_path)
        timeline = next(t for t in session.project.timelines if t.video_id == video.video_id)
        session.mark_point(track.track_id, 2, 20.0, 30.0)
        run = create_tracking_run(video.video_id, track.track_id, "infer", engine="dlc")
        _proj, obs = _create_fake_infer_artifacts(proj_dir, run, video, timeline, point_frames=(1, 3))
        obs.write_text("{corrupt", encoding="utf-8")
        run = replace(run, status="completed", completed_at=utc_now(), extra_fields={
            "observations_path": obs.relative_to(proj_dir).as_posix(),
            "observations_file_info": [obs.stat().st_size, obs.stat().st_mtime_ns],
        })
        session.record_tracking_run(run)
        with pytest.raises(ProjectSessionError, match="unreadable"):
            session.activate_infer_run(track.track_id, run.run_id)

    def test_empty_snapshot_series_dropped_on_deserialize(self):
        """全部快照非法的 series 反序列化为 None，不产生可激活的空集合（review L-4）。"""
        from ai_physics_tracker.application.refinement_history import (
            deserialize_validation_series,
        )

        raw = {"series_id": str(uuid4()), "name": "broken",
               "created_at": utc_now().isoformat(), "label_snapshots": [{"bad": 1}]}
        assert deserialize_validation_series(raw) is None
        assert deserialize_validation_series({"series_id": str(uuid4()), "name": "x",
                                              "created_at": utc_now().isoformat(),
                                              "label_snapshots": []}) is None
