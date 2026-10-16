"""图表用例编排：呈现帧同步、后台计算和主线程的安全批次提交。

Phase 6.2：线性与角运动两个分析族共用同一个 executor / Event / Future /
poll 生命周期（不新增第二套骨架）；按当前标签族路由到 kinematics 或
angular 批次，参数 / 参考 / 选择 / 工程 / 视频变化取消本 GUI 的在途任务，
晚到结果由 ADR-0020 的输入与版本复核兜底拒绝。
"""

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING
from uuid import UUID
from dataclasses import asdict
import json

from PySide6.QtCore import QObject, QSignalBlocker, QTimer, Qt

from ai_physics_tracker.application.angular_job import (
    AngularJob, AngularResult, AngularSpec, prepare_angular_job, run_angular_job,
)
from ai_physics_tracker.application.chart_data import ChartData, build_chart_data
from ai_physics_tracker.application.chart_recipe import reference_recipe, smoothing_recipe
from ai_physics_tracker.application.project_media import workflow_state
from ai_physics_tracker.application.kinematics_job import (
    AnalysisInputs, KinematicsJob, KinematicsResult, analysis_inputs,
    prepare_kinematics_job, run_kinematics_job,
)
from ai_physics_tracker.application.project_session import ProjectSessionError
from ai_physics_tracker.domain.angular import AngularReference, PendulumReference, TwoPointReference
from ai_physics_tracker.domain.derived import ANGULAR_KINDS, KINEMATICS_KINDS
from ai_physics_tracker.domain.timeline import frame_to_time, time_to_frame, clamp_to_working_zone
from ai_physics_tracker.gui.chart_panel import ChartPanel
from ai_physics_tracker.gui.signal_analysis_panel import SignalAnalysisPanel
from ai_physics_tracker.application.signal_analysis_job import (
    SignalAnalysisJob, SignalAnalysisResult, prepare_signal_analysis, run_signal_analysis,
)
from ai_physics_tracker.domain.expression import parse_expression
from ai_physics_tracker.domain.analysis import source_fingerprint
from ai_physics_tracker.gui.signal_preview import SignalPreview
from ai_physics_tracker.application.fit_attempts import FitAttempts

if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


def _run_chart_job(job: KinematicsJob | AngularJob | SignalAnalysisJob, cancel: Event):
    """后台线程唯一入口：按任务类型分发到既有 runner，共享一个执行器。"""

    if isinstance(job, AngularJob):
        return run_angular_job(job, cancel)
    if isinstance(job, SignalAnalysisJob):
        return run_signal_analysis(job, cancel)
    return run_kinematics_job(job, cancel)


class ChartActions(QObject):
    """GUI 线程拥有窗口/结果提交，worker 仅拥有独立计算快照。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.panel = ChartPanel(window)  # Phase 5.7：由 MainWindow 挂入分析工作区
        self.signalPanel = SignalAnalysisPanel(window)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kinematics")
        self._cancel = Event()
        self._future: Future[KinematicsResult | AngularResult | SignalAnalysisResult] | None = None
        self._job_generation = -1
        self._job_inputs: AnalysisInputs | None = None
        self._signal_job: SignalAnalysisJob | None = None
        self._job_workspace = window.currentWorkspace
        self._context_generation = window.deliveryGeneration
        self._render_key = None
        self._seeded_controls = None
        self._settings_edited = False
        self._closed = False
        self.attempts = FitAttempts()
        self.preview = SignalPreview(self)
        self.signalPanel.previousButton.clicked.connect(self.preview.invalidate)
        self.signalPanel.latestButton.clicked.connect(self.preview.invalidate)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        window.presentedFrameChanged.connect(self.presentFrame)
        window.frameRequestFailed.connect(self.clearRequest)
        window.frameRequested.connect(self.requestFrame)
        window.analysisChanged.connect(self._analysisChanged)
        window.projectChanged.connect(self.resetContext)
        window.selectedTrackChanged.connect(self._windowSelectionChanged)
        window.closing.connect(self.shutdown)
        self.panel.selectionChanged.connect(self._selectionChanged)
        self.panel.parametersChanged.connect(self._settingsChanged)
        self.panel.displayChanged.connect(self.scheduleRefresh)
        self.panel.familyChanged.connect(self._familyChanged)
        self.panel.angularControls.referenceEdited.connect(self._settingsChanged)
        self.panel.angularControls.referenceApplied.connect(self._referenceApplied)
        self.panel.recomputeRequested.connect(self.recompute)
        self.panel.cancelRequested.connect(self.cancel)
        self.panel.timeRequested.connect(self.seekTime)
        self.panel.frameRequested.connect(self.seekFrame)
        self.signalPanel.fitRequested.connect(lambda: self.analyzeSignal(True))
        self.signalPanel.recurrenceRequested.connect(lambda: self.analyzeSignal(False))
        self.signalPanel.previewRequested.connect(self.previewSignal)
        self.signalPanel.sourcePreviewRequested.connect(self.previewRecurrence)
        self.signalPanel.cancelRequested.connect(self.cancel)
        self.signalPanel.settingsChanged.connect(self._signalEdited)
        self.signalPanel.targetChanged.connect(self._signalTargetChanged)
        self.signalPanel.frameRequested.connect(self.seekFrame)
        self.signalPanel.undoRequested.connect(lambda: self.analysisHistory(False))
        self.signalPanel.redoRequested.connect(lambda: self.analysisHistory(True))
        self.signalPanel.prepareRequested.connect(self.prepareSignalSource)
        self.signalPanel.timingRequested.connect(lambda: window.timingButton.click())
        self.signalPanel.setupRequested.connect(self.prepareSignalReference)
        self.signalPanel.attemptChoice.currentIndexChanged.connect(self.showAttempt)
        self.signalPanel.retryJournalButton.clicked.connect(self.retryJournal)
        self.refresh()

    @property
    def pending(self) -> bool:
        return self._future is not None

    def scheduleRefresh(self, *_args) -> None:
        if not self._closed and not self._refresh_timer.isActive():
            self._refresh_timer.start(0)

    def _analysisChanged(self) -> None:
        # 保存 / 视图刷新也发同一信号，只取消科学输入或工作区已变化的任务。
        if self.pending and self._job_inputs is not None:
            inputs = self._job_inputs
            session = self.window.analysisSession
            try:
                current = (analysis_inputs(session, inputs.video.video_id,
                           tuple(track.track_id for track in inputs.tracks))
                           if session is not None else None)
            except ProjectSessionError:
                current = None
            source_changed = False
            if self._signal_job is not None and session is not None:
                job = self._signal_job
                source_changed = next((item for item in session.project.derived if item.derived_id == job.source.derived_id), None) != job.source
            if current != inputs or source_changed or self.window.currentWorkspace != self._job_workspace:
                self.cancel()
        self.scheduleRefresh()

    def resetContext(self) -> None:
        self.preview.invalidate()
        self._finishAttempt("interrupted", "Project / video context changed; pending result discarded")
        self._cancel.set()
        self._future = None
        self._job_inputs = None
        self._signal_job = None
        self._timer.stop()
        self._context_generation = self.window.deliveryGeneration
        self._render_key = None
        self._seeded_controls = None
        self._settings_edited = False
        # 参考坐标 / 参考轨迹只属于原视频；工程或视频切换后必须重新确认。
        self.panel.angularControls.clearApplied()
        self.panel.setTracks((), None, reset=True)
        with QSignalBlocker(self.panel.windowLength), QSignalBlocker(self.panel.polyorder):
            self.panel.windowLength.setValue(7)
            self.panel.polyorder.setValue(2)
        session = self.window.analysisSession
        state = workflow_state(session) if session is not None else {}
        self.adoptViewState(state.get("charts", {}))
        self.panel.jobLabel.clear()
        self.clearRequest()
        self.refresh()

    def refresh(self) -> None:
        if self._closed:
            return
        session, video_id = self.window.analysisSession, self.window.activeVideoId
        self.syncJournal()
        self.signalPanel.setContext(session, video_id, pending=self.pending)
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
        self.panel.angularControls.setTracks(tracks)
        selected = self.panel.checkedTracks()
        seed_key = (self.window.deliveryGeneration, self.panel.currentFamily, selected)
        if self._seeded_controls != seed_key:
            self._seeded_controls = seed_key
            # 只在上下文变化且没有草稿时恢复缓存配方；普通刷新不覆盖编辑。
            if not self._settings_edited:
                self._seedControlsFromDerived(project, selected)
        timeline = next(item for item in project.timelines if item.video_id == video_id)
        calibration = session.active_calibration(video_id)
        smoothed = self.panel.positionSource.currentIndex() == 1
        angle_unit = self.panel.currentAngleUnit()
        key = (self.window.deliveryGeneration, video_id, selected, smoothed, angle_unit, tracks,
               timeline, calibration, project.derived)
        if key != self._render_key:
            for kind, plot in self.panel.plots.items():
                plot.renderData(build_chart_data(project, video_id, selected, kind,
                                                 smoothed=smoothed, angle_unit=angle_unit))
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
        self.panel.contextLabel.setText(
            f"Current: {timeline.fps_nominal:g} fps, source frames "
            f"{timeline.working_zone[0]}–{timeline.working_zone[1]} — "
            + self.panel.contextLabel.text())
        if not session.can_measure(video_id):
            self.panel.contextLabel.setToolTip("Current timing is not authorized; cached results only")
        elif timing:
            self.panel.contextLabel.setToolTip("Current timing authorization: " + timing)
        else:
            self.panel.contextLabel.setToolTip("Current timing: verified nominal CFR")
        if not session.can_measure(video_id):
            self.panel.contextLabel.setText(self.panel.contextLabel.text() + " — cached results only; timing not authorized")
        angular_ready = (
            self.panel.currentFamily != "angular"
            or (calibration is not None and self.panel.angularControls.appliedReference() is not None))
        self.panel.recomputeButton.setEnabled(
            bool(selected) and session.can_measure(video_id) and not self.pending and angular_ready)
        self.panel.recomputeButton.setToolTip(
            "Computes θ, ω and α with the applied reference (requires an active calibration)"
            if self.panel.currentFamily == "angular" else
            "Computes the position, velocity and acceleration charts")
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

    def adoptViewState(self, state: dict) -> None:
        """恢复已保存的图表显示选项（保存重开 / 换视频）；缺省保持默认。"""

        self.panel.restoreViewState(state)

    def _selectionChanged(self) -> None:
        if self.pending:
            self.cancel()
        self.scheduleRefresh()

    def _windowSelectionChanged(self, *_args) -> None:
        # 主窗口轨迹选择会经 setTracks(QSignalBlocker) 静默改勾选集，
        # 不会触发 panel.selectionChanged；这里显式取消在途任务。
        self._selectionChanged()

    def _familyChanged(self, _family: str) -> None:
        # 切换分析族意味着重算目标集合改变，在途任务不再对应按钮语义。
        if self.pending:
            self.cancel()
        self.scheduleRefresh()
        tracking = getattr(self.window, "trackingActions", None)
        if tracking is not None:
            tracking.refresh()  # 任务卡 / 状态头的分析就绪按族投影

    def _settingsChanged(self) -> None:
        self._settings_edited = True
        if self.pending:
            self.cancel()
        self.panel.jobLabel.setText("Settings not applied — recompute checked tracks")
        self.scheduleRefresh()

    def _referenceApplied(self) -> None:
        self.scheduleRefresh()

    def _seedControlsFromDerived(self, project, track_ids: tuple[UUID, ...]) -> None:
        """从当前选中轨迹的已计算角运动结果恢复参考与 SG 配方（只播种一次）。

        恢复值标记为"已确认"（它们对应缓存事实）；无角运动结果或配方
        不可读时保持默认草稿，不猜测。渲染状态栏继续显示缓存配方，
        与用户此后未应用的编辑明确区分。
        """

        kinds = ANGULAR_KINDS if self.panel.currentFamily == "angular" else KINEMATICS_KINDS
        for track_id in track_ids:
            angular_record = next(
                (item for item in reversed(project.derived)
                 if item.track_id == track_id and item.kind in ANGULAR_KINDS),
                None)
            reference = reference_recipe(angular_record) if angular_record is not None else None
            seeded: AngularReference | None = None
            if reference is not None and reference.get("mode") == "pendulum":
                pivot = reference.get("pivot_px")
                try:
                    seeded = PendulumReference(pivot_px=(pivot[0], pivot[1]))
                except (TypeError, ValueError, IndexError):
                    seeded = None
            elif reference is not None and reference.get("mode") == "two_point":
                try:
                    seeded = TwoPointReference(
                        reference_track_id=UUID(str(reference.get("reference_track_id"))))
                except (TypeError, ValueError):
                    seeded = None
            if seeded is not None:
                self.panel.angularControls.seedApplied(seeded)
            record = next((item for item in reversed(project.derived)
                           if item.track_id == track_id and item.kind in kinds), None)
            if record is None:
                continue
            recipe = smoothing_recipe(record)
            if recipe is not None:
                with QSignalBlocker(self.panel.windowLength), QSignalBlocker(self.panel.polyorder):
                    self.panel.windowLength.setValue(int(recipe["window_length"]))
                    self.panel.polyorder.setValue(int(recipe["polyorder"]))
            return
        with QSignalBlocker(self.panel.windowLength), QSignalBlocker(self.panel.polyorder):
            self.panel.windowLength.setValue(7)
            self.panel.polyorder.setValue(2)

    def recompute(self) -> None:
        if self.pending or self.window.projectActions.busy or self._closed:
            return
        session, video_id = self.window.analysisSession, self.window.activeVideoId
        if session is None or video_id is None:
            return
        track_ids = self.panel.checkedTracks()
        try:
            if self.panel.currentFamily == "angular":
                job = self._prepare_angular_job(session, video_id, track_ids)
            else:
                job = prepare_kinematics_job(session, video_id, track_ids, self.panel.parameters())
        except ValueError as error:
            self.panel.jobLabel.setText(str(error))
            return
        except Exception as error:
            self.panel.jobLabel.setText(f"Cannot calculate: {error}")
            return
        self._cancel = Event()
        self._job_generation = self.window.deliveryGeneration
        self._job_inputs = job.inputs
        self._job_workspace = self.window.currentWorkspace
        self._future = self._executor.submit(_run_chart_job, job, self._cancel)
        self.panel.jobLabel.setText("Computing: " + ", ".join(
            track.name for track in job.inputs.tracks if track.track_id in track_ids))
        self._timer.start(30)
        self.refresh()

    def _prepare_angular_job(self, session, video_id, track_ids: tuple[UUID, ...]):
        """按已确认参考构造角运动批次；未确认 / 目标含 B 在此明确拒绝。"""

        reference: AngularReference | None = self.panel.angularControls.appliedReference()
        if reference is None:
            raise ValueError(
                "Set and apply an angular reference (pivot or track B) before recompute")
        if isinstance(reference, TwoPointReference) and reference.reference_track_id in track_ids:
            # 不静默删目标：要求用户显式取消勾选参考轨迹或换参考。
            raise ValueError(
                "The two-point reference track is also checked for recompute; "
                "uncheck it or choose another reference")
        specs = tuple(
            AngularSpec(track_id=track_id, reference=reference) for track_id in track_ids)
        return prepare_angular_job(session, video_id, specs, self.panel.parameters())

    def cancel(self) -> None:
        self._cancel.set()
        self.panel.jobLabel.setText("Calculation cancelled — pending results will be discarded")
        if self._signal_job is not None:
            self.signalPanel.jobLabel.setText("Calculation cancelled — saved result retained")

    def _poll(self) -> None:
        if self.attempts.active and not self._cancel.is_set():
            self.signalPanel.jobLabel.setText(f"Fitting current formula… {self.attempts.elapsed_s:.1f} s elapsed. Cancel is available.")
        future = self._future
        if future is None or not future.done() or self.window.projectActions.busy:
            return
        self._timer.stop()
        self._future = None
        self._job_inputs = None
        signal_job = self._signal_job
        self._signal_job = None
        result = None
        try:
            result = future.result()
            if self._cancel.is_set() or self._job_generation != self.window.deliveryGeneration:
                raise CancelledError()
            session = self.window.analysisSession
            if session is None:
                raise CancelledError()
            if isinstance(result, SignalAnalysisResult):
                if result.record is None:
                    self.signalPanel.jobLabel.setText(result.fit_outcome.status + ": " + result.fit_outcome.message + " — saved result retained")
                    self._finishAttempt(result.fit_outcome.status, result.fit_outcome.message, solver=asdict(result.fit_outcome))
                    next_step = {
                        "evaluation_limit": "Raise Model evaluation limit in Optional settings, or Estimate initial values and retry.",
                        "insufficient_samples": "Extend the interval or fix / remove free parameters.",
                        "unidentifiable": "Fix / remove redundant parameters or choose data that distinguishes them.",
                        "domain_error": "Check the formula domain (log, sqrt, division) and edit initial values.",
                    }.get(result.fit_outcome.status, "Inspect the initial curve, adjust values / bounds or Estimate, then retry.")
                    self.signalPanel.jobLabel.setText(self.signalPanel.jobLabel.text() + ". Next: " + next_step)
                    self.refresh()
                    return
                session.apply_analysis_result(result)
            elif isinstance(result, AngularResult):
                session.apply_angular_result(result)
            else:
                session.apply_kinematics_result(result)
        except CancelledError:
            from ai_physics_tracker.application.user_messages import charts_not_updated
            self.panel.jobLabel.setText(charts_not_updated(
                "calculation cancelled").full_text())
            if signal_job:
                self.signalPanel.jobLabel.setText("Calculation cancelled — saved result retained; edit settings or retry.")
                self._finishAttempt("cancelled", "Calculation cancelled; late result discarded")
        except Exception as error:
            from ai_physics_tracker.application.user_messages import charts_not_updated
            self.panel.jobLabel.setText(charts_not_updated(str(error)).full_text())
            if signal_job:
                self.signalPanel.jobLabel.setText(str(error) + " — saved result retained. Check source charts / settings, then retry.")
                self._finishAttempt("rejected" if isinstance(error, ProjectSessionError) else "failed", str(error))
        else:
            self._settings_edited = False
            self._seeded_controls = None
            self.panel.jobLabel.setText("Computed — save project to keep results")
            if signal_job:
                self.signalPanel.jobLabel.setText("Computed — save project to keep results")
                self._finishAttempt("completed", "Fit completed", summary=result.record.extra_fields["analysis"]["summary"])
            self.window.refreshAnalysisHistory()
        self.refresh()
        if signal_job and not self._cancel.is_set() and isinstance(result, SignalAnalysisResult) and result.record is not None:
            self.signalPanel.resultLabel.setText(self.signalPanel.resultLabel.text().replace("Latest applied fit", "Current fit result").replace("Latest applied crossings", "Current crossings"))
            self.signalPanel.draftLabel.setText("Current calculation result — save project to retain the scientific result")
            self.signalPanel.jobLabel.setText("Calculation completed. Inspect the overlay and error comparison; Save keeps the scientific result.")

    def _signalEdited(self) -> None:
        if hasattr(self.window, "trackingActions"):
            self.window.refreshAnalysisSourceBar()
        if self._signal_job is not None:
            self.cancel()
        self.signalPanel.refreshDraftDisplay()
        tracking = getattr(self.window, "trackingActions", None)
        if tracking is not None:
            tracking.refresh()
        if self.signalPanel.methods.currentIndex() == 0:
            self.preview.request()

    def analysisHistory(self, redo: bool) -> None:
        if self.pending or self.window.projectActions.busy or self._closed:
            return
        session = self.window.analysisSession
        if session is None:
            return
        try:
            changed = session.redo_analysis() if redo else session.undo_analysis()
        except ProjectSessionError as error:
            self.signalPanel.jobLabel.setText(str(error))
            return
        if changed:
            self.window.refreshAnalysisHistory()
            self.refresh()
            self.signalPanel.jobLabel.setText("Analysis history restored — saved settings remain available")

    def _signalTargetChanged(self) -> None:
        self._signalEdited()
        self.signalPanel.displaySaved()
        if self.signalPanel.methods.currentIndex() == 1:
            self.previewRecurrence()
        else:
            self.preview.request()

    def _prepareSignal(self, fitting: bool):
        session = self.window.analysisSession
        if session is None:
            raise ValueError("Open a project first")
        panel = self.signalPanel
        return prepare_signal_analysis(session, panel.selection(), panel.fitSpec() if fitting else panel.recurrenceSpec(),
                                       panel.resultFormulas() if fitting else ())

    def previewRecurrence(self) -> None:
        """只展示实际源样本，不计算或发布事件；调线后显式Measure才产生结果。"""
        if self.pending:
            return
        try:
            job = self._prepareSignal(False)
            self.signalPanel.renderSamples(job.samples, job.source.unit,
                                           wrapped=job.source.kind == "angular_position")
            self.signalPanel.refreshDraftDisplay()
            self.signalPanel.jobLabel.setText("Source preview — adjust reference, then Measure crossing intervals")
        except (ValueError, ProjectSessionError) as error:
            self.signalPanel.signalPlot.clear()
            self.signalPanel._valueRange = None
            self.signalPanel.jobLabel.setText(str(error))

    def previewSignal(self) -> None:
        self.preview.request(immediate=True)

    def analyzeSignal(self, fitting: bool) -> None:
        if self.pending or self.window.projectActions.busy or self._closed:
            return
        self.preview.invalidate()
        if fitting:
            self._startAttempt()
        try:
            job = self._prepareSignal(fitting)
        except (ValueError, ProjectSessionError) as error:
            self.signalPanel.jobLabel.setText(f"Fit blocked: {error}. Check source preparation and current settings.")
            self._finishAttempt("rejected", str(error))
            return
        except Exception as error:
            self.signalPanel.jobLabel.setText(f"Fit preparation failed: {error}. Check inputs and retry.")
            self._finishAttempt("failed", str(error))
            return
        try:
            if fitting and self.attempts.active:
                self.attempts.annotate(source_id=str(job.source.derived_id), source_fingerprint=source_fingerprint(job.source),
                                     sample_count=len(job.samples), unit=job.source.unit, spec=asdict(job.spec))
            self._cancel = Event()
            self._job_generation = self.window.deliveryGeneration
            self._job_inputs = job.inputs
            self._signal_job = job
            self._job_workspace = self.window.currentWorkspace
            self._future = self._executor.submit(_run_chart_job, job, self._cancel)
        except Exception as error:
            self._future = None
            self._signal_job = None
            self._job_inputs = None
            self._finishAttempt("failed", str(error))
            self.signalPanel.jobLabel.setText(f"Calculation could not start: {error}. Retry when the worker is available.")
            self.refresh()
            return
        self.signalPanel.jobLabel.setText("Computing…")
        self._timer.start(30)
        self.refresh()

    def prepareSignalSource(self) -> None:
        """在当前分析路径选择同一轨迹/族并调用既有计算；角参考仍需用户确认。"""
        panel = self.signalPanel
        track = panel.trackChoice.currentData()
        if track is not None:
            with QSignalBlocker(self.panel.trackChoices):
                for index in range(self.panel.trackChoices.count()):
                    item = self.panel.trackChoices.item(index)
                    item.setCheckState(Qt.CheckState.Checked if str(item.data(Qt.ItemDataRole.UserRole)) == track else Qt.CheckState.Unchecked)
        self.window.analysisTabs.setCurrentIndex(0)
        angular = panel.quantityChoice.currentText() in ("theta", "omega", "alpha")
        # 保留原族控件入口，用户可检查标定、参考和SG后显式重算。
        self.panel.tabs.setCurrentIndex(5 if angular else 0)
        self.panel.jobLabel.setText("Select / check the intended track and settings, then Recompute. Return to Fit a formula / Measure repeat intervals afterwards.")

    def prepareSignalReference(self) -> None:
        session = self.window.analysisSession
        if (self.signalPanel.quantityChoice.currentText() in ("theta", "omega", "alpha")
                and session is not None and session.active_calibration(self.window.activeVideoId) is not None):
            self.prepareSignalSource()
            self.panel.jobLabel.setText("Angular analysis requires calibration and a confirmed reference. Set these below, Apply reference, then Recompute.")
        else:
            self.window.setWorkspace("setup")

    def syncJournal(self, *, saved: bool = False) -> None:
        if not self.window.projectActions.busy:
            self.attempts.sync(self.window.analysisSession, saved=saved)
        self.showAttempts()

    def _startAttempt(self) -> None:
        self.syncJournal()
        if self.attempts.journal is None:
            return
        panel = self.signalPanel
        parameters = [[panel.parameterTable.item(row, col).text() for col in range(4)] +
                      [panel.parameterTable.item(row, 4).checkState() == Qt.CheckState.Checked]
                      for row in range(panel.parameterTable.rowCount())]
        self.attempts.start({
                           "track_id": panel.trackChoice.currentData(), "quantity": panel.quantityChoice.currentText(),
                           "interval": [panel.startFrame.value(), panel.endFrame.value()], "smoothed": panel.sourceChoice.currentIndex() == 1,
                           "formula": panel.editor.text(), "initial_fields": parameters,
                           "max_evaluations": panel.budget.value(), "result_formulas": panel.resultFormulas()})
        self.showAttempts()

    def _finishAttempt(self, status, reason, **updates) -> None:
        self.attempts.finish(status, reason, **updates)
        self.showAttempts()

    def showAttempts(self) -> None:
        panel = self.signalPanel
        previous = panel.attemptChoice.currentData()
        with QSignalBlocker(panel.attemptChoice):
            panel.attemptChoice.clear()
            for attempt in reversed(self.attempts.journal.attempts[-20:] if self.attempts.journal else []):
                panel.attemptChoice.addItem(f"{attempt.get('quantity', '?')} · {attempt.get('status', '?')} · {attempt.get('formula', '')[:45]}", attempt.get("id"))
            index = panel.attemptChoice.findData(previous)
            panel.attemptChoice.setCurrentIndex(max(0, index))
        panel.journalLabel.setText(
            (self.attempts.journal.warning or ("Attempts are in memory until the first Save." if self.window.analysisSession.project_root is None else "Attempts are stored in analysis/fit-attempts.json."))
            if self.attempts.journal else "No project attempt log")
        panel.retryJournalButton.setVisible(bool(self.attempts.journal and self.attempts.journal.warning and not self.attempts.journal.read_only))
        self.showAttempt()

    def showAttempt(self, *_args) -> None:
        identity = self.signalPanel.attemptChoice.currentData()
        attempt = next((item for item in self.attempts.journal.attempts if item.get("id") == identity), None) if self.attempts.journal else None
        self.signalPanel.attemptDetails.setPlainText(
            f"Formula: {attempt.get('formula', '?')}\nStatus: {attempt.get('status', '?')} — {attempt.get('reason', 'Calculation in progress')}\n"
            f"Source: {attempt.get('quantity', '?')}, frames {attempt.get('interval', '?')}\n"
            f"Elapsed: {attempt.get('elapsed_s', 0):.3g} s\n"
            + json.dumps({key: value for key, value in attempt.items() if key not in ('formula', 'status', 'reason', 'quantity', 'interval', 'elapsed_s')}, indent=2, ensure_ascii=False)
            if attempt else "No recorded Fit request yet. Live previews are not attempts.")

    def retryJournal(self) -> None:
        if self.attempts.journal:
            self.attempts.journal.retry()
            self.showAttempts()

    def shutdown(self) -> None:
        self.preview.shutdown()
        self._finishAttempt("interrupted", "Window closed; pending result discarded")
        self._closed = True
        self._cancel.set()
        self._future = None
        self._timer.stop()
        self._refresh_timer.stop()
        # worker 不持有 Qt 对象；单次 SciPy 运算不能强行终止，结束后无人接收其结果。
        self._executor.shutdown(wait=False, cancel_futures=True)
