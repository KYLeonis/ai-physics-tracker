"""项目菜单、未保存保护与可取消后台操作；不直接执行文件系统 IO。"""

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Callable, TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog

from ai_physics_tracker.application.project_media import PreparedProject
from ai_physics_tracker.application.project_session import ProjectSession

if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


class ProjectActions(QObject):
    """长操作采用独立快照；取消仅放弃候选，不回写活动 Project。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="project-workflow")
        self.busy = False
        self.close_allowed = False
        self._cancellable = False
        self._was_annotating = False
        self._prior_session: ProjectSession | None = None
        self._cancel = Event()
        self._progress: QProgressDialog | None = None
        self._future: Future | None = None
        self._completion: Callable | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        menu = window.menuBar().addMenu("File")
        specs = (
            ("New project", QKeySequence.StandardKey.New, self.newProject),
            ("Open project…", QKeySequence.StandardKey.Open, self.openProject),
            ("Open video (new session)…", None, self.openVideo),
            ("Save", QKeySequence.StandardKey.Save, self.save),
            ("Save as…", QKeySequence.StandardKey.SaveAs, self.saveAs),
            ("Relink video…", None, self.relinkVideo),
            ("Close project", None, self.closeProject),
        )
        self.actions: list[QAction] = []
        for title, shortcut, callback in specs:
            action = QAction(title, window)
            if shortcut is not None:
                action.setShortcut(shortcut)
            action.triggered.connect(lambda _checked=False, fn=callback: fn())
            menu.addAction(action)
            self.actions.append(action)

    def refresh(self) -> None:
        session = self.window._annotation_session
        name = session.project.name if session is not None else "Untitled"
        dirty = " *" if session is not None and session.is_dirty else ""
        self.window.setWindowTitle(f"{name}{dirty} — AI Physics Tracker")

    def guarded(self, continuation: Callable[[], None]) -> None:
        if self.busy:
            return
        session = self.window._annotation_session
        self.window.stopPlayback()
        if session is None or not session.is_dirty:
            continuation()
            return
        choice = QMessageBox.question(
            self.window, "Unsaved changes", "Save project changes before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            self.save(continuation)
        elif choice == QMessageBox.StandardButton.Discard:
            continuation()

    def newProject(self) -> None:
        self.guarded(self._emptyProject)

    def _emptyProject(self) -> None:
        self.window.adoptEmptyProject()

    def closeProject(self) -> None:
        self.guarded(self._emptyProject)

    def openVideo(self) -> None:
        def choose() -> None:
            selected, _ = QFileDialog.getOpenFileName(self.window, "Open video", "",
                "Video files (*.mp4 *.avi *.mov *.mkv *.m4v);;All files (*)")
            if selected:
                self._load(lambda service, cancel: service.open_video(Path(selected), cancel))
        self.guarded(choose)

    def openProject(self) -> None:
        def choose() -> None:
            selected, _ = QFileDialog.getOpenFileName(self.window, "Open project", "", "Project manifest (project.json)")
            if selected:
                self._load(lambda service, cancel: service.open_project(Path(selected).parent, cancel))
        self.guarded(choose)

    def selectVideo(self, index: int) -> None:
        session = self.window._annotation_session
        video_id = self.window.videoSelector.itemData(index)
        if self.busy or session is None or video_id is None:
            return
        candidate = session.detached()
        self._load(lambda service, cancel: service.select_video(candidate, video_id, cancel))

    def relinkVideo(self) -> None:
        session = self.window._annotation_session
        video_id = self.window._annotation_video_id
        if self.busy or session is None or video_id is None:
            return
        selected, _ = QFileDialog.getOpenFileName(self.window, "Relink original video")
        if selected:
            candidate = session.detached()
            self._load(lambda service, cancel: service.relink(candidate, video_id, Path(selected), cancel))

    def _load(self, prepare: Callable) -> None:
        token, service = self.window.candidateService(deferTiming=True)
        def accept(prepared: PreparedProject) -> None:
            if prepared.warning:
                answer = QMessageBox.question(self.window, "Verify video identity", prepared.warning,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    self.executor.submit(prepared.close)
                    return
            self.window.adoptPrepared(prepared, token, service)
        self._run(lambda cancel: prepare(service, cancel), accept, cancellable=True)

    def save(self, after: Callable[[], None] | None = None) -> None:
        session = self.window._annotation_session
        if self.busy or session is None:
            return
        if session.project_root is None:
            self.saveAs(after)
            return
        self._saveCandidate(None, after)

    def saveAs(self, after: Callable[[], None] | None = None) -> None:
        if self.busy or self.window._annotation_session is None:
            return
        selected, _ = QFileDialog.getSaveFileName(self.window, "Choose a NEW project directory", "experiment")
        if selected:
            self._saveCandidate(Path(selected), after)

    def _saveCandidate(self, destination: Path | None, after: Callable[[], None] | None) -> None:
        session = self.window._annotation_session
        if session is None:
            return
        candidate = session.detached()
        candidate.update_view_state(self.window.captureProjectView())
        def save_worker(_cancel: Event) -> ProjectSession:
            if destination is None:
                candidate.save()
            else:
                candidate.save_as(destination)
            return candidate
        def accept(saved: ProjectSession) -> None:
            self.window._annotation_session = saved
            self.window._refreshHistoryButtons()
            self.window.statusBar().showMessage(f"Saved: {saved.project_root}")
            self.refresh()
            if after is not None:
                after()
        # 文件提交阶段不接受取消，避免已写入但 UI 声称未保存；选择目录阶段可取消。
        self._run(save_worker, accept, cancellable=False)

    def _run(self, work: Callable, completion: Callable, *, cancellable: bool) -> None:
        if self.busy:
            return
        self.busy = True
        self._cancellable = cancellable
        self._cancel = Event()
        self._completion = completion
        self._prior_session = self.window._annotation_session
        self._was_annotating = self.window.videoView.is_annotation_mode()
        self.window.stopPlayback()
        self.window.videoView.set_annotation_mode(False)
        self.window.centralWidget().setEnabled(False)
        for action in self.actions:
            action.setEnabled(False)
        self._progress = QProgressDialog("Opening project / checking media identity…" if cancellable else "Saving project…",
                                        "Cancel" if cancellable else "", 0, 0, self.window)
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        if cancellable:
            self._progress.canceled.connect(self._cancel.set)
        else:
            self._progress.setCancelButton(None)
        self._progress.show()
        self._future = self.executor.submit(work, self._cancel)
        self._timer.start(30)

    def _poll(self) -> None:
        if self._future is None or not self._future.done():
            return
        self._timer.stop()
        future, completion = self._future, self._completion
        self._future = None
        self._completion = None
        self.busy = False
        if self._progress is not None:
            self._progress.blockSignals(True)
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None
        self.window.centralWidget().setEnabled(True)
        for action in self.actions:
            action.setEnabled(True)
        try:
            value = future.result()
            if self._cancel.is_set():
                if isinstance(value, PreparedProject):
                    self.executor.submit(value.close)
            elif completion is not None:
                completion(value)
        except CancelledError:
            self.window.statusBar().showMessage("Cancelled; current project retained")
        except Exception as error:
            QMessageBox.critical(self.window, "Project operation failed", str(error))
        if self.busy:
            return  # 保存后续动作已启动新任务，不恢复旧任务的交互状态。
        self.window.syncVideoSelector()
        if (self.window._annotation_session is self._prior_session or not self._cancellable):
            self.window.videoView.set_annotation_mode(
                self._was_annotating and self.window._measurement_allowed)
        self.refresh()

    def requestWindowClose(self) -> bool:
        if self.close_allowed:
            return True
        if self.busy:
            if self._cancellable:
                self._cancel.set()
            return False
        session = self.window._annotation_session
        if session is None or not session.is_dirty:
            return True
        def close() -> None:
            self.close_allowed = True
            QTimer.singleShot(0, self.window.close)
        choice = QMessageBox.question(self.window, "Unsaved changes",
            "Save project changes before closing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Discard:
            return True
        if choice == QMessageBox.StandardButton.Save:
            self.save(close)
        return False

    def shutdown(self) -> None:
        self._timer.stop()
        if self._cancellable:
            self._cancel.set()
        future = self._future
        self._future = None
        self._completion = None
        self.executor.shutdown(wait=True)
        if future is not None:
            try:
                value = future.result()
            except Exception:
                # 关闭后只回收后台操作，不再弹出对话框访问已销毁的窗口。
                value = None
            if isinstance(value, PreparedProject):
                value.close()
        self.busy = False
