"""P6.3完整GUI编排回归：从非单摆数据到拟合 / 周期和只读导航。"""

from concurrent.futures import Future
from dataclasses import replace
from threading import Event
from PySide6.QtCore import Qt

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
    qtbot.waitUntil(lambda: 'Initial curve only' in panel.jobLabel.text())
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
    assert 'Current draft' in panel.draftLabel.text()
    assert 'Current draft' in panel.summary.toPlainText()
    assert panel.savedRecord(disk=False).extra_fields['analysis']['spec']['expression'] == 'a*t + b'
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
    assert 'Latest applied result: stale' in panel.summary.toPlainText()
    assert 'RMSE' in panel.summary.toPlainText()


def test_invalid_formula_clears_initial_preview(qtbot, synthetic_video_path):
    window, _, _ = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.previewButton.click()
    qtbot.waitUntil(lambda: bool(panel.signalPlot.listDataItems()))
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


def test_unreadable_cached_timing_metadata_remains_read_only(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
    record = session.derived_data(track, 'function_fit_x')
    from copy import deepcopy
    extras = deepcopy(record.extra_fields)
    extras['analysis']['source_snapshot']['extra_fields']['timing_context'] = 'future-scalar'
    changed = replace(record, extra_fields=extras)
    session._project = replace(session.project, derived=tuple(changed if item == record else item for item in session.project.derived))
    panel.displaySaved()
    assert 'timing metadata unreadable' in panel.summary.toPlainText()
    assert 'RMSE' in panel.summary.toPlainText()


def test_restoring_old_interval_does_not_silently_clamp_settings(qtbot, synthetic_video_path):
    window, _, _ = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
    panel.startFrame.setRange(2, 4)
    panel.endFrame.setRange(2, 4)
    panel.restoreButton.click()
    assert 'outside the working zone' in panel.jobLabel.text()
    assert 'Saved settings restored' not in panel.draftLabel.text()


def test_analysis_history_buttons_restore_results_without_enabling_raw_edit(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    before = session.project.observations
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
    assert panel.undoButton.isEnabled()
    assert not window.undoButton.isEnabled()
    panel.undoButton.click()
    assert session.derived_data(track, 'function_fit_x') is None
    assert panel.redoButton.isEnabled()
    panel.redoButton.click()
    assert session.derived_data(track, 'function_fit_x') is not None
    assert session.project.observations == before
    assert not window.undoButton.isEnabled()


def test_prominent_tools_entry_opens_editor_from_any_workspace_without_changing_data(qtbot, synthetic_video_path):
    window, session, _ = _window(qtbot, synthetic_video_path)
    observations, derived = session.project.observations, session.project.derived
    for workspace in ('setup', 'acquire', 'analysis'):
        window.analysisTabs.setCurrentIndex(0)
        window.setWorkspace(workspace)
        button = window.workflowHeader.analysisToolsButton
        assert button.isVisible() and button.isEnabled()
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert window.currentWorkspace == 'analysis'
        assert window.analysisTabs.currentIndex() == 1
        assert window.chartActions.signalPanel.editor.isVisible()
        assert not window.analysisToolsHint.isVisible()
        assert session.project.observations == observations
        assert session.project.derived == derived


def test_wheel_scrolls_page_and_only_control_wheel_zooms(qtbot, synthetic_video_path):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QStyle
    import numpy as np
    window, _, _ = _window(qtbot, synthetic_video_path)
    panel, scroll = window.chartActions.signalPanel, window._analysisToolsScroll
    panel.previewButton.click()
    qtbot.waitUntil(lambda: bool(panel.signalPlot.listDataItems()))
    bar = scroll.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    old_scroll = bar.value()
    before = np.array(panel.signalPlot.viewRange())
    def wheel(modifiers, target=None):
        event = QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(target or panel.signalPlot.viewport(), event)
    wheel(Qt.KeyboardModifier.NoModifier)
    assert bar.value() > old_scroll
    np.testing.assert_allclose(panel.signalPlot.viewRange(), before)
    old_scroll = bar.value()
    wheel(Qt.KeyboardModifier.ControlModifier)
    assert bar.value() == old_scroll
    assert not np.allclose(panel.signalPlot.viewRange(), before)
    assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert not bar.style().styleHint(QStyle.StyleHint.SH_ScrollBar_Transient, None, bar)
    panel.resetViewButton.click()
    np.testing.assert_allclose(panel.signalPlot.viewRange(), before)
    old_frame = panel.startFrame.value()
    wheel(Qt.KeyboardModifier.NoModifier, panel.startFrame)
    assert panel.startFrame.value() == old_frame


def test_reference_controls_keep_curve_and_hide_old_events_until_measure(qtbot, synthetic_video_path):
    import numpy as np
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.methods.setCurrentIndex(1)
    assert panel.signalPlot.listDataItems()
    panel.centerReferenceButton.click()
    assert panel.level.value() == 14
    assert panel.levelSlider.value() == 500
    panel.level.setValue(13)
    panel.recurrenceButton.click()
    qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)
    record = session.derived_data(track, 'signal_recurrence_x')
    assert len(panel._eventLines) == 1 and panel._eventLines[0].isVisible()
    curve = panel.signalPlot.listDataItems()[0]
    before = np.array(panel.signalPlot.viewRange())
    panel.referenceLine.setValue(15)
    assert panel.level.value() == 15
    assert panel.levelSlider.value() == 625
    assert panel.signalPlot.listDataItems()[0] is curve
    assert not panel._eventLines[0].isVisible()
    np.testing.assert_allclose(panel.signalPlot.viewRange(), before)
    assert session.derived_data(track, 'signal_recurrence_x') == record
    panel.level.setValue(250)
    assert 'outside signal' in panel.referenceStatus.text()
    panel.showReferenceButton.click()
    assert panel.signalPlot.viewRange()[1][1] >= 250
    panel.centerReferenceButton.click()
    assert panel.level.value() == 14
    np.testing.assert_allclose(panel.signalPlot.viewRange(), before)
    panel.level.setValue(13)
    assert panel._eventLines[0].isVisible()
    assert not panel.summary.isVisible()
    panel.detailsGroup.setChecked(True)
    assert panel.summary.isVisible()
    panel.sourceChoice.setCurrentIndex(1)
    assert not panel._eventLines
    assert session.derived_data(track, 'signal_recurrence_x') == record
    panel.sourceChoice.setCurrentIndex(0)
    assert len(panel._eventLines) == 1 and panel._eventLines[0].isVisible()
    panel.renderSamples([(0, 0., 0., 0., 0), (1, .1, .1, 1e-20, 0)], 'px')
    assert panel.signalPlot.viewRange()[1][1] - panel.signalPlot.viewRange()[1][0] < 1e-19
    panel.level.setValue(250)
    assert panel.levelSlider.value() == 1000
    assert panel.level.value() == 250
    panel.level.setValue(13)
    assert not panel._eventLines  # 相同配方也不能把旧事件叠在不同样本上。


def test_analysis_tools_fit_narrow_viewport_and_initial_curve_cannot_hide_signal(qtbot, synthetic_video_path):
    window, _, _ = _window(qtbot, synthetic_video_path)
    window.resize(1024, 640)
    panel = window.chartActions.signalPanel
    panel.editor.setText('c')
    panel.parameterTable.item(0, 1).setText('1e24')
    panel.previewButton.click()
    qtbot.waitUntil(lambda: bool(panel.signalPlot.listDataItems()))
    scroll = window._analysisToolsScroll
    assert panel.width() <= scroll.viewport().width()
    window.resize(700, 640)
    qtbot.waitUntil(lambda: scroll.viewport().width() >= panel.minimumSizeHint().width())
    assert panel.width() <= scroll.viewport().width()
    assert scroll.horizontalScrollBar().maximum() == 0
    assert panel.signalPlot.width() <= panel.width()
    low, high = panel.signalPlot.viewRange()[1]
    assert low < 10 < 18 < high < 100
    assert not panel.signalPlot.getAxis('left').autoSIPrefix
    assert panel.residualPlot.isHidden()
    panel.plotTabs.setCurrentIndex(1)
    assert panel.residualPlot.isVisible()


def test_live_reference_edit_cancels_pending_measurement_without_publishing(qtbot, synthetic_video_path, monkeypatch):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    panel.methods.setCurrentIndex(1)
    panel.centerReferenceButton.click()
    pending, captured = Future(), []
    def submit(run, job, cancel):
        captured.append((run, job, cancel))
        return pending
    monkeypatch.setattr(actions._executor, 'submit', submit)
    panel.recurrenceButton.click()
    run, job, cancel = captured[0]
    result = run(job, Event())
    panel.referenceLine.setValue(15)
    assert cancel.is_set()
    assert panel.level.value() == 15
    pending.set_result(result)
    actions._poll()
    assert session.derived_data(track, 'signal_recurrence_x') is None
    assert panel.referenceLine in panel.signalPlot.items()


def test_reopened_near_cfr_explains_disabled_fit_and_confirmation_is_visible_in_analysis(
    qtbot, synthetic_video_path, tmp_path, monkeypatch,
):
    from PySide6.QtWidgets import QMessageBox
    window, session, _ = _window(qtbot, synthetic_video_path)
    root = tmp_path / 'reopened-near-cfr'
    session.save_as(root)
    original_points = session.project.observations
    class NearProbe:
        def probe(self, path, cancel=None):
            return TimingReport('near_cfr', 'bounded near-CFR', 5, 10., 10.,
                                max_grid_error_s=.0001, max_interval_error_s=.0002)
    window._timing_probe = NearProbe()
    token, service = window.candidateService()
    window.adoptPrepared(service.open_project(root, Event()), token)
    window.trackList.setCurrentRow(0)
    window.openAnalysisTools()
    qtbot.wait(20)
    session, panel = window.analysisSession, window.chartActions.signalPanel
    panel.editor.setText('A*exp(-gamma*t)*cos(omega*t+phi)+y0')
    assert not panel.fitButton.isEnabled()
    assert panel.fitReadinessLabel.isVisible()
    assert 'Timing not authorized' in panel.fitReadinessLabel.text()
    assert 'Timing not authorized' in panel.fitButton.toolTip()
    assert 'not authorized' in window._analysisSourceLabel.text()
    assert 'verified CFR' not in window._analysisSourceLabel.text()
    assert window.timingLabel.isVisible() and window.timingButton.isVisible()
    assert window.timingButton.parent() is window._analysisReferenceHost
    assert 'Use approximate timing' in window.timingButton.text()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    window.timingButton.click()
    assert not session.can_measure(window.activeVideoId)
    assert not panel.fitButton.isEnabled()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    window.timingButton.click()
    qtbot.waitUntil(panel.fitButton.isEnabled)
    assert 'approximate timing' in window._analysisSourceLabel.text()
    assert panel.fitReadinessLabel.isHidden()
    assert window.timingButton.isHidden()
    panel.previewButton.click()
    qtbot.waitUntil(lambda: 'recompute source first' in panel.jobLabel.text())
    assert 'recompute source first' in panel.jobLabel.text()
    session.compute_kinematics(session.tracks[0].track_id)
    window.chartActions.refresh()
    panel.previewButton.click()
    qtbot.waitUntil(lambda: 'Initial curve only' in panel.jobLabel.text())
    assert 'Initial curve only' in panel.jobLabel.text()
    assert session.project.observations == original_points
    for workspace in ('acquire', 'analysis', 'setup', 'analysis'):
        window.setWorkspace(workspace)
        assert window.timingLabel.isVisible()
        assert window.timingButton.isHidden()
        if workspace != 'analysis':
            assert window._videoColumn.indexOf(window.timingLabel) == 1
            assert window._videoColumn.indexOf(window.timingButton) == 2
            assert window._videoColumn.indexOf(window.videoView) == 3
