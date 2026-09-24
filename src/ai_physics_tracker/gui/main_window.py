import logging
import math
import queue
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from threading import Event
from typing import Callable
from uuid import UUID

from PySide6.QtCore import QObject, QPoint, QPointF, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QInputDialog,
    QHBoxLayout,
    QLabel,
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QSplitter,
    QStackedWidget,
)

from ai_physics_tracker.application.playback import AsyncVideoSession, DecodeDelivery
from ai_physics_tracker.application.project_session import (
    ProjectRepositoryPort,
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import DecodedFrame, VideoError
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.project_media import ProjectMediaService, PreparedProject, workflow_state
from ai_physics_tracker.application.video_timing import VideoTimingProbe
from ai_physics_tracker.gui.calibration_dialog import CalibrationDialog
from ai_physics_tracker.application.experiment_annotation import (
    annotation_guide_state,
    frame_set_worklist,
)
from ai_physics_tracker.gui.pendulum_setup import (
    PendulumSetupPanel,
    PhysicalParametersDialog,
)
from ai_physics_tracker.gui.video_view import PendulumOverlayView
from ai_physics_tracker.gui.project_actions import ProjectActions
from ai_physics_tracker.gui.timing_actions import TimingActions
from ai_physics_tracker.gui.chart_actions import ChartActions
from ai_physics_tracker.gui.suggested_frame_review_actions import DifficultFrameReviewActions
from ai_physics_tracker.gui.tracking_actions import TrackingActions, FrameSelectionActions
from ai_physics_tracker.gui.workflow_header import (
    WORKSPACE_ACQUIRE,
    WORKSPACE_ANALYSIS,
    WORKSPACE_SETUP,
    WorkflowHeader,
)
from ai_physics_tracker.domain.timeline import Timeline, frame_to_time, clamp_to_working_zone
from ai_physics_tracker.gui.video_view import CalibrationView, MarkerView, VideoView

logger = logging.getLogger(__name__)


class _DecodeDeliveryBridge(QObject):
    """把 decoder worker 的交付转投 GUI 线程：数据走线程安全队列，
    Qt 信号只发无参唤醒。

    不再让 worker 直接 emit 携带 Python 对象的 queued signal：PySide6
    6.11 在 Windows 的特定调度时序下，queued 投递对参数对象的引用管理
    会产生损坏（CI 崩溃 0xc0000374 / c0000005，AV at incref on garbage
    pointer）。队列承载对象，信号只传递"有新交付"这一事实。
    """

    pending = Signal()

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._queue: queue.SimpleQueue = queue.SimpleQueue()

    def enqueue(self, item: object) -> None:
        """worker 线程调用：入队后唤醒 GUI 线程（无参 queued signal）。"""

        self._queue.put(item)
        self.pending.emit()

    def drain(self) -> list[object]:
        """GUI 线程调用：取走当前全部在途交付（FIFO，与解码顺序一致）。"""

        items: list[object] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                return items


class MainWindow(QMainWindow):
    """包裹 Qt-free AsyncVideoSession 的薄 Qt 外壳。

    解码交付经 _DecodeDeliveryBridge 转入 GUI 线程（对象走队列、信号只做
    无参唤醒）；播放节奏用 QTimer 按 `Timeline.fps_nominal` 计算的显示间隔
    推进（间隔只是 UI 节奏，不是时间语义，时间显示始终经 Timeline 换算）。
    """

    frameDelivered = Signal(object, int)
    decodeFailed = Signal(str, int)
    decodeCompleted = Signal(object, int)
    presentedFrameChanged = Signal(object)
    frameRequestFailed = Signal()
    frameRequested = Signal(int)
    analysisChanged = Signal()
    selectedTrackChanged = Signal(object)
    projectChanged = Signal()
    closing = Signal()

    def __init__(
        self,
        session_factory: Callable[[], VideoSession],
        annotation_repository: ProjectRepositoryPort,
        timing_probe: VideoTimingProbe,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Physics Tracker")
        self.resize(960, 720)
        self._annotation_repository = annotation_repository
        self._session_factory = session_factory
        self._timing_probe = timing_probe
        # 解码交付桥：worker 只入队，Qt 信号无参唤醒，对象不过 Qt 元对象系统
        self._delivery_bridge = _DecodeDeliveryBridge(self)
        self._delivery_bridge.pending.connect(self._drainDeliveries)
        self._generation_counter = 0
        self._async = self._makeDecoder(0)
        self._measurement_allowed = False
        self._is_playing = False
        self._has_pending_request = False
        self._marks_since_autosave = 0  # 每 10 个标注点静默自动保存一次（用户实测需求）
        self._latest_request_id: int | None = None
        self._frame_count = 0
        self._timeline: Timeline | None = None
        # 交付代际：openVideo 递增；worker 回调发射时捕获当前代际，
        # GUI 侧丢弃跨代际的迟到交付（旧视频的在途帧不得污染新视频展示）
        self._delivery_generation = 0
        # 连续步进的基准：以最后请求帧号计算，避免解码延迟吞掉快速连点
        self._last_requested_frame: int | None = None
        # 已呈现帧号：标注落帧与 overlay 高亮的唯一事实来源（data-model.md
        # §5.5 标注点打在当前帧；_last_requested_frame 领先于显示，不可用）
        self._presented_frame_index: int | None = None
        # 播放倍速：interval = 1000 / (fps_nominal * rate)（显示节奏，非时间语义）
        self._playback_rate = 1.0
        # 标注会话：openVideo 成功后创建并登记当前视频（2.4 起提供项目 UI）
        self._annotation_session: ProjectSession | None = None
        self._annotation_video_id: UUID | None = None
        self._selected_track_id: UUID | None = None
        self._calibration_return_workspace: str | None = None
        self._calibration_return_track_id: UUID | None = None
        self._calibration_guide_action: str | None = None
        # P1.2 引导标注：experiment_id 非 None 即引导激活；点击落点路由到
        # 当前待标 role 的 track（不依赖 track 选中）
        self._guide_experiment_id: UUID | None = None
        self._guide_skipped_roles: set[str] = set()
        # F1(2026-09-24 HR)：加载后的短暂窗口内 seekFrame 可能被拒
        # （busy/解码器未就绪），入口跳帧会被静默丢弃。记下目标帧，
        # 由定时器有界重试，直到呈现目标帧或超时放弃。
        self._guide_jump_target: int | None = None
        self._guide_jump_attempts = 0
        self._guide_jump_timer = QTimer(self)
        self._guide_jump_timer.setInterval(200)
        self._guide_jump_timer.timeout.connect(self._retryGuideJump)

        self.videoView = VideoView(self)
        self.videoSelector = QComboBox(self)
        self.timingLabel = QLabel("No video selected", self)
        self.timingLabel.setWordWrap(True)
        self.timingButton = QPushButton("Use approximate timing…", self)
        self.timingButton.hide()
        self.previousButton = QPushButton("Previous frame", self)
        self.nextButton = QPushButton("Next frame", self)
        self.playButton = QPushButton("Play", self)
        self.frameSpinBox = QSpinBox(self)
        self.timelineSlider = QSlider(Qt.Orientation.Horizontal, self)
        self.frameLabel = QLabel("Frame: —", self)
        self.timeLabel = QLabel("Time: —", self)
        self.zoomLabel = QLabel("Zoom: —", self)

        self.trackList = QListWidget(self)
        # 多选：overlay 同时显示所有选中轨迹的标注点（各用各自颜色）；
        # 标注落点目标 = 最后点击的项（currentItem，Qt 多选语义）
        self.trackList.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.trackDataLabel = QLabel("Stored observations: 0", self)
        self.addTrackButton = QPushButton("Add track", self)
        self.deleteTrackButton = QPushButton("Delete track", self)
        self.deleteTrackButton.setEnabled(False)
        self.deletePointButton = QPushButton("Delete point", self)
        self.deletePointButton.setEnabled(False)
        self.deletePointButton.setToolTip(
            "Delete manual point on current track at current frame (Undoable before save; non-recoverable after save)"
        )
        self.undoButton = QPushButton("↩ Undo", self)
        self.redoButton = QPushButton("↪ Redo", self)
        self.undoButton.setEnabled(False)
        self.redoButton.setEnabled(False)

        # --- 标定控制面板 (Calibration Group) ---
        self.calibrationGroup = QGroupBox("Calibration", self)
        self.calibrationStatusLabel = QLabel("Status: Uncalibrated", self)
        self.calibrationStatusLabel.setWordWrap(True)
        self.calibrationGuideLabel = QLabel("", self)
        self.calibrationGuideLabel.setWordWrap(True)
        self.calibrationGuideLabel.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.calibrationGuideLabel.setContentsMargins(8, 8, 8, 8)
        self.calibrationGuideLabel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.calibrationGuideLabel.setStyleSheet(
            "background: #eaf3ff; border-radius: 4px;")
        self.calibrationGuideLabel.hide()
        self.calibrationGuideButton = QPushButton("", self)
        self.calibrationGuideButton.hide()
        self.calibrationSelector = QComboBox(self)
        self.drawScaleButton = QPushButton("Draw scale", self)
        self.drawScaleButton.setCheckable(True)
        self.drawScaleButton.setEnabled(False)
        self.setOriginButton = QPushButton("Set origin / axes", self)
        self.setOriginButton.setCheckable(True)
        self.setOriginButton.setEnabled(False)
        self.deleteCalibrationButton = QPushButton("Delete calibration", self)
        self.deleteCalibrationButton.setEnabled(False)
        self.editScaleButton = QPushButton("Edit scale…", self)
        self.editScaleButton.setEnabled(False)
        self.deleteInactiveCalibrationButton = QPushButton("Delete inactive…", self)
        self.deleteInactiveCalibrationButton.setEnabled(False)

        self.originLabel = QLabel("Origin: —", self)
        self.rotationSpinBox = QDoubleSpinBox(self)
        self.rotationSpinBox.setRange(-360.0, 360.0)
        self.rotationSpinBox.setSingleStep(1.0)
        self.rotationSpinBox.setDecimals(1)
        self.rotationSpinBox.setSuffix("°")
        self.rotationSpinBox.setPrefix("Rotation: ")
        self.rotationSpinBox.setEnabled(False)

        calButtons = QHBoxLayout()
        calButtons.addWidget(self.drawScaleButton)
        calButtons.addWidget(self.setOriginButton)
        calEditButtons = QHBoxLayout()
        calEditButtons.addWidget(self.editScaleButton)
        calEditButtons.addWidget(self.deleteInactiveCalibrationButton)

        calLayout = QVBoxLayout()
        calLayout.addWidget(self.calibrationGuideLabel)
        calLayout.addWidget(self.calibrationGuideButton)
        calLayout.addWidget(self.calibrationStatusLabel)
        calLayout.addWidget(self.calibrationSelector)
        calLayout.addLayout(calButtons)
        calLayout.addWidget(self.originLabel)
        calLayout.addWidget(self.rotationSpinBox)
        calLayout.addLayout(calEditButtons)
        calLayout.addWidget(self.deleteCalibrationButton)
        self.calibrationGroup.setLayout(calLayout)

        self.frameSpinBox.setPrefix("Go to: ")
        self.frameSpinBox.setMinimum(0)
        self.timelineSlider.setMinimum(0)
        self.timelineSlider.setTickPosition(QSlider.TickPosition.NoTicks)
        for control in (
            self.frameSpinBox,
            self.previousButton,
            self.nextButton,
            self.playButton,
            self.timelineSlider,
        ):
            control.setEnabled(False)

        self._playTimer = QTimer(self)
        self._playTimer.timeout.connect(self._playTick)

        transportControls = QHBoxLayout()
        transportControls.addWidget(self.playButton)
        transportControls.addWidget(self.previousButton)
        transportControls.addWidget(self.nextButton)
        transportControls.addSpacing(8)
        transportControls.addWidget(self.frameSpinBox)
        transportControls.addStretch(1)
        readoutControls = QHBoxLayout()
        readoutControls.addWidget(self.frameLabel)
        readoutControls.addWidget(self.timeLabel)
        readoutControls.addStretch(1)
        readoutControls.addWidget(self.zoomLabel)
        controls = QVBoxLayout()
        controls.setSpacing(2)
        controls.addLayout(transportControls)
        controls.addLayout(readoutControls)

        trackButtons = QHBoxLayout()
        trackButtons.addWidget(self.addTrackButton)
        trackButtons.addWidget(self.deleteTrackButton)
        trackButtons.addWidget(self.deletePointButton)
        historyButtons = QHBoxLayout()
        historyButtons.addWidget(self.undoButton)
        historyButtons.addWidget(self.redoButton)
        trackPanel = QVBoxLayout()
        trackPanel.addWidget(self.trackDataLabel)
        trackPanel.addWidget(self.trackList, 1)
        trackPanel.addLayout(trackButtons)
        trackPanel.addLayout(historyButtons)
        self.trackGroup = QGroupBox("Tracks", self)
        self.trackGroup.setLayout(trackPanel)

        self.pendulumPanel = PendulumSetupPanel(self)
        sideLayout = QVBoxLayout()
        sideLayout.addWidget(self.calibrationGroup)
        sideLayout.addWidget(self.pendulumPanel)
        sideLayout.addWidget(self.trackGroup, 1)
        trackSide = QWidget(self)
        trackSide.setLayout(sideLayout)
        trackSide.setMaximumWidth(260)
        sideScroll = QScrollArea(self)
        sideScroll.setWidgetResizable(True)
        sideScroll.setWidget(trackSide)
        sideScroll.setMinimumWidth(210)
        sideScroll.setMaximumWidth(280)
        sideScroll.setFrameShape(QScrollArea.Shape.NoFrame)

        videoColumn = QVBoxLayout()
        videoColumn.addWidget(self.videoSelector)
        videoColumn.addWidget(self.timingLabel)
        videoColumn.addWidget(self.timingButton)
        videoColumn.addWidget(self.videoView, 1)
        videoColumn.addWidget(self.timelineSlider)
        videoColumn.addLayout(controls)
        videoColumnWidget = QWidget(self)
        videoColumnWidget.setLayout(videoColumn)

        mainRow = QHBoxLayout()
        mainRow.addWidget(videoColumnWidget, 1)
        mainRow.addWidget(sideScroll)
        self._videoPage = QWidget(self)
        self._videoPage.setLayout(mainRow)

        # Phase 5.7：三工作区。视频页承载 实验设置/获取轨迹；分析页以图表为主体、
        # 视频作为参照窗（videoView 在进入/离开分析页时重挂父，解码管线不受影响）。
        self._workspace = WORKSPACE_ACQUIRE
        self._videoColumn = videoColumn
        self._videoColumnWidget = videoColumnWidget
        self._videoViewHomeIndex: int | None = None
        self._analysisReferenceHost = QWidget(self)
        reference_layout = QVBoxLayout(self._analysisReferenceHost)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        self._analysisReferenceCaption = QLabel("Video reference", self)
        self._analysisReferenceCaption.setWordWrap(True)
        reference_layout.addWidget(self._analysisReferenceCaption)
        self._analysisSplitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._analysisChartHost = QWidget(self)  # ChartPanel 挂入点（见 _installChartPanel）
        self._analysisChartHost.setLayout(QVBoxLayout())
        self._analysisSplitter.addWidget(self._analysisChartHost)
        self._analysisSplitter.addWidget(self._analysisReferenceHost)
        self._analysisSplitter.setStretchFactor(0, 3)
        self._analysisSplitter.setStretchFactor(1, 1)
        # 来源条（设计 §8.2/§11.2）：图表始终显示当前输入来自哪里
        self._analysisSourceLabel = QLabel("No analysis source selected", self)
        self._analysisSourceLabel.setWordWrap(True)
        analysis_layout = QVBoxLayout()
        analysis_layout.setContentsMargins(6, 4, 6, 0)
        analysis_layout.addWidget(self._analysisSourceLabel)
        analysis_layout.addWidget(self._analysisSplitter, 1)
        self._analysisPage = QWidget(self)
        self._analysisPage.setLayout(analysis_layout)

        self.workflowHeader = WorkflowHeader(self)
        self.workflowHeader.workspaceRequested.connect(self.setWorkspace)
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.workflowHeader)
        self._workspaceStack = QStackedWidget(self)
        self._workspaceStack.addWidget(self._videoPage)
        self._workspaceStack.addWidget(self._analysisPage)
        outer.addWidget(self._workspaceStack)
        central = QWidget(self)
        central.setLayout(outer)
        self.setCentralWidget(central)

        self.projectActions = ProjectActions(self)
        self.timingActions = TimingActions(self)
        self.videoSelector.currentIndexChanged.connect(self.projectActions.selectVideo)

        zoomInAction = QAction("Zoom in", self)
        zoomInAction.setShortcut(QKeySequence("Ctrl++"))
        zoomInAction.triggered.connect(self.videoView.zoomIn)
        zoomOutAction = QAction("Zoom out", self)
        zoomOutAction.setShortcut(QKeySequence("Ctrl+-"))
        zoomOutAction.triggered.connect(self.videoView.zoomOut)
        zoomFitAction = QAction("Fit to window", self)
        zoomFitAction.setShortcut(QKeySequence("Ctrl+0"))
        zoomFitAction.triggered.connect(self.videoView.zoomFit)
        zoomOriginalAction = QAction("Original size (100%)", self)
        zoomOriginalAction.setShortcut(QKeySequence("Ctrl+1"))
        zoomOriginalAction.triggered.connect(self.videoView.zoomOriginal)
        zoom200Action = QAction("Zoom to 200%", self)
        zoom200Action.setShortcut(QKeySequence("Ctrl+2"))
        zoom200Action.triggered.connect(lambda: self.videoView.zoomTo(2.0))
        zoom400Action = QAction("Zoom to 400%", self)
        zoom400Action.setShortcut(QKeySequence("Ctrl+3"))
        zoom400Action.triggered.connect(lambda: self.videoView.zoomTo(4.0))
        viewMenu = self.menuBar().addMenu("View")
        self.chartActions = ChartActions(self)
        self.trackingActions = TrackingActions(self)
        self.frameSelectionActions = FrameSelectionActions(
            self, self.trackingActions.panel
        )
        self.reviewActions = DifficultFrameReviewActions(
            self, self.trackingActions.panel
        )
        self._installChartPanel(self.chartActions.panel)
        viewMenu.addAction(self.trackingActions.panel.toggleViewAction())
        self.setWorkspace(WORKSPACE_ACQUIRE)
        viewMenu.addAction(zoomInAction)
        viewMenu.addAction(zoomOutAction)
        viewMenu.addSeparator()
        viewMenu.addAction(zoomFitAction)
        viewMenu.addAction(zoomOriginalAction)
        viewMenu.addAction(zoom200Action)
        viewMenu.addAction(zoom400Action)

        self._speedActions: dict[float, QAction] = {}
        speedGroup = QActionGroup(self)
        for rate, label in (
            (0.25, "0.25×"),
            (0.5, "0.5×"),
            (1.0, "1× (original)"),
            (2.0, "2×"),
            (4.0, "4×"),
        ):
            speedAction = QAction(label, self)
            speedAction.setCheckable(True)
            speedAction.setChecked(rate == 1.0)
            speedAction.setActionGroup(speedGroup)
            speedAction.triggered.connect(lambda _=False, r=rate: self.setPlaybackRate(r))
            self._speedActions[rate] = speedAction
        playbackMenu = self.menuBar().addMenu("Playback")
        for rate in (0.25, 0.5, 1.0, 2.0, 4.0):
            playbackMenu.addAction(self._speedActions[rate])

        playShortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        playShortcut.activated.connect(self.togglePlayback)

        self.playButton.clicked.connect(self.togglePlayback)
        self.previousButton.clicked.connect(lambda: self._step(-1))
        self.nextButton.clicked.connect(lambda: self._step(1))
        self.frameSpinBox.valueChanged.connect(self._goToFrame)
        self.timelineSlider.sliderPressed.connect(self._scrubStarted)
        self.timelineSlider.sliderMoved.connect(self._scrubPreview)
        self.timelineSlider.sliderReleased.connect(self._scrubCommitted)
        self.frameDelivered.connect(self._onFrameDelivered)
        self.decodeFailed.connect(self._onDecodeFailed)
        self.decodeCompleted.connect(self._onDecodeCompleted)
        self.videoView.scaleChanged.connect(self._onScaleChanged)
        self.videoView.annotationClicked.connect(self._onAnnotationClicked)
        self.videoView.scaleLineDrawn.connect(self._onScaleLineDrawn)
        self.videoView.originClicked.connect(self._onOriginClicked)
        self.videoView.pivotClicked.connect(self._onPivotClicked)
        self.videoView.verticalLineDrawn.connect(self._onVerticalLineDrawn)
        self.pendulumPanel.pivotButton.clicked.connect(self.beginPivotPick)
        self.pendulumPanel.verticalButton.clicked.connect(self.beginVerticalPick)
        self.pendulumPanel.confirmVerticalButton.clicked.connect(
            self._confirmVerticalDirection)
        self.pendulumPanel.physicalButton.clicked.connect(self.openPhysicalDialog)
        self.pendulumPanel.releaseButton.clicked.connect(self._setReleaseToCurrentFrame)
        self.pendulumPanel.annotateButton.clicked.connect(self.beginExperimentAnnotation)
        self.drawScaleButton.clicked.connect(self._toggleDrawScaleMode)
        self.setOriginButton.clicked.connect(self._toggleSetOriginMode)
        self.calibrationGuideButton.clicked.connect(self._onCalibrationGuideAction)
        self.deleteCalibrationButton.clicked.connect(self._deleteActiveCalibration)
        self.editScaleButton.clicked.connect(self._editActiveScale)
        self.deleteInactiveCalibrationButton.clicked.connect(self._deleteInactiveCalibration)
        self.calibrationSelector.currentIndexChanged.connect(self._onCalibrationSelected)
        self.rotationSpinBox.valueChanged.connect(self._onRotationChanged)
        self.addTrackButton.clicked.connect(self._addTrack)
        self.deleteTrackButton.clicked.connect(self._deleteSelectedTrack)
        self.deletePointButton.clicked.connect(self._deleteCurrentManualPoint)
        self.trackList.itemSelectionChanged.connect(self._onTrackSelectionChanged)
        self.trackList.itemClicked.connect(lambda _item: self._onTrackSelectionChanged())
        annotationEscape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        annotationEscape.activated.connect(self._exitAnnotationMode)
        undoShortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undoShortcut.activated.connect(self._undo)
        redoShortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        redoShortcut.activated.connect(self._redo)
        self.undoButton.clicked.connect(self._undo)
        self.redoButton.clicked.connect(self._redo)

        deletePointShortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        deletePointShortcut.activated.connect(self._onDeletePointShortcut)
        backspacePointShortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self)
        backspacePointShortcut.activated.connect(self._onDeletePointShortcut)

        reviewAcceptShortcut = QShortcut(QKeySequence(Qt.Key.Key_A), self)
        reviewAcceptShortcut.activated.connect(self._onReviewAcceptShortcut)
        reviewSkipShortcut = QShortcut(QKeySequence(Qt.Key.Key_S), self)
        reviewSkipShortcut.activated.connect(self._onReviewSkipShortcut)
        reviewCorrectShortcut = QShortcut(QKeySequence(Qt.Key.Key_C), self)
        reviewCorrectShortcut.activated.connect(self._onReviewCorrectShortcut)

        self.statusBar().showMessage("Ready")

    @property
    def analysisSession(self) -> ProjectSession | None:
        return self._annotation_session

    @property
    def activeVideoId(self) -> UUID | None:
        return self._annotation_video_id

    @property
    def selectedTrackId(self) -> UUID | None:
        return self._selected_track_id

    @property
    def presentedFrameIndex(self) -> int | None:
        return self._presented_frame_index

    @property
    def presented_frame_index(self) -> int | None:
        return self._presented_frame_index

    @property
    def deliveryGeneration(self) -> int:
        return self._delivery_generation

    def seekFrame(self, frame_index: int) -> bool:
        """图表导航统一走现有解码入口，暂停并解除视频上的编辑模式。"""

        if self.projectActions.busy or self._timeline is None or self._async.snapshot() is None:
            return False
        self.stopPlayback()
        if hasattr(self, "reviewActions") and self.reviewActions.is_correcting:
            self.reviewActions.cancelCorrectMode()
        if self._guide_experiment_id is None:
            self.videoView.set_annotation_mode(False)
        if self.videoView.is_calibration_mode() in ("pivot", "vertical"):
            self._hidePendulumGuide()
        self.videoView.set_calibration_mode(None)
        self.drawScaleButton.setChecked(False)
        self.setOriginButton.setChecked(False)
        self._requestFrame(clamp_to_working_zone(frame_index, self._timeline))
        return True

    def jumpToFrame(self, frame_index: int) -> bool:
        """建议帧跳帧（Phase 5.1）：跳转到指定帧，并在有选中 Track 时保持标注模式。"""
        if not self.seekFrame(frame_index):
            return False
        if self._selected_track_id is not None and self._measurement_allowed and not self.projectActions.busy:
            self.videoView.set_annotation_mode(True)
            self.statusBar().showMessage(
                f"Jumped to frame {frame_index}. Click video to annotate target for selected track."
            )
        return True

    def refreshAnalysisHistory(self) -> None:
        self._refreshHistoryButtons()

    @property
    def isPlaying(self) -> bool:
        return self._is_playing

    @property
    def playbackRate(self) -> float:
        return self._playback_rate

    # ------------------------------------------------------------------
    # Phase 5.7 — 三个工作区（导航只改变视图，不执行任务）
    # ------------------------------------------------------------------

    @property
    def currentWorkspace(self) -> str:
        return self._workspace

    def setWorkspace(self, workspace: str) -> None:
        """切换工作区；不取消任务、不改变采用结果、不触发计算。"""
        if workspace == self._workspace and self._workspaceStack.currentIndex() == (
                1 if workspace == WORKSPACE_ANALYSIS else 0):
            self.workflowHeader.setWorkspace(workspace)
            return
        if workspace == WORKSPACE_ANALYSIS:
            self._enterAnalysis()
            self.refreshAnalysisSourceBar()
        else:
            if self._workspace == WORKSPACE_ANALYSIS:
                self._leaveAnalysis()
        self._workspace = workspace
        if workspace == WORKSPACE_ANALYSIS:
            self._workspaceStack.setCurrentWidget(self._analysisPage)
        else:
            self._workspaceStack.setCurrentWidget(self._videoPage)
        tracking_panel = getattr(self, "trackingActions", None)
        if tracking_panel is not None:
            panel = tracking_panel.panel
            if workspace == WORKSPACE_ACQUIRE:
                panel.show()
                panel.raise_()
            else:
                # 分析页以图表为主体；AI 状态经状态头任务条常驻（设计 §8.2）
                panel.hide()
        self.workflowHeader.setWorkspace(workspace)
        self.analysisChanged.emit()
        if workspace == WORKSPACE_ANALYSIS:
            self.refreshAnalysisSourceBar()

    def refreshAnalysisSourceBar(self) -> None:
        """分析页顶部：当前输入来源 + 标定 + 时间依据（§11.2）。"""
        session = self.analysisSession
        track_id = self.selectedTrackId
        if session is None or track_id is None:
            self._analysisSourceLabel.setText("No analysis source selected")
            return
        state = getattr(self.trackingActions, "_current_workflow_state", None)
        traj = state.trajectory if state is not None else None
        manual_count = traj.manual_count if traj is not None else len(
            session.manual_points(track_id))
        if traj is not None and traj.active_label:
            source = (f"Using {traj.active_label} AI result + {manual_count} "
                      "manual position(s)")
        else:
            source = f"Using manual positions only ({manual_count})"
        track = next((t for t in session.tracks if t.track_id == track_id), None)
        if track is not None:
            calibration = self.activeCalibrationFor(track.video_id) \
                if hasattr(self, "activeCalibrationFor") else None
            if calibration is None:
                calibration = session.active_calibration(track.video_id)
            unit = calibration.unit if calibration is not None else "px (no calibration)"
            timing = session.measurement_timing_detail(track.video_id)
            timing_note = "approximate timing" if timing else "verified CFR timing"
            source += f" · Units: {unit} · Timing: {timing_note}"
        self._analysisSourceLabel.setText(source)

    def _enterAnalysis(self) -> None:
        """视频视图重挂为分析页参照窗；解码与 overlay 管线不变。"""
        if self.videoView.parent() is self._analysisReferenceHost:
            return
        layout = self._videoColumn
        self._videoViewHomeIndex = layout.indexOf(self.videoView)
        self._analysisReferenceHost.layout().addWidget(self.videoView)

    def _leaveAnalysis(self) -> None:
        """视频视图回到获取轨迹/实验设置页原位置。"""
        if self.videoView.parent() is self._analysisReferenceHost:
            index = self._videoViewHomeIndex
            if index is None or index > self._videoColumn.count():
                index = self._videoColumn.count()
            self._videoColumn.insertWidget(index, self.videoView)

    def _installChartPanel(self, panel: QWidget) -> None:
        """ChartPanel 由 dock 转为分析页主体（Phase 5.7）。"""
        host_layout = self._analysisChartHost.layout()
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.addWidget(panel)

    def setPlaybackRate(self, rate: float) -> None:
        """设置播放倍速并即时生效；非正值忽略。"""

        if rate <= 0:
            return
        self._playback_rate = rate
        if self._is_playing:
            self._restartPlayTimer()

    def _restartPlayTimer(self) -> None:
        snapshot = self._async.snapshot()
        if snapshot is None:
            return
        fps = snapshot.timeline.fps_nominal
        interval_ms = max(1, round(1000.0 / (fps * self._playback_rate)))
        self._playTimer.start(interval_ms)

    def _makeDecoder(self, token: int) -> AsyncVideoSession:
        # token 在创建时固定；旧 worker 发射迟到帧时不能冒充当前会话。
        # 回调在 worker 线程执行，只入队（见 _DecodeDeliveryBridge）。
        bridge = self._delivery_bridge
        return AsyncVideoSession(self._session_factory(),
            lambda frame: bridge.enqueue(("frame", frame, token)),
            lambda error: bridge.enqueue(("failed", str(error), token)),
            on_result=lambda result: bridge.enqueue(("completed", result, token)))

    def _drainDeliveries(self) -> None:
        """GUI 线程分发在途解码交付（FIFO 顺序与单 worker 解码顺序一致）。"""

        for kind, payload, token in self._delivery_bridge.drain():
            if kind == "completed":
                self.decodeCompleted.emit(payload, token)
            elif kind == "frame":
                self.frameDelivered.emit(payload, token)
            else:
                self.decodeFailed.emit(payload, token)

    def candidateService(self, *, deferTiming: bool = False) -> tuple[int, ProjectMediaService]:
        self._generation_counter += 1
        token = self._generation_counter
        service = ProjectMediaService(self._annotation_repository,
                                     lambda: self._makeDecoder(token), self._timing_probe,
                                     defer_timing=deferTiming)
        return token, service

    def openVideo(self, path: Path, *, show_error: bool = True) -> bool:
        """同步的候选准备接口（测试/脚本）；用户菜单另经 dirty 保护与后台执行。"""

        token, service = self.candidateService()
        try:
            prepared = service.open_video(path, Event())
        except Exception as error:
            self.statusBar().showMessage(str(error))
            if show_error:
                QMessageBox.critical(self, "Unable to open video", str(error))
            return False
        self.adoptPrepared(prepared, token)
        return True

    def adoptPrepared(self, prepared: PreparedProject, token: int,
                      service: ProjectMediaService | None = None) -> None:
        """首帧/身份准备成功后提交预览；时序可后台继续，旧解码器异步释放。"""

        self.stopPlayback()
        old_decoder = self._async
        self._delivery_generation = token
        self._async = prepared.decoder or self._makeDecoder(token)
        self.projectActions.executor.submit(old_decoder.close)
        self._has_pending_request = False
        self._last_requested_frame = None
        self._latest_request_id = None
        self._resetPresentation()
        self._annotation_session = prepared.session
        self._annotation_video_id = prepared.video_id
        self._measurement_allowed = prepared.timing.status == "cfr" and prepared.video_id is not None
        self.syncVideoSelector()
        self._refreshTrackList()
        if prepared.snapshot is not None:
            snapshot = prepared.snapshot
            self._frame_count = snapshot.info.frame_count
            self._timeline = snapshot.timeline
            low, high = self._timeline.working_zone
            with QSignalBlocker(self.frameSpinBox), QSignalBlocker(self.timelineSlider):
                self.frameSpinBox.setRange(low, high)
                self.timelineSlider.setRange(low, high)
            for control in (self.frameSpinBox, self.timelineSlider, self.previousButton,
                            self.nextButton, self.playButton):
                control.setEnabled(True)
            self._presentFrame(snapshot.current_frame)
            state = workflow_state(prepared.session)
            self.videoView.restoreViewState(state.get("view", {}))
            saved_track = state.get("selected_track_id")
            with QSignalBlocker(self.trackList):
                for row in range(self.trackList.count()):
                    track_id = self.trackList.item(row).data(Qt.ItemDataRole.UserRole)
                    if str(track_id) == saved_track:
                        self.trackList.setCurrentRow(row)
                        self._selected_track_id = track_id
            self._refreshMarkers()
        else:
            self.videoView.setPlaceholder(prepared.timing.reason)
        self.videoView.set_annotation_mode(False)
        self.addTrackButton.setEnabled(self._measurement_allowed)
        self._refreshHistoryButtons()
        self._refreshCalibrationUI()
        self.projectActions.refresh()
        self.statusBar().showMessage(prepared.timing.reason +
            ("" if self._measurement_allowed else " — browsing only; new measurements disabled"))
        self.timingActions.adopt(prepared, token, service)
        self.projectChanged.emit()

    def adoptEmptyProject(self) -> None:
        from ai_physics_tracker.application.video_timing import TimingReport
        self._generation_counter += 1
        self.adoptPrepared(PreparedProject(ProjectSession.start(self._annotation_repository),
            None, None, None, TimingReport("unknown", "New project")), self._generation_counter)

    def syncVideoSelector(self) -> None:
        with QSignalBlocker(self.videoSelector):
            self.videoSelector.clear()
            if self._annotation_session is not None:
                for video in self._annotation_session.project.videos:
                    self.videoSelector.addItem(video.display_name, video.video_id)
                index = self.videoSelector.findData(self._annotation_video_id)
                self.videoSelector.setCurrentIndex(index)

    def captureProjectView(self) -> dict:
        state = dict(workflow_state(self._annotation_session)) if self._annotation_session else {}
        state.update({"version": 1, "video_id": str(self._annotation_video_id) if self._annotation_video_id else None})
        if self._presented_frame_index is not None:
            state.update({"frame_index": self._presented_frame_index,
                "selected_track_id": str(self._selected_track_id) if self._selected_track_id else None,
                "view": self.videoView.captureViewState()})
        return state

    def togglePlayback(self) -> None:
        if self._is_playing:
            self.stopPlayback()
            return
        self.startPlayback()

    def startPlayback(self) -> None:
        if hasattr(self, "reviewActions") and self.reviewActions.is_correcting:
            self.reviewActions.cancelCorrectMode()
        snapshot = self._async.snapshot()
        if snapshot is None:
            return
        if snapshot.current_frame.frame_index >= self._timeline.working_zone[1]:
            # 播放到末尾后再次播放：从头开始，避免静止在末帧
            self._requestFrame(self._timeline.working_zone[0])
        self._is_playing = True
        self.playButton.setText("Pause")
        self._restartPlayTimer()
        self._playTick()

    def stopPlayback(self) -> None:
        self._playTimer.stop()
        if self._is_playing:
            self._is_playing = False
        self.playButton.setText("Play")

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.projectActions.requestWindowClose():
            event.ignore()
            return
        self._generation_counter += 1
        self._delivery_generation = self._generation_counter
        self.stopPlayback()
        self.closing.emit()
        self.timingActions.shutdown()
        self._async.close()
        self.projectActions.shutdown()
        super().closeEvent(event)

    def _playTick(self) -> None:
        # 解码慢于帧率时节流：等上一请求交付后再发下一个（不堆积请求）；
        # 也覆盖"从末帧重播"场景——回跳第 0 帧的请求在途时快照仍是末帧。
        if self._has_pending_request:
            return
        snapshot = self._async.snapshot()
        if snapshot is None:
            self.stopPlayback()
            return
        if snapshot.current_frame.frame_index >= self._timeline.working_zone[1]:
            self.stopPlayback()
            return
        self._requestFrame(snapshot.current_frame.frame_index + 1)

    def _requestFrame(self, frame_index: int) -> None:
        self._has_pending_request = True
        self._last_requested_frame = frame_index
        self._latest_request_id = self._async.request_frame(frame_index)
        self.frameRequested.emit(frame_index)

    def _onDecodeCompleted(self, result: DecodeDelivery, generation: int) -> None:
        if generation != self._delivery_generation or result.request_id != self._latest_request_id:
            return  # 旧请求即便失败也不能清除新请求；相同帧号靠编号区分。
        if result.error is not None:
            self.decodeFailed.emit(str(result.error), generation)
        elif result.frame is not None:
            self.frameDelivered.emit(result.frame, generation)

    def _onFrameDelivered(self, frame: DecodedFrame, generation: int) -> None:
        if generation != self._delivery_generation:
            return
        self._has_pending_request = False
        self._last_requested_frame = frame.frame_index
        self._presentFrame(frame)
        if self._is_playing and frame.frame_index >= self._timeline.working_zone[1]:
            self.stopPlayback()

    def _onDecodeFailed(self, message: str, generation: int) -> None:
        if generation != self._delivery_generation:
            return
        self._has_pending_request = False
        self.stopPlayback()
        self.statusBar().showMessage(message)
        snapshot = self._async.snapshot()
        if snapshot is not None:
            self._last_requested_frame = snapshot.current_frame.frame_index
            self._presentFrame(snapshot.current_frame)
        self.frameRequestFailed.emit()

    def _undo(self) -> None:
        # P6R-01：会话层原子拒绝（如撤销越过已登记 AI 任务的建 Track 操作）时，
        # 给出可见反馈而不是让异常穿透 GUI 事件循环；状态已保证完全不变。
        if self._annotation_session is None:
            return
        try:
            stepped = self._annotation_session.undo()
        except ProjectSessionError as error:
            self.statusBar().showMessage(f"Undo unavailable: {error}")
            return
        if not stepped:
            return
        self._afterHistoryStep()

    def _redo(self) -> None:
        if self._annotation_session is None:
            return
        try:
            stepped = self._annotation_session.redo()
        except ProjectSessionError as error:
            self.statusBar().showMessage(f"Redo unavailable: {error}")
            return
        if not stepped:
            return
        self._afterHistoryStep()

    def _afterHistoryStep(self) -> None:
        """撤销/重做后的状态收敛：选择有效性、面板与 overlay 同步。"""

        assert self._annotation_session is not None
        track_ids = {track.track_id for track in self._annotation_session.tracks}
        if self._selected_track_id is not None and (
            self._selected_track_id not in track_ids
        ):
            self.trackList.setCurrentRow(-1)  # 触发 _onTrackSelectionChanged
        if self._guide_experiment_id is not None:
            self._refreshAnnotationGuide()
        self._refreshTrackList()
        # 选择失效或为空时自动选中第一行：撤销"删除 track"后恢复标注上下文
        if self.trackList.currentRow() == -1 and self.trackList.count() > 0:
            self.trackList.setCurrentRow(0)
        self._refreshCalibrationUI()
        self._refreshHistoryButtons()
        self._refreshMarkers()
        self.statusBar().showMessage("")

    def _refreshHistoryButtons(self) -> None:
        session = self._annotation_session
        self.undoButton.setEnabled(session is not None and session.can_undo)
        self.redoButton.setEnabled(session is not None and session.can_redo)
        self._refreshDeletePointButton()
        if hasattr(self, "projectActions"):
            self.projectActions.refresh()
        self.analysisChanged.emit()

    def _refreshDeletePointButton(self) -> None:
        has_manual = False
        session = self._annotation_session
        track_id = self._selected_track_id
        frame_index = self._presented_frame_index
        if session is not None and track_id is not None and frame_index is not None:
            pt = session.effective_point(track_id, frame_index)
            if pt is not None and pt.source == "manual":
                has_manual = True
        enabled = has_manual and self._measurement_allowed and not self.projectActions.busy
        if hasattr(self, "deletePointButton"):
            self.deletePointButton.setEnabled(enabled)
        if hasattr(self, "trackingActions") and hasattr(self.trackingActions.panel, "deleteManualPointButton"):
            self.trackingActions.panel.deleteManualPointButton.setEnabled(enabled)

    def _deleteCurrentManualPoint(self) -> None:
        if not self._measurement_allowed or self.projectActions.busy:
            return
        if self._has_pending_request:
            self.statusBar().showMessage("Waiting for frame; delete ignored")
            return
        session = self._annotation_session
        track_id = self._selected_track_id
        frame_index = self._presented_frame_index
        if session is None or track_id is None or frame_index is None:
            return
        pt = session.effective_point(track_id, frame_index)
        if pt is None or pt.source != "manual":
            return
        session.delete_active_manual_point(track_id, frame_index)
        self._refreshMarkers()
        self._refreshHistoryButtons()
        self._refreshDeletePointButton()
        if hasattr(self, "reviewActions"):
            self.reviewActions.refresh()
        self.statusBar().showMessage(
            f"Deleted manual point at frame {frame_index} (Undoable before save; non-recoverable after save)"
        )

    def _onDeletePointShortcut(self) -> None:
        if self._isTypingInInputWidget():
            return
        self._deleteCurrentManualPoint()

    def _isTypingInInputWidget(self) -> bool:
        from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit, QTextEdit, QPlainTextEdit
        focus = self.focusWidget()
        return isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox))

    def _onReviewAcceptShortcut(self) -> None:
        if self._isTypingInInputWidget():
            return
        if hasattr(self, "reviewActions") and self.reviewActions.controller is not None:
            if self.reviewActions.controller.current_candidate is not None:
                self.reviewActions.acceptCurrent()

    def _onReviewSkipShortcut(self) -> None:
        if self._isTypingInInputWidget():
            return
        if hasattr(self, "reviewActions") and self.reviewActions.controller is not None:
            if self.reviewActions.controller.current_candidate is not None:
                self.reviewActions.skipCurrent()

    def _onReviewCorrectShortcut(self) -> None:
        if self._isTypingInInputWidget():
            return
        if hasattr(self, "reviewActions") and self.reviewActions.controller is not None:
            if self.reviewActions.controller.current_candidate is not None:
                self.reviewActions.startCorrectCurrent()

    def _addTrack(self) -> None:
        if not self._measurement_allowed or self.projectActions.busy or self._annotation_session is None or self._annotation_video_id is None:
            return
        track = self._annotation_session.add_track(self._annotation_video_id)
        self._refreshTrackList()
        # 新 Track 成为唯一选中并立即成为标注目标；既有选中保留会让
        # "建完就标"的新点落到旧 Track 上（多选模式下 setCurrentRow 不清选区）
        self.trackList.clearSelection()
        for row in range(self.trackList.count()):
            if self.trackList.item(row).data(Qt.ItemDataRole.UserRole) == track.track_id:
                self.trackList.setCurrentRow(row)
                self.trackList.item(row).setSelected(True)
                break
        self._refreshHistoryButtons()

    def _deleteSelectedTrack(self) -> None:
        tracking = getattr(self, "trackingActions", None)
        if tracking and tracking.pending and tracking.activeTrackId == self._selected_track_id:
            self.statusBar().showMessage("Cancel the AI task before deleting its track")
            return
        if self._annotation_session is None or self._selected_track_id is None:
            return
        try:
            self._annotation_session.remove_track(self._selected_track_id)
        except (ProjectSessionError, ValueError) as error:
            # 域级联已随删除清理 runs；此处兜底保证按钮失败时用户可见原因
            logger.error("delete track failed", exc_info=True)
            self.statusBar().showMessage(f"Delete track failed: {error}")
            return
        self._selected_track_id = None
        self.trackList.setCurrentRow(-1)
        self.trackList.clearSelection()
        self._refreshTrackList()
        self._refreshMarkers()
        self._refreshHistoryButtons()

    def _onTrackSelectionChanged(self) -> None:
        # 多选语义：标注目标 = 选中集中的 currentItem（最后点击项）；currentItem
        # 已被 toggle 取消选中时回落到任一剩余选中项；选中为空必须得到 None
        # （clearSelection 后 Qt 仍保留 currentItem，不能让它复活旧目标）
        selected = self.trackList.selectedItems()
        current = self.trackList.currentItem()
        if current is not None and current in selected:
            track_id = current.data(Qt.ItemDataRole.UserRole)
        elif selected:
            track_id = selected[0].data(Qt.ItemDataRole.UserRole)
        else:
            track_id = None
        self._selected_track_id = track_id
        self.selectedTrackChanged.emit(track_id)
        self.deleteTrackButton.setEnabled(track_id is not None)
        if track_id is not None:
            self.drawScaleButton.setChecked(False)
            self.setOriginButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
            self.videoView.set_annotation_mode(self._measurement_allowed and not self.projectActions.busy)
            self.statusBar().showMessage(
                "Annotation mode: click the video to mark; Esc or click an empty "
                "list area to exit"
            )
        else:
            self.videoView.set_annotation_mode(False)
            if (
                self._annotation_session is not None
                and not self.drawScaleButton.isChecked()
                and not self.setOriginButton.isChecked()
            ):
                self.statusBar().showMessage("Browse mode")
        self._refreshMarkers()
        self._refreshDeletePointButton()

    def _exitAnnotationMode(self) -> None:
        if hasattr(self, "reviewActions") and self.reviewActions.is_correcting:
            self.reviewActions.cancelCorrectMode()
            self.statusBar().showMessage("Correct mode cancelled")
            return
        if self._selected_track_id is not None:
            self.trackList.setCurrentRow(-1)
            self.trackList.clearSelection()
            self._selected_track_id = None
        if self.drawScaleButton.isChecked():
            self.drawScaleButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
        if self.setOriginButton.isChecked():
            self.setOriginButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
        if self.videoView.is_calibration_mode() in ("pivot", "vertical"):
            self.videoView.set_calibration_mode(None)
            self._hidePendulumGuide()
        if self._guide_experiment_id is not None:
            self._guide_experiment_id = None
            self._guide_jump_target = None
            self._guide_jump_timer.stop()
            self._guide_skipped_roles.clear()
            self._hidePendulumGuide()
            self._refreshMarkers()
        self.statusBar().showMessage("Browse mode")

    def _setCalibrationGuide(
        self, message: str, action: str | None = None,
        action_label: str = "",
    ) -> None:
        self.calibrationGuideLabel.setText(message)
        self.calibrationGuideLabel.show()
        self.calibrationGuideLabel.updateGeometry()
        QTimer.singleShot(0, self._fitCalibrationGuideHeight)
        self._calibration_guide_action = action
        self.calibrationGuideButton.setText(action_label)
        self.calibrationGuideButton.setVisible(action is not None)

    def _fitCalibrationGuideHeight(self) -> None:
        """让换行提示按当前侧栏宽度占足高度，避免高 DPI 下裁字。"""
        label = self.calibrationGuideLabel
        if not label.isVisible():
            return
        label.setMinimumHeight(0)
        required = label.heightForWidth(max(1, label.width()))
        if required > 0:
            label.setMinimumHeight(required)

    def beginCalibrationFlow(self, return_workspace: str = WORKSPACE_ACQUIRE) -> None:
        """启动连续标定引导，并记住完成后要恢复的工作位置。"""
        if not self._measurement_allowed or self.projectActions.busy:
            return
        self._calibration_return_workspace = return_workspace
        self._calibration_return_track_id = self._selected_track_id
        self.setWorkspace(WORKSPACE_SETUP)
        self._setCalibrationGuide(
            "Calibration — step 1 of 2: draw along an object whose real length "
            "you know, then enter that length.")
        if self.drawScaleButton.isEnabled() and not self.drawScaleButton.isChecked():
            self.drawScaleButton.click()

    def _beginOriginStep(self) -> None:
        if self._annotation_session is None or self._annotation_video_id is None:
            return
        self._setCalibrationGuide(
            "Calibration — step 2 of 2: click the coordinate origin. The red +X "
            "axis points right and the green +Y axis points up; adjust Rotation "
            "afterward if your experiment uses different axes.")
        if self.setOriginButton.isEnabled() and not self.setOriginButton.isChecked():
            self.setOriginButton.click()

    def _showCalibrationComplete(self) -> None:
        self._setCalibrationGuide(
            "Calibration complete: scale and coordinate origin are set. Check the "
            "axis overlay, adjust Rotation if needed, then return to marking frames.",
            "return",
            "Return to Acquire trajectory",
        )
        self.statusBar().showMessage(
            "Calibration complete — return to Acquire trajectory to continue marking")

    def _onCalibrationGuideAction(self) -> None:
        if self._calibration_guide_action in (
            "guide_skip", "guide_next", "guide_finish"
        ):
            self._onAnnotationGuideAction(self._calibration_guide_action)
            return
        if self._calibration_guide_action == "retry_scale":
            if self.drawScaleButton.isEnabled() and not self.drawScaleButton.isChecked():
                self.drawScaleButton.click()
            return
        if self._calibration_guide_action == "retry_origin":
            if self._calibration_return_workspace is None:
                self._calibration_return_workspace = self.currentWorkspace
                self._calibration_return_track_id = self._selected_track_id
                self.setWorkspace(WORKSPACE_SETUP)
            self._beginOriginStep()
            return
        if self._calibration_guide_action != "return":
            return
        workspace = self._calibration_return_workspace or WORKSPACE_ACQUIRE
        track_id = self._calibration_return_track_id
        self._calibration_return_workspace = None
        self._calibration_return_track_id = None
        self._calibration_guide_action = None
        self.calibrationGuideLabel.hide()
        self.calibrationGuideButton.hide()
        self.setWorkspace(workspace)
        if track_id is not None:
            for row in range(self.trackList.count()):
                item = self.trackList.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == track_id:
                    self.trackList.clearSelection()
                    item.setSelected(True)
                    self.trackList.setCurrentItem(item)
                    self._onTrackSelectionChanged()
                    break
        self.statusBar().showMessage(
            "Calibration complete — continue marking representative frames")

    # ------------------------------------------------------------------
    # Pendulum experiment setup（P1.1；契约 §2 的 setup 事实录入）
    # ------------------------------------------------------------------

    def currentPendulumExperiment(self):
        """当前视频的 experiment；每 video 至多一个（域不变量）。"""

        session = self._annotation_session
        if session is None or self._annotation_video_id is None:
            return None
        return next(
            (
                item
                for item in session.pendulum_experiments()
                if item.video_id == self._annotation_video_id
            ),
            None,
        )

    def _hidePendulumGuide(self) -> None:
        self.calibrationGuideLabel.hide()
        self.calibrationGuideButton.hide()
        self._calibration_guide_action = None

    def _pendulumGuide(self, message: str) -> None:
        """复用标定引导条展示 pendulum 点选说明（不注册 return 动作）。"""

        self.setWorkspace(WORKSPACE_SETUP)
        self._setCalibrationGuide(message)

    def beginPivotPick(self) -> None:
        if self.currentPendulumExperiment() is None:
            return
        if not self._measurement_allowed or self.projectActions.busy:
            return
        self._pendulumGuide(
            "Fixed pivot — click the suspension point on the video. This is the "
            "fixed geometry reference for the analysis; tracking a pivot landmark "
            "will not overwrite it. Press Esc to cancel.")
        self.trackList.clearSelection()
        self.videoView.set_calibration_mode("pivot")

    def beginVerticalPick(self) -> None:
        if self.currentPendulumExperiment() is None:
            return
        if not self._measurement_allowed or self.projectActions.busy:
            return
        self._pendulumGuide(
            "True vertical — click the TOP end first, then the BOTTOM end "
            "(the direction pointing down along gravity). The direction must be "
            "confirmed afterwards before analysis. Press Esc to cancel.")
        self.trackList.clearSelection()
        self.videoView.set_calibration_mode("vertical")

    def _exitPendulumPick(self) -> None:
        self.videoView.set_calibration_mode(None)
        self._hidePendulumGuide()

    def _onPivotClicked(self, point: QPointF) -> None:
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if (
            not self._measurement_allowed
            or self.projectActions.busy
            or session is None
            or experiment is None
        ):
            self._exitPendulumPick()
            return
        try:
            session.set_fixed_pivot(
                experiment.experiment_id, (point.x(), point.y())
            )
        except ProjectSessionError as error:
            self.statusBar().showMessage(f"Fixed pivot not saved: {error}")
            self._exitPendulumPick()
            return
        self._exitPendulumPick()
        self._afterPendulumChange(f"Fixed pivot set at ({point.x():.1f}, {point.y():.1f}) px")

    def _onVerticalLineDrawn(self, top: QPointF, bottom: QPointF) -> None:
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if (
            not self._measurement_allowed
            or self.projectActions.busy
            or session is None
            or experiment is None
        ):
            self._exitPendulumPick()
            return
        try:
            session.set_true_vertical(
                experiment.experiment_id,
                (top.x(), top.y()),
                (bottom.x(), bottom.y()),
            )
        except ProjectSessionError as error:
            self.statusBar().showMessage(f"True vertical not saved: {error}")
            self._exitPendulumPick()
            return
        self._exitPendulumPick()
        self._afterPendulumChange(
            "True vertical saved (top→bottom) — direction NOT confirmed yet; "
            "press 'Confirm direction' in the Pendulum panel")

    def _confirmVerticalDirection(self) -> None:
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        try:
            session.confirm_true_vertical(experiment.experiment_id)
        except ProjectSessionError as error:
            self.statusBar().showMessage(f"Direction not confirmed: {error}")
            return
        self._afterPendulumChange("Vertical direction confirmed (top→bottom = down)")

    def openPhysicalDialog(self) -> None:
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        dialog = PhysicalParametersDialog(self)
        if experiment.physical is not None:
            dialog.set_physical(experiment.physical)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            session.set_physical(
                experiment.experiment_id, dialog.physical_parameters()
            )
        except ProjectSessionError as error:
            QMessageBox.warning(self, "Physical parameters", str(error))
            return
        self._afterPendulumChange("Physical parameters saved")

    def _setReleaseToCurrentFrame(self) -> None:
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        if self._presented_frame_index is None:
            self.statusBar().showMessage(
                "Navigate to the release frame first, then press this button")
            return
        try:
            session.set_release_frame(
                experiment.experiment_id, self._presented_frame_index
            )
        except ProjectSessionError as error:
            self.statusBar().showMessage(f"Release frame not saved: {error}")
            return
        self._afterPendulumChange(
            f"Release frame set to {self._presented_frame_index}")

    def _afterPendulumChange(self, message: str) -> None:
        """pendulum 事实写入后的统一收敛：面板/卡片/标题同步。"""

        self._refreshCalibrationUI()
        self._refreshHistoryButtons()
        self.statusBar().showMessage(message)
        if self._guide_experiment_id is not None:
            self._refreshAnnotationGuide()

    # ------------------------------------------------------------------
    # Guided four-role marking (P1.2-S3)
    # ------------------------------------------------------------------

    @property
    def experiment_guide_active(self) -> bool:
        return self._guide_experiment_id is not None

    def _exitExperimentGuide(self) -> None:
        if self._guide_experiment_id is None:
            return
        self._guide_experiment_id = None
        self._guide_jump_target = None
        self._guide_jump_timer.stop()
        self._hidePendulumGuide()
        self._refreshMarkers()
        self.statusBar().showMessage("Guided marking finished")

    def beginExperimentAnnotation(self) -> None:
        """进入四 role 顺序引导：点击按当前待标 role 路由，无需选 track。"""

        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        if not self._measurement_allowed or self.projectActions.busy:
            self.statusBar().showMessage(
                "Verify video timing before guided marking")
            return
        worklist = frame_set_worklist(experiment)
        if worklist:
            start_frame = next(
                (
                    frame
                    for frame in worklist
                    if not annotation_guide_state(
                        session.project, experiment, frame
                    ).frame_complete
                ),
                worklist[-1],
            )
            self._beginGuideJump(start_frame)
        self._guide_experiment_id = experiment.experiment_id
        self.trackList.clearSelection()
        self.videoView.set_annotation_mode(True)
        self._refreshMarkers()
        self._refreshAnnotationGuide()
        self.statusBar().showMessage(
            "Guided marking: clicks land on the prompted landmark role")

    def _beginGuideJump(self, start_frame: int) -> None:
        """入口跳帧：立即尝试；被拒或未达目标时进入有界重试（F1）。

        2026-09-24 HR 真机观察到：项目加载后的第一次进入引导时跳帧偶发
        丢失（呈现帧停在原处，重新进入才生效），离线复现 2/2；插桩后
        守卫全绿未能再复现，判定为加载窗口期的瞬态竞态。此处不依赖单次
        seekFrame 的返回值：定时器每 200ms 重发一次（latest-wins 无副作用），
        直到呈现目标帧、引导退出或 5s 放弃并提示。
        """

        self._guide_jump_target = start_frame
        self._guide_jump_attempts = 25
        if not self.jumpToFrame(start_frame):
            self._guide_jump_timer.start()
        elif self._presented_frame_index == start_frame:
            self._guide_jump_target = None

    def _retryGuideJump(self) -> None:
        target = self._guide_jump_target
        if (target is None or self._guide_experiment_id is None
                or self._presented_frame_index == target):
            self._guide_jump_timer.stop()
            self._guide_jump_target = None
            return
        self._guide_jump_attempts -= 1
        if self._guide_jump_attempts <= 0:
            self._guide_jump_timer.stop()
            self._guide_jump_target = None
            self.statusBar().showMessage(
                "Frame jump deferred — video still loading; use the timeline")
            return
        self.jumpToFrame(target)

    def _refreshAnnotationGuide(self) -> None:
        """从当前事实重建引导条；引导未激活时不动标定引导。"""

        if self._guide_experiment_id is None:
            return
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if (
            session is None
            or experiment is None
            or experiment.experiment_id != self._guide_experiment_id
        ):
            self._exitExperimentGuide()
            return
        if self._presented_frame_index is None:
            self._setCalibrationGuide(
                "Guided marking: choose a frame with the timeline, then "
                "click the prompted landmark.")
            self.calibrationGuideButton.hide()
            return
        state = annotation_guide_state(
            session.project, experiment, self._presented_frame_index
        )
        if state.frame_complete:
            if state.next_frame_set_index is not None:
                self._setCalibrationGuide(
                    state.hint(),
                    "guide_next",
                    f"Next frame ({state.next_frame_set_index})",
                )
            else:
                self._setCalibrationGuide(
                    state.hint(), "guide_finish", "Finish guided marking"
                )
        elif state.current_role is not None:
            self._setCalibrationGuide(
                state.hint(), "guide_skip", f"Skip {state.current_role}"
            )
        else:
            self._setCalibrationGuide(state.hint())
            self.calibrationGuideButton.hide()

    def _onAnnotationGuideAction(self, action: str) -> None:
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        if action == "guide_skip":
            state = annotation_guide_state(
                session.project, experiment, self._presented_frame_index
            )
            # 跳过当前待标 role：从 pending 中移除该 role 在本帧的引导，
            # 通过记录跳过集合实现
            self._guide_skipped_roles.add(state.current_role)
            self._refreshAnnotationGuideForced()
            return
        if action == "guide_next":
            state = annotation_guide_state(
                session.project, experiment, self._presented_frame_index
            )
            if state.next_frame_set_index is not None:
                self.jumpToFrame(state.next_frame_set_index)
            return
        if action == "guide_finish":
            self._exitExperimentGuide()

    def _refreshAnnotationGuideForced(self) -> None:
        """Skip role 后按剩余 pending 重建引导条（跳过集合只影响本帧）。"""

        if self._guide_experiment_id is None:
            return
        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if session is None or experiment is None:
            return
        state = annotation_guide_state(
            session.project, experiment, self._presented_frame_index
        )
        remaining = tuple(
            role
            for role in state.pending_roles
            if role not in self._guide_skipped_roles
        )
        if remaining:
            hint = (
                f"Frame {state.frame_index}: click the {remaining[0]} "
                f"({len(state.done_roles)}/4 done; skipping: "
                f"{', '.join(sorted(self._guide_skipped_roles))}). "
                "Partial frames are saved but never used for training."
            )
            self._setCalibrationGuide(
                hint, "guide_skip", f"Skip {remaining[0]}"
            )
        else:
            # 全部剩余 role 均已跳过：保持 skip 集合直到换帧（presentFrame
            # 统一清空），否则引导点击会重新落到被跳过的 role 上
            self._setCalibrationGuide(
                f"Frame {state.frame_index}: remaining roles skipped — "
                "frame stays partial (never used for training).",
                "guide_finish" if state.next_frame_set_index is None
                else "guide_next",
                "Finish guided marking"
                if state.next_frame_set_index is None
                else f"Next frame ({state.next_frame_set_index})",
            )

    def _toggleDrawScaleMode(self, checked: bool) -> None:
        if checked:
            if not self._measurement_allowed or self.projectActions.busy:
                self.drawScaleButton.setChecked(False)
                return
            if self._calibration_return_workspace is None:
                self._calibration_return_workspace = self.currentWorkspace
                self._calibration_return_track_id = self._selected_track_id
                self._setCalibrationGuide(
                    "Calibration — step 1 of 2: draw along an object whose real "
                    "length you know, then enter that length.")
            self.setOriginButton.setChecked(False)
            self.trackList.clearSelection()
            self._selected_track_id = None
            self.videoView.set_annotation_mode(False)
            self.videoView.set_calibration_mode("scale")
            self.statusBar().showMessage(
                "Scale mode: drag or click two points to define scale; Esc to cancel"
            )
        else:
            self.videoView.set_calibration_mode(None)
            self.statusBar().showMessage("Browse mode")

    def _toggleSetOriginMode(self, checked: bool) -> None:
        if checked:
            if not self._measurement_allowed or self.projectActions.busy:
                self.setOriginButton.setChecked(False)
                return
            if self._calibration_return_workspace is None:
                self._calibration_return_workspace = self.currentWorkspace
                self._calibration_return_track_id = self._selected_track_id
                self._setCalibrationGuide(
                    "Calibration — step 2 of 2: click the coordinate origin. "
                    "Check the red +X and green +Y axis directions afterward.")
            self.drawScaleButton.setChecked(False)
            self.trackList.clearSelection()
            self._selected_track_id = None
            self.videoView.set_annotation_mode(False)
            self.videoView.set_calibration_mode("origin")
            self.statusBar().showMessage(
                "Origin mode: click on video to set coordinate origin; Esc to cancel"
            )
        else:
            self.videoView.set_calibration_mode(None)
            self.statusBar().showMessage("Browse mode")

    def _onScaleLineDrawn(self, p1: QPointF, p2: QPointF) -> None:
        if not self._measurement_allowed or self.projectActions.busy:
            self.drawScaleButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
            return
        if self._annotation_session is None or self._annotation_video_id is None:
            self.drawScaleButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
            return

        pixel_length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        if pixel_length < 1.0:
            self.statusBar().showMessage("Scale line is too short; ignored")
            self.drawScaleButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
            self._setCalibrationGuide(
                "The scale line was too short. Draw the known length again.",
                "retry_scale",
                "Draw scale again",
            )
            return

        default_name = self._annotation_session._next_calibration_name()
        dialog = CalibrationDialog(
            pixel_length=pixel_length,
            default_name=default_name,
            parent=self,
        )
        calibration_created = False
        if dialog.exec() == QMessageBox.DialogCode.Accepted or dialog.result() == 1:
            known_len = dialog.known_length()
            unit = dialog.unit()
            name = dialog.calibration_name()
            try:
                self._annotation_session.add_calibration(
                    video_id=self._annotation_video_id,
                    scale_end_1_px=(p1.x(), p1.y()),
                    scale_end_2_px=(p2.x(), p2.y()),
                    known_length=known_len,
                    unit=unit,
                    name=name,
                )
                calibration_created = True
                self.statusBar().showMessage(f"Calibration '{name}' set ({known_len:g} {unit})")
            except (ProjectSessionError, ValueError) as error:
                logger.error("add calibration failed", exc_info=True)
                QMessageBox.warning(self, "Calibration Error", str(error))

        self.drawScaleButton.setChecked(False)
        self.videoView.set_calibration_mode(None)
        self._refreshCalibrationUI()
        self._refreshHistoryButtons()
        if calibration_created:
            self._beginOriginStep()
        else:
            self._setCalibrationGuide(
                "Scale was not saved. Draw the known length again when ready.",
                "retry_scale",
                "Draw scale again",
            )

    def _onOriginClicked(self, pt: QPointF) -> None:
        if not self._measurement_allowed or self.projectActions.busy:
            self.setOriginButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
            return
        if self._annotation_session is None or self._annotation_video_id is None:
            self.setOriginButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
            return

        active_cal = self._annotation_session.active_calibration(self._annotation_video_id)
        if active_cal is None:
            self.statusBar().showMessage("No active calibration; please draw a scale line first")
            self.setOriginButton.setChecked(False)
            self.videoView.set_calibration_mode(None)
            self._setCalibrationGuide(
                "A scale is required before choosing the coordinate origin.",
                "retry_scale",
                "Draw scale",
            )
            return

        origin_set = False
        try:
            updated = replace(active_cal, origin_px=(pt.x(), pt.y()))
            self._annotation_session.update_calibration(updated)
            origin_set = True
            self.statusBar().showMessage(f"Origin set to ({pt.x():.1f}, {pt.y():.1f}) px")
        except (ProjectSessionError, ValueError) as error:
            logger.error("update origin failed", exc_info=True)
            self.statusBar().showMessage(f"Set origin failed: {error}")

        self.setOriginButton.setChecked(False)
        self.videoView.set_calibration_mode(None)
        self._refreshCalibrationUI()
        self._refreshHistoryButtons()
        if origin_set:
            self.projectActions.autosave(
                "coordinate system set", after=self._showCalibrationComplete)
        else:
            self._setCalibrationGuide(
                "The coordinate origin was not saved. Choose the origin again.",
                "retry_origin",
                "Choose origin again",
            )

    def _onRotationChanged(self, deg: float) -> None:
        if self._annotation_session is None or self._annotation_video_id is None:
            return
        active_cal = self._annotation_session.active_calibration(self._annotation_video_id)
        if active_cal is None:
            return
        if math.isclose(active_cal.rotation_deg, deg, rel_tol=0.0, abs_tol=1e-6):
            return
        try:
            updated = replace(active_cal, rotation_deg=deg)
            self._annotation_session.update_calibration(updated)
        except (ProjectSessionError, ValueError) as error:
            logger.error("update rotation failed", exc_info=True)
            self.statusBar().showMessage(f"Rotation update failed: {error}")
            return
        self._refreshCalibrationOverlay()
        self._refreshHistoryButtons()

    def _editActiveScale(self) -> None:
        """复用标尺对话框编辑属性，保留标定 ID、端点与原始观测。"""

        session, video_id = self._annotation_session, self._annotation_video_id
        if not self._measurement_allowed or self.projectActions.busy or session is None or video_id is None:
            return
        calibration = session.active_calibration(video_id)
        if calibration is None:
            return
        self.stopPlayback()
        dialog = CalibrationDialog(math.dist(calibration.scale_end_1_px, calibration.scale_end_2_px),
            calibration.name, calibration.known_length, calibration.unit, self)
        dialog.setWindowTitle("Edit scale calibration")
        # 保持已保存标尺的精度/范围，不能因编辑器的缺省四位小数静默改动它。
        decimals = max(dialog.lengthSpinBox.decimals(), -Decimal(str(calibration.known_length)).as_tuple().exponent)
        dialog.lengthSpinBox.setDecimals(decimals)
        dialog.lengthSpinBox.setRange(min(dialog.lengthSpinBox.minimum(), calibration.known_length),
                                      max(dialog.lengthSpinBox.maximum(), calibration.known_length))
        dialog.lengthSpinBox.setValue(calibration.known_length)
        if dialog.exec() != QMessageBox.DialogCode.Accepted:
            return
        name = calibration.name if dialog.nameEdit.text() == calibration.name else dialog.calibration_name()
        try:
            updated = replace(calibration, known_length=dialog.known_length(), unit=dialog.unit(), name=name)
            if updated == calibration:
                return
            session.update_calibration(updated)
        except (ProjectSessionError, ValueError) as error:
            self.statusBar().showMessage(f"Scale update failed: {error}")
            return
        self._refreshCalibrationUI()
        self._refreshHistoryButtons()
        self.statusBar().showMessage("Scale updated — recompute affected results")

    def _deleteInactiveCalibration(self) -> None:
        """选择非生效标定后删除，不为了删除而切换 active 标定。"""

        session, video_id = self._annotation_session, self._annotation_video_id
        if not self._measurement_allowed or self.projectActions.busy or session is None or video_id is None:
            return
        active = session.active_calibration(video_id)
        candidates = [cal for cal in session.calibrations if cal.video_id == video_id and cal != active]
        if not candidates:
            return
        self.stopPlayback()
        labels = [f"{index + 1}. {cal.name}" for index, cal in enumerate(candidates)]
        selected, accepted = QInputDialog.getItem(self, "Delete inactive calibration",
            "Delete which inactive calibration? (Undo is available)", labels, 0, False)
        if not accepted:
            return
        session.remove_calibration(candidates[labels.index(selected)].calibration_id)
        self._refreshCalibrationUI()
        self._refreshHistoryButtons()
        self.statusBar().showMessage("Inactive calibration deleted; active calibration unchanged")

    def _deleteActiveCalibration(self) -> None:
        if self._annotation_session is None or self._annotation_video_id is None:
            return
        active_cal = self._annotation_session.active_calibration(self._annotation_video_id)
        if active_cal is None:
            return
        self._annotation_session.remove_calibration(active_cal.calibration_id)
        self._refreshCalibrationUI()
        self._refreshHistoryButtons()
        self._setCalibrationGuide(
            "Calibration was removed. Draw a scale to calibrate this video again.",
            "retry_scale",
            "Draw scale",
        )
        self.statusBar().showMessage("Calibration deleted")

    def _onCalibrationSelected(self, _index: int) -> None:
        if self._annotation_session is None or self._annotation_video_id is None:
            return
        cal_id = self.calibrationSelector.currentData(Qt.ItemDataRole.UserRole)
        if cal_id is not None and isinstance(cal_id, UUID):
            self._annotation_session.set_active_calibration(self._annotation_video_id, cal_id)
        else:
            self._annotation_session.set_active_calibration(self._annotation_video_id, None)
        self._refreshCalibrationUI()
        self._refreshHistoryButtons()

    def _refreshCalibrationUI(self) -> None:
        # pendulum checklist 与标定同批刷新：两者共享同一组"session 事实
        # 变化"收敛点（导入/标定编辑/历史步进/几何录入）。
        self.pendulumPanel.refresh(
            self._annotation_session, self._annotation_video_id)
        self._refreshPendulumOverlay()
        if self._annotation_session is None or self._annotation_video_id is None:
            self.calibrationStatusLabel.setText("Status: Uncalibrated")
            with QSignalBlocker(self.calibrationSelector):
                self.calibrationSelector.clear()
            self.drawScaleButton.setEnabled(False)
            self.drawScaleButton.setChecked(False)
            self.setOriginButton.setEnabled(False)
            self.setOriginButton.setChecked(False)
            self.rotationSpinBox.setEnabled(False)
            self.deleteCalibrationButton.setEnabled(False)
            self.editScaleButton.setEnabled(False)
            self.deleteInactiveCalibrationButton.setEnabled(False)
            self.originLabel.setText("Origin: —")
            self.videoView.set_calibration(None)
            return

        session = self._annotation_session
        video_id = self._annotation_video_id
        active_cal = session.active_calibration(video_id)
        video_cals = [c for c in session.calibrations if c.video_id == video_id]

        with QSignalBlocker(self.calibrationSelector):
            self.calibrationSelector.clear()
            if not video_cals:
                self.calibrationSelector.addItem("No calibrations", None)
            else:
                for cal in video_cals:
                    self.calibrationSelector.addItem(cal.name, cal.calibration_id)
                if active_cal is not None:
                    idx = self.calibrationSelector.findData(active_cal.calibration_id)
                    if idx >= 0:
                        self.calibrationSelector.setCurrentIndex(idx)
                else:
                    self.calibrationSelector.setCurrentIndex(-1)

        has_cal = active_cal is not None
        self.drawScaleButton.setEnabled(self._measurement_allowed)
        self.setOriginButton.setEnabled(self._measurement_allowed and has_cal)
        self.rotationSpinBox.setEnabled(self._measurement_allowed and has_cal)
        self.deleteCalibrationButton.setEnabled(self._measurement_allowed and has_cal)
        self.editScaleButton.setEnabled(self._measurement_allowed and has_cal)
        self.deleteInactiveCalibrationButton.setEnabled(self._measurement_allowed and len(video_cals) > int(has_cal))

        if active_cal is not None:
            dx = active_cal.scale_end_2_px[0] - active_cal.scale_end_1_px[0]
            dy = active_cal.scale_end_2_px[1] - active_cal.scale_end_1_px[1]
            px_dist = math.hypot(dx, dy)
            scale_ratio = px_dist / active_cal.known_length
            self.calibrationStatusLabel.setText(
                f"Active: {active_cal.name} ({active_cal.known_length:g} {active_cal.unit}, {scale_ratio:.1f} px/{active_cal.unit})"
            )
            with QSignalBlocker(self.rotationSpinBox):
                self.rotationSpinBox.setValue(active_cal.rotation_deg)
            h = self._snapshot_height()
            if active_cal.origin_px is None:
                ox, oy = 0.0, float(h)
                self.originLabel.setText(
                    f"Origin: default bottom-left ({ox:.1f}, {oy:.1f}) px")
                if (not self.calibrationGuideLabel.isVisible()
                        or self._calibration_guide_action == "return"):
                    self._setCalibrationGuide(
                        "Scale is set. Next, choose the coordinate origin and check "
                        "the +X / +Y axis directions.",
                        "retry_origin",
                        "Choose origin / axes",
                    )
            else:
                ox, oy = active_cal.origin_px
                self.originLabel.setText(f"Origin: ({ox:.1f}, {oy:.1f}) px")
        else:
            self.calibrationStatusLabel.setText("Status: Uncalibrated")
            self.originLabel.setText("Origin: —")

        self._refreshCalibrationOverlay()

    def _snapshot_height(self) -> int:
        if self._annotation_session and self._annotation_video_id:
            for v in self._annotation_session.project.videos:
                if v.video_id == self._annotation_video_id:
                    return v.height_px
        return 480

    def _refreshPendulumOverlay(self) -> None:
        """experiment.geometry → 只读 overlay(S6-R1);无 experiment 即清空。"""

        experiment = self.currentPendulumExperiment()
        vertical = (
            experiment.geometry.true_vertical if experiment is not None else None
        )
        view = (
            PendulumOverlayView(
                fixed_pivot_px=experiment.geometry.fixed_pivot_px,
                vertical_top_px=vertical.top_px if vertical is not None else None,
                vertical_bottom_px=(
                    vertical.bottom_px if vertical is not None else None
                ),
                vertical_confirmed=(
                    vertical.direction_confirmed if vertical is not None else False
                ),
            )
            if experiment is not None
            else None
        )
        self.videoView.set_pendulum_overlay(view)

    def _refreshCalibrationOverlay(self) -> None:
        if self._annotation_session is None or self._annotation_video_id is None:
            self.videoView.set_calibration(None)
            self.videoView.set_pendulum_overlay(None)
            return
        active_cal = self._annotation_session.active_calibration(self._annotation_video_id)
        if active_cal is None:
            self.videoView.set_calibration(None)
            return
        h = self._snapshot_height()
        cal_view = CalibrationView(
            scale_end_1_px=active_cal.scale_end_1_px,
            scale_end_2_px=active_cal.scale_end_2_px,
            known_length=active_cal.known_length,
            unit=active_cal.unit,
            origin_px=active_cal.origin_px,
            rotation_deg=active_cal.rotation_deg,
        )
        self.videoView.set_calibration(cal_view, image_height=h)

    def _onAnnotationClicked(self, view_pos: QPoint) -> None:
        if not self._measurement_allowed or self.projectActions.busy or not self.videoView.is_annotation_mode():
            return
        if self._annotation_session is None:
            return
        guided = self._guide_experiment_id is not None
        if not guided and self._selected_track_id is None:
            return
        if self._presented_frame_index is None:
            return
        if self._has_pending_request:
            # 显示帧仍在途：此刻屏幕上的图像不是落帧目标，拒绝以免把
            # 坐标写到用户从未见过的帧（独立 review B2）
            self.statusBar().showMessage("Waiting for frame; mark ignored")
            return
        pixel = self.videoView.mapScreenToPixel(view_pos)
        if pixel is None:
            return  # 点击落在图像外（data-model.md §6.1：不钳位、不造值）
        if hasattr(self, "reviewActions") and self.reviewActions.is_correcting:
            handled = self.reviewActions.handleCorrectClick(pixel[0], pixel[1])
            if handled:
                self._refreshMarkers()
                self._refreshHistoryButtons()
            return
        if guided:
            self._onGuidedAnnotationClicked(pixel)
            return
        try:
            self._annotation_session.mark_point(
                self._selected_track_id,
                self._presented_frame_index,
                pixel[0],
                pixel[1],
            )
        except (ProjectSessionError, ValueError) as error:
            logger.error("mark point failed", exc_info=True)
            self.statusBar().showMessage(f"Mark failed: {error}")
            return
        self._refreshMarkers()
        self._refreshHistoryButtons()
        self._register_mark_for_autosave()

    def _register_mark_for_autosave(self) -> None:
        """每 10 个成功标注点触发一次静默自动保存（用户实测需求）。"""
        self._marks_since_autosave += 1
        if self._marks_since_autosave >= 10:
            self._marks_since_autosave = 0
            self.projectActions.autosave("10 new annotations")

    def _refreshTrackList(self) -> None:
        self.trackList.clear()
        self.trackDataLabel.setText("Stored observations: 0")
        if self._annotation_session is None:
            return
        self.trackDataLabel.setText(f"Stored observations: {len(self._annotation_session.project.observations)}")
        for track in self._annotation_session.tracks:
            if track.video_id != self._annotation_video_id:
                continue
            item = QListWidgetItem(track.name)
            item.setData(Qt.ItemDataRole.UserRole, track.track_id)
            self.trackList.addItem(item)

    def _onGuidedAnnotationClicked(self, pixel: tuple[float, float]) -> None:
        """引导点击：落点写到当前待标 role 的 track（无第二落点路径）。"""

        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        if (
            session is None
            or experiment is None
            or experiment.experiment_id != self._guide_experiment_id
            or self._presented_frame_index is None
        ):
            return
        state = annotation_guide_state(
            session.project, experiment, self._presented_frame_index
        )
        if state.frame_complete:
            self.statusBar().showMessage(
                "This frame is complete (4/4); use Next frame or the timeline")
            return
        pending = tuple(
            role
            for role in state.pending_roles
            if role not in self._guide_skipped_roles
        )
        if not pending:
            self.statusBar().showMessage(
                "All remaining roles skipped for this frame; use Next frame")
            return
        role = pending[0]
        try:
            session.mark_point(
                experiment.roles.track_id_for(role),
                self._presented_frame_index,
                pixel[0],
                pixel[1],
            )
        except ProjectSessionError as error:
            self.statusBar().showMessage(f"Point not saved: {error}")
            return
        self._refreshMarkers()
        self._refreshHistoryButtons()
        self._register_mark_for_autosave()
        if self._guide_skipped_roles:
            self._refreshAnnotationGuideForced()
        else:
            self._refreshAnnotationGuide()

    def _refreshMarkers(self) -> None:
        if self._annotation_session is None:
            return
        self.trackDataLabel.setText(f"Stored observations: {len(self._annotation_session.project.observations)}")
        if self._guide_experiment_id is not None:
            self._refreshGuidedMarkers()
            return
        selected = self.trackList.selectedItems()
        key = (self._annotation_session.project.observations, self._annotation_session.project.tracks,
               tuple(item.data(Qt.ItemDataRole.UserRole) for item in selected), self._annotation_video_id)
        if key == getattr(self, "_marker_data_key", None) and self._presented_frame_index is not None:
            self.videoView.set_current_frame(self._presented_frame_index)
            return
        self._marker_data_key = key
        if not selected or self._presented_frame_index is None:
            self.videoView.set_markers([])
            return
        tracks_by_id = {
            track.track_id: track for track in self._annotation_session.tracks
        }
        markers: list[MarkerView] = []
        for item in selected:
            track = tracks_by_id.get(item.data(Qt.ItemDataRole.UserRole))
            if track is None:
                continue
            markers.extend(
                MarkerView(
                    pixel_x=point.pixel_x,
                    pixel_y=point.pixel_y,
                    color=track.color,
                    is_current_frame=point.frame_index == self._presented_frame_index,
                    source=point.source, frame_index=point.frame_index,
                )
                for point in self._annotation_session.effective_points(track.track_id)
            )
        self.videoView.set_markers(markers)

    def _refreshGuidedMarkers(self) -> None:
        """引导模式：四 role 轨迹全部显示（各自 track 颜色），不依赖选中。"""

        session = self._annotation_session
        experiment = self.currentPendulumExperiment()
        key = (
            session.project.observations if session else (),
            self._presented_frame_index,
            self._guide_experiment_id,
        )
        if key == getattr(self, "_marker_data_key", None):
            self.videoView.set_current_frame(self._presented_frame_index)
            return
        self._marker_data_key = key
        markers: list[MarkerView] = []
        if session is not None and experiment is not None:
            tracks_by_id = {
                track.track_id: track for track in session.tracks
            }
            for role, member in experiment.roles.by_role().items():
                track = tracks_by_id.get(member)
                if track is None:
                    continue
                markers.extend(
                    MarkerView(
                        pixel_x=point.pixel_x,
                        pixel_y=point.pixel_y,
                        color=track.color,
                        is_current_frame=(
                            point.frame_index == self._presented_frame_index
                        ),
                        source=point.source,
                        frame_index=point.frame_index,
                    )
                    for point in session.effective_points(member)
                )
        self.videoView.set_markers(markers)

    def _onScaleChanged(self, scale: float) -> None:
        self.zoomLabel.setText(f"Zoom: {scale * 100:.0f}%")

    def _presentFrame(self, frame: DecodedFrame) -> None:
        self.videoView.setFrame(frame)
        blocker = QSignalBlocker(self.frameSpinBox)
        self.frameSpinBox.setValue(frame.frame_index)
        del blocker
        # 拖动滑块期间不回写位置，避免在途交付把滑块从用户手中拽走
        if not self.timelineSlider.isSliderDown():
            blocker = QSignalBlocker(self.timelineSlider)
            self.timelineSlider.setValue(frame.frame_index)
            del blocker
        self.frameLabel.setText(f"Frame: {frame.frame_index} / {self._frame_count - 1}")
        if self._timeline is None:
            return
        time_s = frame_to_time(frame.frame_index, self._timeline)
        self.timeLabel.setText(f"Time: {time_s:.3f} s nominal")
        self.previousButton.setEnabled(frame.frame_index > self._timeline.working_zone[0])
        self.nextButton.setEnabled(frame.frame_index < self._timeline.working_zone[1])
        self._presented_frame_index = frame.frame_index
        self._refreshMarkers()
        self._refreshDeletePointButton()
        # 引导标注：换帧即重建引导条（帧完成度随帧变化）
        if self._guide_experiment_id is not None:
            self._guide_skipped_roles.clear()
            self._refreshAnnotationGuide()
        self.presentedFrameChanged.emit(frame.frame_index)

    def _step(self, delta: int) -> None:
        if hasattr(self, "reviewActions") and self.reviewActions.is_correcting:
            self.reviewActions.cancelCorrectMode()
        snapshot = self._async.snapshot()
        if snapshot is None:
            return
        self.stopPlayback()
        # 以最后请求帧号为基准：快速连点时解码延迟不会吞掉第二次步进
        if self._last_requested_frame is not None:
            base = self._last_requested_frame
        else:
            base = snapshot.current_frame.frame_index
        low, high = self._timeline.working_zone
        target = max(low, min(base + delta, high))
        self._requestFrame(target)

    def _goToFrame(self, frame_index: int) -> None:
        if hasattr(self, "reviewActions") and self.reviewActions.is_correcting:
            self.reviewActions.cancelCorrectMode()
        if self._async.snapshot() is None:
            return
        self.stopPlayback()
        self._requestFrame(frame_index)

    def _scrubStarted(self) -> None:
        if hasattr(self, "reviewActions") and self.reviewActions.is_correcting:
            self.reviewActions.cancelCorrectMode()
        self.stopPlayback()

    def _scrubPreview(self, frame_index: int) -> None:
        # 高频拖动下的预览请求经 latest-wins 节流，最终停留位置必被解码
        self._requestFrame(frame_index)

    def _scrubCommitted(self) -> None:
        self._requestFrame(self.timelineSlider.value())

    def _chooseVideo(self) -> None:
        self.projectActions.openVideo()

    def _resetPresentation(self) -> None:
        self.videoView.clearFrame()
        self._calibration_return_workspace = None
        self._calibration_return_track_id = None
        self._calibration_guide_action = None
        self.calibrationGuideLabel.hide()
        self.calibrationGuideButton.hide()
        self._timeline = None
        self._frame_count = 0
        self._measurement_allowed = False
        self.addTrackButton.setEnabled(False)
        for control in (
            self.frameSpinBox,
            self.previousButton,
            self.nextButton,
            self.playButton,
            self.timelineSlider,
        ):
            control.setEnabled(False)
        self.frameLabel.setText("Frame: —")
        self.timeLabel.setText("Time: —")
        self._annotation_session = None
        self._annotation_video_id = None
        self._selected_track_id = None
        self._presented_frame_index = None
        self._refreshHistoryButtons()
        self._refreshCalibrationUI()
        self.trackList.clear()
        self.videoView.set_markers([])
        self.videoView.set_annotation_mode(False)
        self.deleteTrackButton.setEnabled(False)
