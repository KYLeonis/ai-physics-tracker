"""Phase 5.7 — 固定检查帧预选确认对话框（C1）。

系统预选成员，用户**预览并显式确认**后才 freeze（不自动冻结）；
可换成员（转入既有 ManageValidationDialog）、可暂不建立。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

RESULT_KEEP = "keep"        # 保留预选集合（调用方据此 freeze）
RESULT_CHOOSE = "choose"    # 用户要求自行挑选（调用方转 ManageValidationDialog）
RESULT_SKIP = "skip"        # 暂不建立检查帧（沿用无 fixed validation 能力）


class FixedCheckConfirmDialog(QDialog):
    """预览系统预选的固定检查帧并确认冻结。"""

    frameJumpRequested = Signal(int)

    def __init__(self, frames: tuple[int, ...], total_labels: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fixed-check frames")
        self.result_choice: str = RESULT_SKIP

        train_count = total_labels - len(frames)
        intro = QLabel(
            "Keep a few manual positions out of learning so later results are "
            "compared with the same ruler.\n\n"
            f"You marked {total_labels} frames. Suggested: hold out "
            f"{len(frames)} frame(s) as fixed-check frames and learn from the "
            "other {train}.".format(train=train_count))
        intro.setWordWrap(True)

        self.frameList = QListWidget()
        self.frameList.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for frame in frames:
            item = QListWidgetItem(f"Frame {frame}  (click to preview)")
            item.setData(Qt.ItemDataRole.UserRole, frame)
            self.frameList.addItem(item)
        self.frameList.itemClicked.connect(self._onFrameClicked)

        self.explainLabel = QLabel(
            "Fixed-check frames leave learning; they are used to compare runs "
            "fairly. You can still correct their positions — that ends direct "
            "comparison and asks for a new set.")
        self.explainLabel.setWordWrap(True)

        self.keepButton = QPushButton("Keep these check frames")
        self.chooseButton = QPushButton("Choose frames myself…")
        self.skipButton = QPushButton("Skip for now")

        buttons = QHBoxLayout()
        buttons.addWidget(self.keepButton, 1)
        buttons.addWidget(self.chooseButton)
        buttons.addWidget(self.skipButton)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.frameList)
        layout.addWidget(self.explainLabel)
        layout.addLayout(buttons)

        self.keepButton.clicked.connect(lambda: self._finish(RESULT_KEEP))
        self.chooseButton.clicked.connect(lambda: self._finish(RESULT_CHOOSE))
        self.skipButton.clicked.connect(lambda: self._finish(RESULT_SKIP))

    def _finish(self, choice: str) -> None:
        # skip 与 Esc/关闭一致：不建立检查帧，沿用无 fixed validation 的能力
        self.result_choice = choice
        if choice == RESULT_SKIP:
            self.reject()
        else:
            self.accept()

    def _onFrameClicked(self, item: QListWidgetItem) -> None:
        frame = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(frame, int):
            self.frameJumpRequested.emit(frame)
