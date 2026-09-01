"""AI 训练/推理任务面板；只负责展示状态与发出用户操作信号。"""

from uuid import UUID

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.application.tracking_types import InferenceParams, TrainingParams


_RUN_ID_ROLE = Qt.ItemDataRole.UserRole
_UNKNOWN_PROGRESS = (0, 0)
_MAX_LOG_BLOCKS = 2000


class TaskPanel(QDockWidget):
    """底部可停靠的 AI 任务面板。

    面板不启动任务、不读取日志文件，也不修改项目；主窗口通过信号
    获取用户意图，并通过 ``setContext``、``setRuns`` 和 ``setActivity``
    推送当前快照。
    """

    trainRequested = Signal()
    inferRequested = Signal()
    cancelRequested = Signal()
    runSelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("AI tasks", parent)
        self.setObjectName("trackingTasks")
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        self.contextLabel = QLabel("No video selected · No track selected")
        self.contextLabel.setWordWrap(True)

        self.epochsSpinBox = QSpinBox()
        self.epochsSpinBox.setRange(1, 1_000_000)
        self.epochsSpinBox.setValue(50)
        self.batchSizeSpinBox = QSpinBox()
        self.batchSizeSpinBox.setRange(1, 1_000_000)
        self.batchSizeSpinBox.setValue(8)
        self.deviceComboBox = QComboBox()
        self.deviceComboBox.addItems(["auto", "cpu", "mps", "cuda"])

        trainForm = QFormLayout()
        trainForm.addRow("Epochs", self.epochsSpinBox)
        trainForm.addRow("Batch size", self.batchSizeSpinBox)
        trainForm.addRow("Device", self.deviceComboBox)
        self.trainButton = QPushButton("Start Training")
        trainLayout = QVBoxLayout()
        trainLayout.addLayout(trainForm)
        trainLayout.addWidget(self.trainButton)
        trainGroup = QGroupBox("Training")
        trainGroup.setLayout(trainLayout)
        self.trainReasonLabel = QLabel()
        self.trainReasonLabel.setWordWrap(True)
        self.trainReasonLabel.hide()

        self.confidenceSpinBox = QDoubleSpinBox()
        self.confidenceSpinBox.setRange(0.0, 1.0)
        self.confidenceSpinBox.setSingleStep(0.05)
        self.confidenceSpinBox.setDecimals(2)
        self.confidenceSpinBox.setValue(0.6)
        self.modelList = QListWidget()
        self.modelList.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.modelList.setMinimumHeight(52)
        self.modelList.setMaximumHeight(100)
        inferForm = QFormLayout()
        inferForm.addRow("Minimum confidence", self.confidenceSpinBox)
        inferForm.addRow("Device / batch", QLabel("same as training"))
        self.inferButton = QPushButton("Start Inference")
        inferLayout = QVBoxLayout()
        inferLayout.addLayout(inferForm)
        inferLayout.addWidget(self.modelList)
        inferLayout.addWidget(self.inferButton)
        inferGroup = QGroupBox("Inference model")
        inferGroup.setLayout(inferLayout)
        self.inferReasonLabel = QLabel()
        self.inferReasonLabel.setWordWrap(True)
        self.inferReasonLabel.hide()

        self.cancelButton = QPushButton("Cancel")
        self.cancelButton.setEnabled(False)
        self.stageLabel = QLabel("Idle")
        self.progressBar = QProgressBar()
        self.progressBar.setRange(0, 1)
        self.progressBar.setValue(0)
        self.metricsLabel = QLabel()
        self.metricsLabel.setWordWrap(True)

        self.historyList = QListWidget()
        self.historyList.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.historyList.setMinimumHeight(62)
        self.historyList.setMaximumHeight(100)
        self.logText = QPlainTextEdit()
        self.logText.setReadOnly(True)
        self.logText.setMinimumHeight(75)
        self.logText.document().setMaximumBlockCount(_MAX_LOG_BLOCKS)
        self.logText.setPlaceholderText("Select a task to view its log")

        activityLayout = QVBoxLayout()
        activityHeader = QHBoxLayout()
        activityHeader.addWidget(QLabel("Activity"))
        activityHeader.addWidget(self.stageLabel, 1)
        activityHeader.addWidget(self.cancelButton)
        activityLayout.addLayout(activityHeader)
        activityLayout.addWidget(self.progressBar)
        activityLayout.addWidget(self.metricsLabel)

        historyLayout = QVBoxLayout()
        historyLayout.addWidget(QLabel("Task history"))
        historyLayout.addWidget(self.historyList)
        historyLayout.addWidget(self.logText, 1)

        left = QVBoxLayout()
        left.addWidget(trainGroup)
        left.addWidget(self.trainReasonLabel)
        middle = QVBoxLayout()
        middle.addWidget(inferGroup)
        middle.addWidget(self.inferReasonLabel)
        columns = QHBoxLayout()
        columns.addLayout(left, 1)
        columns.addLayout(middle, 1)
        columns.addLayout(historyLayout, 2)
        self.detailsLabel = QLabel("Select a task to view its result details.")
        self.detailsLabel.setWordWrap(True)
        contentLayout = QVBoxLayout()
        contentLayout.addWidget(self.contextLabel)
        contentLayout.addLayout(columns)
        contentLayout.addLayout(activityLayout)
        contentLayout.addWidget(self.detailsLabel)
        contentLayout.addWidget(QLabel("Manual: circle · AI: hollow diamond · Existing points are kept"))
        content = QWidget()
        content.setLayout(contentLayout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.setWidget(scroll)

        self.trainButton.clicked.connect(lambda: self.trainRequested.emit())
        self.inferButton.clicked.connect(lambda: self.inferRequested.emit())
        self.cancelButton.clicked.connect(lambda: self.cancelRequested.emit())
        self.historyList.currentItemChanged.connect(self._onHistorySelected)

    def trainingParameters(self) -> TrainingParams:
        """返回当前训练控件的不可变参数快照。"""

        return TrainingParams(
            epochs=self.epochsSpinBox.value(),
            batch_size=self.batchSizeSpinBox.value(),
            device=self.deviceComboBox.currentText(),
        )

    def inferenceParameters(self) -> InferenceParams:
        """返回当前推理控件的参数；设备和 batch 与训练设置保持一致。"""

        return InferenceParams(
            min_confidence=self.confidenceSpinBox.value(),
            device=self.deviceComboBox.currentText(),
            batch_size=self.batchSizeSpinBox.value(),
        )

    def selectedTrainingRunId(self) -> UUID | None:
        """返回模型列表当前选中的训练运行 ID。"""

        item = self.modelList.currentItem()
        return self._itemRunId(item)

    def setContext(
        self,
        video_name: str,
        track_name: str,
        train_reason: str | None,
        infer_reason: str | None,
        busy: bool,
    ) -> None:
        """更新当前目标及训练/推理按钮的可用状态和禁用原因。"""

        video = video_name.strip() or "No video selected"
        track = track_name.strip() or "No track selected"
        self.contextLabel.setText(f"Video: {video} · Track: {track}")
        self._setReason(self.trainButton, self.trainReasonLabel, train_reason, busy)
        self._setReason(self.inferButton, self.inferReasonLabel, infer_reason, busy)
        self.cancelButton.setEnabled(busy)

    def setRuns(
        self,
        runs: tuple[TrackingRun, ...],
        track_id: UUID | None,
    ) -> None:
        """更新当前 Track 的可用训练模型和项目级任务历史。"""

        selected_model_id = self.selectedTrainingRunId()
        with QSignalBlocker(self.modelList):
            self.modelList.clear()
            for run in runs:
                if (
                    track_id is None
                    or run.track_id != track_id
                    or run.task_type != "train"
                    or run.status != "completed"
                    or not run.model_snapshot
                ):
                    continue
                item = QListWidgetItem(self._runLabel(run))
                item.setData(_RUN_ID_ROLE, run.run_id)
                item.setToolTip(self._runDetails(run))
                self.modelList.addItem(item)
            for index in range(self.modelList.count()):
                item = self.modelList.item(index)
                if item.data(_RUN_ID_ROLE) == selected_model_id:
                    self.modelList.setCurrentItem(item)
                    break

        if self.modelList.currentItem() is None and self.modelList.count():
            self.modelList.setCurrentRow(self.modelList.count() - 1)
        current_history = self._itemRunId(self.historyList.currentItem())
        with QSignalBlocker(self.historyList):
            self.historyList.clear()
            for run in runs:
                item = QListWidgetItem(self._runLabel(run))
                item.setData(_RUN_ID_ROLE, run.run_id)
                item.setToolTip(self._runDetails(run))
                self.historyList.addItem(item)
                if run.run_id == current_history:
                    self.historyList.setCurrentItem(item)

    def setActivity(
        self,
        stage: str,
        step: int | None = None,
        total: int | None = None,
        loss: float | None = None,
        learning_rate: float | None = None,
    ) -> None:
        """显示任务阶段、可选进度及训练指标；未知分母使用忙碌条。"""

        self.stageLabel.setText(stage.strip() or "Working")
        if step is not None and total is not None and total > 0:
            self.progressBar.setRange(0, total)
            self.progressBar.setValue(max(0, min(step, total)))
        elif stage in {"Idle", "Completed", "Cancelled"} or stage.startswith(("Failed", "Cannot start")):
            self.progressBar.setRange(0, 1)
            self.progressBar.setValue(1 if stage == "Completed" else 0)
        else:
            self.progressBar.setRange(*_UNKNOWN_PROGRESS)
            self.progressBar.setValue(0)

        metrics = []
        if loss is not None:
            metrics.append(f"loss={loss:.6g}")
        if learning_rate is not None:
            metrics.append(f"lr={learning_rate:.6g}")
        self.metricsLabel.setText(" · ".join(metrics))

    def setRunDetails(self, run: TrackingRun) -> None:
        """显示结果摘要，不把训练 loss 当成定位精度。"""
        extras = run.extra_fields
        lines = [f"{run.task_type} · {run.status} · device={extras.get('device', run.config.get('device', 'unknown'))}"]
        counts = extras.get("import_summary")
        if isinstance(counts, dict):
            lines.append("Imported {inserted}, kept {skipped}, low confidence {low_confidence_count}, missing {missing_count}".format(
                **{key: counts.get(key, 0) for key in ("inserted", "skipped", "low_confidence_count", "missing_count")}))
        evaluation = extras.get("evaluation")
        if isinstance(evaluation, dict):
            lines.append(f"Evaluation: {evaluation.get('status', 'unknown')}")
            for split in ("train", "test"):
                result = evaluation.get(split)
                if isinstance(result, dict):
                    metrics = ", ".join(f"{name}={value if value is not None else 'N/A'} {result.get('units', {}).get(name, '')}"
                                        for name, value in result.get("metrics", {}).items())
                    lines.append(f"{split} (n={result.get('sample_count', 'unknown')}): {metrics}")
            if evaluation.get("reason"):
                lines.append(str(evaluation["reason"]))
        if run.error_message:
            lines.append(run.error_message)
        self.detailsLabel.setText("\n".join(lines))

    def appendLog(self, text: str) -> None:
        """追加日志文本；文档最多保留最近 2000 个 block。"""

        self.logText.appendPlainText(text)

    def setLog(self, text: str) -> None:
        """替换当前日志文本，并保持 2000 block 上限。"""

        self.logText.setPlainText(text)

    def _onHistorySelected(
        self,
        item: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        run_id = self._itemRunId(item)
        if run_id is not None:
            self.runSelected.emit(run_id)

    def _setReason(
        self,
        button: QPushButton,
        label: QLabel,
        reason: str | None,
        busy: bool,
    ) -> None:
        if reason is not None and reason.strip():
            message = reason.strip()
        elif busy:
            message = "Another AI task is running"
        else:
            message = ""
        button.setEnabled(not busy and not message)
        label.setText(message)
        label.setVisible(bool(message))
        button.setToolTip(message)

    @staticmethod
    def _itemRunId(item: QListWidgetItem | None) -> UUID | None:
        if item is None:
            return None
        value = item.data(_RUN_ID_ROLE)
        if isinstance(value, UUID):
            return value
        return None

    @staticmethod
    def _runLabel(run: TrackingRun) -> str:
        label = f"{run.task_type} · {run.status} · {str(run.run_id)[:8]}"
        if run.model_snapshot:
            label += f" · {run.model_snapshot.replace(chr(92), chr(47)).rsplit(chr(47), 1)[-1]}"
        return label

    @staticmethod
    def _runDetails(run: TrackingRun) -> str:
        details = [
            f"run_id={run.run_id}",
            f"task={run.task_type}",
            f"status={run.status}",
        ]
        if run.model_snapshot:
            details.append(f"model={run.model_snapshot}")
        if run.extra_fields.get("device"):
            details.append(f"device={run.extra_fields['device']}")
        for key in ("import_summary", "evaluation"):
            if key in run.extra_fields:
                details.append(f"{key}={run.extra_fields[key]}")
        if run.error_message:
            details.append(f"error={run.error_message}")
        return "\n".join(details)
