"""Phase 5.7 — 常驻工作区导航与状态头（纯展示，不发任务）。

三个稳定工作区（实验设置 / 获取轨迹 / 分析与图表）+ 两行状态：
- 第 1 行：项目 · 视频 · 目标 · 范围 · 保存状态
- 第 2 行：当前采用轨迹 · 预览 candidate · 分析状态 chip

导航只改变视图；任务执行、结果采用、图表更新均不在此发生（设计 §7）。
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

WORKSPACE_SETUP = "setup"
WORKSPACE_ACQUIRE = "acquire"
WORKSPACE_ANALYSIS = "analysis"

_WORKSPACE_LABELS = (
    (WORKSPACE_SETUP, "Experiment setup"),
    (WORKSPACE_ACQUIRE, "Acquire trajectory"),
    (WORKSPACE_ANALYSIS, "Analysis & charts"),
)

# 分析状态 chip 文案（设计 §11.1 的精确措辞，不是"就绪"徽标）
ANALYSIS_CHIP_TEXT = {
    "not_computable": "Analysis: not computable yet",
    "partial": "Analysis: partial — has limits",
    "needs_update": "Analysis: charts need update",
    "latest": "Analysis: charts up to date",
    None: "Analysis: —",
}


class WorkflowHeader(QWidget):
    """窗口顶部常驻头：工作区切换 + 上下文/轨迹/分析状态。"""

    workspaceRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}

        nav_column = QVBoxLayout()
        nav_column.setContentsMargins(0, 0, 0, 0)
        nav_column.setSpacing(2)
        for key, label in _WORKSPACE_LABELS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, k=key: self.workspaceRequested.emit(k))
            self._buttons[key] = button
            nav_column.addWidget(button)

        self.contextLabel = QLabel("No project")
        self.contextLabel.setWordWrap(True)
        self.trajectoryLabel = QLabel("Current trajectory: —")
        self.trajectoryLabel.setWordWrap(True)
        self.analysisChipLabel = QLabel(ANALYSIS_CHIP_TEXT[None])
        self.analysisChipLabel.setWordWrap(True)
        self.taskStripLabel = QLabel("")
        self.taskStripLabel.setWordWrap(True)
        self.taskStripLabel.hide()

        status_column = QVBoxLayout()
        status_column.setContentsMargins(0, 0, 0, 0)
        status_column.setSpacing(2)
        status_column.addWidget(self.contextLabel)
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self.trajectoryLabel, 1)
        status_row.addWidget(self.analysisChipLabel)
        status_column.addLayout(status_row)
        status_column.addWidget(self.taskStripLabel)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(6, 4, 6, 4)
        content_row.addLayout(nav_column)
        content_row.addWidget(divider)
        content_row.addLayout(status_column, 1)

        header_rule = QFrame()
        header_rule.setFrameShape(QFrame.Shape.HLine)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(content_row)
        outer.addWidget(header_rule)

    def setWorkspace(self, workspace: str) -> None:
        for key, button in self._buttons.items():
            button.setChecked(key == workspace)

    def setAnalysisChip(self, state: str | None) -> None:
        self.analysisChipLabel.setText(
            ANALYSIS_CHIP_TEXT.get(state, ANALYSIS_CHIP_TEXT[None]))

    def setStatus(self, context: str, trajectory: str,
                  analysis_state: str | None) -> None:
        self.contextLabel.setText(context)
        self.trajectoryLabel.setText(trajectory)
        self.setAnalysisChip(analysis_state)

    def setTaskStrip(self, text: str) -> None:
        """分析工作区内 AI 后台任务的常驻提示（设计 §8.2）；空串隐藏。"""
        if text.strip():
            self.taskStripLabel.setText(text)
            self.taskStripLabel.show()
        else:
            self.taskStripLabel.hide()
