"""图表面板的 Qt offscreen 回归：同步、事务生命周期与缓存恢复。"""

from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainterPath
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


@pytest.fixture(autouse=True)
def reject_unexpected_error_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """意外错误对话框直接让测试失败，避免 offscreen 模态框阻塞。"""

    def fail(*args: object, **kwargs: object) -> None:
        del kwargs
        pytest.fail(f"Unexpected QMessageBox.critical: {args}")

    monkeypatch.setattr(QMessageBox, "critical", fail)


class _StaticProbe:
    def __init__(self, report: TimingReport) -> None:
        self.report = report

    def probe(self, _path: Path, cancel: Event | None = None) -> TimingReport:
        if cancel is not None and cancel.is_set():
            raise CancelledError()
        return self.report


class _BlockingJob:
    """用 Event 控制后台作业返回，避免测试依赖 sleep 竞态。"""

    def __init__(self, real_run, *, cancel_aware: bool) -> None:
        self.real_run = real_run
        self.cancel_aware = cancel_aware
        self.started = Event()
        self.finished = Event()
        self.release = Event()

    def __call__(self, job, cancel: Event):
        self.started.set()
        try:
            while not self.release.wait(0.01):
                if self.cancel_aware and cancel.is_set():
                    raise CancelledError()
            return self.real_run(job, cancel)
        finally:
            self.finished.set()


class _SceneMouseEvent:
    def __init__(self, scene_pos: QPointF) -> None:
        self._scene_pos = scene_pos

    def button(self) -> Qt.MouseButton:
        return Qt.MouseButton.LeftButton

    def scenePos(self) -> QPointF:
        return self._scene_pos


def _cfr_report() -> TimingReport:
    return TimingReport(
        status="cfr",
        reason="static CFR test result",
        frame_count=5,
        fps_measured=10.0,
        fps_reference=10.0,
    )


def _near_cfr_report() -> TimingReport:
    return TimingReport(
        status="near_cfr",
        reason="static near-CFR test result",
        frame_count=5,
        fps_measured=10.0,
        fps_reference=10.0,
        max_grid_error_s=0.0001,
        max_interval_error_s=0.0002,
    )


def _window(probe: _StaticProbe | None = None) -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        probe or _StaticProbe(_cfr_report()),
    )


def _opened(qtbot: QtBot, synthetic_video_path: Path, probe: _StaticProbe | None = None) -> MainWindow:
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    return window


def _add_track(
    window: MainWindow,
    *,
    frames: tuple[int, ...] = (0, 1, 2, 3, 4),
    offset: float = 0.0,
):
    window.addTrackButton.click()
    session = window.analysisSession
    assert session is not None
    track = session.tracks[-1]
    for frame_index in frames:
        session.mark_point(
            track.track_id,
            frame_index,
            pixel_x=10.0 + frame_index + offset,
            pixel_y=20.0 + 2.0 * frame_index,
        )
    window._refreshHistoryButtons()
    window.chartActions.refresh()
    return track


def _with_results(
    qtbot: QtBot,
    synthetic_video_path: Path,
    *,
    frames: tuple[int, ...] = (0, 1, 2, 3, 4),
    track_count: int = 1,
) -> tuple[MainWindow, tuple[Track, ...]]:
    window = _opened(qtbot, synthetic_video_path)
    tracks = tuple(
        _add_track(window, frames=frames, offset=float(index))
        for index in range(track_count)
    )
    session = window.analysisSession
    assert session is not None
    for track in tracks:
        session.compute_kinematics(track.track_id)
    window._refreshHistoryButtons()
    window.chartActions.refresh()
    qtbot.wait(20)
    return window, tracks


def test_chart_panel_exposes_five_tabs_pixel_y_and_multi_track_selection(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    window, tracks = _with_results(qtbot, synthetic_video_path, track_count=2)
    panel = window.chartActions.panel

    assert panel.tabs.count() == 5
    assert tuple(panel.plots) == ("x_t", "y_t", "v_t", "a_t", "xy")
    assert [panel.tabs.tabText(index) for index in range(5)] == ["x-t", "y-t", "v-t", "a-t", "x-y"]
    assert panel.checkedTracks() == tuple(track.track_id for track in tracks)
    assert len(panel.plots["x_t"].data.series) == 2
    assert panel.plots["xy"].data.pixel_coordinates is True
    assert panel.plots["xy"].getViewBox().yInverted() is True


def test_presented_frame_updates_actual_cursor_without_seek_and_preserves_pending_target(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    window = _opened(qtbot, synthetic_video_path)
    plot = window.chartActions.panel.plots["x_t"]
    emitted: list[float] = []
    plot.timeRequested.connect(emitted.append)

    window.chartActions.presentFrame(2)
    assert plot.currentFrame == 2
    assert plot.actualLine.value() == pytest.approx(0.2)
    assert plot.requestLine.value() == pytest.approx(0.2)
    assert emitted == []

    plot.setRequestedTime(0.3)
    window.chartActions.presentFrame(1)
    assert plot.actualLine.value() == pytest.approx(0.1)
    assert plot.requestLine.value() == pytest.approx(0.3)
    window.chartActions.presentFrame(3)
    assert plot.actualLine.value() == pytest.approx(0.3)
    assert plot.requestLine.value() == pytest.approx(0.3)


def test_time_and_xy_clicks_seek_source_frames_and_main_window_clamps_working_zone(
    qtbot: QtBot,
    synthetic_video_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, tracks = _with_results(qtbot, synthetic_video_path, frames=(1, 2, 3))
    session = window.analysisSession
    assert session is not None
    old_timeline = session.project.timelines[0]
    timeline = replace(old_timeline, working_zone=(1, 3))
    session._project = replace(session.project, timelines=(timeline,))
    window._timeline = timeline
    window.chartActions._render_key = None
    window.chartActions.refresh()
    qtbot.wait(20)

    requested: list[int] = []
    monkeypatch.setattr(window, "_requestFrame", requested.append)
    time_plot = window.chartActions.panel.plots["x_t"]
    x_min, x_max = time_plot.getViewBox().viewRange()[0]
    y_min, y_max = time_plot.getViewBox().viewRange()[1]
    del x_min, x_max
    click_time = 0.2
    time_pos = time_plot.getViewBox().mapViewToScene(
        QPointF(click_time, (y_min + y_max) / 2.0)
    )
    time_plot._sceneClicked(_SceneMouseEvent(time_pos))

    window.chartActions.panel.tabs.setCurrentIndex(4)
    qtbot.wait(20)
    xy_plot = window.chartActions.panel.plots["xy"]
    xy_item = xy_plot._items[0]
    xy_point = next(point for point in xy_item.scatter.points() if point.data()[1] == 2)
    xy_plot._sceneClicked(_SceneMouseEvent(xy_item.scatter.mapToScene(xy_point.pos())))

    window.chartActions.seekTime(-100.0)
    window.chartActions.seekTime(100.0)

    assert requested == [2, 2, 1, 3]
    assert xy_plot.activeTrack == tracks[0].track_id


def test_sparse_chart_renders_isolated_points_and_highlights_only_present_frame(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    window, _tracks = _with_results(qtbot, synthetic_video_path, frames=(1, 3))
    plot = window.chartActions.panel.plots["x_t"]
    assert plot.data is not None
    assert plot.data.series[0].frames == (1, 3)
    assert plot.data.series[0].connect == (False, False)

    path = plot._items[0].curve.getPath()
    assert sum(
        path.elementAt(index).type == QPainterPath.ElementType.MoveToElement
        for index in range(path.elementCount())
    ) == 2

    plot.setFrame(2, 0.2)
    assert len(plot._highlight.points()) == 0
    plot.setFrame(3, 0.3)
    assert len(plot._highlight.points()) == 1


def test_invalid_smoothing_parameters_are_rejected_before_starting_job(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    window = _opened(qtbot, synthetic_video_path)
    _add_track(window)
    panel = window.chartActions.panel
    panel.windowLength.setValue(8)

    window.chartActions.recompute()

    assert not window.chartActions.pending
    assert "odd" in panel.jobLabel.text()
    assert window.analysisSession is not None
    assert window.analysisSession.project.derived == ()


def test_near_cfr_requires_explicit_authorization_before_chart_recompute(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_video_path: Path,
) -> None:
    window = _opened(qtbot, synthetic_video_path, _StaticProbe(_near_cfr_report()))
    # 重新走用户使用的 deferred timing 路径；图表可读但新计算必须被锁住。
    window.projectActions._load(
        lambda service, cancel: service.open_video(synthetic_video_path, cancel)
    )
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)
    assert not window._measurement_allowed
    assert not window.chartActions.panel.recomputeButton.isEnabled()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    window.timingButton.click()
    assert window._measurement_allowed
    _add_track(window)
    window.chartActions.refresh()
    assert window.chartActions.panel.recomputeButton.isEnabled()


def test_cancelled_slow_job_returns_without_committing_results(
    qtbot: QtBot,
    synthetic_video_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _opened(qtbot, synthetic_video_path)
    _add_track(window)
    import ai_physics_tracker.gui.chart_actions as chart_actions_module

    gate = _BlockingJob(chart_actions_module.run_kinematics_job, cancel_aware=True)
    monkeypatch.setattr(chart_actions_module, "run_kinematics_job", gate)
    try:
        window.chartActions.recompute()
        qtbot.waitUntil(gate.started.is_set, timeout=5000)
        assert window.chartActions.pending
        window.chartActions.panel.cancelButton.click()
        qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
        assert gate.finished.is_set()
        assert window.analysisSession is not None
        assert window.analysisSession.project.derived == ()
        assert "no results committed" in window.chartActions.panel.jobLabel.text()
    finally:
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)


def test_slow_job_after_project_switch_cannot_restore_old_results(
    qtbot: QtBot,
    synthetic_video_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _opened(qtbot, synthetic_video_path)
    _add_track(window)
    import ai_physics_tracker.gui.chart_actions as chart_actions_module

    gate = _BlockingJob(chart_actions_module.run_kinematics_job, cancel_aware=False)
    monkeypatch.setattr(chart_actions_module, "run_kinematics_job", gate)
    try:
        window.chartActions.recompute()
        qtbot.waitUntil(gate.started.is_set, timeout=5000)
        window.adoptEmptyProject()
        new_session = window.analysisSession
        assert new_session is not None
        assert new_session.project.videos == ()
        assert not window.chartActions.pending
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)
        qtbot.wait(50)
        assert new_session.project.derived == ()
    finally:
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)


def test_slow_job_result_during_save_keeps_raw_points_and_commits_to_saved_session(
    qtbot: QtBot,
    synthetic_video_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = _opened(qtbot, synthetic_video_path)
    track = _add_track(window)
    session = window.analysisSession
    assert session is not None
    original_point = session.manual_points(track.track_id)[-1]
    import ai_physics_tracker.gui.chart_actions as chart_actions_module

    gate = _BlockingJob(chart_actions_module.run_kinematics_job, cancel_aware=False)
    monkeypatch.setattr(chart_actions_module, "run_kinematics_job", gate)
    repository = window._annotation_repository
    original_create = repository.create_from_project
    save_started = Event()
    release_save = Event()

    def blocked_create(root: Path, project):
        save_started.set()
        if not release_save.wait(5.0):
            raise TimeoutError("synthetic save gate was not released")
        return original_create(root, project)

    monkeypatch.setattr(repository, "create_from_project", blocked_create)
    root = tmp_path / "saved-while-computing"
    try:
        window.chartActions.recompute()
        qtbot.waitUntil(gate.started.is_set, timeout=5000)
        window.projectActions._saveCandidate(root, None)
        qtbot.waitUntil(save_started.is_set, timeout=5000)
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)
        assert window.chartActions.pending
        assert window.projectActions.busy
        release_save.set()
        qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
        qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
        active = window.analysisSession
        assert active is not None
        assert active.project_root == root.resolve()
        assert active.manual_points(track.track_id)[-1] == original_point
        assert len(active.project.derived) == 4
        saved = ProjectRepository().load(root)
        assert original_point in saved.observations
        assert len(saved.observations) == len(active.project.observations)
    finally:
        gate.release.set()
        release_save.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)


def test_input_mutation_discards_late_result_but_keeps_new_raw_point(
    qtbot: QtBot,
    synthetic_video_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _opened(qtbot, synthetic_video_path)
    track = _add_track(window, frames=(0, 1, 2, 3))
    session = window.analysisSession
    assert session is not None
    import ai_physics_tracker.gui.chart_actions as chart_actions_module

    gate = _BlockingJob(chart_actions_module.run_kinematics_job, cancel_aware=False)
    monkeypatch.setattr(chart_actions_module, "run_kinematics_job", gate)
    try:
        window.chartActions.recompute()
        qtbot.waitUntil(gate.started.is_set, timeout=5000)
        changed = session.mark_point(track.track_id, 4, 90.0, 91.0)
        window._refreshHistoryButtons()
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)
        qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
        assert session.manual_points(track.track_id)[-1] == changed
        assert session.project.derived == ()
        assert "not committed" in window.chartActions.panel.jobLabel.text()
    finally:
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)


def test_reopen_restores_cached_charts_without_making_project_dirty(
    qtbot: QtBot,
    synthetic_video_path: Path,
    tmp_path: Path,
) -> None:
    window = _opened(qtbot, synthetic_video_path)
    track = _add_track(window)
    session = window.analysisSession
    assert session is not None
    session.compute_kinematics(track.track_id)
    root = tmp_path / "cached-project"
    session.save_as(root)
    assert not session.is_dirty

    window.projectActions._load(
        lambda service, cancel: service.open_project(root, cancel)
    )
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)
    loaded = window.analysisSession
    assert loaded is not None
    assert len(loaded.project.derived) == 4
    assert not loaded.is_dirty
    assert window.chartActions.panel.plots["x_t"].data is not None
    assert window.chartActions.panel.plots["x_t"].data.series

    window.chartActions.panel.tabs.setCurrentIndex(4)
    window.chartActions.panel.fitButton.click()
    assert not loaded.is_dirty
