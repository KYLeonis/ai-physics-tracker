"""项目菜单失败保护与真实持久化恢复的 Qt 回归。"""

from pathlib import Path
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


@pytest.fixture
def opened(qtbot, synthetic_video_path):
    window = MainWindow(lambda: VideoSession(OpenCVVideoReader()),
                        ProjectRepository(), FFprobeTimingProbe())
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    window._annotation_session.mark_point(window._selected_track_id, 0, 25.0, 20.0)
    window._refreshMarkers()
    return window


def test_first_save_reopen_restores_points_frame_and_paused_state(opened, qtbot, monkeypatch, tmp_path):
    window = opened
    window.frameSpinBox.setValue(3)
    qtbot.waitUntil(lambda: window._presented_frame_index == 3)
    original = window._annotation_session.project
    root = tmp_path / "实验项目"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(root), ""))

    window.projectActions.save()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    assert window._annotation_session.project_root == root
    assert not window._annotation_session.is_dirty
    assert not window._annotation_session.can_undo
    window.projectActions._load(lambda service, cancel: service.open_project(root, cancel))
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

    assert window._annotation_session.project.project_id == original.project_id
    assert window._annotation_session.project.observations == original.observations
    assert window._timeline == original.timelines[0]
    assert window._presented_frame_index == 3
    assert not window.isPlaying
    assert not window.videoView.is_annotation_mode()
    assert window.videoView.marker_count() == 1


def test_reopen_uses_saved_fps_zone_and_does_not_request_clamped_old_spinbox(opened, qtbot, tmp_path):
    session = opened._annotation_session.detached()
    timeline = replace(session.project.timelines[0], fps_nominal=20.0, working_zone=(1, 3))
    session._project = replace(session.project, timelines=(timeline,))
    session.update_view_state({"version": 1, "video_id": str(timeline.video_id), "frame_index": 2})
    root = tmp_path / "different-timeline"
    session.save_as(root)
    opened.frameSpinBox.setValue(4)
    qtbot.waitUntil(lambda: opened._presented_frame_index == 4)

    opened.projectActions._load(lambda service, cancel: service.open_project(root, cancel))
    qtbot.waitUntil(lambda: not opened.projectActions.busy)
    qtbot.wait(50)

    assert opened._timeline == timeline
    assert opened._presented_frame_index == 2
    assert opened.timeLabel.text() == "Time: 0.100 s nominal"
    assert (opened.frameSpinBox.minimum(), opened.frameSpinBox.maximum()) == (1, 3)


def test_cancel_new_preserves_project_and_history(opened, monkeypatch):
    session = opened._annotation_session
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    opened.projectActions.newProject()
    assert opened._annotation_session is session
    assert session.is_dirty and session.can_undo


def test_window_close_cancel_then_discard(opened, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    opened.close()
    assert opened.isVisible()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    opened.close()
    assert not opened.isVisible()


def test_cancel_pending_load_keeps_old_session(opened, qtbot):
    from concurrent.futures import CancelledError
    from threading import Event
    entered = Event()
    session = opened._annotation_session
    def slow(service, cancel):
        entered.set()
        cancel.wait(2.0)
        raise CancelledError()
    opened.projectActions._load(slow)
    qtbot.waitUntil(entered.is_set)
    opened.projectActions._cancel.set()
    qtbot.waitUntil(lambda: not opened.projectActions.busy)
    assert opened._annotation_session is session
    assert session.is_dirty and session.can_undo


def test_cancel_first_save_does_not_continue_discard(opened, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    opened.projectActions.guarded(lambda: calls.append("discarded"))
    assert calls == []
    assert opened._annotation_session.project_root is None
    assert opened._annotation_session.is_dirty


def test_save_failure_keeps_old_session_and_does_not_continue(opened, qtbot, monkeypatch, tmp_path):
    session = opened._annotation_session
    errors, calls = [], []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "new"), ""))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[-1]))
    def fail(*args):
        raise OSError("synthetic permission failure")
    monkeypatch.setattr(opened._annotation_repository, "create_from_project", fail)

    opened.projectActions.guarded(lambda: calls.append("discarded"))
    qtbot.waitUntil(lambda: not opened.projectActions.busy)
    assert errors and calls == []
    assert opened._annotation_session is session
    assert session.project_root is None and session.can_undo and session.is_dirty


def test_failed_project_load_keeps_old_frame_and_annotations(opened, qtbot, monkeypatch, tmp_path):
    session = opened._annotation_session
    frame = opened._presented_frame_index
    errors = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[-1]))
    opened.projectActions._load(lambda service, cancel: service.open_project(tmp_path / "absent", cancel))
    qtbot.waitUntil(lambda: not opened.projectActions.busy)
    assert errors and opened._annotation_session is session
    assert opened._presented_frame_index == frame
    assert opened.videoView.marker_count() == 1
    assert opened.videoView.is_annotation_mode()


def test_late_actual_old_decoder_callback_cannot_replace_new_frame(opened, qtbot, synthetic_video_path):
    old = opened._async
    old_frame = old.snapshot().current_frame
    assert opened.openVideo(synthetic_video_path, show_error=False)
    opened.frameSpinBox.setValue(2)
    qtbot.waitUntil(lambda: opened._presented_frame_index == 2)
    old._on_frame(old_frame)
    qtbot.wait(20)
    assert opened._presented_frame_index == 2


def test_missing_video_load_keeps_registered_tracks(opened, qtbot, tmp_path, synthetic_video_path):
    root = tmp_path / "project"
    session = opened._annotation_session.detached()
    session.save_as(root)
    opened._async.close()
    synthetic_video_path.rename(synthetic_video_path.with_name("moved.avi"))
    opened.projectActions._load(lambda service, cancel: service.open_project(root, cancel))
    qtbot.waitUntil(lambda: not opened.projectActions.busy)
    assert opened.trackList.count() == 1
    assert len(opened._annotation_session.project.observations) == 1
    assert not opened._measurement_allowed and not opened.addTrackButton.isEnabled()
    assert "missing" in opened.statusBar().currentMessage().lower()


class TestAutosave:
    """静默自动保存（用户实测需求：每 10 个标注点 / AI 任务完成后各保存一次）。"""

    def test_autosave_noop_when_project_has_no_save_path(self, qtbot, opened, tmp_path):
        # 未保存过的项目（无 project_root）不触发自动保存
        window = opened
        window.projectActions.autosave("test")
        assert not window.projectActions.busy

    def test_autosave_writes_dirty_project_and_updates_baseline(
        self, qtbot, synthetic_video_path, tmp_path
    ):
        from ai_physics_tracker.gui.main_window import MainWindow
        from ai_physics_tracker.application.video_session import VideoSession
        from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
        from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
        from tests.gui.test_frame_selection_actions import _StaticTimingProbe

        win = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(),
                         _StaticTimingProbe())
        qtbot.addWidget(win)
        assert win.openVideo(synthetic_video_path, show_error=False)
        win.addTrackButton.click()
        track_id = win.selectedTrackId
        session = win.analysisSession
        session.save_as(tmp_path / "proj")
        assert not session.is_dirty

        session.mark_point(track_id, 3, 11.0, 12.0)
        assert session.is_dirty
        win.projectActions.autosave("unit test")
        qtbot.waitUntil(lambda: not win.projectActions.busy, timeout=3000)
        assert not session.is_dirty  # 保存基线已更新

        import json as _json
        data = _json.loads((tmp_path / "proj" / "project.json").read_text(encoding="utf-8"))
        assert any(p["frame_index"] == 3 for p in data["observations"])

    def test_every_ten_marks_trigger_one_autosave(self, qtbot, opened):
        window = opened
        calls = []
        window.projectActions.autosave = lambda reason: calls.append(reason)
        for _ in range(9):
            window._register_mark_for_autosave()
        assert calls == []
        window._register_mark_for_autosave()  # 第 10 个
        assert calls == ["10 new annotations"]
        assert window._marks_since_autosave == 0

