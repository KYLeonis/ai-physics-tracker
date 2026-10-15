"""P6.3完整GUI编排回归：从非单摆数据到拟合 / 周期和只读导航。"""

from concurrent.futures import Future
from dataclasses import replace
from threading import Event

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


class _Probe:
    def probe(self, path, cancel=None):
        return TimingReport('cfr', 'synthetic', 5, 10., 10.)


def _window(qtbot, synthetic_video_path):
    window = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), _Probe())
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    session = window.analysisSession
    track = session.tracks[-1]
    for frame in range(5):
        session.mark_point(track.track_id, frame, pixel_x=10+frame*2, pixel_y=20)
    session.compute_kinematics(track.track_id)
    window.chartActions.refresh()
    window.setWorkspace('analysis')
    window.analysisTabs.setCurrentIndex(1)
    return window, session, track.track_id


def test_nonpendulum_fit_preview_publish_and_restore_settings(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    assert panel.sourceChoice.currentIndex() == 0
    panel.startFrame.setValue(1)
    panel.previewButton.click()
    assert 'Initial curve only' in panel.jobLabel.text()
    assert session.derived_data(track, 'function_fit_x') is None
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not actions.pending, timeout=5000)
    record = session.derived_data(track, 'function_fit_x')
    assert record is not None, panel.jobLabel.text()
    assert record.frames == (1, 2, 3, 4)
    assert 'RMSE' in panel.summary.toPlainText()
    assert 'a=20' in panel.summary.toPlainText()
    panel.editor.setText('c')
    assert 'Draft changed' in panel.draftLabel.text()
    assert 'a*t + b' in panel.summary.toPlainText()
    panel.restoreButton.click()
    assert panel.editor.text() == 'a*t + b'
    assert panel.startFrame.value() == 1
    assert panel.parameterTable.rowCount() == 2


def test_independent_crossing_measurement_and_visible_reference(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.methods.setCurrentIndex(1)
    panel.level.setValue(13)
    panel.recurrenceButton.click()
    qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
    record = session.derived_data(track, 'signal_recurrence_x')
    assert record is not None
    assert 'insufficient_events' in panel.summary.toPlainText()
    assert 'fundamental' not in panel.summary.toPlainText() or 'not inferred' in panel.summary.toPlainText()
    panel.referenceLine.setValue(12)
    panel.referenceLine.sigPositionChangeFinished.emit(panel.referenceLine)
    assert panel.level.value() == 12
    assert session.derived_data(track, 'function_fit_x') is None


def test_formula_edit_cancels_late_result_without_publishing(qtbot, synthetic_video_path, monkeypatch):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    pending = Future()
    captured = []
    def submit(run, job, cancel):
        captured.append((run, job, cancel))
        return pending
    monkeypatch.setattr(actions._executor, 'submit', submit)
    panel.fitButton.click()
    run, job, cancel = captured[0]
    result = run(job, Event())
    panel.editor.setText('a*t+b+0')
    assert cancel.is_set()
    pending.set_result(result)
    actions._poll()
    assert session.derived_data(track, 'function_fit_x') is None
    assert 'cancelled' in panel.jobLabel.text()


def test_upstream_change_cancels_and_stale_result_remains_readable(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
    session.compute_kinematics(track)
    window.refreshAnalysisHistory()
    window.chartActions.refresh()
    assert 'Saved result: stale' in panel.summary.toPlainText()
    assert 'RMSE' in panel.summary.toPlainText()


def test_invalid_formula_clears_initial_preview(qtbot, synthetic_video_path):
    window, _, _ = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.previewButton.click()
    assert panel.signalPlot.listDataItems()
    panel.editor.setText('a**')
    assert not panel.signalPlot.listDataItems()
    panel.fitButton.click()
    assert not window.chartActions.pending
    assert panel.jobLabel.text()


def test_formula_typing_owns_letter_and_space_keys_in_analysis(qtbot, synthetic_video_path):
    window, session, _ = _window(qtbot, synthetic_video_path)
    edit = window.chartActions.signalPanel.editor.formulaEdit
    edit.setFocus()
    edit.selectAll()
    before = session.project.observations
    qtbot.keyClicks(edit, 'A*sin(t) + c')
    assert edit.text() == 'A*sin(t) + c'
    assert session.project.observations == before
    assert not window._is_playing
