"""入口、按钮和执行准备共用应用事实，工作流同轮只采集一次瞬时状态。"""

from dataclasses import replace
from concurrent.futures import Future
from threading import Event

import pytest

from tests.gui.test_signal_analysis import _window
from ai_physics_tracker.application.workflow_projection import EXEC_IDLE


def test_header_buttons_and_actual_preparation_share_unknown_source_reason(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    source = session.derived_data(track, 'world_position')
    unknown = replace(source, pipeline=source.pipeline+({'step':'future', 'params':{}},))
    session._project = replace(session.project, derived=tuple(unknown if item == source else item for item in session.project.derived))
    actions.refresh()
    state = actions.signalSourceState()
    card = window.analysisPurposeTaskCard()
    assert state is actions.signalSourceState()
    assert state.source_issue and not state.ready
    assert not panel.fitButton.isEnabled()
    assert state.reason == panel.fitButton.toolTip()
    assert any(state.reason in text for text in card.explanation)
    actions.preview.launch()
    assert state.reason in panel.jobLabel.text()
    assert not actions.pending


def test_changed_applied_parameters_refresh_guidance_and_reuse_source_preparation(qtbot, synthetic_video_path):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    actions.preview.invalidate()
    panel.quantityChoice.setCurrentText('vx')
    actions.preview.invalidate()
    window.trackingActions.refresh()
    ready = actions.signalSourceState()
    assert ready.ready
    actions.panel.windowLength.setValue(9)
    qtbot.waitUntil(lambda: not panel.fitButton.isEnabled())
    actions.preview.invalidate()
    window.trackingActions.refresh()
    state = actions.signalSourceState()
    assert state.preparation is not None and state is not ready
    assert actions._prepareSignalSource() is state.preparation
    assert window.analysisPurposeTaskCard().primary.action_id == 'analysis_prepare_source'
    assert not panel.fitButton.isEnabled()
    assert panel.fitButton.toolTip() == state.reason
    assert session.derived_data(track, 'velocity').pipeline[-1]['params']['window_length'] == 7


def test_workflow_refresh_projects_the_same_execution_facts_once(qtbot, synthetic_video_path, monkeypatch):
    window, _, _ = _window(qtbot, synthetic_video_path)
    tracking = window.trackingActions
    original = tracking._execution_input
    captured = []
    def collect():
        value = original()
        captured.append(value)
        return value
    monkeypatch.setattr(tracking, '_execution_input', collect)
    tracking._context_key = None
    tracking.refresh()
    assert len(captured) == 1
    assert tracking._current_workflow_state.execution is captured[0]
    assert captured[0].kind == EXEC_IDLE


@pytest.mark.parametrize('method', [0, 1])
@pytest.mark.parametrize('outcome', ['success', 'cancelled', 'failed'])
def test_automatic_source_preparation_keeps_page_position(qtbot, synthetic_video_path, monkeypatch, method, outcome):
    window, session, track = _window(qtbot, synthetic_video_path)
    actions, panel = window.chartActions, window.chartActions.signalPanel
    panel.methods.setCurrentIndex(method)
    window.resize(1024, 640)
    bar = window._analysisToolsScroll.verticalScrollBar()
    qtbot.waitUntil(lambda: bar.maximum() > 0)
    actions.preview.invalidate()
    session.clear_derived(track)
    observations = session.project.observations
    future = Future()
    captured = []
    def submit(run, job, cancel):
        captured.append((run, job))
        return future
    monkeypatch.setattr(actions._executor, 'submit', submit)
    feedback = []
    panel.feedbackRequested.connect(lambda: feedback.append(panel.jobLabel.text()))
    bar.setValue(bar.maximum() // 2)
    before = bar.value()
    assert before > 0
    actions.refresh()
    actions.preview.launch()
    assert actions.pending and 'Updating source data' in panel.jobLabel.text()
    assert bar.value() == before and feedback == []
    if outcome == 'failed':
        future.set_exception(ValueError('source worker unavailable'))
    else:
        if outcome == 'cancelled':
            actions.cancel()
        run, job = captured[0]
        future.set_result(run(job, Event()))
    actions._poll()
    if outcome == 'success':
        actions.preview.launch()
        qtbot.waitUntil(lambda: actions.preview._future is None)
    actions.preview.invalidate()
    assert bar.value() == before and feedback == []
    assert session.project.observations == observations
    assert session.derived_data(track, 'function_fit_x') is None
    assert session.derived_data(track, 'signal_recurrence_x') is None
    (panel.previewButton if method == 0 else panel.showSourceButton).click()
    actions.preview.invalidate()
    assert bar.value() == 0 and feedback  # 显式操作仍定位；被动状态不借用该信号。
