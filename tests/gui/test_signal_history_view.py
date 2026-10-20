"""历史选择同步整份只读表单，同时保留草稿和工程状态。"""

from concurrent.futures import Future
from copy import deepcopy
from uuid import uuid4

from PySide6.QtCore import Qt
import pytest

from tests.gui.test_signal_analysis import _window


def _fit(qtbot, actions):
    actions.signalPanel.fitButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    assert actions.attempts.journal.attempts[-1]['status'] == 'completed'


def _choose(panel, identity):
    index = panel.attemptChoice.findData(identity)
    assert index >= 0
    panel.attemptChoice.setCurrentIndex(index)
    panel.attemptChoice.activated.emit(index)


def test_saved_view_syncs_setup_and_return_preserves_even_invalid_draft(qtbot, synthetic_video_path, tmp_path):
    window, session, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    panel.startFrame.setValue(1)
    panel.parameterTable.item(0, 1).setText('20')
    panel.parameterTable.item(0, 4).setCheckState(Qt.CheckState.Checked)
    panel.parameterTable.item(1, 2).setText('0')
    panel.parameterTable.item(1, 3).setText('30')
    panel.budget.setValue(321)
    panel.resultName.setText('speed'); panel.resultFormula.setText('a')
    _fit(qtbot, actions)
    recorded = panel.fitSpec()
    session.save_as(tmp_path/'saved'); actions.syncJournal(saved=True); actions.refresh()
    panel.editor.setText('c')
    panel.parameterTable.item(0, 1).setText('not a number')
    panel.startFrame.setValue(2)
    panel.resultName.clear(); panel.resultFormula.clear()
    draft = panel.history.capture()
    before = session.project, session.is_dirty, session.can_undo_analysis, deepcopy(actions.attempts.journal.attempts)

    panel.previousButton.click()

    assert panel.fitSpec() == recorded
    assert panel.startFrame.value() == 1
    assert panel.resultFormula.text() == 'a'
    assert panel.parameterTable.horizontalHeaderItem(1).text() == 'Recorded initial'
    assert not panel.editor.isEnabled() and not panel.fitButton.isEnabled()
    assert not panel.undoButton.isEnabled()
    assert panel.attemptChoice.currentIndex() == -1
    assert 'frames 1–4' in window._analysisSourceLabel.text()
    card = window.analysisPurposeTaskCard()
    assert card.primary.action_id == 'analysis_return_draft'
    assert card.secondary[0].enabled
    assert 'Viewing recorded analysis' in window.analysisPurposeLabel.text()
    panel.returnDraftButton.click()
    assert panel.history.capture() == draft
    assert (session.project, session.is_dirty, session.can_undo_analysis, actions.attempts.journal.attempts) == before


def test_bottom_selector_changes_formula_curve_and_target_without_fitting(qtbot, synthetic_video_path, monkeypatch):
    window, session, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    linear = actions.attempts.journal.attempts[-1]['id']
    panel.quantityChoice.setCurrentText('y')
    panel.editor.setText('c')
    _fit(qtbot, actions)
    constant = actions.attempts.journal.attempts[-1]['id']
    panel.editor.setText('d*t')
    draft = panel.history.capture()
    before = session.project, session.is_dirty, session.can_undo_analysis, deepcopy(actions.attempts.journal.attempts)
    def forbidden(*args, **kwargs):
        raise AssertionError('Selecting history must not run the fitter')
    monkeypatch.setattr(actions._executor, 'submit', forbidden)

    _choose(panel, linear)
    qtbot.waitUntil(lambda: not panel.history.pending)
    assert panel.quantityChoice.currentText() == 'x'
    assert panel.editor.text() == 'a*t + b'
    assert 'a=20' in panel.modelLabel.text()
    assert len(panel.signalPlot.listDataItems()) == 2, panel.jobLabel.text()
    assert panel.signalPlot.listDataItems()[-1].yData[-1] == pytest.approx(18)
    assert 'current matching source' in panel.jobLabel.text()
    _choose(panel, constant)
    qtbot.waitUntil(lambda: not panel.history.pending)
    assert panel.quantityChoice.currentText() == 'y'
    assert panel.editor.text() == 'c'
    assert panel.signalPlot.listDataItems()[-1].yData[-1] == pytest.approx(20)
    assert 'no time variation' in panel.resultLabel.text()
    panel.returnDraftButton.click()
    assert panel.history.capture() == draft
    assert (session.project, session.is_dirty, session.can_undo_analysis, actions.attempts.journal.attempts) == before


@pytest.mark.parametrize('unavailable', ['rejected', 'source_changed'])
def test_unavailable_attempt_clears_previous_curve_and_explains(qtbot, synthetic_video_path, unavailable):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    identity = actions.attempts.journal.attempts[-1]['id']
    if unavailable == 'rejected':
        panel.editor.setText('sin('); panel.fitButton.click()
        identity = actions.attempts.journal.attempts[-1]['id']
    else:
        session.mark_point(track, 0, pixel_x=999, pixel_y=20)
        session.compute_kinematics(track)
        actions.refresh()
    _choose(panel, identity)
    qtbot.waitUntil(lambda: not panel.history.pending)
    assert not panel.signalPlot.listDataItems()
    assert not panel.residualPlot.listDataItems()
    assert panel._previewRange is None
    assert 'No historical curve available' in panel.resultLabel.text()
    assert panel.returnDraftButton.isVisible()
    assert 'source' in panel.jobLabel.text() if unavailable == 'source_changed' else 'no recorded FitSpec' in panel.jobLabel.text()


@pytest.mark.parametrize('change', ['return_to_draft', 'timing_revoked'])
def test_late_history_delivery_respects_draft_and_current_authorization(qtbot, synthetic_video_path, monkeypatch, change):
    window, session, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    attempt = deepcopy(actions.attempts.journal.attempts[-1])
    panel.editor.setText('c')
    actions.preview.invalidate()
    future = Future(); future.set_running_or_notify_cancel()
    work = []
    def submit(run, *args):
        work.append((run, args))
        return future
    panel.history.bind(window, submit)
    _choose(panel, attempt['id'])
    if change == 'return_to_draft':
        panel.returnDraftButton.click()
    else:
        session._verified_videos.clear()
    actions.preview.invalidate()
    run, args = work[0]
    future.set_result(run(*args))
    panel.history.poll()
    if change == 'return_to_draft':
        assert panel.editor.text() == 'c'
        assert not panel.history.active
    else:
        assert panel.history.active
        assert 'Project context changed' in panel.jobLabel.text()
    assert not panel.signalPlot.listDataItems()


def test_history_controls_stay_unavailable_during_fit(qtbot, synthetic_video_path, monkeypatch):
    window, _, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    future = Future()
    monkeypatch.setattr(actions._executor, 'submit', lambda *args: future)
    panel.fitButton.click()
    assert not panel.latestButton.isEnabled()
    assert not panel.previousButton.isEnabled()
    assert not panel.attemptChoice.isEnabled()
    panel.cancelButton.click()
    future.cancel(); actions._poll()


def test_foreign_or_missing_track_cannot_use_current_video_for_history(qtbot, synthetic_video_path):
    window, session, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    attempt = deepcopy(actions.attempts.journal.attempts[-1])
    attempt['track_id'] = str(uuid4())
    before = session.project
    frames = []
    panel.frameRequested.connect(frames.append)

    panel.history.viewAttempt(attempt)

    assert 'another video or a missing track' in panel.jobLabel.text()
    assert not panel.signalPlot.listDataItems()
    panel._requestSampleFrame(2)
    assert not frames
    panel.restoreButton.click()
    assert panel.history.active
    assert session.project is before
    panel.returnDraftButton.click()
    assert not panel.history.active


def test_new_history_selection_discards_late_result_from_previous_selection(qtbot, synthetic_video_path, monkeypatch):
    window, _, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    first = deepcopy(actions.attempts.journal.attempts[-1])
    panel.editor.setText('c'); _fit(qtbot, actions)
    second = deepcopy(actions.attempts.journal.attempts[-1])
    actions.preview.invalidate()
    work = []
    def submit(run, *args):
        future = Future(); future.set_running_or_notify_cancel()
        work.append((future, run, args))
        return future
    panel.history.bind(window, submit)
    panel.history.viewAttempt(first)
    panel.history.viewAttempt(second)
    future, run, args = work[0]
    future.set_result(run(*args))
    panel.history.poll()
    assert panel.editor.text() == 'c'
    assert not panel.signalPlot.listDataItems()
    future, run, args = work[1]
    future.set_result(run(*args))
    panel.history.poll()
    assert len(panel.signalPlot.listDataItems()) == 2
    assert 'x(t) = c' in panel.modelLabel.text()


def test_leaving_analysis_returns_to_draft_before_acquire_can_change_source(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    panel.editor.setText('c')
    panel.latestButton.click()
    assert panel.history.active

    window.setWorkspace('acquire')

    assert not panel.history.active
    assert panel.editor.text() == 'c'
    assert panel.editor.isEnabled()
    assert not panel.history.pending
    assert not panel.signalPlot.listDataItems()
    session.mark_point(track, 0, pixel_x=99, pixel_y=20)
    session.compute_kinematics(track)
    window.setWorkspace('analysis')
    assert not panel.history.active
    assert panel.editor.text() == 'c'


def test_adopted_crossing_setup_previews_current_events_without_measuring(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    panel.methods.setCurrentIndex(1); panel.level.setValue(13)
    panel.recurrenceButton.click(); qtbot.waitUntil(lambda: not actions.pending)
    record = session.derived_data(track, 'signal_recurrence_x')
    assert record.extra_fields['analysis']['summary']['events']
    panel.latestButton.click()
    assert panel._eventLines

    panel.restoreButton.click()

    assert 'no measured result published' in panel.draftLabel.text()
    assert not panel._eventLines
    assert not panel._eventSamplesMatch
    panel.showSourceButton.click()
    panel.level.setValue(12); panel.level.setValue(13)
    assert not panel._eventLines
    qtbot.waitUntil(lambda: panel._eventPreview)
    assert panel._eventLines
    assert session.derived_data(track, 'signal_recurrence_x') == record
    panel.recurrenceButton.click(); qtbot.waitUntil(lambda: not actions.pending)
    assert panel._eventLines
    assert not panel._eventPreview


@pytest.mark.parametrize('change', [
    'applied', 'saved', 'adopt', 'workspace', 'reset', 'shutdown',
    'video', 'generation', 'source_changed', 'unreadable_saved',
])
def test_history_delivery_after_transition_cannot_replace_display(
        qtbot, synthetic_video_path, tmp_path, monkeypatch, change):
    from dataclasses import replace

    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    session.save_as(tmp_path / 'saved')
    actions.syncJournal(saved=True)
    actions.refresh()
    attempt = deepcopy(actions.attempts.journal.attempts[-1])
    panel.editor.setText('c')
    future = Future()
    future.set_running_or_notify_cancel()
    work = []

    def submit(run, *args):
        work.append((run, args))
        return future

    panel.history.bind(window, submit)
    original_video = window.activeVideoId
    _choose(panel, attempt['id'])
    if change == 'applied':
        panel.latestButton.click()
    elif change == 'saved':
        panel.previousButton.click()
    elif change == 'adopt':
        panel.restoreButton.click()
    elif change == 'workspace':
        window.setWorkspace('acquire')
    elif change == 'reset':
        actions.resetContext()
    elif change == 'shutdown':
        actions.shutdown()
    elif change == 'video':
        window._annotation_video_id = uuid4()
    elif change == 'generation':
        window._delivery_generation += 1
    elif change == 'source_changed':
        session.mark_point(track, 0, pixel_x=999, pixel_y=20)
    else:
        record = replace(panel.savedRecord(disk=False), extra_fields={'analysis': {'version': 999}})
        monkeypatch.setattr(panel, 'savedRecord', lambda **kwargs: record)
        panel.latestButton.click()
    display = (panel.editor.text(), panel.resultLabel.text(), panel.summary.toPlainText(),
               tuple(panel.signalPlot.listDataItems()))
    state = session.project, session.is_dirty, session.can_undo_analysis, deepcopy(actions.attempts.journal.attempts)

    run, args = work[0]
    future.set_result(run(*args))
    panel.history.poll()
    if change == 'video':
        window._annotation_video_id = original_video

    assert not panel.history.pending
    assert (panel.editor.text(), panel.resultLabel.text(), panel.summary.toPlainText(),
            tuple(panel.signalPlot.listDataItems())) == display
    assert (session.project, session.is_dirty, session.can_undo_analysis, actions.attempts.journal.attempts) == state
    if change in ('video', 'generation', 'source_changed'):
        assert 'Project context changed' in panel.jobLabel.text()


def test_history_delivery_waits_for_save_before_display(qtbot, synthetic_video_path):
    window, _, _ = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    _fit(qtbot, actions)
    attempt = deepcopy(actions.attempts.journal.attempts[-1])
    future = Future()

    def submit(run, *args):
        future.set_result(run(*args))
        return future

    panel.history.bind(window, submit)
    _choose(panel, attempt['id'])
    window.projectActions.busy = True
    try:
        panel.history.poll()
        assert panel.history.pending
        assert not panel.signalPlot.listDataItems()
    finally:
        window.projectActions.busy = False
    panel.history.poll()
    assert not panel.history.pending
    assert len(panel.signalPlot.listDataItems()) == 2
