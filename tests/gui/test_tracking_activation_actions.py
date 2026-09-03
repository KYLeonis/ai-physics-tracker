"""TrackingActions 的结果激活、替换、清除与固定验证集管理 GUI 测试（Phase 5.4 Slice 4）。"""

from dataclasses import asdict, replace
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PySide6.QtWidgets import QMessageBox

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.tracking_run import TrackingRun, create_tracking_run
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.gui.validation_dialog import ManageValidationDialog
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from tests.gui.test_tracking_actions import _FakeRunner, _StaticTimingProbe, _opened_window


def _create_fake_completed_run(
    session,
    track_id: UUID,
    video_id: UUID,
    point_frames: tuple[int, ...],
) -> TrackingRun:
    root = session.project_root
    run = create_tracking_run(
        video_id=video_id,
        track_id=track_id,
        task_type="infer",
        engine="dlc",
        engine_version="3.0.1",
        source_detail="test-engine",
    )
    folder = root / "data" / "engines" / str(run.run_id)
    folder.mkdir(parents=True, exist_ok=True)

    obs_path = folder / "observations.json"
    points = []
    now = utc_now()
    for f in point_frames:
        pt = TrackPoint(
            point_id=uuid4(),
            track_id=track_id,
            frame_index=f,
            time_s=f / 10.0,
            pixel_x=50.0 + f,
            pixel_y=60.0 + f,
            source="dlc",
            confidence=0.95,
            visibility="visible",
            status="active",
            source_detail="test-engine",
            created_at=now,
            modified_at=now,
        )
        points.append(asdict(pt))

    obs_path.write_text(json.dumps(points, ensure_ascii=False, default=str), encoding="utf-8")
    st = obs_path.stat()

    completed_run = replace(
        run,
        status="completed",
        completed_at=now,
        extra_fields={
            "observations_path": obs_path.relative_to(root).as_posix(),
            "observations_file_info": [st.st_size, st.st_mtime_ns],
        },
    )
    session.record_tracking_run(completed_run)
    return completed_run


def test_activate_and_replace_with_confirmation_and_cancellation(
    qtbot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    runner = _FakeRunner()
    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path, runner)
    actions = window.trackingActions
    video_id = window.activeVideoId

    # Points at frames 0, 1, 2 exist from _opened_window
    assert len(session.manual_points(track_id)) == 3

    run1 = _create_fake_completed_run(session, track_id, video_id, point_frames=(1, 2, 3, 4))
    run2 = _create_fake_completed_run(session, track_id, video_id, point_frames=(0, 2, 4))
    actions.refresh()

    monkeypatch.setattr(QMessageBox, "critical", lambda *args: (_ for _ in ()).throw(AssertionError(f"CRITICAL: {args}")))
    # 1. Activate Run 1 with cancellation (User clicks No)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    actions.activateRun(run1.run_id)
    assert session.get_track_activation_status(track_id)[0] == "none"

    # 2. Activate Run 1 with confirmation (User clicks Yes)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    actions.activateRun(run1.run_id)
    status, active_id, _ = session.get_track_activation_status(track_id)
    assert status == "active"
    assert active_id == run1.run_id

    # Manual points preserved at frames 0, 1, 2
    eff_points = session.effective_points(track_id)
    assert len(eff_points) == 5  # frames 0, 1, 2 (manual), 3, 4 (dlc)
    assert session.effective_point(track_id, 1).source == "manual"
    assert session.effective_point(track_id, 3).source == "dlc"

    # Panel UI reflection and Undo button
    assert str(run1.run_id)[:8] in actions.panel.activeRunLabel.text()
    assert window.undoButton.isEnabled()

    # 3. Replace cancellation (User clicks No)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    actions.replaceRun(run2.run_id)
    assert session.get_track_activation_status(track_id)[1] == run1.run_id

    # Replace confirmation (User clicks Yes)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    actions.replaceRun(run2.run_id)
    status2, active_id2, _ = session.get_track_activation_status(track_id)
    assert status2 == "active"
    assert active_id2 == run2.run_id
    assert str(run2.run_id)[:8] in actions.panel.activeRunLabel.text()
    assert window.undoButton.isEnabled()

    # 4. Clear cancellation (User clicks No)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    actions.clearActivation()
    assert session.get_track_activation_status(track_id)[1] == run2.run_id

    # Clear confirmation (User clicks Yes)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    actions.clearActivation()
    status3, active_id3, _ = session.get_track_activation_status(track_id)
    assert status3 == "none"
    assert active_id3 is None
    assert len(session.effective_points(track_id)) == 3
    assert "None" in actions.panel.activeRunLabel.text()
    assert window.undoButton.isEnabled()

    # 5. Undo restores active run 2
    assert session.can_undo
    window.undoButton.click()
    assert session.get_track_activation_status(track_id)[1] == run2.run_id


def test_manage_validation_dialog_workflow(
    qtbot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    runner = _FakeRunner()
    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path, runner)
    actions = window.trackingActions

    # Currently has 3 points (0, 1, 2). Add a 4th point at frame 3
    session.mark_point(track_id, 3, 40.0, 50.0)
    assert len(session.manual_points(track_id)) == 4

    dialog = ManageValidationDialog(session, track_id, window)
    qtbot.addWidget(dialog)

    # Initial state: freezeButton enabled because len(manual_points) == 4 >= 4
    assert dialog.freezeButton.isEnabled()
    assert dialog.deleteButton is None

    # Try freeze without selecting any checkbox
    for _, cb in dialog._checkboxes:
        cb.setChecked(False)

    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args))
    dialog.freezeButton.click()
    assert any("No Frames Selected" in str(w) for w in warned)

    # Try select all 4 frames (leaves 0 for training < 3)
    for _, cb in dialog._checkboxes:
        cb.setChecked(True)
    warned.clear()
    dialog.freezeButton.click()
    assert any("Insufficient Training Frames" in str(w) for w in warned)

    # Select only frame 3 (leaves 0, 1, 2 for training = 3)
    for f_idx, cb in dialog._checkboxes:
        cb.setChecked(f_idx == 3)

    info_messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: info_messages.append(args))
    dialog.freezeButton.click()

    ref_state = session.get_refinement_state(track_id)
    assert ref_state.active_series is not None
    assert ref_state.active_series.frame_indices == (3,)
    val_valid, _ = session.validate_active_validation_series(track_id)
    assert val_valid is True

    # Now open dialog again to delete active series
    dialog2 = ManageValidationDialog(session, track_id, window)
    qtbot.addWidget(dialog2)
    assert dialog2.deleteButton is not None

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    dialog2.deleteButton.click()

    ref_state_after = session.get_refinement_state(track_id)
    assert ref_state_after.active_series is None


# ---------------------------------------------------------------------------
# 合并后复审（R2）——按钮矩阵与历史标注加固
# ---------------------------------------------------------------------------

def test_activation_buttons_disabled_while_track_has_pending_run(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    """当前 track 有 pending/running run 时禁用四个激活按钮（review F-2 GUI 缓解）。"""
    win, session, track_id, video = _open_with_track(qtbot, tmp_path, synthetic_video_path)
    pending = replace(create_tracking_run(video.video_id, track_id, "infer", engine="dlc"),
                      status="running")
    session.record_tracking_run(pending)
    win.trackingActions._context_key = None
    win.trackingActions.refresh()

    panel = win.trackingActions.panel
    assert not panel.activateButton.isEnabled()
    assert not panel.replaceButton.isEnabled()
    assert not panel.clearActivationButton.isEnabled()
    assert not panel.manageValidationButton.isEnabled()
    assert "AI task is active" in panel.replaceButton.toolTip()

    # 任务结束后恢复
    session.update_tracking_run(replace(pending, status="completed"))
    win.trackingActions._context_key = None
    win.trackingActions.refresh()
    assert panel.manageValidationButton.isEnabled()


def test_activation_buttons_disabled_during_project_busy(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    """autosave/项目操作进行中（project_busy）禁用激活按钮（review F-3）。"""
    win, _session, _track_id, _video = _open_with_track(qtbot, tmp_path, synthetic_video_path)
    panel = win.trackingActions.panel
    panel.setContext("v", "t", None, None, busy=False, project_busy=True)
    assert not panel.clearActivationButton.isEnabled()
    panel.setContext("v", "t", None, None, busy=False, project_busy=False)
    assert panel.manageValidationButton.isEnabled()


def test_history_labels_other_track_active_run(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    """项目级 history 对其他 track 的 active run 标注 Active (other track)（review F-4）。"""
    win, session, track_id, video = _open_with_track(qtbot, tmp_path, synthetic_video_path)
    panel = win.trackingActions.panel
    other = session.add_track(video.video_id, "TrackB")
    run_b = _create_fake_completed_run(session, other.track_id, video.video_id, (1, 2, 3))
    session.activate_infer_run(other.track_id, run_b.run_id)

    win.trackingActions._context_key = None
    win.trackingActions.refresh()
    # 选中 Track 1 时，TrackB 的 active run 不应显示为 Not active
    labels = [panel.historyList.item(i).text()
              for i in range(panel.historyList.count())]
    assert any("Active (other track)" in text for text in labels)
    assert not any("Not active" in text and str(run_b.run_id)[:8] in text
                   for text in labels)


def _open_with_track(qtbot, tmp_path, synthetic_video_path):
    win = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(),
                     _StaticTimingProbe())
    qtbot.addWidget(win)
    win.show()
    assert win.openVideo(synthetic_video_path, show_error=False)
    win.addTrackButton.click()
    track_id = win.selectedTrackId
    session = win.analysisSession
    session.mark_point(track_id, 1, 10.0, 10.0)
    session.save_as(tmp_path / "proj")
    video = session.project.videos[0]
    win.trackingActions._context_key = None
    win.trackingActions.refresh()
    return win, session, track_id, video
