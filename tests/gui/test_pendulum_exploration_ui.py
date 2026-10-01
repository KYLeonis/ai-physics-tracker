"""P4图的数据映射与只读任务生命周期；体验最终由用户HR验收。"""

from concurrent.futures import Future
from dataclasses import replace
from threading import Event

import numpy as np
import pyqtgraph as pg
import pytest

from ai_physics_tracker.application.pendulum_exploration import read_fit_exploration, preview_equivalence
from ai_physics_tracker.domain.pendulum_identifiability import IdentifiabilitySurface
from ai_physics_tracker.gui.pendulum_criticism_panel import ModelCriticismPanel
from ai_physics_tracker.gui.pendulum_teaching_panel import ParameterEquivalencePanel
from ai_physics_tracker.gui.pendulum_exploration import PendulumExplorationActions
from ai_physics_tracker.gui.pendulum_fit import PendulumFitActions
from test_pendulum_analysis_ui import Window
from test_pendulum_exploration import fitted_session


def test_panels_map_source_points_raw_parameters_and_surface_axes(qtbot, tmp_path, synthetic_video_path):
    session, _, record = fitted_session(tmp_path, synthetic_video_path)
    source = read_fit_exploration(session.detached(), record, Event())
    critic = ModelCriticismPanel(); qtbot.addWidget(critic); critic.setSource(source)
    assert "individual model diagnostics only" in critic.status.text()
    item = next(item for item in critic.plots["residual"].plotItem.items if isinstance(item, pg.ScatterPlotItem))
    assert len(item.points()) == 121
    assert item.points()[0].data() == 5
    with qtbot.waitSignal(critic.frameRequested) as signal:
        critic._pointClicked(item, [item.points()[0]])
    assert signal.args == [5]
    assert critic.physicalTable.rowCount() >= 10
    assert "not agreement with observed energy" in critic.messages["physical"].text()
    assert "own fit-window mean" in critic.messages["phase"].text()
    teaching = ParameterEquivalencePanel(); qtbot.addWidget(teaching)
    teaching.configure(source)
    preview = preview_equivalence(source, 1.12, False, None, Event())
    teaching.setPreview(source, preview)
    assert teaching.rawTable.rowCount() == 7
    assert float(teaching.rawTable.item(0, 2).text()) == pytest.approx(.12)
    assert float(teaching.rawTable.item(6, 1).text()) == float(teaching.rawTable.item(6, 2).text())
    assert len(teaching.referenceCurve.getData()[0]) == 501
    assert "Equivalent family" in teaching.status.text()
    # 小型已知显示网格，明确alpha为横轴、raw omega0²为纵轴；不伪作数值回归。
    grid = ((0., 1.), (2., 3.), (4., 5.))
    surface = IdentifiabilitySurface((0., .06, .12), (18., 22.), grid, grid, grid, 1.)
    teaching.setSurface(surface)
    np.testing.assert_array_equal(teaching.image.image, np.asarray(grid).T)
    assert teaching.image.mapToParent(0, 0).x() == pytest.approx(-.03)
    assert teaching.image.mapToParent(0, 0).y() == pytest.approx(16.)
    assert teaching.image.mapToParent(3, 2).x() == pytest.approx(.15)
    control = preview_equivalence(source, 1.12, True, None, Event())
    teaching.setPreview(source, control)
    assert "NON-EQUIVALENT" in teaching.status.text()
    assert teaching.plots['surface'].viewRange()[1][1] >= control.displayed_raw.omega0_sq_s_inv2
    assert "no color extrapolation" in teaching.nodeLabel.text()
    teaching.setSurface(replace(surface, log10_objective_ratio_grid=((None, None),)*3))
    teaching.setPreview(source, control)
    assert "zero fitted objective" in teaching.nodeLabel.text()
    critic.clearData(); teaching.clearData()
    assert critic.physicalTable.rowCount() == teaching.rawTable.rowCount() == 0


def test_background_cache_cancel_and_late_input_rejection(qtbot, tmp_path, synthetic_video_path, monkeypatch):
    session, experiment, _ = fitted_session(tmp_path, synthetic_video_path)
    window = Window(session, experiment); qtbot.addWidget(window)
    window.pendulumFitActions = PendulumFitActions(window)
    critic = ModelCriticismPanel(window)
    actions = PendulumExplorationActions(window, critic)
    try:
        qtbot.waitUntil(lambda: actions._cache is not None and actions._future is None, timeout=20000)
        before = session.project
        assert actions.teaching.buildButton.isEnabled()
        assert not actions.teaching.progress.isVisible()
        actions.scan()
        assert not actions.teaching.lambdaValue.isEnabled()
        qtbot.waitUntil(lambda: actions._future is None, timeout=45000)
        assert actions._cache[1] is not None and actions._cache[2] is not None
        assert actions.teaching.tabs.currentIndex() == 2
        assert actions.teaching.buildButton.text() == "Show cached surface"
        curve = actions._cache[1]
        def no_rescan(*args, **kwargs):
            raise AssertionError("lambda adjustment must reuse the same-fit surface")
        monkeypatch.setattr("ai_physics_tracker.gui.pendulum_exploration.build_identifiability_curve", no_rescan)
        actions.teaching.lambdaValue.setValue(1.01)
        actions.teaching.lambdaValue.setValue(1.12)
        qtbot.waitUntil(lambda: actions._future is None and not actions._previewTimer.isActive()
                       and "λ=1.1200" in actions.teaching.status.text(), timeout=15000)
        assert actions._cache[1] is curve
        actions.scan()  # 复用已完成曲面，不启动第二次222点扫描。
        assert actions._future is None
        old_cache = actions._cache
        source = old_cache[0]
        preview = preview_equivalence(source, 1., False, None, Event())
        pending = Future()
        actions._future = pending; actions._context = (actions._key, "scan")
        actions._cancel = Event(); actions._counts = None; actions._started = 0.
        actions._progress.put((7, 222)); actions._poll()
        assert actions.teaching.progress.maximum() == 222 and actions.teaching.progress.value() == 7
        assert "7/222 nodes" in actions.teaching.status.text()
        actions.cancel(); pending.set_result((old_cache, preview)); actions._poll()
        assert actions._cache is old_cache
        # 取消/代际/换视频/输入改动的迟到结果不能覆盖现图或写结果。
        for reason in ("cancel", "generation", "video", "edit"):
            key = actions._key
            future = Future()
            actions._context = (key, "preview"); actions._future = future
            actions._cancel = Event(); actions._started = 0.; actions._counts = None
            if reason == "cancel": actions.cancel()
            elif reason == "generation": window.deliveryGeneration += 1
            elif reason == "video": window.activeVideoId = None
            else: session.mark_point(experiment.roles.tip, 10, 1., 100.)
            future.set_result(((source, None, None), preview)); actions._poll()
            assert actions._cache is old_cache
            assert len(session.project.scientific_results) == len(before.scientific_results)
            if reason == "generation": window.deliveryGeneration -= 1
            if reason == "video": window.activeVideoId = experiment.video_id
        actions.refresh()
        assert actions._cache is None and not actions.teaching.buildButton.isEnabled()
        assert "current verified ODE fit" in critic.status.text()
        # 关闭后无论旧future何时返回，都不再送入Qt。
        actions.shutdown(); window.pendulumFitActions.shutdown()
        assert actions._future is None
    finally:
        actions.shutdown(); window.pendulumFitActions.shutdown()
