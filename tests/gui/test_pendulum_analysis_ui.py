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
