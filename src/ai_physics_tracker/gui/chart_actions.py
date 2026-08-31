"""图表用例编排：呈现帧同步、后台计算和主线程的安全批次提交。"""

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Qt

from ai_physics_tracker.application.chart_data import ChartData, build_chart_data
from ai_physics_tracker.application.kinematics_job import (
    KinematicsResult, prepare_kinematics_job, run_kinematics_job,
)
from ai_physics_tracker.domain.timeline import frame_to_time, time_to_frame, clamp_to_working_zone
from ai_physics_tracker.gui.chart_panel import ChartPanel

if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


class ChartActions(QObject):
    """GUI 线程拥有窗口/结果提交，worker 仅拥有独立计算快照。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.panel = ChartPanel(window)
        window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.panel)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kinematics")
        self._cancel = Event()
        self._future: Future[KinematicsResult] | None = None
        self._job_generation = -1
        self._context_generation = window.deliveryGeneration
        self._render_key = None
        self._closed = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        window.presentedFrameChanged.connect(self.presentFrame)
        window.frameRequestFailed.connect(self.clearRequest)
        window.frameRequested.connect(self.requestFrame)
        window.analysisChanged.connect(self.scheduleRefresh)
        window.projectChanged.connect(self.resetContext)
        window.selectedTrackChanged.connect(self.scheduleRefresh)
        window.closing.connect(self.shutdown)
        self.panel.selectionChanged.connect(self._selectionChanged)
        self.panel.parametersChanged.connect(self._parametersChanged)
        self.panel.recomputeRequested.connect(self.recompute)
        self.panel.cancelRequested.connect(self.cancel)
        self.panel.timeRequested.connect(self.seekTime)
        self.panel.frameRequested.connect(self.seekFrame)
        self.refresh()

    @property
    def pending(self) -> bool:
        return self._future is not None

    def scheduleRefresh(self, *_args) -> None:
        if not self._closed and not self._refresh_timer.isActive():
            self._refresh_timer.start(0)

    def resetContext(self) -> None:
        self._cancel.set()
        self._future = None
        self._timer.stop()
        self._context_generation = self.window.deliveryGeneration
        self._render_key = None
        self.panel.setTracks((), None, reset=True)
        self.panel.jobLabel.clear()
        self.clearRequest()
        self.refresh()

    def refresh(self) -> None:
        if self._closed:
            return
        session, video_id = self.window.analysisSession, self.window.activeVideoId
        if session is None or video_id is None:
            self.panel.setTracks((), None, reset=True)
            self.panel.contextLabel.setText("No video selected")
            for plot in self.panel.plots.values():
                plot.renderData(ChartData("", "Time", "Position", "s", "", (), ("No video selected",), False))
                plot.setNavigation(False, None)
                plot.setFrame(None, None)
            self.panel.recomputeButton.setEnabled(False)
            self.panel.cancelButton.setEnabled(False)
            self.panel.updateStatus()
            return
        project = session.project
        video = next(item for item in project.videos if item.video_id == video_id)
        tracks = tuple(track for track in session.tracks if track.video_id == video_id)
        self.panel.setTracks(tracks, self.window.selectedTrackId)
        selected = self.panel.checkedTracks()
        timeline = next(item for item in project.timelines if item.video_id == video_id)
        calibration = session.active_calibration(video_id)
        smoothed = self.panel.positionSource.currentIndex() == 1
        key = (self.window.deliveryGeneration, video_id, selected, smoothed, tracks,
               timeline, calibration, project.derived)
        if key != self._render_key:
            for kind, plot in self.panel.plots.items():
                plot.renderData(build_chart_data(project, video_id, selected, kind, smoothed=smoothed))
            self._render_key = key
        bounds = tuple(frame_to_time(frame, timeline) for frame in timeline.working_zone)
        can_navigate = self.window.presentedFrameIndex is not None
        for plot in self.panel.plots.values():
            plot.setNavigation(can_navigate, bounds)
        timing = session.measurement_timing_detail(video_id)
        historical_approximation = any(
            item.extra_fields.get("timing_context", {}).get("approximation")
            for item in project.derived if item.track_id in selected
            and isinstance(item.extra_fields.get("timing_context"), dict))
        self.panel.contextLabel.setText(
            "Approximate nominal timing — velocity/acceleration accuracy is not guaranteed"
            if timing or historical_approximation or video.vfr_suspected else
            "Nominal timeline; uncalibrated data use pixels" if calibration is None else "Calibrated coordinates; nominal timeline")
        if not session.can_measure(video_id):
            self.panel.contextLabel.setText(self.panel.contextLabel.text() + " — cached results only; timing not authorized")
        self.panel.recomputeButton.setEnabled(bool(selected) and session.can_measure(video_id) and not self.pending)
        self.panel.cancelButton.setEnabled(self.pending)
        self.presentFrame(self.window.presentedFrameIndex)
        self.panel.updateStatus()

    def presentFrame(self, frame_index: int | None) -> None:
        if self._closed or self._context_generation != self.window.deliveryGeneration:
            return
        session, video_id = self.window.analysisSession, self.window.activeVideoId
        timeline = next((item for item in session.project.timelines if item.video_id == video_id), None) if session else None
        time_s = frame_to_time(frame_index, timeline) if frame_index is not None and timeline else None
        for plot in self.panel.plots.values():
            plot.setFrame(frame_index, time_s)

    def seekTime(self, time_s: float) -> None:
        session, video_id = self.window.analysisSession, self.window.activeVideoId
        if session is None or video_id is None:
            return
        timeline = next(item for item in session.project.timelines if item.video_id == video_id)
        video = next(item for item in session.project.videos if item.video_id == video_id)
        try:
            frame_index = time_to_frame(time_s, timeline, video.frame_count)
        except ValueError:
            return  # 非有限鼠标映射不是合法的导航请求。
        self.seekFrame(frame_index)

    def seekFrame(self, frame_index: int) -> None:
        self.window.seekFrame(frame_index)

    def requestFrame(self, frame_index: int) -> None:
        session = self.window.analysisSession
        if session is None or self._context_generation != self.window.deliveryGeneration:
            return
        timeline = next(item for item in session.project.timelines
                        if item.video_id == self.window.activeVideoId)
        time_s = frame_to_time(clamp_to_working_zone(frame_index, timeline), timeline)
        for plot in self.panel.plots.values():
            plot.setRequestedTime(time_s)

    def clearRequest(self) -> None:
        for plot in self.panel.plots.values():
            plot.setRequestedTime(None)

    def _selectionChanged(self) -> None:
        if self.pending:
            self.cancel()
        self.scheduleRefresh()

    def _parametersChanged(self) -> None:
        if self.pending:
            self.cancel()
        self.panel.jobLabel.setText("Settings not applied — recompute checked tracks")

    def recompute(self) -> None:
        if self.pending or self.window.projectActions.busy or self._closed:
            return
        session, video_id = self.window.analysisSession, self.window.activeVideoId
        if session is None or video_id is None:
            return
        try:
            job = prepare_kinematics_job(session, video_id, self.panel.checkedTracks(), self.panel.parameters())
        except ValueError as error:
            self.panel.jobLabel.setText(str(error))
            return
        except Exception as error:
            self.panel.jobLabel.setText(f"Cannot calculate: {error}")
            return
        self._cancel = Event()
        self._job_generation = self.window.deliveryGeneration
        self._future = self._executor.submit(run_kinematics_job, job, self._cancel)
        self.panel.jobLabel.setText("Computing: " + ", ".join(track.name for track in job.inputs.tracks))
        self._timer.start(30)
        self.refresh()

    def cancel(self) -> None:
        self._cancel.set()
        self.panel.jobLabel.setText("Calculation cancelled — pending results will be discarded")

    def _poll(self) -> None:
        future = self._future
        if future is None or not future.done() or self.window.projectActions.busy:
            return
        self._timer.stop()
        self._future = None
        try:
            result = future.result()
            if self._cancel.is_set() or self._job_generation != self.window.deliveryGeneration:
                raise CancelledError()
            session = self.window.analysisSession
            if session is None:
                raise CancelledError()
            session.apply_kinematics_result(result)
        except CancelledError:
            self.panel.jobLabel.setText("Calculation cancelled; no results committed")
        except Exception as error:
            self.panel.jobLabel.setText(f"Calculation not committed: {error}")
        else:
            self.panel.jobLabel.setText("Computed — save project to keep results")
            self.window.refreshAnalysisHistory()
        self.refresh()

    def shutdown(self) -> None:
        self._closed = True
        self._cancel.set()
        self._future = None
        self._timer.stop()
        self._refresh_timer.stop()
        # worker 不持有 Qt 对象；单次 SciPy 运算不能强行终止，结束后无人接收其结果。
        self._executor.shutdown(wait=False, cancel_futures=True)
