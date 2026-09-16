"""P6R-04：Advisor 输入采集器的组合行为测试（Qt-free，Pre-Phase 6 stabilization）。

链路：Project / Session / TrackingRuns → production collector → AdvisorInput
→ recommendation。固定两条事实口径：
- timeline 取所选 Track 的真实 video_id（标注集中在 working zone 一部分时
  uncovered_zone_segments 必须为 True）；
- last_train_failed 表示最近一次相关训练的状态（OOM 失败后成功重训 → False）。
"""

import dataclasses
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from ai_physics_tracker.application.advisor_collection import collect_advisor_input
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.refinement_history import (
    RefinementIterationInfo,
    ValidationLabelSnapshot,
    attach_refinement_iteration,
)
from ai_physics_tracker.application.training_advisor import (
    ACTION_LABEL_MORE,
    ACTION_RESTART,
    recommend_training_action,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.tracking_run import (
    create_tracking_run,
    mark_run_completed,
    mark_run_failed,
    mark_run_running,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _labels(frames) -> tuple[ValidationLabelSnapshot, ...]:
    return tuple(
        ValidationLabelSnapshot(
            point_id=uuid4(), frame_index=f, pixel_x=1.0, pixel_y=2.0,
            modified_at=utc_now().isoformat(),
        )
        for f in frames
    )


def _session_with_clustered_labels(tmp_path: Path, *, dir_name: str = "proj"):
    """40 帧视频；manual 点只集中在 working zone 第一段（frames 0–2）。"""
    session = ProjectSession.start(ProjectRepository(), name="Advisor collection")
    proj_dir = tmp_path / dir_name
    session.save_as(proj_dir)
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"dummy video")
    info = VideoStreamInfo(64, 48, 10.0, 40, "fake", "cfr")
    video, _ = session.register_external_video(video_file, info)
    track = session.add_track(video.video_id)
    for frame in (0, 1, 2):
        session.mark_point(track.track_id, frame, 5.0 + frame, 6.0 + frame)
    return session, track, proj_dir


def _completed_train(session, track, proj_dir, *, training_frames, series_id,
                     val_rmse: float, created_at=None):
    import dataclasses

    run = create_tracking_run(track.video_id, track.track_id, "train", engine_version="mock")
    if created_at is not None:
        # 显式时间戳：Windows 时钟分辨率较粗，连续 utc_now() 可能相同（CI 实测）
        run = dataclasses.replace(run, created_at=created_at)
    snapshot_rel = f"data/engines/{run.run_id}/snapshot.pt"
    snapshot_file = proj_dir / snapshot_rel
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_bytes(b"weights")
    run = mark_run_completed(run, model_snapshot=snapshot_rel)
    run = attach_refinement_iteration(run, RefinementIterationInfo(
        iteration_index=0,
        validation_series_id=series_id,
        training_mode="restart",
        training_labels=_labels(training_frames),
    ))
    run = dataclasses.replace(run, extra_fields={
        **run.extra_fields,
        "evaluation": {"metrics": {"train_rmse": 4.0, "test_rmse": val_rmse}, "unit": "px"},
    })
    session.record_tracking_run(run)
    return run


def test_collector_reports_clustered_labels_oom_recovery_and_drives_recommendation(
    tmp_path: Path,
) -> None:
    session, track, proj_dir = _session_with_clustered_labels(tmp_path)
    series = session.create_validation_series(track.track_id, "fixed", [2])

    base = utc_now()
    # 第一轮：干净 restart，labels {0,1} 与验证帧 {2} 互斥
    _completed_train(session, track, proj_dir, training_frames=[0, 1],
                     series_id=series.series_id, val_rmse=5.00,
                     created_at=base - timedelta(seconds=30))

    # 一次 OOM 失败（此刻是最近一次相关训练）
    oom_run = dataclasses.replace(
        create_tracking_run(track.video_id, track.track_id, "train", engine_version="mock"),
        created_at=base - timedelta(seconds=10))
    session.record_tracking_run(oom_run)
    session.update_tracking_run(mark_run_running(oom_run))
    session.update_tracking_run(mark_run_failed(oom_run, "CUDA out of memory"))

    runs = session.tracking_runs()
    during_failure = collect_advisor_input(
        session, track.track_id, runs, has_active_task=False,
        requested_batch_size=8, requested_epochs=50)
    assert during_failure.last_train_failed
    assert during_failure.last_failure_is_oom
    # 标注只覆盖 working zone 第一段（P6R-04 timeline 修复的直接证据）
    assert during_failure.uncovered_zone_segments
    assert during_failure.recent_rounds[-1].comparison_qualification == "clean"

    oom_rec = recommend_training_action(during_failure)
    assert oom_rec.action == ACTION_RESTART
    assert oom_rec.batch_size == 4  # OOM 减半规则仍然生效

    # 之后成功重训：同 series 干净第二轮，validation RMSE 处于 plateau（+0.4%）
    _completed_train(session, track, proj_dir, training_frames=[0, 1],
                     series_id=series.series_id, val_rmse=5.02, created_at=base)

    runs = session.tracking_runs()
    recovered = collect_advisor_input(
        session, track.track_id, runs, has_active_task=False,
        requested_batch_size=8, requested_epochs=50)

    # P6R-04：成功训练之后不再报告"最近训练失败"
    assert not recovered.last_train_failed
    assert not recovered.last_failure_is_oom
    assert recovered.uncovered_zone_segments
    assert recovered.completed_train_runs == 2
    assert recovered.recent_rounds[-1].comparison_qualification == "clean"

    rec = recommend_training_action(recovered)
    assert rec.action == ACTION_LABEL_MORE  # plateau + 时间段缺口 → 补标注
    assert any("working zone" in e for e in rec.evidence)


def test_equal_created_at_tie_breaks_to_most_recently_registered(tmp_path: Path) -> None:
    """created_at 相同（时钟分辨率限制）时，按注册顺序取最新尝试。"""
    session, track, proj_dir = _session_with_clustered_labels(tmp_path)
    same_time = utc_now() - timedelta(seconds=5)

    completed = _completed_train(session, track, proj_dir, training_frames=[0, 1],
                                 series_id=uuid4(), val_rmse=5.0, created_at=same_time)
    failed = dataclasses.replace(
        create_tracking_run(track.video_id, track.track_id, "train", engine_version="mock"),
        created_at=same_time)
    session.record_tracking_run(failed)
    session.update_tracking_run(mark_run_failed(failed, "out of memory"))

    later_attempt_is_failure = collect_advisor_input(
        session, track.track_id, session.tracking_runs(), has_active_task=False,
        requested_batch_size=8, requested_epochs=50)
    assert later_attempt_is_failure.last_train_failed
    assert later_attempt_is_failure.last_failure_is_oom

    # 反序：失败在前、成功在后 → 不再报失败
    session2, track2, proj_dir2 = _session_with_clustered_labels(tmp_path, dir_name="proj2")
    failed_first = dataclasses.replace(
        create_tracking_run(track2.video_id, track2.track_id, "train", engine_version="mock"),
        created_at=same_time)
    session2.record_tracking_run(failed_first)
    session2.update_tracking_run(mark_run_failed(failed_first, "out of memory"))
    _completed_train(session2, track2, proj_dir2, training_frames=[0, 1],
                     series_id=uuid4(), val_rmse=5.0, created_at=same_time)

    recovered = collect_advisor_input(
        session2, track2.track_id, session2.tracking_runs(), has_active_task=False,
        requested_batch_size=8, requested_epochs=50)
    assert not recovered.last_train_failed


def test_changed_series_and_selected_source_gate_improvement_advice(tmp_path: Path) -> None:
    from ai_physics_tracker.application.training_advisor import ACTION_RESTART, ACTION_RESUME
    from ai_physics_tracker.application.tracking_job import prepare_tracking_request
    from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams

    session, track, proj_dir = _session_with_clustered_labels(tmp_path)
    series = session.create_validation_series(track.track_id, "A", [2])
    first = _completed_train(session, track, proj_dir, training_frames=[0, 1],
                             series_id=series.series_id, val_rmse=5.0)
    last = _completed_train(session, track, proj_dir, training_frames=[0, 1],
                            series_id=series.series_id, val_rmse=4.0)

    def advice(source=None):
        return recommend_training_action(collect_advisor_input(
            session, track.track_id, session.tracking_runs(), has_active_task=False,
            requested_batch_size=8, requested_epochs=50, resume_source_run_id=source,
        ))

    assert advice(last.run_id).action == ACTION_RESUME
    session.create_validation_series(track.track_id, "B", [1])
    assert advice(last.run_id).action == ACTION_RESTART
    # 保留老 A 的评价历史，但当前 B 下只让 first 模型有干净 lineage。
    clean_info = RefinementIterationInfo(
        iteration_index=0, validation_series_id=series.series_id,
        training_labels=_labels([0]),
    )
    session.update_tracking_run(attach_refinement_iteration(first, clean_info))
    assert advice(last.run_id).action == ACTION_RESTART  # 不能借用另一个模型的资格
    assert advice(first.run_id).action == ACTION_RESUME
    request = prepare_tracking_request(
        session, track.track_id, TrainingParams(epochs=1), training_mode="resume",
        resume_from_training_run_id=first.run_id,
    )
    assert request.resume_from_training_run_id == first.run_id
