"""AI 训练/推理任务面板；只负责展示状态与发出用户操作信号。"""

from typing import Any
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

from ai_physics_tracker.application.difficult_frames import MiningParams
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.application.tracking_types import (
    InferenceParams, TrainingParams, FrameSelectionResult,
)


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
    suggestFramesRequested = Signal(int, str)   # (n_frames, algorithm)
    suggestCancelRequested = Signal()           # F4
    suggestedFrameJumped = Signal(int)           # 用户点击建议帧，发出帧号
    mineDifficultRequested = Signal(object, object)  # (run_id, MiningParams)
    mineCancelRequested = Signal()
    reviewNextRequested = Signal()
    reviewPrevRequested = Signal()
    reviewAcceptRequested = Signal()
    reviewSkipRequested = Signal()
    reviewCorrectRequested = Signal()
    reviewCandidateJumpRequested = Signal(int)
    deleteManualPointRequested = Signal()
    activateRunRequested = Signal(object)
    replaceRunRequested = Signal(object)
    clearActivationRequested = Signal()
    manageValidationRequested = Signal()

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

        # Phase 5.5：Restart/Resume 模式与 Advisor 摘要（ADR-0015）
        self.trainingModeComboBox = QComboBox()
        self.trainingModeComboBox.addItems(["Restart", "Resume (fine-tune)"])
        self.trainingModeComboBox.setToolTip(
            "Resume continues from the selected model's snapshot; "
            "'Epochs' then means additional epochs for this run.")
        self.advisorLabel = QLabel("Advisor: select a track with training history")
        self.advisorLabel.setWordWrap(True)
        self.advisorApplyButton = QPushButton("Apply Suggestion")
        self.advisorApplyButton.setToolTip(
            "Fill mode / epochs / batch size from the suggestion. Never starts training.")
        self.advisorApplyButton.setEnabled(False)
        self.advisorApplyButton.clicked.connect(self._onApplySuggestionClicked)

        trainForm = QFormLayout()
        trainForm.addRow("Mode", self.trainingModeComboBox)
        trainForm.addRow("Epochs this run", self.epochsSpinBox)
        trainForm.addRow("Batch size", self.batchSizeSpinBox)
        trainForm.addRow("Device", self.deviceComboBox)
        self.trainButton = QPushButton("Start Training")
        trainLayout = QVBoxLayout()
        trainLayout.addLayout(trainForm)
        trainLayout.addWidget(self.advisorLabel)
        trainLayout.addWidget(self.advisorApplyButton)
        trainLayout.addWidget(self.trainButton)
        trainGroup = QGroupBox("Training")
        trainGroup.setLayout(trainLayout)
        self.trainReasonLabel = QLabel()
        self.trainReasonLabel.setWordWrap(True)
        self.trainReasonLabel.hide()

        # --- 建议帧（Phase 5.1）---
        self.nFramesSpinBox = QSpinBox()
        self.nFramesSpinBox.setRange(1, 200)
        self.nFramesSpinBox.setValue(10)
        self.algorithmComboBox = QComboBox()
        self.algorithmComboBox.addItem("K-means", "kmeans")
        self.algorithmComboBox.addItem("Uniform", "uniform")
        self.suggestButton = QPushButton("Suggest Frames")
        self.suggestCancelButton = QPushButton("Cancel")
        self.suggestCancelButton.setEnabled(False)
        self.suggestCancelButton.hide()
        self.suggestStatusLabel = QLabel("")
        self.suggestStatusLabel.setWordWrap(True)
        self.suggestStatusLabel.hide()
        self.suggestedFramesList = QListWidget()
        self.suggestedFramesList.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.suggestedFramesList.setMinimumHeight(52)
        self.suggestedFramesList.setMaximumHeight(120)
        self.suggestedFramesList.setToolTip(
            "Double-click a frame to jump to it. Annotate it manually—suggestions do not create labels."
        )
        suggestForm = QFormLayout()
        suggestForm.addRow("Frames to suggest", self.nFramesSpinBox)
        suggestForm.addRow("Algorithm", self.algorithmComboBox)
        suggestLayout = QVBoxLayout()
        suggestLayout.addLayout(suggestForm)
        suggestButtonRow = QHBoxLayout()
        suggestButtonRow.addWidget(self.suggestButton, 1)
        suggestButtonRow.addWidget(self.suggestCancelButton)
        suggestLayout.addLayout(suggestButtonRow)
        suggestLayout.addWidget(self.suggestStatusLabel)
        suggestLayout.addWidget(self.suggestedFramesList)
        suggestGroup = QGroupBox("Suggest Representative Frames")
        suggestGroup.setLayout(suggestLayout)

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

        # --- 建议帧审核与困难帧挖掘（Phase 5.2/5.3）---
        self.mineTopNSpinBox = QSpinBox()
        self.mineTopNSpinBox.setRange(1, 100)
        self.mineTopNSpinBox.setValue(10)
        self.mineMinGapSpinBox = QDoubleSpinBox()
        self.mineMinGapSpinBox.setRange(0.05, 5.0)
        self.mineMinGapSpinBox.setSingleStep(0.05)
        self.mineMinGapSpinBox.setValue(0.25)
        self.mineButton = QPushButton("Mine Difficult Frames")
        self.mineCancelButton = QPushButton("Cancel Mining")
        self.mineCancelButton.setEnabled(False)
        self.mineCancelButton.hide()
        self.mineStatusLabel = QLabel("")
        self.mineStatusLabel.setWordWrap(True)
        self.mineStatusLabel.hide()
        self.mineReasonLabel = QLabel("")
        self.mineReasonLabel.setWordWrap(True)
        self.mineReasonLabel.hide()

        mineForm = QFormLayout()
        mineForm.addRow("Top candidates", self.mineTopNSpinBox)
        mineForm.addRow("Min gap (s)", self.mineMinGapSpinBox)

        mineButtonRow = QHBoxLayout()
        mineButtonRow.addWidget(self.mineButton, 1)
        mineButtonRow.addWidget(self.mineCancelButton)

        self.reviewProgressLabel = QLabel("No active review batch")
        self.candidateDetailsLabel = QLabel("Select a completed infer run to mine or review.")
        self.candidateDetailsLabel.setWordWrap(True)

        self.reviewPrevButton = QPushButton("◀ Prev")
        self.reviewNextButton = QPushButton("Next ▶")
        self.reviewPrevButton.setEnabled(False)
        self.reviewNextButton.setEnabled(False)
        navRow = QHBoxLayout()
        navRow.addWidget(self.reviewPrevButton)
        navRow.addWidget(self.reviewNextButton)

        self.reviewAcceptButton = QPushButton("Accept (A)")
        self.reviewSkipButton = QPushButton("Skip (S)")
        self.reviewCorrectButton = QPushButton("Correct (C)")
        self.deleteManualPointButton = QPushButton("Delete Manual")
        self.reviewAcceptButton.setEnabled(False)
        self.reviewSkipButton.setEnabled(False)
        self.reviewCorrectButton.setEnabled(False)
        self.deleteManualPointButton.setEnabled(False)
        self.deleteManualPointButton.setToolTip(
            "Delete active manual point on current track at current frame (Undoable before save; non-recoverable after save)"
        )
        actionRow = QHBoxLayout()
        actionRow.addWidget(self.reviewAcceptButton)
        actionRow.addWidget(self.reviewSkipButton)
        actionRow.addWidget(self.reviewCorrectButton)
        actionRow.addWidget(self.deleteManualPointButton)

        self.reviewCandidatesList = QListWidget()
        self.reviewCandidatesList.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.reviewCandidatesList.setMinimumHeight(52)
        self.reviewCandidatesList.setMaximumHeight(100)
        self.reviewCandidatesList.setToolTip("Double-click a candidate to jump to its frame.")

        reviewLayout = QVBoxLayout()
        reviewLayout.addLayout(mineForm)
        reviewLayout.addLayout(mineButtonRow)
        reviewLayout.addWidget(self.mineReasonLabel)
        reviewLayout.addWidget(self.mineStatusLabel)
        reviewLayout.addWidget(self.reviewProgressLabel)
        reviewLayout.addWidget(self.candidateDetailsLabel)
        reviewLayout.addLayout(navRow)
        reviewLayout.addLayout(actionRow)
        reviewLayout.addWidget(self.reviewCandidatesList)

        reviewGroup = QGroupBox("Difficult Frames Review")
        reviewGroup.setLayout(reviewLayout)

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

        self._active_status: str = "none"
        self._active_run_id: UUID | None = None
        self._current_track_id: UUID | None = None
        self._busy: bool = False
        self._latest_advisor = None
        self._project_busy: bool = False
        self._ref_state: Any | None = None
        self._runs_by_id: dict[UUID, TrackingRun] = {}
        self._active_run_ids_by_track: dict[UUID, UUID] = {}

        self.activeRunLabel = QLabel("Active AI: None")
        self.activeValidationLabel = QLabel("Validation: None")
        self.activeValidationLabel.setWordWrap(True)

        activationActionRow = QHBoxLayout()
        self.activateButton = QPushButton("Activate")
        self.activateButton.setEnabled(False)
        self.replaceButton = QPushButton("Replace Active")
        self.replaceButton.setEnabled(False)
        self.clearActivationButton = QPushButton("Clear AI")
        self.clearActivationButton.setEnabled(False)
        self.manageValidationButton = QPushButton("Validation...")

        activationActionRow.addWidget(self.activateButton)
        activationActionRow.addWidget(self.replaceButton)
        activationActionRow.addWidget(self.clearActivationButton)
        activationActionRow.addWidget(self.manageValidationButton)

        self.activateButton.clicked.connect(self._onActivateClicked)
        self.replaceButton.clicked.connect(self._onReplaceClicked)
        self.clearActivationButton.clicked.connect(self.clearActivationRequested)
        self.manageValidationButton.clicked.connect(self.manageValidationRequested)

        historyLayout = QVBoxLayout()
        historyLayout.addWidget(QLabel("Task history & activation"))
        historyLayout.addWidget(self.activeRunLabel)
        historyLayout.addWidget(self.activeValidationLabel)
        historyLayout.addLayout(activationActionRow)
        historyLayout.addWidget(self.historyList)
        historyLayout.addWidget(self.logText, 1)

        left = QVBoxLayout()
        left.addWidget(suggestGroup)
        left.addWidget(trainGroup)
        left.addWidget(self.trainReasonLabel)
        middle = QVBoxLayout()
        middle.addWidget(inferGroup)
        middle.addWidget(self.inferReasonLabel)
        middle.addWidget(reviewGroup)
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
        self.suggestButton.clicked.connect(self._onSuggestClicked)
        self.suggestCancelButton.clicked.connect(lambda: self.suggestCancelRequested.emit())
        self.suggestedFramesList.itemDoubleClicked.connect(self._onSuggestedFrameDoubleClicked)

        self.mineButton.clicked.connect(self._onMineClicked)
        self.mineCancelButton.clicked.connect(lambda: self.mineCancelRequested.emit())
        self.reviewPrevButton.clicked.connect(lambda: self.reviewPrevRequested.emit())
        self.reviewNextButton.clicked.connect(lambda: self.reviewNextRequested.emit())
        self.reviewAcceptButton.clicked.connect(lambda: self.reviewAcceptRequested.emit())
        self.reviewSkipButton.clicked.connect(lambda: self.reviewSkipRequested.emit())
        self.reviewCorrectButton.clicked.connect(lambda: self.reviewCorrectRequested.emit())
        self.deleteManualPointButton.clicked.connect(lambda: self.deleteManualPointRequested.emit())
        self.reviewCandidatesList.itemDoubleClicked.connect(self._onReviewCandidateDoubleClicked)

    def trainingMode(self) -> str:
        """返回当前选择的训练模式："restart" 或 "resume"。"""

        return "resume" if self.trainingModeComboBox.currentIndex() == 1 else "restart"

    def setTrainingMode(self, mode: str) -> None:
        """供 Apply Suggestion 填入模式。"""

        self.trainingModeComboBox.setCurrentIndex(1 if mode == "resume" else 0)

    def setAdvisorSummary(self, recommendation) -> None:
        """展示 Advisor 单一建议摘要与证据；None 表示无可给建议。"""

        self._latest_advisor = recommendation
        if recommendation is None:
            self.advisorLabel.setText("Advisor: select a track with training history")
            self.advisorApplyButton.setEnabled(False)
            return
        params = []
        if recommendation.epochs is not None:
            params.append(f"epochs={recommendation.epochs}")
        if recommendation.batch_size is not None:
            params.append(f"batch={recommendation.batch_size}")
        if recommendation.label_count is not None:
            params.append(f"label {recommendation.label_count} more frame(s)")
        summary = f"Advisor: {recommendation.action}"
        if params:
            summary += f" ({', '.join(params)})"
        if recommendation.evidence:
            summary += "\n· " + "\n· ".join(recommendation.evidence)
        if recommendation.limits:
            summary += "\nLimits: " + " ".join(recommendation.limits)
        self.advisorLabel.setText(summary)
        fillable = recommendation.action in {"restart", "resume"} and (
            recommendation.epochs is not None or recommendation.batch_size is not None)
        self.advisorApplyButton.setEnabled(fillable)

    def _onApplySuggestionClicked(self) -> None:
        """Apply Suggestion 只填表（mode/epochs/batch），绝不自动启动训练。"""

        rec = self._latest_advisor
        if rec is None:
            return
        if rec.training_mode:
            self.setTrainingMode(rec.training_mode)
        if rec.epochs is not None:
            self.epochsSpinBox.setValue(rec.epochs)
        if rec.batch_size is not None:
            self.batchSizeSpinBox.setValue(rec.batch_size)

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
        project_busy: bool = False,
    ) -> None:
        """更新当前目标及训练/推理按钮的可用状态和禁用原因。

        project_busy 表示项目级操作（含静默自动保存）进行中：激活/替换/清除
        按钮随之禁用，避免"可点击但被静默忽略"（review F-3）。
        """

        video = video_name.strip() or "No video selected"
        track = track_name.strip() or "No track selected"
        self.contextLabel.setText(f"Video: {video} · Track: {track}")
        self._busy = busy
        self._project_busy = project_busy
        self._setReason(self.trainButton, self.trainReasonLabel, train_reason, busy)
        self._setReason(self.inferButton, self.inferReasonLabel, infer_reason, busy)
        self.cancelButton.setEnabled(busy)
        self._updateActivationButtonStates()

    def setRuns(
        self,
        runs: tuple[TrackingRun, ...],
        track_id: UUID | None,
        active_run_ids_by_track: dict[UUID, UUID] | None = None,
    ) -> None:
        """更新当前 Track 的可用训练模型和项目级任务历史。

        active_run_ids_by_track 为各 Track 的 active infer run 映射，用于在
        项目级 historyList 中正确标注其他 Track 的 Active 结果（review F-4）。
        """
        if active_run_ids_by_track is not None:
            self._active_run_ids_by_track = active_run_ids_by_track
        self._current_track_id = track_id
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
        # 切到无训练历史的 track 时复位 Resume 模式，避免点击 Start 才报错（review #6）
        if not self.modelList.count() and self.trainingMode() == "resume":
            self.setTrainingMode("restart")
        current_history = self._itemRunId(self.historyList.currentItem())
        self._runs_by_id = {run.run_id: run for run in runs}
        with QSignalBlocker(self.historyList):
            self.historyList.clear()
            for run in runs:
                item = QListWidgetItem(self._runLabel(run))
                item.setData(_RUN_ID_ROLE, run.run_id)
                item.setToolTip(self._runDetails(run))
                self.historyList.addItem(item)
                if run.run_id == current_history:
                    self.historyList.setCurrentItem(item)
        self._updateActivationButtonStates()

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
        lines.extend(self._iteration_detail_lines(run))
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
        self._updateActivationButtonStates()

    def _onActivateClicked(self) -> None:
        item = self.historyList.currentItem()
        run_id = self._itemRunId(item)
        if run_id is not None:
            self.activateRunRequested.emit(run_id)

    def _onReplaceClicked(self) -> None:
        item = self.historyList.currentItem()
        run_id = self._itemRunId(item)
        if run_id is not None:
            self.replaceRunRequested.emit(run_id)

    def _updateActivationButtonStates(self) -> None:
        track_runs = [
            run for run in self._runs_by_id.values()
            if run.track_id == self._current_track_id
        ]
        track_busy = any(run.status in {"pending", "running"} for run in track_runs)
        if self._busy or self._project_busy or track_busy:
            # 当前 track 有 pending/running run 时领域层会拒绝全部激活操作
            # （review F-2 GUI 缓解）：禁用并给出原因，不再"可点击但必失败"
            reason = (
                "An AI task is active on this track"
                if track_busy else
                "A project operation is in progress"
                if self._project_busy else
                "An AI task is running"
            )
            for button in (self.activateButton, self.replaceButton,
                           self.clearActivationButton, self.manageValidationButton):
                button.setEnabled(False)
                button.setToolTip(reason)
            return

        self.manageValidationButton.setEnabled(self._current_track_id is not None)
        self.manageValidationButton.setToolTip("")

        item = self.historyList.currentItem()
        run_id = self._itemRunId(item)
        run = self._runs_by_id.get(run_id) if run_id else None

        is_completed_infer = (
            run is not None
            and self._current_track_id is not None
            and run.track_id == self._current_track_id
            and run.task_type == "infer"
            and run.status == "completed"
        )
        is_active = (run_id is not None and run_id == self._active_run_id)
        has_active_obs = (
            self._current_track_id is not None
            and self._active_status in ("active", "legacy_inferred", "legacy_mixed")
        )

        if is_completed_infer and not is_active:
            if has_active_obs:
                self.activateButton.setEnabled(False)
                self.activateButton.setToolTip("")
                self.replaceButton.setEnabled(True)
                self.replaceButton.setToolTip("")
            else:
                self.activateButton.setEnabled(True)
                self.activateButton.setToolTip("")
                self.replaceButton.setEnabled(False)
                self.replaceButton.setToolTip("")
        else:
            self.activateButton.setEnabled(False)
            self.activateButton.setToolTip("")
            self.replaceButton.setEnabled(False)
            # legacy_inferred 状态下选中被推断 run：Replace 因 is_active 被禁，
            # 说明升级为显式 active 的路径（review F-7）
            if (is_active and self._active_status == "legacy_inferred"):
                self.replaceButton.setToolTip(
                    "Legacy active run: use Clear, then Activate to make it explicit")
            else:
                self.replaceButton.setToolTip("")

        clear_enabled = has_active_obs
        self.clearActivationButton.setEnabled(clear_enabled)
        self.clearActivationButton.setToolTip("" if clear_enabled else "No active AI observations to clear")

    def setRefinementInfo(
        self,
        active_status: str,
        active_run_id: UUID | None,
        ref_state: Any | None,
        validation_valid: bool,
        validation_reason: str | None,
    ) -> None:
        """更新当前 Track 的 AI 激活状态与固定验证集状态。"""
        self._active_status = active_status
        self._active_run_id = active_run_id
        self._ref_state = ref_state

        if active_status == "active" and active_run_id is not None:
            self.activeRunLabel.setText(f"Active AI: <b>{str(active_run_id)[:8]}</b>")
        elif active_status == "legacy_inferred" and active_run_id is not None:
            self.activeRunLabel.setText(f"Active AI: <b>{str(active_run_id)[:8]}</b> (legacy)")
        elif active_status == "legacy_mixed":
            self.activeRunLabel.setText("Active AI: <b>Legacy mixed</b>")
        else:
            self.activeRunLabel.setText("Active AI: None")

        active_series = getattr(ref_state, "active_series", None) if ref_state else None
        if active_series:
            n_frames = len(active_series.label_snapshots)
            status_desc = "Valid" if validation_valid else f"Invalid ({validation_reason or 'modified'})"
            self.activeValidationLabel.setText(
                f"Validation: <b>'{active_series.name}'</b> ({n_frames} frames, {status_desc})"
            )
        else:
            self.activeValidationLabel.setText("Validation: None")

        for index in range(self.historyList.count()):
            item = self.historyList.item(index)
            r_id = self._itemRunId(item)
            r = self._runs_by_id.get(r_id)
            if r:
                item.setText(self._runLabel(r))

        self._updateActivationButtonStates()

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

    def _runLabel(self, run: TrackingRun) -> str:
        iter_suffix = ""
        iter_info = run.extra_fields.get("refinement_iteration_v1")
        if isinstance(iter_info, dict) and "iteration_index" in iter_info:
            iter_suffix = f" · iter {iter_info['iteration_index']}"

        if run.task_type == "infer":
            if run.run_id == self._active_run_id:
                status_str = "Active"
            elif (run.track_id != self._current_track_id
                  and run.run_id == self._active_run_ids_by_track.get(run.track_id)):
                # 项目级 historyList：其他 Track 正在使用的结果不能标成
                # "Not active" 误导用户（review F-4）
                status_str = "Active (other track)"
            elif run.status == "completed":
                status_str = "Completed · Not active"
            else:
                status_str = run.status.capitalize()
        else:
            status_str = run.status.capitalize()

        label = f"{run.task_type} · {status_str} · {str(run.run_id)[:8]}{iter_suffix}"
        if run.model_snapshot:
            label += f" · {run.model_snapshot.replace(chr(92), chr(47)).rsplit(chr(47), 1)[-1]}"
        return label

    def _runDetails(self, run: TrackingRun) -> str:
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

        details.extend(self._iteration_detail_lines(run))
        if run.error_message:
            details.append(f"error={run.error_message}")
        return "\n".join(details)

    def _iteration_detail_lines(self, run: TrackingRun) -> list[str]:
        """训练迭代的完整可追溯展示（label 数、审核摘要、coverage、可比性）。"""
        lines: list[str] = []
        iter_info = run.extra_fields.get("refinement_iteration_v1")
        if not isinstance(iter_info, dict) or iter_info.get("iteration_index") is None:
            return lines
        lines.append(f"iteration={iter_info['iteration_index']}")
        # lineage 展示（plan Scope：实际 mode、resume source、本次 epochs）
        mode = iter_info.get("training_mode")
        if mode:
            mode_line = f"training_mode={mode}"
            if mode == "resume" and iter_info.get("resume_from_training_run_id"):
                mode_line += (f" · resume_source="
                              f"{str(iter_info['resume_from_training_run_id'])[:8]}")
            lines.append(mode_line)
        epochs_this_run = run.config.get("epochs")
        if epochs_this_run is not None:
            lines.append(f"epochs_this_run={epochs_this_run}")
        train_labels = iter_info.get("training_labels")
        if isinstance(train_labels, list):
            lines.append(f"training_labels={len(train_labels)}")
        series_id = iter_info.get("validation_series_id")
        if series_id:
            val_count = self._validation_label_count(series_id)
            lines.append(
                f"validation_labels={val_count if val_count is not None else 'unavailable'}"
                f" · validation_series={series_id}"
            )
        else:
            lines.append(
                "validation_labels=0 · no fixed validation — "
                "cross-iteration RMSE comparison unavailable"
            )
        review = iter_info.get("review_summary")
        if isinstance(review, dict):
            lines.append(
                "review_summary="
                + ", ".join(
                    f"{key}={review[key]}"
                    for key in ("total_candidates", "reviewed_count", "pending_count",
                                "accepted_count", "corrected_count", "skipped_count")
                    if key in review
                )
            )
            if review.get("pending_count"):
                lines.append(f"remaining_candidates={review['pending_count']}")
        source_infer = iter_info.get("source_infer_run_id")
        if source_infer:
            try:
                source_run = self._runs_by_id.get(UUID(str(source_infer)))
            except (TypeError, ValueError):
                source_run = None
            coverage = None
            if source_run is not None:
                summary = source_run.extra_fields.get("prediction_summary_v1")
                if isinstance(summary, dict) and summary.get("coverage") is not None:
                    coverage = summary["coverage"]
            lines.append(
                f"prediction_coverage={coverage:.1%}"
                if isinstance(coverage, (int, float)) and not isinstance(coverage, bool)
                else "prediction_coverage=unavailable"
            )
        return lines

    def _validation_label_count(self, series_id: str) -> int | None:
        """按 id 在当前 Track 的 refinement 状态中查 series 标签数；查不到返回 None。

        series 快照不可变，历史评价的标签数因此可追溯；跨 track/legacy 场景
        可能无数据，此时展示 unavailable 而不是伪造数值。
        """
        try:
            target = UUID(str(series_id))
        except (TypeError, ValueError):
            return None
        ref_state = self._ref_state
        series = ref_state.get_series(target) if ref_state is not None else None
        return len(series.label_snapshots) if series is not None else None

    # --- 建议帧公共接口（Phase 5.1）---

    def setSuggestResult(self, result: FrameSelectionResult | None) -> None:
        """用建议帧结果更新列表；None 表示清空。

        列表只显示帧号，双击发出 suggestedFrameJumped 信号（跳帧）；
        不自动创建 TrackPoint，用户需手动标注。
        """
        self.suggestedFramesList.clear()
        if result is None:
            return
        for frame in result.suggested_frames:
            item = QListWidgetItem(f"Frame {frame}  (double-click to jump)")
            item.setData(Qt.ItemDataRole.UserRole, frame)
            self.suggestedFramesList.addItem(item)
        excluded = result.excluded_count
        actual = result.actual_n
        self.setSuggestStatus(
            f"Suggested {actual} frame(s) · {excluded} existing label(s) excluded · "
            f"algorithm={result.request_algorithm}"
        )

    def setSuggestStatus(self, message: str) -> None:
        """显示或隐藏建议帧区域的状态标签。"""
        if message.strip():
            self.suggestStatusLabel.setText(message)
            self.suggestStatusLabel.show()
        else:
            self.suggestStatusLabel.hide()

    def setSuggestEnabled(self, enabled: bool, reason: str = "", *, hint: bool = False) -> None:
        """控制"建议帧"按钮可用状态及 tooltip。

        hint=True 时把禁用原因作为可见状态文案显示（如"首次选帧需要保存"）；
        恢复可用时若状态栏仍显示该提示则清除，不吞掉结果状态。
        """
        self.suggestButton.setEnabled(enabled)
        self.suggestButton.setToolTip(reason if not enabled else "")
        is_running = "running" in reason.lower()
        self.suggestCancelButton.setEnabled(not enabled and is_running)
        self.suggestCancelButton.setVisible(not enabled and is_running)
        if hint and not enabled:
            self._suggest_hint = reason
            self.setSuggestStatus(reason)
        elif enabled and getattr(self, "_suggest_hint", "") and self.suggestStatusLabel.text() == self._suggest_hint:
            self._suggest_hint = ""
            self.setSuggestStatus("")

    def _onSuggestClicked(self) -> None:
        n = self.nFramesSpinBox.value()
        algorithm = self.algorithmComboBox.currentData()
        if not algorithm:
            algo_text = self.algorithmComboBox.currentText()
            algorithm = "kmeans" if "k" in algo_text.lower() else "uniform"
        self.suggestFramesRequested.emit(n, str(algorithm))

    def _onSuggestedFrameDoubleClicked(self, item: QListWidgetItem) -> None:
        frame = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(frame, int):
            self.suggestedFrameJumped.emit(frame)

    # --- 建议帧审核公共接口（Phase 5.2/5.3）---

    def _onMineClicked(self) -> None:
        params = MiningParams(
            top_n=self.mineTopNSpinBox.value(),
            min_gap_s=self.mineMinGapSpinBox.value(),
        )
        self.mineDifficultRequested.emit(None, params)

    def _onReviewCandidateDoubleClicked(self, item: QListWidgetItem) -> None:
        frame = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(frame, int):
            self.reviewCandidateJumpRequested.emit(frame)

    def setMineEnabled(self, enabled: bool, reason: str = "") -> None:
        self.mineButton.setEnabled(enabled)
        self.mineButton.setToolTip(reason if not enabled else "")
        if not enabled and reason:
            self.mineReasonLabel.setText(reason)
            self.mineReasonLabel.show()
        else:
            self.mineReasonLabel.setText("")
            self.mineReasonLabel.hide()

    def setMineBusy(self, busy: bool) -> None:
        self.mineButton.setEnabled(not busy)
        self.mineCancelButton.setEnabled(busy)
        self.mineCancelButton.setVisible(busy)

    def setMineStatus(self, message: str) -> None:
        if message.strip():
            self.mineStatusLabel.setText(message)
            self.mineStatusLabel.show()
        else:
            self.mineStatusLabel.setText("")
            self.mineStatusLabel.hide()

    def setReviewBatch(
        self,
        controller: Any | None,
        summary: Any | None,
    ) -> None:
        if controller is None or controller.active_batch is None or summary is None:
            self.reviewProgressLabel.setText("No active review batch")
            self.candidateDetailsLabel.setText("Select a completed infer run to mine or review.")
            self.reviewPrevButton.setEnabled(False)
            self.reviewNextButton.setEnabled(False)
            self.reviewAcceptButton.setEnabled(False)
            self.reviewSkipButton.setEnabled(False)
            self.reviewCorrectButton.setEnabled(False)
            self.reviewCorrectButton.setText("Correct (C)")
            self.reviewCorrectButton.setStyleSheet("")
            self.deleteManualPointButton.setEnabled(False)
            self.reviewCandidatesList.clear()
            return

        tot = summary.total_candidates
        rev = summary.total_reviewed
        pen = summary.pending_count
        acc = summary.accepted_count
        skp = summary.skipped_count
        cor = summary.corrected_count

        if pen == 0 and tot > 0:
            self.reviewProgressLabel.setText(
                f"🎉 Review Complete: all {tot} reviewed ({acc} accepted · {skp} skipped · {cor} corrected)"
            )
        else:
            self.reviewProgressLabel.setText(
                f"Review: {rev}/{tot} reviewed ({pen} pending · {acc} accepted · {skp} skipped · {cor} corrected)"
            )

        curr = controller.current_candidate
        idx = controller.current_index
        if curr is not None:
            disp = controller.current_disposition
            pred_str = "no prediction"
            if curr.prediction is not None:
                pred_str = (
                    f"({curr.prediction.pixel_x:.1f}, {curr.prediction.pixel_y:.1f}) "
                    f"conf={curr.prediction.confidence:.2f}"
                )
            reasons_str = ", ".join(curr.reasons) if curr.reasons else "none"
            guidance = "\n👉 Correct mode: click video to place point (Esc to cancel)" if controller.is_correcting else ""
            self.candidateDetailsLabel.setText(
                f"Candidate {idx + 1}/{tot} (Frame {curr.frame_index}) · Status: {disp.upper()}\n"
                f"AI: {pred_str} · Score: {curr.total_score:.3f}\n"
                f"Reasons: {reasons_str}{guidance}"
            )
            is_already_corrected = (disp == "corrected")
            self.reviewAcceptButton.setEnabled(not is_already_corrected)
            self.reviewSkipButton.setEnabled(not is_already_corrected)
            self.reviewCorrectButton.setEnabled(True)
            if is_already_corrected:
                self.reviewAcceptButton.setToolTip("Frame has a manual point; delete it first to change disposition")
                self.reviewSkipButton.setToolTip("Frame has a manual point; delete it first to change disposition")
            else:
                self.reviewAcceptButton.setToolTip("")
                self.reviewSkipButton.setToolTip("")
            if controller.is_correcting:
                self.reviewCorrectButton.setText("Click Video...")
                self.reviewCorrectButton.setStyleSheet("font-weight: bold; background-color: #ffe0b2;")
            else:
                self.reviewCorrectButton.setText("Correct (C)")
                self.reviewCorrectButton.setStyleSheet("")
        else:
            self.candidateDetailsLabel.setText("No candidate selected")
            self.reviewAcceptButton.setEnabled(False)
            self.reviewSkipButton.setEnabled(False)
            self.reviewCorrectButton.setEnabled(False)
            self.reviewCorrectButton.setText("Correct (C)")
            self.reviewCorrectButton.setStyleSheet("")

        self.reviewPrevButton.setEnabled(controller.can_navigate_previous)
        self.reviewNextButton.setEnabled(controller.can_navigate_next)

        self.reviewCandidatesList.blockSignals(True)
        self.reviewCandidatesList.clear()
        state = controller.state
        reviewed = state.reviewed_frames if state else {}
        for i, c in enumerate(controller.candidates):
            rec = reviewed.get(c.frame_index)
            disp_tag = f"[{rec.disposition.upper()}]" if rec else "[PENDING]"
            score_tag = f"score={c.total_score:.2f}"
            item_text = f"{i + 1}. Frame {c.frame_index} {disp_tag} {score_tag}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, c.frame_index)
            self.reviewCandidatesList.addItem(item)
            if i == idx:
                item.setSelected(True)
                self.reviewCandidatesList.setCurrentItem(item)
        self.reviewCandidatesList.blockSignals(False)
