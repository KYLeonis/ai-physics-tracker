"""Phase 2 桌面外壳：异步播放、时间轴与逐帧浏览。"""

import logging
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.application.playback import AsyncVideoSession
from ai_physics_tracker.application.video import DecodedFrame, VideoError
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.gui.video_view import VideoView

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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI Physics Tracker")
        self.resize(960, 720)

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

        self.videoView = VideoView(self)
        self.previousButton = QPushButton("Previous frame", self)
        self.nextButton = QPushButton("Next frame", self)
        self.playButton = QPushButton("Play", self)
        self.frameSpinBox = QSpinBox(self)
        self.timelineSlider = QSlider(Qt.Orientation.Horizontal, self)
        self.frameLabel = QLabel("Frame: —", self)
        self.timeLabel = QLabel("Time: —", self)
        self.zoomLabel = QLabel("Zoom: —", self)

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

        layout = QVBoxLayout()
        layout.addWidget(self.videoView, 1)
        layout.addWidget(self.timelineSlider)
        layout.addLayout(controls)
        central = QWidget(self)
        central.setLayout(layout)
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
        viewMenu = self.menuBar().addMenu("View")
        viewMenu.addAction(zoomInAction)
        viewMenu.addAction(zoomOutAction)
        viewMenu.addSeparator()
        viewMenu.addAction(zoomFitAction)
        viewMenu.addAction(zoomOriginalAction)

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
        self.statusBar().showMessage("Ready")

    @property
    def isPlaying(self) -> bool:
        return self._is_playing

    def openVideo(self, path: Path, *, show_error: bool = True) -> bool:
        """打开视频并初始化全部展示状态；失败时保持关闭态。"""

        self.stopPlayback()
        self._delivery_generation += 1
        self._has_pending_request = False
        self._last_requested_frame = None
        self._resetPresentation()
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
        fps = snapshot.timeline.fps_nominal
        interval_ms = max(1, round(1000.0 / fps))
        self._is_playing = True
        self.playButton.setText("Pause")
        self._playTimer.start(interval_ms)
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
