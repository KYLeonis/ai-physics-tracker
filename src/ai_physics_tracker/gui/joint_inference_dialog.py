"""P1.4-S4 联合推理启动对话框:选择模型与推理参数(Qt GUI 层)。

只做选择与参数收集;真正的 prepare/start 由 ExperimentInferenceActions
执行,启动时仍会 live 复核模型有效状态(这里的列表是静态字段快照)。
"""

from __future__ import annotations

from uuid import UUID

from ai_physics_tracker.application.teacher_models import effective_compatibility_state

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
    """选择模型与推理参数；未验证模型先真实自检再推理。"""

    def __init__(self, model_references, parent=None, *, training_runs=()) -> None:
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
        runs = {run.run_id: run for run in training_runs}
        for model in sorted(model_references, key=lambda m: m.created_at, reverse=True):
            state = effective_compatibility_state(model)
            run = runs.get(model.source_train_run_id)
            date = (run.created_at if run else model.created_at).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            item = QListWidgetItem(
                f"{date} · {model.origin} model {str(model.model_id)[:8]} — {state}"
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
            "confident predictions. Changing this threshold does not improve "
            "the model. After relabeling, train again and select the new model "
            "here to use the updated labels.", self)
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
        if self.modelList.count():
            self.modelList.setCurrentRow(0)
        self._refresh_ok()

    def _refresh_ok(self, *_args) -> None:
        model = self._selected_model()
        state = effective_compatibility_state(model) if model else None
        compatible = state == "compatible"
        self._ok_button.setEnabled(state in ("compatible", "unverified"))
        self._ok_button.setText("Run inference" if compatible else "Verify & run")
        if model is None:
            self.hintLabel.setText(
                _ROLE_HINT if self._models else
                "No model references yet — run joint training or import a "
                "teacher model first.")
        elif compatible:
            self.hintLabel.setText(
                "Ready: the model self-test passed on this machine. The "
                "worker re-verifies every input file before running.")
        elif state == "unverified":
            self.hintLabel.setText(
                "This model has not been checked yet. Verify & run loads it and "
                "tests one frame, then starts inference automatically if successful. "
                "Progress and Cancel appear in Activity.")
        else:
            self.hintLabel.setText(f"Model is {state}; inference cannot start. Check its files or import a working model.")

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

    session = window.analysisSession
    dialog = JointInferenceDialog(
        model_references, window,
        training_runs=session.tracking_runs() if session else ())
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    model_id = dialog.selected_model_id()
    if model_id is None:
        return None
    min_confidence, batch_size = dialog.inference_parameters()
    return model_id, InferenceParams(
        min_confidence=min_confidence, batch_size=batch_size, device="cpu")
