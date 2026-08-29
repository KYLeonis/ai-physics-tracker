"""Regression checks for Phase 2 dependency direction."""

from pathlib import Path


def _python_texts(root: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))


def test_domain_and_application_do_not_import_qt() -> None:
    package = Path(__file__).parents[1] / "src" / "ai_physics_tracker"

    assert "PySide6" not in _python_texts(package / "domain")
    assert "PySide6" not in _python_texts(package / "application")


def test_gui_does_not_import_opencv() -> None:
    package = Path(__file__).parents[1] / "src" / "ai_physics_tracker"

    assert "import cv2" not in _python_texts(package / "gui")
    assert "infrastructure" not in _python_texts(package / "gui")
