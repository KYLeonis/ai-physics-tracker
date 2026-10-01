"""单摆分析 scalar 图表源帧、后台提交/取消/迟到编排；体验仍需真人验收。"""

from concurrent.futures import Future
from threading import Event
from types import SimpleNamespace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ai_physics_tracker.application.pendulum_analysis import prepare_analysis_job, run_analysis_job, analysis_input_state
from ai_physics_tracker.domain.pendulum import QCExclusion
from ai_physics_tracker.gui.pendulum_analysis import PendulumAnalysisActions, PendulumAnalysisPanel
from test_pendulum_analysis import analysis_session


class Window(QWidget):
    analysisChanged = Signal()
    projectChanged = Signal()
    selectedTrackChanged = Signal(object)
    presentedFrameChanged = Signal(object)
    closing = Signal()

    def __init__(self, session, experiment):
        super().__init__()
        self.analysisSession = session
        self.activeVideoId = experiment.video_id
        self.presentedFrameIndex = 0
        self.deliveryGeneration = 1
        self.projectActions = SimpleNamespace(busy=False)
        self.chartActions = SimpleNamespace(panel=QWidget(self))
        self.seeks = []

    def currentPendulumExperiment(self):
        return self.analysisSession.pendulum_experiments()[0]

    def seekSourceFrame(self, frame):
        self.seeks.append(frame)

    def _refreshHistoryButtons(self):
        self.analysisChanged.emit()


def test_scalar_points_gaps_units_and_source_navigation(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    session.set_qc_exclusions(experiment.experiment_id, (QCExclusion(5, 'occlusion'),))
    result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    panel = PendulumAnalysisPanel()
    qtbot.addWidget(panel)
    panel.setPayload(result.payload, True)
    assert 'q=g/L' in panel.summaryLabel.text() and 'not fitted' in panel.summaryLabel.text()
    assert 's⁻²' in panel.summaryLabel.text()
    _, y = panel.items['theta'].getData()
    assert str(y[5]) == 'nan'
    assert not panel.items['theta'].opts['connect'][4]
    panel.presentFrame(5)
    assert 'Source frame 5' in panel.frameLabel.text() and 'QC excluded' in panel.frameLabel.text()
    assert 'tip: manual' in panel.frameLabel.text()
    with qtbot.waitSignal(panel.frameRequested) as signal:
        panel._pointClicked(None, [SimpleNamespace(data=lambda: 7)])
    assert signal.args == [7]


def test_background_compute_and_changed_inputs_show_stale(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    window = Window(session, experiment)
    qtbot.addWidget(window)
    actions = PendulumAnalysisActions(window)
    try:
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None, timeout=10000)
        assert len(session.project.scientific_results) == 1
        assert actions.panel.statusLabel.text().startswith('Current')
        session.mark_point(experiment.roles.tip, 4, 1., 100.)
        window.analysisChanged.emit()
        qtbot.waitUntil(lambda: 'STALE' in actions.panel.statusLabel.text(), timeout=10000)
        assert session.project.scientific_results[0].execution_status == 'success'
        actions.panel._pointClicked(None, [SimpleNamespace(data=lambda: 4)])
        assert window.seeks == [4]
    finally:
        actions.shutdown()


def test_cancel_late_generation_and_input_change_never_commit(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    window = Window(session, experiment)
    qtbot.addWidget(window)
    actions = PendulumAnalysisActions(window)
    result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    try:
        for reason in ('cancel', 'generation', 'edit'):
            future = Future()
            state = analysis_input_state(session, experiment.experiment_id)
            actions._newCancel()
            actions._submit('compute', state, future)
            if reason == 'cancel':
                actions.cancel()
            elif reason == 'generation':
                window.deliveryGeneration += 1
            else:
                session.mark_point(experiment.roles.tip, 4, 2., 100.)
            future.set_result(result)
            actions._poll()
            assert session.project.scientific_results == ()
        # 新项目/关闭后遗留future完成，不能再触发manifest提交。
        future = Future()
        actions._newCancel()
        actions._submit('compute', state, future)
        actions.resetContext()
        future.set_result(result)
        actions._poll()
        assert session.project.scientific_results == ()
    finally:
        actions.shutdown()


def test_sparse_qc_previews_and_empty_charts_recover(qtbot, tmp_path, synthetic_video_path):
    from copy import deepcopy
    from math import sin

    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    complete = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event()).payload
    sparse = deepcopy(complete)
    sparse['config']['end_frame_index'] = 147
    sparse['measurement']['video']['fps_nominal'] = 30.
    valid_frames = {block * 15 + offset for block in range(8) for offset in range(5)} | {120, 121}
    sparse['rows'] = []
    for frame in range(148):
        row = deepcopy(complete['rows'][0])
        row.update(frame_index=frame, time_release_relative_s=frame/30.,
                   theta_rad=.2*sin(frame/10.) if frame < 133 else None,
                   is_qc_valid=frame in valid_frames,
                   qc_reasons=[] if frame in valid_frames else ['body_top:no_adopted_point'],
                   omega_rad_s=None, omega_reason='short_segment' if frame in valid_frames else 'qc_excluded',
                   energy_s_inv2=None)
        sparse['rows'].append(row)
    panel = PendulumAnalysisPanel()
    qtbot.addWidget(panel)
    panel.setPayload(sparse, True)
    assert '42/148' in panel.summaryLabel.text()
    assert 'Longest QC-valid block: 5 frames' in panel.summaryLabel.text()
    assert len(panel.excludedAngles.points()) == 91  # 133 geometrical angles minus 42 valid
    with qtbot.waitSignal(panel.frameRequested) as signal:
        point = panel.excludedAngles.points()[0]
        panel._pointClicked(panel.excludedAngles, [point])
    assert signal.args == [point.data()]
    for kind in ('omega', 'phase', 'energy'):
        assert panel.plots[kind].isHidden()
        x, y = panel.items[kind].getData()
        assert x is None or len(x) == 0
        assert y is None or len(y) == 0  # 不把全NaN交给autorange
        assert '9 consecutive QC-valid frames' in panel.chartMessages[kind].text()
        assert 'longest block: 5' in panel.chartMessages[kind].text()
        assert 'source block 0–8' in panel.chartMessages[kind].text()
        assert 'frames 5, 6, 7, 8' in panel.chartMessages[kind].text()
    panel.setPayload(complete, True)
    for kind in ('omega', 'phase', 'energy'):
        assert not panel.plots[kind].isHidden()
        assert 'unavailable' not in panel.chartMessages[kind].text()
    assert len(panel.excludedAngles.points()) == 0
    panel.setPayload(sparse, True)
    assert panel.plots['omega'].isHidden()
    panel.clearData()
    assert len(panel.excludedAngles.points()) == 0
    assert all(plot.isHidden() for plot in panel.plots.values())


def test_repair_suggestions_reject_changed_inputs_and_restored_four_points_produce_charts(
    qtbot, tmp_path, synthetic_video_path
):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    for frame in range(4, 8):
        session.mark_point(experiment.roles.tip, frame, 0., 200.)
    window = Window(session, experiment)
    qtbot.addWidget(window)
    repairs = []
    window.beginExperimentAnnotation = lambda frames, **kw: repairs.append(frames)
    actions = PendulumAnalysisActions(window)
    try:
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None)
        assert actions.panel.repair_frames == (4, 5, 6, 7)
        assert actions.panel.repairButton.isEnabled()
        assert actions.panel.plots['omega'].isHidden()
        before = session.project
        actions.panel.repairButton.click()
        assert repairs == [(4, 5, 6, 7)] and session.project == before
        # 旧结果的建议不能绕过实际输入变化；无需等UI刷新先拒绝。
        session.mark_point(experiment.roles.tip, 0, 1., 100.)
        actions.repairSuggestedFrames()
        assert len(repairs) == 1 and not actions.panel.repairButton.isEnabled()
        session.mark_point(experiment.roles.tip, 0, 0., 100.)
        for frame in range(4, 8):
            for role, xy in zip(('tip', 'body_top', 'body_bottom', 'pivot'), ((0., 100.), (0., 10.), (0., 20.), (0., 0.))):
                session.mark_point(experiment.roles.track_id_for(role), frame, *xy)
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None)
        assert not actions.panel.repair_frames
        for kind in ('omega', 'phase', 'energy'):
            assert not actions.panel.plots[kind].isHidden()
            assert len(actions.panel.items[kind].getData()[0]) == 12
        assert all(r['is_qc_valid'] and r['omega_rad_s'] is not None and r['energy_s_inv2'] is not None
                   for r in actions.panel.payload['rows'])
    finally:
        actions.shutdown()


def test_tip_only_with_no_auxiliary_points_generates_all_angular_charts(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    for role in ('body_top', 'body_bottom', 'pivot'):
        for frame in range(12):
            session.delete_active_manual_point(experiment.roles.track_id_for(role), frame)
    # 旧AI辅助坐标可能仍存在；无效/缺失都不得阻塞tip。
    window = Window(session, experiment)
    qtbot.addWidget(window)
    actions = PendulumAnalysisActions(window)
    try:
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None)
        assert all(r['is_qc_valid'] for r in actions.panel.payload['rows'])
        assert all(r['omega_rad_s'] is not None for r in actions.panel.payload['rows'])
        assert all(not actions.panel.plots[k].isHidden() for k in ('theta', 'omega', 'phase', 'energy'))
    finally:
        actions.shutdown()


def test_custom_sg_settings_restore_short_charts_and_reopen_controls(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    session.set_qc_exclusions(experiment.experiment_id, (QCExclusion(8, 'occlusion'),))
    window = Window(session, experiment)
    qtbot.addWidget(window)
    actions = PendulumAnalysisActions(window)
    try:
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None)
        assert actions.panel.plots['phase'].isHidden()
        assert actions.panel.repairButton.isEnabled()
        actions.panel.sgPresets[1].click()  # 7/3，明确选择而非静默缩窗。
        assert actions.panel.sgSettings() == (7, 3)
        assert '8 points eligible' in actions.panel.sgHint.text()
        assert 'Settings changed' in actions.panel.statusLabel.text()
        assert not actions.panel.repairButton.isEnabled()
        assert actions.panel.plots['phase'].isHidden()  # 旧图不重解释。
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None)
        assert 'custom SG7/3' in actions.panel.statusLabel.text()
        assert all(not actions.panel.plots[k].isHidden() for k in ('omega', 'phase', 'energy'))
        assert 'first/last 3 points' in actions.panel.note.text()
        assert not actions.panel.repair_frames
        session.save()
        from ai_physics_tracker.application.project_session import ProjectSession
        from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
        reopened = ProjectSession.load(ProjectRepository(), session.project_root)
        # Window替身没有真实媒体打开/时序探针；模拟本次媒体会话授权。
        reopened._verified_videos.add(experiment.video_id)
        window.analysisSession = reopened
        actions.resetContext()
        qtbot.waitUntil(lambda: actions._future is None)
        assert actions.panel.sgSettings() == (7, 3)
        assert actions.panel.statusLabel.text().startswith('Current')
        # 手输非法偶数窗口不计算，恢复默认可以再次计算。
        actions.panel.sgWindow.setValue(4)
        assert not actions.panel.computeButton.isEnabled()
        actions.panel.sgPresets[0].click()
        assert actions.panel.sgSettings() == (9, 3) and actions.panel.computeButton.isEnabled()
    finally:
        actions.shutdown()


def test_late_computation_rejects_changed_sg_settings(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    window = Window(session, experiment)
    qtbot.addWidget(window)
    actions = PendulumAnalysisActions(window)
    result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    try:
        future = Future()
        actions._newCancel()
        actions._submit('compute', analysis_input_state(session, experiment.experiment_id), future)
        assert not actions.panel.sgWindow.isEnabled()
        actions.panel.sgWindow.setValue(7)  # 程序改值也不能让旧请求提交。
        future.set_result(result)
        actions._poll()
        assert session.project.scientific_results == ()
    finally:
        actions.shutdown()


def test_undo_redo_analysis_restores_historical_sg_controls(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    window = Window(session, experiment)
    qtbot.addWidget(window)
    actions = PendulumAnalysisActions(window)
    try:
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None)
        actions.panel.setSG(7, 3)
        actions.compute()
        qtbot.waitUntil(lambda: actions._future is None)
        assert actions.panel.sgSettings() == (7, 3)
        for operation, expected in ((session.undo, (9, 3)), (session.redo, (7, 3))):
            assert operation()
            window.analysisChanged.emit()
            qtbot.waitUntil(lambda: actions._future is None and actions.panel.sgSettings() == expected)
            assert actions.panel.settingsMatchPayload()
            assert actions.panel.statusLabel.text().startswith('Current')
    finally:
        actions.shutdown()
