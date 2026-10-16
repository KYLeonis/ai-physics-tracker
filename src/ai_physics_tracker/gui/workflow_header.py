"""常驻工作区导航、状态与下一步推荐。

三个稳定工作区（实验设置 / 获取轨迹 / 分析与图表）+ 两行状态：
- 第 1 行：项目 · 视频 · 目标 · 范围 · 保存状态
- 第 2 行：当前采用轨迹 · 预览 candidate · 分析状态 chip

导航只改变视图；推荐按钮发出动作 ID，执行由既有任务卡入口负责。
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.application.workflow_projection import TaskCard

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
    actionRequested = Signal(str)
    analysisToolsRequested = Signal()

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
        self.analysisToolsButton = QPushButton("Fit formula / Measure intervals")
        self.analysisToolsButton.setObjectName("openAnalysisTools")
        self.analysisToolsButton.setToolTip(
            "Open the formula editor, fitting results and crossing-interval measurement tools")
        self.analysisToolsButton.setStyleSheet(
            "background: #eaf3ff; color: #172b4d; font-weight: bold; padding: 5px;")
        self.analysisToolsButton.clicked.connect(self.analysisToolsRequested)
        nav_column.addWidget(self.analysisToolsButton)

        self.contextLabel = QLabel("No project")
        self.contextLabel.setWordWrap(True)
        self.trajectoryLabel = QLabel("Current trajectory: —")
        self.trajectoryLabel.setWordWrap(True)
        self.analysisChipLabel = QLabel(ANALYSIS_CHIP_TEXT[None])
        self.analysisChipLabel.setWordWrap(True)
        self.limitationsLabel = QLabel("")
        self.limitationsLabel.setWordWrap(True)
        self.limitationsLabel.hide()
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
        status_column.addWidget(self.limitationsLabel)
        status_column.addWidget(self.taskStripLabel)
        self.nextStepLabel = QLabel()
        self.nextStepLabel.setWordWrap(True)
        self.nextStepLabel.setStyleSheet(
            "background: #eaf3ff; color: #172b4d; border-radius: 4px; padding: 4px;")
        self.nextStepLabel.hide()
        # 换行状态标签按可用宽度换行显示；Windows 上换行标签的
        # minimumSizeHint 是整行文本宽度，不能让它决定窗口最小宽度
        #（否则窄屏笔记本用户无法缩小窗口），水平方向忽略其提示。
        for label in (self.contextLabel, self.trajectoryLabel, self.analysisChipLabel,
                      self.limitationsLabel, self.taskStripLabel, self.nextStepLabel):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        status_column.addWidget(self.nextStepLabel)
        next_actions = QHBoxLayout()
        self.nextStepButtons = [QPushButton() for _ in range(3)]
        for button in self.nextStepButtons:
            button.clicked.connect(
                lambda _checked=False, b=button:
                self.actionRequested.emit(b.property("actionId")))
            next_actions.addWidget(button)
            button.hide()
        next_actions.addStretch()
        status_column.addLayout(next_actions)

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

    def setTaskCard(self, card: TaskCard | None) -> None:
        """顶部显示主动作与前两个旁路；完整说明/审核导航保留在获取轨迹面板。"""
        actions = () if card is None else (
            ((card.primary,) if card.primary is not None else ()) + card.secondary
        )
        text = ""
        if card is not None:
            text = card.title
            if card.explanation:
                text += " · " + card.explanation[0]
            reasons = [spec.reason for spec in actions[:3]
                       if not spec.enabled and spec.reason]
            if reasons:
                text += "\n" + "; ".join(reasons)
        self.nextStepLabel.setText(text)
        self.nextStepLabel.setVisible(card is not None)
        self.nextStepLabel.setToolTip("\n".join(card.explanation) if card else "")
        for index, button in enumerate(self.nextStepButtons):
            if index >= len(actions):
                button.hide()
                button.setProperty("actionId", "")
                button.setEnabled(False)
                continue
            spec = actions[index]
            button.setText(spec.label)
            button.setProperty("actionId", spec.action_id)
            button.setEnabled(spec.enabled)
            button.setToolTip(spec.reason or "")
            button.show()
        # 同步失效布局缓存：按钮显示/隐藏后立即按当前可见内容报告最小尺寸，
        # 不等事件循环投递LayoutRequest（程序化连续刷新时旧缓存会虚高最小宽度）。
        self.layout().invalidate()

    def setAnalysisChip(self, state: str | None) -> None:
        self.analysisChipLabel.setText(
            ANALYSIS_CHIP_TEXT.get(state, ANALYSIS_CHIP_TEXT[None]))

    def setStatus(self, context: str, trajectory: str,
                  analysis_state: str | None) -> None:
        self.contextLabel.setText(context)
        self.trajectoryLabel.setText(trajectory)
        self.setAnalysisChip(analysis_state)

    def setLimitations(self, limitations: tuple[str, ...] | list[str]) -> None:
        """§11.1 第 2 行：可部分分析时并列限制数量与范围。"""
        if limitations:
            self.limitationsLabel.setText(
                "Limits: " + "; ".join(str(item) for item in limitations))
            self.limitationsLabel.show()
        else:
            self.limitationsLabel.hide()

    def setTaskStrip(self, text: str) -> None:
        """分析工作区内 AI 后台任务的常驻提示（设计 §8.2）；空串隐藏。"""
        if text.strip():
            self.taskStripLabel.setText(text)
            self.taskStripLabel.show()
        else:
            self.taskStripLabel.hide()
