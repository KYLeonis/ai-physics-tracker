"""P1.4-S4 四 role 候选审核对话框(Qt GUI 层,非模态)。

对话框只呈现队列与当前帧诊断、发出导航/处置信号;写路径全部经
ExperimentInferenceActions(它调 session 的 run-scoped 审核动作)。
Correct 的落点在主窗口视频上点击(对话框保持可见,角色由下拉框选择)。
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

_DISPOSITION_MARKS = {
    "accepted": "✓ accepted",
    "skipped": "– skipped",
    "corrected": "✎ corrected",
}


class JointReviewDialog(QDialog):
    """experiment 四 role 候选审核队列窗口(非模态)。"""

    acceptRequested = Signal()
    skipRequested = Signal()
    correctRequested = Signal(str)        # 选定 role
    cancelCorrectRequested = Signal()
    previousRequested = Signal()
    nextRequested = Signal()
    finishRequested = Signal()
    frameJumped = Signal(int)             # 队列列表双击

    def __init__(self, run_id: UUID, parent=None) -> None:
        super().__init__(parent)
        self.run_id = run_id
        self.setWindowTitle(
            f"Joint candidate review — run {str(run_id)[:8]} (not active)")
        self.setMinimumSize(520, 420)
        self.setModal(False)

        root = QVBoxLayout(self)
        self.infoLabel = QLabel(self)
        self.infoLabel.setWordWrap(True)
        root.addWidget(self.infoLabel)

        self.frameList = QListWidget(self)
        self.frameList.itemDoubleClicked.connect(
            lambda item: self.frameJumped.emit(int(item.data(0x0100))))
        root.addWidget(self.frameList, stretch=2)

        detail = QLabel("Current frame diagnostics (per role)", self)
        root.addWidget(detail)
        self.roleTable = QTableWidget(0, 4, self)
        self.roleTable.setHorizontalHeaderLabels(
            ["Role", "Confidence", "Position (px)", "Diagnostics"])
        self.roleTable.verticalHeader().setVisible(False)
        self.roleTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.roleTable, stretch=3)

        correct_row = QHBoxLayout()
        self.roleCombo = QComboBox(self)
        self.correctButton = QPushButton("Correct selected role…", self)
        self.cancelCorrectButton = QPushButton("Cancel correct (Esc)", self)
        self.cancelCorrectButton.setVisible(False)
        correct_row.addWidget(self.roleCombo)
        correct_row.addWidget(self.correctButton)
        correct_row.addWidget(self.cancelCorrectButton)
        root.addLayout(correct_row)

        nav = QGridLayout()
        self.prevButton = QPushButton("◀ Previous", self)
        self.nextButton = QPushButton("Next ▶", self)
        self.acceptButton = QPushButton("Accept frame", self)
        self.skipButton = QPushButton("Skip frame", self)
        self.finishButton = QPushButton("Finish reviewing", self)
        nav.addWidget(self.prevButton, 0, 0)
        nav.addWidget(self.acceptButton, 0, 1)
        nav.addWidget(self.skipButton, 0, 2)
        nav.addWidget(self.nextButton, 0, 3)
        nav.addWidget(self.finishButton, 1, 0, 1, 4)
        root.addLayout(nav)

        self.prevButton.clicked.connect(self.previousRequested)
        self.nextButton.clicked.connect(self.nextRequested)
        self.acceptButton.clicked.connect(self.acceptRequested)
        self.skipButton.clicked.connect(self.skipRequested)
        self.finishButton.clicked.connect(self.finishRequested)
        self.correctButton.clicked.connect(self._on_correct_clicked)
        self.cancelCorrectButton.clicked.connect(self.cancelCorrectRequested)

    def _on_correct_clicked(self) -> None:
        role = self.roleCombo.currentText()
        if role:
            self.correctRequested.emit(role)

    # --- 状态同步(由控制器调用) ---

    def set_roles(self, roles) -> None:
        self.roleCombo.clear()
        self.roleCombo.addItems(list(roles))

    def sync(self, candidates, records, current_index, correcting_role) -> None:
        """candidates: ExperimentFrameCandidate 序列;records: frame→record。"""

        self.frameList.clear()
        for candidate in candidates:
            mark = _DISPOSITION_MARKS.get(
                (records.get(candidate.frame_index) or {}).get("disposition", ""),
                "pending")
            item = QListWidgetItem(f"Frame {candidate.frame_index} — {mark}")
            item.setData(0x0100, candidate.frame_index)
            self.frameList.addItem(item)
            if current_index is not None and candidate.frame_index == current_index:
                self.frameList.setCurrentItem(item)

        current = next(
            (c for c in candidates
             if current_index is not None and c.frame_index == current_index),
            None)
        self.roleTable.setRowCount(0)
        if current is not None:
            self.roleTable.setRowCount(4)
            for row, role in enumerate(current.predictions):
                prediction = current.predictions[role]
                reasons = ", ".join(current.role_reasons[role]) or "ok"
                if prediction is None:
                    confidence, position = "missing", "—"
                else:
                    confidence = (
                        "manual" if prediction.confidence is None
                        else f"{prediction.confidence:.2f}")
                    position = (
                        f"({prediction.pixel_x:.1f}, {prediction.pixel_y:.1f})")
                values = (role, confidence, position, reasons)
                for column, text in enumerate(values):
                    self.roleTable.setItem(row, column, QTableWidgetItem(text))
        self.roleTable.resizeColumnsToContents()

        reviewed = len(records)
        total = len(candidates)
        pending = sum(
            1 for c in candidates if c.frame_index not in records)
        self.infoLabel.setText(
            f"{reviewed} of {total} queue frame(s) reviewed · {pending} "
            f"pending. Correct writes one manual point for the chosen role "
            f"only; Accept/Skip never write points."
            + (f"\nCorrecting role '{correcting_role}': click the position "
               f"in the video." if correcting_role else ""))
        has_current = current is not None
        self.acceptButton.setEnabled(has_current)
        self.skipButton.setEnabled(has_current)
        self.correctButton.setEnabled(has_current and not correcting_role)
        self.cancelCorrectButton.setVisible(bool(correcting_role))
        self.roleCombo.setEnabled(not correcting_role)

    def set_navigation(self, can_previous: bool, can_next: bool) -> None:
        self.prevButton.setEnabled(can_previous)
        self.nextButton.setEnabled(can_next)
