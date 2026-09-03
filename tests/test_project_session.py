"""与 Qt 无关的 ProjectSession 标注会话测试。

验证 phase2-requirements.md §2 R5：manual TrackPoint 写入语义
（time_s 冻结、manual last-wins、superseded 遮蔽）与 dirty 生命周期。
"""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    ReviewCandidate,
    ReviewPredictionSnapshot,
    SuggestedFrameReviewState,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_completed,
    mark_run_running,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _info(fps: float = 10.0, frame_count: int = 5) -> VideoStreamInfo:
    return VideoStreamInfo(64, 48, fps, frame_count, "fake", "cfr")


def _session_with_video(tmp_path: Path) -> ProjectSession:
    session = ProjectSession.start(ProjectRepository())
    session.register_external_video(tmp_path / "clip.mp4", _info())
    return session


def test_register_external_video_adds_video_and_timeline(tmp_path: Path) -> None:
    session = ProjectSession.start(ProjectRepository())

    video, timeline = session.register_external_video(
        tmp_path / "clip.mp4", _info(fps=24.0, frame_count=30)
    )

    assert session.project.videos == (video,)
    assert session.project.timelines == (timeline,)
    assert video.original_path == str(tmp_path / "clip.mp4")
    assert video.file_path is None
    assert timeline.fps_nominal == pytest.approx(24.0)
    assert session.is_dirty


def test_add_track_auto_names_and_rotates_palette(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    first = session.add_track(video.video_id)
    second = session.add_track(video.video_id)

    assert first.name == "Track 1"
    assert second.name == "Track 2"
    assert first.color != second.color
    assert session.tracks == (first, second)
    assert session.project.tracks == (first, second)


def test_add_track_respects_explicit_unique_name(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    session.add_track(video.video_id)

    named = session.add_track(video.video_id, name=" Pendulum bob ")

    assert named.name == "Pendulum bob"


def test_mark_point_freezes_time_via_timeline_and_manual_semantics(
    tmp_path: Path,
) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    point = session.mark_point(track.track_id, 2, 31.5, 24.0)

    assert point.source == "manual"
    assert point.confidence is None
    assert point.status == "active"
    assert point.visibility == "visible"  # data-model.md §3.5 manual 缺省
    assert point.time_s == pytest.approx(0.2, abs=1e-12)  # 2 / 10 fps
    assert session.project.observations == (point,)


def test_mark_point_same_frame_last_wins_deletes_old_manual(
    tmp_path: Path,
) -> None:
    # data-model.md §4.2：旧 manual 点硬删除；引擎点保留为 superseded
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    first = session.mark_point(track.track_id, 1, 10.0, 10.0)
    second = session.mark_point(track.track_id, 1, 42.0, 21.0)

    stored = session.project.observations
    assert len(stored) == 1
    assert stored[0].point_id == second.point_id
    assert first.point_id != second.point_id
    assert session.effective_point(track.track_id, 1) == second
    assert session.manual_points(track.track_id) == (second,)


def test_remove_track_cascades_observations(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)

    session.remove_track(track.track_id)

    assert session.tracks == ()
    assert session.project.observations == ()
    with pytest.raises(ProjectSessionError):
        session.mark_point(track.track_id, 0, 2.0, 2.0)


def test_remove_track_with_runs_succeeds_and_undo_keeps_runs_deleted(
    tmp_path: Path,
) -> None:
    # review F1 回归：带 TrackingRun 的 track 删除不再被聚合校验拒绝；
    # undo 恢复 track/观测（数据层），run 注册表是审计日志、不进撤销快照。
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)
    session.record_tracking_run(
        create_tracking_run(
            video.video_id, track.track_id, "train", engine_version="3.0.1-mock"
        )
    )

    session.remove_track(track.track_id)

    assert session.tracks == ()
    assert session.project.observations == ()
    assert session.project.tracking_runs == ()

    assert session.undo()

    assert session.tracks == (track,)
    assert len(session.project.observations) == 1
    assert session.project.tracking_runs == ()


def test_detached_snapshot_is_isolated_from_subsequent_writes(
    tmp_path: Path,
) -> None:
    # review F5：detached 去除 deepcopy 后，隔离性由"frozen + replace()"契约
    # 保证；本测试固定该契约——任何一侧的原地修改都会在这里暴露。
    from copy import deepcopy

    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)
    snapshot = session.detached()
    reference = deepcopy(snapshot.project)

    session.mark_point(track.track_id, 1, 2.0, 3.0)
    session.add_calibration(
        video_id=video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(10.0, 0.0),
        known_length=1.0,
    )
    session.record_tracking_run(
        create_tracking_run(
            video.video_id, track.track_id, "train", engine_version="3.0.1-mock"
        )
    )
    session.update_view_state({"frame_index": 7})

    assert snapshot.project == reference

    snapshot.update_view_state({"frame_index": 9})
    workflow = session.project.ui_state.get("workflow", {})
    assert workflow.get("frame_index") == 7


def test_detached_shares_frozen_project_without_copying(tmp_path: Path) -> None:
    # review F5 实现契约：detached 必须共享不可变结构（O(1)）。
    # 退化回 deepcopy 会让 GUI 线程上的成本随观测数线性增长。
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)

    snapshot = session.detached()

    assert snapshot._project is session._project
    assert snapshot._saved_project is session._saved_project


def test_dirty_lifecycle_across_save_roundtrip(tmp_path: Path) -> None:
    repository = ProjectRepository()
    root = tmp_path / "proj"
    root.mkdir()
    session = ProjectSession.start(repository, name="Pendulum run 1")
    video, _timeline = session.register_external_video(
        tmp_path / "clip.mp4", _info()
    )
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 5.0, 6.0)
    assert session.is_dirty

    with pytest.raises(ProjectSessionError):
        ProjectSession.start(repository).save()  # 无根目录不能保存

    session._project_root = root  # 测试直接注入根目录；2.4 提供 Save As UI
    saved = session.save()

    assert not session.is_dirty
    assert saved.tracks == session.tracks

    reloaded = repository.load(root)
    assert reloaded.tracks == session.tracks
    assert reloaded.observations == session.project.observations
    assert reloaded.observations[0].pixel_x == pytest.approx(5.0)


def test_mark_point_unknown_track_reports_error(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    from uuid import uuid4

    with pytest.raises(ProjectSessionError):
        session.mark_point(uuid4(), 0, 1.0, 1.0)


def test_undo_restores_point_replaced_by_last_wins(tmp_path: Path) -> None:
    # last-wins 硬删旧 manual 点；undo 必须能恢复被替换的旧点
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    session.mark_point(track.track_id, 1, 10.0, 10.0)
    session.mark_point(track.track_id, 1, 42.0, 21.0)
    assert len(session.project.observations) == 1

    assert session.undo()

    points = session.manual_points(track.track_id)
    assert len(points) == 1
    assert (points[0].pixel_x, points[0].pixel_y) == (10.0, 10.0)

    assert session.redo()

    points = session.manual_points(track.track_id)
    assert (points[0].pixel_x, points[0].pixel_y) == (42.0, 21.0)


def test_undo_add_track_and_delete_track(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    assert session.undo()
    assert session.tracks == ()

    assert session.redo()
    assert session.tracks == (track,)

    session.mark_point(track.track_id, 0, 5.0, 5.0)
    session.remove_track(track.track_id)
    assert session.tracks == ()

    assert session.undo()  # 恢复删除
    assert session.tracks == (track,)
    assert len(session.project.observations) == 1


def test_undo_stack_is_limited_and_save_clears_it(tmp_path: Path) -> None:
    from ai_physics_tracker.application.project_session import UNDO_STACK_LIMIT

    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    for step in range(UNDO_STACK_LIMIT + 5):
        session.mark_point(track.track_id, step % 5, 1.0, 1.0)  # 合成视频 5 帧

    # 栈深限制：最早的 mark（add_track 之后）已不可撤销
    for _ in range(UNDO_STACK_LIMIT):
        assert session.undo()
    assert not session.can_undo

    session._project_root = tmp_path  # 测试注入根
    session.save()
    assert not session.can_undo and not session.can_redo


def test_new_write_clears_redo_stack(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)

    session.mark_point(track.track_id, 0, 1.0, 1.0)
    assert session.undo()
    assert session.can_redo

    session.mark_point(track.track_id, 1, 2.0, 2.0)  # 分支：旧 redo 作废

    assert not session.can_redo


def test_add_calibration_creates_and_activates_calibration(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(10.0, 20.0),
        scale_end_2_px=(110.0, 20.0),
        known_length=1.0,
        unit="m",
    )

    assert cal.name == "Calibration 1"
    assert cal.known_length == 1.0
    assert cal.unit == "m"
    assert session.calibrations == (cal,)
    assert session.active_calibration(video.video_id) == cal
    assert session.project.active_calibration_by_video == {video.video_id: cal.calibration_id}
    assert session.is_dirty


def test_add_calibration_auto_names_and_custom_name(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal1 = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(50.0, 0.0),
        known_length=0.5,
        unit="m",
    )
    cal2 = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=100.0,
        unit="cm",
        name="Ruler 1m",
    )

    assert cal1.name == "Calibration 1"
    assert cal2.name == "Ruler 1m"
    assert session.active_calibration(video.video_id) == cal2


def test_add_calibration_invalid_params_raises(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    with pytest.raises(ProjectSessionError):
        session.add_calibration(
            video.video_id,
            scale_end_1_px=(10.0, 10.0),
            scale_end_2_px=(10.0, 10.0),  # 重合点
            known_length=1.0,
        )

    with pytest.raises(ProjectSessionError):
        session.add_calibration(
            video.video_id,
            scale_end_1_px=(0.0, 0.0),
            scale_end_2_px=(10.0, 10.0),
            known_length=-5.0,  # 负长度
        )


def test_remove_calibration_and_set_active(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
    )
    assert session.active_calibration(video.video_id) == cal

    session.set_active_calibration(video.video_id, None)
    assert session.active_calibration(video.video_id) is None

    session.set_active_calibration(video.video_id, cal.calibration_id)
    assert session.active_calibration(video.video_id) == cal

    session.remove_calibration(cal.calibration_id)
    assert session.calibrations == ()
    assert session.active_calibration(video.video_id) is None


def test_update_calibration_modifies_origin_and_rotation(tmp_path: Path) -> None:
    from dataclasses import replace

    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
    )

    updated_cal = replace(cal, origin_px=(10.0, 40.0), rotation_deg=45.0)
    session.update_calibration(updated_cal)

    active = session.active_calibration(video.video_id)
    assert active is not None
    assert active.origin_px == (10.0, 40.0)
    assert active.rotation_deg == 45.0


def test_undo_redo_calibration_operations(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]

    cal = session.add_calibration(
        video.video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(100.0, 0.0),
        known_length=1.0,
        unit="m",
    )

    assert session.undo()
    assert session.calibrations == ()
    assert session.active_calibration(video.video_id) is None

    assert session.redo()
    assert session.calibrations == (cal,)
    assert session.active_calibration(video.video_id) == cal

    session.remove_calibration(cal.calibration_id)
    assert session.calibrations == ()

    assert session.undo()
    assert session.calibrations == (cal,)
    assert session.active_calibration(video.video_id) == cal


def _session_with_completed_infer_and_review_batch(
    tmp_path: Path,
) -> tuple[ProjectSession, Track, TrackingRun]:
    session = _session_with_video(tmp_path)
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

    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(pixel_x=10.0, pixel_y=20.0, confidence=0.7),
        components={"uncertainty": 0.3},
        raw_components={"uncertainty": 0.3},
        reasons=("low_confidence",),
        total_score=0.8,
    )
    c2 = ReviewCandidate(
        frame_index=2,
        prediction=ReviewPredictionSnapshot(pixel_x=12.0, pixel_y=22.0, confidence=0.5),
        components={"jump": 0.8},
        raw_components={"jump": 3.0},
        reasons=("jump_outlier",),
        total_score=0.9,
    )
    batch = ActiveReviewBatch(request_id=uuid4(), params_snapshot={"top_n": 2}, candidates=(c1, c2))
    session.set_active_review_batch(completed_run.run_id, batch)
    return session, track, completed_run


def test_accept_and_skip_suggested_frame_records_disposition_without_creating_points(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)
    assert session.project.observations == ()

    session.accept_suggested_frame(run.run_id, 1)
    session.skip_suggested_frame(run.run_id, 2)

    # AC-5: Accept/Skip do NOT create TrackPoints
    assert session.project.observations == ()
    assert session.is_dirty

    summary = session.get_review_summary(run.run_id)
    assert summary.total_candidates == 2
    assert summary.accepted_count == 1
    assert summary.skipped_count == 1
    assert summary.corrected_count == 0
    assert summary.pending_count == 0
    assert summary.total_reviewed == 2

    rev = session.get_suggested_frame_review(run.run_id)
    assert rev is not None
    assert rev.reviewed_frames[1].disposition == "accepted"
    assert rev.reviewed_frames[1].manual_point_id is None
    assert rev.reviewed_frames[2].disposition == "skipped"
    assert rev.reviewed_frames[2].manual_point_id is None


def test_correct_suggested_frame_atomically_adds_manual_point_and_records_disposition(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)

    point = session.correct_suggested_frame(run.run_id, 1, 15.0, 25.0)

    assert isinstance(point, TrackPoint)
    assert point.frame_index == 1
    assert point.pixel_x == 15.0
    assert point.pixel_y == 25.0
    assert point.source == "manual"
    assert point.status == "active"
    assert session.project.observations == (point,)
    assert session.is_dirty

    rev = session.get_suggested_frame_review(run.run_id)
    assert rev is not None
    assert rev.reviewed_frames[1].disposition == "corrected"
    assert rev.reviewed_frames[1].manual_point_id == point.point_id
    assert rev.reviewed_frames[1].prediction == ReviewPredictionSnapshot(10.0, 20.0, 0.7)

    summary = session.get_review_summary(run.run_id)
    assert summary.corrected_count == 1
    assert summary.pending_count == 1


def test_correct_suggested_frame_supersedes_engine_point_and_records_prediction_provenance(
    tmp_path: Path,
) -> None:
    session = _session_with_video(tmp_path)
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

    now = utc_now()
    engine_pt = TrackPoint(
        point_id=uuid4(),
        track_id=track.track_id,
        frame_index=1,
        time_s=0.1,
        pixel_x=10.0,
        pixel_y=20.0,
        source="dlc",
        source_detail="test-infer",
        confidence=0.7,
        visibility="visible",
        status="active",
        created_at=now,
        modified_at=now,
    )
    session.import_engine_points((engine_pt,), completed_run)

    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(pixel_x=10.0, pixel_y=20.0, confidence=0.7),
        components={"uncertainty": 0.3},
        raw_components={"uncertainty": 0.3},
        reasons=("low_confidence",),
        total_score=0.8,
    )
    batch = ActiveReviewBatch(request_id=uuid4(), params_snapshot={"top_n": 1}, candidates=(c1,))
    session.set_active_review_batch(completed_run.run_id, batch)

    assert session.effective_point(track.track_id, 1) == engine_pt

    # Correct frame 1
    correct_pt = session.correct_suggested_frame(completed_run.run_id, 1, 14.0, 24.0)

    # Engine point superseded by manual last-wins
    obs = {p.point_id: p for p in session.project.observations}
    assert obs[engine_pt.point_id].status == "superseded"
    assert obs[engine_pt.point_id].superseded_by == correct_pt.point_id
    assert session.effective_point(track.track_id, 1) == correct_pt


def test_delete_active_manual_point_removes_point_and_restores_superseded_ai_point(
    tmp_path: Path,
) -> None:
    session = _session_with_video(tmp_path)
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

    now = utc_now()
    engine_pt = TrackPoint(
        point_id=uuid4(),
        track_id=track.track_id,
        frame_index=1,
        time_s=0.1,
        pixel_x=10.0,
        pixel_y=20.0,
        source="dlc",
        source_detail="test-infer",
        confidence=0.7,
        visibility="visible",
        status="active",
        created_at=now,
        modified_at=now,
    )
    session.import_engine_points((engine_pt,), completed_run)

    # Annotate regular manual point
    manual_pt = session.mark_point(track.track_id, 1, 15.0, 25.0)
    assert session.effective_point(track.track_id, 1) == manual_pt

    # Delete active manual point
    deleted = session.delete_active_manual_point(track.track_id, 1)
    assert deleted.point_id == manual_pt.point_id

    # Observation deleted, engine point restored
    assert len(session.project.observations) == 1
    restored = session.project.observations[0]
    assert restored.point_id == engine_pt.point_id
    assert restored.status == "active"
    assert restored.superseded_by is None
    assert session.effective_point(track.track_id, 1) == restored


def test_delete_active_manual_point_from_correction_reverts_candidate_to_pending(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)

    session.correct_suggested_frame(run.run_id, 1, 15.0, 25.0)
    assert session.get_review_summary(run.run_id).corrected_count == 1

    session.delete_active_manual_point(track.track_id, 1)

    assert session.project.observations == ()
    summary = session.get_review_summary(run.run_id)
    assert summary.corrected_count == 0
    assert summary.pending_count == 2
    rev = session.get_suggested_frame_review(run.run_id)
    assert rev is not None
    assert 1 not in rev.reviewed_frames


def test_delete_active_manual_point_fails_if_no_manual_point(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)
    with pytest.raises(ProjectSessionError, match="No active manual point"):
        session.delete_active_manual_point(track.track_id, 1)


def test_undo_redo_accept_and_skip(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)

    session.accept_suggested_frame(run.run_id, 1)
    session.skip_suggested_frame(run.run_id, 2)

    assert session.get_review_summary(run.run_id).accepted_count == 1
    assert session.get_review_summary(run.run_id).skipped_count == 1

    # Undo skip
    assert session.undo()
    assert session.get_review_summary(run.run_id).accepted_count == 1
    assert session.get_review_summary(run.run_id).skipped_count == 0
    assert session.get_review_summary(run.run_id).pending_count == 1

    # Undo accept
    assert session.undo()
    assert session.get_review_summary(run.run_id).accepted_count == 0
    assert session.get_review_summary(run.run_id).pending_count == 2

    # Redo accept
    assert session.redo()
    assert session.get_review_summary(run.run_id).accepted_count == 1

    # Redo skip
    assert session.redo()
    assert session.get_review_summary(run.run_id).accepted_count == 1
    assert session.get_review_summary(run.run_id).skipped_count == 1


def test_undo_redo_correct_restores_both_manual_point_and_review_state_atomically(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)

    point = session.correct_suggested_frame(run.run_id, 1, 15.0, 25.0)
    assert len(session.project.observations) == 1
    assert session.get_review_summary(run.run_id).corrected_count == 1

    # Undo Correct
    assert session.undo()
    assert session.project.observations == ()
    assert session.get_review_summary(run.run_id).corrected_count == 0
    assert session.get_review_summary(run.run_id).pending_count == 2

    # Redo Correct
    assert session.redo()
    assert session.project.observations == (point,)
    assert session.get_review_summary(run.run_id).corrected_count == 1


def test_undo_redo_delete_manual_point_restores_point_and_review_state(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)

    point = session.correct_suggested_frame(run.run_id, 1, 15.0, 25.0)
    session.delete_active_manual_point(track.track_id, 1)
    assert session.project.observations == ()
    assert session.get_review_summary(run.run_id).corrected_count == 0

    # Undo Delete -> point restored, disposition restored to corrected
    assert session.undo()
    assert session.project.observations == (point,)
    assert session.get_review_summary(run.run_id).corrected_count == 1

    # Redo Delete -> point deleted again, disposition reverted to pending
    assert session.redo()
    assert session.project.observations == ()
    assert session.get_review_summary(run.run_id).corrected_count == 0


def test_undo_does_not_rollback_unrelated_tracking_runs_or_background_progress(
    tmp_path: Path,
) -> None:
    session, track, run1 = _session_with_completed_infer_and_review_batch(tmp_path)

    run2 = mark_run_running(
        create_tracking_run(
            run1.video_id,
            track.track_id,
            "train",
            engine="dlc",
            engine_version="3.0.1",
            source_detail="test-train",
        )
    )
    session.record_tracking_run(run2)

    session.accept_suggested_frame(run1.run_id, 1)

    completed_run2 = mark_run_completed(run2)
    session.update_tracking_run(completed_run2)
    assert next(r for r in session.tracking_runs() if r.run_id == run2.run_id).status == "completed"

    assert session.undo()
    assert session.get_review_summary(run1.run_id).accepted_count == 0

    # run2 status MUST remain completed
    assert next(r for r in session.tracking_runs() if r.run_id == run2.run_id).status == "completed"


def test_review_actions_mark_session_dirty_and_save_clears_dirty_and_undo(
    tmp_path: Path,
) -> None:
    session, track, run = _session_with_completed_infer_and_review_batch(tmp_path)

    project_dir = tmp_path / "saved_proj"
    session.save_as(project_dir)
    assert not session.is_dirty
    assert not session.can_undo

    session.accept_suggested_frame(run.run_id, 1)
    assert session.is_dirty
    assert session.can_undo

    assert session.undo()
    assert not session.is_dirty

    session.accept_suggested_frame(run.run_id, 1)
    session.save()
    assert not session.is_dirty
    assert not session.can_undo


