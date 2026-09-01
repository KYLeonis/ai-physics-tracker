"""GUI 组件与真实 CPU 引擎闭环冒烟；不是交互体验的 Human Review。"""

import os
from pathlib import Path
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from smoke_test_dlc_train import create_synthetic_video
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


class SyntheticTimingProbe:
    def probe(self, path, cancel=None):
        return TimingReport("cfr", "Known generated CFR fixture", 10, 30.0, 30.0)


def wait_task(app, window):
    deadline = time.monotonic() + 300
    while window.trackingActions.pending:
        app.processEvents()
        if time.monotonic() > deadline:
            window.trackingActions.cancel()
            raise TimeoutError("GUI tracking task timed out")
        time.sleep(0.01)
    run = window.analysisSession.tracking_runs()[-1]
    assert run.status == "completed", run.error_message
    print(run.task_type, run.status, run.extra_fields, flush=True)
    return run


def main():
    root = Path(tempfile.mkdtemp(prefix="physics_gui_tracking_")).resolve()
    print(f"Artifacts retained at: {root}", flush=True)
    media = root / "synthetic_pendulum.mp4"
    create_synthetic_video(media)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), SyntheticTimingProbe())
    try:
        window.show()
        assert window.openVideo(media, show_error=False)
        window.addTrackButton.click()
        session = window.analysisSession
        track_id = window.selectedTrackId
        for frame_index in range(0, 10, 2):
            session.mark_point(track_id, frame_index, 30 + 4 * frame_index, 50)
        session.save_as(root / "project")
        actions = window.trackingActions
        actions.refresh()
        panel = actions.panel
        panel.epochsSpinBox.setValue(1)
        panel.batchSizeSpinBox.setValue(1)
        panel.deviceComboBox.setCurrentText("cpu")
        panel.confidenceSpinBox.setValue(0.0)
        panel.trainButton.click()
        assert actions.pending
        trained = wait_task(app, window)
        assert trained.extra_fields["evaluation"]["status"] == "completed", trained.extra_fields["evaluation"]
        actions.refresh()
        assert panel.selectedTrainingRunId() == trained.run_id
        panel.inferButton.click()
        assert actions.pending
        inferred = wait_task(app, window)
        assert inferred.extra_fields["import_summary"]["inserted"] == 5
        assert len(session.manual_points(track_id)) == 5
        assert len(session.effective_points(track_id)) == 10
        assert window.analysisSession is session
        session.compute_kinematics(track_id)
        session.save()
        reopened = ProjectRepository().load(session.project_root)
        assert reopened.observations == session.project.observations
        print("GUI COMPONENT SMOKE PASSED; human interaction review still required", flush=True)
    finally:
        window.projectActions.close_allowed = True
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
