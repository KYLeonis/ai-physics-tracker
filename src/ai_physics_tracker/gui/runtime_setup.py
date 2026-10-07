"""GUI 层：AI 环境安装/修复与诊断，Qt timer 轮询后台快照，不跨线程 emit 对象。"""

from __future__ import annotations

from concurrent.futures import CancelledError, ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import platform
from queue import Empty, SimpleQueue
import shutil
import time
from typing import TYPE_CHECKING
import zipfile

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from ai_physics_tracker.gui import launch_context
from ai_physics_tracker.application.runtime_setup import (
    RuntimeCancellation, RuntimeProgress, install_runtime, load_profiles, profile_supported, verify_runtime,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ai_physics_tracker.gui.main_window import MainWindow


class RuntimeSetupDialog(QDialog):
    def __init__(self, actions: RuntimeSetupActions) -> None:
        super().__init__(actions.window)
        self.actions = actions
        self.setWindowTitle("AI environment")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        self.statusLabel = QLabel()
        self.statusLabel.setWordWrap(True)
        layout.addWidget(self.statusLabel)
        explanation = QLabel(
            "Install a private Python + PyTorch + DeepLabCut environment. Your projects and any existing "
            "Python installations are preserved. First training may download pretrained model weights."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.profileCombo = QComboBox()
        for profile in actions.profiles:
            size = (profile["python"]["size"] + sum(p["size"] for p in profile["packages"])) / 1024**3
            self.profileCombo.addItem(f"{profile['label']} · download {size:.2f} GiB", profile)
        if platform.system() == "Windows" and shutil.which("nvidia-smi") and self.profileCombo.count() > 1:
            self.profileCombo.setCurrentIndex(1)
        layout.addWidget(self.profileCombo)
        self.phaseLabel = QLabel("Ready to install")
        self.phaseLabel.setWordWrap(True)
        layout.addWidget(self.phaseLabel)
        self.progressBar = QProgressBar()
        layout.addWidget(self.progressBar)
        self.logView = QPlainTextEdit()
        self.logView.setReadOnly(True)
        self.logView.setMaximumBlockCount(250)
        layout.addWidget(self.logView, 1)
        row = QHBoxLayout()
        self.installButton = QPushButton("Install and use")
        self.repairButton = QPushButton("Repair / reinstall")
        self.checkButton = QPushButton("Check current environment")
        self.cancelButton = QPushButton("Cancel")
        for button in (self.installButton, self.repairButton, self.checkButton, self.cancelButton):
            row.addWidget(button)
        layout.addLayout(row)
        self.exportButton = QPushButton("Export diagnostics…")
        layout.addWidget(self.exportButton)
        licenses = QLabel("AI components retain their own licenses: DeepLabCut LGPL-3.0-or-later; PyTorch BSD-3-Clause; "
                          "Python PSF. Pinned package/source details accompany this application.")
        licenses.setWordWrap(True)
        layout.addWidget(licenses)
        licensesButton = QPushButton("Third-party licenses and source details…")
        licensesButton.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(actions.manifest.parent / "NOTICE.md"))))
        layout.addWidget(licensesButton)
        self.installButton.clicked.connect(actions.install)
        self.repairButton.clicked.connect(actions.install)
        self.checkButton.clicked.connect(actions.check)
        self.cancelButton.clicked.connect(actions.cancel)
        self.exportButton.clicked.connect(actions.exportDiagnostics)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.actions.busy:
            self.actions.cancel()
            self.phaseLabel.setText("Cancelling setup; wait for downloads/processes to stop before closing.")
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        # Esc 与窗口关闭使用同一取消协议，不让后台安装在隐藏窗口里继续发布。
        if self.actions.busy:
            self.actions.cancel()
            return
        super().reject()


class RuntimeSetupActions(QObject):
    def __init__(self, window: MainWindow, *, data_root: Path | None = None, manifest: Path | None = None) -> None:
        super().__init__(window)
        self.window = window
        self.data_root = data_root or launch_context.app_data_dir()
        base = launch_context.resource_root() or Path(__file__).resolve().parents[3] / "resources"
        self.manifest = manifest or base / "runtime/manifest.json"
        self.profiles = ()
        self.manifest_error = ""
        try:
            self.profiles = tuple(p for p in load_profiles(self.manifest) if profile_supported(p))
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            self.manifest_error = f"AI setup manifest unavailable: {error}"
        self.dialog = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="runtime-setup")
        self._future = None
        self._cancel = RuntimeCancellation()
        self._progress = SimpleQueue()
        self._started_s = 0.0
        self._installing = False
        self._last_progress = None
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._poll)
        action = QAction("AI environment…", window)
        action.triggered.connect(self.open)
        window.menuBar().addMenu("Settings").addAction(action)

    @property
    def busy(self) -> bool:
        return self._future is not None

    def open(self) -> None:
        if self.dialog is None:
            self.dialog = RuntimeSetupDialog(self)
        self.refresh()
        self.window.trackingActions.refresh()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _aiBusy(self) -> bool:
        return bool(self.window.trackingActions.pending or self.window.modelActions.busy or
                    self.window.experimentInferenceActions.busy or self.window.projectActions.busy)

    def refresh(self) -> None:
        if self.dialog is None:
            return
        python = launch_context.runtime_python()
        status = f"Current AI interpreter: {python}" if python else "AI environment is not installed. Choose Install and use."
        override = os.environ.get("AI_PHYSICS_RUNTIME_PYTHON")
        if override:
            status += "\nAn advanced interpreter override is active; Install and use replaces it for this session."
        self.dialog.statusLabel.setText(status)
        blocked = self.busy or self._aiBusy()
        self.dialog.profileCombo.setEnabled(not blocked)
        self.dialog.installButton.setEnabled(bool(self.profiles) and not blocked)
        self.dialog.repairButton.setEnabled(bool(self.profiles) and bool(python) and not blocked)
        self.dialog.checkButton.setEnabled(bool(python) and not blocked)
        self.dialog.cancelButton.setEnabled(self.busy and not self._cancel.is_set())
        self.dialog.exportButton.setEnabled(not self.busy)
        if not self.profiles and not self.busy:
            self.dialog.phaseLabel.setText(self.manifest_error or "No compatible AI runtime profile. Apple Silicon requires macOS 14 or newer.")

    def install(self) -> None:
        if self.busy or self._aiBusy() or not self.profiles:
            self.open()
            return
        profile = self.dialog.profileCombo.currentData()
        self._begin(installing=True)
        self._future = self._executor.submit(install_runtime, self.data_root, profile,
                                             launch_context.worker_package_root(), self._cancel, self._progress.put,
                                             opencv_wheels=(launch_context.resource_root() / "opencv-lgpl"
                                                            if launch_context.is_frozen() and profile["system"] == "Darwin"
                                                            else None))
        self.refresh()
        self.window.trackingActions.refresh()

    def check(self) -> None:
        python = launch_context.runtime_python()
        if self.busy or self._aiBusy() or python is None:
            return
        self._begin(installing=False)
        job = self.data_root / "runtimes/checks" / str(time.time_ns())
        self._future = self._executor.submit(verify_runtime, Path(python), job,
                                             launch_context.worker_package_root(), self._cancel)
        self.refresh()
        self.window.trackingActions.refresh()

    def _begin(self, *, installing: bool) -> None:
        self._installing = installing
        self._cancel = RuntimeCancellation()
        self._progress = SimpleQueue()
        self._started_s = time.monotonic()
        self._last_progress = None
        self.dialog.logView.clear()
        self.dialog.progressBar.setRange(0, 0)
        self.dialog.phaseLabel.setText("Starting setup…" if installing else "Checking Python, Torch and DeepLabCut…")
        self._timer.start()

    def cancel(self) -> None:
        self._cancel.set()
        if self.dialog:
            self.dialog.phaseLabel.setText("Environment verified; finishing activation…" if self._cancel.committed else
                                           "Cancelling; preserving the current environment…")
            self.refresh()

    def _poll(self) -> None:
        latest = None
        while True:
            try:
                latest = self._progress.get_nowait()
            except Empty:
                break
        if latest is not None and not self._cancel.is_set():
            self._last_progress = latest
            if latest.total:
                self.dialog.progressBar.setRange(0, 1000)
                self.dialog.progressBar.setValue(round(1000 * latest.completed / latest.total))
            else:
                self.dialog.progressBar.setRange(0, 0)
            self.dialog.logView.appendPlainText(f"{latest.stage}: {latest.detail}")
        if self._last_progress is not None and not self._cancel.is_set():
            p = self._last_progress
            self.dialog.phaseLabel.setText(f"{p.stage}: {p.detail} · elapsed {time.monotonic()-self._started_s:.0f} s")
        if self._future is None or not self._future.done():
            return
        future = self._future
        self._future = None
        self._timer.stop()
        self.dialog.progressBar.setRange(0, 100)
        self.dialog.progressBar.setValue(0)
        try:
            result = future.result()
        except CancelledError:
            self.dialog.phaseLabel.setText("Setup cancelled. The previous AI environment is unchanged. You can retry.")
        except Exception as error:
            logger.exception("AI environment setup failed")
            self.dialog.phaseLabel.setText(f"Setup failed: {error}\nRetry installation or export diagnostics.")
            self.dialog.logView.appendPlainText(str(error))
        else:
            if self._installing:
                os.environ.pop("AI_PHYSICS_RUNTIME_PYTHON", None)
                python = str(result)
                self.window.modelActions.set_runtime_python(python)
                self.window.experimentInferenceActions.set_runtime_python(python)
                self.dialog.phaseLabel.setText("AI environment installed and verified. Training and inference are now available.")
            else:
                versions = result["versions"]
                self.dialog.phaseLabel.setText(f"Verified: Torch {versions['torch']}, DLC {versions['deeplabcut']}; "
                                               f"actual device: {result['actual_device']}")
            self.dialog.progressBar.setValue(100)
        self.refresh()
        self.window.trackingActions.refresh()

    def exportDiagnostics(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self.dialog, "Export AI diagnostics", "ai-runtime-diagnostics.zip", "ZIP (*.zip)")
        if not target:
            return
        try:
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("summary.json", json.dumps({"platform": platform.platform(), "machine": platform.machine(),
                                      "runtime_python": launch_context.runtime_python(), "manifest_error": self.manifest_error}, indent=2))
                if self.manifest.is_file():
                    archive.write(self.manifest, "manifest.json")
                # 只收环境诊断文件；绝不把解释器、权重、视频或工程一并打包。
                files = [self.data_root / "logs/app.log", self.data_root / "runtimes/active.txt"]
                for root in (self.data_root / "runtimes/installs", self.data_root / "runtimes/checks"):
                    if root.is_dir():
                        recent = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()),
                                        key=lambda p: p.stat().st_mtime, reverse=True)[:5]
                        for folder in recent:
                            for pattern in ("install.log", "install-state.json", "environment/runtime-ready.json",
                                            "worker.log", "result.json", "request.json", "selftest/*.json", "selftest/worker.log"):
                                files.extend(folder.glob(pattern))
                for file in files:
                    if file.is_file() and not file.is_symlink():
                        # ponytail: 每个诊断文件只收尾部 1 MiB，避免大型训练日志阻塞 GUI。
                        with file.open("rb") as source:
                            source.seek(max(0, file.stat().st_size - 1024**2))
                            archive.writestr(str(file.relative_to(self.data_root)), source.read())
            self.dialog.phaseLabel.setText(f"Diagnostics saved: {target}")
        except OSError as error:
            self.dialog.phaseLabel.setText(f"Could not export diagnostics: {error}")

    def shutdown(self) -> None:
        self._cancel.set()
        self._timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
