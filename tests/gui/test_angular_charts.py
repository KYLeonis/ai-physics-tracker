"""P6.2 图表配置、真实源帧导航与后台事务回归。"""

from dataclasses import replace
from math import pi
from threading import Event
from uuid import uuid4

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

from ai_physics_tracker.application.chart_data import ChartData, ChartSeries
from ai_physics_tracker.application.chart_recipe import timing_identity
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.domain.angular import PendulumReference, TwoPointReference
from ai_physics_tracker.domain.derived import ANGULAR_KINDS, KINEMATICS_KINDS
from ai_physics_tracker.domain.project import update_timeline
from ai_physics_tracker.gui.chart_panel import ChartPlot
from test_charts import _add_track, _BlockingJob, _opened, _SceneMouseEvent


def _angular_window(qtbot, path, *, calibrated=True):
    window = _opened(qtbot, path)
    track = _add_track(window)
    session = window.analysisSession
    if calibrated:
        session.add_calibration(track.video_id, scale_end_1_px=(0., 0.),
                                scale_end_2_px=(10., 0.), known_length=1., unit="m")
    window.setWorkspace("analysis")
    panel = window.chartActions.panel
    panel.tabs.setCurrentIndex(5)
    panel.angularControls.pivotX.setValue(10.)
    panel.angularControls.pivotY.setValue(0.)
    panel.angularControls.applyButton.click()
    window.chartActions.refresh()
    return window, track


def _compute(qtbot, window):
    window.chartActions.recompute()
    qtbot.waitUntil(lambda: not window.chartActions.pending, timeout=5000)


def test_editing_confirmed_reference_disables_recompute_without_other_ui_actions(qtbot, synthetic_video_path):
    window, _track = _angular_window(qtbot, synthetic_video_path)
    actions = window.chartActions
    qtbot.waitUntil(lambda: not actions._refresh_timer.isActive(), timeout=5000)
    assert actions.panel.recomputeButton.isEnabled()

    actions.panel.angularControls.pivotX.setValue(11.)

    qtbot.waitUntil(lambda: not actions.panel.recomputeButton.isEnabled(), timeout=500)


def test_confirmed_reference_computes_rad_results_and_degree_is_display_only(qtbot, synthetic_video_path):
    window, track = _angular_window(qtbot, synthetic_video_path)
    session, panel = window.analysisSession, window.chartActions.panel
    raw = session.project.observations
    _compute(qtbot, window)
    records = session.project.derived
    assert {r.kind for r in records} == set(ANGULAR_KINDS)
    assert all(len(row) == 1 for r in records for row in r.values)
    radians = panel.plots["theta_t"].data.series[0].y_values
    panel.angleUnit.setCurrentText("degree")
    window.chartActions.refresh()
    assert panel.plots["theta_t"].data.series[0].y_values == pytest.approx(
        tuple(value * 180 / pi for value in radians), abs=1e-10)
    assert panel.plots["theta_omega"].data.x_unit == "°"
    assert panel.plots["theta_omega"].data.y_unit == "°/s"
    assert session.project.derived == records and session.project.observations == raw
    assert not window.videoView.is_annotation_mode()
    assert "raw wrapped" in panel.plots["theta_t"]._items[0].name()
    panel.positionSource.setCurrentIndex(1)
    window.chartActions.refresh()
    assert "smoothed unwrapped" in panel.plots["theta_t"]._items[0].name()
    assert "10 fps" in panel.contextLabel.text() and "0–4" in panel.contextLabel.text()


def test_x_vx_recomputes_linear_without_angular_reference_and_keeps_y_up(qtbot, synthetic_video_path):
    window = _opened(qtbot, synthetic_video_path)
    _add_track(window)
    panel = window.chartActions.panel
    window.setWorkspace("analysis")
    panel.tabs.setCurrentIndex(9)
    window.chartActions.refresh()
    assert panel.currentFamily == "linear"
    assert panel.angularControls.appliedReference() is None
    assert panel.recomputeButton.isEnabled()
    _compute(qtbot, window)
    records = window.analysisSession.project.derived
    assert {r.kind for r in records} == set(KINEMATICS_KINDS)
    assert all(timing_identity(record) is not None for record in records)
    plot = panel.plots["x_vx"]
    assert plot.data.series and not plot.getViewBox().yInverted()
    assert not plot.actualLine.isVisible() and not plot.requestLine.isVisible()


def test_two_point_reference_is_explicit_and_self_target_rejection_is_atomic(qtbot, synthetic_video_path):
    window, track = _angular_window(qtbot, synthetic_video_path)
    session, panel = window.analysisSession, window.chartActions.panel
    ref = session.add_track(track.video_id, "B")
    for frame_index in range(5):
        session.mark_point(ref.track_id, frame_index, 10., 0.)
    window.chartActions.refresh()
    controls = panel.angularControls
    controls.modeCombo.setCurrentIndex(1)
    controls.applyButton.click()
    assert controls.appliedReference() is None
    controls.referenceTrack.setCurrentIndex(controls.referenceTrack.findData(ref.track_id))
    controls.applyButton.click()
    _compute(qtbot, window)
    assert all(r.input.reference_track_id == ref.track_id for r in session.project.derived)
    assert "A→B" in panel.plots["theta_omega"]._items[0].name()
    before = session.project
    controls.referenceTrack.setCurrentIndex(controls.referenceTrack.findData(track.track_id))
    controls.applyButton.click()
    _compute(qtbot, window)
    assert session.project == before
    assert "also checked" in panel.jobLabel.text()


@pytest.mark.parametrize("failure", ["no_calibration", "no_timing", "unconfirmed"])
def test_angular_prerequisite_failure_preserves_raw_and_cached_results(qtbot, synthetic_video_path, failure):
    window, track = _angular_window(qtbot, synthetic_video_path, calibrated=failure != "no_calibration")
    session, panel = window.analysisSession, window.chartActions.panel
    if failure == "no_timing":
        session.confirm_video_timing(track.video_id, TimingReport("unknown", "test"))
    elif failure == "unconfirmed":
        panel.angularControls.pivotX.setValue(11.)
    before = session.project
    window.chartActions.refresh()
    assert not panel.recomputeButton.isEnabled()
    _compute(qtbot, window)
    assert session.project == before


@pytest.mark.parametrize("change", ["sg", "reference", "checked_track", "active_track", "family", "project", "cancel",
                                    "raw", "calibration", "timing", "zone", "workspace"])
def test_changed_gui_context_discards_even_cancel_ignoring_angular_result(qtbot, synthetic_video_path, monkeypatch, change):
    window, track = _angular_window(qtbot, synthetic_video_path)
    session, actions = window.analysisSession, window.chartActions
    session.compute_kinematics(track.track_id)
    import ai_physics_tracker.gui.chart_actions as module
    real_run = module.run_angular_job
    gate = _BlockingJob(lambda job, _cancel: real_run(job, Event()), cancel_aware=False)
    monkeypatch.setattr(module, "run_angular_job", gate)
    try:
        actions.recompute()
        qtbot.waitUntil(gate.started.is_set, timeout=5000)
        if change == "sg":
            actions.panel.windowLength.setValue(9)
        elif change == "reference":
            actions.panel.angularControls.pivotX.setValue(11.)
        elif change == "checked_track":
            actions.panel.trackChoices.item(0).setCheckState(Qt.CheckState.Unchecked)
        elif change == "active_track":
            window._selected_track_id = None
            window.selectedTrackChanged.emit(None)
        elif change == "family":
            actions.panel.tabs.setCurrentIndex(9)
        elif change == "project":
            window.adoptEmptyProject()
        elif change == "raw":
            session.mark_point(track.track_id, 0, 50., 51.)
            window._refreshHistoryButtons()
        elif change == "calibration":
            calibration = session.active_calibration(track.video_id)
            session.update_calibration(replace(calibration, origin_px=(1., 2.)))
            window._refreshHistoryButtons()
        elif change == "timing":
            session.confirm_video_timing(track.video_id, TimingReport("unknown", "test"))
            window.analysisChanged.emit()
        elif change == "zone":
            session._project = update_timeline(session.project, replace(session.project.timelines[0], working_zone=(1, 4)))
            window.analysisChanged.emit()
        elif change == "workspace":
            window.setWorkspace("acquire")
        else:
            actions.cancel()
        assert actions._cancel.is_set()
        expected = session.project
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)
        qtbot.waitUntil(lambda: not actions.pending, timeout=5000)
        assert session.project.derived == expected.derived
        assert session.project.observations == expected.observations
        if change == "project":
            assert window.analysisSession.project.derived == ()
    finally:
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)


def test_analysis_refresh_without_input_change_keeps_running_job(qtbot, synthetic_video_path, monkeypatch):
    window, _track = _angular_window(qtbot, synthetic_video_path)
    actions = window.chartActions
    import ai_physics_tracker.gui.chart_actions as module
    gate = _BlockingJob(module.run_angular_job, cancel_aware=False)
    monkeypatch.setattr(module, "run_angular_job", gate)
    try:
        actions.recompute()
        qtbot.waitUntil(gate.started.is_set, timeout=5000)
        window.analysisChanged.emit()
        actions.panel.angleUnit.setCurrentText("degree")
        assert not actions._cancel.is_set()
        gate.release.set()
        qtbot.waitUntil(lambda: not actions.pending, timeout=5000)
        assert len(window.analysisSession.project.derived) == 4
    finally:
        gate.release.set()
        qtbot.waitUntil(gate.finished.is_set, timeout=5000)


def test_angular_batch_preserves_other_family_and_has_one_undo_step(qtbot, synthetic_video_path):
    window, track = _angular_window(qtbot, synthetic_video_path)
    session = window.analysisSession
    linear = session.compute_kinematics(track.track_id)
    _compute(qtbot, window)
    assert len(session.project.derived) == 8
    assert all(record in session.project.derived for record in linear)
    assert session.undo() and session.project.derived == linear
    assert session.redo() and len(session.project.derived) == 8
    before = session.project
    window._undo()
    assert session.project == before


def test_cached_pivot_precision_is_preserved_when_confirmed_again(qtbot, synthetic_video_path):
    window, _track = _angular_window(qtbot, synthetic_video_path)
    controls = window.chartActions.panel.angularControls
    reference = PendulumReference((10.1234567890123, 9.98765432109876))
    controls.seedApplied(reference)
    controls.applyButton.click()
    assert controls.appliedReference() is reference
    controls.pivotX.setValue(-100.)
    controls.applyButton.click()
    assert controls.appliedReference().pivot_px[0] == pytest.approx(-100., abs=1e-12)


def test_save_reopen_restores_recipe_display_and_unknown_chart_preferences(qtbot, synthetic_video_path, tmp_path, monkeypatch):
    window, track = _angular_window(qtbot, synthetic_video_path)
    session, panel = window.analysisSession, window.chartActions.panel
    panel.windowLength.setValue(9)
    _compute(qtbot, window)
    panel.angleUnit.setCurrentText("degree")
    panel.tabs.setCurrentIndex(8)
    session.update_view_state({"charts": {"version": 1, "extension": {"keep": True}}})
    root = tmp_path / "angular"
    session.save_as(root)
    window.projectActions.save()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    saved = session.project
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(root / "project.json"), ""))
    window.projectActions.openProject()
    qtbot.waitUntil(lambda: window.analysisSession is not session and not window.projectActions.busy
                   and not window.timingActions.pending, timeout=5000)
    assert panel.currentPlot.kind == "theta_omega" and panel.currentAngleUnit() == "degree"
    assert panel.windowLength.value() == 9
    assert panel.angularControls.appliedReference() == PendulumReference((10., 0.))
    assert window.captureProjectView()["charts"]["extension"] == {"keep": True}
    assert window.analysisSession.project.observations == saved.observations
    assert window.analysisSession.project.derived == saved.derived
    panel.angleUnit.setCurrentText("degree")
    window.adoptEmptyProject()
    assert panel.currentAngleUnit() == "rad" and panel.currentPlot.kind == "x_t"
    future = {"version": 2, "custom": {"keep": [1, 2]}}
    panel.tabs.setCurrentIndex(8)
    panel.angleUnit.setCurrentText("degree")
    panel.positionSource.setCurrentIndex(1)
    panel.restoreViewState(future)
    assert panel.currentPlot.kind == "theta_omega" and panel.currentAngleUnit() == "degree"
    assert panel.positionSource.currentIndex() == 1
    window.analysisSession.update_view_state({"charts": future})
    assert window.captureProjectView()["charts"] == future


def test_family_cache_settings_restore_without_overwriting_unapplied_edit(qtbot, synthetic_video_path):
    window, track = _angular_window(qtbot, synthetic_video_path)
    session, panel = window.analysisSession, window.chartActions.panel
    session.compute_kinematics(track.track_id, window_length=11)
    session.compute_angular(track.track_id, reference=PendulumReference((10., 0.)), window_length=9)
    window.chartActions.resetContext()
    assert panel.windowLength.value() == 11
    panel.tabs.setCurrentIndex(5)
    window.chartActions.refresh()
    assert panel.windowLength.value() == 9
    panel.windowLength.setValue(13)
    panel.tabs.setCurrentIndex(0)
    window.chartActions.refresh()
    assert panel.windowLength.value() == 13
    assert "Settings not applied" in panel.jobLabel.text()


def test_phase_chooses_screen_nearest_source_sample_under_unequal_axis_scales(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(500, 400)
    plot = ChartPlot("theta_omega", parent)
    plot.setGeometry(0, 0, 500, 400)
    parent.show()
    track_id = uuid4()
    series = ChartSeries(track_id, "Bob", "#ff0000", "theta_omega", (1, 2),
                         (.007, 0.), (0., .8), (False, False), "rad/s", "valid", "")
    plot.renderData(ChartData("phase", "θ", "ω", "rad", "rad/s", (series,), (), False))
    plot.getViewBox().setRange(xRange=(-1., 1.), yRange=(-200., 200.), padding=0)
    plot.setNavigation(True, None)
    plot.setFrame(1, .1)
    QApplication.processEvents()
    scene = plot.getViewBox().mapViewToScene(QPointF(0., 0.))
    requested, times = [], []
    plot.frameRequested.connect(requested.append)
    plot.timeRequested.connect(times.append)
    plot._sceneClicked(_SceneMouseEvent(scene))
    assert requested == [2] and times == []
    assert not plot.actualLine.isVisible() and not plot.requestLine.isVisible()
    plot.setFrame(3, .3)
    assert len(plot._highlight.points()) == 0
    overlapping = replace(series, frames=(1, 3, 5), x_values=(0., 0., 0.),
                          y_values=(0., 0., 0.), connect=(False, False, False))
    plot.renderData(replace(plot.data, series=(overlapping,)))
    plot.setFrame(4, .4)
    plot._sceneClicked(_SceneMouseEvent(plot.getViewBox().mapViewToScene(QPointF(0., 0.))))
    assert requested[-1] == 3
