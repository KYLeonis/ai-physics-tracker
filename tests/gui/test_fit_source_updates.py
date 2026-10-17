"""公式拟合页源自动补齐、相关输入联动与取消隔离回归。"""

from concurrent.futures import Future
from dataclasses import replace
from threading import Event

from tests.gui.test_signal_analysis import _window
from ai_physics_tracker.domain.angular import PendulumReference


def _ready(qtbot, panel):
    qtbot.waitUntil(lambda: "Initial curve only" in panel.jobLabel.text(), timeout=8000)


def test_missing_source_is_prepared_in_place_without_fitting_or_touching_other_tracks(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    other = session.add_track(window.activeVideoId)
    for frame in range(5):
        session.mark_point(other.track_id, frame, pixel_x=frame, pixel_y=10)
    untouched = session.compute_kinematics(other.track_id)
    session.clear_derived(track)
    raw = session.project.observations
    actions.refresh()
    assert not panel.fitButton.isEnabled()

    _ready(qtbot, panel)

    assert window.analysisTabs.currentIndex() == 1
    assert session.project.observations == raw
    assert session.derived_data(track, "world_position") is not None
    assert all(session.derived_data(other.track_id, item.kind) == item for item in untouched)
    assert session.derived_data(track, "function_fit_x") is None
    assert actions.attempts.journal.attempts == []
    assert panel.fitButton.isEnabled()
    assert "world_position" in panel.contextLabel.text()
    assert "px" in panel.contextLabel.text()
    actions.refresh()
    assert "world_position" in panel.contextLabel.text()


def test_source_edit_updates_preview_and_stales_previous_fit_without_automatic_fit(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _ready(qtbot, panel)
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    previous = session.derived_data(track, "function_fit_x")
    attempts = len(actions.attempts.journal.attempts)
    source = session.derived_data(track, "world_position")

    session.mark_point(track, 2, pixel_x=50, pixel_y=20)
    window.analysisChanged.emit()
    qtbot.waitUntil(lambda: session.derived_data(track, "world_position").derived_id != source.derived_id, timeout=8000)
    _ready(qtbot, panel)

    result = session.derived_data(track, "function_fit_x")
    assert result.derived_id == previous.derived_id and result.status == "stale"
    assert len(actions.attempts.journal.attempts) == attempts
    assert panel.signalPlot.listDataItems()[0].getData()[1][2] == 50


def test_cancelled_source_does_not_publish_or_restart_on_refresh(qtbot, synthetic_video_path, monkeypatch):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    session.clear_derived(track)
    captured = []
    future = Future()
    future.set_running_or_notify_cancel()

    def submit(run, job, cancel):
        captured.append((run, job))
        return future

    monkeypatch.setattr(actions._executor, "submit", submit)
    actions.refresh()
    actions.preview.launch()
    assert actions.pending
    assert "Updating source data" in panel.jobLabel.text()
    panel.cancelButton.click()
    run, job = captured[0]
    future.set_result(run(job, Event()))
    actions._poll()
    actions.refresh()

    assert session.derived_data(track, "world_position") is None
    assert not actions.pending and len(captured) == 1
    assert not actions.preview._debounce.isActive()
    assert "cancelled" in panel.jobLabel.text()


def test_changed_selection_discards_late_source_group(qtbot, synthetic_video_path, monkeypatch):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    session.clear_derived(track)
    future = Future()
    future.set_running_or_notify_cancel()
    captured = []

    def submit(run, job, cancel):
        captured.append((run, job))
        return future

    monkeypatch.setattr(actions._executor, "submit", submit)
    actions.refresh()
    actions.preview.launch()
    panel.quantityChoice.setCurrentText("y")
    actions.preview.invalidate()
    run, job = captured[0]
    future.set_result(run(job, Event()))
    actions._poll()
    actions.preview.invalidate()

    assert session.derived_data(track, "world_position") is None
    assert session.derived_data(track, "function_fit_x") is None


def test_unknown_source_recipe_is_not_automatically_replaced(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    source = session.derived_data(track, "world_position")
    unknown = replace(source, status="stale", pipeline=source.pipeline + ({"step": "future_method", "params": {}},))
    session._project = replace(session.project, derived=tuple(unknown if item == source else item for item in session.project.derived))
    before = session.project
    actions.refresh()
    actions.preview.launch()

    assert session.project == before and not actions.pending
    assert "unsupported recipe" in panel.jobLabel.text()
    assert not actions.preview._debounce.isActive()


def test_angular_source_does_not_guess_calibration_or_reference(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    before = session.project
    panel.quantityChoice.setCurrentText("theta")
    actions.preview.launch()

    assert not actions.pending and session.project == before
    assert "calibration" in panel.jobLabel.text() and "applied reference" in panel.jobLabel.text()
    assert window.analysisTabs.currentIndex() == 1


def test_derivative_choice_reports_the_actual_source_and_restores_position_options(qtbot, synthetic_video_path):
    window, _, _ = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.sourceChoice.setCurrentIndex(1)
    panel.quantityChoice.setCurrentText("vx")
    assert not panel.sourceChoice.isEnabled()
    assert panel.sourceChoice.currentText() == "SG derivative"
    assert not panel.selection().smoothed
    panel.quantityChoice.setCurrentText("x")
    assert panel.sourceChoice.isEnabled() and panel.sourceChoice.currentText() == "Smoothed"


def test_confirmed_angular_reference_updates_source_preview_and_units_together(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    session.add_calibration(window.activeVideoId, scale_end_1_px=(0., 0.),
                            scale_end_2_px=(10., 0.), known_length=1., unit="m")
    controls = actions.panel.angularControls
    controls.pivotX.setValue(10.)
    controls.pivotY.setValue(0.)
    controls.applyButton.click()
    panel.quantityChoice.setCurrentText("theta")
    _ready(qtbot, panel)
    source = session.derived_data(track, "angular_position")
    assert source is not None and "angular_position" in panel.contextLabel.text()
    assert "rad" in panel.contextLabel.text()
    raw = session.project.observations

    controls.pivotX.setValue(12.)
    actions.refresh()
    actions.preview.launch()
    assert not actions.pending and "applied reference" in panel.jobLabel.text()
    assert session.derived_data(track, "angular_position") == source
    controls.applyButton.click()
    qtbot.waitUntil(lambda: session.derived_data(track, "angular_position").derived_id != source.derived_id, timeout=8000)
    _ready(qtbot, panel)
    assert session.project.observations == raw
    assert session.derived_data(track, "function_fit_theta") is None


def test_history_and_save_refresh_do_not_start_automatic_computation(qtbot, synthetic_video_path, tmp_path, monkeypatch):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _ready(qtbot, panel)
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not actions.pending)

    def unexpected(*args):
        raise AssertionError("Read-only refresh must not compute")

    monkeypatch.setattr(actions._executor, "submit", unexpected)
    monkeypatch.setattr(actions.preview._executor, "submit", unexpected)
    session.save_as(tmp_path / "saved")
    actions.refresh()
    assert not actions.preview._debounce.isActive()
    panel.latestButton.click()
    assert panel.history.active
    session.clear_derived(track)
    before = session.project
    actions.refresh()
    assert session.project == before
    assert not actions.pending and not actions.preview._debounce.isActive()


def test_failed_source_update_is_visible_without_automatic_retry(qtbot, synthetic_video_path, monkeypatch):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    session.clear_derived(track)
    future = Future()
    monkeypatch.setattr(actions._executor, "submit", lambda *args: future)
    actions.refresh()
    actions.preview.launch()
    future.set_exception(RuntimeError("source worker unavailable"))
    actions._poll()
    actions.refresh()
    assert "Source update failed" in panel.jobLabel.text()
    assert "source worker unavailable" in panel.jobLabel.text()
    assert not actions.pending and not actions.preview._debounce.isActive()
    assert session.derived_data(track, "world_position") is None


def test_switching_fit_track_keeps_that_tracks_own_reference(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    session.add_calibration(window.activeVideoId, scale_end_1_px=(0., 0.),
                            scale_end_2_px=(10., 0.), known_length=1., unit="m")
    other = session.add_track(window.activeVideoId, "Other reference")
    for frame in range(5):
        session.mark_point(other.track_id, frame, pixel_x=20 + frame, pixel_y=10)
    session.compute_angular(track, reference=PendulumReference((10., 0.)))
    session.compute_angular(other.track_id, reference=PendulumReference((50., 0.)))
    source = session.derived_data(other.track_id, "angular_position")
    actions.refresh()
    actions.panel.angularControls.seedApplied(PendulumReference((10., 0.)))
    assert actions.panel.checkedTracks() == (track,)
    panel.trackChoice.setCurrentIndex(panel.trackChoice.findData(str(other.track_id)))
    panel.quantityChoice.setCurrentText("theta")
    _ready(qtbot, panel)
    assert session.derived_data(other.track_id, "angular_position") == source


def test_new_track_reports_its_own_default_smoothing_instead_of_other_tracks_controls(qtbot, synthetic_video_path):
    window, session, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    actions.panel.windowLength.setValue(9)
    other = session.add_track(window.activeVideoId, "New source")
    for frame in range(5):
        session.mark_point(other.track_id, frame, pixel_x=frame, pixel_y=10)
    actions.refresh()
    panel.trackChoice.setCurrentIndex(panel.trackChoice.findData(str(other.track_id)))
    panel.quantityChoice.setCurrentText("vx")
    _ready(qtbot, panel)
    assert actions.panel.windowLength.value() == 9
    assert "SG window 7, order 2" in panel.contextLabel.text()
    assert session.derived_data(other.track_id, "function_fit_vx") is None


def test_derivative_attempt_and_history_record_actual_source_semantics(qtbot, synthetic_video_path):
    window, _, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    panel.sourceChoice.setCurrentIndex(1)
    panel.quantityChoice.setCurrentText("vx")
    _ready(qtbot, panel)
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    assert actions.attempts.journal.attempts[-1]["smoothed"] is False
    panel.latestButton.click()
    assert panel.history.active
    assert "sg derivative" in panel.contextLabel.text()
