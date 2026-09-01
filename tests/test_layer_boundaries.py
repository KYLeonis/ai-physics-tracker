"""基于 AST 的分层依赖回归检查（architecture.md §1 / CODE_STANDARD.md §4）。

字符串包含式检查无法发现跨包私有 import 与组合根旁路（review F4），
这里直接解析 import 语句并按层规则断言。

已接受的现状（不视为违规）：
- application → infrastructure 的**公共**符号 import（如 DLCAdapter）；
  infrastructure → application.tracking_types 的值对象 import。
  双向私有符号（下划线开头）被下方规则禁止。
"""

import ast
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "ai_physics_tracker"
DLC_ADAPTER = PACKAGE_ROOT / "infrastructure" / "dlc_adapter.py"

# 层 → 禁止 import 的本包兄弟层
FORBIDDEN_PACKAGE_IMPORTS: dict[str, set[str]] = {
    "domain": {"application", "gui", "infrastructure"},
    "application": {"gui"},
    "gui": {"infrastructure"},
    "infrastructure": {"gui"},
}

# 层 → 禁止 import 的第三方顶层包
FORBIDDEN_THIRD_PARTY: dict[str, set[str]] = {
    "domain": {"PySide6", "cv2", "deeplabcut"},
    "application": {"PySide6", "cv2", "deeplabcut"},
    "gui": {"cv2", "deeplabcut"},
}


def _layer_of(path: Path) -> str | None:
    relative = path.relative_to(PACKAGE_ROOT)
    if len(relative.parts) == 1:
        return None  # 顶层模块（__main__ 等）不参与层规则
    return relative.parts[0]


def _collect_imports(path: Path) -> list[tuple[int, str, int, list[str]]]:
    """返回 (行号, 绝对模块或 None, relative level, 导入名列表)。"""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    collected: list[tuple[int, str, int, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                collected.append((node.lineno, alias.name, 0, []))
        elif isinstance(node, ast.ImportFrom):
            collected.append(
                (
                    node.lineno,
                    node.module,
                    node.level or 0,
                    [alias.name for alias in node.names],
                )
            )
    return collected


def _violations(
    *,
    package_rules: bool,
    third_party_rules: bool,
    private_rules: bool,
    deeplabcut_rules: bool,
) -> list[str]:
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        layer = _layer_of(path)
        for lineno, module, level, names in _collect_imports(path):
            if level > 0 or module is None:
                continue  # 相对导入不跨层；本项目 src 一律绝对导入
            root = module.split(".")[0]
            if root == "ai_physics_tracker":
                parts = module.split(".")
                target_layer = parts[1] if len(parts) > 1 else "root"
                if (
                    package_rules
                    and layer is not None
                    and target_layer in FORBIDDEN_PACKAGE_IMPORTS.get(layer, set())
                ):
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT)}:{lineno} 层违规："
                        f"{layer} 不得 import {module}"
                    )
                if (
                    private_rules
                    and layer is not None
                    and target_layer != "root"
                    and target_layer != layer
                    and any(name.startswith("_") for name in names)
                ):
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT)}:{lineno} 跨包私有符号："
                        f"不得从 {module} import 下划线名称 {names}"
                    )
                continue
            if (
                third_party_rules
                and layer is not None
                and root in FORBIDDEN_THIRD_PARTY.get(layer, set())
            ):
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{lineno} 第三方违规："
                    f"{layer} 不得 import {root}"
                )
            if deeplabcut_rules and root == "deeplabcut" and path != DLC_ADAPTER:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{lineno} deeplabcut 只允许出现在 "
                    f"infrastructure/dlc_adapter.py"
                )
    return violations


def test_layer_package_dependency_rules() -> None:
    assert _violations(
        package_rules=True,
        third_party_rules=False,
        private_rules=False,
        deeplabcut_rules=False,
    ) == []


def test_layer_third_party_rules() -> None:
    assert _violations(
        package_rules=False,
        third_party_rules=True,
        private_rules=False,
        deeplabcut_rules=False,
    ) == []


def test_deeplabcut_confined_to_dlc_adapter() -> None:
    assert _violations(
        package_rules=False,
        third_party_rules=False,
        private_rules=False,
        deeplabcut_rules=True,
    ) == []


def test_no_cross_package_private_imports() -> None:
    assert _violations(
        package_rules=False,
        third_party_rules=False,
        private_rules=True,
        deeplabcut_rules=False,
    ) == []


def test_detector_flags_planted_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 检测器自检：植入已知违规，确保各规则不是空转
    module = sys.modules[__name__]
    package = tmp_path / "ai_physics_tracker"
    (package / "domain").mkdir(parents=True)
    (package / "application").mkdir()
    (package / "infrastructure").mkdir()
    (package / "domain" / "bad.py").write_text(
        "from ai_physics_tracker.application.session import _secret\n"
        "import cv2\n"
        "from ai_physics_tracker.gui.main_window import MainWindow\n",
        encoding="utf-8",
    )
    (package / "application" / "uses_dlc.py").write_text(
        "import deeplabcut\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PACKAGE_ROOT", package)
    monkeypatch.setattr(
        module, "DLC_ADAPTER", package / "infrastructure" / "dlc_adapter.py"
    )

    package_hits = "\n".join(
        _violations(
            package_rules=True,
            third_party_rules=False,
            private_rules=False,
            deeplabcut_rules=False,
        )
    )
    assert "gui 不得 import" in package_hits or "domain 不得 import" in package_hits

    third_party_hits = "\n".join(
        _violations(
            package_rules=False,
            third_party_rules=True,
            private_rules=False,
            deeplabcut_rules=False,
        )
    )
    assert "cv2" in third_party_hits
    assert "deeplabcut" in third_party_hits

    private_hits = "\n".join(
        _violations(
            package_rules=False,
            third_party_rules=False,
            private_rules=True,
            deeplabcut_rules=False,
        )
    )
    assert "_secret" in private_hits

    confined_hits = "\n".join(
        _violations(
            package_rules=False,
            third_party_rules=False,
            private_rules=False,
            deeplabcut_rules=True,
        )
    )
    assert "uses_dlc.py" in confined_hits
