"""拟合页同请求、原始残差与源帧导航；GUI体验仍待真人验收。"""

from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest

from ai_physics_tracker.application.pendulum_fit import prepare_fit_job, run_fit_job
from ai_physics_tracker.domain.pendulum_ode import M0, IntegrationSettings, InitialCondition
from ai_physics_tracker.gui.pendulum_fit_panel import PendulumFitPanel
from test_pendulum_fit_job import fit_session


def test_normal_advanced_options_roundtrip_and_invalid_values(qtbot, tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    panel = PendulumFitPanel(); qtbot.addWidget(panel)
    panel.startFrame.setRange(5, 125); panel.endFrame.setRange(5, 125)
    panel.restoreOptions(options)
    assert panel.options() == options
    panel.commonFields["rtol"].setText("3e-10")
    assert panel.precision.currentIndex() == 2
    assert panel.options().integration == IntegrationSettings(3e-10, 2e-12)
    panel.loss.setCurrentText("linear")
    assert panel.options().loss == "linear"
    panel.icMode.setCurrentIndex(1)
    with pytest.raises(ValueError): panel.options()
    panel.theta0.setText(".3"); panel.omega0.setText("0")
    assert panel.options().explicit_ic == InitialCondition(.3, 0., "explicit")
    panel.modelFields[M0]["alpha1_bounds"].setText(".5, 0")
    with pytest.raises(ValueError): panel.options()
    panel.resetDefaults()
    assert panel.options().m0_settings.max_nfev == 180
    assert panel.options().explicit_ic == InitialCondition(.3, 0., "explicit")


def test_overlay_full_residual_and_frame_navigation(qtbot, tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    panel = PendulumFitPanel(); qtbot.addWidget(panel)
    panel.setPayload(result.payload, True)
    assert len(panel.observations.getData()[0]) == 121
    assert len(panel.curves["residual", M0].getData()[0]) == 121
    assert "full RMSE" in panel.summaryLabel.text() and "s⁻¹" in panel.summaryLabel.text()
    assert "optimizer_success" in panel.details.toPlainText()
    assert panel.parameterTable.rowCount() == 5
    assert panel.startTable.rowCount() == len(result.payload["fits"][M0]["starts"])
    assert panel.parameterTable.item(4, 2).text() != "—"
    assert panel.plots["overlay"].minimumHeight() >= 240
    assert panel.settingsScroll.maximumHeight() == 240
    # 显示层合成第二条曲线，用已知差值验证比较图；不伪作科学拟合结果。
    from copy import deepcopy
    from math import degrees
    from ai_physics_tracker.domain.pendulum_ode import M1
    comparison = deepcopy(result.payload)
    comparison["fits"][M1] = deepcopy(comparison["fits"][M0])
    comparison["fits"][M1]["parameters"]["alpha2_rad_inv"] = .01
    for row in comparison["rows"]:
        if row["m0_theta_rad"] is not None:
            row["m1_theta_rad"] = row["m0_theta_rad"] + .01
            row["m1_residual_rad"] = row["m0_residual_rad"] + .01
    panel.setPayload(comparison, True)
    assert panel.differenceCurve.getData()[1] == pytest.approx([degrees(.01)]*121, abs=1e-12)
    assert panel.parameterTable.item(2, 3).text() == "0.01"
    assert panel.curves["overlay", M0].opts["pen"].style() != panel.curves["overlay", M1].opts["pen"].style()
    assert panel.plots["overlay"].viewRange()[0][0] > -.5
    with qtbot.waitSignal(panel.frameRequested) as signal:
        panel._pointClicked(None, [SimpleNamespace(data=lambda: 90)])
    assert signal.args == [90]
    panel.presentFrame(90)
    assert "Source frame 90" in panel.frameLabel.text()
    panel.setPayload(result.payload, False, "input changed")
    assert "STALE" in panel.statusLabel.text()
    assert panel.curves["residual", M0].opts["pen"] is None


def test_background_fit_commit_settings_change_stale_and_reopen(qtbot, tmp_path, synthetic_video_path):
    from ai_physics_tracker.gui.pendulum_fit import PendulumFitActions
    from test_pendulum_analysis_ui import Window
    from ai_physics_tracker.application.project_session import ProjectSession
    from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    window = Window(session, experiment); qtbot.addWidget(window)
    actions = PendulumFitActions(window)
    try:
        actions.panel.restoreOptions(options)
        assert actions.panel.runButton.isEnabled()
        actions.compute()
        assert actions.panel.progressBar.maximum() == 0
        assert not actions.panel.progressBar.isHidden()
        actions._poll()
        assert "elapsed" in actions.panel.progressLabel.text()
        qtbot.waitUntil(lambda: actions._future is None, timeout=15000)
        assert len(session.project.scientific_results) == 1
        assert actions.panel.progressBar.isHidden()
        assert actions.panel.payload_valid and actions.panel.statusLabel.text().startswith("Current")
        actions.panel.loss.setCurrentText("linear")
        assert "Settings changed" in actions.panel.statusLabel.text()
        session.mark_point(experiment.roles.tip, 20, 1., 100.)
        window.analysisChanged.emit()
        qtbot.waitUntil(lambda: "STALE" in actions.panel.statusLabel.text(), timeout=15000)
        assert not actions.panel.payload_valid
        session.undo(); session.save()
        window.analysisSession = ProjectSession.load(ProjectRepository(), session.project_root)
        window.projectChanged.emit()
        qtbot.waitUntil(lambda: actions._future is None, timeout=15000)
        assert actions.panel.payload_valid and actions.panel.options() == options
    finally:
        actions.shutdown()


def test_cancel_generation_and_input_changes_discard_owned_artifact(qtbot, tmp_path, synthetic_video_path, monkeypatch):
    from concurrent.futures import Future
    from ai_physics_tracker.gui.pendulum_fit import PendulumFitActions
    from test_pendulum_analysis_ui import Window
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    window = Window(session, experiment); qtbot.addWidget(window)
    actions = PendulumFitActions(window)
    try:
        for reason in ("cancel", "generation", "edit", "settings", "reset"):
            result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
            artifact = session.project_root/result.record.payload.path
            future = Future()
            with monkeypatch.context() as patch:
                patch.setattr(actions._executor, "submit", lambda *args, **kwargs: future)
                actions.panel.restoreOptions(options); actions.compute()
                if reason == "cancel": actions.cancel()
                elif reason == "generation": window.deliveryGeneration += 1
                elif reason == "edit": session.mark_point(experiment.roles.tip, 10, 1., 100.)
                elif reason == "settings": actions.panel.loss.setCurrentText("linear")
                elif reason == "reset": actions.resetContext()
                future.set_result(result)
                actions._poll()
            assert not session.project.scientific_results and not artifact.exists()
            if reason == "edit": session.undo()
    finally:
        actions.shutdown()


def test_failed_fit_keeps_previous_plot_and_accepted_artifact_on_shutdown(qtbot, tmp_path, synthetic_video_path, monkeypatch):
    from concurrent.futures import Future
    from ai_physics_tracker.gui.pendulum_fit import PendulumFitActions
    from test_pendulum_analysis_ui import Window
    from ai_physics_tracker.domain.pendulum import QCExclusion
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    good = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    session.apply_pendulum_fit_result(good)
    window = Window(session, experiment); qtbot.addWidget(window)
    actions = PendulumFitActions(window)
    try:
        qtbot.waitUntil(lambda: actions._future is None, timeout=15000)
        original_payload = actions.panel.payload
        session.set_qc_exclusions(experiment.experiment_id, tuple(QCExclusion(i, "occluded") for i in range(10, 100)))
        failed = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
        future = Future()
        with monkeypatch.context() as patch:
            patch.setattr(actions._executor, "submit", lambda *args, **kwargs: future)
            actions.panel.restoreOptions(options); actions.compute(); future.set_result(failed); actions._poll()
        assert actions.panel.payload == original_payload
        assert "previous fit kept" in actions.panel.statusLabel.text()
        assert len(session.project.scientific_results) == 2
        actions.shutdown()
        assert (session.project_root/good.record.payload.path).exists()
        assert (session.project_root/failed.record.payload.path).exists()
    finally:
        actions.shutdown()


def test_fill_release_angle_requires_verified_current_raw_measurement(qtbot, tmp_path, synthetic_video_path):
    from ai_physics_tracker.gui.pendulum_fit import PendulumFitActions
    from ai_physics_tracker.application.pendulum_analysis import prepare_analysis_job, run_analysis_job, analysis_input_state
    from test_pendulum_analysis_ui import Window
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    analysis = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 125), Event())
    window = Window(session, experiment); qtbot.addWidget(window)
    window.pendulumAnalysisActions = SimpleNamespace(_future=None,
        _key=(analysis_input_state(session, experiment.experiment_id), analysis.record, analysis.verified_video_stamp),
        panel=SimpleNamespace(payload_valid=True, payload=analysis.payload))
    actions = PendulumFitActions(window)
    try:
        actions.panel.icMode.setCurrentIndex(1); actions.fillReleaseAngle()
        assert float(actions.panel.theta0.text()) == pytest.approx(.3, abs=1e-12)
        assert actions.panel.omega0.text() == "" and not actions.panel.runButton.isEnabled()
        actions.panel.omega0.setText("0")
        assert actions.panel.runButton.isEnabled()
        session.mark_point(experiment.roles.tip, 5, 1., 100.)
        actions.fillReleaseAngle()
        assert "QC-valid tip angle" in actions.panel.statusLabel.text()
    finally:
        actions.shutdown()


def test_save_as_is_blocked_before_copying_unregistered_fit_payload():
    from ai_physics_tracker.gui.project_actions import ProjectActions
    messages = []
    window = SimpleNamespace(pendulumFitActions=SimpleNamespace(pending=True),
        statusBar=lambda: SimpleNamespace(showMessage=messages.append))
    ProjectActions.saveAs(SimpleNamespace(window=window))
    assert messages == ["Cancel the ODE fit before Save as"]


def test_timing_prerequisite_is_visible_and_reuses_existing_confirmation(qtbot, tmp_path, synthetic_video_path):
    from PySide6.QtWidgets import QPushButton
    from ai_physics_tracker.gui.pendulum_fit import PendulumFitActions
    from test_pendulum_analysis_ui import Window
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    session._verified_videos.clear()
    window = Window(session, experiment); qtbot.addWidget(window)
    window.timingButton = QPushButton("Use approximate timing…", window)
    from ai_physics_tracker.gui.timing_actions import TimingActions
    from concurrent.futures import Future
    window.timingActions = TimingActions(window)
    requested = []
    window.timingButton.clicked.connect(lambda: requested.append(True))
    actions = PendulumFitActions(window)
    try:
        actions.panel.restoreOptions(options)
        assert not actions.panel.runButton.isEnabled()
        assert "Run fit requires video timing confirmation" in actions.panel.timingHint.text()
        assert actions.panel.timingButton.isEnabled()
        actions.panel.timingButton.click()
        assert requested == [True]
        window.timingActions._future = Future(); actions._enableRun()
        assert "Validating" in actions.panel.timingHint.text()
        assert not actions.panel.timingButton.isEnabled()
        window.timingActions._future = None
        session._verified_videos.add(experiment.video_id); actions._enableRun()
        assert actions.panel.timingHint.isHidden() and actions.panel.runButton.isEnabled()
    finally:
        actions.shutdown()
        window.timingActions.shutdown()
