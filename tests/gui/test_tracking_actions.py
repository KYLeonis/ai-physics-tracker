"""TrackingActions 的 GUI 线程边界、取消竞争与保存身份回归。"""

from pathlib import Path
from threading import Event
import time

import pytest
from PySide6.QtCore import QTimer

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskResult


class _FakeHandle:
    """可控任务句柄；默认存活，取消可选择阻塞在后台。"""

    def __init__(self, *, block_cancel: bool = False) -> None:
        self._alive = True
        self._messages = []
        self.block_cancel = block_cancel
        self.cancel_started = Event()
        self.cancel_release = Event()
        self.cancel_calls = 0
        self.exitcode = None

    def poll_messages(self, limit: int | None = None):
        if limit is None:
            messages, self._messages = self._messages, []
            return messages
        messages, self._messages = self._messages[:limit], self._messages[limit:]
        return messages

    def is_alive(self) -> bool:
        return self._alive

    def cancel(self, timeout_s: float = 3.0) -> None:
        del timeout_s
        self.cancel_calls += 1
        self.cancel_started.set()
        if self.block_cancel:
            self.cancel_release.wait(2.0)
        self._alive = False
        self.exitcode = 0

    def add_message(self, message: object) -> None:
        self._messages.append(message)


class _FakeRunner:
    def __init__(self, *handles: _FakeHandle) -> None:
        self.handles = list(handles)
        self.started = Event()
        self.calls = 0

    def start_task(self, run_id, target, *args, **kwargs):
        del run_id, target, args, kwargs
        self.calls += 1
        self.started.set()
        if not self.handles:
            raise AssertionError("fake runner has no handle")
        return self.handles.pop(0)


def _opened_window(qtbot, synthetic_video_path: Path, tmp_path: Path, runner: _FakeRunner):
    window = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        _StaticTimingProbe(),
    )
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    track_id = window.selectedTrackId
    assert track_id is not None
    session = window.analysisSession
    assert session is not None
    for frame_index in (0, 1, 2):
        session.mark_point(track_id, frame_index, 10.0 + frame_index, 20.0)
    session.save_as(tmp_path / "project")
    window.projectActions.refresh()
    window.trackingActions.runner = runner
    window.trackingActions.refresh()
    return window, session, track_id


class _StaticTimingProbe:
    def probe(self, path, cancel=None):
        del path, cancel
        from ai_physics_tracker.application.video_timing import TimingReport

        return TimingReport(
            status="cfr",
            reason="static GUI test timing",
            frame_count=5,
            fps_measured=10.0,
            fps_reference=10.0,
        )


def _active_run(session) -> TrackingRun:
    runs = session.tracking_runs()
    return runs[-1]


def _wait_started(qtbot, actions, handle: _FakeHandle) -> None:
    qtbot.waitUntil(lambda: actions.pending and actions._handle is handle, timeout=3000)


def test_cancel_returns_immediately_while_qt_event_loop_stays_responsive(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    handle = _FakeHandle(block_cancel=True)
    runner = _FakeRunner(handle)
    window, session, _track_id = _opened_window(qtbot, synthetic_video_path, tmp_path, runner)
    actions = window.trackingActions
    actions.train()
    _wait_started(qtbot, actions, handle)

    ticks = []
    timer = QTimer(window)
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    started = time.monotonic()
    actions.cancel()
    elapsed = time.monotonic() - started

    assert elapsed < 0.2
    qtbot.waitUntil(handle.cancel_started.is_set, timeout=3000)
    qtbot.waitUntil(lambda: len(ticks) >= 3, timeout=3000)
    assert actions.cancelling

    handle.cancel_release.set()
    qtbot.waitUntil(lambda: not actions.pending, timeout=3000)
    timer.stop()
    assert _active_run(session).status == "cancelled"


def test_late_success_after_cancel_is_ignored_and_next_task_can_start(
    qtbot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    first = _FakeHandle()
    second = _FakeHandle()
    runner = _FakeRunner(first, second)
    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path, runner)
    actions = window.trackingActions

    actions.train()
    _wait_started(qtbot, actions, first)
    run_id = _active_run(session).run_id
    actions.cancel()
    qtbot.waitUntil(lambda: not actions.pending, timeout=3000)
    assert _active_run(session).status == "cancelled"

    first.add_message(
        TaskResult(
            run_id,
            True,
            {"status": "completed", "result_path": "data/engines/late/task-result.json"},
        )
    )
    qtbot.wait(150)
    assert len(session.project.observations) == 3

    actions.train()
    _wait_started(qtbot, actions, second)
    assert runner.calls == 2
    assert _active_run(session).track_id == track_id
    actions.cancel()
    qtbot.waitUntil(lambda: not actions.pending, timeout=3000)
    assert _active_run(session).status == "cancelled"


def test_ordinary_save_keeps_session_identity_and_concurrent_edit_dirty(
    qtbot, synthetic_video_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, session, track_id = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner()
    )
    session.mark_point(track_id, 3, 13.0, 20.0)
    entered = Event()
    release = Event()
    repository = window._annotation_repository
    original_save = repository.save

    def slow_save(root, project):
        entered.set()
        assert release.wait(3.0)
        return original_save(root, project)

    monkeypatch.setattr(repository, "save", slow_save)
    window.projectActions.save()
    qtbot.waitUntil(entered.is_set, timeout=3000)
    concurrent = session.mark_point(track_id, 4, 14.0, 20.0)
    release.set()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

    assert window.analysisSession is session
    assert session.is_dirty
    assert concurrent in session.project.observations


def test_cancel_during_evaluation_keeps_model_and_ignores_late_terminal(qtbot, synthetic_video_path, tmp_path):
    import json
    from ai_physics_tracker.domain.tracking_run import mark_run_completed
    from ai_physics_tracker.infrastructure.project_serializer import tracking_run_to_payload

    handle = _FakeHandle()
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner(handle))
    actions = window.trackingActions
    actions.train()
    _wait_started(qtbot, actions, handle)
    run = _active_run(session)
    folder = session.project_root / "data" / "engines" / str(run.run_id)
    folder.mkdir(parents=True)
    model = folder / "model.pt"
    model.write_bytes(b"mock model")
    completed = mark_run_completed(run, model_snapshot=model.relative_to(session.project_root).as_posix())
    (folder / "model-ready.json").write_text(json.dumps({"run": tracking_run_to_payload(completed),
                                                       "points_path": None}), encoding="utf-8")
    handle.add_message(TaskResult(run.run_id, False, {"status": "cancelled"}))
    actions.cancel()
    qtbot.waitUntil(lambda: not actions.pending, timeout=5000)
    recorded = _active_run(session)
    assert recorded.status == "completed"
    assert recorded.extra_fields["evaluation"]["status"] == "cancelled"
    assert model.is_file()
    assert handle.cancel_calls == 1


def test_navigation_cancel_keeps_task_and_confirmed_discard_cancels_before_switch(
    qtbot, synthetic_video_path, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    handle = _FakeHandle()
    window, original, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner(handle))
    actions = window.trackingActions
    actions.train()
    _wait_started(qtbot, actions, handle)

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.projectActions.closeProject()
    assert actions.pending
    assert window.analysisSession is original
    assert handle.cancel_calls == 0

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    window.projectActions.closeProject()
    qtbot.waitUntil(lambda: not actions.pending, timeout=5000)
    qtbot.waitUntil(lambda: window.analysisSession is not original, timeout=5000)
    assert window.analysisSession.project.videos == ()
    assert handle.cancel_calls == 1


def test_file_chooser_cancel_and_context_breaking_actions_do_not_cancel_or_mutate_task(
    qtbot, synthetic_video_path, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog

    handle = _FakeHandle()
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner(handle))
    actions = window.trackingActions
    actions.train()
    _wait_started(qtbot, actions, handle)
    root = session.project_root

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("", ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (_ for _ in ()).throw(AssertionError("disabled")))
    window.projectActions.openProject()
    window.projectActions.saveAs()
    window.projectActions.relinkVideo()

    assert actions.pending
    assert handle.cancel_calls == 0
    assert session.project_root == root
    actions.cancel()
    qtbot.waitUntil(lambda: not actions.pending, timeout=5000)
