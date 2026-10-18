"""重复间隔联动：候选交点只预览，正式结果必须显式发布。"""

from concurrent.futures import Future
from threading import Event

import numpy as np
import pytest

from tests.gui.test_signal_analysis import _window


def _ready(qtbot, panel):
    qtbot.waitUntil(lambda: panel._eventPreview and 'Crossing preview only' in panel.jobLabel.text(), timeout=8000)


def _periodic(qtbot, path):
    window, session, track = _window(qtbot, path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    for frame, value in enumerate((10, 18, 10, 18, 10)):
        session.mark_point(track, frame, pixel_x=value, pixel_y=20)
    panel.methods.setCurrentIndex(1)
    panel.level.setValue(14)
    window.analysisChanged.emit()
    _ready(qtbot, panel)
    return window, session, track


def test_missing_recurrence_source_prepared_in_place_without_measurement(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    other = session.add_track(window.activeVideoId)
    for frame in range(5):
        session.mark_point(other.track_id, frame, pixel_x=frame, pixel_y=10)
    untouched = session.compute_kinematics(other.track_id)
    session.clear_derived(track)
    observations = session.project.observations
    panel.methods.setCurrentIndex(1)
    actions.refresh()
    assert not panel.recurrenceButton.isEnabled()

    _ready(qtbot, panel)

    assert session.project.observations == observations
    assert all(session.derived_data(other.track_id, item.kind) == item for item in untouched)
    assert session.derived_data(track, 'world_position') is not None
    assert session.derived_data(track, 'signal_recurrence_x') is None
    assert session.derived_data(track, 'function_fit_x') is None
    assert actions.attempts.journal.attempts == []
    assert panel.recurrenceButton.isEnabled()
    assert 'world_position' in panel.contextLabel.text() and 'px' in panel.contextLabel.text()
    assert window.analysisTabs.currentIndex() == 1


def test_reference_direction_and_noise_preview_match_explicit_measurement(qtbot, synthetic_video_path):
    window, session, track = _periodic(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    project, undo = session.project, tuple(session._undo_stack)
    curve = panel.signalPlot.listDataItems()[0]
    view = np.array(panel.signalPlot.viewRange())
    np.testing.assert_allclose([line.value() for line in panel._eventLines], [.05, .25], atol=1e-9)

    panel.direction.setCurrentIndex(1)
    _ready(qtbot, panel)
    np.testing.assert_allclose([line.value() for line in panel._eventLines], [.15, .35], atol=1e-9)
    panel.level.setValue(12)
    _ready(qtbot, panel)
    np.testing.assert_allclose([line.value() for line in panel._eventLines], [.175, .375], atol=1e-9)
    assert panel.signalPlot.listDataItems()[0] is curve
    np.testing.assert_allclose(panel.signalPlot.viewRange(), view, atol=1e-9)
    panel.separation.setValue(.3)
    _ready(qtbot, panel)
    assert len(panel._eventLines) == 1
    panel.separation.setValue(0)
    panel.hysteresis.setValue(.5)
    _ready(qtbot, panel)
    expected = [line.value() for line in panel._eventLines]
    assert session.project == project and tuple(session._undo_stack) == undo
    assert actions.attempts.journal.attempts == []

    panel.recurrenceButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    record = session.derived_data(track, 'signal_recurrence_x')
    np.testing.assert_allclose([event['time_s'] for event in record.extra_fields['analysis']['summary']['events']], expected, atol=1e-9)
    assert not panel._eventPreview
    panel.level.setValue(14)
    _ready(qtbot, panel)
    assert session.derived_data(track, 'signal_recurrence_x') == record


def test_raw_interval_quantity_updates_source_and_preserves_old_measurement(qtbot, synthetic_video_path):
    window, session, track = _periodic(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    panel.recurrenceButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    record = session.derived_data(track, 'signal_recurrence_x')
    source = session.derived_data(track, 'world_position')
    session.mark_point(track, 2, pixel_x=12, pixel_y=21)
    window.analysisChanged.emit()
    _ready(qtbot, panel)
    assert session.derived_data(track, 'world_position').derived_id != source.derived_id
    current = session.derived_data(track, 'signal_recurrence_x')
    assert current.derived_id == record.derived_id and current.status == 'stale'
    panel.startFrame.setValue(1)
    _ready(qtbot, panel)
    assert 'frames 1–4' in panel.contextLabel.text()
    panel.quantityChoice.setCurrentText('y')
    _ready(qtbot, panel)
    assert 'y [px]' in panel.contextLabel.text()
    assert session.derived_data(track, 'signal_recurrence_y') is None
    assert actions.attempts.journal.attempts == []


@pytest.mark.parametrize('change', ['level', 'method', 'workspace', 'history', 'track'])
def test_late_recurrence_preview_cannot_replace_current_context(qtbot, synthetic_video_path, monkeypatch, change):
    window, session, track = _periodic(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    panel.recurrenceButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    record = session.derived_data(track, 'signal_recurrence_x')
    pending = Future()
    pending.set_running_or_notify_cancel()
    captured = []

    def submit(run, job, estimate, cancel):
        captured.append((run, job))
        return pending

    monkeypatch.setattr(actions.preview._executor, 'submit', submit)
    actions.preview.request(immediate=True)
    actions.preview.launch()
    run, job = captured[0]
    if change == 'level':
        panel.level.setValue(16)
    elif change == 'method':
        panel.methods.setCurrentIndex(0)
    elif change == 'workspace':
        window.setWorkspace('tracking')
    elif change == 'history':
        panel.latestButton.click()
    else:
        other = session.add_track(window.activeVideoId)
        actions.refresh()
        panel.trackChoice.setCurrentIndex(panel.trackChoice.findData(other.track_id))
    text = panel.jobLabel.text()
    pending.set_result(run(job, False, Event()))
    actions.preview.poll()
    assert panel.jobLabel.text() == text
    assert not panel._eventPreview
    assert session.derived_data(track, 'signal_recurrence_x') == record


def test_measure_does_not_wait_for_preview_worker(qtbot, synthetic_video_path, monkeypatch):
    window, session, track = _periodic(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    future = Future()
    future.set_running_or_notify_cancel()
    monkeypatch.setattr(actions.preview._executor, 'submit', lambda *args: future)
    actions.preview.request(immediate=True)
    actions.preview.launch()
    panel.recurrenceButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    assert session.derived_data(track, 'signal_recurrence_x') is not None
    assert not future.done()
    future.set_result(None)
    actions.preview.poll()
    assert 'Current calculation result' in panel.draftLabel.text()


def test_late_source_after_method_switch_is_not_applied(qtbot, synthetic_video_path, monkeypatch):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    session.clear_derived(track)
    panel.methods.setCurrentIndex(1)
    future = Future()
    future.set_running_or_notify_cancel()
    captured = []

    def submit(run, job, cancel):
        captured.append((run, job))
        return future

    monkeypatch.setattr(actions._executor, 'submit', submit)
    actions.preview.launch()
    panel.methods.setCurrentIndex(0)
    actions.preview.invalidate()
    run, job = captured[0]
    future.set_result(run(job, Event()))
    actions._poll()
    actions.refresh()
    assert session.derived_data(track, 'world_position') is None
    assert len(captured) == 1
    actions.preview.invalidate()
