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

class JointReviewDialog(QDialog):
    """experiment 四 role 推荐帧窗口(非模态)。"""

    correctRequested = Signal(str)        # 选定 role
    cancelCorrectRequested = Signal()
    previousRequested = Signal()
    nextRequested = Signal()
    finishRequested = Signal()
    frameJumped = Signal(int)             # 队列列表双击
    addFrameToTrainingRequested = Signal()

    def __init__(self, run_id: UUID, parent=None) -> None:
        super().__init__(parent)
        self.run_id = run_id
        self.setWindowTitle(
            f"Suggested frames — run {str(run_id)[:8]}")
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
        self.cancelCorrectButton = QPushButton("Stop correcting (Esc)", self)
        self.cancelCorrectButton.setVisible(False)
        correct_row.addWidget(self.roleCombo)
        correct_row.addWidget(self.correctButton)
        correct_row.addWidget(self.cancelCorrectButton)
        root.addLayout(correct_row)

        nav = QGridLayout()
        self.prevButton = QPushButton("◀ Previous", self)
        self.nextButton = QPushButton("Next ▶", self)
        self.trainButton = QPushButton("Add this frame and mark 4 roles…", self)
        self.finishButton = QPushButton("Close suggestions", self)
        nav.addWidget(self.prevButton, 0, 0)
        nav.addWidget(self.nextButton, 0, 1)
        nav.addWidget(self.trainButton, 1, 0, 1, 2)
        nav.addWidget(self.finishButton, 2, 0, 1, 2)
        root.addLayout(nav)

        self.prevButton.clicked.connect(self.previousRequested)
        self.nextButton.clicked.connect(self.nextRequested)
        self.trainButton.clicked.connect(self.addFrameToTrainingRequested)
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

    def sync(self, candidates, records, current_index, correcting_role,
             training_frames, frame_ready: bool) -> None:
        """candidates: ExperimentFrameCandidate 序列;records: frame→record。"""

        self.frameList.clear()
        for candidate in candidates:
            mark = ("✓ in training set" if candidate.frame_index in training_frames
                    else "✎ corrected" if (records.get(candidate.frame_index) or {}).get(
                        "disposition") == "corrected" else "suggested")
            reason = next(
                (f"{role}: {reasons[0]}" for role, reasons in
                 candidate.role_reasons.items() if reasons),
                candidate.geometry_reasons[0] if candidate.geometry_reasons
                else "screening signal")
            item = QListWidgetItem(
                f"Frame {candidate.frame_index} — {reason} · {mark}")
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

        total = len(candidates)
        selected = sum(c.frame_index in training_frames for c in candidates)
        self.infoLabel.setText(
            f"{total} suggested frame(s) · {selected} already in training set.\n"
            "These are optional suggestions, not frames you must accept. "
            "Add one to the shared training set, then mark all four roles "
            "manually for retraining. Correct one role only if its measurement "
            "position is wrong."
            + (f"\nCorrecting '{correcting_role}': "
               + ("click once in the video (Esc to cancel)." if frame_ready
                  else f"waiting for frame {current_index} to appear in the video…")
               if correcting_role else ""))
        has_current = current is not None
        self.trainButton.setEnabled(
            has_current and current_index not in training_frames and not correcting_role)
        self.correctButton.setEnabled(has_current and not correcting_role)
        self.cancelCorrectButton.setVisible(bool(correcting_role))
        self.roleCombo.setEnabled(not correcting_role)

    def set_navigation(self, can_previous: bool, can_next: bool) -> None:
        self.prevButton.setEnabled(can_previous)
        self.nextButton.setEnabled(can_next)
