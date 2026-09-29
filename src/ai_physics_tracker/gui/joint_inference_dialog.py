"""P1.4-S4 联合推理启动对话框:选 compatible 模型与推理参数(Qt GUI 层)。

只做选择与参数收集;真正的 prepare/start 由 ExperimentInferenceActions
执行,启动时仍会 live 复核模型有效状态(这里的列表是静态字段快照)。
"""

from __future__ import annotations

from uuid import UUID

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

_ROLE_HINT = (
    "Only models marked compatible can run. A model becomes compatible "
    "after a successful self-test on this machine."
)


class JointInferenceDialog(QDialog):
    """选择一个 compatible 模型并设定 min confidence / batch size。"""

    def __init__(self, model_references, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run joint inference")
        self.setMinimumWidth(460)
        self._models = {
            model.model_id: model for model in model_references
        }

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Track all four landmark roles once with one model. The result "
            "is a candidate only — nothing is written to the tracks until "
            "you review and activate it."))
        self.modelList = QListWidget(self)
        self.modelList.setMaximumHeight(160)
        for model in model_references:
            state = model.compatibility_state
            item = QListWidgetItem(
                f"{model.origin} model {str(model.model_id)[:8]} — {state}"
            )
            item.setData(0x0100, model.model_id)   # Qt.ItemDataRole.UserRole
            self.modelList.addItem(item)
        self.modelList.currentRowChanged.connect(self._refresh_ok)
        layout.addWidget(self.modelList)
        self.hintLabel = QLabel(self)
        self.hintLabel.setWordWrap(True)
        layout.addWidget(self.hintLabel)

        form = QFormLayout()
        self.confidenceSpin = QDoubleSpinBox(self)
        self.confidenceSpin.setRange(0.0, 1.0)
        self.confidenceSpin.setSingleStep(0.05)
        self.confidenceSpin.setDecimals(2)
        self.confidenceSpin.setValue(0.60)
        form.addRow("Min confidence (screening threshold)", self.confidenceSpin)
        self.batchSpin = QSpinBox(self)
        self.batchSpin.setRange(1, 64)
        self.batchSpin.setValue(8)
        form.addRow("Batch size", self.batchSpin)
        layout.addLayout(form)
        self.thresholdLabel = QLabel(
            "Threshold meaning: predictions with confidence below this value "
            "are flagged in review and are NOT written when you activate the "
            "candidate (those frames become missing data). Lower it (e.g. 0.3) "
            "if activation leaves too many gaps; raise it to keep only "
            "confident predictions.", self)
        self.thresholdLabel.setWordWrap(True)
        layout.addWidget(self.thresholdLabel)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ok_button: QPushButton = buttons.button(
            QDialogButtonBox.StandardButton.Ok)
        self._refresh_ok()

    def _refresh_ok(self, *_args) -> None:
        model = self._selected_model()
        compatible = model is not None and model.compatibility_state == "compatible"
        self._ok_button.setEnabled(compatible)
        if model is None:
            self.hintLabel.setText(
                _ROLE_HINT if self._models else
                "No model references yet — run joint training or import a "
                "teacher model first.")
        elif compatible:
            self.hintLabel.setText(
                "Ready: the model self-test passed on this machine. The "
                "worker re-verifies every input file before running.")
        else:
            self.hintLabel.setText(_ROLE_HINT)

    def _selected_model(self):
        item = self.modelList.currentItem()
        if item is None:
            return None
        return self._models.get(item.data(0x0100))

    def selected_model_id(self) -> UUID | None:
        model = self._selected_model()
        return model.model_id if model is not None else None

    def inference_parameters(self) -> tuple[float, int]:
        return float(self.confidenceSpin.value()), int(self.batchSpin.value())


def run_joint_inference_dialog(window, model_references) -> tuple | None:
    """模态执行;返回 (model_id, InferenceParams) 或 None(取消/不可用)。"""

    from ai_physics_tracker.application.tracking_types import InferenceParams

    dialog = JointInferenceDialog(model_references, window)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    model_id = dialog.selected_model_id()
    if model_id is None:
        return None
    min_confidence, batch_size = dialog.inference_parameters()
    return model_id, InferenceParams(
        min_confidence=min_confidence, batch_size=batch_size, device="cpu")
