"""P6.4：三列表格 / 方法、旧记录及草稿生命周期。"""

from copy import deepcopy
from threading import Event

from PySide6.QtCore import Qt

from tests.gui.test_signal_analysis import _window
from tests.gui.test_guided_fit import _preview
from ai_physics_tracker.gui.fit_explanation import parameter_error_rows


def _fit(qtbot, window):
    panel = window.chartActions.signalPanel
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not window.chartActions.pending)
    assert panel.parameterResults.rowCount() == 2
    return panel


def test_three_columns_method_and_draft_never_retain_recorded_se(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = _fit(qtbot, window)
    assert [panel.parameterResults.horizontalHeaderItem(i).text().replace('\n', ' ') for i in range(3)] == [
        'Parameter', 'Estimate', 'Conditional standard error']
    assert not panel.parameterResults.isHidden()
    assert float(panel.parameterResults.item(0, 2).text()) >= 0
    panel.errorMethodToggle.setChecked(True)
    assert not panel.errorMethod.isHidden()
    assert 'independent' in panel.errorMethod.text()
    assert 'systematics' in panel.errorMethod.text()
    assert 'residual scatter' in panel.resultLabel.text()
    before = session.project
    panel.parameterTable.item(0, 1).setText('7')
    assert panel.parameterResults.isHidden() and panel.parameterResults.rowCount() == 0
    assert panel.errorMethod.isHidden()
    _preview(qtbot, panel)
    assert panel.parameterResults.isHidden() and session.project == before
    panel.latestButton.click()
    assert panel.parameterResults.rowCount() == 2
    panel.returnDraftButton.click()
    assert panel.parameterResults.isHidden() and panel.parameterResults.rowCount() == 0


def test_fixed_and_unsupported_source_and_conversion_are_explicit(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    panel.sourceChoice.setCurrentIndex(1)
    panel.parameterTable.item(1, 4).setCheckState(Qt.CheckState.Checked)
    panel.resultName.setText('inverse'); panel.resultFormula.setText('1/a')
    _preview(qtbot, panel)
    _fit(qtbot, window)
    assert 'Unsupported source' in panel.parameterResults.item(0, 2).text()
    assert panel.parameterResults.item(1, 2).text() == 'Fixed'
    assert 'value only, uncertainty not propagated' in panel.resultLabel.text()
    panel.methods.setCurrentIndex(1)
    assert panel.parameterResults.isHidden()


def test_legacy_unknown_and_stale_statistics_are_readonly(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = _fit(qtbot, window)
    record = session.derived_data(track, 'function_fit_x')
    metadata = deepcopy(record.extra_fields['analysis'])
    del metadata['summary']['parameter_uncertainty']
    assert all(row[2] == 'Not recorded' for row in parameter_error_rows(metadata))
    metadata['summary']['parameter_uncertainty'] = {'version': 99}
    assert all('Unsupported' in row[2] for row in parameter_error_rows(metadata))
    session.mark_point(track, 1, pixel_x=100, pixel_y=100)
    panel.renderSaved(session.derived_data(track, 'function_fit_x'))
    assert 'stale' in panel.parameterResultsLabel.text()
    assert 'historical inputs only' in panel.parameterResultsLabel.text()
    panel.setContext(None, None)
    assert panel.parameterResults.isHidden()


def test_attempt_se_is_recorded_and_old_attempt_does_not_gain_statistics(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = _fit(qtbot, window)
    attempt = window.chartActions.attempts.journal.attempts[-1]
    recorded = deepcopy(attempt['summary']['parameter_uncertainty'])
    panel.history.viewAttempt(attempt)
    qtbot.waitUntil(lambda: panel.history._future is None)
    assert panel.parameterResults.rowCount() == 2
    assert attempt['summary']['parameter_uncertainty'] == recorded
    panel.returnDraftButton.click()
    legacy = deepcopy(attempt)
    del legacy['summary']['parameter_uncertainty']
    panel.history.viewAttempt(legacy)
    qtbot.waitUntil(lambda: panel.history._future is None)
    assert all(panel.parameterResults.item(row, 2).text() == 'Not recorded' for row in range(2))
    assert 'parameter_uncertainty' not in legacy['summary']


def test_recorded_source_conflict_hides_statistics_in_saved_and_attempt_views(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = _fit(qtbot, window)
    metadata = deepcopy(session.derived_data(track, 'function_fit_x').extra_fields['analysis'])
    metadata['source_snapshot']['kind'] = 'smoothed_position'
    assert all('conflicts with recorded source' in row[2] for row in parameter_error_rows(metadata))
    del metadata['source_snapshot']
    metadata['selection']['smoothed'] = True
    assert all('conflicts with recorded source' in row[2] for row in parameter_error_rows(metadata))


def test_snapshot_and_selection_conflict_cannot_display_a_parameter_error(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    _fit(qtbot, window)
    metadata = deepcopy(session.derived_data(track, 'function_fit_x').extra_fields['analysis'])
    metadata['selection']['smoothed'] = True
    assert all('conflicts with recorded source' in row[2] for row in parameter_error_rows(metadata))


def test_wide_fit_controls_have_reachable_right_edge_and_horizontal_wheel(qtbot, synthetic_video_path):
    from PySide6.QtCore import QPoint, QPointF, QCoreApplication
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QCheckBox, QPushButton
    window, _, _ = _window(qtbot, synthetic_video_path)
    panel = window.chartActions.signalPanel
    font = panel.font()
    font.setPointSize(18)
    panel.setFont(font)
    for box in panel.editor.findChildren(QCheckBox):
        box.setChecked(True)
    scroll = panel.controlsScroll
    qtbot.waitUntil(lambda: scroll.widget().width() > scroll.viewport().width())
    bar = scroll.horizontalScrollBar()
    assert bar.isVisible()
    assert bar.maximum() > 0
    bar.setValue(0)
    initial = panel.startFrame.value()
    wheel = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(-120, 0), QPoint(),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.ScrollUpdate, False)
    QCoreApplication.sendEvent(panel.startFrame, wheel)
    assert bar.value() > 0
    assert panel.startFrame.value() == initial
    bar.setValue(bar.maximum())
    rightmost = max(panel.editor.findChildren(QPushButton),
                    key=lambda button: button.mapTo(scroll.widget(), QPoint(button.width()-1, 0)).x())
    edge = rightmost.mapTo(scroll.viewport(), QPoint(rightmost.width()-1, 0)).x()
    assert 0 <= edge < scroll.viewport().width()
