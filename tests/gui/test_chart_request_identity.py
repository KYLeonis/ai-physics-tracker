"""真实解码线程的请求身份回归：旧帧/旧错误不得覆盖较新的图表导航。"""

from threading import Event

import numpy as np
import pytest

from ai_physics_tracker.application.playback import DecodeDelivery
from ai_physics_tracker.application.video import DecodedFrame, VideoFrameError, VideoStreamInfo
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


class GatedReader:
    def __init__(self, fail_first):
        self.is_open = False
        self.info = VideoStreamInfo(64, 48, 10, 5, "fake")
        self.fail_first = fail_first
        self.first_started, self.first_release = Event(), Event()
        self.second_started, self.second_release = Event(), Event()

    def open(self, _path):
        self.is_open = True
        return self.info

    def read_frame(self, frame_index):
        if frame_index == 1:
            self.first_started.set()
            assert self.first_release.wait(5)
            if self.fail_first:
                raise VideoFrameError("old request failed")
        if frame_index == 3:
            self.second_started.set()
            assert self.second_release.wait(5)
        return DecodedFrame(frame_index, np.zeros((48, 64, 3), dtype=np.uint8))

    def close(self):
        self.is_open = False


class TimingProbe:
    def probe(self, _path, _cancel=None):
        return TimingReport("cfr", "test", 5, 10)


@pytest.mark.parametrize("fail_first", [False, True])
def test_old_delivery_cannot_replace_new_target_or_step_base(qtbot, synthetic_video_path, fail_first):
    readers = []
    def factory():
        reader = GatedReader(fail_first)
        readers.append(reader)
        return VideoSession(reader)
    window = MainWindow(factory, ProjectRepository(), TimingProbe())
    qtbot.addWidget(window)
    window.show()
    try:
        assert window.openVideo(synthetic_video_path, show_error=False)
        reader = readers[-1]
        window._requestFrame(1)
        qtbot.waitUntil(reader.first_started.is_set)
        window.chartActions.seekFrame(3)
        with qtbot.waitSignal(window.decodeCompleted, timeout=5000):
            reader.first_release.set()
        qtbot.waitUntil(reader.second_started.is_set)
        assert window.presentedFrameIndex == 0
        assert window._last_requested_frame == 3
        assert window._has_pending_request
        assert window.chartActions.panel.plots["x_t"].requestLine.value() == pytest.approx(0.3)
        window.nextButton.click()
        assert window._last_requested_frame == 4
        reader.second_release.set()
        qtbot.waitUntil(lambda: window.presentedFrameIndex == 4, timeout=5000)
        assert not window._has_pending_request
        assert window.chartActions.panel.plots["x_t"].actualLine.value() == pytest.approx(0.4)
    finally:
        for reader in readers:
            reader.first_release.set()
            reader.second_release.set()
        window.projectActions.close_allowed = True
        window.close()


def test_same_frame_old_error_is_ignored_and_latest_failure_restores_base(
    qtbot, synthetic_video_path, monkeypatch,
):
    window = MainWindow(lambda: VideoSession(GatedReader(False)), ProjectRepository(), TimingProbe())
    qtbot.addWidget(window)
    assert window.openVideo(synthetic_video_path, show_error=False)
    requests = []
    def request(frame_index):
        requests.append(frame_index)
        return len(requests)
    monkeypatch.setattr(window._async, "request_frame", request)
    window.chartActions.seekFrame(3)
    window.chartActions.seekFrame(3)
    window.decodeCompleted.emit(DecodeDelivery(1, 3, error=VideoFrameError("old")), window.deliveryGeneration)
    assert window._has_pending_request and window._last_requested_frame == 3
    assert window.chartActions.panel.plots["x_t"].requestLine.value() == pytest.approx(0.3)
    window.decodeCompleted.emit(DecodeDelivery(2, 3, error=VideoFrameError("latest")), window.deliveryGeneration)
    assert not window._has_pending_request
    assert window._last_requested_frame == 0
    assert window.chartActions.panel.plots["x_t"].requestLine.value() == pytest.approx(0.0)
    window.nextButton.click()
    assert requests[-1] == 1
