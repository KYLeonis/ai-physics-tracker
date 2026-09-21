"""Pendulum experiment setup 的侧栏面板、创建向导与物理参数对话框（P1.1-S5）。

只做显示与交互：业务事实经 `ProjectSession` 动作落地，本模块不直接改
Project。向导只收集 destination + 四 role draft，迁移执行在
ProjectActions 的后台线程完成。
"""

from pathlib import Path
from uuid import UUID

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.application.pendulum_setup import pendulum_setup_status
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.domain.pendulum import (
    ROLE_ORDER,
    PendulumRoles,
    PhysicalParameters,
)
from ai_physics_tracker.domain.track import Track

_ROLE_DESCRIPTIONS = {
    "tip": "the pendulum bob / marker tip",
    "body_top": "top end of the suspension rod or body",
    "body_bottom": "bottom end of the rod or body (near the bob)",
    "pivot": "the fixed suspension point (tracked for quality checks only)",
}

_GAP_LABELS = {
    "fixed_pivot": "fixed pivot on the video",
    "true_vertical": "true vertical (top→bottom)",
    "true_vertical_confirmation": "vertical direction confirmation",
    "active_calibration": "active scale calibration",
    "physical_parameters": "physical L and g",
    "release_frame": "release frame",
}


class PendulumSetupPanel(QGroupBox):
    """侧栏 checklist：每项显示状态并提供对应入口；无 experiment 时隐藏。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Pendulum experiment", parent)
        self._experiment_id: UUID | None = None

        self.statusLabel = QLabel("Setup incomplete", self)
        self.statusLabel.setWordWrap(True)

        self.scaleLabel = QLabel("scale: not set (uses Calibration)", self)
        self.pivotButton = QPushButton("Mark fixed pivot", self)
        self.pivotLabel = QLabel("fixed pivot: not set", self)
        self.verticalButton = QPushButton("Mark vertical (top→bottom)", self)
        self.verticalLabel = QLabel("true vertical: not set", self)
        self.confirmVerticalButton = QPushButton("Confirm direction", self)
        self.confirmVerticalButton.setEnabled(False)
        self.confirmVerticalButton.setToolTip(
            "Confirm that the marked direction (first point = top) points downward "
            "along gravity"
        )
        self.physicalButton = QPushButton("Enter L and g…", self)
        self.physicalLabel = QLabel("L / g: not set", self)
        self.releaseButton = QPushButton("Set release to current frame", self)
        self.releaseLabel = QLabel("release frame: not set", self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.statusLabel)
        layout.addWidget(self.scaleLabel)
        for label, button in (
            (self.pivotLabel, self.pivotButton),
            (self.verticalLabel, self.verticalButton),
            (self.physicalLabel, self.physicalButton),
        ):
            row = QHBoxLayout()
            row.addWidget(label, 1)
            row.addWidget(button)
            layout.addLayout(row)
        layout.addWidget(self.confirmVerticalButton)
        layout.addWidget(self.releaseButton)
        layout.addWidget(self.releaseLabel)
        self.hide()

    def experimentId(self) -> UUID | None:
        return self._experiment_id

    def refresh(self, session: ProjectSession | None, video_id: UUID | None) -> None:
        """从 experiment 事实重建 checklist；不构成第二套 workflow 真值。"""

        experiment = None
        if session is not None and video_id is not None:
            experiment = next(
                (
                    item
                    for item in session.pendulum_experiments()
                    if item.video_id == video_id
                ),
                None,
            )
        if experiment is None:
            self._experiment_id = None
            self.hide()
            return
        self._experiment_id = experiment.experiment_id
        self.show()
        status = pendulum_setup_status(session.project, experiment)
        self.scaleLabel.setText(
            "scale: set (active calibration)"
            if status.scale_calibration_id is not None
            else "scale: not set — use Calibration"
        )
        geometry = experiment.geometry

        if status.fixed_pivot_set and geometry.fixed_pivot_px is not None:
            self.pivotLabel.setText(
                f"fixed pivot: ({geometry.fixed_pivot_px[0]:.1f}, "
                f"{geometry.fixed_pivot_px[1]:.1f}) px"
            )
        else:
            self.pivotLabel.setText("fixed pivot: not set")

        vertical = geometry.true_vertical
        if status.true_vertical_confirmed:
            self.verticalLabel.setText(
                "true vertical: set — direction confirmed (top→bottom = down)"
            )
        elif status.true_vertical_present and vertical is not None:
            self.verticalLabel.setText(
                "true vertical: set — direction NOT confirmed yet"
            )
        else:
            self.verticalLabel.setText("true vertical: not set")
        self.confirmVerticalButton.setEnabled(
            status.true_vertical_present and not status.true_vertical_confirmed
        )

        if status.physical_set and experiment.physical is not None:
            self.physicalLabel.setText(
                f"L = {experiment.physical.length_m:.3f} m, "
                f"g = {experiment.physical.g_m_s2:.2f} m/s²"
            )
        else:
            self.physicalLabel.setText("L / g: not set")

        if status.release_set:
            self.releaseLabel.setText(
                f"release frame: {experiment.release_frame_index}"
            )
        else:
            self.releaseLabel.setText(
                "release frame: not set (annotation works; analysis needs it)"
            )

        if status.can_analyze:
            self.statusLabel.setText("Setup complete — analysis enabled")
        elif status.missing_for_analysis:
            self.statusLabel.setText(
                "Setup incomplete — missing: "
                + ", ".join(
                    _GAP_LABELS.get(gap, gap) for gap in status.missing_for_analysis
                )
            )


class PendulumWizardDialog(QDialog):
    """收集 destination（仅 v1 迁移路径）与完整四 role draft。

    只做输入收集与本地校验；执行（迁移/首存/创建 experiment）由调用方
    在后台线程完成。`require_destination=False` 用于已 publication 项目
    上直接创建 experiment。
    """

    def __init__(
        self,
        tracks: list[Track],
        *,
        require_destination: bool = True,
        first_save: bool = False,
        default_destination: str = "",
        create_track: Callable[[str], Track] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Pendulum experiment")
        self.setMinimumWidth(520)
        self._require_destination = require_destination
        self._create_track = create_track

        layout = QVBoxLayout(self)

        if require_destination:
            if first_save:
                intro_text = (
                    "This saves the project as a NEW publication project "
                    "(schema v2) at the chosen directory.\n"
                    "Nothing is discarded — this is simply the project's first "
                    "save, in the publication format.")
            else:
                intro_text = (
                    "This saves a NEW publication copy of the project in "
                    "schema v2.\n"
                    "The current project stays untouched and can still be "
                    "opened on its own.")
            intro = QLabel(intro_text, self)
            intro.setWordWrap(True)
            layout.addWidget(intro)
            destRow = QHBoxLayout()
            self.destinationEdit = QLineEdit(default_destination, self)
            browseButton = QPushButton("Choose…", self)
            browseButton.clicked.connect(self._browse)
            destRow.addWidget(self.destinationEdit, 1)
            destRow.addWidget(browseButton)
            layout.addLayout(destRow)
        else:
            self.destinationEdit = None
            note = QLabel(
                "This project is already a publication project; the wizard only "
                "creates the experiment.", self)
            note.setWordWrap(True)
            layout.addWidget(note)

        rolesGroup = QGroupBox("Four landmark roles", self)
        rolesLayout = QVBoxLayout(rolesGroup)
        self._role_combos: dict[str, QComboBox] = {}
        for role in ROLE_ORDER:
            label = QLabel(f"{role} — {_ROLE_DESCRIPTIONS[role]}", rolesGroup)
            combo = QComboBox(rolesGroup)
            for track in tracks:
                combo.addItem(track.name, str(track.track_id))
            self._role_combos[role] = combo
            if create_track is not None:
                new_button = QPushButton(f"New track for {role}", rolesGroup)
                new_button.clicked.connect(
                    lambda _checked=False, r=role: self._create_track_for_role(r)
                )
                row = QHBoxLayout()
                row.addWidget(combo, 1)
                row.addWidget(new_button)
                rolesLayout.addWidget(label)
                rolesLayout.addLayout(row)
            else:
                rolesLayout.addWidget(label)
                rolesLayout.addWidget(combo)
        # ≥4 track 时预填四个互不相同的 track，避免首点 Create 必报重复
        if len(tracks) >= len(ROLE_ORDER):
            for index, role in enumerate(ROLE_ORDER):
                self._role_combos[role].setCurrentIndex(index)
        layout.addWidget(rolesGroup)

        self.errorLabel = QLabel("", self)
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setStyleSheet("color: #b00020;")
        layout.addWidget(self.errorLabel)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_track_for_role(self, role: str) -> None:
        if self._create_track is None:
            return
        try:
            track = self._create_track(role)
        except Exception as error:  # session guard 拒绝时只提示，不关闭向导
            self.errorLabel.setText(f"Could not create track: {error}")
            return
        self.set_role_track(role, track)
        self.errorLabel.setText("")

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose a NEW project directory (publication copy)"
        )
        if selected:
            self.destinationEdit.setText(selected)

    def _validate_and_accept(self) -> None:
        error = self.validate()
        if error is not None:
            self.errorLabel.setText(error)
            return
        self.errorLabel.setText("")
        self.accept()

    def destination(self) -> Path:
        return Path(self.destinationEdit.text().strip())

    def selected_roles(self) -> dict[str, UUID | None]:
        roles: dict[str, UUID | None] = {}
        for role, combo in self._role_combos.items():
            data = combo.currentData()
            roles[role] = UUID(data) if data else None
        return roles

    def set_role_track(self, role: str, track: Track) -> None:
        """外部创建新 track 后回填并选中。"""

        combo = self._role_combos[role]
        index = combo.findData(str(track.track_id))
        if index < 0:
            combo.addItem(track.name, str(track.track_id))
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    def validate(self) -> str | None:
        roles = self.selected_roles()
        missing = [role for role, track_id in roles.items() if track_id is None]
        if not roles or missing:
            return "Select a track for every role: " + ", ".join(missing)
        distinct = {track_id for track_id in roles.values() if track_id is not None}
        if len(distinct) != len(ROLE_ORDER):
            return "Each role needs a different track (one track cannot play two roles)."
        if self._require_destination:
            text = self.destinationEdit.text().strip()
            if not text:
                return "Choose a destination directory for the publication copy."
            destination = Path(text)
            if destination.exists():
                return f"Destination already exists: {destination}\nChoose a new, empty directory name."
        return None

    def pendulum_roles(self) -> PendulumRoles:
        roles = self.selected_roles()
        return PendulumRoles(
            tip=roles["tip"],
            body_top=roles["body_top"],
            body_bottom=roles["body_bottom"],
            pivot=roles["pivot"],
        )


class PhysicalParametersDialog(QDialog):
    """录入 effective pivot-to-COM 长度 L、重力 g 与各自来源。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pendulum physical parameters")
        form = QFormLayout(self)

        self.lengthSpin = QDoubleSpinBox(self)
        self.lengthSpin.setRange(0.001, 100.0)
        self.lengthSpin.setDecimals(4)
        self.lengthSpin.setSuffix(" m")
        self.lengthSpin.setToolTip(
            "Effective pivot-to-center-of-mass length (measure with a ruler; "
            "do not estimate from the bob radius)"
        )
        form.addRow("L (pivot to center of mass):", self.lengthSpin)

        self.lengthSourceEdit = QLineEdit(self)
        self.lengthSourceEdit.setPlaceholderText("how L was measured, e.g. ruler")
        form.addRow("L source:", self.lengthSourceEdit)

        self.gSpin = QDoubleSpinBox(self)
        self.gSpin.setRange(0.1, 100.0)
        self.gSpin.setDecimals(4)
        self.gSpin.setSuffix(" m/s²")
        self.gSpin.setValue(9.81)
        form.addRow("g:", self.gSpin)

        self.gSourceEdit = QLineEdit(self)
        self.gSourceEdit.setPlaceholderText("where g comes from, e.g. standard 9.81")
        self.gSourceEdit.setText("standard gravity 9.81 m/s²")
        form.addRow("g source:", self.gSourceEdit)

        self.errorLabel = QLabel("", self)
        self.errorLabel.setStyleSheet("color: #b00020;")
        self.errorLabel.setWordWrap(True)
        form.addRow(self.errorLabel)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _validate_and_accept(self) -> None:
        if self.validate() is None:
            self.accept()

    def validate(self) -> str | None:
        if self.lengthSpin.value() <= 0:
            return "L must be positive."
        if not self.lengthSourceEdit.text().strip():
            return "Describe how L was measured (provenance is required)."
        if not self.gSourceEdit.text().strip():
            return "Describe where g comes from (provenance is required)."
        return None

    def physical_parameters(self) -> PhysicalParameters:
        return PhysicalParameters(
            length_m=self.lengthSpin.value(),
            g_m_s2=self.gSpin.value(),
            length_source=self.lengthSourceEdit.text().strip(),
            g_source=self.gSourceEdit.text().strip(),
        )
