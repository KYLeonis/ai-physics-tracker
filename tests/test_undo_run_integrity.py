"""P6R-01：Undo/Redo 与 Track/TrackingRun 引用的一致事务（Pre-Phase 6 stabilization）。

政策（docs/status/pre-phase6-stabilization-plan.md）：
- 撤销/重做恢复被删 Track 时，其 TrackingRun 一并从快照恢复；
- undo 越过"快照之外登记的 run 依赖"时原子拒绝，五项状态（Project、TrackStore、
  Undo 栈、Redo 栈、run registry）完全不变；
- 存续 Track 的 run 生命周期不被 Undo/Redo 回滚。
"""

from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.tracking_run import (
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


def _saved_session_with_track(tmp_path: Path) -> tuple[ProjectSession, object, Path]:
    """带 project_root 的会话（激活/保存重开路径需要已落盘目录）。"""

    session = ProjectSession.start(ProjectRepository(), name="Undo integrity")
    proj_dir = tmp_path / "proj"
    session.save_as(proj_dir)
    video, _ = session.register_external_video(tmp_path / "clip.mp4", _info(frame_count=20))
    track = session.add_track(video.video_id)
    return session, track, proj_dir


def _fake_infer_artifacts(
    proj_dir: Path, run, point_frames: tuple[int, ...]
) -> None:
    output_dir = proj_dir / "data" / "engines" / str(run.run_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    points = []
    for frame in point_frames:
        point = TrackPoint(
            point_id=uuid4(),
            track_id=run.track_id,
            frame_index=frame,
            time_s=frame / 10.0,
            pixel_x=10.0 + frame,
            pixel_y=20.0 + frame,
            source=run.engine,
            confidence=0.95,
            visibility="visible",
            status="active",
            source_detail=run.source_detail,
            created_at=now,
            modified_at=now,
        )
        points.append(asdict(point))
    (output_dir / "observations.json").write_text(
        json.dumps(points, ensure_ascii=False, default=str), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 复现 A：新建 Track + 登记 run 后，撤销不可越过（原子拒绝，无半提交）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["pending", "running", "completed"])
def test_undo_of_track_creation_with_run_dependency_is_atomic_rejection(
    tmp_path: Path, status: str
) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    for frame in range(4):
        session.mark_point(track.track_id, frame, 1.0, 1.0)
    run = create_tracking_run(video.video_id, track.track_id, "train", engine_version="mock")
    if status in {"running", "completed"}:
        session.record_tracking_run(run)
        session.update_tracking_run(mark_run_running(run))
        if status == "completed":
            session.update_tracking_run(
                mark_run_completed(run, model_snapshot="data/engines/fake/snap.pt")
            )
    else:
        session.record_tracking_run(run)

    for _ in range(4):
        assert session.undo()  # 撤销 4 次标注本身合法，run 注册表保持

    undo_depth = len(session._undo_stack)
    redo_depth = len(session._redo_stack)
    project_before = session.project
    store_tracks_before = session.tracks

    with pytest.raises(ProjectSessionError):
        session.undo()  # 撤销 add_track 越过 run 依赖 → 拒绝

    # 拒绝后五项不变量：Project、TrackStore、Undo 栈、Redo 栈、run registry
    assert session.project is project_before
    assert session.tracks == store_tracks_before
    assert len(session._undo_stack) == undo_depth
    assert len(session._redo_stack) == redo_depth
    assert [r.run_id for r in session.project.tracking_runs] == [run.run_id]

    # 拒绝不毒化会话：redo 仍可前进
    assert session.redo()
    assert len(session.manual_points(track.track_id)) == 1


def test_undo_of_track_creation_without_runs_still_succeeds(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 1.0)

    assert session.undo()
    assert session.undo()

    assert session.tracks == ()
    assert session.project.tracking_runs == ()
    assert not session.can_undo


# ---------------------------------------------------------------------------
# 复现 B：删除带 active infer run 的 Track 后 Undo，恢复引用一致性并可保存重开
# ---------------------------------------------------------------------------


def _activated_track_session(
    tmp_path: Path,
) -> tuple[ProjectSession, object, object, Path]:
    session, track, proj_dir = _saved_session_with_track(tmp_path)
    video = next(v for v in session.project.videos if v.video_id == track.video_id)
    run = create_tracking_run(
        video.video_id, track.track_id, "infer", engine="dlc", engine_version="3.0.1"
    )
    session.record_tracking_run(run)
    _fake_infer_artifacts(proj_dir, run, point_frames=(0, 1, 2))
    session.update_tracking_run(mark_run_completed(run))
    session.activate_infer_run(track.track_id, run.run_id)
    return session, track, run, proj_dir


def test_undo_remove_track_restores_runs_and_active_pointer_and_survives_reopen(
    tmp_path: Path,
) -> None:
    session, track, run, proj_dir = _activated_track_session(tmp_path)

    session.remove_track(track.track_id)
    assert session.project.tracking_runs == ()

    assert session.undo()

    status, active_run_id, _ = session.get_track_activation_status(track.track_id)
    assert status == "active"
    assert active_run_id == run.run_id
    assert [r.run_id for r in session.project.tracking_runs] == [run.run_id]
    assert len(session.effective_points(track.track_id)) == 3

    session.save()
    reopened = ProjectSession.load(ProjectRepository(), proj_dir)
    reopened_status, reopened_active, _ = reopened.get_track_activation_status(track.track_id)
    assert reopened_status == "active"
    assert reopened_active == run.run_id
    assert len(reopened.project.tracking_runs) == 1


def test_redo_after_undo_remove_track_removes_track_and_runs_again(
    tmp_path: Path,
) -> None:
    session, track, run, _proj_dir = _activated_track_session(tmp_path)

    session.remove_track(track.track_id)
    assert session.undo()
    assert session.redo()

    assert session.tracks == ()
    assert [r.run_id for r in session.project.tracking_runs] == []
    # 恢复↔删除可重复往返，引用始终可解析
    assert session.undo()
    assert [r.run_id for r in session.project.tracking_runs] == [run.run_id]


# ---------------------------------------------------------------------------
# 无关 run 的生命周期不被 Undo/Redo 回滚；run 登记清空 redo
# ---------------------------------------------------------------------------


def test_undo_keeps_unrelated_run_lifecycle_progress(tmp_path: Path) -> None:
    session = _session_with_video(tmp_path)
    video = session.project.videos[0]
    first = session.add_track(video.video_id)
    second = session.add_track(video.video_id)
    session.mark_point(first.track_id, 0, 1.0, 1.0)

    unrelated = create_tracking_run(video.video_id, second.track_id, "train",
                                    engine_version="mock")
    session.record_tracking_run(unrelated)
    session.update_tracking_run(mark_run_running(unrelated))
    session.mark_point(first.track_id, 1, 2.0, 2.0)
    session.update_tracking_run(
        mark_run_completed(unrelated, model_snapshot="data/engines/fake/snap.pt")
    )

    assert session.undo()  # 撤销第二条标注，second 的 run 状态不被回滚

    (kept,) = session.project.tracking_runs
    assert kept.run_id == unrelated.run_id
    assert kept.status == "completed"
    assert session.redo()
    (kept,) = session.project.tracking_runs
    assert kept.status == "completed"


def test_recording_a_run_invalidates_redo_navigation(tmp_path: Path) -> None:
    session = _saved_session_with_track(tmp_path)[0]
    track = session.tracks[0]
    session.mark_point(track.track_id, 0, 1.0, 1.0)

    assert session.undo()
    assert session.can_redo

    session.record_tracking_run(
        create_tracking_run(track.video_id, track.track_id, "train", engine_version="mock")
    )

    # 新 run 登记是前向写入：redo 不能越过它恢复"删除前的世界"
    assert not session.can_redo


def test_run_only_progression_during_save_keeps_no_ghost_undo_step(
    tmp_path: Path,
) -> None:
    # stabilization R1 F2：保存窗口期间仅 run 状态演进（pending→running）不产生
    # 空撤销步；真实数据变化仍保留一次回到保存点的撤销。
    session, track, _proj_dir = _saved_session_with_track(tmp_path)
    run = create_tracking_run(track.video_id, track.track_id, "train", engine_version="mock")
    session.record_tracking_run(run)
    saved = session.detached()
    saved.save()
    # 保存期间后台仅推进 run 状态
    session.update_tracking_run(mark_run_running(run))

    session.accept_saved_snapshot(saved)

    assert not session.can_undo  # run-only 变化不再是"保存期间的新数据"

    # 对照：保存期间发生真实数据编辑（新标注）→ 保留一个撤销步
    session.mark_point(track.track_id, 1, 3.0, 4.0)
    saved2 = session.detached()
    saved2.save()
    session.mark_point(track.track_id, 2, 5.0, 6.0)
    session.accept_saved_snapshot(saved2)
    assert session.can_undo
    assert session.undo()
    assert len(session.manual_points(track.track_id)) == 1
