"""Phase 2 desktop shell for opening and stepping through one video."""

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.application.video import VideoError
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.video_view import VideoView


class MainWindow(QMainWindow):
    """Thin Qt shell around a Qt-free VideoSession."""

    def __init__(
        self,
        session: VideoSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self.setWindowTitle("AI Physics Tracker")
        self.resize(960, 720)

        self.videoView = VideoView(self)
        self.previousButton = QPushButton("Previous frame", self)
        self.nextButton = QPushButton("Next frame", self)
        self.frameSpinBox = QSpinBox(self)
        self.frameLabel = QLabel("Frame: —", self)
        self.timeLabel = QLabel("Time: —", self)

        self.frameSpinBox.setPrefix("Go to: ")
        self.frameSpinBox.setMinimum(0)
        self.frameSpinBox.setEnabled(False)
        self.previousButton.setEnabled(False)
        self.nextButton.setEnabled(False)

        controls = QHBoxLayout()
        controls.addWidget(self.previousButton)
        controls.addWidget(self.nextButton)
        controls.addSpacing(16)
        controls.addWidget(self.frameSpinBox)
        controls.addStretch(1)
        controls.addWidget(self.frameLabel)
        controls.addWidget(self.timeLabel)

        layout = QVBoxLayout()
        layout.addWidget(self.videoView, 1)
        layout.addLayout(controls)
        central = QWidget(self)
        central.setLayout(layout)
        self.setCentralWidget(central)

        openAction = QAction("Open video…", self)
        openAction.setShortcut(QKeySequence.StandardKey.Open)
        openAction.triggered.connect(self._chooseVideo)
        fileMenu = self.menuBar().addMenu("File")
        fileMenu.addAction(openAction)

        self.previousButton.clicked.connect(lambda: self._step(-1))
        self.nextButton.clicked.connect(lambda: self._step(1))
        self.frameSpinBox.valueChanged.connect(self._goToFrame)
        self.statusBar().showMessage("Ready")

    def openVideo(self, path: Path, *, show_error: bool = True) -> bool:
        """Open a path for UI or tests and refresh all presentation state."""

        try:
            self._session.open(path)
        except VideoError as error:
            self._resetPresentation()
            self.statusBar().showMessage(str(error))
            if show_error:
                QMessageBox.critical(self, "Unable to open video", str(error))
            return False
        self.frameSpinBox.setMaximum(self._session.info.frame_count - 1)
        self.frameSpinBox.setEnabled(True)
        self.previousButton.setEnabled(True)
        self.nextButton.setEnabled(True)
        self.statusBar().showMessage(str(path))
        self._refreshFrame()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:
        self._session.close()
        super().closeEvent(event)

    def _chooseVideo(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Open video",
            "",
            "Video files (*.mp4 *.avi *.mov *.mkv *.m4v);;All files (*)",
        )
        if selected:
            self.openVideo(Path(selected))

    def _step(self, delta: int) -> None:
        if not self._session.is_open:
            return
        try:
            self._session.step(delta)
        except VideoError as error:
            QMessageBox.critical(self, "Unable to read frame", str(error))
            return
        self._refreshFrame()

    def _goToFrame(self, frame_index: int) -> None:
        if not self._session.is_open:
            return
        try:
            self._session.go_to_frame(frame_index)
        except VideoError as error:
            QMessageBox.critical(self, "Unable to read frame", str(error))
            return
        self._refreshFrame()

    def _refreshFrame(self) -> None:
        frame = self._session.current_frame
        self.videoView.setFrame(frame)
        blocker = QSignalBlocker(self.frameSpinBox)
        self.frameSpinBox.setValue(frame.frame_index)
        del blocker
        self.frameLabel.setText(
            f"Frame: {frame.frame_index} / {self._session.info.frame_count - 1}"
        )
        self.timeLabel.setText(f"Time: {self._session.current_time_s:.3f} s nominal")
        self.previousButton.setEnabled(frame.frame_index > 0)
        self.nextButton.setEnabled(
            frame.frame_index < self._session.info.frame_count - 1
        )

    def _resetPresentation(self) -> None:
        self.videoView.clearFrame()
        self.frameSpinBox.setEnabled(False)
        self.previousButton.setEnabled(False)
        self.nextButton.setEnabled(False)
        self.frameLabel.setText("Frame: —")
        self.timeLabel.setText("Time: —")
