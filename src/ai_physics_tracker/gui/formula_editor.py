"""公式编辑控件：连接受限表达式解析、错误位置提示与 MathText 预览。"""

import numpy as np
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import MathTextParser
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QCheckBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.domain.expression import (
    ExpressionError,
    MathExpression,
    parse_expression,
)


_EXAMPLES = {
    "Linear": "a*t + b",
    "Quadratic": "a*t^2 + b*t + c",
    "Cosine": "A*cos(omega*t + phi) + y0",
    "Damped cosine": "A*exp(-gamma*t)*cos(omega*t + phi) + y0",
}

_INSERTIONS = {
    "sin": "sin()",
    "cos": "cos()",
    "exp": "exp()",
    "log": "log()",
    "sqrt": "sqrt()",
    "abs": "abs()",
    "pi": "pi",
    "^": "^",
    "()": "()",
    "*": "*",
}


class FormulaEditor(QWidget):
    """单行数学表达式编辑器，预览和计算使用同一领域表达式树。"""

    formulaChanged = Signal(str)
    exampleSelected = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expression: MathExpression | None = None
        self._mathTextParser = MathTextParser("agg")

        self.quantityLabel = QLabel("y(t)")
        self.quantityLabel.setAccessibleName("Target quantity")
        self.equalsLabel = QLabel("=")
        self.formulaEdit = QLineEdit("a*t + b")
        self.formulaEdit.setObjectName("formulaEdit")
        self.formulaEdit.setAccessibleName("Function of time")
        self.formulaEdit.setAccessibleDescription(
            "Enter an explicit multiplication expression using t for time."
        )
        self.formulaEdit.setClearButtonEnabled(True)

        self.previewLabel = QLabel()
        self.previewLabel.setObjectName("formulaPreview")
        self.previewLabel.setAccessibleName("Rendered formula preview")
        self.previewLabel.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.previewLabel.setMinimumHeight(40)

        self.errorLabel = QLabel()
        self.errorLabel.setObjectName("formulaError")
        self.errorLabel.setAccessibleName("Formula error")
        self.errorLabel.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        formulaRow = QHBoxLayout()
        formulaRow.addWidget(self.quantityLabel)
        formulaRow.addWidget(self.equalsLabel)
        formulaRow.addWidget(self.formulaEdit, 1)
        layout.addLayout(formulaRow)

        insertionGroup = QCheckBox("Insert symbols / functions")
        insertionGroup.setChecked(False)
        insertionHost = QWidget()
        insertionRow = QGridLayout(insertionHost)
        insertionRow.addWidget(QLabel("Insert:"), 0, 0, 2, 1)
        for index, (name, insertion) in enumerate(_INSERTIONS.items()):
            button = QPushButton(name)
            object_name = name.replace("*", "multiply").replace("^", "power")
            object_name = object_name.replace("(", "paren").replace(")", "")
            button.setObjectName(f"insert_{object_name}")
            button.setAccessibleName(f"Insert {name}")
            button.clicked.connect(
                lambda _checked=False, token=insertion: self._insertText(token)
            )
            insertionRow.addWidget(button, index // 5, index % 5 + 1)
        insertionHost.hide()
        insertionGroup.toggled.connect(insertionHost.setVisible)
        layout.addWidget(insertionGroup)
        layout.addWidget(insertionHost)

        exampleRow = QGridLayout()
        exampleRow.addWidget(QLabel("Editable examples:"), 0, 0, 1, 2)
        for index, (name, formula) in enumerate(_EXAMPLES.items()):
            button = QPushButton(name)
            button.setObjectName(f"example_{name.lower().replace(' ', '_')}")
            button.setAccessibleName(f"Load editable {name.lower()} example")
            button.clicked.connect(lambda _checked=False, value=formula: self._selectExample(value))
            exampleRow.addWidget(button, 1+index//2, index%2)
        layout.addLayout(exampleRow)

        previewScroll = QScrollArea()
        previewScroll.setWidget(self.previewLabel)
        previewScroll.setMaximumHeight(100)
        previewScroll.setMinimumHeight(65)
        previewScroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(previewScroll)
        layout.addWidget(self.errorLabel)

        self.formulaEdit.textChanged.connect(self._onTextChanged)
        self._updatePreview(self.formulaEdit.text())

    def _selectExample(self, value: str) -> None:
        self.setText(value)
        self.exampleSelected.emit()

    def text(self) -> str:
        """返回输入框中的原始表达式文本。"""
        return self.formulaEdit.text()

    def setText(self, text: str) -> None:
        """设置表达式并同步解析状态与预览。"""
        self.formulaEdit.setText(text)

    def expression(self) -> MathExpression | None:
        """返回当前解析结果；输入无效时返回 None。"""
        return self._expression

    def setQuantityLabel(self, text: str) -> None:
        """设置等式左侧只读目标量标签。"""
        self.quantityLabel.setText(text)

    def _onTextChanged(self, text: str) -> None:
        self._updatePreview(text)
        self.formulaChanged.emit(text)

    def _updatePreview(self, text: str) -> None:
        self._expression = None
        self.previewLabel.clear()
        self.errorLabel.clear()
        if not text.strip():
            self.errorLabel.setText("Enter a formula.")
            self.formulaEdit.setAccessibleDescription("Enter a formula.")
            return

        try:
            expression = parse_expression(text)
        except ExpressionError as error:
            self.errorLabel.setText(
                f"{error} (character {error.position + 1}; "
                f"source index {error.position}, zero-based)"
            )
            self.formulaEdit.setAccessibleDescription(self.errorLabel.text())
            return

        try:
            parsed = self._mathTextParser.parse(
                f"${expression.latex}$",
                dpi=120,
                prop=FontProperties(size=18),
            )
            alpha = np.asarray(parsed.image)
            rgba = np.empty((*alpha.shape, 4), dtype=np.uint8)
            color = self.palette().color(self.foregroundRole()).getRgb()
            rgba[:, :, :3] = color[:3]
            rgba[:, :, 3] = alpha
            image = QImage(
                rgba.data,
                alpha.shape[1],
                alpha.shape[0],
                int(rgba.strides[0]),
                QImage.Format.Format_RGBA8888,
            ).copy()
            self.previewLabel.setPixmap(QPixmap.fromImage(image))
            self.previewLabel.adjustSize()
        except Exception as error:
            self.previewLabel.clear()
            self.previewLabel.setAccessibleDescription(
                "MathText could not render this formula preview."
            )
            self.errorLabel.setText(f"MathText preview failed: {error}")
            self.formulaEdit.setAccessibleDescription(self.errorLabel.text())
            self._expression = expression
            return
        self.previewLabel.setAccessibleDescription(f"Rendered expression: {text}")
        self.formulaEdit.setAccessibleDescription(
            "Enter an explicit multiplication expression using t for time."
        )
        self._expression = expression

    def _insertText(self, text: str) -> None:
        start = self.formulaEdit.selectionStart()
        if start < 0:
            start = self.formulaEdit.cursorPosition()
        self.formulaEdit.insert(text)
        if text.endswith("()"):
            self.formulaEdit.setCursorPosition(start + len(text) - 1)
