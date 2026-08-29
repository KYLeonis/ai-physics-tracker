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

    frameDelivered = Signal(object)
    decodeFailed = Signal(str)

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

        self.videoView = VideoView(self)
        self.previousButton = QPushButton("Previous frame", self)
        self.nextButton = QPushButton("Next frame", self)
        self.playButton = QPushButton("Play", self)
        self.frameSpinBox = QSpinBox(self)
        self.timelineSlider = QSlider(Qt.Orientation.Horizontal, self)
        self.frameLabel = QLabel("Frame: —", self)
        self.timeLabel = QLabel("Time: —", self)

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
        self.statusBar().showMessage("Ready")

    @property
    def isPlaying(self) -> bool:
        return self._is_playing

    def openVideo(self, path: Path, *, show_error: bool = True) -> bool:
        """打开视频并初始化全部展示状态；失败时保持关闭态。"""

        self.stopPlayback()
        self._resetPresentation()
        try:
            snapshot = self._async.open(path).result(timeout=10.0)
        except VideoError as error:
            self.statusBar().showMessage(str(error))
            if show_error:
                QMessageBox.critical(self, "Unable to open video", str(error))
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
        # worker 线程上下文：Qt signal emit 线程安全，slot 排队回 GUI 线程
        self.frameDelivered.emit(frame)

    def _emitDecodeFailed(self, error: VideoError) -> None:
        self.decodeFailed.emit(str(error))

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
        self._async.request_frame(frame_index)

    def _onFrameDelivered(self, frame: DecodedFrame) -> None:
        self._has_pending_request = False
        self._presentFrame(frame)
        if self._is_playing and frame.frame_index >= self._frame_count - 1:
            self.stopPlayback()

    def _onDecodeFailed(self, message: str) -> None:
        self._has_pending_request = False
        self.stopPlayback()
        self.statusBar().showMessage(message)
        snapshot = self._async.snapshot()
        if snapshot is not None:
            self._presentFrame(snapshot.current_frame)

    def _presentFrame(self, frame: DecodedFrame) -> None:
        self.videoView.setFrame(frame)
        blocker = QSignalBlocker(self.frameSpinBox)
        self.frameSpinBox.setValue(frame.frame_index)
        del blocker
        blocker = QSignalBlocker(self.timelineSlider)
        self.timelineSlider.setValue(frame.frame_index)
        del blocker
        self.frameLabel.setText(f"Frame: {frame.frame_index} / {self._frame_count - 1}")
        assert self._timeline is not None
        time_s = frame_to_time(frame.frame_index, self._timeline)
        self.timeLabel.setText(f"Time: {time_s:.3f} s nominal")
        self.previousButton.setEnabled(frame.frame_index > 0)
        self.nextButton.setEnabled(frame.frame_index < self._frame_count - 1)

    def _step(self, delta: int) -> None:
        snapshot = self._async.snapshot()
        if snapshot is None:
            return
        self.stopPlayback()
        target = snapshot.current_frame.frame_index + delta
        self._requestFrame(max(0, min(target, self._frame_count - 1)))

    def _goToFrame(self, frame_index: int) -> None:
        if self._async.snapshot() is None:
            return
        self.stopPlayback()
        self._requestFrame(frame_index)

    def _scrubStarted(self) -> None:
        self.stopPlayback()

    def _scrubPreview(self, frame_index: int) -> None:
        # 拖动中的预览请求经 latest-wins 合并，只有最终停留位置会被解码
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
