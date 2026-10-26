"""P6.4：四列表格 / 方法、旧记录及草稿生命周期。"""

from copy import deepcopy
from threading import Event

import pytest
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


def test_four_columns_method_and_draft_never_retain_recorded_statistics(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = _fit(qtbot, window)
    assert [panel.parameterResults.horizontalHeaderItem(i).text().replace('\n', ' ') for i in range(4)] == [
        'Parameter', 'Estimate', 'Conditional standard error', '95% confidence interval (local)']
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


def test_measured_fit_displays_recorded_95_percent_bounds_and_v1_does_not_gain_them(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    for frame, noise in enumerate((.1, -.1, -.1, .1, 0.)):
        session.mark_point(track, frame, pixel_x=10+frame*2+noise, pixel_y=20)
    session.compute_kinematics(track)
    window.chartActions.refresh()
    panel = _fit(qtbot, window)
    assert panel.parameterResults.columnCount() == 4
    for row in range(panel.parameterResults.rowCount()):
        text = panel.parameterResults.item(row, 3).text()
        assert text.startswith('[') and text.endswith(']')
        assert len(text.split(',')) == 2
    assert 'approximately normal residuals' in panel.errorMethod.text()
    assert 'not a joint region' in panel.errorMethod.text()
    metadata = deepcopy(session.derived_data(track, 'function_fit_x').extra_fields['analysis'])
    stats = metadata['summary']['parameter_uncertainty']
    stats['version'] = 1
    del stats['confidence_level'], stats['interval_method']
    for entry in stats['parameters']:
        del entry['confidence_interval'], entry['interval_reason']
    rows = parameter_error_rows(metadata)
    assert all(float(row[2]) > 0 and row[3] == 'Not recorded' for row in rows)


def test_interval_bounds_fit_in_cells_and_header_can_be_dragged(qtbot, synthetic_video_path):
    from PySide6.QtCore import QPoint
    window, session, track = _window(qtbot, synthetic_video_path)
    for frame, noise in enumerate((.1, -.1, -.1, .1, 0.)):
        session.mark_point(track, frame, pixel_x=10+frame*2+noise, pixel_y=20)
    session.compute_kinematics(track)
    window.chartActions.refresh()
    panel = window.chartActions.signalPanel
    font = panel.font()
    font.setPointSize(18)
    panel.setFont(font)
    _fit(qtbot, window)
    table = panel.parameterResults
    # 独立窄视口用于真实表头拖动，不依赖外层页面的纵向滚动位置。
    table.setParent(None)
    table.setFont(font)
    qtbot.addWidget(table)
    table.resize(300, 175)
    table.show()
    panel.renderParameterStatistics(session.derived_data(track, 'function_fit_x').extra_fields['analysis'])
    qtbot.waitUntil(lambda: table.horizontalScrollBar().maximum() > 0)
    for row in range(table.rowCount()):
        bounds = table.item(row, 3).text().split(', ')
        assert len(bounds) == 2
        assert all(table.fontMetrics().horizontalAdvance(bound) + 8 <= table.columnWidth(3) for bound in bounds)
        assert table.rowHeight(row) >= table.fontMetrics().height()
    header = table.horizontalHeader()
    before = table.columnWidth(0)
    divider = QPoint(header.sectionViewportPosition(0) + before - 1, header.height() // 2)
    qtbot.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=divider)
    qtbot.mouseMove(header.viewport(), divider + QPoint(40, 0))
    qtbot.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=divider + QPoint(40, 0))
    assert table.columnWidth(0) >= before + 30
    table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
    assert table.visualItemRect(table.item(0, 3)).right() < table.viewport().width()


def test_result_pane_and_controls_resize_by_drag_and_table_fills_width(qtbot, synthetic_video_path):
    from PySide6.QtCore import QPoint
    from ai_physics_tracker.gui.signal_analysis_panel import SignalAnalysisPanel
    window, session, track = _window(qtbot, synthetic_video_path)
    _fit(qtbot, window)
    panel = SignalAnalysisPanel()
    qtbot.addWidget(panel)
    panel.resize(1350, 1050)
    panel.renderParameterStatistics(session.derived_data(track, 'function_fit_x').extra_fields['analysis'])
    panel.show()
    qtbot.waitUntil(lambda: panel.resultSplitter.isVisible())
    table = panel.parameterResults
    qtbot.waitUntil(lambda: table.horizontalHeader().length() >= table.viewport().width())
    assert table.columnWidth(3) >= table.fontMetrics().horizontalAdvance(table.item(0, 3).text()) + 8
    assert table.height() > 175
    for splitter, delta, dimension in (
            (panel.workspaceSplitter, QPoint(-80, 0), 'width'),
            (panel.resultSplitter, QPoint(0, -80), 'height')):
        before = splitter.sizes()
        handle = splitter.handle(1)
        center = handle.rect().center()
        qtbot.mousePress(handle, Qt.MouseButton.LeftButton, pos=center)
        qtbot.mouseMove(handle, center + delta)
        qtbot.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=center + delta)
        qtbot.waitUntil(lambda: abs(splitter.sizes()[0] - before[0]) >= 50)
        assert getattr(splitter.widget(1), dimension)() > before[1]
    width = table.viewport().width()
    panel.resize(1550, 1150)
    qtbot.waitUntil(lambda: table.viewport().width() > width)
    assert table.horizontalHeader().length() >= table.viewport().width()
    before = panel.resultSplitter.sizes()[1]
    panel.editor.setText('a*t + b + c')
    assert panel.parameterResultsPane.isHidden()
    qtbot.waitUntil(lambda: panel.resultSplitter.sizes()[1] == 0)
    assert before > 0


@pytest.mark.parametrize('target', ('cell', 'indicator', 'keyboard'))
def test_fixed_help_leads_from_recorded_setup_to_held_initial_value(qtbot, synthetic_video_path, target):
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
    window, session, track = _window(qtbot, synthetic_video_path)
    panel = _fit(qtbot, window)
    panel.restoreButton.click()
    assert panel.parameterTable.isColumnHidden(4)
    assert panel.fixedParameterHelp.isHidden()
    panel.parameterOptions.click()
    assert not panel.parameterTable.isColumnHidden(4)
    assert not panel.fixedParameterHelp.isHidden()
    assert 'Initial' in panel.fixedParameterHelp.text() and 'Fixed' in panel.fixedParameterHelp.text()
    assert 'not the previous fitted Estimate' in panel.parameterOptions.toolTip()
    panel.parameterTable.item(1, 1).setText('3')
    fixed = panel.parameterTable.item(1, 4)
    panel.parameterTable.scrollToItem(fixed)
    rect = panel.parameterTable.visualItemRect(fixed)
    if target == 'keyboard':
        panel.parameterTable.setCurrentItem(fixed)
        panel.parameterTable.setFocus()
        playback = window.playButton.text()
        qtbot.keyClick(panel.parameterTable, Qt.Key.Key_Space)
        assert window.playButton.text() == playback
    else:
        point = rect.center()
        if target == 'indicator':
            option = QStyleOptionViewItem()
            option.initFrom(panel.parameterTable)
            panel.parameterTable.itemDelegate().initStyleOption(option, panel.parameterTable.indexFromItem(fixed))
            option.rect = rect
            point = panel.parameterTable.style().subElementRect(
                QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, panel.parameterTable).center()
        qtbot.mouseClick(panel.parameterTable.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert fixed.checkState() == Qt.CheckState.Checked
    assert panel.parameterTable.item(0, 4).checkState() == Qt.CheckState.Unchecked
    _preview(qtbot, panel)
    _fit(qtbot, window)
    assert panel.parameterResults.item(1, 1).text() == '3'
    assert panel.parameterResults.item(1, 2).text() == 'Fixed'
    assert panel.parameterResults.item(1, 3).text() == 'Fixed'
    for column in range(4):
        assert panel.parameterResults.horizontalHeaderItem(column).toolTip()
        assert panel.parameterResults.item(0, column).text().replace('\n', ' ') in panel.parameterResults.item(0, column).toolTip()


def test_fixed_click_respects_history_lock_and_works_after_adopting_setup(qtbot, synthetic_video_path):
    window, session, _ = _window(qtbot, synthetic_video_path)
    panel = _fit(qtbot, window)
    panel.latestButton.click()
    panel.parameterOptions.setChecked(True)
    table = panel.parameterTable
    assert panel.history.active and not table.isEnabled()
    before = session.project
    fixed = table.item(1, 4)
    table.scrollToItem(fixed)
    qtbot.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(fixed).center())
    assert fixed.checkState() == Qt.CheckState.Unchecked
    panel.restoreButton.click()
    assert not panel.history.active and table.isEnabled()
    panel.parameterOptions.setChecked(True)
    fixed = table.item(1, 4)
    table.scrollToItem(fixed)
    for expected in (Qt.CheckState.Checked, Qt.CheckState.Unchecked):
        qtbot.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(fixed).center())
        assert fixed.checkState() == expected
        assert panel.fitSpec().parameters[1].fixed == (expected == Qt.CheckState.Checked)
    assert session.project == before
