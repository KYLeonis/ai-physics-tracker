"""标定已知长度与单位输入对话框。"""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class CalibrationDialog(QDialog):
    """弹出对话框：输入已知长度、单位与标定名称。"""

    def __init__(
        self,
        pixel_length: float,
        default_name: str = "Calibration 1",
        default_length: float = 1.0,
        default_unit: str = "mm",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set Scale Calibration")
        self.setModal(True)
        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.pixelLabel = QLabel(f"{pixel_length:.2f} px", self)
        self.lengthSpinBox = QDoubleSpinBox(self)
        self.lengthSpinBox.setRange(0.0001, 1000000.0)
        self.lengthSpinBox.setDecimals(4)
        self.lengthSpinBox.setValue(default_length)

        self.unitComboBox = QComboBox(self)
        self.unitComboBox.addItems(["m", "cm", "mm"])
        self.unitComboBox.setCurrentText(default_unit)

        self.nameEdit = QLineEdit(self)
        self.nameEdit.setText(default_name)

        form.addRow("Measured length:", self.pixelLabel)
        form.addRow("Known real length:", self.lengthSpinBox)
        form.addRow("Unit:", self.unitComboBox)
        form.addRow("Name:", self.nameEdit)
        layout.addLayout(form)

        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addWidget(self.buttonBox)

    def known_length(self) -> float:
        return self.lengthSpinBox.value()

    def unit(self) -> str:
        return self.unitComboBox.currentText()

    def calibration_name(self) -> str:
        return self.nameEdit.text().strip()
