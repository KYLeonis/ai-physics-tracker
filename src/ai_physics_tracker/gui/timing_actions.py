"""非模态时序验证与自动采用合格近似；只在 GUI 线程提交结果。"""

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer

from ai_physics_tracker.application.project_media import PreparedProject, ProjectMediaService, ValidatedMedia
from ai_physics_tracker.application.project_session import ProjectSessionError
from ai_physics_tracker.application.video_timing import TimingReport, approximation_errors

if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


class TimingActions(QObject):
    """验证不占用项目菜单的 busy 状态；旧任务取消后不再投递结果。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-timing")
        self._cancel = Event()
        self._future: Future[ValidatedMedia] | None = None
        self._prepared: PreparedProject | None = None
        self._service: ProjectMediaService | None = None
        self._token = 0
        self._report = TimingReport("unknown", "No video selected")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        window.timingButton.clicked.connect(self._clicked)

    @property
    def pending(self) -> bool:
        return self._future is not None

    def adopt(self, prepared: PreparedProject, token: int, service: ProjectMediaService | None) -> None:
        self._cancel.set()
        self._timer.stop()
        self._future = None
        self._prepared, self._service, self._token = prepared, service, token
        self._report = prepared.timing
        self._applyReport()
        if prepared.validation is not None and service is not None:
            self._start()

    def _start(self) -> None:
        request = self._prepared.validation if self._prepared else None
        if request is None or self._service is None:
            return
        self._cancel = Event()
        self._future = self._executor.submit(self._service.validate, request, self._cancel)
        self.window.timingLabel.setText("Validating timing in background — browsing available; measurements locked")
        self.window.timingButton.setText("Cancel validation")
        self.window.timingButton.show()
        self._timer.start(30)

    def _poll(self) -> None:
        future = self._future
        # 保存副本的提交结束后再合并，避免结果被尚在 IO 中的旧副本覆盖。
        if future is None or not future.done() or self.window.projectActions.busy:
            return
        self._timer.stop()
        self._future = None
        if self._token != self.window._delivery_generation:
            return
        try:
            result = future.result()
            if self._cancel.is_set():
                raise CancelledError()
        except CancelledError:
            self._report = TimingReport("unknown", "Validation cancelled; browsing only")
        except Exception as error:
            self._report = TimingReport("unknown", f"Validation failed: {error}")
        else:
            self._report = result.timing
            session = self.window._annotation_session
            video_id = self.window._annotation_video_id
            if session is not None and video_id is not None:
                session.record_media_validation(video_id, result.timing, result.sha256)
                self.window.projectActions.refresh()
        self._applyReport()
        self.window.statusBar().showMessage(self._report.reason +
            (" — measurements enabled" if self.window._measurement_allowed else " — browsing only"))

    def _applyReport(self) -> None:
        window = self.window
        session, video_id = window._annotation_session, window._annotation_video_id
        if self._report.status == "near_cfr" and session is not None and video_id is not None:
            try:
                session.accept_approximate_timing(video_id, self._report, automatic=True)
            except ProjectSessionError as error:
                self._report = replace(self._report, status="unknown", reason=str(error))
                session.confirm_video_timing(video_id, self._report)
        window._measurement_allowed = bool(session is not None and video_id is not None
                                           and self._report.status in ("cfr", "near_cfr") and session.can_measure(video_id))
        self.window.addTrackButton.setEnabled(self.window._measurement_allowed)
        self.window._refreshCalibrationUI()
        self._showReport()
        self.window.analysisChanged.emit()

    def _showReport(self) -> None:
        window = self.window
        report = self._report
        window.timingButton.hide()
        window.addTrackButton.setToolTip(report.reason)
        if report.status == "cfr":
            window.timingLabel.setText("Timing verified: CFR — measurements enabled")
            return
        if report.status == "near_cfr" and window._timeline is not None:
            errors = approximation_errors(report, window._timeline.fps_nominal)
            if errors is not None:
                window.timingLabel.setText(
                    f"Approximate timing (automatic): {window._timeline.fps_nominal:.8g} FPS; max time error ≈ {errors[0]*1000:.4f} ms; "
                    f"interval error ≈ {errors[1]*1000:.4f} ms — measurements enabled")
                return
            window.timingLabel.setText("Browsing only: saved Timeline exceeds the timing approximation budget")
            return
        window.timingLabel.setText(f"Browsing only: {report.reason}")
        if report.status == "unknown" and self._prepared and self._prepared.validation:
            window.timingButton.setText("Retry validation")
            window.timingButton.show()

    def _clicked(self) -> None:
        window = self.window
        if window.projectActions.busy:
            return
        if self.pending:
            self._cancel.set()
            window.timingLabel.setText("Cancelling timing validation — browsing remains available")
            return
        self._start()

    def shutdown(self) -> None:
        self._cancel.set()
        self._timer.stop()
        self._future = None
        self._executor.shutdown(wait=True, cancel_futures=True)
