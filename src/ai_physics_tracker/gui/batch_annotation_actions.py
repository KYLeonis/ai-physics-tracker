"""GUI：建议帧多选、连续标注 / 修正与暂停；复用 Session 的原子写点。"""

import logging
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout

from ai_physics_tracker.application.annotation_batch import AnnotationBatch
from ai_physics_tracker.application.project_session import ProjectSessionError

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


class BatchAnnotationActions(QObject):
    """只持有瞬时队列；换工程 / Track 清空队列，已写人工点保持原样。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.batch: AnnotationBatch | None = None
        self._session = None
        panel = window.trackingActions.panel
        panel.suggestedFramesList.setSelectionMode(panel.suggestedFramesList.SelectionMode.ExtendedSelection)
        panel.reviewCandidatesList.setSelectionMode(panel.reviewCandidatesList.SelectionMode.ExtendedSelection)
        self.labelButton = QPushButton("Label selected frames")
        self.correctButton = QPushButton("Correct selected frames")
        self.selectionGroup = QGroupBox("Suggested frames — select a batch")
        selection_layout = QVBoxLayout(self.selectionGroup)
        selection_layout.addWidget(QLabel("Use Cmd/Ctrl or Shift to select frames; click once per frame to advance."))
        selection_layout.addWidget(panel.suggestedFramesList)
        selection_layout.addWidget(self.labelButton)
        panel.widget().widget().layout().insertWidget(8, self.selectionGroup)
        panel.suggestionsChanged.connect(self.refresh)
        panel.reviewCandidatesList.parentWidget().layout().addWidget(self.correctButton)
        self.labelButton.clicked.connect(lambda: self.startSelected(False))
        self.correctButton.clicked.connect(lambda: self.startSelected(True))
        self.group = QGroupBox("Continuous annotation")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.pauseButton = QPushButton("Pause (Esc)")
        self.resumeButton = QPushButton("Resume batch")
        self.skipButton = QPushButton("Skip this frame")
        self.learnButton = QPushButton("Start learning with corrected labels")
        layout = QVBoxLayout(self.group)
        for widget in (self.status, self.pauseButton, self.resumeButton, self.skipButton, self.learnButton):
            layout.addWidget(widget)
        panel.widget().widget().layout().insertWidget(8, self.group)
        self.pauseButton.clicked.connect(self.pause)
        self.resumeButton.clicked.connect(self.resume)
        self.skipButton.clicked.connect(self.skip)
        self.learnButton.clicked.connect(lambda: window.trackingActions._onCardAction("start_learning"))
        window.selectedTrackChanged.connect(self._contextChanged)
        window.projectChanged.connect(self.clear)
        window.analysisChanged.connect(self.refresh)
        panel.suggestedFramesList.itemSelectionChanged.connect(self._selectionChanged)
        panel.reviewCandidatesList.itemSelectionChanged.connect(self._selectionChanged)
        self.refresh()

    def _selectionChanged(self) -> None:
        # 列表可能正处于 clear()/重建中，不能从选择信号重入整个任务面板刷新。
        panel = self.window.trackingActions.panel
        blocked = self._blocked()
        self.labelButton.setEnabled(bool(panel.suggestedFramesList.selectedItems()) and not blocked)
        self.correctButton.setEnabled(bool(panel.reviewCandidatesList.selectedItems()) and not blocked)

    @property
    def active(self) -> bool:
        return self.batch is not None and not self.batch.finished and not self.batch.paused

    def _blocked(self) -> bool:
        w = self.window
        return (w.projectActions.busy or w.trackingActions.pending or w.frameSelectionActions.busy
                or w.reviewActions.busy or bool(getattr(w, "modelActions", None) and w.modelActions.busy))

    def startSelected(self, review: bool) -> None:
        panel = self.window.trackingActions.panel
        source = panel.reviewCandidatesList if review else panel.suggestedFramesList
        frames = tuple(item.data(Qt.ItemDataRole.UserRole) for item in source.selectedItems())
        run_id = self.window.reviewActions.controller.run_id if review and self.window.reviewActions.controller else None
        if review and run_id is None:
            return
        self.start(frames, run_id)

    def start(self, frames: tuple[int, ...], run_id: UUID | None = None) -> None:
        w = self.window
        session, track_id = w.analysisSession, w.selectedTrackId
        if not frames or self._blocked() or session is None or track_id is None:
            return
        track = next(t for t in session.tracks if t.track_id == track_id)
        if not session.can_measure(track.video_id):
            return
        timeline = next(t for t in session.project.timelines if t.video_id == track.video_id)
        if any(type(f) is not int or not timeline.working_zone[0] <= f <= timeline.working_zone[1] for f in frames):
            w.statusBar().showMessage("Select frames inside the current working zone")
            return
        if run_id is not None:
            run = next((r for r in session.tracking_runs() if r.run_id == run_id), None)
            state = session.get_suggested_frame_review(run_id)
            allowed = {c.frame_index for c in state.active_batch.candidates} if state and state.active_batch else set()
            if run is None or run.track_id != track_id or not set(frames) <= allowed:
                return
        w.reviewActions.cancelCorrectMode()
        self._session = session
        self.batch = AnnotationBatch(track_id, tuple(dict.fromkeys(frames)), run_id)
        w.setWorkspace("acquire")
        self._seek()
        self.refresh()

    def _seek(self) -> None:
        if not self.active:
            return
        w = self.window
        if not w.seekFrame(self.batch.current_frame):
            self.batch = replace(self.batch, paused=True)
            w.statusBar().showMessage("Batch paused; finish the current operation before resuming")
            return
        if self.batch.run_id is not None and w.reviewActions.controller is not None:
            w.reviewActions.controller.select_frame(self.batch.current_frame)
            w.reviewActions._sync_panel_with_controller()
        w.videoView.set_annotation_mode(True)

    def handleClick(self, pixel_x: float, pixel_y: float) -> bool:
        if not self.active:
            return False
        w, batch = self.window, self.batch
        if (self._blocked() or w.currentWorkspace != "acquire" or w.analysisSession is not self._session
                or w.selectedTrackId != batch.track_id or w.presented_frame_index != batch.current_frame
                or w._has_pending_request):
            w.statusBar().showMessage("Wait for the selected batch frame before placing a point")
            return True
        try:
            if batch.run_id is None:
                self._session.mark_point(batch.track_id, batch.current_frame, pixel_x, pixel_y)
            else:
                self._session.correct_suggested_frame(batch.run_id, batch.current_frame, pixel_x, pixel_y)
        except (ProjectSessionError, ValueError) as error:
            logger.error("batch annotation failed: %s", error)
            w.statusBar().showMessage(f"Correction failed: {error}")
            return True
        self.batch = batch.advance(corrected=True)
        w._refreshMarkers()
        w._refreshHistoryButtons()
        self._advance()
        return True

    def skip(self) -> None:
        if not self.active or self._blocked():
            return
        if self.batch.run_id is not None:
            state = self._session.get_suggested_frame_review(self.batch.run_id)
            existing = state.reviewed_frames.get(self.batch.current_frame)
            # 已修正项保留原事务；未修正困难帧记录 Skip，代表帧跳过不制造标签。
            if existing is None or existing.disposition != "corrected":
                try:
                    self._session.skip_suggested_frame(self.batch.run_id, self.batch.current_frame)
                except (ProjectSessionError, ValueError) as error:
                    self.window.statusBar().showMessage(f"Skip failed: {error}")
                    return
                self.window._refreshHistoryButtons()
        self.batch = self.batch.advance(corrected=False)
        self._advance()

    def _advance(self) -> None:
        if self.batch.finished:
            self.window.videoView.set_annotation_mode(False)
            self.window.projectActions.autosave("continuous annotation batch completed")
        else:
            self._seek()
        self.refresh()

    def pause(self) -> None:
        if self.active:
            self.batch = replace(self.batch, paused=True)
            self.window.videoView.set_annotation_mode(False)
            self.refresh()

    def resume(self) -> None:
        if self.batch is None or self.batch.finished or self._blocked():
            return
        self.window.setWorkspace("acquire")
        self.batch = replace(self.batch, paused=False)
        self._seek()
        self.refresh()

    def clear(self, *_args) -> None:
        was_active = self.active
        self.batch, self._session = None, None
        if was_active:
            self.window.videoView.set_annotation_mode(False)
        self.refresh()

    def _contextChanged(self, *_args) -> None:
        if self.batch and self.batch.track_id != self.window.selectedTrackId:
            self.clear()

    def refresh(self, *_args) -> None:
        w = self.window
        panel = w.trackingActions.panel
        blocked = self._blocked()
        self.selectionGroup.setVisible(panel.suggestedFramesList.count() > 0)
        self.labelButton.setEnabled(bool(panel.suggestedFramesList.selectedItems()) and not blocked)
        self.correctButton.setEnabled(bool(panel.reviewCandidatesList.selectedItems()) and not blocked)
        batch = self.batch
        self.group.setVisible(batch is not None)
        if batch is not None:
            self.status.setText(
                f"Batch complete: {batch.corrected} manual label(s). "
                + ("Next: start learning. " if batch.corrected else "No labels added. ")
                + "Skipped frames remain unchanged."
                if batch.finished else
                f"{'Paused' if batch.paused else 'Click video'} · {batch.index + 1}/{len(batch.frames)} · frame {batch.current_frame}")
            self.pauseButton.setVisible(self.active)
            self.skipButton.setVisible(self.active)
            self.resumeButton.setVisible(batch.paused and not batch.finished)
            self.resumeButton.setEnabled(not blocked)
            self.skipButton.setEnabled(not blocked)
            self.learnButton.setVisible(batch.finished and batch.corrected > 0)
            manual_count = len(w.analysisSession.manual_points(batch.track_id)) if w.analysisSession else 0
            self.learnButton.setEnabled(not blocked and manual_count >= 3)
        w.trackingActions._context_key = None
        w.trackingActions.refresh()
