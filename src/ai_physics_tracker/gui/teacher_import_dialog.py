"""教师模型导入向导(P1.3-S6):目录→安全解析→显式映射→受管导入。

身份规则与 application/teacher_import 一致:四 role 必须显式映射到
config bodyparts(默认同名直映,改名后由用户逐 role 选择);checkpoint
从 bundle 文件中选择;检测到 pose_cfg.yaml 才能事后 runtime 自检。
对话框只做收集与预检,导入事务经 session.import_teacher_model。
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ai_physics_tracker.application.project_session import ProjectSessionError
from ai_physics_tracker.application.teacher_import import (
    TeacherImportError,
    parse_teacher_config,
)
from ai_physics_tracker.application.teacher_models import resolve_pose_cfg_path
from ai_physics_tracker.domain.pendulum import ROLE_ORDER

logger = logging.getLogger(__name__)


def propose_identity_mapping(bodyparts: list[str]) -> dict[str, str | None]:
    """默认映射:与规范 role 同名的 bodypart 直映,否则留空待用户选择。"""

    return {role: (role if role in bodyparts else None) for role in ROLE_ORDER}


class TeacherImportDialog(QDialog):
    def __init__(self, window, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self._bundle_root: Path | None = None
        self._config: dict | None = None
        self._config_name: str = "config.yaml"
        self.setWindowTitle("Import DLC Model…")
        self.resize(760, 560)
        self.setSizeGripEnabled(True)

        self.directory_edit = QLineEdit(self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._browse)
        self.status_label = QLabel("Choose the teacher bundle directory (holds config.yaml).", self)
        self.status_label.setWordWrap(True)

        self.role_boxes: dict[str, QComboBox] = {}
        form = QFormLayout()
        for role in ROLE_ORDER:
            box = QComboBox(self)
            self.role_boxes[role] = box
            form.addRow(f"{role} ←", box)

        self.checkpoint_box = QComboBox(self)
        self.checkpoint_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.checkpoint_box.setMinimumContentsLength(48)
        form.addRow("Checkpoint", self.checkpoint_box)
        self.pose_cfg_label = QLabel("pose_cfg: —", self)
        self.pose_cfg_label.setWordWrap(True)
        form.addRow("", self.pose_cfg_label)

        self.selftest_checkbox = QCheckBox(
            "Run compatibility self-test after import (needs pose_cfg)", self)
        self.selftest_checkbox.setChecked(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        dir_row = QVBoxLayout()
        dir_row.addWidget(self.directory_edit)
        dir_row.addWidget(browse)
        layout.addLayout(dir_row)
        layout.addWidget(self.status_label)
        layout.addLayout(form)
        layout.addWidget(self.selftest_checkbox)
        layout.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setEnabled(False)

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Teacher bundle directory", str(Path.home())
        )
        if selected:
            self.directory_edit.setText(selected)
            self.load_bundle(Path(selected))

    def load_bundle(self, bundle_root: Path) -> bool:
        self._bundle_root = None
        self._config_name = "config.yaml"
        self._ok_button.setEnabled(False)
        # DLC 3.x pytorch 引擎的模型结构配置原生名是 pytorch_config.yaml;
        # 向导同时接受两者,导入时统一落为 managed config.yaml
        for name in ("config.yaml", "pytorch_config.yaml"):
            if (bundle_root / name).is_file():
                self._config_name = name
                break
        else:
            self.status_label.setText(
                "No config.yaml / pytorch_config.yaml at the bundle root.")
            return False
        config_path = bundle_root / self._config_name
        try:
            config = parse_teacher_config(config_path)
        except TeacherImportError as error:
            self.status_label.setText(str(error))
            return False
        self._bundle_root = bundle_root
        self._config = config
        bodyparts = list(config["bodyparts"])
        proposed = propose_identity_mapping(bodyparts)
        for role, box in self.role_boxes.items():
            box.clear()
            box.addItems(bodyparts)
            # M3(S6 review):未选状态必须是"空",否则 QComboBox 自动选中
            # 第 0 项会让漏选 role 静默落到一个用户从未显式选择的 bodypart
            box.setCurrentIndex(-1)
            default = proposed[role]
            if default is not None:
                box.setCurrentText(default)
        # HR 2026-09-29:真实 DLC 训练产物是嵌套布局(checkpoint 与
        # pytorch_config 在 dlc-models-pytorch/**/train/ 深处),根目录扫描
        # 会得到空 checkpoint 下拉——改为递归搜索,显示相对路径
        self.checkpoint_box.clear()
        checkpoints = sorted(
            p.relative_to(bundle_root).as_posix()
            for p in bundle_root.rglob("*")
            if p.is_file() and p.suffix in {".pt", ".pth"}
            and ".staging" not in p.parts
        )
        self.checkpoint_box.addItems(checkpoints)
        pose_candidates = sorted(
            p.relative_to(bundle_root).as_posix()
            for p in bundle_root.rglob("*")
            if p.is_file()
            and p.name in ("pose_cfg.yaml", "pytorch_config.yaml")
            and p.parent != bundle_root
            and ".staging" not in p.parts
        )
        pose_found = bool(pose_candidates) or (bundle_root / "pose_cfg.yaml").is_file()
        self.pose_cfg_label.setText(
            f"model cfg for self-test: "
            + (f"detected ({', '.join(pose_candidates[:2])})"
               if pose_candidates
               else ('detected (pose_cfg.yaml)' if pose_found
                     else "NOT found (self-test unavailable)"))
        )
        self.selftest_checkbox.setEnabled(pose_found)
        self.selftest_checkbox.setChecked(pose_found)
        self.status_label.setText(
            f"Bundle loaded ({self._config_name}): {len(bodyparts)} bodyparts "
            f"{bodyparts}. "
            "Map every role explicitly, then Import."
        )
        self._ok_button.setEnabled(bool(self.checkpoint_box.count()))
        return True

    def collect_mapping(self) -> tuple[tuple[str, str], ...] | None:
        mapping: list[tuple[str, str]] = []
        for role in ROLE_ORDER:
            value = self.role_boxes[role].currentText()
            if not value:
                self.status_label.setText(f"Role {role!r} is not mapped yet.")
                return None
            mapping.append((role, value))
        targets = [t for _r, t in mapping]
        if len(set(targets)) != len(targets):
            self.status_label.setText("Two roles map to the same bodypart.")
            return None
        return tuple(mapping)

    def accept(self) -> None:
        session = self.window.analysisSession
        if session is None or self._bundle_root is None or self._config is None:
            return
        mapping = self.collect_mapping()
        if mapping is None:
            return
        checkpoint = self.checkpoint_box.currentText()
        if not checkpoint:
            return
        extra_files: tuple[str, ...] = ()
        # 自检模型配置:只收 train/pytorch_config.yaml(HR 2026-09-29:此前
        # 把 test/pose_cfg.yaml 误当模型配置,worker 的 PoseConfig 校验必炸);
        # 多 shuffle 时取含 train/ 的第一个
        candidates = sorted(
            p.relative_to(self._bundle_root).as_posix()
            for p in self._bundle_root.rglob("pytorch_config.yaml")
            if p.is_file() and ".staging" not in p.parts
        )
        train_matches = [c for c in candidates if "/train/" in f"/{c}"]
        if train_matches:
            extra_files = (train_matches[0],)
        elif candidates:
            extra_files = (candidates[0],)
        try:
            reference = session.import_teacher_model(
                self._bundle_root, self._config_name, checkpoint, mapping,
                extra_files=extra_files,
            )
        except (ProjectSessionError, TeacherImportError) as error:
            self.status_label.setText(f"Import failed: {error}")
            return
        self.window.statusBar().showMessage(
            f"Teacher model {reference.model_id} imported (unverified)")
        self.window.projectActions.refresh()
        self.reference = reference
        super().accept()


def run_import_dialog(window, model_actions) -> bool:
    """打开导入向导;成功后按勾选发起 runtime 自检。返回是否导入成功。"""

    dialog = TeacherImportDialog(window)
    dialog.reference = None
    if dialog.exec() != QDialog.DialogCode.Accepted or dialog.reference is None:
        return False
    if dialog.selftest_checkbox.isChecked():
        model_actions.runSelftest(dialog.reference.model_id)
    return True
