"""教师模型导入、自检与候选轨迹入口；耗时 IO / 引擎均在后台。"""

from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QFileDialog, QGroupBox, QLabel, QPushButton, QVBoxLayout, QFormLayout

from ai_physics_tracker.application.imported_model_job import ModelJobRunner, verified_self_test
from ai_physics_tracker.domain.imported_model import ImportedModel


if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


class ModelActions(QObject):
    """Qt 只处理选择与上下文；生命周期与文件写入委托应用层。"""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.backend = ModelJobRunner()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="teacher-model")
        self._future = None
        self._pending_probe = False
        self._cancel = Event()
        self._context = None
        self._kind = None
        self._closed = False
        self._video_editable = None
        self.group = QGroupBox("Teacher model")
        layout = QVBoxLayout(self.group)
        self.models = QComboBox()
        self.bodyparts = QComboBox()
        self.device = QComboBox()
        self.device.addItems(["auto", "cpu", "mps", "cuda"])
        self.importButton = QPushButton("Import DLC teacher model…")
        self.testButton = QPushButton("Self-test on displayed frame")
        self.inferButton = QPushButton("Generate trajectory with teacher")
        self.cancelButton = QPushButton("Cancel model operation")
        self.status = QLabel("Import config.yaml, pytorch_config.yaml and a .pt checkpoint.")
        self.status.setWordWrap(True)
        layout.addWidget(self.importButton)
        form = QFormLayout()
        form.addRow("Model", self.models)
        form.addRow("Bodypart → current track", self.bodyparts)
        form.addRow("Teacher device", self.device)
        layout.addLayout(form)
        for widget in (self.testButton, self.inferButton, self.cancelButton, self.status):
            layout.addWidget(widget)
        panel = window.trackingActions.panel
        panel.widget().widget().layout().insertWidget(8, self.group)
        self.fileAction = QAction("Import teacher model…", window)
        window.projectActions.menu.addAction(self.fileAction)
        self.fileAction.triggered.connect(self.selectFiles)
        self.importButton.clicked.connect(self.selectFiles)
        self.testButton.clicked.connect(self.selfTest)
        self.inferButton.clicked.connect(self.infer)
        self.cancelButton.clicked.connect(self.cancel)
        self.models.currentIndexChanged.connect(self._selected)
        self.device.currentTextChanged.connect(self._deviceChanged)
        window.projectChanged.connect(self.refresh)
        window.selectedTrackChanged.connect(self.refresh)
        window.analysisChanged.connect(self.refresh)
        window.closing.connect(self.shutdown)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(50)
        self.refresh()

    @property
    def runner(self):
        return self.backend.runner

    @runner.setter
    def runner(self, value):
        self.backend.runner = value

    @property
    def busy(self) -> bool:
        return self._future is not None or self._pending_probe

    def selectedModel(self) -> ImportedModel | None:
        session = self.window.analysisSession
        return next((m for m in session.project.imported_models if m.model_id == self.models.currentData()), None) if session else None

    def isVerified(self, model: ImportedModel | None = None) -> bool:
        """校验当前视频与所选模型/设备的轻量自检身份。"""
        model = model or self.selectedModel()
        session = self.window.analysisSession
        if model is None or session is None:
            return False
        video = next((v for v in session.project.videos if v.video_id == self.window.activeVideoId), None)
        return bool(video and verified_self_test(model, self.device.currentText(),
                                                video.video_id, session.video_path(video)))

    def _blocked(self):
        w = self.window
        return (self.busy or w.projectActions.busy or w.trackingActions.pending
                or w.frameSelectionActions.busy or w.reviewActions.busy)

    def _selected(self, *_args):
        model = self.selectedModel()
        self.bodyparts.clear()
        if model:
            self.bodyparts.addItems(model.bodyparts)
        if model and not self.busy:
            self._showModelStatus(model)
        self.refresh()

    def _showModelStatus(self, model):
        if self.isVerified(model):
            evidence = model.self_test
            self.status.setText(f"Self-test passed · actual {evidence['actual_device']} · frame {evidence.get('frame_index', '?')}. Next: generate a candidate trajectory.")
        else:
            self.status.setText("Selected model/environment/device needs an actual-frame self-test before generating a trajectory.")

    def _deviceChanged(self, *_args):
        model = self.selectedModel()
        if model is not None and not self.busy:
            self._showModelStatus(model)
        self.refresh()

    def selectFiles(self) -> None:
        if self._blocked():
            return
        paths = []
        for title, filter_ in (("Select DLC project config.yaml", "YAML (*.yaml *.yml)"),
                               ("Select model pytorch_config.yaml", "YAML (*.yaml *.yml)"),
                               ("Select teacher checkpoint", "PyTorch checkpoint (*.pt)")):
            path, _ = QFileDialog.getOpenFileName(self.window, title, "", filter_)
            if not path:
                return
            paths.append(Path(path))
        self.importFiles(tuple(paths))

    def importFiles(self, paths: tuple[Path, Path, Path]) -> None:
        session = self.window.analysisSession
        if self._blocked() or session is None or session.project_root is None:
            self.status.setText("Save the project before importing a teacher model.")
            return
        self._begin("import", session)
        self._future = self.executor.submit(self.backend.import_model, session.project_root, paths, self._cancel)
        self.status.setText("Copying teacher model into the project…")
        self.refresh()

    def _begin(self, kind, session):
        self._kind = kind
        self._context = (session, session.project_root, self.window.activeVideoId,
                         self.window.deliveryGeneration, self.models.currentData(), self.device.currentText())
        self._cancel = Event()
        self.window.setWorkspace("acquire")
        self.window.stopPlayback()
        self.window.batchAnnotationActions.pause()
        self.window.reviewActions.cancelCorrectMode()
        self.window.drawScaleButton.setChecked(False)
        self.window.setOriginButton.setChecked(False)
        self.window.videoView.set_calibration_mode(None)
        self.window.videoView.set_annotation_mode(False)

    def selfTest(self) -> None:
        w, model = self.window, self.selectedModel()
        session, frame = w.analysisSession, w.presented_frame_index
        if self._blocked() or not model or session is None or session.project_root is None or frame is None or w._has_pending_request:
            self.status.setText("Display an actual video frame before self-testing.")
            return
        video = next((v for v in session.project.videos if v.video_id == w.activeVideoId), None)
        path = session.video_path(video) if video else None
        if path is None:
            self.status.setText("Relink the video before self-testing.")
            return
        model = replace(model, self_test={})
        session.register_imported_model(model)
        self._begin("test", session)
        self._pending_probe = True
        self.status.setText("Saving revoked self-test authorization before testing…")
        def launch():
            self._pending_probe = False
            if (self._closed or self._cancel.is_set() or w.analysisSession is not session
                    or w.activeVideoId != video.video_id or w.deliveryGeneration != self._context[3]):
                self.status.setText("Model operation cancelled or project context changed; result not applied.")
                self.refresh()
                return
            self._future = self.executor.submit(self.backend.probe, self._cancel, session.project_root,
                                               model, path, video.video_id, frame, self.device.currentText())
            self.status.setText(f"Running teacher model on actual frame {frame}…")
            self.refresh()
        w.projectActions.autosave("teacher self-test authorization revoked", after=launch)
        self.refresh()

    def infer(self) -> None:
        model = self.selectedModel()
        if self._blocked() or model is None or not self.isVerified(model):
            return
        params = replace(self.window.trackingActions.panel.inferenceParameters(), device=self.device.currentText())
        self.window.trackingActions._start(params, imported_model_id=model.model_id,
                                          imported_bodypart=self.bodyparts.currentText())

    def cancel(self) -> None:
        if self.busy:
            self._cancel.set()
            self.status.setText("Cancelling; waiting for model operation to stop…")
            self.refresh()

    def _poll(self):
        if self._closed:
            return
        if self._pending_probe:
            if not self.window.projectActions.busy:
                self._pending_probe = False
                self.status.setText("Authorization save failed; self-test was not started. Save the project and retry.")
            self.refresh()
            return
        if self._future is None or not self._future.done():
            self.refresh()
            return
        if self.window.projectActions.busy:
            return  # 先完成现有保存，再登记模型并保存新元数据。
        future, self._future = self._future, None
        session, root, video_id, generation, model_id, device = self._context
        current = self.window.analysisSession
        matches = (current is not None and current.project_root == root
                   and current.project.project_id == session.project.project_id)
        if self._kind == "test":
            matches = (matches and current is session and self.window.activeVideoId == video_id
                       and self.window.deliveryGeneration == generation)
        elif matches:
            session = current  # 导入属于整个项目；视频切换后的 detached 会话也可接收。
        try:
            result = future.result()
            if self._cancel.is_set() or not matches:
                if self._kind == "import":
                    self.executor.submit(self.backend.discard, root, result)
                self.status.setText("Model operation cancelled or project context changed; result not applied.")
            elif self._kind == "import":
                session.register_imported_model(result)
                self.status.setText("Imported. Next: self-test on an actual displayed frame.")
                self.refresh()
                self.models.setCurrentIndex(self.models.findData(result.model_id))
                self.window.projectActions.autosave("teacher model imported")
            else:
                model = next(m for m in session.project.imported_models if m.model_id == model_id)
                if self.models.currentData() != model_id or self.device.currentText() != device:
                    raise ValueError("Selected model/device changed; repeat self-test")
                tested = replace(model, self_test=result)
                if not self.isVerified(tested):
                    raise ValueError("Self-test evidence no longer matches the current video; repeat self-test")
                session.register_imported_model(tested)
                self.status.setText(f"Self-test passed · actual {result['actual_device']} · frame {result['frame_index']}. Next: generate a candidate trajectory.")
                self.window.projectActions.autosave("teacher model actual-frame self-test")
        except CancelledError:
            self.status.setText("Model operation cancelled. Existing models and observations kept.")
        except Exception as error:
            self.status.setText(f"Model operation failed: {error}")
        self.refresh()

    def refresh(self, *_args) -> None:
        editable = self.window.canEditVideo()
        if editable != self._video_editable:
            self._video_editable = editable
            self.window._refreshCalibrationUI()
            self.window._refreshHistoryButtons()
        session = self.window.analysisSession
        models = session.project.imported_models if session else ()
        if [self.models.itemData(i) for i in range(self.models.count())] != [m.model_id for m in models]:
            selected = self.models.currentData()
            self.models.blockSignals(True)
            self.models.clear()
            for model in models:
                self.models.addItem(model.name, model.model_id)
            self.models.setCurrentIndex(max(0, self.models.findData(selected)))
            self.models.blockSignals(False)
            self._selected()
        blocked = self._blocked()
        saved = session is not None and session.project_root is not None
        model = self.selectedModel()
        self.importButton.setEnabled(saved and not blocked)
        self.fileAction.setEnabled(saved and not blocked)
        for widget in (self.models, self.bodyparts, self.device):
            widget.setEnabled(not blocked)
        self.testButton.setEnabled(bool(model) and not blocked and self.window.presented_frame_index is not None)
        self.inferButton.setEnabled(bool(model and self.isVerified(model))
                                   and not blocked and self.window.selectedTrackId is not None)
        self.cancelButton.setVisible(self.busy)
        self.cancelButton.setEnabled(self.busy and not self._cancel.is_set())
        self.window.projectActions.refresh()

    def shutdown(self) -> None:
        self._closed = True
        self.timer.stop()
        self._cancel.set()
        self.executor.shutdown(wait=True, cancel_futures=False)
