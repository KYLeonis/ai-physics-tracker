"""固定验证集管理对话框：从当前 manual points 勾选并冻结创建，或删除已有 series。"""

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.refinement_history import (
    extract_refinement_state,
)


class ManageValidationDialog(QDialog):
    """固定验证集管理对话框。"""

    def __init__(
        self,
        session: ProjectSession,
        track_id: UUID,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Fixed Validation Series")
        self.resize(440, 520)

        self._session = session
        self._track_id = track_id

        track = next((t for t in session.tracks if t.track_id == track_id), None)
        track_name = track.name if track else "Unknown Track"
        ref_state = session.get_refinement_state(track_id)
        active_series = ref_state.active_series

        layout = QVBoxLayout(self)

        info_label = QLabel(f"Track: <b>{track_name}</b>")
        layout.addWidget(info_label)

        status_group = QGroupBox("Active Validation Series")
        status_layout = QVBoxLayout()
        if active_series:
            val_valid, val_reason = session.validate_active_validation_series(track_id)
            val_desc = "Valid" if val_valid else f"Invalid ({val_reason or 'modified'})"
            cur_label = QLabel(
                f"<b>{active_series.name}</b>: {len(active_series.label_snapshots)} frames ({val_desc})\n"
                f"Created at: {active_series.created_at}"
            )
            cur_label.setWordWrap(True)
            status_layout.addWidget(cur_label)

            self.deleteButton = QPushButton("Delete Active Series")
            self.deleteButton.clicked.connect(self._on_delete_active_series)
            status_layout.addWidget(self.deleteButton)
        else:
            cur_label = QLabel("No active validation series set.")
            status_layout.addWidget(cur_label)
            self.deleteButton = None
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        create_group = QGroupBox("Freeze New Validation Series")
        create_layout = QVBoxLayout()

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Series Name:"))
        default_name = f"Validation Set {len(ref_state.validation_series) + 1}"
        self.nameEdit = QLineEdit(default_name)
        name_layout.addWidget(self.nameEdit)
        create_layout.addLayout(name_layout)

        create_layout.addWidget(
            QLabel("Select manual points to freeze as fixed validation test set:")
        )

        manual_points = session.manual_points(track_id)
        self._checkboxes: list[tuple[int, QCheckBox]] = []
        point_list_widget = QWidget()
        point_list_layout = QVBoxLayout(point_list_widget)
        point_list_layout.setContentsMargins(4, 4, 4, 4)

        active_val_frames = set(active_series.frame_indices) if active_series else set()

        for pt in manual_points:
            cb = QCheckBox(f"Frame {pt.frame_index}: ({pt.pixel_x:.1f}, {pt.pixel_y:.1f})")
            if pt.frame_index in active_val_frames:
                cb.setChecked(True)
            point_list_layout.addWidget(cb)
            self._checkboxes.append((pt.frame_index, cb))

        if not manual_points:
            point_list_layout.addWidget(QLabel("No manual points marked on this track."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(point_list_widget)
        scroll.setMaximumHeight(180)
        create_layout.addWidget(scroll)

        self.freezeButton = QPushButton("Freeze & Activate Series")
        self.freezeButton.setEnabled(len(manual_points) >= 4)
        self.freezeButton.clicked.connect(self._on_freeze_series)
        create_layout.addWidget(self.freezeButton)

        create_group.setLayout(create_layout)
        layout.addWidget(create_group)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_freeze_series(self) -> None:
        name = self.nameEdit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Series name must not be blank.")
            return

        selected_frames = [
            f_idx for f_idx, cb in self._checkboxes if cb.isChecked()
        ]
        if not selected_frames:
            QMessageBox.warning(
                self,
                "No Frames Selected",
                "Please select at least 1 manual point for the validation series.",
            )
            return

        total_manual = len(self._checkboxes)
        remaining_train = total_manual - len(selected_frames)
        if remaining_train < 3:
            QMessageBox.warning(
                self,
                "Insufficient Training Frames",
                f"Selecting {len(selected_frames)} out of {total_manual} frames leaves "
                f"only {remaining_train} frames for training.\n\n"
                f"DeepLabCut training requires at least 3 distinct training frames.",
            )
            return

        try:
            series = self._session.create_validation_series(
                self._track_id, name, selected_frames
            )
            QMessageBox.information(
                self,
                "Validation Series Created",
                f"Validation series '{series.name}' frozen with {len(series.label_snapshots)} frames.\n"
                f"Remaining {remaining_train} manual frames will be used for training.",
            )
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Error Creating Series", str(err))

    def _on_delete_active_series(self) -> None:
        ref_state = self._session.get_refinement_state(self._track_id)
        active_series = ref_state.active_series
        if not active_series:
            return

        reply = QMessageBox.question(
            self,
            "Delete Validation Series",
            f"Delete active validation series '{active_series.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._session.delete_validation_series(self._track_id, active_series.series_id)
                self.accept()
            except Exception as err:
                QMessageBox.critical(self, "Error Deleting Series", str(err))
