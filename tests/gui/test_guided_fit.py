"""P6.3.1完整草稿、初值保护、结果解释及尝试留痕回归。"""
from concurrent.futures import Future
import pytest
from PySide6.QtCore import Qt
from tests.gui.test_signal_analysis import _window


def _preview(qtbot,panel):
    qtbot.waitUntil(lambda: 'Initial curve only' in panel.jobLabel.text(),timeout=5000)


def test_live_preview_estimates_and_protects_manual_values(qtbot,synthetic_video_path):
    window,session,track = _window(qtbot,synthetic_video_path)
    panel, actions = window.chartActions.signalPanel, window.chartActions
    panel.editor._selectExample('a*t+b')
    _preview(qtbot,panel)
    assert abs(panel.fitSpec().parameters[0].initial-20) < 1e-7
    assert 'Estimated from data' in panel.estimateLabel.text()
    assert session.derived_data(track,'function_fit_x') is None
    panel.parameterTable.item(0,1).setText('7')
    panel.editor._selectExample('a*t+b')
    _preview(qtbot,panel)
    assert panel.fitSpec().parameters[0].initial == 7
    panel.startFrame.setValue(1)
    _preview(qtbot,panel)
    assert panel.fitSpec().parameters[0].initial == 7
    panel.estimateButton.click()
    _preview(qtbot,panel)
    assert abs(panel.fitSpec().parameters[0].initial-20)<1e-7
    assert actions.attempts.journal.attempts == []


def test_constant_formula_and_partial_conversion_explain_actual_result(qtbot,synthetic_video_path,tmp_path):
    window,session,track = _window(qtbot,synthetic_video_path)
    panel,actions = window.chartActions.signalPanel,window.chartActions
    panel.editor.setText('theta')
    panel.resultName.setText('T'); panel.resultFormula.setText('2*pi/Omega')
    _preview(qtbot,panel)
    assert 'constant level' in panel.meaningLabel.text()
    panel.fitButton.click()
    qtbot.waitUntil(lambda: not actions.pending)
    assert 'no time variation' in panel.resultLabel.text()
    assert 'T was not calculated' in panel.resultLabel.text()
    assert 'Omega' in panel.resultLabel.text()
    assert 'Error reduction vs constant mean:' in panel.resultLabel.text()
    assert session.derived_data(track,'function_fit_x') is not None
    attempt = actions.attempts.journal.attempts[-1]
    assert attempt['status']=='completed'
    assert attempt['summary']['result_formulas'][0]['error']
    assert 'prediction' not in attempt['summary']
    session.save_as(tmp_path/'saved'); actions.syncJournal(saved=True)
    assert (session.project_root/'analysis/fit-attempts.json').is_file()
    panel.restoreButton.click()
    _preview(qtbot,panel)
    assert panel.initialProtected


def test_rejected_failed_cancelled_attempts_remain_and_do_not_replace_success(qtbot,synthetic_video_path,monkeypatch):
    window,session,track = _window(qtbot,synthetic_video_path)
    actions,panel=window.chartActions,window.chartActions.signalPanel
    panel.fitButton.click(); qtbot.waitUntil(lambda:not actions.pending)
    saved = session.derived_data(track,'function_fit_x')
    panel.editor.setText('sin('); panel.fitButton.click()
    assert actions.attempts.journal.attempts[-1]['status']=='rejected'
    panel.editor.setText('a*t+b'); panel.budget.setValue(1)
    panel.fitButton.click(); qtbot.waitUntil(lambda:not actions.pending)
    assert actions.attempts.journal.attempts[-1]['status']=='evaluation_limit'
    assert session.derived_data(track,'function_fit_x') == saved
    panel.budget.setValue(1000)
    future=Future()
    monkeypatch.setattr(actions._executor,'submit',lambda *args:future)
    panel.fitButton.click(); panel.cancelButton.click()
    future.cancel(); actions._poll()
    assert actions.attempts.journal.attempts[-1]['status']=='cancelled'
    assert session.derived_data(track,'function_fit_x') == saved


def test_late_preview_cannot_overwrite_newer_draft_or_fit(qtbot,synthetic_video_path,monkeypatch):
    from ai_physics_tracker.gui.signal_preview import _preview as compute_preview
    window,session,track = _window(qtbot,synthetic_video_path)
    actions,panel=window.chartActions,window.chartActions.signalPanel
    actions.preview.invalidate()
    submitted=[]
    def submit(run,job,*args):
        future=Future(); future.set_running_or_notify_cancel(); submitted.append((future,run,job));return future
    monkeypatch.setattr(actions.preview._executor,'submit',submit)
    panel.editor.setText('a*t+b');actions.preview.launch()
    future,run,job=submitted[-1]
    panel.editor.setText('c')
    future.set_result(run(job,False))
    actions.preview.poll()
    assert panel.editor.text()=='c'
    assert not panel.signalPlot.listDataItems()
    assert session.derived_data(track,'function_fit_x') is None


def test_unexpected_prepare_error_is_a_failed_attempt(qtbot,synthetic_video_path,monkeypatch):
    window,_,_ = _window(qtbot,synthetic_video_path)
    actions=window.chartActions
    def broken(_fitting): raise RuntimeError('broken preparation')
    monkeypatch.setattr(actions,'_prepareSignal',broken)
    actions.analyzeSignal(True)
    assert not actions.pending
    assert actions.attempts.journal.attempts[-1]['status']=='failed'
    assert 'broken preparation' in actions.signalPanel.jobLabel.text()


def test_prepare_buttons_select_correct_family_and_never_invent_calibration(qtbot,synthetic_video_path):
    window,session,track = _window(qtbot,synthetic_video_path)
    actions,panel = window.chartActions,window.chartActions.signalPanel
    before=session.project
    panel.quantityChoice.setCurrentText('theta')
    panel.prepareRequested.emit()
    assert actions.panel.currentFamily=='angular'
    assert actions.panel.checkedTracks()==(track,)
    panel.setupRequested.emit()
    assert window.currentWorkspace=='setup'
    assert session.project==before


def test_full_model_view_is_explicit_and_reset_restores_source(qtbot,synthetic_video_path):
    import numpy as np
    window,_,_= _window(qtbot,synthetic_video_path)
    panel=window.chartActions.signalPanel
    panel.editor.setText('c');panel.parameterTable.item(0,1).setText('1e24')
    _preview(qtbot,panel)
    source=np.array(panel.signalPlot.viewRange())
    assert source[1,1]<100
    assert 'outside' in panel.showModelButton.text()
    panel.showModelButton.click()
    assert panel.signalPlot.viewRange()[1][1]>1e24
    panel.resetViewButton.click()
    np.testing.assert_allclose(panel.signalPlot.viewRange(),source)


def test_explicit_fit_does_not_wait_for_running_preview(qtbot,synthetic_video_path,monkeypatch):
    from threading import Event
    import ai_physics_tracker.gui.signal_preview as preview_module
    window,session,track=_window(qtbot,synthetic_video_path)
    actions,panel=window.chartActions,window.chartActions.signalPanel
    started,release=Event(),Event()
    def blocked(job,estimate,cancel):
        started.set();release.wait(5)
        return job.spec,None,[0]*len(job.samples)
    monkeypatch.setattr(preview_module,'_preview',blocked)
    actions.preview.request(immediate=True)
    qtbot.waitUntil(started.is_set)
    try:
        panel.fitButton.click()
        qtbot.waitUntil(lambda:not actions.pending,timeout=3000)
        assert session.derived_data(track,'function_fit_x') is not None
        assert not release.is_set()
    finally:release.set()


def test_saved_snapshot_is_distinct_from_new_unsaved_fit(qtbot,synthetic_video_path,tmp_path):
    window,session,track=_window(qtbot,synthetic_video_path)
    actions,panel=window.chartActions,window.chartActions.signalPanel
    panel.fitButton.click();qtbot.waitUntil(lambda:not actions.pending)
    session.save_as(tmp_path/'saved');actions.syncJournal(saved=True);actions.refresh()
    assert panel.previousButton.isEnabled()
    panel.editor.setText('c');panel.fitButton.click();qtbot.waitUntil(lambda:not actions.pending)
    panel.previousButton.click()
    assert panel.savedRecord().extra_fields['analysis']['spec']['expression']=='a*t + b'
    assert 'historical' in panel.draftLabel.text()
    panel.latestButton.click()
    assert panel.savedRecord().extra_fields['analysis']['spec']['expression']=='c'
    assert 'Latest applied' in panel.draftLabel.text()
    assert session.derived_data(track,'function_fit_x').extra_fields['analysis']['spec']['expression']=='c'


@pytest.mark.parametrize('preview',[False,True])
def test_submit_failure_is_visible_and_formal_attempt_is_finished(qtbot,synthetic_video_path,monkeypatch,preview):
    window,_,_=_window(qtbot,synthetic_video_path)
    actions=window.chartActions
    def broken(*args):raise RuntimeError('worker unavailable')
    monkeypatch.setattr(actions.preview._executor if preview else actions._executor,'submit',broken)
    if preview:actions.preview.request(immediate=True);qtbot.waitUntil(lambda:'could not start' in actions.signalPanel.jobLabel.text())
    else:
        actions.analyzeSignal(True)
        assert actions.attempts.journal.attempts[-1]['status']=='failed'
    assert not actions.pending and not actions.attempts.active
    assert 'worker unavailable' in actions.signalPanel.jobLabel.text()


def test_source_bar_tracks_signal_panel_target(qtbot,synthetic_video_path):
    window,session,first=_window(qtbot,synthetic_video_path)
    second=session.add_track(window.activeVideoId,'Second signal')
    for frame in range(5):session.mark_point(second.track_id,frame,pixel_x=frame,pixel_y=2)
    session.compute_kinematics(second.track_id)
    window.chartActions.refresh()
    panel=window.chartActions.signalPanel
    panel.trackChoice.setCurrentIndex(panel.trackChoice.findData(str(second.track_id)))
    assert 'Second signal' in window._analysisSourceLabel.text()
    assert '(5)' in window._analysisSourceLabel.text()


def test_restore_disk_settings_becomes_draft_without_relabeling_current_curve(qtbot,synthetic_video_path,tmp_path):
    window,session,_=_window(qtbot,synthetic_video_path)
    actions,panel=window.chartActions,window.chartActions.signalPanel
    panel.fitButton.click();qtbot.waitUntil(lambda:not actions.pending)
    session.save_as(tmp_path/'saved');actions.syncJournal(saved=True);actions.refresh()
    panel.editor.setText('c');panel.fitButton.click();qtbot.waitUntil(lambda:not actions.pending)
    panel.latestButton.click()
    assert 'Latest applied result:' in panel.summary.toPlainText()
    assert 'Recorded formula: c' in panel.summary.toPlainText()
    assert panel.signalPlot.listDataItems()[-1].name()=='Latest applied result'
    panel.previousButton.click()
    assert panel.signalPlot.listDataItems()[-1].name()=='Previous disk-saved result'
    panel.detailsGroup.setChecked(True)
    panel.restoreButton.click()
    assert 'Current draft' in panel.summary.toPlainText()
    assert 'Disk-saved historical' not in panel.summary.toPlainText()
    assert panel.editor.text()=='a*t + b'
    assert not panel.signalPlot.listDataItems()
    assert 'current draft' in panel.draftLabel.text()
    _preview(qtbot,panel)
    assert panel.signalPlot.listDataItems()[-1].name()=='Initial preview'
