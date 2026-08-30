"""首帧预览、后台时序验证与近似授权的 Qt 回归测试。"""

from concurrent.futures import CancelledError
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from threading import Event

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


@pytest.fixture(autouse=True)
def reject_unexpected_error_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """意外错误直接令测试失败，不在无头环境留下等待点击的模态框。"""

    def fail(*args):
        pytest.fail(f"Unexpected error dialog: {args[-1]}")
    monkeypatch.setattr(QMessageBox, "critical", fail)


def _cfr_report() -> TimingReport:
    """构造与五帧、10 FPS 合成视频匹配的严格 CFR 结论。"""

    return TimingReport(
        status="cfr",
        reason="strict CFR test result",
        frame_count=5,
        fps_measured=10.0,
        fps_reference=10.0,
    )


def _near_report() -> TimingReport:
    """构造落在 ADR-0007 近似预算内的 near-CFR 结论。"""

    return TimingReport(
        status="near_cfr",
        reason="bounded near-CFR test result",
        frame_count=5,
        fps_measured=10.0,
        fps_reference=10.0,
        max_grid_error_s=0.0001,
        max_interval_error_s=0.0002,
    )


def _unknown_report() -> TimingReport:
    return TimingReport(
        status="unknown",
        reason="timing probe unavailable",
        frame_count=0,
    )


@dataclass(frozen=True)
class _ProbeStep:
    report: TimingReport
    block: bool = False
    cancel_aware: bool = True


class _ScriptedProbe:
    """按调用顺序返回报告，可用 Event 精确控制后台验证时机。"""

    def __init__(self, *steps: _ProbeStep) -> None:
        self._steps = steps
        self.calls = 0
        self.started = Event()
        self.completed = Event()
        self.cancel_seen = Event()
        self.release = Event()

    def probe(self, path: Path, cancel: Event | None = None) -> TimingReport:
        del path
        step = self._steps[min(self.calls, len(self._steps) - 1)]
        self.calls += 1
        if step.block:
            self.started.set()
            while not self.release.wait(0.01):
                if step.cancel_aware and cancel is not None and cancel.is_set():
                    self.cancel_seen.set()
                    raise CancelledError()
        self.completed.set()
        return step.report


def _window(probe: _ScriptedProbe) -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        probe,
    )


def _start_deferred_open(window: MainWindow, path: Path) -> None:
    """走用户菜单使用的 deferred timing 加载路径。"""

    window.projectActions._load(
        lambda service, cancel: service.open_video(path, cancel)
    )


def _start_deferred_project_open(window: MainWindow, root: Path) -> None:
    window.projectActions._load(
        lambda service, cancel: service.open_project(root, cancel)
    )


def _wait_for_preview(window: MainWindow, probe: _ScriptedProbe, qtbot: QtBot) -> None:
    qtbot.waitUntil(probe.started.is_set, timeout=5000)
    qtbot.waitUntil(window.videoView.hasFrame, timeout=5000)
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)


def test_deferred_load_adopts_first_frame_before_slow_timing_probe_finishes(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    probe = _ScriptedProbe(_ProbeStep(_cfr_report(), block=True, cancel_aware=True))
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    try:
        _start_deferred_open(window, synthetic_video_path)
        _wait_for_preview(window, probe, qtbot)

        assert window.videoView.hasFrame()
        assert window.frameLabel.text() == "Frame: 0 / 4"
        assert window.frameSpinBox.isEnabled()
        assert window.nextButton.isEnabled()
        assert window.timelineSlider.isEnabled()
        assert window.timingActions.pending
        assert not window.addTrackButton.isEnabled()
        assert "Validating timing" in window.timingLabel.text()
        window.nextButton.click()
        qtbot.waitUntil(lambda: window._presented_frame_index == 1, timeout=5000)
        assert window.timingActions.pending
    finally:
        probe.release.set()
        qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)

    assert window._measurement_allowed
    assert window.addTrackButton.isEnabled()


def test_unknown_timing_keeps_add_track_disabled(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    probe = _ScriptedProbe(_ProbeStep(_unknown_report()))
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    _start_deferred_open(window, synthetic_video_path)
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)

    assert window.videoView.hasFrame()
    assert not window._measurement_allowed
    assert not window.addTrackButton.isEnabled()
    assert window.timingButton.isVisible()
    assert "Retry" in window.timingButton.text()

    window.addTrackButton.click()
    assert window.trackList.count() == 0


def test_near_cfr_no_keeps_add_track_disabled_and_allows_later_confirmation(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_video_path: Path,
) -> None:
    probe = _ScriptedProbe(_ProbeStep(_near_report()))
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    _start_deferred_open(window, synthetic_video_path)
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)
    assert not window.addTrackButton.isEnabled()
    assert window.timingButton.isVisible()
    assert "Near-CFR" in window.timingLabel.text()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.No,
    )
    window.timingButton.click()

    assert not window._measurement_allowed
    assert not window.addTrackButton.isEnabled()
    assert window.timingButton.isVisible()


def test_near_cfr_yes_records_source_detail_and_reopen_requires_confirmation(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_video_path: Path,
    tmp_path: Path,
) -> None:
    probe = _ScriptedProbe(_ProbeStep(_near_report()))
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    _start_deferred_open(window, synthetic_video_path)
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    window.timingButton.click()
    assert window._measurement_allowed
    assert window.addTrackButton.isEnabled()

    window.addTrackButton.click()
    session = window._annotation_session
    assert session is not None
    track = session.tracks[0]
    point = session.mark_point(track.track_id, 2, 17.5, 21.25)
    assert point.source_detail is not None
    detail = json.loads(point.source_detail)
    assert detail["timing_method"] == "near_cfr_user_accepted_v1"
    assert detail["fps_nominal"] == pytest.approx(10.0)
    assert detail["max_grid_error_s"] == pytest.approx(0.0001)
    assert detail["max_interval_error_s"] == pytest.approx(0.0002)

    root = tmp_path / "near-cfr-project"
    session.save_as(root)
    original_source_detail = point.source_detail

    _start_deferred_project_open(window, root)
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)

    assert window._annotation_session is not None
    assert window._annotation_session.project.observations[0].source_detail == original_source_detail
    assert not window._measurement_allowed
    assert not window.addTrackButton.isEnabled()
    assert window.timingButton.isVisible()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.StandardButton.No,
    )
    window.timingButton.click()
    assert not window._measurement_allowed
    assert not window.addTrackButton.isEnabled()


def test_late_timing_result_after_opening_new_video_cannot_change_active_session(
    qtbot: QtBot,
    synthetic_video_path: Path,
    tmp_path: Path,
) -> None:
    second_video = tmp_path / "second.avi"
    shutil.copyfile(synthetic_video_path, second_video)
    probe = _ScriptedProbe(
        _ProbeStep(_cfr_report(), block=True, cancel_aware=False),
        _ProbeStep(_unknown_report()),
    )
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    try:
        _start_deferred_open(window, synthetic_video_path)
        _wait_for_preview(window, probe, qtbot)
        first_session = window._annotation_session
        assert first_session is not None

        _start_deferred_open(window, second_video)
        qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
        qtbot.waitUntil(
            lambda: window._annotation_session is not first_session,
            timeout=5000,
        )
        assert window._annotation_session is not None
        assert window._annotation_session.project.name == "second"
        assert window._annotation_session.project.videos[0].original_path == str(
            second_video.resolve()
        )

        probe.release.set()
        qtbot.waitUntil(lambda: probe.calls >= 2, timeout=5000)
        qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)
        assert window._annotation_session.project.name == "second"
        assert window._annotation_session.project.videos[0].original_path == str(
            second_video.resolve()
        )
        assert not window._measurement_allowed
        assert not window.addTrackButton.isEnabled()
    finally:
        probe.release.set()


def test_late_timing_result_after_new_empty_project_cannot_restore_old_video(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    probe = _ScriptedProbe(
        _ProbeStep(_cfr_report(), block=True, cancel_aware=False),
    )
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    try:
        _start_deferred_open(window, synthetic_video_path)
        _wait_for_preview(window, probe, qtbot)
        window.adoptEmptyProject()
        assert window._annotation_session is not None
        assert window._annotation_session.project.videos == ()
        assert window._annotation_video_id is None
        assert not window.addTrackButton.isEnabled()
        assert not window.timingActions.pending

        probe.release.set()
        qtbot.waitUntil(probe.completed.is_set, timeout=5000)
        qtbot.wait(50)
        assert window._annotation_session.project.videos == ()
        assert window._annotation_video_id is None
        assert not window.addTrackButton.isEnabled()
    finally:
        probe.release.set()


def test_cancel_validation_exposes_retry_and_retry_can_grant_cfr_permission(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    probe = _ScriptedProbe(
        _ProbeStep(_unknown_report(), block=True, cancel_aware=True),
        _ProbeStep(_cfr_report()),
    )
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    _start_deferred_open(window, synthetic_video_path)
    _wait_for_preview(window, probe, qtbot)
    assert window.timingActions.pending
    assert window.timingButton.text() == "Cancel validation"

    window.timingButton.click()
    qtbot.waitUntil(probe.cancel_seen.is_set, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)
    assert not window._measurement_allowed
    assert not window.addTrackButton.isEnabled()
    assert "Retry" in window.timingButton.text()

    window.timingButton.click()
    qtbot.waitUntil(lambda: probe.calls >= 2, timeout=5000)
    qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)
    assert window._measurement_allowed
    assert window.addTrackButton.isEnabled()
    assert "CFR" in window.timingLabel.text()


def test_save_during_validation_preserves_points_and_applies_permission_to_saved_session(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_video_path: Path,
    tmp_path: Path,
) -> None:
    probe = _ScriptedProbe(
        _ProbeStep(_cfr_report()),
        _ProbeStep(_cfr_report(), block=True, cancel_aware=False),
    )
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    # 先建立一个含 raw point 的已保存项目，随后以 deferred timing 重开。
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    session = window._annotation_session
    assert session is not None
    track = session.tracks[0]
    original_point = session.mark_point(track.track_id, 1, 12.0, 13.0)
    root = tmp_path / "saved-during-validation"
    session.save_as(root)

    save_started = Event()
    release_save = Event()
    try:
        _start_deferred_project_open(window, root)
        qtbot.waitUntil(probe.started.is_set, timeout=5000)
        qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
        qtbot.waitUntil(lambda: window.timingActions.pending, timeout=5000)
        active_before_save = window._annotation_session
        assert active_before_save is not None
        assert active_before_save.project.observations == (original_point,)
        assert not window.addTrackButton.isEnabled()

        repository = window._annotation_repository
        original_save = repository.save

        def blocked_save(project_root: Path, project):
            save_started.set()
            if not release_save.wait(5.0):
                raise TimeoutError("synthetic save gate was not released")
            return original_save(project_root, project)

        monkeypatch.setattr(repository, "save", blocked_save)
        window.projectActions.save()
        qtbot.waitUntil(save_started.is_set, timeout=5000)

        # 让时序结果先完成；ProjectActions 忙时 TimingActions 不得提交它。
        probe.release.set()
        qtbot.waitUntil(probe.completed.is_set, timeout=5000)
        qtbot.waitUntil(lambda: window.projectActions.busy, timeout=5000)
        assert window._annotation_session is active_before_save
        assert window._annotation_session.project.observations == (original_point,)
        assert not window._measurement_allowed
        assert not window.addTrackButton.isEnabled()

        release_save.set()
        qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
        qtbot.waitUntil(lambda: not window.timingActions.pending, timeout=5000)
        assert window._annotation_session is not active_before_save
        assert window._annotation_session.project.observations == (original_point,)
        assert window._measurement_allowed
        assert window.addTrackButton.isEnabled()
    finally:
        probe.release.set()
        release_save.set()


def test_window_close_cancels_pending_timing_validation(
    qtbot: QtBot,
    synthetic_video_path: Path,
) -> None:
    probe = _ScriptedProbe(
        _ProbeStep(_cfr_report(), block=True, cancel_aware=True),
    )
    window = _window(probe)
    qtbot.addWidget(window)
    window.show()

    _start_deferred_open(window, synthetic_video_path)
    _wait_for_preview(window, probe, qtbot)
    assert window.timingActions.pending

    window.close()

    assert probe.cancel_seen.is_set()
    assert not window.isVisible()
    assert not window.timingActions.pending
