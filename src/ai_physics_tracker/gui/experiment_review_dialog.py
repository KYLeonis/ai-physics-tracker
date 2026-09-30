"""联合推理的推荐帧选择与连续重标窗口；写入由控制器负责。"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class JointReviewDialog(QDialog):
    """选择少量推荐帧，逐帧四点重标；浏览和标注使用同一列表。"""

    labelSelectedRequested = Signal()
    cancelCorrectRequested = Signal()
    skipFrameRequested = Signal()
    previousRequested = Signal()
    nextRequested = Signal()
    finishRequested = Signal()
    frameJumped = Signal(int)

    def __init__(self, run_id: UUID, parent=None) -> None:
        super().__init__(parent)
        self.run_id = run_id
        self.setWindowTitle(f"Relabel suggested frames — run {str(run_id)[:8]}")
        self.setMinimumSize(620, 480)
        self.setModal(False)
        self._batch_pending = False

        root = QVBoxLayout(self)
        self.infoLabel = QLabel(
            "Choose a few frames to relabel (first 5 checked). Click Start once, "
            "then mark tip → body_top → body_bottom → pivot in the video. "
            "After four clicks, the next selected frame opens automatically. "
            "Existing manual labels on selected frames will be replaced as you click.", self)
        self.infoLabel.setWordWrap(True)
        root.addWidget(self.infoLabel)
        self.progressLabel = QLabel(self)
        self.progressLabel.setWordWrap(True)
        root.addWidget(self.progressLabel)
        self.frameList = QListWidget(self)
        self.frameList.itemClicked.connect(
            lambda item: self.frameJumped.emit(int(item.data(Qt.ItemDataRole.UserRole))))
        self.frameList.itemChanged.connect(self._update_selection)
        root.addWidget(self.frameList, stretch=2)

        self.roleTable = QTableWidget(0, 4, self)
        self.roleTable.setHorizontalHeaderLabels(
            ["Role", "AI confidence", "AI position (px)", "Why suggested"])
        self.roleTable.verticalHeader().setVisible(False)
        self.roleTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.roleTable, stretch=2)

        nav = QHBoxLayout()
        self.prevButton = QPushButton("Preview previous suggestion", self)
        self.nextButton = QPushButton("Preview next suggestion", self)
        nav.addWidget(self.prevButton)
        nav.addWidget(self.nextButton)
        root.addLayout(nav)
        actions = QHBoxLayout()
        self.trainButton = QPushButton("Start relabeling selected frames", self)
        self.cancelCorrectButton = QPushButton("Pause (Esc)", self)
        self.skipButton = QPushButton("Skip this frame", self)
        self.cancelCorrectButton.hide()
        self.skipButton.hide()
        for button in (self.trainButton, self.cancelCorrectButton, self.skipButton):
            actions.addWidget(button)
        root.addLayout(actions)
        self.finishButton = QPushButton("Close — keep saved labels", self)
        root.addWidget(self.finishButton)

        self.prevButton.clicked.connect(self.previousRequested)
        self.nextButton.clicked.connect(self.nextRequested)
        self.trainButton.clicked.connect(self.labelSelectedRequested)
        self.cancelCorrectButton.clicked.connect(self.cancelCorrectRequested)
        self.skipButton.clicked.connect(self.skipFrameRequested)
        self.finishButton.clicked.connect(self.finishRequested)

    def checkedFrames(self) -> tuple[int, ...]:
        return tuple(
            int(self.frameList.item(row).data(Qt.ItemDataRole.UserRole))
            for row in range(self.frameList.count())
            if self.frameList.item(row).checkState() == Qt.CheckState.Checked)

    def _update_selection(self, *_args) -> None:
        if not self._batch_pending:
            count = len(self.checkedFrames())
            self.trainButton.setText(f"Start relabeling {count} selected frame(s)")
            self.trainButton.setEnabled(count > 0)

    def uncheckFrames(self, frames: set[int]) -> None:
        for row in range(self.frameList.count()):
            item = self.frameList.item(row)
            if item.data(Qt.ItemDataRole.UserRole) in frames:
                item.setCheckState(Qt.CheckState.Unchecked)

    def sync(self, candidates, records, current_index, correcting_role,
             training_frames, frame_ready: bool, *, progress: str = "",
             batch_pending: bool = False) -> None:
        """刷新诊断与进度；勾选状态只在首次打开时初始化。"""

        self._batch_pending = batch_pending
        initial = self.frameList.count() == 0
        self.frameList.blockSignals(True)
        for row, candidate in enumerate(candidates):
            if initial:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, candidate.frame_index)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if row < 5
                                   else Qt.CheckState.Unchecked)
                self.frameList.addItem(item)
            item = self.frameList.item(row)
            reason = "; ".join(
                f"{role}: {', '.join(reasons)}"
                for role, reasons in candidate.role_reasons.items() if reasons)
            reason = reason or ", ".join(candidate.geometry_reasons)
            mark = " · in training set" if candidate.frame_index in training_frames else ""
            corrected = len(records.get(candidate.frame_index, {}).get("manual_point_ids", {}))
            if corrected:
                mark += f" · {corrected}/4 corrected"
            item.setText(f"Frame {candidate.frame_index} — {reason}{mark}")
            if candidate.frame_index == current_index:
                self.frameList.setCurrentItem(item)
        self.frameList.blockSignals(False)
        self.frameList.setEnabled(not batch_pending)
        current = next((c for c in candidates if c.frame_index == current_index), None)
        self.roleTable.setRowCount(0 if current is None else 4)
        if current is not None:
            for row, (role, prediction) in enumerate(current.predictions.items()):
                values = (
                    role,
                    "missing" if prediction is None else f"{prediction.confidence:.3f}",
                    "—" if prediction is None else
                    f"({prediction.pixel_x:.1f}, {prediction.pixel_y:.1f})",
                    ", ".join(current.role_reasons[role]) or "—",
                )
                for column, value in enumerate(values):
                    self.roleTable.setItem(row, column, QTableWidgetItem(value))
        self.roleTable.resizeColumnsToContents()
        self.progressLabel.setText(progress or (
            f"{len(candidates)} suggestions from this inference run. "
            "Preview buttons only browse; Start begins labeling."
            if candidates else "No remaining difficult frames need new labels."))
        self.cancelCorrectButton.setVisible(bool(correcting_role))
        self.skipButton.setVisible(bool(correcting_role) and batch_pending)
        if batch_pending:
            self.trainButton.setText("Resume relabeling")
            self.trainButton.setEnabled(not correcting_role)
        else:
            self._update_selection()

    def set_navigation(self, can_previous: bool, can_next: bool) -> None:
        self.prevButton.setEnabled(can_previous and not self._batch_pending)
        self.nextButton.setEnabled(can_next and not self._batch_pending)
