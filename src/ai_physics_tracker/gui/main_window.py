"""Phase 2 桌面外壳：异步播放、时间轴、逐帧浏览与手工标注。"""

import logging
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QPoint, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.application.playback import AsyncVideoSession
from ai_physics_tracker.application.project_session import (
    ProjectRepositoryPort,
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import DecodedFrame, VideoError
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.gui.video_view import MarkerView, VideoView

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """包裹 Qt-free AsyncVideoSession 的薄 Qt 外壳。

    解码回调由 worker 线程经 Qt signal 转入 GUI 线程；播放节奏用 QTimer
    按 `Timeline.fps_nominal` 计算的显示间隔推进（间隔只是 UI 节奏，不是
    时间语义，时间显示始终经 Timeline 换算）。
    """

    frameDelivered = Signal(object, int)
    decodeFailed = Signal(str, int)

    def __init__(
        self,
        session: VideoSession,
        annotation_repository: ProjectRepositoryPort,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Physics Tracker")
        self.resize(960, 720)
        self._annotation_repository = annotation_repository

        self._async = AsyncVideoSession(
            session, self._emitFrameDelivered, self._emitDecodeFailed
        )
        self._is_playing = False
        self._has_pending_request = False
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

        self.videoView = VideoView(self)
        self.previousButton = QPushButton("Previous frame", self)
        self.nextButton = QPushButton("Next frame", self)
        self.playButton = QPushButton("Play", self)
        self.frameSpinBox = QSpinBox(self)
        self.timelineSlider = QSlider(Qt.Orientation.Horizontal, self)
        self.frameLabel = QLabel("Frame: —", self)
        self.timeLabel = QLabel("Time: —", self)
        self.zoomLabel = QLabel("Zoom: —", self)

        self.trackList = QListWidget(self)
        self.addTrackButton = QPushButton("Add track", self)
        self.deleteTrackButton = QPushButton("Delete track", self)
        self.deleteTrackButton.setEnabled(False)

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

        controls = QHBoxLayout()
        controls.addWidget(self.playButton)
        controls.addWidget(self.previousButton)
        controls.addWidget(self.nextButton)
        controls.addSpacing(16)
        controls.addWidget(self.frameSpinBox)
        controls.addStretch(1)
        controls.addWidget(self.frameLabel)
        controls.addWidget(self.timeLabel)
        controls.addWidget(self.zoomLabel)

        trackButtons = QHBoxLayout()
        trackButtons.addWidget(self.addTrackButton)
        trackButtons.addWidget(self.deleteTrackButton)
        trackPanel = QVBoxLayout()
        trackPanel.addWidget(self.trackList, 1)
        trackPanel.addLayout(trackButtons)
        trackSide = QWidget(self)
        trackSide.setLayout(trackPanel)
        trackSide.setMaximumWidth(220)

        videoColumn = QVBoxLayout()
        videoColumn.addWidget(self.videoView, 1)
        videoColumn.addWidget(self.timelineSlider)
        videoColumn.addLayout(controls)
        videoColumnWidget = QWidget(self)
        videoColumnWidget.setLayout(videoColumn)

        mainRow = QHBoxLayout()
        mainRow.addWidget(videoColumnWidget, 1)
        mainRow.addWidget(trackSide)
        central = QWidget(self)
        central.setLayout(mainRow)
        self.setCentralWidget(central)

        openAction = QAction("Open video…", self)
        openAction.setShortcut(QKeySequence.StandardKey.Open)
        openAction.triggered.connect(self._chooseVideo)
        fileMenu = self.menuBar().addMenu("File")
        fileMenu.addAction(openAction)

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
        self.videoView.scaleChanged.connect(self._onScaleChanged)
        self.videoView.annotationClicked.connect(self._onAnnotationClicked)
        self.addTrackButton.clicked.connect(self._addTrack)
        self.deleteTrackButton.clicked.connect(self._deleteSelectedTrack)
        self.trackList.itemSelectionChanged.connect(self._onTrackSelectionChanged)
        annotationEscape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        annotationEscape.activated.connect(self._exitAnnotationMode)
        self.statusBar().showMessage("Ready")

    @property
    def isPlaying(self) -> bool:
        return self._is_playing

    @property
    def playbackRate(self) -> float:
        return self._playback_rate

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

    def openVideo(self, path: Path, *, show_error: bool = True) -> bool:
        """打开视频并初始化全部展示状态；失败时保持关闭态。"""

        self.stopPlayback()
        self._delivery_generation += 1
        self._has_pending_request = False
        self._last_requested_frame = None
        self._resetPresentation()
        # domain Video 的 original_path 要求绝对路径；对话框恒给绝对路径，
        # 编程调用（测试/脚本）可能给相对路径，此处统一解析
        path = path.resolve()
        try:
            snapshot = self._async.open(path).result(timeout=10.0)
        except VideoError as error:
            self.statusBar().showMessage(str(error))
            if show_error:
                QMessageBox.critical(self, "Unable to open video", str(error))
            return False
        except TimeoutError:
            # worker 仍在打开中；不再等待，提示用户稍后重试
            message = "Opening video timed out; the file may be very large."
            self.statusBar().showMessage(message)
            if show_error:
                QMessageBox.critical(self, "Unable to open video", message)
            return False
        except Exception as error:
            logger.error("unexpected open failure", exc_info=True)
            message = f"Unexpected error while opening video: {error}"
            self.statusBar().showMessage(message)
            if show_error:
                QMessageBox.critical(self, "Unable to open video", message)
            return False
        self._frame_count = snapshot.info.frame_count
        self._timeline = snapshot.timeline
        self._annotation_session = ProjectSession.start(self._annotation_repository)
        _video, _project_timeline = self._annotation_session.register_external_video(
            path, snapshot.info
        )
        self._annotation_video_id = _video.video_id
        self._selected_track_id = None
        self._refreshTrackList()
        self.frameSpinBox.setMaximum(self._frame_count - 1)
        self.timelineSlider.setMaximum(self._frame_count - 1)
        for control in (
            self.frameSpinBox,
            self.previousButton,
            self.nextButton,
            self.playButton,
            self.timelineSlider,
        ):
            control.setEnabled(True)
        self.statusBar().showMessage(str(path))
        self._presentFrame(snapshot.current_frame)
        return True

    def togglePlayback(self) -> None:
        if self._is_playing:
            self.stopPlayback()
            return
        self.startPlayback()

    def startPlayback(self) -> None:
        snapshot = self._async.snapshot()
        if snapshot is None:
            return
        if snapshot.current_frame.frame_index >= self._frame_count - 1:
            # 播放到末尾后再次播放：从头开始，避免静止在末帧
            self._requestFrame(0)
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
        self.stopPlayback()
        self._async.close()
        super().closeEvent(event)

    def _emitFrameDelivered(self, frame: DecodedFrame) -> None:
        # worker 线程上下文：Qt signal emit 线程安全，slot 排队回 GUI 线程；
        # 代际随交付携带，跨代际的迟到交付在 slot 内丢弃
        self.frameDelivered.emit(frame, self._delivery_generation)

    def _emitDecodeFailed(self, error: VideoError) -> None:
        self.decodeFailed.emit(str(error), self._delivery_generation)

    def _playTick(self) -> None:
        # 解码慢于帧率时节流：等上一请求交付后再发下一个（不堆积请求）；
        # 也覆盖"从末帧重播"场景——回跳第 0 帧的请求在途时快照仍是末帧。
        if self._has_pending_request:
            return
        snapshot = self._async.snapshot()
        if snapshot is None:
            self.stopPlayback()
            return
        if snapshot.current_frame.frame_index >= self._frame_count - 1:
            self.stopPlayback()
            return
        self._requestFrame(snapshot.current_frame.frame_index + 1)

    def _requestFrame(self, frame_index: int) -> None:
        self._has_pending_request = True
        self._last_requested_frame = frame_index
        self._async.request_frame(frame_index)

    def _onFrameDelivered(self, frame: DecodedFrame, generation: int) -> None:
        if generation != self._delivery_generation:
            return
        self._has_pending_request = False
        self._last_requested_frame = frame.frame_index
        self._presentFrame(frame)
        if self._is_playing and frame.frame_index >= self._frame_count - 1:
            self.stopPlayback()

    def _onDecodeFailed(self, message: str, generation: int) -> None:
        if generation != self._delivery_generation:
            return
        self._has_pending_request = False
        self.stopPlayback()
        self.statusBar().showMessage(message)
        snapshot = self._async.snapshot()
        if snapshot is not None:
            self._presentFrame(snapshot.current_frame)

    def _addTrack(self) -> None:
        if self._annotation_session is None or self._annotation_video_id is None:
            return
        track = self._annotation_session.add_track(self._annotation_video_id)
        self._refreshTrackList()
        for row in range(self.trackList.count()):
            if self.trackList.item(row).data(Qt.ItemDataRole.UserRole) == track.track_id:
                self.trackList.setCurrentRow(row)

    def _deleteSelectedTrack(self) -> None:
        if self._annotation_session is None or self._selected_track_id is None:
            return
        self._annotation_session.remove_track(self._selected_track_id)
        self._selected_track_id = None
        self.trackList.setCurrentRow(-1)
        self.trackList.clearSelection()
        self._refreshTrackList()
        self._refreshMarkers()

    def _onTrackSelectionChanged(self) -> None:
        # 基于 selectedItems 而非 currentItem：clearSelection/点击列表空白后
        # currentItem 仍保留旧项（Qt 语义），据此判定无法实现 D2 退出路径
        selected = self.trackList.selectedItems()
        track_id = (
            selected[0].data(Qt.ItemDataRole.UserRole) if selected else None
        )
        self._selected_track_id = track_id
        self.deleteTrackButton.setEnabled(track_id is not None)
        self.videoView.set_annotation_mode(track_id is not None)
        if track_id is not None:
            self.statusBar().showMessage(
                "Annotation mode: click the video to mark; Esc or click an empty "
                "list area to exit"
            )
        elif self._annotation_session is not None:
            self.statusBar().showMessage("Browse mode")
        self._refreshMarkers()

    def _exitAnnotationMode(self) -> None:
        if self._selected_track_id is not None:
            self.trackList.setCurrentRow(-1)

    def _onAnnotationClicked(self, view_pos: QPoint) -> None:
        if self._annotation_session is None or self._selected_track_id is None:
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

    def _refreshTrackList(self) -> None:
        self.trackList.clear()
        if self._annotation_session is None:
            return
        for track in self._annotation_session.tracks:
            item = QListWidgetItem(track.name)
            item.setData(Qt.ItemDataRole.UserRole, track.track_id)
            self.trackList.addItem(item)

    def _refreshMarkers(self) -> None:
        if self._annotation_session is None:
            return
        if self._selected_track_id is None:
            self.videoView.set_markers([])
            return
        track = next(
            (
                item
                for item in self._annotation_session.tracks
                if item.track_id == self._selected_track_id
            ),
            None,
        )
        if track is None:
            self.videoView.set_markers([])
            return
        if self._presented_frame_index is None:
            self.videoView.set_markers([])
            return
        markers = [
            MarkerView(
                pixel_x=point.pixel_x,
                pixel_y=point.pixel_y,
                color=track.color,
                is_current_frame=point.frame_index == self._presented_frame_index,
            )
            for point in self._annotation_session.manual_points(track.track_id)
        ]
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
        self.previousButton.setEnabled(frame.frame_index > 0)
        self.nextButton.setEnabled(frame.frame_index < self._frame_count - 1)
        self._presented_frame_index = frame.frame_index
        self._refreshMarkers()

    def _step(self, delta: int) -> None:
        snapshot = self._async.snapshot()
        if snapshot is None:
            return
        self.stopPlayback()
        # 以最后请求帧号为基准：快速连点时解码延迟不会吞掉第二次步进
        if self._last_requested_frame is not None:
            base = self._last_requested_frame
        else:
            base = snapshot.current_frame.frame_index
        target = max(0, min(base + delta, self._frame_count - 1))
        self._requestFrame(target)

    def _goToFrame(self, frame_index: int) -> None:
        if self._async.snapshot() is None:
            return
        self.stopPlayback()
        self._requestFrame(frame_index)

    def _scrubStarted(self) -> None:
        self.stopPlayback()

    def _scrubPreview(self, frame_index: int) -> None:
        # 高频拖动下的预览请求经 latest-wins 节流，最终停留位置必被解码
        self._requestFrame(frame_index)

    def _scrubCommitted(self) -> None:
        self._requestFrame(self.timelineSlider.value())

    def _chooseVideo(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Open video",
            "",
            "Video files (*.mp4 *.avi *.mov *.mkv *.m4v);;All files (*)",
        )
        if selected:
            self.openVideo(Path(selected))

    def _resetPresentation(self) -> None:
        self.videoView.clearFrame()
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
        self.trackList.clear()
        self.videoView.set_markers([])
        self.videoView.set_annotation_mode(False)
        self.deleteTrackButton.setEnabled(False)
